from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np
import torch

from . import memprobe
from .bridge import build_bridge
from .config import EnvConfig, ModelConfig
from .data import placement_shaped_returns
from .env import MahjongEnv
from .evaluate import evaluate_duplicate_seats
from .global_ev import GlobalEVNet
from .model import PolicyValueNet
from .storage import fsync_dir, load_checkpoint, save_checkpoint
from .types import Observation

LEARNING_SEAT = 0

HISTORY_FILENAME = "history.json"

AUX_LOSS_WEIGHT = 0.1

# Adversarial round 10, high finding: this helper moved to storage.py (so
# `save_checkpoint` there can share it too, instead of duplicating the
# platform guard); kept as a local alias so oracle.py's existing
# `from .ppo import _fsync_dir` keeps working unchanged.
_fsync_dir = fsync_dir


def _write_history_atomic(path: Path, history: List[dict]) -> None:
    """Persist `history` durably: write to a sibling temp file (flushed and
    fsynced before it is ever linked into place), atomically replace, then
    fsync the parent directory, so a crash or power loss -- whether
    mid-write or in the gap between the rename landing and its directory
    entry actually reaching disk -- can never truncate or corrupt the
    existing history.json (adversarial round 9, high finding: the previous
    version fsynced neither the tmp file nor the directory)."""
    tmp = path.with_name(path.name + ".tmp")
    payload = json.dumps(history, indent=2)
    with open(tmp, "w") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def cpu_state_snapshot(model: "torch.nn.Module") -> dict:
    """Detached CPU COPY of a model's params. The .clone() is required: on a
    CPU model .cpu() is a no-op and state_dict() returns live references, so
    without it a 'snapshot' would alias and drift with the live model."""
    return {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}


def default_num_workers() -> int:
    """Hardware-aware default for parallel self-play rollout workers.

    Profiling showed rollout throughput is CPU-core-bound, not memory-bound
    (~380MB/worker, so ~13% RAM at 10 workers on a 24-core/31GB box). Throughput
    scales near-linearly to ~8 workers and keeps climbing with a knee near 16
    (0.61/0.91/1.03 matches/s at 8/16/20). Default to core count minus headroom
    for the main process and the OS, capped so large machines stay sane; override
    with --num-workers.

    Uses the CPUs available to THIS process (affinity/cpuset and cgroup CPU
    quota), not the host total, so an affinity-limited or containerized allocation
    is not oversubscribed.
    """
    try:
        cores = len(os.sched_getaffinity(0))  # Linux: CPUs available to this process
    except AttributeError:  # not available on macOS/Windows
        cores = os.cpu_count() or 4
    quota = _cgroup_cpu_quota()  # cpuset can still be the full host under a CFS quota
    if quota is not None:
        cores = min(cores, max(1, int(quota)))
    return max(1, min(16, cores - 8))


def _cgroup_cpu_quota() -> Optional[float]:
    """Best-effort effective CPU count from the cgroup CPU quota (cgroup v2
    `cpu.max`, then v1 `cfs_quota_us`/`cfs_period_us`). Returns None when there is
    no quota or it can't be read, so callers fall back to the affinity count."""
    try:  # cgroup v2
        with open("/sys/fs/cgroup/cpu.max") as f:
            quota_s, period_s = f.read().split()
        if quota_s != "max":
            quota, period = int(quota_s), int(period_s)
            if quota > 0 and period > 0:
                return quota / period
    except (OSError, ValueError):
        pass
    try:  # cgroup v1
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us") as f:
            quota = int(f.read())
        with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us") as f:
            period = int(f.read())
        if quota > 0 and period > 0:
            return quota / period
    except (OSError, ValueError):
        pass
    return None


@dataclass
class PPOConfig:
    iterations: int = 50
    matches_per_iter: int = 16
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_eps: float = 0.2
    entropy_coef: float = 0.01
    value_coef: float = 0.5
    ppo_epochs: int = 4
    minibatch_size: int = 256
    lr: float = 2e-5
    max_grad_norm: float = 1.0
    normalize_advantages: bool = True
    sample_temperature: float = 1.0
    eval_interval: int = 5
    eval_seeds: int = 80
    eval_start_seed: int = 870000
    match_mode: str = "chongci"
    max_steps_per_episode: Optional[int] = 4000
    num_workers: int = 1
    # Max matches per sequential dispatch round in ParallelB2bCollector; 0 =
    # single dispatch (legacy). Bounds PER-WORKER resident trajectory memory
    # at ~chunk/num_workers matches without changing collected data: matches
    # are seeded per-match, so trajectories are provably chunk-invariant
    # (fh-mj-collect-bench digest parity). Added for data-scale-960
    # Amendment 2 (2026-08-12 consult) — the 960-match preflight OOM'd a
    # 31GB box when each of 10 workers held its full 96-match block.
    collect_dispatch_chunk: int = 0
    # Amendment 5 (data-scale-960, 2026-08-15): keep the full RolloutBatch in
    # HOST memory and synchronously move each minibatch to the update device
    # inside the PPO loop, instead of one full-rollout transfer up front. The
    # Amendment 4 profile measured the full-rollout path at ~23.7GiB projected
    # CUDA allocation at 960 matches — over the 20GiB gate and effectively
    # over the 24GB 4090. Values, permutation RNG (still torch.randperm on the
    # update device), global advantage normalization (still computed on the
    # update device), and optimizer behavior are unchanged; parity is pinned
    # bit-for-bit by test_ppo/test_collect_profile and the on-box gauntlet.
    # No async prefetch or double buffering — synchronous one-minibatch-at-a-
    # time transfer only, per the ruling.
    minibatch_device_transfer: bool = False
    # mortal-scale-scratch Amendment 1 §6: two AdamW parameter groups for
    # --scratch --init-from-bc runs. Parameters loaded from the BC stage
    # (SCRATCH_BC_PREFIXES) train at `lr` throughout; every other parameter
    # (event encoder, value/Q, privileged critic, aux and risk heads) trains at
    # `head_lr` for iterations 1..head_lr_iters, then at `lr`. The optimizer is
    # never rebuilt at the switch -- moments are retained. None = one group.
    head_lr: Optional[float] = None
    head_lr_iters: int = 0
    collector: str = "process"   # "process" (spawn workers) | "batched" (env pool + batched forward)
    pool_slots: int = 128        # concurrent env-pool slots for collector="batched"
    pool_max_size: int = 1
    pool_snapshot_interval: int = 10
    grp_checkpoint: Optional[Path] = None
    grp_placement_values: tuple = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)
    # Placement-reshape experiment (spec 2026-08-21, Option A): additive
    # terminal utility lambda * values[rank] on each seat's final recorded
    # row in collect_b2b_rollouts. values=None disables it entirely (the
    # champion recipe). When enabled, collection fails CLOSED on any match
    # without a complete four-seat terminal standing. The calibration digest
    # pins which Stage-0 collection produced lambda. All three are recipe
    # fields: the resume echo rejects any change.
    placement_bonus_values: Optional[tuple] = None
    placement_bonus_lambda: float = 0.0
    placement_bonus_calibration_digest: str = ""
    device: str = "cpu"
    objective: str = "ppo"       # "ppo" | "ach" (selects the policy update)
    ach_beta: float = 2.0        # hedge/logit trust-region threshold when objective="ach"


@dataclass
class RolloutBatch:
    planes: np.ndarray
    scalars: np.ndarray
    action_mask: np.ndarray
    actions: np.ndarray
    old_logprobs: np.ndarray
    values: np.ndarray
    rewards: np.ndarray
    dones: np.ndarray  # 1.0 at each match's final learning-seat step
    truncated_matches: int = 0  # matches that hit the step limit (no final standings)
    events: np.ndarray | None = None          # [N, W] uint32 packed codec values
    event_lengths: np.ndarray | None = None   # [N] int32 true lengths
    dealin_labels: np.ndarray | None = None   # [N] float32 hindsight deal-in
    rank_labels: np.ndarray | None = None     # [N] int64 rank 0-3 / 4=bust / -1=masked
    # Seed-keyed match-level telemetry (NOT row-aligned; one dict per match,
    # in collection order). Carried separately from the row arrays so it can
    # never misalign them; covered by the collect-bench digest.
    match_telemetry: list | None = None

    def __len__(self) -> int:
        return int(self.actions.shape[0])


_ROLLOUT_ARRAY_FIELDS = (
    "planes", "scalars", "action_mask", "actions",
    "old_logprobs", "values", "rewards", "dones",
)

_ROLLOUT_OPTIONAL_ARRAY_FIELDS = (
    "events", "event_lengths", "dealin_labels", "rank_labels",
)


def concat_rollout_batches(batches: List["RolloutBatch"], consume: bool = False) -> "RolloutBatch":
    """Concatenate per-worker rollout batches into one flat batch. Empty batches
    are skipped; raises if there is nothing to concatenate. Each match is
    self-contained (dones=1 at its final step), so GAE over the concatenation is
    correct without any boundary fix-up.

    With ``consume=True`` each source field is released (set to None) right
    after it is concatenated, so at any moment only ONE field exists in both
    source and destination form. Since planes dominate batch memory, this
    bounds the concat peak near 2x-of-planes instead of 2x-of-everything —
    the difference between fitting and OOM at large matches_per_iter (the
    512x16 run was OOM-killed while assembling worker results). Consumed
    inputs must not be reused.

    The B2b optional fields (events/event_lengths/dealin_labels/rank_labels)
    are small relative to planes, so they skip the consume choreography; they
    must be present in ALL batches or ABSENT in all — a mixed set would
    silently misalign event rows against planes/scalars, so that raises."""
    nonempty = [b for b in batches if len(b) > 0]
    if not nonempty:
        raise RuntimeError("concat_rollout_batches: no rollout data")
    truncated_matches = sum(int(b.truncated_matches) for b in nonempty)
    fields = {}
    for name in _ROLLOUT_ARRAY_FIELDS:
        fields[name] = np.concatenate([getattr(b, name) for b in nonempty], axis=0)
        if consume:
            for b in nonempty:
                setattr(b, name, None)
        memprobe.probe("concat_field", field=name, nbytes=int(fields[name].nbytes),
                       consume=bool(consume), sources=len(nonempty))
    for name in _ROLLOUT_OPTIONAL_ARRAY_FIELDS:
        present = [getattr(b, name) is not None for b in nonempty]
        if all(present):
            fields[name] = np.concatenate([getattr(b, name) for b in nonempty], axis=0)
            memprobe.probe("concat_field", field=name, nbytes=int(fields[name].nbytes),
                           consume=False, sources=len(nonempty))
        elif any(present):
            raise ValueError(
                f"concat_rollout_batches: '{name}' is present in some batches but "
                "not others; this would silently misalign event rows against "
                "planes/scalars."
            )
        else:
            fields[name] = None
    present = [b.match_telemetry is not None for b in nonempty]
    if all(present):
        fields["match_telemetry"] = [t for b in nonempty for t in b.match_telemetry]
    elif any(present):
        raise ValueError("concat_rollout_batches: 'match_telemetry' is present in some batches but not others")
    else:
        fields["match_telemetry"] = None
    result = RolloutBatch(**fields, truncated_matches=truncated_matches)
    memprobe.probe("concat_done", rows=len(result), sources=len(nonempty))
    return result


def masked_policy_distribution(masked_logits: torch.Tensor,
                               validate_args: Optional[bool] = None) -> torch.distributions.Categorical:
    """Categorical over actions; logits are already -inf-masked (finfo.min) for
    illegal actions by PolicyValueNet.forward, so illegal probability is ~0 and
    entropy stays finite. `validate_args=False` skips torch's argument checks,
    which sync the host; the values are identical."""
    return torch.distributions.Categorical(logits=masked_logits, validate_args=validate_args)


def masked_logprob(logits_row: torch.Tensor, temperature: float, action: int) -> float:
    """Log-probability of `action` under the temperature-scaled masked policy
    for ONE decision. `logits_row` is the model's [A] logits row (illegal
    actions already finfo.min-masked). Shared by both B2b collectors so
    `old_logprobs` is the same Torch computation regardless of how the
    action was chosen (sampled, greedy) or batched."""
    scaled = logits_row / max(float(temperature), 1e-6)
    dist = masked_policy_distribution(scaled)
    return float(dist.log_prob(torch.tensor(int(action), device=logits_row.device)))


def masked_logprobs(logits: torch.Tensor, temperature: float, actions: list[int]) -> list[float]:
    """`masked_logprob` for every row of a contiguous [N, A] CPU logits tensor
    in one Categorical. Bit-identical to calling `masked_logprob` per row: the
    division is elementwise and CPU logsumexp reduces each contiguous row with
    the same kernel (pinned by test_masked_logprobs_matches_per_row), at ~1/30
    of the per-row cost."""
    scaled = logits / max(float(temperature), 1e-6)
    dist = masked_policy_distribution(scaled)
    return dist.log_prob(torch.as_tensor(actions, dtype=torch.int64, device=logits.device)).tolist()


def compute_gae(
    rewards: np.ndarray,
    values: np.ndarray,
    dones: np.ndarray,
    gamma: float,
    gae_lambda: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Generalized Advantage Estimation over a flat, time-ordered batch where
    `dones[t]==1` marks the final step of a match. Boundaries reset both the value
    bootstrap and the advantage accumulation via the (1-done) factor."""
    rewards = np.asarray(rewards, dtype=np.float32)
    values = np.asarray(values, dtype=np.float32)
    dones = np.asarray(dones, dtype=np.float32)
    n = rewards.shape[0]
    advantages = np.zeros(n, dtype=np.float32)
    last_adv = 0.0
    for t in range(n - 1, -1, -1):
        next_nonterminal = 1.0 - dones[t]
        next_value = values[t + 1] if (t + 1 < n) else 0.0
        delta = rewards[t] + gamma * next_value * next_nonterminal - values[t]
        last_adv = delta + gamma * gae_lambda * next_nonterminal * last_adv
        advantages[t] = last_adv
    returns = advantages + values
    memprobe.probe("gae_done", rows=int(n))
    return advantages, returns


def ppo_update(
    model,
    optimizer,
    batch: RolloutBatch,
    advantages: np.ndarray,
    returns: np.ndarray,
    config: PPOConfig,
) -> dict:
    """One PPO update over `batch`. On CUDA, cuDNN autotunes its convolution
    algorithms for the update (restored on exit): its default heuristic picks a
    slow non-tensor-core weight-gradient kernel for the (3, k) convs over 42x1
    planes, over half the update's GPU time at 192x24. Autotuning chooses by
    timing, so the floats differ from the heuristic's by summation order, and
    can differ between processes. Each new shape (the ragged final minibatch
    changes size every iteration) costs one tuning pass, about a second.

    cuDNN caches the plan per shape whatever the flag was when the shape was
    first seen: a shape first run untuned in this process stays untuned."""
    if torch.device(config.device).type != "cuda":
        return _ppo_update(model, optimizer, batch, advantages, returns, config)
    previous = torch.backends.cudnn.benchmark
    torch.backends.cudnn.benchmark = True
    try:
        return _ppo_update(model, optimizer, batch, advantages, returns, config)
    finally:
        torch.backends.cudnn.benchmark = previous


def _ppo_update(model, optimizer, batch: RolloutBatch, advantages: np.ndarray,
                returns: np.ndarray, config: PPOConfig) -> dict:
    device = config.device
    n = len(batch)
    host_transfer = bool(getattr(config, "minibatch_device_transfer", False))
    # Per-row 1-D vectors are device-resident in BOTH paths: they are tiny
    # (a few MB even at 960 matches) and the global advantage-normalization
    # reduction must run on the same device as the legacy path to stay
    # byte-identical (Amendment 5 gauntlet condition 2).
    actions = torch.from_numpy(np.asarray(batch.actions, dtype=np.int64)).to(device)
    old_logprobs = torch.from_numpy(np.asarray(batch.old_logprobs, dtype=np.float32)).to(device)
    adv_t = torch.from_numpy(np.asarray(advantages, dtype=np.float32)).to(device)
    ret_t = torch.from_numpy(np.asarray(returns, dtype=np.float32)).to(device)
    if config.normalize_advantages:
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

    planes = scalars = action_mask = None
    planes_h = scalars_h = action_mask_h = None
    if host_transfer:
        # from_numpy shares the batch's buffers — no host copy here; each
        # minibatch is gathered on CPU and moved synchronously in the loop.
        planes_h = torch.from_numpy(np.asarray(batch.planes, dtype=np.float32))
        scalars_h = torch.from_numpy(np.asarray(batch.scalars, dtype=np.float32))
        action_mask_h = torch.from_numpy(np.asarray(batch.action_mask, dtype=np.int8))
    else:
        planes = torch.from_numpy(np.asarray(batch.planes, dtype=np.float32)).to(device)
        scalars = torch.from_numpy(np.asarray(batch.scalars, dtype=np.float32)).to(device)
        action_mask = torch.from_numpy(np.asarray(batch.action_mask, dtype=np.int8)).to(device)

    events_t = lengths_t = dealin_t = rank_t = None
    events_np = None
    if batch.events is not None:
        lengths_t = torch.from_numpy(np.asarray(batch.event_lengths, dtype=np.int64)).to(device)
        dealin_t = torch.from_numpy(np.asarray(batch.dealin_labels, dtype=np.float32)).to(device)
        rank_t = torch.from_numpy(np.asarray(batch.rank_labels, dtype=np.int64)).to(device)
        if host_transfer:
            # The uint32->int64 cast happens per minibatch (gauntlet condition
            # 4 allows it: the resulting device tensor is byte-identical to
            # the legacy full-cast) instead of materializing a 2x-size int64
            # copy of the whole event history on the host.
            events_np = np.asarray(batch.events)
        else:
            events_t = torch.from_numpy(np.asarray(batch.events, dtype=np.int64)).to(device)
    memprobe.probe("ppo_tensors_ready", rows=int(n), device=str(device),
                   host_transfer=host_transfer)

    model_config = getattr(model, "model_config", None)
    has_aux = bool(getattr(model_config, "aux_heads", False))
    belief_target = None
    if has_aux:
        plane_channels = (planes_h if host_transfer else planes).shape[1]
        if plane_channels < 51:
            raise ValueError(
                f"model has aux_heads enabled but planes have only {plane_channels} "
                "channels (need 51 for the belief-target oracle-threshold planes "
                "39:51); this would silently compute wrong belief targets."
            )
        if not host_transfer:
            belief_target = (planes[:, 39:51] > 0).float().squeeze(-1)
    metric_names = list(_PPO_METRICS) + (list(_AUX_METRICS) if has_aux else [])

    def step_losses(mb: dict) -> tuple[torch.Tensor, torch.Tensor]:
        """Loss and the [len(metric_names)] metric vector for one minibatch.
        No host syncs, so a CUDA graph can capture it."""
        if has_aux:
            # Encode ONCE for the policy/value heads and the aux heads. The net
            # has no dropout or batch norm, so a second encode would recompute
            # the same features and double the trunk's forward and backward.
            features = model.encode(mb["planes"], mb["scalars"], mb["events"], mb["lengths"])
            masked_logits, value = model.policy_value(features, mb["planes"], mb["mask"])
        else:
            masked_logits, value = model(mb["planes"], mb["scalars"], mb["mask"],
                                         events=mb["events"], event_lengths=mb["lengths"])
        # validate_args=False: the argument checks sync the host; values are unchanged.
        dist = masked_policy_distribution(masked_logits, validate_args=False)
        new_logprobs = dist.log_prob(mb["actions"])
        ratio = torch.exp(new_logprobs - mb["old_logprobs"])
        surr1 = ratio * mb["adv"]
        surr2 = torch.clamp(ratio, 1.0 - config.clip_eps, 1.0 + config.clip_eps) * mb["adv"]
        policy_loss = -torch.min(surr1, surr2).mean()
        value_loss = torch.nn.functional.mse_loss(value, mb["ret"])
        entropy = dist.entropy().mean()
        loss = policy_loss + config.value_coef * value_loss - config.entropy_coef * entropy
        with torch.no_grad():
            approx_kl = (mb["old_logprobs"] - new_logprobs).mean()
            clip_fraction = (torch.abs(ratio - 1.0) > config.clip_eps).float().mean()
        metrics = [policy_loss, value_loss, entropy, approx_kl, clip_fraction]
        if has_aux:
            aux = model.aux_predictions(features)
            belief_loss = torch.nn.functional.binary_cross_entropy_with_logits(
                aux["belief"], mb["belief"])
            dealin_loss = torch.nn.functional.binary_cross_entropy_with_logits(
                aux["dealin"], mb["dealin"])
            # Mean over labelled rows (rank >= 0), 0 when there are none. A masked
            # sum, not boolean indexing: indexing's data-dependent shape would
            # sync the host every minibatch.
            labelled = mb["rank"] >= 0
            rank_ce = torch.nn.functional.cross_entropy(
                aux["rank"], mb["rank"].clamp(min=0), reduction="none")
            rank_loss = ((rank_ce * labelled).sum()
                         / labelled.sum().clamp(min=1).to(rank_ce.dtype))
            loss = loss + AUX_LOSS_WEIGHT * (belief_loss + dealin_loss + rank_loss)
            metrics += [belief_loss, dealin_loss, rank_loss]
        return loss, torch.stack([m.detach() for m in metrics])

    # Telemetry is aggregated over ALL minibatches (row-weighted, so the
    # ragged final minibatch counts by its true size) rather than reporting
    # only the final minibatch's values — final-minibatch-only metrics are a
    # single-slice sample that cannot be compared across batch scales
    # (data-scale-960 Stage 0 prerequisite). `optimizer_steps` counts every
    # optimizer.step() taken, i.e. ppo_epochs * ceil(n / minibatch_size).
    # The totals stay on the device (float64) and are read once at the end: a
    # per-step .item() stalls the host every minibatch, idling the GPU while
    # the next minibatch is gathered and launched.
    metric_total: Optional[torch.Tensor] = None
    rows_seen = 0
    optimizer_steps = 0
    params = [p for p in model.parameters()]
    # On CUDA every full-size minibatch replays one captured forward+backward
    # (_GraphedStep); clipping and the optimizer step stay eager. The ragged
    # final minibatch runs eagerly.
    graphed_step: Optional[_GraphedStep] = None
    use_graph = GRAPHED_UPDATE_STEP and torch.device(device).type == "cuda"
    model.train()
    for _ in range(config.ppo_epochs):
        perm = torch.randperm(n, device=device)
        # One device->host copy per epoch instead of a sync per minibatch.
        perm_h = perm.cpu() if host_transfer else None
        for start in range(0, n, config.minibatch_size):
            idx = perm[start : start + config.minibatch_size]
            mb = {"lengths": lengths_t[idx] if lengths_t is not None else None}
            if host_transfer:
                idx_h = perm_h[start : start + config.minibatch_size]
                mb["planes"] = planes_h.index_select(0, idx_h).to(device)
                mb["scalars"] = scalars_h.index_select(0, idx_h).to(device)
                mb["mask"] = action_mask_h.index_select(0, idx_h).to(device)
                mb["events"] = (torch.from_numpy(
                    events_np[idx_h.numpy()].astype(np.int64)).to(device)
                    if events_np is not None else None)
            else:
                mb["planes"] = planes[idx]
                mb["scalars"] = scalars[idx]
                mb["mask"] = action_mask[idx]
                mb["events"] = events_t[idx] if events_t is not None else None
            mb["actions"] = actions[idx]
            mb["old_logprobs"] = old_logprobs[idx]
            mb["adv"] = adv_t[idx]
            mb["ret"] = ret_t[idx]
            if has_aux:
                # In the legacy path belief_target was precomputed from the
                # full device-resident planes; in the host-transfer path it is
                # derived per minibatch from the SAME plane values (an exact
                # comparison, so the result is byte-identical either way).
                mb["belief"] = (belief_target[idx] if belief_target is not None
                                else (mb["planes"][:, 39:51] > 0).float().squeeze(-1))
                mb["dealin"] = dealin_t[idx]
                mb["rank"] = rank_t[idx]
            mb_rows = int(idx.shape[0])
            if use_graph and mb_rows == config.minibatch_size:
                if graphed_step is None:
                    graphed_step = _GraphedStep(step_losses, params, mb)
                metric_vec = graphed_step.run(mb)
            else:
                # After a capture the gradients live in the graph's buffers:
                # zero them in place rather than dropping them.
                optimizer.zero_grad(set_to_none=graphed_step is None)
                loss, metric_vec = step_losses(mb)
                loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
            optimizer.step()
            weighted = metric_vec.to(torch.float64) * mb_rows
            metric_total = weighted if metric_total is None else metric_total + weighted
            rows_seen += mb_rows
            optimizer_steps += 1
    if rows_seen:
        totals = metric_total.tolist()
        metrics = {key: total / rows_seen for key, total in zip(metric_names, totals)}
    else:  # ppo_epochs == 0: keep the historical zeroed shape
        metrics = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0,
                   "approx_kl": 0.0, "clip_fraction": 0.0}
    metrics["optimizer_steps"] = optimizer_steps
    memprobe.probe("ppo_update_done", rows=int(n), optimizer_steps=int(optimizer_steps))
    return metrics


# Tests switch this off to compare the graphed step with the eager one.
GRAPHED_UPDATE_STEP = True

_PPO_METRICS = ("policy_loss", "value_loss", "entropy", "approx_kl", "clip_fraction")
_AUX_METRICS = ("belief_loss", "dealin_loss", "rank_loss")


class _GraphedStep:
    """One PPO minibatch's forward, losses and backward captured as a CUDA graph.

    The update is launch-bound at production sizes (hundreds of small kernels per
    step); a replay issues them in one call. The graph runs the same kernels as
    the eager step, so it matches it bit for bit given the same cuDNN plans; it
    is captured once per `ppo_update` call, after three eager warmups on a side
    stream (which also let cuDNN autotune before capture). Capture starts with
    every gradient unset, so the graph writes, rather than accumulates, into
    gradient buffers it owns; they stay the parameters' `.grad` afterwards.
    """

    WARMUP = 3

    def __init__(self, step_losses, params: list, example: dict) -> None:
        self.static = {k: v.clone() for k, v in example.items() if v is not None}
        inputs = {k: self.static.get(k) for k in example}
        side = torch.cuda.Stream()
        side.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(side):
            for _ in range(self.WARMUP):
                for p in params:
                    p.grad = None
                loss, _ = step_losses(inputs)
                loss.backward()
        torch.cuda.current_stream().wait_stream(side)
        for p in params:
            p.grad = None
        self.graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(self.graph):
            loss, self.metrics = step_losses(inputs)
            loss.backward()

    def run(self, mb: dict) -> torch.Tensor:
        for key, static in self.static.items():
            static.copy_(mb[key])
        self.graph.replay()
        return self.metrics


def _obs_to_tensors(obs: Observation, device: str):
    planes = torch.from_numpy(np.asarray(obs.planes, dtype=np.float32)).unsqueeze(0).to(device)
    scalars = torch.from_numpy(np.asarray(obs.scalars, dtype=np.float32)).unsqueeze(0).to(device)
    mask = torch.from_numpy(np.asarray(obs.action_mask, dtype=np.int8)).unsqueeze(0).to(device)
    return planes, scalars, mask


def _seat_step_reward(step_rewards, seat: int) -> float:
    """The env's immediate per-seat reward for this step. In Chongci this is the
    per-seat running-score delta accumulated since the previous decision (dense;
    it telescopes to the match net); for classic it is the terminal round
    payout."""
    arr = np.asarray(step_rewards, dtype=np.float32)
    if arr.ndim >= 1 and arr.shape[-1] > seat:
        return float(arr[seat])
    return 0.0


def _grp_match_rewards(match_g, realized, gamma):
    """Per-decision GRP placement rewards for one match, as discount-correct
    potential-based shaping (Ng et al.) with potential Φ = GRP placement value:
    `gamma * g_{k+1} - g_k` for each non-final learner decision, and
    `realized - g_last` for the final decision (terminal potential = 0). The
    GAE-discounted return then telescopes to `gamma^(n-1) * realized - g_0` for
    ANY gamma; the plain `g_{k+1} - g_k` form only telescopes at gamma=1.

    `realized` is the learner's placement value at the terminal: the true final
    standings for a completed match, or the worst placement value for a step-limit
    truncation (an explicit adverse outcome — see the caller). The penalty is a
    fixed constant independent of `g`, so unlike bootstrapping from the frozen
    GRP's own prediction it cannot be inflated by a stalling policy."""
    n = len(match_g)
    out = []
    for k in range(n):
        if k + 1 < n:
            out.append(float(gamma * match_g[k + 1] - match_g[k]))
        else:
            out.append(float(realized - match_g[k]))
    return out


def collect_rollouts(
    env_config: EnvConfig,
    policy_model,
    frozen_anchor,
    config: PPOConfig,
    base_seed: int,
    opponents: Optional[list] = None,
    grp_model=None,
) -> RolloutBatch:
    """Play `matches_per_iter` full matches; record on-policy experience for the
    learning seat (samples from the masked policy), with the frozen anchor in the
    other seats. Per-hand score deltas become rewards; done at match end."""
    device = config.device
    cfg = EnvConfig(
        action_space_size=env_config.action_space_size,
        plane_shape=env_config.plane_shape,
        scalar_features=env_config.scalar_features,
        bridge_kind=env_config.bridge_kind,
        bridge_library_path=env_config.bridge_library_path,
        learning_seats=(0, 1, 2, 3),
        auto_play_heuristics=False,
        max_steps_per_episode=config.max_steps_per_episode,
        match_mode=config.match_mode,
    )
    bridge = build_bridge(cfg)
    env = MahjongEnv(cfg, bridge=bridge)
    policy_model.eval()
    pool = list(opponents) if opponents else [frozen_anchor]
    for net in pool:
        net.eval()

    planes_l, scalars_l, mask_l, actions_l = [], [], [], []
    logprobs_l, values_l, rewards_l, dones_l = [], [], [], []
    truncated_matches = 0

    try:
        for m in range(config.matches_per_iter):
            obs = env.reset(seed=base_seed + m)
            torch.manual_seed(int(base_seed + m))
            # Opponent assignment uses a separate NumPy RNG so it never perturbs
            # the learner's torch sampling stream (keeps pool-size-1 byte-identical
            # to the single-anchor path) and stays reproducible across the
            # sequential and parallel collectors.
            opp_rng = np.random.default_rng(int(base_seed + m))
            seat_opponent = {s: pool[int(opp_rng.integers(len(pool)))] for s in (1, 2, 3)}
            reset_result = env.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                continue
            last_learn_index: Optional[int] = None
            match_indices: list[int] = []   # rewards_l indices for this match (GRP path)
            match_g: list[float] = []        # GRP placement value at each learner decision
            cum_net = np.zeros(4, dtype=np.float32)  # per-seat cumulative net (telescopes to match net)
            if grp_model is not None and reset_result is not None:
                # Include any score change from reset-time autoplay (a hand resolved
                # before the learner's first decision) so realized_placement ranks on
                # the TRUE final net, matching the eval placement + net metrics.
                rr = np.asarray(reset_result.rewards, dtype=np.float32)
                if rr.size:
                    cum_net[: min(4, rr.shape[-1])] += rr[: min(4, rr.shape[-1])]
            while True:
                seat = int(obs.seat)
                planes, scalars, mask = _obs_to_tensors(obs, device)
                if seat == LEARNING_SEAT:
                    with torch.no_grad():
                        logits, value = policy_model(planes, scalars, mask)
                        logits = logits / max(config.sample_temperature, 1e-6)
                        dist = masked_policy_distribution(logits)
                        action = int(dist.sample()[0].item())
                        logprob = float(dist.log_prob(torch.tensor([action], device=device))[0])
                        val = float(value[0].item())
                    planes_l.append(np.asarray(obs.planes, dtype=np.float32))
                    scalars_l.append(np.asarray(obs.scalars, dtype=np.float32))
                    mask_l.append(np.asarray(obs.action_mask, dtype=np.int8))
                    actions_l.append(action)
                    logprobs_l.append(logprob)
                    values_l.append(val)
                    rewards_l.append(0.0)
                    dones_l.append(0.0)
                    last_learn_index = len(actions_l) - 1
                    if grp_model is not None:
                        with torch.no_grad():
                            g = float(grp_model(planes, scalars)[0])
                        match_indices.append(last_learn_index)
                        match_g.append(g)
                else:
                    net = seat_opponent.get(seat, pool[0])
                    with torch.no_grad():
                        logits, _ = net(planes, scalars, mask)
                        action = int(torch.argmax(logits, dim=1)[0].item())
                step = env.step(action)
                if grp_model is not None:
                    sr = np.asarray(step.rewards, dtype=np.float32)
                    if sr.size:
                        cum_net += sr[:4]
                elif last_learn_index is not None:
                    rewards_l[last_learn_index] += _seat_step_reward(step.rewards, LEARNING_SEAT)
                if step.terminated or step.truncated:
                    is_trunc = bool(step.truncated) and not bool(step.terminated)
                    if is_trunc:
                        truncated_matches += 1
                    if last_learn_index is not None:
                        dones_l[last_learn_index] = 1.0
                    if grp_model is not None and match_indices:
                        # A step-limit truncation has no final standings. Rather than
                        # discard the match (which lets a stalling policy censor its
                        # own bad trajectories — survivorship bias — and could abort a
                        # run if every match truncated) or bootstrap from the frozen
                        # GRP's own prediction (a phantom gamma^(n-1)*g_last return the
                        # policy could farm by stalling), score it as an explicit
                        # adverse outcome: the worst placement value. That penalty is a
                        # fixed constant independent of the GRP prediction, so it can't
                        # be inflated; with the gamma == 1 GRP objective (enforced in
                        # train_ppo) it reaches every decision undiscounted, so stalling
                        # to a longer horizon cannot attenuate it.
                        if is_trunc:
                            realized = float(min(config.grp_placement_values))
                        else:
                            realized = float(placement_shaped_returns(
                                cum_net[None, :], config.grp_placement_values)[0, LEARNING_SEAT])
                        for idx, r in zip(match_indices, _grp_match_rewards(match_g, realized, config.gamma)):
                            rewards_l[idx] = r
                    break
                obs = step.observation
    finally:
        close = getattr(bridge, "close", None)
        if callable(close):
            close()

    if not actions_l:
        raise RuntimeError("collect_rollouts produced no learning-seat decisions")

    return RolloutBatch(
        planes=np.stack(planes_l).astype(np.float32),
        scalars=np.stack(scalars_l).astype(np.float32),
        action_mask=np.stack(mask_l).astype(np.int8),
        actions=np.asarray(actions_l, dtype=np.int64),
        old_logprobs=np.asarray(logprobs_l, dtype=np.float32),
        values=np.asarray(values_l, dtype=np.float32),
        rewards=np.asarray(rewards_l, dtype=np.float32),
        dones=np.asarray(dones_l, dtype=np.float32),
        truncated_matches=truncated_matches,
    )


def build_opponent_nets(env_config, model_config, pool_states, device="cpu"):
    """Build a frozen PolicyValueNet for each opponent state_dict in the pool.
    Shared by the sequential trainer and the parallel workers so both construct
    opponents identically."""
    nets = []
    for state in pool_states:
        net = PolicyValueNet(env_config, model_config).to(device)
        net.load_state_dict(state)
        net.eval()
        for p in net.parameters():
            p.requires_grad_(False)
        nets.append(net)
    return nets


def load_grp_model(env_config, model_config, grp_checkpoint, device="cpu", placement_values=None):
    """Load a frozen GlobalEVNet GRP model (same ModelConfig as the policy), rejecting
    any checkpoint whose training objective is not placement shaping.

    GlobalEVNet's training defaults to RAW terminal net-score targets, which are
    unbounded and on a different scale than the bounded placement values PPO uses as
    potentials. A raw-score checkpoint is architecturally identical, so it would load
    and silently change the reward scale and objective — wasting an entire PPO run.
    We therefore require the checkpoint to declare `reward_shaping="placement"` in its
    metadata (written by fh-mj-train-global-ev), with placement values matching the
    PPO config when provided."""
    path = Path(grp_checkpoint)
    payload = torch.load(path, map_location="cpu")
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    if not metadata or "reward_shaping" not in metadata:
        raise ValueError(
            f"GRP checkpoint {path} has no objective metadata; it predates objective "
            "tagging or was not produced by fh-mj-train-global-ev. Retrain/re-save the "
            "GlobalEVNet with --reward-shaping placement so the objective can be verified."
        )
    shaping = metadata.get("reward_shaping")
    if shaping != "placement":
        raise ValueError(
            f"GRP checkpoint {path} was trained with reward_shaping={shaping!r}, but PPO "
            "GRP shaping requires 'placement' (bounded placement potentials). Retrain the "
            "GlobalEVNet with --reward-shaping placement."
        )
    if placement_values is not None:
        ckpt_pv = tuple(round(float(v), 6) for v in metadata.get("placement_values", ()))
        want_pv = tuple(round(float(v), 6) for v in placement_values)
        if ckpt_pv != want_pv:
            raise ValueError(
                f"GRP checkpoint {path} placement_values {ckpt_pv} != PPO "
                f"grp_placement_values {want_pv}; the reward scale would mismatch."
            )
    grp = GlobalEVNet(env_config, model_config).to(device)
    load_checkpoint(path, grp)
    grp.eval()
    for p in grp.parameters():
        p.requires_grad_(False)
    return grp


def train_ppo(
    env_config: EnvConfig,
    model_config: ModelConfig,
    init_checkpoint: Path,
    checkpoint_dir: Path,
    config: PPOConfig,
    base_seed: int = 0,
    run_eval: bool = True,
    iteration_callback: Optional[Callable[[dict], None]] = None,
) -> List[dict]:
    # Reject invalid pool config up front rather than silently running a different
    # configuration (anchor-only) or dividing by zero on the first snapshot
    # iteration — either would waste an expensive configured run.
    if config.pool_max_size < 1:
        raise ValueError(f"pool_max_size must be >= 1, got {config.pool_max_size}")
    if config.pool_max_size > 1 and config.pool_snapshot_interval < 1:
        raise ValueError(
            "pool_snapshot_interval must be >= 1 when pool_max_size > 1, "
            f"got {config.pool_snapshot_interval}"
        )
    # The GRP placement objective is episodic: gamma < 1 discounts the terminal
    # placement (and the worst-placement truncation penalty) toward zero for long
    # matches — e.g. 0.99^999 ~= 4e-5 — so a stalling policy could attenuate a loss
    # and the placement signal would barely reach early decisions. Require gamma == 1
    # so the placement return telescopes to `realized - g_0` independent of horizon.
    if config.grp_checkpoint is not None and config.gamma != 1.0:
        raise ValueError(
            "GRP placement shaping requires gamma == 1.0 (episodic placement "
            "objective; gamma < 1 discounts the terminal placement and the "
            f"truncation penalty toward zero for long matches). Got gamma={config.gamma}."
        )
    device = config.device
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    grp_model = None
    if config.grp_checkpoint is not None:
        grp_model = load_grp_model(env_config, model_config, config.grp_checkpoint,
                                   device, placement_values=config.grp_placement_values)

    model = PolicyValueNet(env_config, model_config).to(device)
    load_checkpoint(Path(init_checkpoint), model)
    frozen = PolicyValueNet(env_config, model_config).to(device)
    load_checkpoint(Path(init_checkpoint), frozen)
    frozen.eval()
    for p in frozen.parameters():
        p.requires_grad_(False)

    optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr)
    history: List[dict] = []
    history_path = checkpoint_dir / HISTORY_FILENAME
    _write_history_atomic(history_path, history)

    frozen_state = cpu_state_snapshot(frozen)
    pool_states: List[dict] = [frozen_state]  # index 0 = anchor, always kept

    collector: Optional["ParallelRolloutCollector"] = None
    try:
        if config.num_workers > 1:
            from .parallel_rollouts import ParallelRolloutCollector
            grp_state = None
            if grp_model is not None:
                grp_state = {k: v.detach().cpu() for k, v in grp_model.state_dict().items()}
            collector = ParallelRolloutCollector(
                env_config, model_config, config, config.num_workers, grp_state_dict=grp_state,
            )
            collector.start()

        for iteration in range(1, config.iterations + 1):
            iter_seed = base_seed + iteration * config.matches_per_iter

            # Grow the opponent pool with a snapshot of the current learner.
            if config.pool_max_size > 1 and iteration % config.pool_snapshot_interval == 0:
                pool_states.append(cpu_state_snapshot(model))
                if len(pool_states) > config.pool_max_size:
                    pool_states.pop(1)  # evict oldest snapshot; keep anchor at index 0

            if collector is not None:
                learner_state = cpu_state_snapshot(model)
                batch = collector.collect(learner_state, pool_states, iter_seed, config.matches_per_iter)
            elif config.pool_max_size > 1:
                opponents = build_opponent_nets(env_config, model_config, pool_states, device)
                batch = collect_rollouts(env_config, model, frozen, config, base_seed=iter_seed, opponents=opponents, grp_model=grp_model)
            else:
                batch = collect_rollouts(env_config, model, frozen, config, base_seed=iter_seed, grp_model=grp_model)
            advantages, returns = compute_gae(batch.rewards, batch.values, batch.dones, config.gamma, config.gae_lambda)
            metrics = ppo_update(model, optimizer, batch, advantages, returns, config)
            metrics["iteration"] = iteration
            # Under GRP this is the telescoped placement quantity (not net score); eval gate still uses net.
            metrics["mean_reward"] = float(np.sum(batch.rewards) / max(1.0, float(batch.dones.sum())))
            metrics["steps"] = len(batch)
            metrics["pool_size"] = len(pool_states)
            # Surface step-limit truncations so a stalling pathology can never be
            # silent: truncated matches are kept and scored as the worst placement.
            metrics["rollout_truncations"] = int(getattr(batch, "truncated_matches", 0))

            if run_eval and iteration % config.eval_interval == 0:
                seeds = list(range(config.eval_start_seed, config.eval_start_seed + config.eval_seeds))
                try:
                    report = evaluate_duplicate_seats(
                        model=model, seeds=seeds, bridge_kind=env_config.bridge_kind,
                        bridge_library_path=env_config.bridge_library_path, device=device,
                        large_loss_threshold=-1.0, match_mode=config.match_mode,
                        max_steps_per_episode=config.max_steps_per_episode,
                    )
                    metrics["eval_mean_reward"] = report["mean_reward"]
                    metrics["eval_mean_reward_ci95"] = report["mean_reward_ci95"]
                    metrics["eval_large_loss_rate"] = report["large_loss_rate"]
                    # Placement is the GRP objective — capture it so GRP runs can be
                    # selected/compared on it, not just on net reward.
                    metrics["eval_mean_placement"] = report.get("mean_placement")
                    metrics["eval_mean_placement_ci95"] = report.get("mean_placement_ci95")
                except Exception as exc:  # eval must not abort training
                    metrics["eval_error"] = str(exc)[:200]

            save_checkpoint(checkpoint_dir / f"iter_{iteration:03d}.pt", model)
            history.append(metrics)
            line = (
                f"iter {iteration}: policy_loss={metrics['policy_loss']:.4f} "
                f"value_loss={metrics['value_loss']:.4f} entropy={metrics['entropy']:.4f} "
                f"approx_kl={metrics['approx_kl']:.4f} mean_reward={metrics['mean_reward']:.4f}"
            )
            if "eval_mean_reward" in metrics:
                line += (
                    f" eval_mean_reward={metrics['eval_mean_reward']:.4f} "
                    f"eval_ci95={metrics['eval_mean_reward_ci95']:.4f} "
                    f"eval_large_loss_rate={metrics['eval_large_loss_rate']:.4f}"
                )
                if metrics.get("eval_mean_placement") is not None:
                    line += f" eval_mean_placement={metrics['eval_mean_placement']:.4f}"
            elif "eval_error" in metrics:
                err = " ".join(str(metrics["eval_error"]).split())
                line += f" eval_error={err}"
            print(line)
            # Persist after every iteration so an interruption keeps completed
            # iterations' metrics (checkpoints are already saved per iteration).
            _write_history_atomic(history_path, history)
            # Optional per-iteration hook (e.g. live MLflow logging); kept as a
            # callback so ppo.py stays decoupled from any tracking backend.
            if iteration_callback is not None:
                iteration_callback(metrics)
    finally:
        if collector is not None:
            collector.close()
    return history

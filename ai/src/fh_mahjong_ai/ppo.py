from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np
import torch

from .bridge import build_bridge
from .config import EnvConfig, ModelConfig
from .data import placement_shaped_returns
from .env import MahjongEnv
from .evaluate import evaluate_duplicate_seats
from .global_ev import GlobalEVNet
from .model import PolicyValueNet
from .storage import load_checkpoint, save_checkpoint
from .types import Observation

LEARNING_SEAT = 0

HISTORY_FILENAME = "history.json"

AUX_LOSS_WEIGHT = 0.1


def _write_history_atomic(path: Path, history: List[dict]) -> None:
    """Persist `history` durably: write to a sibling temp file then atomically
    replace, so a crash mid-write can never truncate or corrupt the existing
    history.json."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(history, indent=2))
    os.replace(tmp, path)


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
    collector: str = "process"   # "process" (spawn workers) | "batched" (env pool + batched forward)
    pool_slots: int = 128        # concurrent env-pool slots for collector="batched"
    pool_max_size: int = 1
    pool_snapshot_interval: int = 10
    grp_checkpoint: Optional[Path] = None
    grp_placement_values: tuple = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)
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
    for name in _ROLLOUT_OPTIONAL_ARRAY_FIELDS:
        present = [getattr(b, name) is not None for b in nonempty]
        if all(present):
            fields[name] = np.concatenate([getattr(b, name) for b in nonempty], axis=0)
        elif any(present):
            raise ValueError(
                f"concat_rollout_batches: '{name}' is present in some batches but "
                "not others; this would silently misalign event rows against "
                "planes/scalars."
            )
        else:
            fields[name] = None
    return RolloutBatch(**fields, truncated_matches=truncated_matches)


def masked_policy_distribution(masked_logits: torch.Tensor) -> torch.distributions.Categorical:
    """Categorical over actions; logits are already -inf-masked (finfo.min) for
    illegal actions by PolicyValueNet.forward, so illegal probability is ~0 and
    entropy stays finite."""
    return torch.distributions.Categorical(logits=masked_logits)


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
    return advantages, returns


def ppo_update(
    model,
    optimizer,
    batch: RolloutBatch,
    advantages: np.ndarray,
    returns: np.ndarray,
    config: PPOConfig,
) -> dict:
    device = config.device
    n = len(batch)
    planes = torch.from_numpy(np.asarray(batch.planes, dtype=np.float32)).to(device)
    scalars = torch.from_numpy(np.asarray(batch.scalars, dtype=np.float32)).to(device)
    action_mask = torch.from_numpy(np.asarray(batch.action_mask, dtype=np.int8)).to(device)
    actions = torch.from_numpy(np.asarray(batch.actions, dtype=np.int64)).to(device)
    old_logprobs = torch.from_numpy(np.asarray(batch.old_logprobs, dtype=np.float32)).to(device)
    adv_t = torch.from_numpy(np.asarray(advantages, dtype=np.float32)).to(device)
    ret_t = torch.from_numpy(np.asarray(returns, dtype=np.float32)).to(device)
    if config.normalize_advantages:
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

    events_t = lengths_t = dealin_t = rank_t = None
    if batch.events is not None:
        events_t = torch.from_numpy(np.asarray(batch.events, dtype=np.int64)).to(device)
        lengths_t = torch.from_numpy(np.asarray(batch.event_lengths, dtype=np.int64)).to(device)
        dealin_t = torch.from_numpy(np.asarray(batch.dealin_labels, dtype=np.float32)).to(device)
        rank_t = torch.from_numpy(np.asarray(batch.rank_labels, dtype=np.int64)).to(device)

    model_config = getattr(model, "model_config", None)
    has_aux = bool(getattr(model_config, "aux_heads", False))
    belief_target = None
    if has_aux:
        if planes.shape[1] < 51:
            raise ValueError(
                f"model has aux_heads enabled but planes have only {planes.shape[1]} "
                "channels (need 51 for the belief-target oracle-threshold planes "
                "39:51); this would silently compute wrong belief targets."
            )
        belief_target = (planes[:, 39:51] > 0).float().squeeze(-1)

    last = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "approx_kl": 0.0, "clip_fraction": 0.0}
    model.train()
    for _ in range(config.ppo_epochs):
        perm = torch.randperm(n, device=device)
        for start in range(0, n, config.minibatch_size):
            idx = perm[start : start + config.minibatch_size]
            mb_events = events_t[idx] if events_t is not None else None
            mb_lengths = lengths_t[idx] if lengths_t is not None else None
            masked_logits, value = model(planes[idx], scalars[idx], action_mask[idx],
                                         events=mb_events, event_lengths=mb_lengths)
            dist = masked_policy_distribution(masked_logits)
            new_logprobs = dist.log_prob(actions[idx])
            ratio = torch.exp(new_logprobs - old_logprobs[idx])
            mb_adv = adv_t[idx]
            surr1 = ratio * mb_adv
            surr2 = torch.clamp(ratio, 1.0 - config.clip_eps, 1.0 + config.clip_eps) * mb_adv
            policy_loss = -torch.min(surr1, surr2).mean()
            value_loss = torch.nn.functional.mse_loss(value, ret_t[idx])
            entropy = dist.entropy().mean()
            loss = policy_loss + config.value_coef * value_loss - config.entropy_coef * entropy

            aux_metrics = {}
            if has_aux:
                features = model.encode(planes[idx], scalars[idx], mb_events, mb_lengths)
                aux = model.aux_predictions(features)
                belief_loss = torch.nn.functional.binary_cross_entropy_with_logits(
                    aux["belief"], belief_target[idx])
                dealin_loss = torch.nn.functional.binary_cross_entropy_with_logits(
                    aux["dealin"], dealin_t[idx])
                rank_mask = rank_t[idx] >= 0
                if rank_mask.any():
                    rank_loss = torch.nn.functional.cross_entropy(
                        aux["rank"][rank_mask], rank_t[idx][rank_mask])
                else:
                    rank_loss = torch.zeros((), device=device)
                loss = loss + AUX_LOSS_WEIGHT * (belief_loss + dealin_loss + rank_loss)
                aux_metrics = {
                    "belief_loss": float(belief_loss.item()),
                    "dealin_loss": float(dealin_loss.item()),
                    "rank_loss": float(rank_loss.item()),
                }

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
            optimizer.step()

            with torch.no_grad():
                approx_kl = (old_logprobs[idx] - new_logprobs).mean()
                clip_fraction = (torch.abs(ratio - 1.0) > config.clip_eps).float().mean()
            last = {
                "policy_loss": float(policy_loss.item()),
                "value_loss": float(value_loss.item()),
                "entropy": float(entropy.item()),
                "approx_kl": float(approx_kl.item()),
                "clip_fraction": float(clip_fraction.item()),
                **aux_metrics,
            }
    return last


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

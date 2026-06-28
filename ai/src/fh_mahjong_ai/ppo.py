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
    pool_max_size: int = 1
    pool_snapshot_interval: int = 10
    grp_checkpoint: Optional[Path] = None
    grp_placement_values: tuple = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)
    device: str = "cpu"


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

    def __len__(self) -> int:
        return int(self.actions.shape[0])


def concat_rollout_batches(batches: List["RolloutBatch"]) -> "RolloutBatch":
    """Concatenate per-worker rollout batches into one flat batch. Empty batches
    are skipped; raises if there is nothing to concatenate. Each match is
    self-contained (dones=1 at its final step), so GAE over the concatenation is
    correct without any boundary fix-up."""
    nonempty = [b for b in batches if len(b) > 0]
    if not nonempty:
        raise RuntimeError("concat_rollout_batches: no rollout data")
    return RolloutBatch(
        planes=np.concatenate([b.planes for b in nonempty], axis=0),
        scalars=np.concatenate([b.scalars for b in nonempty], axis=0),
        action_mask=np.concatenate([b.action_mask for b in nonempty], axis=0),
        actions=np.concatenate([b.actions for b in nonempty], axis=0),
        old_logprobs=np.concatenate([b.old_logprobs for b in nonempty], axis=0),
        values=np.concatenate([b.values for b in nonempty], axis=0),
        rewards=np.concatenate([b.rewards for b in nonempty], axis=0),
        dones=np.concatenate([b.dones for b in nonempty], axis=0),
    )


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

    last = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "approx_kl": 0.0, "clip_fraction": 0.0}
    model.train()
    for _ in range(config.ppo_epochs):
        perm = torch.randperm(n, device=device)
        for start in range(0, n, config.minibatch_size):
            idx = perm[start : start + config.minibatch_size]
            masked_logits, value = model(planes[idx], scalars[idx], action_mask[idx])
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
                    cum_net += np.asarray(step.rewards, dtype=np.float32)[:4] if np.asarray(step.rewards).size else 0.0
                elif last_learn_index is not None:
                    rewards_l[last_learn_index] += _seat_step_reward(step.rewards, LEARNING_SEAT)
                if step.terminated or step.truncated:
                    if last_learn_index is not None:
                        dones_l[last_learn_index] = 1.0
                    if grp_model is not None and match_indices:
                        realized = float(placement_shaped_returns(
                            cum_net[None, :], config.grp_placement_values)[0, LEARNING_SEAT])
                        for k, idx in enumerate(match_indices):
                            if k + 1 < len(match_g):
                                rewards_l[idx] = match_g[k + 1] - match_g[k]
                            else:
                                rewards_l[idx] = realized - match_g[k]
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


def load_grp_model(env_config, model_config, grp_checkpoint, device="cpu"):
    """Load a frozen GlobalEVNet GRP model (same ModelConfig as the policy)."""
    grp = GlobalEVNet(env_config, model_config).to(device)
    load_checkpoint(Path(grp_checkpoint), grp)
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
    device = config.device
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    grp_model = None
    if config.grp_checkpoint is not None:
        grp_model = load_grp_model(env_config, model_config, config.grp_checkpoint, device)

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
            metrics["mean_reward"] = float(np.sum(batch.rewards) / max(1.0, float(batch.dones.sum())))
            metrics["steps"] = len(batch)
            metrics["pool_size"] = len(pool_states)

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

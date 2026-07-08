"""Oracle-guiding helpers (Phase 1): build a perfect-information policy
warm-started from the 39-channel anchor."""
from __future__ import annotations

import json
import multiprocessing as mp
import queue as _queue
import traceback
from dataclasses import replace
from pathlib import Path

import numpy as np
import torch

from .ach import ach_update
from .bridge import build_bridge
from .config import EnvConfig, ModelConfig
from .env import MahjongEnv
from .model import PolicyValueNet
from .parallel_rollouts import _split_counts
from .ppo import (
    RolloutBatch, PPOConfig, compute_gae, concat_rollout_batches, ppo_update,
    masked_policy_distribution, _obs_to_tensors, _seat_step_reward, LEARNING_SEAT,
    cpu_state_snapshot,
)
from .storage import load_compatible_checkpoint, save_checkpoint


def build_oracle_model(env_config: EnvConfig, model_config: ModelConfig,
                       anchor_checkpoint: Path, device: str = "cpu") -> PolicyValueNet:
    """Build a 51-channel oracle `PolicyValueNet` warm-started from the 39-channel
    anchor. Every layer except the first plane conv is loaded by shape
    (`load_compatible_checkpoint` skips the 39->51 conv); the input conv is then
    initialized so the oracle equals the anchor when the 12 oracle channels are 0:
    the anchor's weights occupy the first 39 input channels and the new 12 are
    zeroed."""
    oracle = PolicyValueNet(env_config, model_config).to(device)
    # Load all same-shape tensors (skips plane_stem.0.weight: [C,39,3,3] vs [C,51,3,3]).
    load_compatible_checkpoint(Path(anchor_checkpoint), oracle)
    # Read the anchor's input conv weight directly from the checkpoint.
    payload = torch.load(Path(anchor_checkpoint), map_location="cpu")
    anchor_w = payload["model"]["plane_stem.0.weight"]  # [C, 39, 3, 3]
    base = anchor_w.shape[1]  # 39
    with torch.no_grad():
        w = oracle.plane_stem[0].weight
        w.zero_()
        w[:, :base].copy_(anchor_w.to(w.device))
    oracle.eval()
    return oracle


def extract_deployable_student(oracle_model: PolicyValueNet, env_config_39ch: EnvConfig,
                               model_config: ModelConfig) -> PolicyValueNet:
    """Extract the deployable 39-channel policy from a trained 51-channel net. Copy
    every tensor except the first plane conv, and set the 39ch input conv to the
    51ch net's `plane_stem[0].weight[:, :39]`. By construction the student's output
    on a 39ch observation equals the 51ch net's output on that observation
    zero-padded to 51ch (the oracle channels contribute zero when their input is 0).
    Inverse of `build_oracle_model`."""
    oracle_w = oracle_model.plane_stem[0].weight  # [C, 51, 3, 3]
    in_ch = oracle_w.shape[1]
    if in_ch != 51:
        raise ValueError(f"expected a 51-channel oracle net, got input conv with {in_ch} channels")
    student = PolicyValueNet(env_config_39ch, model_config)
    src = oracle_model.state_dict()
    dst = student.state_dict()
    merged = dict(dst)
    for key, val in src.items():
        if key == "plane_stem.0.weight":
            continue  # shape mismatch [C,51,..] vs [C,39,..]; set explicitly below
        if key in dst and val.shape == dst[key].shape:
            merged[key] = val
    student.load_state_dict(merged)
    with torch.no_grad():
        student.plane_stem[0].weight.copy_(oracle_w[:, :39].to(student.plane_stem[0].weight.device))
    student.eval()
    return student


def feature_dropout_schedule(iteration: int, iterations: int,
                             hold_start_frac: float = 0.2, ramp_frac: float = 0.6) -> float:
    """Suphx feature-dropout probability delta for a 1-based `iteration` of
    `iterations`: 0 (full perfect info) for the first `hold_start_frac`, a linear
    ramp 0->1 over the next `ramp_frac`, then 1 (pure public-info student)."""
    if iterations <= 1:
        return 1.0
    frac = (iteration - 1) / (iterations - 1)  # 0..1 over the run
    if frac <= hold_start_frac:
        return 0.0
    if frac >= hold_start_frac + ramp_frac:
        return 1.0
    return float((frac - hold_start_frac) / ramp_frac)


def collect_oracle_rollouts(env_config: EnvConfig, model: PolicyValueNet,
                            config: PPOConfig, base_seed: int) -> RolloutBatch:
    """Single-seat PPO rollouts: the oracle is the only learning seat; the env
    auto-plays heuristic opponents. Records the learner's decisions with dense
    per-hand score-delta reward; done=1 at match end."""
    device = config.device
    cfg = EnvConfig(
        action_space_size=env_config.action_space_size,
        plane_shape=env_config.plane_shape,
        scalar_features=env_config.scalar_features,
        bridge_kind=env_config.bridge_kind,
        bridge_library_path=env_config.bridge_library_path,
        learning_seats=(LEARNING_SEAT,),
        auto_play_heuristics=True,
        max_steps_per_episode=config.max_steps_per_episode,
        match_mode=config.match_mode,
        oracle_observation=env_config.oracle_observation,
    )
    bridge = build_bridge(cfg)
    env = MahjongEnv(cfg, bridge=bridge)
    model.eval()
    planes_l, scalars_l, mask_l, actions_l = [], [], [], []
    logprobs_l, values_l, rewards_l, dones_l = [], [], [], []
    try:
        for m in range(config.matches_per_iter):
            obs = env.reset(seed=base_seed + m)
            torch.manual_seed(int(base_seed + m))
            reset_result = env.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                continue
            last_idx = None
            while True:
                planes, scalars, mask = _obs_to_tensors(obs, device)
                with torch.no_grad():
                    logits, value = model(planes, scalars, mask)
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
                last_idx = len(actions_l) - 1
                step = env.step(action)
                if last_idx is not None:
                    rewards_l[last_idx] += _seat_step_reward(step.rewards, LEARNING_SEAT)
                if step.terminated or step.truncated:
                    if last_idx is not None:
                        dones_l[last_idx] = 1.0
                    break
                obs = step.observation
    finally:
        close = getattr(bridge, "close", None)
        if callable(close):
            close()
    if not actions_l:
        raise RuntimeError("collect_oracle_rollouts produced no learning-seat decisions")
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


def collect_selfplay_rollouts(env_config: EnvConfig, model: PolicyValueNet,
                              config: PPOConfig, base_seed: int, drop_prob: float) -> RolloutBatch:
    """Symmetric self-play PPO rollouts: all four seats are the SAME `model`, each
    sampling on-policy; every seat's transitions are recorded. Feature-dropout: with
    probability `drop_prob`, the 12 oracle channels (planes 39..50) of the obs the
    model sees are zeroed AND the masked obs is recorded (so the PPO update matches
    what the policy acted on). Each seat's dense per-hand score delta is credited to
    that seat's last decision so its reward telescopes to its match net; `done=1` at
    each seat's final decision."""
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
        oracle_observation=env_config.oracle_observation,
    )
    bridge = build_bridge(cfg)
    env = MahjongEnv(cfg, bridge=bridge)
    model.eval()
    oracle_lo, oracle_hi = 39, 51  # oracle channels to mask
    planes_l, scalars_l, mask_l, actions_l = [], [], [], []
    logprobs_l, values_l, rewards_l, dones_l = [], [], [], []
    try:
        for m in range(config.matches_per_iter):
            obs = env.reset(seed=base_seed + m)
            torch.manual_seed(int(base_seed + m))
            mask_rng = np.random.default_rng(base_seed + m)  # seeded -> parallel == sequential
            reset_result = env.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                continue
            # Per-seat trajectory buffers: each is a list-of-lists indexed by seat 0..3.
            seat_planes:   list[list] = [[], [], [], []]
            seat_scalars:  list[list] = [[], [], [], []]
            seat_masks:    list[list] = [[], [], [], []]
            seat_actions:  list[list] = [[], [], [], []]
            seat_logprobs: list[list] = [[], [], [], []]
            seat_values:   list[list] = [[], [], [], []]
            seat_rewards:  list[list] = [[], [], [], []]
            while True:
                seat = int(obs.seat)
                planes_np = np.asarray(obs.planes, dtype=np.float32).copy()
                if planes_np.shape[0] >= oracle_hi and mask_rng.random() < drop_prob:
                    planes_np[oracle_lo:oracle_hi] = 0.0  # feature-dropout
                planes = torch.from_numpy(planes_np).unsqueeze(0).to(device)
                scalars = torch.from_numpy(np.asarray(obs.scalars, dtype=np.float32)).unsqueeze(0).to(device)
                amask = torch.from_numpy(np.asarray(obs.action_mask, dtype=np.int8)).unsqueeze(0).to(device)
                with torch.no_grad():
                    logits, value = model(planes, scalars, amask)
                    logits = logits / max(config.sample_temperature, 1e-6)
                    dist = masked_policy_distribution(logits)
                    action = int(dist.sample()[0].item())
                    logprob = float(dist.log_prob(torch.tensor([action], device=device))[0])
                    val = float(value[0].item())
                seat_planes[seat].append(planes_np)  # record the MASKED obs
                seat_scalars[seat].append(np.asarray(obs.scalars, dtype=np.float32))
                seat_masks[seat].append(np.asarray(obs.action_mask, dtype=np.int8))
                seat_actions[seat].append(action)
                seat_logprobs[seat].append(logprob)
                seat_values[seat].append(val)
                seat_rewards[seat].append(0.0)
                step = env.step(action)
                # Credit each seat's score delta to ITS current last decision.
                for k in range(4):
                    if seat_rewards[k]:
                        seat_rewards[k][-1] += _seat_step_reward(step.rewards, k)
                if step.terminated or step.truncated:
                    break
                obs = step.observation
            # At match end: emit each seat's trajectory as a contiguous block ending in done=1.
            for k in range(4):
                n = len(seat_actions[k])
                if n == 0:
                    continue
                planes_l.extend(seat_planes[k])
                scalars_l.extend(seat_scalars[k])
                mask_l.extend(seat_masks[k])
                actions_l.extend(seat_actions[k])
                logprobs_l.extend(seat_logprobs[k])
                values_l.extend(seat_values[k])
                rewards_l.extend(seat_rewards[k])
                dones_l.extend([0.0] * (n - 1) + [1.0])
    finally:
        close = getattr(bridge, "close", None)
        if callable(close):
            close()
    if not actions_l:
        raise RuntimeError("collect_selfplay_rollouts produced no decisions")
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


def _oracle_worker_loop(env_config, model_config, ppo_config, task_q, result_q):
    import torch as _torch

    from .model import PolicyValueNet as _PVN

    _torch.set_num_threads(1)
    model = _PVN(env_config, model_config)
    while True:
        task = task_q.get()
        if task is None:
            return
        worker_id, state_dict, base_seed, matches = task
        try:
            model.load_state_dict(state_dict)
            cfg = replace(ppo_config, matches_per_iter=matches, device="cpu")
            batch = collect_oracle_rollouts(env_config, model, cfg, base_seed=base_seed)
            result_q.put((worker_id, batch, None))
            batch = None  # release our reference; the queue keeps the object alive until the feeder thread has serialized it, then all copies are freed
        except Exception:  # noqa: BLE001 - report any worker failure to the parent
            result_q.put((worker_id, None, traceback.format_exc()))


class ParallelOracleCollector:
    """Persistent spawn-context worker pool for single-seat oracle rollouts (CPU
    inference), concatenated into one RolloutBatch. Mirrors ParallelRolloutCollector
    but has no opponent pool — the env auto-plays the heuristic opponents, so each
    worker only ships/loads the learner state. Seed blocks are contiguous and
    disjoint (base_seed + cumulative offset), so the union equals the sequential
    run's seed range and the concatenation is the same set of matches."""

    def __init__(self, env_config: EnvConfig, model_config: ModelConfig,
                 ppo_config: PPOConfig, num_workers: int) -> None:
        if num_workers < 1:
            raise ValueError("num_workers must be >= 1")
        self.env_config = env_config
        self.model_config = model_config
        self.ppo_config = ppo_config
        self.num_workers = int(num_workers)
        self._ctx = mp.get_context("spawn")
        self._task_q = None
        self._result_q = None
        self._procs = []

    def start(self) -> None:
        self._task_q = self._ctx.Queue()
        self._result_q = self._ctx.Queue()
        self._procs = []
        for _ in range(self.num_workers):
            p = self._ctx.Process(
                target=_oracle_worker_loop,
                args=(self.env_config, self.model_config, self.ppo_config,
                      self._task_q, self._result_q),
                daemon=True,
            )
            p.start()
            self._procs.append(p)

    def collect(self, state_dict, base_seed: int, matches_per_iter: int) -> RolloutBatch:
        counts = _split_counts(matches_per_iter, self.num_workers)
        offset = 0
        dispatched = 0
        for worker_id, count in enumerate(counts):
            if count == 0:
                continue
            self._task_q.put((worker_id, state_dict, int(base_seed + offset), int(count)))
            offset += count
            dispatched += 1

        results: dict = {}
        received = 0
        while received < dispatched:
            try:
                worker_id, batch, err = self._result_q.get(timeout=30.0)
            except _queue.Empty:
                if any(p.exitcode is not None for p in self._procs):
                    self.close()
                    raise RuntimeError("an oracle rollout worker exited unexpectedly during collect")
                continue
            if err is not None:
                self.close()
                raise RuntimeError(f"oracle rollout worker {worker_id} failed:\n{err}")
            results[worker_id] = batch
            received += 1
        ordered = [results[w] for w in sorted(results)]
        return concat_rollout_batches(ordered, consume=True)

    def close(self) -> None:
        if not self._procs:
            return
        for _ in self._procs:
            try:
                self._task_q.put(None)
            except Exception:  # noqa: BLE001
                pass
        for p in self._procs:
            p.join(timeout=10)
            if p.is_alive():
                p.terminate()
        self._procs = []


def _selfplay_worker_loop(env_config, model_config, ppo_config, task_q, result_q):
    import torch as _torch

    from .model import PolicyValueNet as _PVN

    _torch.set_num_threads(1)
    model = _PVN(env_config, model_config)
    while True:
        task = task_q.get()
        if task is None:
            return
        worker_id, state_dict, base_seed, matches, drop_prob = task
        try:
            model.load_state_dict(state_dict)
            cfg = replace(ppo_config, matches_per_iter=matches, device="cpu")
            batch = collect_selfplay_rollouts(env_config, model, cfg, base_seed=base_seed, drop_prob=drop_prob)
            result_q.put((worker_id, batch, None))
            batch = None  # release our reference; the queue keeps the object alive until the feeder thread has serialized it, then all copies are freed
        except Exception:  # noqa: BLE001
            result_q.put((worker_id, None, traceback.format_exc()))


class ParallelSelfplayCollector:
    """Spawn-context worker pool for all-4 self-play feature-dropout rollouts,
    concatenated into one RolloutBatch. Mirrors ParallelOracleCollector; the task
    additionally carries the feature-dropout probability `drop_prob`."""

    def __init__(self, env_config: EnvConfig, model_config: ModelConfig,
                 ppo_config: PPOConfig, num_workers: int) -> None:
        if num_workers < 1:
            raise ValueError("num_workers must be >= 1")
        self.env_config = env_config
        self.model_config = model_config
        self.ppo_config = ppo_config
        self.num_workers = int(num_workers)
        self._ctx = mp.get_context("spawn")
        self._task_q = None
        self._result_q = None
        self._procs = []

    def start(self) -> None:
        self._task_q = self._ctx.Queue()
        self._result_q = self._ctx.Queue()
        self._procs = []
        for _ in range(self.num_workers):
            p = self._ctx.Process(
                target=_selfplay_worker_loop,
                args=(self.env_config, self.model_config, self.ppo_config,
                      self._task_q, self._result_q),
                daemon=True,
            )
            p.start()
            self._procs.append(p)

    def collect(self, state_dict, base_seed: int, matches_per_iter: int, drop_prob: float) -> RolloutBatch:
        counts = _split_counts(matches_per_iter, self.num_workers)
        offset = 0
        dispatched = 0
        for worker_id, count in enumerate(counts):
            if count == 0:
                continue
            self._task_q.put((worker_id, state_dict, int(base_seed + offset), int(count), float(drop_prob)))
            offset += count
            dispatched += 1
        results: dict = {}
        received = 0
        while received < dispatched:
            try:
                worker_id, batch, err = self._result_q.get(timeout=30.0)
            except _queue.Empty:
                if any(p.exitcode is not None for p in self._procs):
                    self.close()
                    raise RuntimeError("a self-play rollout worker exited unexpectedly during collect")
                continue
            if err is not None:
                self.close()
                raise RuntimeError(f"self-play rollout worker {worker_id} failed:\n{err}")
            results[worker_id] = batch
            received += 1
        ordered = [results[w] for w in sorted(results)]
        return concat_rollout_batches(ordered, consume=True)

    def close(self) -> None:
        if not self._procs:
            return
        for _ in self._procs:
            try:
                self._task_q.put(None)
            except Exception:  # noqa: BLE001
                pass
        for p in self._procs:
            p.join(timeout=10)
            if p.is_alive():
                p.terminate()
        self._procs = []


def train_selfplay_oracle(env_config: EnvConfig, model_config: ModelConfig, anchor_checkpoint: Path,
                          checkpoint_dir: Path, config: PPOConfig, base_seed: int = 0,
                          run_eval: bool = False) -> list[dict]:
    """All-4 self-play feature-dropout training. Warm-start a 51ch net from the
    anchor; each iteration set delta from feature_dropout_schedule, collect self-play
    rollouts with that mask probability, then compute_gae + the config-selected
    update (ppo_update, or ach_update when config.objective=="ach"). Saves the
    51ch checkpoint per iter (extract the deployable 39ch student post-hoc / at eval
    time)."""
    device = config.device
    if config.objective not in ("ppo", "ach"):
        raise ValueError(
            f"train_selfplay_oracle: config.objective must be 'ppo' or 'ach', "
            f"got {config.objective!r} (a typo would silently train PPO)")
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    model = build_oracle_model(env_config, model_config, anchor_checkpoint, device)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr)
    update_fn = ach_update if config.objective == "ach" else ppo_update
    history: list[dict] = []
    collector = None
    pool = None
    if config.collector == "batched":
        from .batched_selfplay import collect_selfplay_rollouts_batched
        from .envpool import make_selfplay_pool
        pool = make_selfplay_pool(env_config, config, config.pool_slots)
    elif config.num_workers > 1:
        collector = ParallelSelfplayCollector(env_config, model_config, config, config.num_workers)
        collector.start()
    try:
        for iteration in range(1, config.iterations + 1):
            delta = feature_dropout_schedule(iteration, config.iterations)
            iter_seed = base_seed + iteration * config.matches_per_iter
            if pool is not None:
                batch = collect_selfplay_rollouts_batched(
                    env_config, model, config, base_seed=iter_seed, drop_prob=delta, pool=pool)
            elif collector is not None:
                state = cpu_state_snapshot(model)
                batch = collector.collect(state, iter_seed, config.matches_per_iter, delta)
            else:
                batch = collect_selfplay_rollouts(env_config, model, config, base_seed=iter_seed, drop_prob=delta)
            advantages, returns = compute_gae(batch.rewards, batch.values, batch.dones,
                                              config.gamma, config.gae_lambda)
            metrics = update_fn(model, optimizer, batch, advantages, returns, config)
            metrics["iteration"] = iteration
            metrics["delta"] = delta
            metrics["mean_reward"] = float(np.sum(batch.rewards) / max(1.0, float(batch.dones.sum())))
            metrics["steps"] = len(batch)
            # Record ACH metadata only on the ACH path so the default PPO history
            # schema is byte-unchanged (no new keys on pre-existing PPO runs).
            if config.objective == "ach":
                metrics["objective"] = config.objective
                metrics["ach_beta"] = config.ach_beta
            save_checkpoint(checkpoint_dir / f"iter_{iteration:03d}.pt", model)
            history.append(metrics)
            (checkpoint_dir / "history.json").write_text(json.dumps(history))
            print(f"iter {iteration}: delta={delta:.3f} policy_loss={metrics['policy_loss']:.4f} "
                  f"value_loss={metrics['value_loss']:.4f} entropy={metrics['entropy']:.4f} "
                  f"mean_reward={metrics['mean_reward']:.4f}")
    finally:
        if collector is not None:
            collector.close()
        if pool is not None:
            pool.close()
    return history


def train_oracle(env_config: EnvConfig, model_config: ModelConfig, anchor_checkpoint: Path,
                 checkpoint_dir: Path, config: PPOConfig, base_seed: int = 0,
                 run_eval: bool = False) -> list[dict]:
    """Warm-start a 51ch oracle from the anchor and train it single-seat vs the
    env's heuristic with dense score reward (reuses compute_gae + ppo_update)."""
    device = config.device
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    model = build_oracle_model(env_config, model_config, anchor_checkpoint, device)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr)
    history: list[dict] = []
    # Parallel single-seat collection (CPU-inference workers) when num_workers > 1;
    # the GPU update stays in the parent. The env is CPU-bound on shanten search, so
    # this is the main throughput lever (mirrors the PPO ParallelRolloutCollector).
    collector = None
    if getattr(config, "num_workers", 1) > 1:
        collector = ParallelOracleCollector(env_config, model_config, config, config.num_workers)
        collector.start()
    try:
        for iteration in range(1, config.iterations + 1):
            iter_seed = base_seed + iteration * config.matches_per_iter
            if collector is not None:
                state = cpu_state_snapshot(model)
                batch = collector.collect(state, iter_seed, config.matches_per_iter)
            else:
                batch = collect_oracle_rollouts(env_config, model, config, base_seed=iter_seed)
            advantages, returns = compute_gae(batch.rewards, batch.values, batch.dones,
                                              config.gamma, config.gae_lambda)
            metrics = ppo_update(model, optimizer, batch, advantages, returns, config)
            metrics["iteration"] = iteration
            metrics["mean_reward"] = float(np.sum(batch.rewards) / max(1.0, float(batch.dones.sum())))
            metrics["steps"] = len(batch)
            save_checkpoint(checkpoint_dir / f"iter_{iteration:03d}.pt", model)
            history.append(metrics)
            (checkpoint_dir / "history.json").write_text(json.dumps(history))
            print(f"iter {iteration}: policy_loss={metrics['policy_loss']:.4f} "
                  f"value_loss={metrics['value_loss']:.4f} entropy={metrics['entropy']:.4f} "
                  f"mean_reward={metrics['mean_reward']:.4f}")
    finally:
        if collector is not None:
            collector.close()
    return history

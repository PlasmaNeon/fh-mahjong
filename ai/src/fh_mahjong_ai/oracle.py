"""Oracle-guiding helpers (Phase 1): build a perfect-information policy
warm-started from the 39-channel anchor."""
from __future__ import annotations

import json
import logging
import math
import multiprocessing as mp
import os
import queue as _queue
import random
import traceback
from dataclasses import asdict, replace
from pathlib import Path
from typing import Optional

import numpy as np
import torch

from .ach import ach_update
from .bridge import build_bridge
from .config import EnvConfig, ModelConfig
from .env import MahjongEnv
from .model import PolicyValueNet, _reconstruct_env_config
from .parallel_rollouts import _split_counts
from .ppo import (
    RolloutBatch, PPOConfig, compute_gae, concat_rollout_batches, ppo_update,
    masked_policy_distribution, _obs_to_tensors, _seat_step_reward, LEARNING_SEAT,
    cpu_state_snapshot, _write_history_atomic,
)
from .storage import load_compatible_checkpoint, model_config_metadata, save_checkpoint

logger = logging.getLogger(__name__)


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
    if config.objective == "ach" and not (math.isfinite(config.ach_beta) and config.ach_beta > 0):
        # Require a FINITE positive hedge threshold on the ACH path. This rejects
        # nan/0/negative (which would disable the hedge or fire saturation in
        # unintended regions) AND +inf: inf is a valid math "no-hedge" sentinel but
        # json.dumps serializes it as bare `Infinity`, producing a non-standard
        # history.json that strict/cross-language consumers reject. A no-hedge
        # ablation should use a large finite beta. Fail before any setup.
        raise ValueError(
            f"train_selfplay_oracle: ach_beta must be a finite positive value for "
            f"objective='ach', got {config.ach_beta!r}")
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


def _b2b_model_env_config(env_config: EnvConfig) -> EnvConfig:
    """Derive the 39ch EnvConfig used to CONSTRUCT a B2b `PolicyValueNet`.

    The privileged-critic branch (`_value_features` in model.py) assumes
    `policy_channels == 39` so it can slice the trailing 12 oracle channels
    (`planes[:, 39:51]`) out of a 51ch observation. Constructing the model
    directly from an `oracle_observation=True` (51ch) EnvConfig would instead
    set `policy_channels = 51`, which breaks that slice at the first privileged
    forward pass. Rollout envs still run with `oracle_observation=True` (51ch
    observations) — only the model's construction config differs."""
    return EnvConfig(
        action_space_size=env_config.action_space_size,
        scalar_features=env_config.scalar_features,
        bridge_kind=env_config.bridge_kind,
        bridge_library_path=env_config.bridge_library_path,
        match_mode=env_config.match_mode,
    )


def build_b2b_model(env_config: EnvConfig, model_config: ModelConfig,
                    champion_checkpoint: Path, device: str = "cpu") -> PolicyValueNet:
    """Warm-start the B2b net from the 39ch champion. The plane stem is
    UNCHANGED (39ch policy slice), so only two tensors need surgery:
    trunk.0 (event columns zeroed => step-0 logits == champion) and
    value_head.0 (privileged columns zeroed => step-0 values == champion).
    `env_config` must be a 39ch (oracle_observation=False) config — callers
    building a B2b net from an oracle env_config should first pass it through
    `_b2b_model_env_config`."""
    model = PolicyValueNet(env_config, model_config).to(device)
    _, report = load_compatible_checkpoint(Path(champion_checkpoint), model)
    payload = torch.load(Path(champion_checkpoint), map_location="cpu")
    # FAIL CLOSED on architecture mismatch: every champion tensor must either
    # load same-shape or be one of the two explicitly-widened tensors the
    # surgery below repairs. Anything else (e.g. a residual-block count
    # mismatch) would silently drop champion layers and break the step-0
    # equivalence invariant.
    surgical = {"trunk.0.weight", "value_head.0.weight"}
    new_module_prefixes = ("event_encoder.", "privileged_encoder.",
                           "belief_head.", "dealin_head.", "rank_head.")
    bad_skipped = [k for k in report["skipped_keys"] if k not in surgical]
    bad_missing = [k for k in report["missing_keys"]
                   if k not in surgical and not k.startswith(new_module_prefixes)]
    if bad_skipped or bad_missing:
        raise RuntimeError(
            "champion checkpoint is architecturally incompatible with the B2b model "
            f"config (skipped={bad_skipped[:6]}, missing={bad_missing[:6]}) — check "
            "--model-residual-blocks and width flags against the champion"
        )
    old_trunk_w = payload["model"]["trunk.0.weight"]      # [T, P+S]
    old_value_w = payload["model"]["value_head.0.weight"]  # [V, T]
    with torch.no_grad():
        w = model.trunk[0].weight                          # [T, P+S(+E)]
        w.zero_()
        w[:, : old_trunk_w.shape[1]].copy_(old_trunk_w.to(w.device))
        model.trunk[0].bias.copy_(payload["model"]["trunk.0.bias"].to(w.device))
        if model_config.privileged_critic:
            vw = model.value_head[0].weight                # [V, T+128]
            vw.zero_()
            vw[:, : old_value_w.shape[1]].copy_(old_value_w.to(vw.device))
            model.value_head[0].bias.copy_(payload["model"]["value_head.0.bias"].to(vw.device))
    model.eval()
    return model


def grow_b2b_model(anchor_checkpoint: Path, growth_blocks: int, device: str = "cpu",
                   env_config: Optional[EnvConfig] = None) -> PolicyValueNet:
    """Warm-start a wider B2b net by stacking `growth_blocks` ReZero residual
    blocks (deep16-rezero) after a post-B2b anchor's existing plane trunk.
    Unlike `build_b2b_model` (39ch -> B2b surgery), this performs NO surgery:
    the anchor must already be a complete B2b checkpoint (event encoder,
    privileged critic, aux heads as applicable), and every one of its tensors
    must load into the grown net at identical shape — the new `growth.*`
    blocks are the ONLY architectural delta, and they are identity at
    alpha=0 (ReZeroResidualBlock), so step-0 outputs equal the anchor's
    exactly.

    `anchor_checkpoint`'s `metadata["model_config"]` is authoritative for the
    anchor's full architecture (event_window is not recoverable from tensor
    shapes alone, so an anchor without this key cannot be grown safely).
    Growing an already-grown anchor (`growth_blocks > 0` in its own config)
    is out of scope and rejected: this warm start does not attempt to
    reconcile two different ReZero stacks.

    `env_config`, when given, must be the LIVE env config that collection
    will actually run under (i.e. what the caller passes to `train_b2b`).
    The model is otherwise constructed purely from the anchor's own tensor
    shapes (`_reconstruct_env_config`), which says nothing about whether
    those shapes still match the live env — a stale anchor (older
    action-space size, different scalar-feature count, or a different
    event-history window) would silently train a model shaped to the wrong
    wire format, with `encode()`'s zero-pad/truncate masking the drift
    instead of failing. Passing `env_config` catches that up front. Callers
    that omit it (e.g. tests exercising `grow_b2b_model` in isolation, with
    no "live env" to check against) skip this cross-check."""
    anchor_checkpoint = Path(anchor_checkpoint)
    payload = torch.load(anchor_checkpoint, map_location="cpu")
    metadata = payload.get("metadata") or {}
    model_config_meta = metadata.get("model_config")
    if not isinstance(model_config_meta, dict):
        raise RuntimeError(
            "anchor lacks complete model_config metadata — grow_b2b_model requires a "
            "post-B2b checkpoint saved with metadata['model_config'] (event_window is not "
            "recoverable from tensor shapes alone)"
        )
    anchor_config = ModelConfig(**model_config_meta)
    if anchor_config.growth_blocks != 0:
        raise RuntimeError(
            f"anchor checkpoint is already grown (growth_blocks={anchor_config.growth_blocks}); "
            "growing an already-grown net is out of scope"
        )
    grown_config = replace(anchor_config, growth_blocks=growth_blocks)
    anchor_env_config = _reconstruct_env_config(payload["model"], anchor_config)
    if env_config is not None:
        live_env_config = _b2b_model_env_config(env_config)
        mismatches = []
        if anchor_env_config.action_space_size != live_env_config.action_space_size:
            mismatches.append(
                "action_space_size (anchor was trained under "
                f"{anchor_env_config.action_space_size}, live env provides "
                f"{live_env_config.action_space_size})"
            )
        if anchor_env_config.scalar_features != live_env_config.scalar_features:
            mismatches.append(
                "scalar_features (anchor was trained under "
                f"{anchor_env_config.scalar_features}, live env provides "
                f"{live_env_config.scalar_features})"
            )
        anchor_channels, anchor_area, _ = anchor_env_config.plane_shape
        live_channels, live_area, _ = live_env_config.plane_shape
        if (anchor_channels, anchor_area) != (live_channels, live_area):
            mismatches.append(
                "plane_shape (anchor was trained under "
                f"{anchor_env_config.plane_shape}, live env provides "
                f"{live_env_config.plane_shape})"
            )
        if anchor_config.event_window != env_config.event_history_window:
            mismatches.append(
                "event_window (anchor was trained under "
                f"{anchor_config.event_window}, live env provides "
                f"{env_config.event_history_window})"
            )
        if mismatches:
            raise RuntimeError(
                "grow_b2b_model: anchor checkpoint's construction shapes do not match "
                "the live env_config collection will run under — " + "; ".join(mismatches)
                + ". Refusing to silently train a model shaped to a stale anchor."
            )
    model = PolicyValueNet(anchor_env_config, grown_config).to(device)
    _, report = load_compatible_checkpoint(anchor_checkpoint, model)
    # FAIL CLOSED: every anchor tensor must load same-shape except the brand
    # new `growth.*` keys (missing from the anchor by construction, since it
    # predates this warm start). Anything else silently dropping an anchor
    # layer would break the step-0 parity invariant.
    bad_skipped = [k for k in report["skipped_keys"] if not k.startswith("growth.")]
    bad_missing = [k for k in report["missing_keys"] if not k.startswith("growth.")]
    if bad_skipped or bad_missing:
        raise RuntimeError(
            "anchor checkpoint is architecturally incompatible with the grown model "
            f"config (skipped={bad_skipped[:6]}, missing={bad_missing[:6]}) — its "
            "metadata['model_config'] does not match its own saved tensor shapes"
        )
    model.eval()
    return model


def _assemble_hindsight_labels(rows: list[tuple[int, int]], hand_outcomes: dict[int, dict],
                               final_scores: dict[int, float], bust_threshold: float,
                               truncated: bool) -> tuple[np.ndarray, np.ndarray]:
    """Pure hindsight-label assembler (Spec B2b).

    `rows`: (seat, hand_id) tuples in EMISSION order (seat-contiguous blocks,
    matching the collector's flat emission order). `hand_outcomes`: hand_id ->
    decoded round-outcome dict (bridge's `_decode_round_outcome`); a hand with
    no entry (e.g. the mock bridge, which never produces `round_outcome`)
    contributes no deal-in signal. `final_scores`: seat -> final match score
    for all 4 seats. Returns `(dealin float32[N], rank int64[N])`.

    dealin[i] = 1.0 iff rows[i]'s hand closed as a non-draw `ACTION_RON` paid
    by that row's own seat (`discarder_seat == seat`); deal-in labels survive
    truncation (they are a fact about a hand that already closed).

    rank: -1 for every row when `truncated` (no valid final standings, since
    the match never reached a terminal state); otherwise each seat's 0-based
    COMPETITION rank (the count of non-busted seats with strictly greater
    score — tied scores SHARE a rank, matching the engine's standings; an
    arbitrary tiebreak would teach one tied leader it finished second), and
    4 for any seat whose score is <= `bust_threshold` (busted seats never
    receive a numeric placement)."""
    dealin = np.zeros(len(rows), dtype=np.float32)
    for i, (seat, hand_id) in enumerate(rows):
        outcome = hand_outcomes.get(hand_id)
        if outcome is None:
            continue
        if (not outcome.get("is_draw", False)
                and outcome.get("win_type_name") == "ACTION_RON"
                and int(outcome.get("discarder_seat", -1)) == seat):
            dealin[i] = 1.0

    if truncated:
        rank_by_seat = {seat: -1 for seat in final_scores}
    else:
        seats_sorted = sorted(final_scores)
        non_busted = [s for s in seats_sorted if final_scores[s] > bust_threshold]
        rank_by_seat = {
            s: sum(1 for other in non_busted if final_scores[other] > final_scores[s])
            for s in non_busted
        }
        for s in seats_sorted:
            rank_by_seat.setdefault(s, 4)

    rank = np.asarray([rank_by_seat.get(seat, -1) for seat, _ in rows], dtype=np.int64)
    return dealin, rank


def collect_b2b_rollouts(env_config: EnvConfig, model: PolicyValueNet,
                         config: PPOConfig, base_seed: int) -> RolloutBatch:
    """Symmetric self-play PPO rollouts for Spec B2b: all four seats are the
    SAME `model`, each seat's transitions recorded seat-contiguously (mirrors
    `collect_selfplay_rollouts`). No feature-dropout (B2b's event/privileged
    channels are always on). Each row additionally carries its event-history
    (tail-padded to `model.model_config.event_window`) and, at match end, the
    hindsight `dealin_labels`/`rank_labels` assembled by
    `_assemble_hindsight_labels` from the `round_outcome` entries seen in
    `StepResult.info` (a step whose info carries `round_outcome` closes the
    CURRENT hand for all seats)."""
    device = config.device
    window = int(model.model_config.event_window)
    cfg = EnvConfig(
        action_space_size=env_config.action_space_size,
        scalar_features=env_config.scalar_features,
        bridge_kind=env_config.bridge_kind,
        bridge_library_path=env_config.bridge_library_path,
        learning_seats=(0, 1, 2, 3),
        auto_play_heuristics=False,
        max_steps_per_episode=config.max_steps_per_episode,
        match_mode=config.match_mode,
        chongci_starting_score=env_config.chongci_starting_score,
        chongci_bust_threshold=env_config.chongci_bust_threshold,
        chongci_max_hands=env_config.chongci_max_hands,
        oracle_observation=True,
        event_history_window=window,
    )
    bridge = build_bridge(cfg)
    env = MahjongEnv(cfg, bridge=bridge)
    model.eval()
    # Label parameters read from `cfg` — the SAME config the bridge simulates
    # under — so hindsight ranks can never diverge from the played match.
    # UNITS: the Go env emits chongci rewards as score deltas / 1000
    # (internal/rl/env.go) in float32. Labels are computed in EXACT integer
    # points: the accumulated float net is scaled back by 1000 and rounded
    # (float32 drift over a match is << 0.5 points), so exact-threshold
    # busts and score ties cannot flip on rounding order.
    chongci = config.match_mode == "chongci"
    starting_score = float(cfg.chongci_starting_score) if chongci else 0.0
    bust_threshold = float(cfg.chongci_bust_threshold) if chongci else float("-inf")
    planes_l, scalars_l, mask_l, actions_l = [], [], [], []
    logprobs_l, values_l, rewards_l, dones_l = [], [], [], []
    events_l, lengths_l, dealin_l, rank_l = [], [], [], []
    truncated_matches = 0
    completed_matches = 0
    outcomes_seen = 0
    try:
        for m in range(config.matches_per_iter):
            obs = env.reset(seed=base_seed + m)
            torch.manual_seed(int(base_seed + m))
            reset_result = env.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                continue
            # Match-level net per seat, accumulated UNCONDITIONALLY (incl.
            # reset-time autoplay rewards and payouts landing before a seat's
            # first decision) — the transition-crediting buffers below only
            # credit seats that have already acted, which is correct for PPO
            # telescoping but would corrupt final scores for rank labels.
            match_net = np.zeros(4, dtype=np.float64)
            if reset_result is not None:
                rr = np.asarray(reset_result.rewards, dtype=np.float64)
                match_net[: min(4, rr.shape[-1])] += rr[: min(4, rr.shape[-1])]
            seat_planes:   list[list] = [[], [], [], []]
            seat_scalars:  list[list] = [[], [], [], []]
            seat_masks:    list[list] = [[], [], [], []]
            seat_actions:  list[list] = [[], [], [], []]
            seat_logprobs: list[list] = [[], [], [], []]
            seat_values:   list[list] = [[], [], [], []]
            seat_rewards:  list[list] = [[], [], [], []]
            seat_events:   list[list] = [[], [], [], []]
            seat_lengths:  list[list] = [[], [], [], []]
            seat_hand_ids: list[list] = [[], [], [], []]
            hand_id = 0
            hand_outcomes: dict[int, dict] = {}
            step = None
            while True:
                seat = int(obs.seat)
                planes_np = np.asarray(obs.planes, dtype=np.float32)
                scalars_np = np.asarray(obs.scalars, dtype=np.float32)
                mask_np = np.asarray(obs.action_mask, dtype=np.int8)
                row_events = np.zeros(window, dtype=np.uint32)
                ev = np.asarray(obs.event_history, dtype=np.uint32)
                ev_len = min(int(ev.shape[0]), window)
                if ev_len > 0:
                    # TAIL of the history (newest events) — matches the
                    # serving-side TorchGreedyPolicy convention. Unreachable
                    # difference today (bridge window == model window) but the
                    # conventions must not drift.
                    row_events[:ev_len] = ev[-ev_len:]
                planes = torch.from_numpy(planes_np).unsqueeze(0).to(device)
                scalars = torch.from_numpy(scalars_np).unsqueeze(0).to(device)
                amask = torch.from_numpy(mask_np).unsqueeze(0).to(device)
                events_t = torch.from_numpy(row_events.astype(np.int64)).unsqueeze(0).to(device)
                length_t = torch.tensor([ev_len], dtype=torch.int64, device=device)
                with torch.no_grad():
                    logits, value = model(planes, scalars, amask, events=events_t, event_lengths=length_t)
                    logits = logits / max(config.sample_temperature, 1e-6)
                    dist = masked_policy_distribution(logits)
                    action = int(dist.sample()[0].item())
                    logprob = float(dist.log_prob(torch.tensor([action], device=device))[0])
                    val = float(value[0].item())
                seat_planes[seat].append(planes_np)
                seat_scalars[seat].append(scalars_np)
                seat_masks[seat].append(mask_np)
                seat_actions[seat].append(action)
                seat_logprobs[seat].append(logprob)
                seat_values[seat].append(val)
                seat_rewards[seat].append(0.0)
                seat_events[seat].append(row_events)
                seat_lengths[seat].append(ev_len)
                seat_hand_ids[seat].append(hand_id)
                step = env.step(action)
                sr = np.asarray(step.rewards, dtype=np.float64)
                match_net[: min(4, sr.shape[-1])] += sr[: min(4, sr.shape[-1])]
                for k in range(4):
                    if seat_rewards[k]:
                        seat_rewards[k][-1] += _seat_step_reward(step.rewards, k)
                outcome = step.info.get("round_outcome")
                if outcome:
                    outcomes_seen += 1
                if outcome:
                    hand_outcomes[hand_id] = outcome
                    hand_id += 1
                if step.terminated or step.truncated:
                    break
                obs = step.observation
            is_truncated = bool(step.truncated) if step is not None else False
            if not is_truncated:
                completed_matches += 1
            if is_truncated:
                truncated_matches += 1
            final_scores = {k: starting_score + round(float(match_net[k]) * 1000.0) for k in range(4)}
            rows: list[tuple[int, int]] = []
            for k in range(4):
                rows.extend((k, hid) for hid in seat_hand_ids[k])
            dealin_labels, rank_labels = _assemble_hindsight_labels(
                rows, hand_outcomes, final_scores, bust_threshold=bust_threshold,
                truncated=is_truncated)
            offset = 0
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
                events_l.extend(seat_events[k])
                lengths_l.extend(seat_lengths[k])
                dealin_l.extend(dealin_labels[offset : offset + n].tolist())
                rank_l.extend(rank_labels[offset : offset + n].tolist())
                offset += n
    finally:
        close = getattr(bridge, "close", None)
        if callable(close):
            close()
    if chongci and completed_matches > 0 and outcomes_seen == 0:
        # A completed chongci match ALWAYS surfaces at least one round
        # outcome on the step path (internal/rl/env.go attaches boundary and
        # terminal outcomes). Zero outcomes across completed matches means
        # the bridge library predates that fix — deal-in supervision would
        # silently degenerate to all-negative labels for the whole run.
        raise RuntimeError(
            "no round outcomes surfaced across "
            f"{completed_matches} completed chongci matches — the Go bridge library "
            "predates chongci round-outcome delivery; rebuild it "
            "(go build -buildmode=c-shared ./cmd/rlbridge)"
        )
    if not actions_l:
        raise RuntimeError("collect_b2b_rollouts produced no decisions")
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
        events=np.stack(events_l).astype(np.uint32),
        event_lengths=np.asarray(lengths_l, dtype=np.int32),
        dealin_labels=np.asarray(dealin_l, dtype=np.float32),
        rank_labels=np.asarray(rank_l, dtype=np.int64),
    )


def _b2b_worker_loop(env_config, model_config, ppo_config, task_q, result_q):
    import torch as _torch

    from .model import PolicyValueNet as _PVN

    _torch.set_num_threads(1)
    model = _PVN(_b2b_model_env_config(env_config), model_config)
    while True:
        task = task_q.get()
        if task is None:
            return
        worker_id, state_dict, base_seed, matches = task
        try:
            model.load_state_dict(state_dict)
            cfg = replace(ppo_config, matches_per_iter=matches, device="cpu")
            batch = collect_b2b_rollouts(env_config, model, cfg, base_seed=base_seed)
            _apply_test_b2b_worker_perturbation(batch, matches)
            result_q.put((worker_id, batch, None))
            batch = None  # release our reference; the queue keeps the object alive until the feeder thread has serialized it, then all copies are freed
        except Exception:  # noqa: BLE001 - report any worker failure to the parent
            result_q.put((worker_id, None, traceback.format_exc()))


def _apply_test_b2b_worker_perturbation(batch: RolloutBatch, matches: int) -> None:
    """Spawn-safe can-fail hook used only by collector regression tests.

    Parent-process monkeypatches disappear when spawn re-imports this module.
    A test-only environment variable survives that boundary, so perturbation
    tests exercise the real multi-worker queue/model/lifecycle path. Only
    two-match chunks are mutated: the four-match one-worker baseline remains
    unchanged while the two-worker fan-out changes.
    """
    field = os.environ.get("FH_MAHJONG_TEST_B2B_PERTURB_FIELD")
    if field is None or matches != 2:
        return
    if field == "events":
        if batch.events is None:
            raise RuntimeError("events perturbation requires B2b event rows")
        batch.events[0, 0] ^= 1
    elif field in {"rewards", "old_logprobs"}:
        values = getattr(batch, field)
        values[0] += 1.0
    elif field == "dones":
        batch.dones[0] = 1.0 - batch.dones[0]
    else:
        raise RuntimeError(
            "unknown FH_MAHJONG_TEST_B2B_PERTURB_FIELD value "
            f"{field!r}")


class ParallelB2bCollector:
    """Spawn-context worker pool for Spec B2b self-play rollouts, concatenated
    into one RolloutBatch. Mirrors `ParallelSelfplayCollector` (seeding,
    seed-block splitting, result-queue conventions) minus `drop_prob` — B2b has
    no feature-dropout schedule."""

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
                target=_b2b_worker_loop,
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
                    raise RuntimeError("a B2b rollout worker exited unexpectedly during collect")
                continue
            if err is not None:
                self.close()
                raise RuntimeError(f"B2b rollout worker {worker_id} failed:\n{err}")
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


_RESUME_MISSING = object()


def _train_b2b_config_echo(config: PPOConfig, model_config: ModelConfig, env_config: EnvConfig) -> dict:
    """Snapshot of the three config dataclasses that fully determine a
    `train_b2b` recipe, in plain-dict form so it round-trips through
    `torch.save`/`torch.load` and compares by value. Stored in
    `train_state.pt["config_echo"]` and re-derived from the CALLER-supplied
    configs on `--resume-from-state` for the mismatch check below."""
    return {
        "ppo_config": asdict(config),
        "model_config": model_config_metadata(model_config),
        "env_config": asdict(env_config),
    }


_RESUME_IGNORED_FIELDS = {
    # "iterations" is deliberately exempt: --resume-from-state's whole point is
    # to keep training PAST what the state file was saved under (e.g. resume a
    # 2-iteration state with --iterations 260), so a higher target here is the
    # expected, common case rather than a recipe drift.
    ("ppo_config", "iterations"),
}


def _validate_resume_config_echo(current: dict, saved: dict) -> None:
    """Raise with a clear, specific message on the FIRST field that differs
    between the currently-supplied configs and the ones a `train_state.pt`
    was saved under. Resuming under a different recipe (a changed lr, event
    window, ...) silently corrupts the run (e.g. an optimizer whose momentum
    was tuned for a different lr), so any drift is an error, not a warning —
    except `ppo_config.iterations` (see `_RESUME_IGNORED_FIELDS`)."""
    for section in ("ppo_config", "model_config", "env_config"):
        current_section = current[section]
        saved_section = saved[section]
        keys = sorted(set(current_section) | set(saved_section))
        for key in keys:
            if (section, key) in _RESUME_IGNORED_FIELDS:
                continue
            current_value = current_section.get(key, _RESUME_MISSING)
            saved_value = saved_section.get(key, _RESUME_MISSING)
            if current_value != saved_value:
                raise ValueError(
                    f"--resume-from-state config mismatch in {section}.{key}: "
                    f"state file has {saved_value!r}, currently-supplied config has "
                    f"{current_value!r} — resuming under a different recipe is not "
                    "supported (pass the same configs the original run used)"
                )


def _atomic_torch_save(payload: dict, path: Path) -> None:
    """`torch.save` via a tmp-file + `os.replace` so a crash mid-write never
    leaves a half-written `train_state.pt` for the next resume to load."""
    path = Path(path)
    tmp_path = path.with_name(path.name + ".tmp")
    torch.save(payload, tmp_path)
    os.replace(tmp_path, path)


def _load_resume_history(path: Path) -> list[dict]:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        reason = "missing" if isinstance(exc, FileNotFoundError) else "corrupt"
        logger.warning(
            "history.json is %s; history was reset from a corrupt or missing "
            "file. Per-iteration checkpoints are unaffected; only the JSON "
            "log rows are lost.",
            reason,
        )
        return []


def _save_train_state(path: Path, model: torch.nn.Module, optimizer: torch.optim.Optimizer,
                      next_iteration: int, config: PPOConfig, model_config: ModelConfig,
                      env_config: EnvConfig, base_seed: int) -> None:
    payload = {
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "torch_rng": torch.get_rng_state(),
        "cuda_rng": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
        "numpy_rng": np.random.get_state(),
        "python_rng": random.getstate(),
        "next_iteration": next_iteration,
        "config_echo": _train_b2b_config_echo(config, model_config, env_config),
        "base_seed": base_seed,
    }
    _atomic_torch_save(payload, path)


def train_b2b(env_config: EnvConfig, model_config: ModelConfig, champion_checkpoint: Optional[Path],
             checkpoint_dir: Path, config: PPOConfig, base_seed: int = 0,
             growth_blocks: int = 0, train_state_every: int = 5,
             resume_from_state: Optional[Path] = None) -> list[dict]:
    """Spec B2b training: warm-start the event-GRU/privileged-critic/aux-head
    net from the 39ch champion, then run PPO with the aux losses folded in
    automatically by `ppo_update` (it reads `model.model_config.aux_heads` and
    `batch.events`/`batch.dealin_labels`/`batch.rank_labels`). Mirrors
    `train_selfplay_oracle` minus feature-dropout/ACH/the batched-pool path —
    B2b has no dropout schedule and always trains PPO.

    `growth_blocks > 0` (deep16-rezero capacity growth) routes model
    construction through `grow_b2b_model` instead: `champion_checkpoint` must
    then be a complete post-B2b anchor (not the raw 39ch champion the
    growth_blocks=0 surgery path expects), and `model_config` is superseded
    by the grown model's own config (the anchor's saved architecture plus
    `growth_blocks` ReZero blocks) so every downstream checkpoint save below
    records the true architecture, including `growth_blocks`.

    Resumable state (deep16-rezero capacity lap survives box restarts):
    every `train_state_every` iterations, and always at completion, writes
    `<checkpoint_dir>/train_state.pt` (model + optimizer + torch/cuda/numpy/
    python RNG state + `next_iteration` + a `config_echo` of the three config
    dataclasses, atomically). `resume_from_state`, when given, SKIPS the
    champion/growth warm-start entirely — the model is built directly from
    the CALLER-supplied `model_config` (which must therefore already be the
    EFFECTIVE architecture the run trained under, i.e. for a growth_blocks>0
    lap, the anchor's own config with `growth_blocks` folded in — exactly
    what `config_echo["model_config"]` records) and its weights come from the
    state file, not from `champion_checkpoint`/`growth_blocks`. The
    caller-supplied `config`/`model_config`/`env_config` and `base_seed` are
    validated against the state file (any drift raises `ValueError` naming
    both values) before anything is restored, then training continues from
    `next_iteration` through `config.iterations`, appending to the existing
    `history.json` when it is valid. A missing or malformed history file is
    reset with a warning; checkpoint recovery still proceeds."""
    device = config.device
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    state_payload = None
    if resume_from_state is not None:
        # weights_only=False: the state includes numpy/python RNG state (plain
        # tuples/arrays, not just tensors), which torch's default safe
        # unpickler rejects. train_state.pt is our own trusted output.
        state_payload = torch.load(Path(resume_from_state), map_location="cpu", weights_only=False)
        saved_base_seed = state_payload.get("base_seed", _RESUME_MISSING)
        if saved_base_seed != base_seed:
            raise ValueError(
                "--resume-from-state base_seed mismatch: "
                f"state file has {saved_base_seed!r}, requested base_seed is "
                f"{base_seed!r} — resuming with a different seed schedule is "
                "not supported (pass the base_seed the original run used)"
            )
        current_echo = _train_b2b_config_echo(config, model_config, env_config)
        _validate_resume_config_echo(current_echo, state_payload["config_echo"])
        model = PolicyValueNet(_b2b_model_env_config(env_config), model_config).to(device)
        model.load_state_dict(state_payload["model"])
        start_iteration = int(state_payload["next_iteration"])
        history_path = checkpoint_dir / "history.json"
        history = _load_resume_history(history_path)
        # Reconcile against a STALE state file: train_state.pt is only written
        # every `train_state_every` iterations (plus at completion), but
        # history.json is appended every iteration. Resuming from a state
        # older than the last history rows (e.g. state saved at iter 5, then
        # iters 6-7 ran and appended to history before the process died
        # without reaching the next state-save at iter 10) must not keep
        # those orphaned rows — the loop below re-runs and re-appends
        # iterations >= start_iteration from scratch, so keep only rows
        # strictly before start_iteration or they'd be duplicated.
        # Re-running iteration N after restoring the exact model/optimizer/
        # RNG state from before it is a deterministic replay of that
        # iteration (same seed derivation from base_seed+iteration, same
        # torch/numpy/python RNG state), so the per-iteration checkpoint
        # `iter_{N:03d}.pt` files it overwrites are recomputed identically —
        # safe to clobber by name, not a second distinct result.
        history: list[dict] = [row for row in history if int(row["iteration"]) < start_iteration]
    elif growth_blocks > 0:
        model = grow_b2b_model(champion_checkpoint, growth_blocks, device, env_config=env_config)
        model_config = model.model_config
        start_iteration = 1
        history = []
    else:
        model = build_b2b_model(_b2b_model_env_config(env_config), model_config, champion_checkpoint, device)
        start_iteration = 1
        history = []
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr)
    if state_payload is not None:
        optimizer.load_state_dict(state_payload["optimizer"])
        torch.set_rng_state(state_payload["torch_rng"])
        if torch.cuda.is_available() and state_payload.get("cuda_rng") is not None:
            torch.cuda.set_rng_state_all(state_payload["cuda_rng"])
        np.random.set_state(state_payload["numpy_rng"])
        random.setstate(state_payload["python_rng"])
    collector = None
    if config.num_workers > 1:
        collector = ParallelB2bCollector(env_config, model_config, config, config.num_workers)
        collector.start()
    try:
        for iteration in range(start_iteration, config.iterations + 1):
            iter_seed = base_seed + iteration * config.matches_per_iter
            if collector is not None:
                state = cpu_state_snapshot(model)
                batch = collector.collect(state, iter_seed, config.matches_per_iter)
            else:
                batch = collect_b2b_rollouts(env_config, model, config, base_seed=iter_seed)
            advantages, returns = compute_gae(batch.rewards, batch.values, batch.dones,
                                              config.gamma, config.gae_lambda)
            metrics = ppo_update(model, optimizer, batch, advantages, returns, config)
            metrics["iteration"] = iteration
            metrics["mean_reward"] = float(np.sum(batch.rewards) / max(1.0, float(batch.dones.sum())))
            metrics["steps"] = len(batch)
            # Aux-supervision telemetry: an all-zero deal-in rate across many
            # iters is the corrupted-labels signature — watch it in history.json.
            if batch.dealin_labels is not None:
                metrics["dealin_positive_rate"] = float(np.mean(batch.dealin_labels))
            if batch.rank_labels is not None:
                metrics["rank_label_coverage"] = float(np.mean(batch.rank_labels >= 0))
            metrics["truncated_matches"] = int(batch.truncated_matches)
            matches_total = max(1, int(config.matches_per_iter))
            truncation_rate = batch.truncated_matches / matches_total
            metrics["truncation_rate"] = float(truncation_rate)
            if truncation_rate > 0.02:
                # Truncated matches keep censored partial returns with done=1
                # (the champion recipe's semantics; truncations were ~0 at
                # max-steps 4000). A policy could exploit that by stalling
                # into the cap — a rising rate is that exploit's signature,
                # so the run halts loudly instead of optimizing it.
                raise RuntimeError(
                    f"iter {iteration}: truncation rate {truncation_rate:.1%} exceeds 2% — "
                    "a stalling policy can exploit censored truncation returns; "
                    "investigate before continuing (raise max_steps_per_episode or "
                    "inspect the policy)"
                )
            save_checkpoint(
                checkpoint_dir / f"iter_{iteration:03d}.pt", model,
                # Pins the trained horizon/architecture so fh-mj-evaluate can
                # refuse to run this checkpoint under a different effective
                # window (silent mis-evaluation guard). The "b2b" four-flag
                # block stays for older readers; "model_config" is the
                # complete ModelConfig so Spec B2c loaders (infer_model_config)
                # can reconstruct the architecture exactly instead of
                # re-deriving it from tensor shapes.
                metadata={
                    "b2b": {
                        "event_window": int(model_config.event_window),
                        "privileged_critic": bool(model_config.privileged_critic),
                        "aux_heads": bool(model_config.aux_heads),
                        "residual_blocks": int(model_config.residual_blocks),
                    },
                    "model_config": model_config_metadata(model_config),
                })
            history.append(metrics)
            _write_history_atomic(checkpoint_dir / "history.json", history)
            print(f"iter {iteration}: policy_loss={metrics['policy_loss']:.4f} "
                  f"value_loss={metrics['value_loss']:.4f} entropy={metrics['entropy']:.4f} "
                  f"mean_reward={metrics['mean_reward']:.4f}")
            is_last_iteration = iteration == config.iterations
            if train_state_every > 0 and (iteration % train_state_every == 0 or is_last_iteration):
                _save_train_state(
                    checkpoint_dir / "train_state.pt", model, optimizer,
                    next_iteration=iteration + 1, config=config, model_config=model_config,
                    env_config=env_config, base_seed=base_seed,
                )
    finally:
        if collector is not None:
            collector.close()
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

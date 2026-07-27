"""Oracle-guiding helpers (Phase 1): build a perfect-information policy
warm-started from the 39-channel anchor."""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import math
import multiprocessing as mp
import os
import queue as _queue
import random
import re
import shutil
import traceback
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import torch

from .ach import ach_update
from .bridge import build_bridge, resolve_bridge_library_path
from .config import EnvConfig, ModelConfig
from .env import MahjongEnv
from .model import PolicyValueNet, _derive_growth_blocks, _reconstruct_env_config
from .parallel_rollouts import _split_counts
from .ppo import (
    _fsync_dir,
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
    # Adversarial round 13, medium finding: trust the STATE DICT, not the
    # metadata's growth_blocks claim -- an anchor whose metadata lies about
    # growth_blocks==0 while its tensors actually carry growth.*.alpha keys
    # (nonzero alphas) would otherwise load those tensors into "growth_blocks=0"
    # slots undetected, silently breaking the step-0 warm-start parity this
    # function exists to guarantee. `_derive_growth_blocks` counts alpha keys
    # directly off the state dict and fails closed on a malformed/tampered
    # index set, so this check cannot be fooled by metadata alone.
    #
    # Adversarial round 18, medium finding: round 13's check above only
    # covers an UNDER-claim (metadata says 0, state dict has real growth
    # tensors). The inverse -- metadata OVER-claims growth_blocks>0 while the
    # state dict carries NO growth.* keys at all (a stripped grown
    # checkpoint) -- used to sail straight through, since the old guard only
    # tested `derived_growth_blocks != 0`. Reuse the same shape (claim vs.
    # state-dict-derived) that `infer_model_config`'s
    # `_verify_metadata_matches_shapes` uses for every other ModelConfig
    # field: the claim and the derivation must AGREE, and the only value
    # this function is willing to grow from is 0/0. Any other combination --
    # over-claim, under-claim, or a genuinely-already-grown anchor where both
    # agree at a nonzero count -- raises, naming both values, since growing
    # an already-grown (or inconsistently-labeled) net is out of scope.
    derived_growth_blocks = _derive_growth_blocks(payload["model"])
    if anchor_config.growth_blocks != 0 or derived_growth_blocks != 0:
        raise RuntimeError(
            "anchor checkpoint is not a valid growth_blocks=0 base for grow_b2b_model: "
            f"metadata claims growth_blocks={anchor_config.growth_blocks}, but the state "
            f"dict's derived growth block count is {derived_growth_blocks} (field: "
            f"(claimed, shape_derived))=growth_blocks=({anchor_config.growth_blocks}, "
            f"{derived_growth_blocks}); growing an already-grown net (or a checkpoint "
            "whose metadata claim disagrees with its own tensors) is out of scope"
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
            result_q.put((worker_id, batch, None))
            batch = None  # release our reference; the queue keeps the object alive until the feeder thread has serialized it, then all copies are freed
        except Exception:  # noqa: BLE001 - report any worker failure to the parent
            result_q.put((worker_id, None, traceback.format_exc()))


class ParallelB2bCollector:
    """Spawn-context worker pool for Spec B2b self-play rollouts, concatenated
    into one RolloutBatch. Mirrors `ParallelSelfplayCollector` (seeding,
    seed-block splitting, result-queue conventions) minus `drop_prob` — B2b has
    no feature-dropout schedule.

    `worker_target` (adversarial round 9, medium finding) overrides the
    per-worker process entry point; defaults to `_b2b_worker_loop`, the
    production path. This exists ONLY so tests (e.g. `test_collect_bench.py`'s
    spawn-path perturbation regressions) can inject a test-only worker
    function -- picklable by `multiprocessing`'s spawn context because it is
    a plain module-level callable, not a closure -- instead of the previous
    `FH_MAHJONG_TEST_B2B_PERTURB_FIELD` environment variable the production
    worker used to read. That env var was a production-code hook: any
    process (a CI runner, a shell profile, an inherited env from a parent
    launcher) that happened to set it would silently corrupt real training
    data, since spawned child processes inherit the parent's environment.
    Production callers (`train_b2b`) never pass `worker_target`, so they are
    unaffected."""

    def __init__(self, env_config: EnvConfig, model_config: ModelConfig,
                 ppo_config: PPOConfig, num_workers: int,
                 worker_target: Optional[Callable] = None) -> None:
        if num_workers < 1:
            raise ValueError("num_workers must be >= 1")
        self.env_config = env_config
        self.model_config = model_config
        self.ppo_config = ppo_config
        self.num_workers = int(num_workers)
        self._worker_target = worker_target if worker_target is not None else _b2b_worker_loop
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
                target=self._worker_target,
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


def _resolve_current_bridge_fingerprint(env_config: EnvConfig) -> tuple[Optional[str], Optional[str]]:
    """(resolved_path, sha256) of the Go bridge library `env_config`'s CURRENT
    resolution points at, mirroring `fh-mj-compare`'s provenance digest
    (`evaluate._bridge_library_digest`) so a `--resume-from-state` run can
    pin the identical simulator binary a fresh launch would load, not just
    the `bridge_kind`/`bridge_library_path` *configuration* that
    `config_echo` already records (adversarial round 13, high finding:
    rebuilding the .so at the same path leaves `config_echo` byte-identical
    while the actual simulator changes under it).

    `bridge_kind != "go"` (e.g. the mock bridge used throughout tests) has
    no library to pin -- both are `None`, and `None == None` at the resume
    check below is a pass, matching `evaluate.py`'s existing convention.

    A `bridge_kind == "go"` run, by contrast, MUST have a real, readable
    simulator binary to pin. Adversarial round 16, high finding: this used
    to swallow `OSError` here too and return `(None, None)` -- indistinguish-
    able from a genuine mock config -- which let a fresh Go-backed run whose
    library was missing/unreadable pin `(None, None)` silently, and
    `_verify_bridge_unchanged`'s `pinned_bridge_sha256 is None` guard then
    no-ops for the WHOLE run, permanently disabling drift protection instead
    of refusing to start. So for `bridge_kind == "go"`, an `OSError` while
    resolving/reading the library now propagates (re-raised naming the
    resolved path and the underlying errno) instead of degrading to the
    mock sentinel. There is deliberately no retry here: a single failed
    read aborts the run even if a later read of the identical path would
    happen to succeed -- a transient/flaky read failure is not
    distinguishable, from this call alone, from a library that could vanish
    again mid-run, and "try again and hope" is exactly the silent-recovery
    behavior this fix removes."""
    if env_config.bridge_kind != "go":
        return None, None
    path = resolve_bridge_library_path(env_config.bridge_library_path)
    try:
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError as exc:
        raise OSError(
            f"cannot pin Go bridge library identity: failed to read {str(path)!r} "
            f"({exc.__class__.__name__} errno={exc.errno}: {exc.strerror or exc}) "
            "-- a bridge_kind='go' run must never start (or continue) with an "
            "unverifiable simulator identity. Fix the missing/unreadable "
            "library path and retry."
        ) from exc
    return str(path), digest


def _verify_bridge_unchanged(env_config: EnvConfig, pinned_bridge_path: Optional[str],
                              pinned_bridge_sha256: Optional[str], allow_bridge_mismatch: bool,
                              warned_state: dict) -> None:
    """Adversarial round 15, high finding: round 14's drift check lived ONLY
    inside `_save_train_state`, so it fired only on iterations that happened
    to coincide with a periodic state save (every `train_state_every`
    iterations, plus completion). Every OTHER iteration collected its
    rollouts, ran PPO, and published `iter_N.pt` + a `history.json` row
    under a simulator binary that had already drifted out from under the
    pinned identity -- `train_state_every > 1` let several such iterations
    through before the next save's check finally fired, and
    `train_state_every=0` (never state-saves) never checked at all.

    The fix: this check is now a standalone gate, called by `train_b2b`
    TWICE per iteration -- once before rollout collection starts, and once
    after the PPO update but before that iteration's `iter_N.pt`/history row
    is written -- so a drifted binary is caught before it can produce ANY
    artifact, regardless of `train_state_every`. `_save_train_state` no
    longer performs this check itself; it only ever writes the PINNED
    digest (see its docstring) once the caller has already verified it here.

    Cost: hashing a ~30MB Go bridge .so is a few milliseconds; doing it
    twice per iteration (versus once) is negligible next to a ~15-minute
    self-play iteration.

    `pinned_bridge_sha256 is None` (mock bridge) skips the check entirely,
    mirroring `_resolve_current_bridge_fingerprint`'s own convention.
    `allow_bridge_mismatch=True` downgrades a mismatch to a warning instead
    of raising -- logged ONCE for the whole run (via the shared mutable
    `warned_state` dict), not once per check, so a persistently drifted
    binary does not spam the log every iteration."""
    if pinned_bridge_sha256 is None:
        return
    current_bridge_path, current_bridge_sha256 = _resolve_current_bridge_fingerprint(env_config)
    if current_bridge_sha256 == pinned_bridge_sha256:
        return
    message = (
        "bridge library drift detected mid-run: this run pinned "
        f"bridge_sha256={pinned_bridge_sha256!r} ({pinned_bridge_path!r}) at "
        f"start, but the CURRENT bridge resolution ({current_bridge_path!r}) "
        f"now hashes to bridge_sha256={current_bridge_sha256!r} -- the Go "
        "simulator binary changed underneath this run (e.g. rebuilt at the "
        "same path mid-run). Continuing would publish a checkpoint/history "
        "row produced under a different simulator than the one this "
        "lineage is pinned to."
    )
    if not allow_bridge_mismatch:
        raise ValueError(
            message + " Aborting WITHOUT collecting/publishing anything for "
            "this iteration. If you have deliberately confirmed the new "
            "binary is an acceptable, attribution-breaking substitution, "
            "pass --allow-bridge-mismatch to downgrade this to a warning."
        )
    if not warned_state.get("warned"):
        logger.warning(
            message + " --allow-bridge-mismatch: continuing anyway (this "
            "warning is logged once for the run, not per iteration) -- "
            "attribution past this point is no longer guaranteed."
        )
        warned_state["warned"] = True


_BRIDGE_SNAPSHOT_GLOB = ".bridge-*.so"


def _bridge_snapshot_path(checkpoint_dir: Path, sha256: str) -> Path:
    """The content-addressed path a bridge library digest snapshots to:
    `<checkpoint_dir>/.bridge-<sha256-prefix16>.so`. Deterministic in both
    directions -- same content always names the same file, so concurrent
    creators (parallel workers, a fresh run vs a resume of the same
    lineage) converge on one path -- and the leading dot plus non-`iter_*.pt`
    name keeps it outside `_check_artifact_lineage_or_raise`'s `iter_*.pt`
    lineage scan by construction (see that function's docstring)."""
    return checkpoint_dir / f".bridge-{sha256[:16]}.so"


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write `data` to `path` via a tmp sibling + `fsync` + `os.replace`
    (mirrors `_atomic_torch_save`'s durability pattern), so a crash mid-copy
    never leaves a torn snapshot for a worker to `dlopen`."""
    tmp_path = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    with open(tmp_path, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)
    _fsync_dir(path.parent)


def _read_and_hash_bridge_source(source_path: str) -> tuple[bytes, str]:
    """Read `source_path` ONCE and return `(bytes, sha256-of-those-bytes)`.
    Every bridge-snapshot call site (fresh pin, resume recreation) routes
    through this single function so the digest that gets pinned/compared is
    always computed from the SAME bytes a snapshot write copies -- never
    from a second, independent read -- which is what closes the ABA window
    described in `_write_bridge_snapshot_if_needed`'s docstring."""
    resolved = Path(source_path)
    try:
        data = resolved.read_bytes()
    except OSError as exc:
        raise OSError(
            f"cannot pin Go bridge library identity: failed to read {str(resolved)!r} "
            f"({exc.__class__.__name__} errno={exc.errno}: {exc.strerror or exc}) "
            "-- a bridge_kind='go' run must never start (or continue) with an "
            "unverifiable simulator identity. Fix the missing/unreadable "
            "library path and retry."
        ) from exc
    return data, hashlib.sha256(data).hexdigest()


def _write_bridge_snapshot_if_needed(checkpoint_dir: Path, sha256: str, data: bytes) -> str:
    """Adversarial round 20, high finding: rounds 13-19 pinned/verified a
    sha256 of the bridge library's PATH, re-reading that path both at pin
    time and at every drift check -- but every rollout worker (parallel
    `spawn` workers, and the single-env path) independently `dlopen`s that
    same MUTABLE path later, on its own schedule. A swap-and-restore of the
    file between "hash" and a worker's later "load" defeats every check
    that came before (ABA); parallel workers racing a rebuild can even end
    up loading DIFFERENT binaries from each other. Hashing the path is not
    the same as binding to the bytes that get loaded.

    The fix: copy the verified library bytes ONCE into a run-owned,
    content-addressed snapshot (`_bridge_snapshot_path`) and thread THAT
    path into every `EnvConfig` handed to collection (see `train_b2b`'s
    `bridge_env_config`) -- so every worker loads the immutable snapshot,
    never the mutable source.

    Idempotent by construction: if a snapshot already exists at the
    content-addressed path for this content's digest with a matching size,
    the copy is skipped entirely -- the common case, since every worker of
    the same run (and a resume of the same lineage) computes the identical
    path for identical content. Returns the snapshot's path as a string."""
    snapshot_path = _bridge_snapshot_path(checkpoint_dir, sha256)
    already_present = False
    try:
        already_present = snapshot_path.stat().st_size == len(data)
    except OSError:
        already_present = False
    if not already_present:
        _write_bytes_atomic(snapshot_path, data)
    return str(snapshot_path)


def _create_bridge_snapshot(checkpoint_dir: Path, source_path: str) -> tuple[str, str]:
    """Read `source_path` once and (idempotently) copy it into this
    checkpoint dir's content-addressed bridge snapshot. Returns
    `(snapshot_path, sha256)`. See `_write_bridge_snapshot_if_needed` for
    the ABA rationale; kept as a single call for call sites (resume
    recreation) that don't need to split the read from the write."""
    data, sha256 = _read_and_hash_bridge_source(source_path)
    snapshot_path = _write_bridge_snapshot_if_needed(checkpoint_dir, sha256, data)
    return snapshot_path, sha256


def _resolve_bridge_snapshot_for_resume(env_config: EnvConfig, checkpoint_dir: Path,
                                        pinned_bridge_sha256: str,
                                        allow_bridge_mismatch: bool) -> tuple[str, str]:
    """Ensure this lineage's content-addressed bridge snapshot exists for a
    `--resume-from-state` run, returning `(snapshot_path, effective_sha256)`
    to thread into the resumed run's bridge `EnvConfig`.

    Snapshot-first (adversarial round 21, high finding): the common case is
    that the snapshot the ORIGINAL run created for `pinned_bridge_sha256` is
    still sitting in `checkpoint_dir` (it is a managed artifact -- see
    `_find_fresh_run_managed_artifacts` -- so nothing legitimate removes it).
    When present, its OWN bytes are re-hashed and compared against
    `pinned_bridge_sha256` -- a mismatch means the snapshot itself was
    tampered with or corrupted on disk and raises unconditionally (there is
    no override for this; the pinned bytes are gone either way). On a match,
    the snapshot is reused as-is and the caller's mutable SOURCE path is
    NEVER read, hashed, or even resolved -- a deleted or rebuilt source
    cannot brick this resume (that used to happen because the caller
    fingerprinted the source before ever reaching this function; see this
    resume path's docstring for the round-21 fix on that side).

    Only when the snapshot is MISSING does this function fall back to the
    source: if the source's CURRENT content still hashes to
    `pinned_bridge_sha256`, the snapshot is recreated from it (the source was
    never a problem, only the snapshot was lost -- e.g. `checkpoint_dir` was
    partially cleaned). If the source has since changed (rebuilt at the same
    path), recreating the snapshot under the OLD digest name is impossible --
    those exact bytes are gone -- so this raises unless the caller passed
    `--allow-bridge-mismatch`, in which case the CURRENT source is accepted
    as this lineage's new baseline: it is snapshotted under its own (new)
    digest, and that new digest is returned as the effective pin going
    forward (mirroring `--allow-bridge-mismatch`'s existing
    attribution-breaking semantics elsewhere in this module)."""
    snapshot_path = _bridge_snapshot_path(checkpoint_dir, pinned_bridge_sha256)
    if snapshot_path.exists():
        snapshot_bytes = snapshot_path.read_bytes()
        snapshot_actual_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
        if snapshot_actual_sha256 != pinned_bridge_sha256:
            raise ValueError(
                f"bridge snapshot {str(snapshot_path)!r} is corrupted: its "
                f"content-addressed name pins bridge_sha256={pinned_bridge_sha256!r} "
                f"but its CURRENT bytes hash to {snapshot_actual_sha256!r} -- the "
                "snapshot was tampered with or corrupted on disk after being "
                "written. This is never safe to resume from and has no "
                "override (the originally pinned bytes cannot be recovered "
                "from a corrupted snapshot); restore it from backup or start "
                "a fresh run."
            )
        return str(snapshot_path), pinned_bridge_sha256
    source_path = resolve_bridge_library_path(env_config.bridge_library_path)
    try:
        data, current_sha256 = _read_and_hash_bridge_source(str(source_path))
    except OSError as exc:
        raise OSError(
            f"cannot recreate missing bridge snapshot {str(snapshot_path)!r}: {exc}"
        ) from exc
    if current_sha256 == pinned_bridge_sha256:
        _write_bridge_snapshot_if_needed(checkpoint_dir, pinned_bridge_sha256, data)
        return str(snapshot_path), pinned_bridge_sha256
    if not allow_bridge_mismatch:
        raise ValueError(
            f"bridge library mismatch: snapshot {str(snapshot_path)!r} for pinned "
            f"bridge_sha256={pinned_bridge_sha256!r} is missing, and the source "
            f"library at {str(source_path)!r} no longer matches it (current "
            f"digest {current_sha256!r}) -- the source was rebuilt after the "
            "snapshot was lost, so the originally pinned bytes can no longer be "
            "recovered. Pass --allow-bridge-mismatch to accept the current "
            "source as this lineage's new baseline (it will be snapshotted and "
            "pinned going forward)"
        )
    logger.warning(
        "--allow-bridge-mismatch: bridge snapshot for bridge_sha256=%r was missing "
        "and the source has since changed (current digest %r at %r) -- accepting "
        "the CURRENT source as this lineage's new baseline",
        pinned_bridge_sha256, current_sha256, source_path,
    )
    new_snapshot_path = _write_bridge_snapshot_if_needed(checkpoint_dir, current_sha256, data)
    return new_snapshot_path, current_sha256


def _assert_bridge_pinned(env_config: EnvConfig, pinned_bridge_sha256: Optional[str]) -> None:
    """Adversarial round 16, high finding, belt-and-braces: a
    `bridge_kind="go"` run must never proceed with a null pinned digest --
    that is precisely the condition that let `_verify_bridge_unchanged`'s
    `pinned_bridge_sha256 is None` guard silently no-op for the whole run.
    Neither `_read_and_hash_bridge_source` nor `_resolve_bridge_snapshot_for_
    resume` can return `None` for a `bridge_kind == "go"` config (both raise
    instead), so this should be unreachable in practice; it exists as a hard
    stop against a future regression re-introducing that silent path.
    Called both immediately after each pinning path establishes
    `pinned_bridge_sha256` (before any snapshot/artifact mutation) and once
    more before the training loop starts, so a hypothetical bug anywhere in
    between is still caught."""
    if env_config.bridge_kind == "go" and pinned_bridge_sha256 is None:
        raise RuntimeError(
            "internal invariant violated: bridge_kind='go' but this run's "
            "pinned bridge digest is None -- refusing to start/continue "
            "training with an unpinned (unverifiable) simulator identity"
        )


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


def _validate_resume_iterations_not_truncating(current_iterations: int, saved_iterations: int,
                                               start_iteration: int) -> None:
    """Raise if resuming would silently truncate the run's original target.

    `iterations` is exempt from `_validate_resume_config_echo`'s strict
    equality check (see `_RESUME_IGNORED_FIELDS`) because extending
    training past the original target is the whole point of
    `--resume-from-state`. But that exemption cuts both ways: nothing else
    validated a LOWER target either, so a state saved from a long run
    (e.g. `--iterations 260`) resumed with a mistyped smaller value that
    still exceeds the saved `next_iteration` (e.g. `--iterations 26`) used
    to run to completion and silently rewrite `train_state.pt` as a
    "finished" 26-iteration run, discarding the original 260-iteration
    target with no error at all (adversarial round 12, high finding).

    Only fires when the requested target would actually let training
    proceed (`start_iteration <= current_iterations`) but stop strictly
    short of the saved target -- a target at or below `start_iteration`
    can't train anything regardless of the original target, and is caught
    with a more specific message by the "already satisfied" exhausted-
    target check that runs after this one."""
    if start_iteration <= current_iterations < saved_iterations:
        raise ValueError(
            "--resume-from-state would truncate the run: state was saved "
            f"from a --iterations {saved_iterations} run (currently at "
            f"iteration {start_iteration - 1}), but --iterations "
            f"{current_iterations} was requested -- resuming with a lower "
            f"target than the run was saved under is not supported (pass "
            f"{saved_iterations} (or higher), or start a new run)"
        )


def _train_state_prev_path(path: Path) -> Path:
    """The one-generation-back sibling of a `train_state.pt`-style path,
    e.g. `train_state.pt` -> `train_state.prev.pt`."""
    path = Path(path)
    return path.with_name(path.stem + ".prev" + path.suffix)


def _train_state_is_loadable(path: Path) -> bool:
    """Whether `path` currently `torch.load`s cleanly. Used only to decide if
    an existing `train_state.pt` is worth preserving as `.prev` before being
    replaced -- a file that's already torn/corrupt from some earlier crash
    is not worth keeping around under a name that shadows a genuinely good
    `.prev` generation from further back."""
    try:
        torch.load(path, map_location="cpu", weights_only=False)
        return True
    except Exception:
        return False


def _atomic_torch_save(payload: dict, path: Path) -> None:
    """`torch.save` via a tmp-file + `os.replace`, so a crash mid-write never
    leaves a half-written `train_state.pt` for the next resume to load.

    Durability (adversarial round 9, high finding): the tmp file is flushed
    and `fsync`ed before the replace, and the parent directory is `fsync`ed
    afterward (platform-guarded -- see `_fsync_dir`) so the rename itself
    survives a power loss, not just the file's bytes.

    Generation retention (same finding): a host reset landing exactly
    between one `_atomic_torch_save` completing and the NEXT one finishing
    used to leave nothing to fall back to, because the previous (still-good)
    generation had already been clobbered in place. Now, if `path` already
    holds a file that loads cleanly, it is renamed to `_train_state_prev_path
    (path)` (`train_state.prev.pt`) BEFORE the new tmp file is put in its
    place -- so the old generation is only ever destroyed once the new one
    is fully written, fsynced, and a single atomic rename away from
    replacing it. `train_state.pt` and `train_state.prev.pt` are both
    managed artifacts of the fresh-dir guard / `--fresh-run-overwrite`
    deletion (see `_find_fresh_run_managed_artifacts`) but are never
    lineage-scanned as `iter_*.pt` files. A resume should use
    `_load_train_state_with_fallback`, which tries `path` first and falls
    back to `.prev` when the newest generation is unreadable."""
    path = Path(path)
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "wb") as f:
        torch.save(payload, f)
        f.flush()
        os.fsync(f.fileno())
    if path.exists() and _train_state_is_loadable(path):
        os.replace(path, _train_state_prev_path(path))
    os.replace(tmp_path, path)
    _fsync_dir(path.parent)


def _load_train_state_with_fallback(path: Path) -> dict:
    """Load a `--resume-from-state` payload from `path`, falling back to its
    `.prev` sibling generation (`_train_state_prev_path`) when `path` itself
    is unreadable (adversarial round 9, high finding) -- e.g. a host reset
    landed between `_atomic_torch_save` promoting the previous generation to
    `.prev` and completing the final rename, or corrupted the newest file
    outright. Logs which generation was actually loaded. Raises (chaining
    both underlying errors) only when BOTH generations are unreadable, or
    `path` is missing/unreadable with no `.prev` fallback on disk at all."""
    path = Path(path)
    prev_path = _train_state_prev_path(path)
    try:
        payload = torch.load(path, map_location="cpu", weights_only=False)
    except Exception as exc:
        if not prev_path.exists():
            raise
        logger.warning(
            "--resume-from-state: %s is unreadable (%s: %s); falling back to "
            "the previous generation %s",
            path, type(exc).__name__, exc, prev_path,
        )
        try:
            payload = torch.load(prev_path, map_location="cpu", weights_only=False)
        except Exception as prev_exc:
            raise RuntimeError(
                f"--resume-from-state: both {path} and its fallback generation "
                f"{prev_path} are unreadable ({type(exc).__name__}: {exc}; "
                f"fallback {type(prev_exc).__name__}: {prev_exc}) -- cannot "
                "resume from either generation"
            ) from prev_exc
        logger.warning("--resume-from-state: resumed from fallback generation %s", prev_path)
        return payload
    logger.info("--resume-from-state: loaded %s", path)
    return payload


def read_b2b_history_rows(path: Path) -> list[dict]:
    """Public accessor for `train_b2b`'s `history.json` rows, tolerant of both
    the current `{"run_id": ..., "rows": [...]}` wrapper (adversarial round 3,
    Finding 1: `run_id` binds a `history.json` to the `train_state.pt` it
    belongs to, so a resume can't silently splice unrelated run histories
    together) and the legacy bare-list format written before `run_id` existed.
    In-repo/box-side consumers of `history.json` (screening scripts,
    telemetry checks) should use this instead of `json.loads(...)` directly
    so they keep working across the format change."""
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        return data
    return data["rows"]


def _artifact_run_id(path: Path) -> Optional[str]:
    """`metadata["run_id"]` of an `iter_*.pt` checkpoint, or `None` if the
    checkpoint has no metadata / no `run_id` key (pre-round-4 checkpoint)."""
    payload = torch.load(path, map_location="cpu")
    metadata = payload.get("metadata") or {}
    return metadata.get("run_id")


_ITER_CHECKPOINT_NAME_RE = re.compile(r"^iter_(\d+)\.pt$")

_STALE_CHECKPOINT_SUFFIX = ".stale"


def _quarantine_stale_future_checkpoints(checkpoint_dir: Path, start_iteration: int) -> list[Path]:
    """Rename every `iter_N.pt` in `checkpoint_dir` with `N >= start_iteration`
    to `iter_N.pt.stale`, atomically (`os.replace` -- same filesystem, so this
    is a rename, never a copy+delete window). Returns the list of quarantined
    `.stale` paths.

    Adversarial round 19, high finding: `--resume-from-state` truncates
    `history.json`/its in-memory history back to `start_iteration` (see the
    caller, just below this function's call site), but pre-round-19 left any
    `iter_N.pt` for `N >= start_iteration` sitting on disk, live, until the
    replayed loop happened to reach and overwrite it by name. CUDA replay is
    not bit-identical (nondeterministic reductions, cuDNN algorithm
    selection), so a resumed iteration N can legitimately diverge from
    whatever produced the OLD `iter_N.pt` -- that old file still carries the
    resuming state's `run_id` (it is not a lineage mismatch by
    `_check_artifact_lineage_or_raise`'s test) but no longer descends from the
    trajectory this resume actually replays. Anything that reads `iter_N.pt`
    by name during the window between resume-start and that iteration's
    replay finishing -- concurrent screening/eval tooling, or a second crash
    mid-replay before the fresh file lands -- could silently select an
    obsolete-trajectory checkpoint with a same-`run_id` label that looks
    perfectly legitimate.

    The `.stale` suffix, not a `iter_*.pt` name, is deliberate: it drops the
    file out of every glob that matters without any glob needing to change
    for it --  `_check_artifact_lineage_or_raise`'s `iter_*.pt` scan,
    screening/eval tooling's own `iter_*.pt` globs, and (for the CLI's
    resume-then-later-fresh-launch path) `_find_fresh_run_managed_artifacts`'s
    `iter_*.pt` glob all already require a `.pt`-terminated name, which
    `iter_NNN.pt.stale` is not. `_find_fresh_run_managed_artifacts` also globs
    `iter_*.pt.stale` explicitly (see its docstring) so a leftover quarantine
    file from an interrupted resume is still covered by the fresh-dir guard
    and `--fresh-run-overwrite`.

    Called by `train_b2b`'s resume branch once, after every resume validation
    (base_seed, config_echo, iterations-not-truncating, artifact-lineage,
    bridge-digest) has already passed, and before `history.json` is persisted
    or the training loop starts -- so a crash between quarantine and the
    first replayed iteration leaves on-disk state self-consistent: a
    truncated `history.json`, no live checkpoint past `start_iteration - 1`,
    and every future iteration's prior attempt safely parked under `.stale`.
    The caller deletes each `.stale` file the moment its replacement
    `iter_N.pt` is durably written (see `train_b2b`'s loop body), and sweeps
    any still-quarantined leftovers at successful run completion (e.g. a
    resume whose `--iterations` target is lower than the number of files
    quarantined here, so some are never replaced this run)."""
    quarantined: list[Path] = []
    for artifact_path in sorted(checkpoint_dir.glob("iter_*.pt")):
        match = _ITER_CHECKPOINT_NAME_RE.match(artifact_path.name)
        if match is None or int(match.group(1)) < start_iteration:
            continue
        stale_path = artifact_path.with_name(artifact_path.name + _STALE_CHECKPOINT_SUFFIX)
        os.replace(artifact_path, stale_path)
        quarantined.append(stale_path)
    return quarantined


def _train_state_run_id(path: Path) -> Optional[str]:
    """`run_id` of a `train_state.pt`-style payload at `path` (`None` if the
    payload predates `run_id`). Raises if `path` is unreadable -- unlike an
    `iter_*.pt` checkpoint (see `_check_artifact_lineage_or_raise`'s torn-
    file tolerance), a destination train_state generation has no "at/past
    the resume point, training will regenerate it" escape hatch: it IS
    recovery evidence for the resume point, so an unreadable one can't be
    waved through."""
    payload = torch.load(path, map_location="cpu", weights_only=False)
    return payload.get("run_id")


def _check_artifact_lineage_or_raise(checkpoint_dir: Path, state_run_id: Optional[str],
                                     next_iteration: int,
                                     resume_from_state: Optional[Path] = None) -> None:
    """Guard EVERY `--resume-from-state` against silently mixing run
    lineages, whether or not `history.json` itself needed recovery
    (adversarial round 5, high finding: round 4 only ran this scan on the
    missing/corrupt-history path, so a resume with a perfectly valid,
    matching state/history pair never inspected checkpoint_dir's existing
    iter_*.pt artifacts at all -- a foreign checkpoint left behind by an
    unrelated run went undetected, since training only overwrites
    iterations >= start_iteration and leaves earlier foreign files in place
    for screening/retention tooling to pick up later).

    Scans `checkpoint_dir` for existing `iter_*.pt` artifacts -- ALL of
    them, including ones at iterations >= start_iteration that this resume
    is about to overwrite anyway: a foreign file sitting there is still
    evidence of a wrong directory even if training would clobber it a
    moment later. For each artifact, its saved `metadata["run_id"]` must
    equal `state_run_id` -- including the legacy case where both are `None`
    (pre-run_id artifact resuming from a pre-run_id state; nothing to
    compare, so it passes, preserving pre-round-4 behavior). Any artifact
    whose run_id differs (or is `None` while `state_run_id` is set --
    lineage can't be proven) raises. An empty or brand-new checkpoint_dir
    (no iter_*.pt at all) has nothing on disk to contradict the resume, so
    it passes through untouched -- relocating a state file into a fresh
    directory is fine.

    Note on cost: this does a full `torch.load` per `iter_*.pt` (metadata is
    stored inside the same pickled dict as the tensors, so there is no
    cheaper metadata-only read) with `map_location="cpu"` to avoid a GPU
    round-trip. For a large checkpoint_dir this is a one-off cost paid only
    at resume time (a rare event), not per training iteration.

    Torn-file tolerance (adversarial round 8, high finding): `iter_*.pt` is
    written non-atomically-no-more (storage.py's `save_checkpoint` now goes
    through a tmp-sibling + `os.replace`), but old runs and any crash that
    happened to land exactly between that `torch.save` and `os.replace`
    (or before this fix shipped) can still leave a torn/truncated file on
    disk. Without tolerance, `torch.load` raising on that file here would
    make `--resume-from-state` -- the feature that exists to survive a
    crash -- fail in precisely the crash window it is meant to cover. An
    unreadable artifact is handled by comparing its iteration number
    (parsed from the `iter_NNN.pt` filename) against `next_iteration`: at
    or past the resume point, training is about to regenerate that file
    anyway, so it is quarantined (renamed `<name>.corrupt`, with a logged
    warning) and the scan continues; before the resume point, the file is
    irreplaceable historical evidence that training will never rewrite, so
    the scan raises, naming the file (recoverable via
    `--force-history-reset`, which bypasses this entire scan -- see below).
    A filename that doesn't match `iter_<digits>.pt` can't be matched
    against `next_iteration` at all, so it raises rather than guessing.

    `--force-history-reset` (the `force_history_reset` flag on `train_b2b`)
    skips ONLY this check -- it is the general lineage-validation override,
    covering both the missing/corrupt-history recovery path and this
    unconditional every-resume scan -- never the base_seed/config_echo
    checks in `train_b2b`'s resume path.

    Destination train_state generations (adversarial round 11, high
    finding): the scan above only ever covered `iter_*.pt`. Resuming run A's
    state (from any path) into run B's checkpoint_dir proceeded unchallenged
    whenever B's history.json and iter_*.pt evidence were already gone
    (corrupt/missing history, pruned checkpoints) and all that remained was
    B's own `train_state.pt` / `train_state.prev.pt` -- exactly the recovery
    scenario the earlier rounds exist to protect. The very next
    `_atomic_torch_save` would then rotate/destroy B's last recovery point,
    silently splicing A's lineage into B's directory. `checkpoint_dir`'s
    `train_state.pt` and `train_state.prev.pt` are therefore inspected too,
    with `resume_from_state` (the exact file being resumed FROM) compared
    via `os.path.realpath` and skipped -- the overwhelmingly normal case is
    resuming the destination's own state in place, which is not foreign
    lineage to compare against itself. Any OTHER loadable generation found
    must carry the same `run_id` as `state_run_id` (mismatch, including a
    missing/`None` run_id while `state_run_id` is set, raises naming the
    file). Unlike `iter_*.pt`, there is no torn-file/at-resume-point
    tolerance here: an unreadable foreign generation can't have its lineage
    proven, so it raises rather than being quarantined -- recoverable only
    via `--force-history-reset`, same as the rest of this scan."""
    for artifact_path in sorted(checkpoint_dir.glob("iter_*.pt")):
        try:
            artifact_run_id = _artifact_run_id(artifact_path)
        except Exception as exc:
            match = _ITER_CHECKPOINT_NAME_RE.match(artifact_path.name)
            if match is not None and int(match.group(1)) >= next_iteration:
                quarantined_path = artifact_path.with_name(artifact_path.name + ".corrupt")
                os.replace(artifact_path, quarantined_path)
                logger.warning(
                    "%s is unreadable (%s: %s) and at/past the resume point "
                    "(iteration %s >= next_iteration %s) -- quarantined to %s; "
                    "training will regenerate it.",
                    artifact_path.name, type(exc).__name__, exc,
                    match.group(1), next_iteration, quarantined_path.name,
                )
                continue
            raise ValueError(
                f"{artifact_path.name} in checkpoint_dir is unreadable "
                f"({type(exc).__name__}: {exc}) and is needed historical "
                "evidence (its iteration is before the resume point, so "
                "training will never regenerate it) -- resuming cannot "
                "safely proceed without it (pass --force-history-reset if "
                "you are certain this file's loss is fine and want to skip "
                "the artifact-lineage scan entirely)"
            ) from exc
        if artifact_run_id != state_run_id:
            raise ValueError(
                f"{artifact_path.name} in checkpoint_dir carries "
                f"run_id={artifact_run_id!r}, which does not match the "
                f"resuming state file's run_id={state_run_id!r} -- resuming "
                "here would silently mix unrelated runs' checkpoints/history "
                "(point --resume-from-state at the checkpoint_dir that "
                "actually belongs to it, or pass --force-history-reset if "
                "you are certain this is a genuine torn-file recovery and "
                "not a lineage mixup)"
            )

    resume_from_state_real = (
        os.path.realpath(resume_from_state) if resume_from_state is not None else None
    )
    for state_name in ("train_state.pt", "train_state.prev.pt"):
        state_path = checkpoint_dir / state_name
        if not state_path.exists():
            continue
        if resume_from_state_real is not None and os.path.realpath(state_path) == resume_from_state_real:
            continue  # the destination's own state is what's being resumed, not foreign lineage
        try:
            generation_run_id = _train_state_run_id(state_path)
        except Exception as exc:
            raise ValueError(
                f"{state_path.name} in checkpoint_dir is unreadable "
                f"({type(exc).__name__}: {exc}) and its lineage relative to "
                "the resuming state file cannot be proven -- resuming cannot "
                "safely proceed without it (pass --force-history-reset if "
                "you are certain this file's loss is fine and want to skip "
                "the artifact-lineage scan entirely)"
            ) from exc
        if generation_run_id != state_run_id:
            raise ValueError(
                f"{state_path.name} in checkpoint_dir carries "
                f"run_id={generation_run_id!r}, which does not match the "
                f"resuming state file's run_id={state_run_id!r} -- resuming "
                "here would silently mix unrelated runs' train state (point "
                "--resume-from-state at the checkpoint_dir that actually "
                "belongs to it, or pass --force-history-reset if you are "
                "certain this is a genuine torn-file recovery and not a "
                "lineage mixup)"
            )


def _load_resume_history(path: Path, state_run_id: Optional[str], checkpoint_dir: Path,
                         next_iteration: int, force_history_reset: bool = False,
                         resume_from_state: Optional[Path] = None) -> list[dict]:
    """Load `history.json` for a `--resume-from-state` continuation, enforcing
    that its `run_id` matches the resuming state file's `run_id`.

    Format compatibility (adversarial round 3, Finding 1): a legacy bare-list
    `history.json` (written before `run_id` existed) has an implicit
    `run_id` of `None`. It is accepted as matching ONLY when `state_run_id`
    is also `None` (both pre-run_id) -- a state file that DOES carry a
    `run_id` resuming against a legacy bare-list history is rejected, since
    there is no way to confirm the two ever belonged together. Any other
    `run_id` mismatch (including two different UUIDs) raises, naming both,
    to stop a resume from silently merging unrelated run lineages/checkpoints
    into one checkpoint_dir.

    A missing or corrupt file resets history rows to `[]` with a warning, as
    before Finding 1 -- lineage is still preserved because the caller writes
    `state_run_id` into the fresh history going forward. Adversarial round 4,
    high finding: that reset used to run BEFORE any lineage check could catch
    a resume into the wrong checkpoint_dir. Adversarial round 5, high
    finding: round 4's fix only ran `_check_artifact_lineage_or_raise` on
    THIS missing/corrupt-history recovery path -- a resume with a perfectly
    valid, matching history.json never scanned checkpoint_dir's existing
    iter_*.pt artifacts at all, so a foreign checkpoint from an unrelated run
    could sit there undetected. The lineage scan now runs unconditionally on
    every resume (unless `force_history_reset` is set), before this file is
    even read, so both the recovery path and the normal valid-history path
    are covered by the same check. Adversarial round 11, high finding: the
    scan itself now also inspects checkpoint_dir's `train_state.pt` /
    `train_state.prev.pt` generations, not just `iter_*.pt` -- see
    `_check_artifact_lineage_or_raise`'s docstring. `resume_from_state` is
    threaded through so that check can skip the exact file being resumed
    FROM instead of comparing it against itself."""
    if not force_history_reset:
        _check_artifact_lineage_or_raise(checkpoint_dir, state_run_id, next_iteration,
                                         resume_from_state=resume_from_state)
    try:
        raw = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        reason = "missing" if isinstance(exc, FileNotFoundError) else "corrupt"
        logger.warning(
            "history.json is %s; history was reset from a corrupt or missing "
            "file. Per-iteration checkpoints are unaffected; only the JSON "
            "log rows are lost.",
            reason,
        )
        return []
    if isinstance(raw, list):
        history_run_id = None
        rows = raw
    else:
        history_run_id = raw.get("run_id")
        rows = raw.get("rows", [])
    if history_run_id != state_run_id:
        raise ValueError(
            "--resume-from-state run_id mismatch: train_state.pt has "
            f"run_id={state_run_id!r}, but history.json in the same "
            f"checkpoint_dir has run_id={history_run_id!r} -- resuming would "
            "silently mix unrelated run histories/checkpoints (point "
            "--resume-from-state at the checkpoint_dir whose history.json "
            "matches this train_state.pt, or start a fresh checkpoint_dir)"
        )
    return rows


def _save_train_state(path: Path, model: torch.nn.Module, optimizer: torch.optim.Optimizer,
                      next_iteration: int, config: PPOConfig, model_config: ModelConfig,
                      env_config: EnvConfig, base_seed: int, run_id: Optional[str],
                      pinned_bridge_sha256: Optional[str], pinned_bridge_path: Optional[str]) -> None:
    # Adversarial round 14, high finding: round 13's fix recomputed the
    # bridge fingerprint HERE, on every save -- so a .so rebuilt mid-run
    # (same path, new bytes) silently became the new saved baseline on the
    # very next periodic save, and a later --resume-from-state happily
    # accepted a run that had mixed two different simulator binaries under
    # one lineage. The fix: the bridge identity is now PINNED EXACTLY ONCE,
    # at run start (see train_b2b's fresh-run / resume branches, which
    # compute/derive `pinned_bridge_sha256`/`pinned_bridge_path` and pass
    # them in here) -- this function must never recompute those as the
    # values to STORE.
    #
    # Adversarial round 15, high finding: drift DETECTION used to also live
    # here, which meant it only ever fired on iterations that happened to
    # coincide with a periodic save -- every other iteration's checkpoint
    # and history row were published under a drifted binary before this
    # function ever ran. Detection has been hoisted out to the caller
    # (`train_b2b`, via `_verify_bridge_unchanged`), which now verifies
    # BEFORE rollout collection and again BEFORE this iteration's
    # checkpoint/history are written -- by the time `_save_train_state` is
    # reached, the caller has already confirmed no drift occurred for this
    # iteration (or that `--allow-bridge-mismatch` was given). This function
    # therefore only ever WRITES the pinned digest, never re-checks it.
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
        "run_id": run_id,
        # Always the value PINNED at run start -- never the freshly recomputed
        # current one; see the drift-detection block above.
        "bridge_sha256": pinned_bridge_sha256,
        "bridge_library_path": pinned_bridge_path,
    }
    _atomic_torch_save(payload, path)


def _growth_alpha_mean_abs(model: torch.nn.Module) -> Optional[float]:
    """Mean absolute value of every `ReZeroResidualBlock.alpha` in
    `model.growth`, or `None` for a growth-free model (`growth_blocks == 0`,
    an empty `nn.Sequential`).

    Adversarial round 2, Finding 1: `deep16-rezero`'s runbook null-
    interpretation rule ("alphas hugging 0 = protocol null signal") depends
    on these magnitudes actually being recorded somewhere — this feeds
    `train_b2b`'s per-iteration history rows. Returning `None` (rather than
    0.0) for growth-free runs lets callers distinguish "no growth blocks to
    report on" from "growth blocks present but still at/near their zero
    init" — `train_b2b` below omits the history key entirely in the `None`
    case rather than recording a misleading 0.0."""
    alphas = [block.alpha.detach().abs().item() for block in model.growth]
    if not alphas:
        return None
    return float(sum(alphas) / len(alphas))


def _find_fresh_run_managed_artifacts(checkpoint_dir: Path) -> list[Path]:
    """Files in `checkpoint_dir` that a previous `train_b2b` run would have
    written -- `history.json`, `train_state.pt`, and any `iter_*.pt`
    checkpoint -- used to guard a fresh (non-`--resume-from-state`) launch
    against silently reusing a directory that already belongs to another
    run (adversarial round 6, high finding). An empty or brand-new
    directory returns `[]`. Anything else in the directory (e.g. stray
    notes, unrelated files) is intentionally not included -- the guard, and
    `--fresh-run-overwrite`'s move-to-backup (adversarial round 18: no longer
    a delete, see `train_b2b`'s fresh branch), only ever touch these managed
    names. `train_state.prev.pt` (adversarial round 9, high finding: the
    one-generation-back durability fallback `_atomic_torch_save` keeps
    alongside `train_state.pt`) is included here too -- it belongs to this
    run exactly as much as `train_state.pt` itself, and is never
    lineage-scanned as an `iter_*.pt` file. A `.overwrite-backup-*`
    subdirectory left behind by a still-completing (or previously
    interrupted) overwrite is never matched by any of the globs/names above
    -- it holds a PRIOR run's backed-up files, not this directory's own live
    artifacts, and must survive both this guard's inspection and any future
    overwrite's move logic untouched. `iter_*.pt.stale` (adversarial round 19,
    high finding: `_quarantine_stale_future_checkpoints`'s quarantined
    obsolete-trajectory checkpoints from an in-progress or interrupted
    `--resume-from-state`) is included too -- it is exactly as much this run's
    own managed artifact as a live `iter_*.pt`, just temporarily parked
    pending its replacement or an end-of-run sweep; a fresh launch must cover
    it the same way, not leave it behind as an untouched stray file.

    `.bridge-*.so` (adversarial round 20, high finding) -- the content-
    addressed bridge-library snapshot a Go-backed run pins its simulator
    identity to (see `_create_bridge_snapshot`) -- is included too: it is
    exactly as much this run's own managed artifact as `train_state.pt`,
    so a fresh launch into a directory that still holds one must fail
    closed (or, with `--fresh-run-overwrite`, move it into the backup)
    like every other managed artifact here, rather than silently leaving a
    stale, disconnected snapshot behind for a NEW run's digest to
    accidentally collide with."""
    found = [checkpoint_dir / name
             for name in ("history.json", "train_state.pt", "train_state.prev.pt")
             if (checkpoint_dir / name).exists()]
    found.extend(sorted(checkpoint_dir.glob("iter_*.pt")))
    found.extend(sorted(checkpoint_dir.glob("iter_*.pt" + _STALE_CHECKPOINT_SUFFIX)))
    found.extend(sorted(checkpoint_dir.glob(_BRIDGE_SNAPSHOT_GLOB)))
    return found


_RUN_LOCK_NAME = ".run.lock"


def _acquire_checkpoint_dir_lock(checkpoint_dir: Path):
    """Claim exclusive ownership of `checkpoint_dir` for the lifetime of this
    process, via `fcntl.flock(LOCK_EX | LOCK_NB)` on `<checkpoint_dir>/.run.lock`
    (adversarial round 7, high finding: the fresh-dir/lineage guards above are
    TOCTOU -- two concurrent `train_b2b` launches pointed at the same
    checkpoint_dir can both pass the artifact-inspection checks, mint
    different `run_id`s, and interleave writes to the same
    iter_*.pt/history.json/train_state.pt).

    Called at the very start of `train_b2b`, before ANY artifact inspection
    or deletion -- covers the fresh, `--fresh-run-overwrite`, and
    `--resume-from-state` paths alike. The lock is released when the
    returned file object is closed (train_b2b does this in a `finally` once
    the run ends) OR when the process dies for any other reason -- flock is
    tied to the open file description, so the OS releases it automatically
    on process exit/crash. That means there is no stale-lock file to clean
    up: a leftover `.run.lock` from a crashed run is inert and the next
    launch acquires it immediately.

    `LOCK_NB` (non-blocking) means a second launch against an
    already-locked directory fails immediately with a loud, named error
    instead of hanging indefinitely waiting for the first run to finish.

    `.run.lock` is deliberately excluded from
    `_find_fresh_run_managed_artifacts`'s names: it must survive both the
    fresh-dir guard's inspection and `--fresh-run-overwrite`'s deletion --
    if overwrite deleted it, a concurrent launch could slip in during the
    brief window between that deletion and this function reacquiring it for
    the new run."""
    lock_path = checkpoint_dir / _RUN_LOCK_NAME
    lock_file = open(lock_path, "a+")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        lock_file.close()
        raise RuntimeError(
            f"could not acquire exclusive lock on {lock_path} -- another "
            f"training process likely already owns checkpoint_dir "
            f"{checkpoint_dir} (running two train_b2b launches against the "
            "same directory would otherwise interleave writes to its "
            "iter_*.pt/history.json/train_state.pt); wait for that run to "
            "finish or point --checkpoint-dir at a different directory"
        ) from exc
    # Diagnostics only -- ownership is enforced by the flock above, not by
    # this content. Overwrite any stale pid/run_id from a prior holder.
    _write_lock_owner(lock_file, run_id=None)
    return lock_file


def _write_lock_owner(lock_file, *, run_id: Optional[str]) -> None:
    """Diagnostics-only: record the owning pid (and, once known, run_id) in
    an already-`flock`-held lock file. Never part of the locking mechanism
    itself -- callers must not rely on this content for correctness, only
    the flock held on `lock_file`'s fd does that."""
    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write(f"pid={os.getpid()} run_id={run_id}\n")
    lock_file.flush()


def train_b2b(env_config: EnvConfig, model_config: ModelConfig, champion_checkpoint: Optional[Path],
             checkpoint_dir: Path, config: PPOConfig, base_seed: int = 0,
             growth_blocks: int = 0, train_state_every: int = 5,
             resume_from_state: Optional[Path] = None,
             force_history_reset: bool = False,
             fresh_run_overwrite: bool = False,
             allow_bridge_mismatch: bool = False,
             accept_legacy_unpinned_state: bool = False) -> list[dict]:
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
    reset with a warning; checkpoint recovery still proceeds.

    A `next_iteration` already `> config.iterations` raises `ValueError`
    instead of returning an empty history — resuming always intends more
    training, so an exhausted target is an error, not a silent no-op
    (adversarial round 3, Finding 2).

    Every run (fresh or `--resume-from-state`) is tagged with a `run_id`
    (a fresh `uuid4().hex` for new runs; the state file's own `run_id` when
    resuming), persisted in both `train_state.pt["run_id"]` and
    `history.json`'s `{"run_id": ..., "rows": [...]}` wrapper. A resume
    requires `state.run_id == history.run_id` (mismatch raises, naming both)
    so a `train_state.pt` from one run can never be pointed at an unrelated
    run's `history.json`/checkpoints in the same directory. Legacy bare-list
    `history.json` files (written before `run_id` existed) are accepted only
    when the state file also predates `run_id` (both `None`); use
    `read_b2b_history_rows(path)` to read rows back regardless of format
    (adversarial round 3, Finding 1).

    Every `iter_*.pt` checkpoint also carries `metadata["run_id"]`
    (adversarial round 4, high finding). On EVERY resume (adversarial round
    5, high finding: not just when history.json is missing or corrupt --
    round 4's check ran only on that recovery path, so a resume with a
    perfectly valid, matching history.json never inspected checkpoint_dir at
    all), `_check_artifact_lineage_or_raise` validates every existing
    `iter_*.pt` artifact's `run_id` against the resuming state's `run_id`
    before proceeding -- a mismatch (or a legacy artifact with no `run_id`
    while the state has one) raises instead of silently mixing lineages; an
    empty checkpoint_dir passes through. `force_history_reset=True` (the
    CLI's `--force-history-reset`; the name predates this generalization but
    is kept to avoid a runbook-breaking rename -- see its `--help` text)
    skips ONLY that artifact-lineage check, on both the recovery path and
    this unconditional every-resume scan, never the base_seed/config_echo
    checks above.

    A resume also pins the Go simulator library itself, not merely the
    bridge_kind/bridge_library_path *configuration* `config_echo` already
    covers: `train_state.pt["bridge_sha256"]` records the sha256 of the
    library `env_config` resolved to AT SAVE TIME (see
    `_resolve_current_bridge_fingerprint`), and every resume recomputes it
    from the CURRENT resolution and raises, naming both digests, on any
    mismatch -- a rebuild of the .so at the same path leaves `config_echo`
    byte-identical while silently mixing simulator versions across the
    resume boundary (adversarial round 13, high finding). This is never
    safe -- a different simulator changes the very rules the model was
    trained under -- so `force_history_reset` does NOT cover it. The
    dedicated, explicitly attribution-breaking override is
    `allow_bridge_mismatch=True` (the CLI's `--allow-bridge-mismatch`,
    named after `fh-mj-compare`'s own `--allow-bridge-mismatch`), which
    proceeds anyway but logs a warning naming both digests. Mock-bridge runs
    (`bridge_kind != "go"`) have no library to pin: both digests are
    `None`, which compares equal and always passes.

    Snapshot-first ordering (adversarial round 21, high finding): the
    source-fingerprint-and-compare step described in the previous paragraph
    is skipped ENTIRELY whenever this lineage's content-addressed bridge
    snapshot (named by the SAVED digest) already exists in `checkpoint_dir`
    -- the mutable source is not read, hashed, or even resolved in that
    case. Rounds 13-20 always fingerprinted the source here first, so a
    deleted or rebuilt source bricked resume (an unrecoverable raise, since
    the source read/compare happened before the snapshot was ever
    consulted) even though the pinned snapshot bytes sat completely intact
    on disk -- `--allow-bridge-mismatch` could not help, because the
    exception fired before that flag was ever checked. `_resolve_bridge_
    snapshot_for_resume` (below) re-hashes the snapshot's OWN bytes against
    the saved digest and raises if they were tampered with or corrupted --
    the only failure mode an intact-looking snapshot can still have -- with
    no override, since corrupted bytes cannot be un-corrupted. Only when the
    snapshot is ABSENT does this fall back to the source-based recovery
    described above (round 20's missing-snapshot rules, unchanged).

    A Go-backed state saved with no digest at all (`bridge_sha256 is None`,
    i.e. a legacy `train_state.pt` from before this pinning existed) fails
    closed (adversarial round 19, high finding: round 16 accepted this
    unconditionally and left the pin at `None` FOREVER, permanently
    disabling drift detection for the rest of the run's life). Resuming it
    now raises `ValueError` naming the remedy, `accept_legacy_unpinned_state
    =True` (the CLI's `--accept-legacy-unpinned-state`), unless that flag is
    given. WITH the flag, the resume proceeds and establishes a NEW
    provenance boundary starting at this resume: the digest the library
    CURRENTLY resolves to is pinned as this lineage's baseline from here
    forward (recorded in every subsequent `train_state.pt`/`iter_*.pt`), a
    warning is logged naming the new digest, and drift detection resumes
    normally for the rest of the run. Iterations up to and including this
    resume point have unverifiable simulator provenance (nothing was ever
    pinned for them); only iterations from here forward are drift-protected
    again. Mock-bridge states are never affected -- they never enter this
    branch at all (`bridge_kind == "go"` is required).

    A fresh (non-`resume_from_state`) call fails closed if `checkpoint_dir`
    already contains ANY managed artifact -- `history.json`,
    `train_state.pt`, or an `iter_*.pt` checkpoint (adversarial round 6,
    high finding: without this, a mistaken fresh launch into a prior run's
    directory silently overwrote its early checkpoints while leaving later
    ones in place -- mixed lineage, and potentially days of lost progress).
    The `ValueError` names what was found and points at the two legitimate
    fixes: `resume_from_state` to continue that run, or a new/empty
    `checkpoint_dir` for a truly fresh one. `fresh_run_overwrite=True` (the
    CLI's `--fresh-run-overwrite`) is the explicit destructive override: it
    deletes exactly those managed artifacts -- nothing else in the
    directory -- logs what was removed, and then proceeds as a normal fresh
    run. A brand-new or genuinely empty `checkpoint_dir` always proceeds
    without asking (mkdir-if-absent, as before)."""
    device = config.device
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    lock_file = _acquire_checkpoint_dir_lock(checkpoint_dir)
    try:
        state_payload = None
        # Adversarial round 18, high finding: only ever set (non-None) by the
        # fresh `--fresh-run-overwrite` path below, when it moved existing
        # managed artifacts into a backup subdirectory instead of deleting
        # them. `backup_cleared` starts True so a resume (or a fresh run into
        # an empty directory, which never creates a backup) never attempts to
        # clean up a backup that doesn't exist. `durability_trigger` picks
        # which save this run's OWN first durable artifact is: `train_state.pt`
        # when periodic state saves happen at all (`train_state_every > 0`),
        # else the first `iter_*.pt` checkpoint (train_state_every == 0 means
        # train_state.pt is never written for the whole run -- see
        # `test_train_state_every_zero_still_blocks_publish_of_drifted_iteration`).
        overwrite_backup_dir: Optional[Path] = None
        backup_cleared = True
        durability_trigger = "state" if train_state_every > 0 else "checkpoint"
        if resume_from_state is not None:
            # weights_only=False: the state includes numpy/python RNG state (plain
            # tuples/arrays, not just tensors), which torch's default safe
            # unpickler rejects. train_state.pt is our own trusted output.
            # `_load_train_state_with_fallback` also covers the newest
            # generation being unreadable by falling back to `.prev` (see its
            # docstring; adversarial round 9, high finding).
            state_payload = _load_train_state_with_fallback(Path(resume_from_state))
            saved_base_seed = state_payload.get("base_seed", _RESUME_MISSING)
            if saved_base_seed != base_seed:
                raise ValueError(
                    "--resume-from-state base_seed mismatch: "
                    f"state file has {saved_base_seed!r}, requested base_seed is "
                    f"{base_seed!r} — resuming with a different seed schedule is "
                    "not supported (pass the base_seed the original run used)"
                )
            # Adversarial round 13, high finding: config_echo's env_config
            # section only records the bridge_kind/bridge_library_path
            # *configuration*, which stays byte-identical across a rebuild of
            # the .so at the same path -- pin the ACTUAL simulator binary via
            # its content digest instead, recomputed from the CURRENT
            # resolution (never trusted from the state file, which is exactly
            # what a rebuild-between-runs would stale-read).
            saved_bridge_sha256 = state_payload.get("bridge_sha256")
            # Adversarial round 16, high finding: a `train_state.pt` saved by
            # a run from BEFORE the fingerprint-pinning fix existed (rounds
            # 13-15) can legitimately have `bridge_sha256=None` even though
            # `bridge_kind == "go"` -- it simply never recorded one. Treating
            # that the same as the round-13 mismatch check below would raise
            # "bridge library mismatch" (None vs a real current digest) and
            # brick every pre-fix state file outright, which is exactly the
            # kind of state-bricking `force_history_reset` was invented to
            # avoid elsewhere in this function -- except this check does NOT
            # accept `force_history_reset` (see its docstring), so there
            # would be no override at all short of `--allow-bridge-mismatch`,
            # which also (deliberately) logs a scarier "simulator changed
            # mid-lineage" warning that doesn't fit this case. Instead: a
            # `None` SAVED digest on a `bridge_kind == "go"` resume warns
            # loudly and is treated as unpinned-legacy for the rest of THIS
            # run -- no drift comparison is attempted (there is nothing to
            # compare the current digest against), and periodic saves keep
            # writing `bridge_sha256=None` rather than quietly re-pinning to
            # whatever the library happens to hash to now.
            legacy_unpinned_go_resume = env_config.bridge_kind == "go" and saved_bridge_sha256 is None
            if legacy_unpinned_go_resume:
                # Adversarial round 19, high finding: round 16's fix accepted
                # this case unconditionally and kept the pin at `None` FOREVER
                # (every subsequent `_save_train_state` for this lineage wrote
                # `bridge_sha256=None` again), which permanently disabled
                # drift detection for the rest of the run's life instead of
                # merely tolerating the one pre-existing gap. Fail closed
                # instead: a Go-backed resume whose state lacks a digest now
                # raises unless the caller explicitly opts in via
                # `--accept-legacy-unpinned-state`
                # (`accept_legacy_unpinned_state=True`). Opting in does NOT
                # keep the pin null -- it establishes a NEW provenance
                # boundary starting at this resume: the digest the library
                # CURRENTLY resolves to is pinned as of now (recorded in
                # every subsequent `train_state.pt`/`iter_*.pt` going
                # forward), so drift protection resumes for the rest of the
                # run's life. Iterations up to and including this resume
                # point have unverifiable simulator provenance (nothing was
                # ever pinned for them); iterations from here forward are
                # fully covered again.
                if not accept_legacy_unpinned_state:
                    raise ValueError(
                        "--resume-from-state: this bridge_kind='go' train_state.pt "
                        "has bridge_sha256=None -- a LEGACY state saved before "
                        "bridge identity pinning existed. Resuming it silently "
                        "would leave drift detection permanently disabled for the "
                        "rest of this run's life. Pass "
                        "--accept-legacy-unpinned-state to acknowledge this "
                        "state's pre-boundary iterations have unverifiable "
                        "simulator provenance and pin the CURRENT bridge digest "
                        "as a new provenance boundary starting from this resume"
                    )
                current_bridge_path, current_bridge_sha256 = _resolve_current_bridge_fingerprint(env_config)
                logger.warning(
                    "--accept-legacy-unpinned-state: resuming a bridge_kind='go' "
                    "train_state.pt with bridge_sha256=None -- this is a LEGACY "
                    "state saved before bridge identity pinning existed "
                    "(adversarial round 16). Establishing a NEW provenance "
                    "boundary starting now: the library currently resolves to "
                    "%r (bridge_sha256=%r), which is pinned as this lineage's "
                    "baseline from this resume forward. Iterations up to and "
                    "including this resume point have unverifiable simulator "
                    "provenance; only iterations from here forward are "
                    "drift-protected.",
                    current_bridge_path, current_bridge_sha256,
                )
                # Pin the CURRENT digest (not the missing saved one) -- unlike
                # round 16, this lineage is no longer permanently unpinned.
                saved_bridge_sha256 = current_bridge_sha256
                state_payload["bridge_library_path"] = current_bridge_path
            elif env_config.bridge_kind == "go" and _bridge_snapshot_path(checkpoint_dir, saved_bridge_sha256).exists():
                # Adversarial round 21, high finding: rounds 13-20 always
                # fingerprinted the MUTABLE source here to compare it against
                # `saved_bridge_sha256` -- even though `_resolve_bridge_snapshot_
                # for_resume` below is perfectly capable of binding this run to
                # the pinned content-addressed snapshot WITHOUT ever touching
                # the source, when that snapshot is present. A deleted or
                # rebuilt source (e.g. the .so was cleaned up, or rebuilt at the
                # same path for unrelated reasons) made `_resolve_current_bridge_
                # fingerprint` above raise or report a mismatch immediately --
                # bricking resume (or requiring `--allow-bridge-mismatch`) even
                # though the pinned bytes were sitting completely intact in
                # `checkpoint_dir` and nothing about THIS lineage's provenance
                # was actually in question.
                #
                # Fix: snapshot-first. When the snapshot named by the SAVED
                # digest already exists, skip this whole source-fingerprint-
                # and-compare step entirely -- the source is not read, and a
                # deleted/rebuilt source cannot brick or even be observed by
                # this resume. `_resolve_bridge_snapshot_for_resume` below
                # re-hashes the snapshot's OWN bytes (never the source) and
                # raises if those bytes were tampered with/corrupted, which is
                # the only case that should still abort a resume with an
                # intact-looking snapshot on disk. Only when the snapshot is
                # ABSENT does control fall through to the elif-less path below
                # (round 20's existing missing-snapshot recovery, which in turn
                # falls back to the source -- see that function's docstring).
                pass
            else:
                current_bridge_path, current_bridge_sha256 = _resolve_current_bridge_fingerprint(env_config)
                if current_bridge_sha256 != saved_bridge_sha256:
                    if not allow_bridge_mismatch:
                        raise ValueError(
                            "--resume-from-state bridge library mismatch: state file was "
                            f"saved under bridge_sha256={saved_bridge_sha256!r}, the "
                            f"CURRENT bridge resolution ({current_bridge_path!r}) hashes "
                            f"to bridge_sha256={current_bridge_sha256!r} -- the Go "
                            "simulator was rebuilt (or otherwise changed) since this run "
                            "started. Resuming under a different simulator binary is "
                            "never safe -- --force-history-reset does NOT override this "
                            "check. If you have deliberately confirmed the new binary is "
                            "an acceptable, attribution-breaking substitution, pass "
                            "--allow-bridge-mismatch to override"
                        )
                    logger.warning(
                        "--allow-bridge-mismatch: resuming despite a bridge library "
                        "mismatch (state file bridge_sha256=%r, current bridge_sha256=%r "
                        "at %r) -- attribution across this resume boundary is no longer "
                        "guaranteed",
                        saved_bridge_sha256, current_bridge_sha256, current_bridge_path,
                    )
            # Adversarial round 14, high finding: the bridge identity this run
            # threads into every _save_train_state call is pinned HERE, once,
            # to the VALIDATED saved digest -- never the freshly-recomputed
            # `current_bridge_sha256` above, even when --allow-bridge-mismatch
            # let a mismatch through. Recomputing per-save (round 13's
            # behavior) let a mid-run .so replacement quietly become the new
            # baseline; pinning to the saved value keeps the ORIGINAL
            # simulator identity as the one true baseline for this lineage.
            # A legacy-unpinned resume (round 19; see above) already rewrote
            # `saved_bridge_sha256`/`state_payload["bridge_library_path"]` to
            # the CURRENT resolution above -- this is that new provenance
            # boundary's baseline, not the (missing) original one.
            pinned_bridge_sha256 = saved_bridge_sha256
            pinned_bridge_path = state_payload.get("bridge_library_path")
            # Adversarial round 20, high finding: rebind this resumed run to
            # its content-addressed bridge snapshot the same way a fresh run
            # does -- see `_resolve_bridge_snapshot_for_resume`'s docstring
            # for the missing-snapshot/drifted-source recovery rules. Every
            # collector/rollout call below uses `bridge_env_config`, never
            # `env_config`, so the SOURCE path is never consulted again past
            # this point.
            if env_config.bridge_kind == "go":
                snapshot_path, pinned_bridge_sha256 = _resolve_bridge_snapshot_for_resume(
                    env_config, checkpoint_dir, pinned_bridge_sha256, allow_bridge_mismatch)
                _assert_bridge_pinned(env_config, pinned_bridge_sha256)
                bridge_env_config = replace(env_config, bridge_library_path=snapshot_path)
            else:
                bridge_env_config = env_config
            current_echo = _train_b2b_config_echo(config, model_config, env_config)
            _validate_resume_config_echo(current_echo, state_payload["config_echo"])
            model = PolicyValueNet(_b2b_model_env_config(env_config), model_config).to(device)
            model.load_state_dict(state_payload["model"])
            start_iteration = int(state_payload["next_iteration"])
            # Adversarial round 12, high finding: a target lower than the one
            # the state was saved under (but still above start_iteration, so
            # the exhausted-target check below wouldn't catch it) must raise
            # rather than silently truncating the run -- see
            # _validate_resume_iterations_not_truncating's docstring.
            saved_iterations = state_payload["config_echo"]["ppo_config"]["iterations"]
            _validate_resume_iterations_not_truncating(
                config.iterations, saved_iterations, start_iteration)
            # Adversarial round 3, Finding 2: an exhausted target is a silent
            # no-op, not success -- the runbook's resume command always intends
            # MORE training, so a state already past config.iterations must raise
            # loudly instead of returning an empty history.
            if start_iteration > config.iterations:
                raise ValueError(
                    f"state is at iteration {start_iteration - 1}; --iterations "
                    f"{config.iterations} already satisfied — nothing to resume; "
                    "raise --iterations or stop"
                )
            run_id = state_payload.get("run_id")
            history_path = checkpoint_dir / "history.json"
            history = _load_resume_history(history_path, run_id, checkpoint_dir,
                                           start_iteration,
                                           force_history_reset=force_history_reset,
                                           resume_from_state=Path(resume_from_state))
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
            # Adversarial round 19, high finding: quarantine every live
            # `iter_N.pt` with `N >= start_iteration` to `iter_N.pt.stale`
            # BEFORE the loop below collects or publishes anything -- see
            # `_quarantine_stale_future_checkpoints`'s docstring for why an
            # old same-run_id checkpoint at/past the resume point is not
            # trustworthy evidence of the trajectory this resume is about to
            # replay. Immediately followed by durably persisting the
            # already-truncated `history` (computed just above) so a crash
            # in the gap before the loop's first iteration leaves on-disk
            # state self-consistent: no live checkpoint or history row past
            # `start_iteration - 1`.
            pending_stale_checkpoints = _quarantine_stale_future_checkpoints(
                checkpoint_dir, start_iteration)
            _write_history_atomic(history_path, {"run_id": run_id, "rows": history})
        else:
            existing_artifacts = _find_fresh_run_managed_artifacts(checkpoint_dir)
            if existing_artifacts and not fresh_run_overwrite:
                names = ", ".join(p.name for p in existing_artifacts)
                raise ValueError(
                    f"checkpoint_dir {checkpoint_dir} already contains managed "
                    f"training artifact(s) ({names}) but this is a fresh run "
                    "(no --resume-from-state was given) -- launching here would "
                    "silently reuse/overwrite a prior run's checkpoints, mixing "
                    "lineages and risking lost progress. Either pass "
                    "--resume-from-state pointed at this directory's "
                    "train_state.pt to continue that run, use a new/empty "
                    "checkpoint_dir for a truly fresh run, or pass "
                    "--fresh-run-overwrite to delete exactly these managed "
                    "artifacts and start fresh here"
                )
            # Adversarial round 18, high finding: --fresh-run-overwrite must be
            # TRANSACTIONAL. The old implementation deleted the prior run's
            # managed artifacts before doing anything else -- if champion/anchor
            # validation, model construction, or bridge-fingerprint resolution
            # then failed, checkpoint_dir was left destroyed with no
            # replacement. Fix: validate everything that can fail FIRST, while
            # the old artifacts are still untouched, and only once all of it
            # succeeds move (never delete outright) the existing managed
            # artifacts into a timestamped backup subdirectory. The backup is
            # removed later, once this run's own first durable artifact is
            # written (see the `overwrite_backup_dir`/`backup_cleared` handling
            # in the training loop below) -- so a failure at ANY point up to
            # and including early iterations of the new run still leaves the
            # old run fully recoverable from the backup directory via a manual
            # move.
            if growth_blocks > 0:
                model = grow_b2b_model(champion_checkpoint, growth_blocks, device, env_config=env_config)
                model_config = model.model_config
            else:
                model = build_b2b_model(_b2b_model_env_config(env_config), model_config, champion_checkpoint, device)
            # Adversarial round 14, high finding: pin the bridge identity for
            # this fresh run ONCE, before any rollout collection, so every
            # `_save_train_state` call below threads the SAME pinned digest
            # rather than each recomputing (and thus potentially rebasing
            # onto) whatever binary happens to be on disk at save time. Also
            # part of round 18's transactional ordering: this can raise (e.g.
            # a "go" bridge whose library is unreadable), so it too must run
            # before any existing artifact is touched.
            #
            # Adversarial round 20, high finding: this used to pin just a
            # digest of the SOURCE path, which every worker later re-resolved
            # and `dlopen`ed independently -- an ABA swap-and-restore of that
            # mutable path between this hash and a worker's later load defeats
            # the pin entirely. The source bytes are read ONCE here (never
            # re-read after this point); the actual snapshot COPY is deferred
            # until after the `--fresh-run-overwrite` backup-move below (so a
            # content-identical leftover snapshot from a PRIOR run in
            # `existing_artifacts` gets moved into the backup, not confused
            # with this run's own snapshot-to-be), and `bridge_env_config` --
            # bound to that snapshot, never the source -- is what every
            # collector/rollout call below actually uses.
            if env_config.bridge_kind == "go":
                pinned_bridge_path = str(resolve_bridge_library_path(env_config.bridge_library_path))
                bridge_source_bytes, pinned_bridge_sha256 = _read_and_hash_bridge_source(pinned_bridge_path)
                _assert_bridge_pinned(env_config, pinned_bridge_sha256)
            else:
                pinned_bridge_path, pinned_bridge_sha256 = _resolve_current_bridge_fingerprint(env_config)
                bridge_source_bytes = None
            if existing_artifacts:
                names = ", ".join(p.name for p in existing_artifacts)
                overwrite_backup_dir = checkpoint_dir / f".overwrite-backup-{uuid.uuid4().hex}"
                overwrite_backup_dir.mkdir()
                for artifact_path in existing_artifacts:
                    # os.rename: same filesystem (both under checkpoint_dir), so
                    # this is an atomic move, not a copy+delete -- there is no
                    # window where the artifact exists in neither location.
                    os.rename(str(artifact_path), str(overwrite_backup_dir / artifact_path.name))
                backup_cleared = False
                logger.warning(
                    "--fresh-run-overwrite: moved %d prior managed artifact(s) from %s "
                    "into backup %s before starting fresh: %s. This backup is kept "
                    "until the new run writes its first durable checkpoint -- if the "
                    "new run fails before then, the old run is fully recoverable: move "
                    "these files back from %s into %s.",
                    len(existing_artifacts), checkpoint_dir, overwrite_backup_dir, names,
                    overwrite_backup_dir, checkpoint_dir,
                )
            if env_config.bridge_kind == "go":
                snapshot_path = _write_bridge_snapshot_if_needed(
                    checkpoint_dir, pinned_bridge_sha256, bridge_source_bytes)
                bridge_env_config = replace(env_config, bridge_library_path=snapshot_path)
            else:
                bridge_env_config = env_config
            start_iteration = 1
            history = []
            run_id = uuid.uuid4().hex
            # A fresh run never has anything to quarantine -- either the
            # directory was empty/new, or `--fresh-run-overwrite` just moved
            # every prior managed artifact (including any leftover `.stale`
            # files -- see `_find_fresh_run_managed_artifacts`) into the
            # backup subdirectory above.
            pending_stale_checkpoints: list[Path] = []
        # Belt-and-braces final check before the training loop starts -- see
        # `_assert_bridge_pinned`'s docstring; both branches above already
        # call it right after establishing `pinned_bridge_sha256`, so this
        # should be unreachable in practice.
        _assert_bridge_pinned(env_config, pinned_bridge_sha256)
        _write_lock_owner(lock_file, run_id=run_id)
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
            # Adversarial round 20, high finding: threads the SNAPSHOT-bound
            # env_config into every worker, never the mutable source path --
            # see `bridge_env_config`'s construction above.
            collector = ParallelB2bCollector(bridge_env_config, model_config, config, config.num_workers)
            collector.start()
        # Adversarial round 15, high finding: shared across every
        # `_verify_bridge_unchanged` call this run so a persistently-allowed
        # mismatch (`--allow-bridge-mismatch`) logs its warning ONCE for the
        # whole run rather than once per check (2x per iteration).
        bridge_drift_warned: dict = {"warned": False}
        try:
            for iteration in range(start_iteration, config.iterations + 1):
                # Adversarial round 15, high finding: verify BEFORE collecting
                # this iteration's rollouts -- round 14's check ran only
                # inside `_save_train_state`, so with `train_state_every > 1`
                # (or 0, which never checks at all) a drifted binary could
                # collect, train, and publish several iterations' artifacts
                # before the next periodic save finally caught it.
                _verify_bridge_unchanged(bridge_env_config, pinned_bridge_path, pinned_bridge_sha256,
                                         allow_bridge_mismatch, bridge_drift_warned)
                iter_seed = base_seed + iteration * config.matches_per_iter
                if collector is not None:
                    state = cpu_state_snapshot(model)
                    batch = collector.collect(state, iter_seed, config.matches_per_iter)
                else:
                    batch = collect_b2b_rollouts(bridge_env_config, model, config, base_seed=iter_seed)
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
                # Adversarial round 2, Finding 1: record growth-block ReZero alpha
                # magnitudes so the runbook's null-interpretation rule ("alphas
                # hugging 0 = protocol null signal") has telemetry to check
                # against. Omitted (not 0.0) for growth-free runs -- see
                # `_growth_alpha_mean_abs`'s docstring.
                growth_alpha_mean_abs = _growth_alpha_mean_abs(model)
                if growth_alpha_mean_abs is not None:
                    metrics["growth_alpha_mean_abs"] = growth_alpha_mean_abs
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
                # Adversarial round 15, high finding: verify AGAIN here, after
                # the (potentially long-running) rollout collection + PPO
                # update but strictly BEFORE this iteration's `iter_N.pt`/
                # history row is written -- a binary that drifted DURING this
                # iteration's own collection/update must still block that
                # iteration's artifacts from being published, not just the
                # NEXT iteration's.
                _verify_bridge_unchanged(bridge_env_config, pinned_bridge_path, pinned_bridge_sha256,
                                         allow_bridge_mismatch, bridge_drift_warned)
                save_checkpoint(
                    checkpoint_dir / f"iter_{iteration:03d}.pt", model,
                    # Pins the trained horizon/architecture so fh-mj-evaluate can
                    # refuse to run this checkpoint under a different effective
                    # window (silent mis-evaluation guard). The "b2b" four-flag
                    # block stays for older readers; "model_config" is the
                    # complete ModelConfig so Spec B2c loaders (infer_model_config)
                    # can reconstruct the architecture exactly instead of
                    # re-deriving it from tensor shapes. "run_id" (adversarial
                    # round 4, high finding) lets a `--resume-from-state` whose
                    # history.json is missing/corrupt verify this checkpoint's
                    # lineage against the resuming state file instead of
                    # silently mixing unrelated runs' checkpoints together --
                    # infer_model_config ignores unknown metadata keys, so this
                    # is additive and doesn't affect loading.
                    metadata={
                        "b2b": {
                            "event_window": int(model_config.event_window),
                            "privileged_critic": bool(model_config.privileged_critic),
                            "aux_heads": bool(model_config.aux_heads),
                            "residual_blocks": int(model_config.residual_blocks),
                        },
                        "model_config": model_config_metadata(model_config),
                        "run_id": run_id,
                    })
                # Adversarial round 19, high finding: this iteration's FRESH
                # `iter_N.pt` just replaced whatever was quarantined at
                # `_quarantine_stale_future_checkpoints` time -- drop that
                # obsolete-trajectory `.stale` sibling now rather than
                # leaving it to the end-of-run sweep below, so a concurrent
                # directory listing never sees both the fresh checkpoint and
                # its quarantined predecessor at once for longer than
                # necessary.
                stale_sibling = checkpoint_dir / f"iter_{iteration:03d}.pt{_STALE_CHECKPOINT_SUFFIX}"
                if stale_sibling in pending_stale_checkpoints:
                    stale_sibling.unlink(missing_ok=True)
                    pending_stale_checkpoints.remove(stale_sibling)
                # Adversarial round 18, high finding: this iteration's
                # `iter_*.pt` checkpoint just landed durably on disk. When
                # train_state_every == 0 (train_state.pt is never written for
                # this whole run), THIS is the new run's first durable
                # artifact -- safe to drop the `--fresh-run-overwrite` backup
                # of the old run's artifacts now that the new run has its own
                # durable output.
                if overwrite_backup_dir is not None and not backup_cleared and durability_trigger == "checkpoint":
                    shutil.rmtree(overwrite_backup_dir, ignore_errors=True)
                    backup_cleared = True
                history.append(metrics)
                # Adversarial round 3, Finding 1: wrap history rows with the run's
                # run_id so a `--resume-from-state` can bind history.json's
                # lineage to the resuming train_state.pt (see _load_resume_history)
                # instead of silently mixing unrelated runs. Use
                # `read_b2b_history_rows` to read this file back.
                _write_history_atomic(checkpoint_dir / "history.json", {"run_id": run_id, "rows": history})
                print(f"iter {iteration}: policy_loss={metrics['policy_loss']:.4f} "
                      f"value_loss={metrics['value_loss']:.4f} entropy={metrics['entropy']:.4f} "
                      f"mean_reward={metrics['mean_reward']:.4f}")
                is_last_iteration = iteration == config.iterations
                if train_state_every > 0 and (iteration % train_state_every == 0 or is_last_iteration):
                    _save_train_state(
                        checkpoint_dir / "train_state.pt", model, optimizer,
                        next_iteration=iteration + 1, config=config, model_config=model_config,
                        env_config=env_config, base_seed=base_seed, run_id=run_id,
                        pinned_bridge_sha256=pinned_bridge_sha256,
                        pinned_bridge_path=pinned_bridge_path,
                    )
                    # Adversarial round 18, high finding: `train_state.pt` just
                    # landed durably -- this is the new run's first durable
                    # artifact when periodic state saves are enabled at all
                    # (see `durability_trigger`). Drop the `--fresh-run-
                    # overwrite` backup of the old run's artifacts now.
                    if overwrite_backup_dir is not None and not backup_cleared and durability_trigger == "state":
                        shutil.rmtree(overwrite_backup_dir, ignore_errors=True)
                        backup_cleared = True
        finally:
            if collector is not None:
                collector.close()
        # Adversarial round 19, high finding: sweep any `.stale` files still
        # left over at successful run completion -- e.g. this resume's
        # `--iterations` target stopped short of some iteration numbers that
        # were quarantined at resume-start (`config.iterations` lower than
        # the highest quarantined iteration), so the per-iteration deletion
        # above never reached them. They are obsolete-trajectory checkpoints
        # by definition (see `_quarantine_stale_future_checkpoints`) and this
        # run is ending without ever regenerating them, so there is nothing
        # left to wait for.
        for stale_path in pending_stale_checkpoints:
            stale_path.unlink(missing_ok=True)
        return history
    finally:
        lock_file.close()


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

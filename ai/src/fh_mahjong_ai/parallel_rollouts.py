from __future__ import annotations

import multiprocessing as mp
import queue
import traceback
from dataclasses import replace
from typing import Dict, List, Optional

from .config import EnvConfig, ModelConfig
from .ppo import PPOConfig, RolloutBatch, build_opponent_nets, collect_rollouts, concat_rollout_batches


def _split_counts(total: int, workers: int) -> List[int]:
    """Even split of `total` matches across `workers`, remainder on the first
    workers. The cumulative offsets give contiguous, disjoint seed blocks whose
    union equals the sequential run's seed range."""
    base, rem = divmod(int(total), int(workers))
    return [base + (1 if i < rem else 0) for i in range(workers)]


def _worker_loop(env_config, model_config, ppo_config, grp_state_dict, task_q, result_q):
    import torch

    from .model import PolicyValueNet

    torch.set_num_threads(1)
    learner = PolicyValueNet(env_config, model_config)
    grp_model = None
    if grp_state_dict is not None:
        from .global_ev import GlobalEVNet
        grp_model = GlobalEVNet(env_config, model_config)
        grp_model.load_state_dict(grp_state_dict)
        grp_model.eval()
        for p in grp_model.parameters():
            p.requires_grad_(False)

    while True:
        task = task_q.get()
        if task is None:
            return
        worker_id, learner_state_dict, pool_states, base_seed, matches = task
        try:
            learner.load_state_dict(learner_state_dict)
            opponents = build_opponent_nets(env_config, model_config, pool_states, device="cpu")
            cfg = replace(ppo_config, matches_per_iter=matches, device="cpu")
            batch = collect_rollouts(
                env_config, learner, opponents[0], cfg, base_seed=base_seed, opponents=opponents,
                grp_model=grp_model,
            )
            result_q.put((worker_id, batch, None))
            batch = None  # release our reference; the queue keeps the object alive until the feeder thread has serialized it, then all copies are freed
        except Exception:  # noqa: BLE001 - report any worker failure to the parent
            result_q.put((worker_id, None, traceback.format_exc()))


class ParallelRolloutCollector:
    """Persistent spawn-context worker pool that collects full self-play matches
    in parallel (CPU inference) and concatenates them into one RolloutBatch."""

    def __init__(self, env_config: EnvConfig, model_config: ModelConfig,
                 ppo_config: PPOConfig, num_workers: int,
                 grp_state_dict=None) -> None:
        if num_workers < 1:
            raise ValueError("num_workers must be >= 1")
        self.env_config = env_config
        self.model_config = model_config
        self.ppo_config = ppo_config
        self.num_workers = int(num_workers)
        self.grp_state_dict = grp_state_dict
        self._ctx = mp.get_context("spawn")
        self._task_q = None
        self._result_q = None
        self._procs: List[mp.process.BaseProcess] = []

    def start(self) -> None:
        self._task_q = self._ctx.Queue()
        self._result_q = self._ctx.Queue()
        self._procs = []
        for _ in range(self.num_workers):
            p = self._ctx.Process(
                target=_worker_loop,
                args=(self.env_config, self.model_config, self.ppo_config,
                      self.grp_state_dict, self._task_q, self._result_q),
                daemon=True,
            )
            p.start()
            self._procs.append(p)

    def collect(self, learner_state_dict, pool_states, base_seed: int, matches_per_iter: int) -> RolloutBatch:
        counts = _split_counts(matches_per_iter, self.num_workers)
        offset = 0
        dispatched = 0
        for worker_id, count in enumerate(counts):
            if count == 0:
                continue
            self._task_q.put((worker_id, learner_state_dict, pool_states, int(base_seed + offset), int(count)))
            offset += count
            dispatched += 1

        results: Dict[int, RolloutBatch] = {}
        received = 0
        while received < dispatched:
            try:
                worker_id, batch, err = self._result_q.get(timeout=30.0)
            except queue.Empty:
                if any(p.exitcode is not None for p in self._procs):
                    self.close()
                    raise RuntimeError("a rollout worker exited unexpectedly during collect")
                continue
            if err is not None:
                self.close()
                raise RuntimeError(f"rollout worker {worker_id} failed:\n{err}")
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

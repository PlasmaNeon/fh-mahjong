"""fh-mj-collect-bench: exact-semantics collector benchmark for B2b rollout
collection.

Before scaling `--num-workers` up for a real, multi-day `train_b2b` lap
(deep16-rezero: 260 iterations), this proves the collector infrastructure is
worker-count-INDEPENDENT: matches are seeded per-match
(`base_seed + match_index`), so the trajectories `collect_b2b_rollouts`
produces for a given match must not depend on how many workers the run fans
out across. A regression here (e.g. a worker accidentally sharing torch RNG
state, or a chunking change that reorders matches) would silently corrupt
every future worker-count choice's data without ever showing up in a normal
training run's loss curves.

This benchmark runs through the ACTUAL persistent, spawn-context
`ParallelB2bCollector` that multi-worker `train_b2b` uses. For each requested
worker count it constructs and starts a fresh collector, runs one warmup
collection round (startup timing), then reuses the same live workers for one
steady-state collection round (steady timing and digest). This exercises
spawn-time model construction, state-dict transfer, queues, seed-block
splitting, result ordering, worker reuse, and lifecycle cleanup while keeping
the model weights and match seeds fixed.

`--full-cycle` (data-scale-960 Stage 0 preflight) extends each worker-count
phase into a complete training iteration: after the steady collection round it
runs GAE + one real `ppo_update` on a fresh copy of the warm-started model
(fresh optimizer, fixed `--update-seed`, so the update is identical across
worker counts given a digest-equal batch), and measures what the spec's
go/no-go needs — host peak RSS across the whole collect+update phase, CUDA
peak allocation/reservation, transition rows, optimizer steps, collection
throughput, aux label coverage, truncation, KL, and clip fraction — plus an
explicit rows/labels worker-count-invariance check on top of the digest gate.
`ppo_update` moves the ENTIRE rollout onto the update device, so this is the
memory-honest preflight for raising matches_per_iter (collection-only numbers
under-measure both host RAM and CUDA peak). CUDA peaks are reported
separately for collection and for the update: the collection peak is
snapshotted before the update's `reset_peak_memory_stats()` erases it.

`--collector batched` benches the pool collector
(`batched_b2b.collect_b2b_rollouts_batched`) instead: one process, one
persistent `--pool-slots` env pool reused for the warmup and steady rounds,
one batched forward per round on `--device`. The invariance question is then
slot count rather than worker count, and `--pool-slots` replaces `--workers`.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Optional

import numpy as np
import torch

from ..batched_b2b import collect_b2b_rollouts_batched, make_b2b_pool
from ..config import EnvConfig
from ..fdlimit import raise_file_descriptor_limit
from ..train_b2b import ParallelB2bCollector, _b2b_model_env_config, build_b2b_model, grow_b2b_model
from ..ppo import PPOConfig, RolloutBatch, compute_gae, cpu_state_snapshot, ppo_update
from ..model_config_args import add_model_config_args, model_config_from_args
from ..placement_bonus_args import add_placement_bonus_args, placement_bonus_kwargs


def _build_model(env_config: EnvConfig, model_config, champion: Path, growth_blocks: int, device: str):
    """Warm-start the B2b model exactly as `train_b2b` does: `growth_blocks >
    0` routes through `grow_b2b_model` (champion must be a complete post-B2b
    anchor), otherwise through `build_b2b_model` (champion is the raw 39ch
    champion)."""
    if growth_blocks > 0:
        model = grow_b2b_model(champion, growth_blocks, device, env_config=env_config)
        return model, model.model_config
    model = build_b2b_model(_b2b_model_env_config(env_config), model_config, champion, device)
    return model, model_config


_ROLLOUT_DIGEST_ARRAY_FIELDS = (
    "planes",
    "scalars",
    "action_mask",
    "actions",
    "old_logprobs",
    "values",
    "rewards",
    "dones",
    "events",
    "event_lengths",
    "dealin_labels",
    "rank_labels",
)


def _update_length_prefixed(h, payload: bytes) -> None:
    h.update(len(payload).to_bytes(8, "big", signed=False))
    h.update(payload)


def _update_array_digest(h, name: str, value) -> None:
    if value is None:
        metadata = {"dtype": None, "field": name, "present": False, "shape": None}
        _update_length_prefixed(
            h, json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode())
        return
    array = np.asarray(value)
    metadata = {
        "dtype": array.dtype.str,
        "field": name,
        "present": True,
        "shape": list(array.shape),
    }
    _update_length_prefixed(
        h, json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode())
    _update_length_prefixed(h, np.ascontiguousarray(array).tobytes())


# The two fields a batched forward may round differently depending on which
# other rows share its batch. `_semantic_digest_batch` omits them so slot-count
# invariance is gated EXACTLY on everything a reordering or bookkeeping bug
# would touch; these two are measured and reported instead.
#
# Their spread is architecture-dependent, which is why it is reported and not
# gated here. Measured on CPU, chongci, the anchor075 net (96ch / 4 blocks /
# event GRU): 32 matches over 8-slot vs 32-slot pools (65077 rows) differ by
# up to 3.96e-5, with 754 of 130154 elements outside atol=1e-6/rtol=1e-5; on
# a 6-match probe `old_logprobs` was max 1.4e-5 (p50 0, p99 1.9e-6) and
# `values` max 1.4e-6. `--inference-mode per_row` is bit-identical across slot
# counts on the same net (max abs diff exactly 0), so this is batch-
# composition rounding, not orchestration. The tiny test net stays inside the
# tolerance, which is what the G0.1b pytest gate pins.
_ROLLOUT_TOLERANT_FIELDS = ("old_logprobs", "values")
_FLOAT_INVARIANCE_TOL = dict(atol=1e-6, rtol=1e-5)


def _digest_batch(base_seed: int, matches: int, batch, exclude: tuple[str, ...] = ()) -> str:
    """Hash every `RolloutBatch` field plus each array's shape and dtype.

    All twelve array fields are consumed by PPO/GAE/auxiliary training.
    `truncated_matches` is also included because `train_b2b` uses it for its
    fail-closed truncation-rate gate. No `RolloutBatch` field is excluded
    unless `exclude` names it (see `_semantic_digest_batch`).
    """
    expected_fields = set(_ROLLOUT_DIGEST_ARRAY_FIELDS) | {"truncated_matches", "match_telemetry"}
    actual_fields = {field.name for field in fields(RolloutBatch)}
    if actual_fields != expected_fields:
        raise RuntimeError(
            "collect-bench digest field list is stale: "
            f"expected {sorted(actual_fields)}, covers {sorted(expected_fields)}")
    header = {"base_seed": int(base_seed), "matches": int(matches)}
    # Only stamped when something IS excluded, so the full digest keeps the
    # byte stream its recorded golden values were taken over.
    if exclude:
        header["excluded"] = sorted(exclude)
    h = hashlib.sha256()
    _update_length_prefixed(
        h, json.dumps(header, sort_keys=True, separators=(",", ":")).encode())
    for name in _ROLLOUT_DIGEST_ARRAY_FIELDS:
        if name in exclude:
            continue
        _update_array_digest(h, name, getattr(batch, name))
    _update_length_prefixed(
        h, json.dumps(
            {"dtype": "int", "field": "truncated_matches", "shape": []},
            sort_keys=True, separators=(",", ":")).encode())
    h.update(int(batch.truncated_matches).to_bytes(8, "big", signed=True))
    tel = batch.match_telemetry
    payload = json.dumps({"field": "match_telemetry", "present": tel is not None,
                          "value": tel}, sort_keys=True, separators=(",", ":")).encode()
    _update_length_prefixed(h, payload)
    return h.hexdigest()


def _semantic_digest_batch(base_seed: int, matches: int, batch) -> str:
    """`_digest_batch` over everything except the two float fields a batched
    forward may round by batch composition. Equal semantic digests mean the
    two runs collected the same decisions, rewards, events, labels and
    telemetry, in the same order."""
    return _digest_batch(base_seed, matches, batch, exclude=_ROLLOUT_TOLERANT_FIELDS)


def _float_field_diff(reference: dict, current: dict) -> Optional[float]:
    """Max absolute difference across `_ROLLOUT_TOLERANT_FIELDS` between two
    runs, or None when their shapes disagree (a semantic difference, which
    the semantic digest reports on its own)."""
    worst = 0.0
    for name in _ROLLOUT_TOLERANT_FIELDS:
        a, b = reference[name], current[name]
        if a.shape != b.shape:
            return None
        if a.size:
            worst = max(worst, float(np.abs(a - b).max()))
    return worst


@dataclass
class FullCycleSettings:
    """PPO-update hyperparameters for `--full-cycle` mode. Defaults mirror
    `PPOConfig`'s; a real preflight passes the frozen recipe values explicitly
    (the runbook pins them) so the bench measures the exact update the lap
    will run."""
    minibatch_size: int = 256
    ppo_epochs: int = 4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    lr: float = 2e-5
    entropy_coef: float = 0.01
    device: str = "cpu"
    update_seed: int = 0
    # Amendment 5: synchronous per-minibatch host-to-device transfer instead
    # of one full-rollout transfer (PPOConfig.minibatch_device_transfer).
    minibatch_device_transfer: bool = False


def _linux_descendant_pids(root_pid: int) -> list[int]:
    """All live descendant pids of `root_pid` via /proc children files."""
    out: list[int] = []
    stack = [root_pid]
    while stack:
        pid = stack.pop()
        task_dir = f"/proc/{pid}/task"
        try:
            tids = os.listdir(task_dir)
        except OSError:
            continue
        for tid in tids:
            try:
                with open(f"{task_dir}/{tid}/children") as f:
                    children = [int(c) for c in f.read().split()]
            except (OSError, ValueError):
                continue
            out.extend(children)
            stack.extend(children)
    return out


def _linux_rss_bytes(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024  # kB -> bytes
    except (OSError, ValueError, IndexError):
        pass
    return 0


class _PeakRssSampler:
    """Tracks the peak TOTAL resident set size of this process plus all live
    descendants (the spawned collection workers) over a phase.

    On Linux a daemon thread samples /proc every `interval` seconds and keeps
    the max of the summed VmRSS — this is the number that has to fit in the
    box's RAM, which `getrusage` cannot provide (RUSAGE_CHILDREN's ru_maxrss
    is the max of any SINGLE reaped child, not the concurrent sum, and both
    counters are monotonic over the whole process lifetime, so per-phase
    attribution is impossible). On non-Linux platforms (no /proc) sampling is
    skipped and `stop()` falls back to those approximate lifetime-peak
    getrusage numbers, labeled as such in `method` — good enough for dev-box
    smoke runs; the real preflight box is Linux."""

    def __init__(self, interval: float = 0.1):
        self._interval = interval
        self._peak = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._proc_available = os.path.isdir(f"/proc/{os.getpid()}/task")

    def _sample_once(self) -> None:
        pid = os.getpid()
        total = _linux_rss_bytes(pid)
        for child in _linux_descendant_pids(pid):
            total += _linux_rss_bytes(child)
        if total > self._peak:
            self._peak = total

    def _run(self) -> None:
        while not self._stop.is_set():
            self._sample_once()
            self._stop.wait(self._interval)
        self._sample_once()

    def start(self) -> None:
        if self._proc_available:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self) -> tuple[int, str]:
        """Returns (peak_rss_bytes, method)."""
        if self._thread is not None:
            self._stop.set()
            self._thread.join()
            return self._peak, "proc-tree-sampled"
        import resource
        self_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        child_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        # macOS reports ru_maxrss in bytes, Linux in kilobytes; the Linux
        # branch here is unreachable (proc sampler wins there) but kept for
        # exotic /proc-less Linuxes.
        scale = 1 if sys.platform == "darwin" else 1024
        return (self_rss + child_rss) * scale, "getrusage-lifetime-approx"


def _cuda_peaks(active: bool) -> tuple[Optional[int], Optional[int]]:
    """(allocated, reserved) CUDA peak bytes since the last reset, or
    (None, None) when this phase did not run on CUDA."""
    if not active:
        return None, None
    torch.cuda.synchronize()
    return int(torch.cuda.max_memory_allocated()), int(torch.cuda.max_memory_reserved())


def _run_full_cycle_update(warm_started, batch, matches: int, steady_seconds: float,
                          settings: FullCycleSettings, match_mode: str,
                          max_steps_per_episode: Optional[int]) -> dict:
    """One real training update on `batch`, measured. Uses a fresh deep copy
    of the warm-started model and a fresh optimizer each call so every worker
    count's update starts from identical weights; with `update_seed` fixed and
    a digest-equal batch, the update telemetry must then be worker-count
    invariant (a second, independent invariance signal on top of the digest)."""
    fc: dict = {
        "transition_rows": int(len(batch)),
        "matches_per_second": float(matches) / steady_seconds if steady_seconds > 0 else 0.0,
        "truncated_matches": int(batch.truncated_matches),
        "truncation_rate": float(batch.truncated_matches) / max(1, matches),
        "dealin_positive_rate": (float(np.mean(batch.dealin_labels))
                                 if batch.dealin_labels is not None else None),
        "rank_label_coverage": (float(np.mean(batch.rank_labels >= 0))
                                if batch.rank_labels is not None else None),
    }
    update_config = PPOConfig(
        minibatch_size=settings.minibatch_size, ppo_epochs=settings.ppo_epochs,
        gamma=settings.gamma, gae_lambda=settings.gae_lambda, lr=settings.lr,
        entropy_coef=settings.entropy_coef, match_mode=match_mode,
        max_steps_per_episode=max_steps_per_episode, device=settings.device,
        minibatch_device_transfer=settings.minibatch_device_transfer,
    )
    use_cuda = settings.device.startswith("cuda") and torch.cuda.is_available()
    model = copy.deepcopy(warm_started).to(settings.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=settings.lr)
    if use_cuda:
        # The caller has already snapshotted the COLLECTION peak (see
        # `run_bench`); this reset scopes the numbers below to the update.
        torch.cuda.reset_peak_memory_stats()
    torch.manual_seed(settings.update_seed)
    update_start = time.perf_counter()
    advantages, returns = compute_gae(batch.rewards, batch.values, batch.dones,
                                      settings.gamma, settings.gae_lambda)
    metrics = ppo_update(model, optimizer, batch, advantages, returns, update_config)
    if use_cuda:
        torch.cuda.synchronize()
    fc["update_seconds"] = time.perf_counter() - update_start
    fc["cuda_peak_allocated_bytes"], fc["cuda_peak_reserved_bytes"] = _cuda_peaks(use_cuda)
    fc.update(metrics)
    return fc


_FULL_CYCLE_INVARIANT_KEYS = (
    "transition_rows", "truncated_matches",
    "dealin_positive_rate", "rank_label_coverage",
)


def run_bench(*, champion: Path, model_config, growth_blocks: int,
             workers: Optional[list[int]] = None,
             matches: int, base_seed: int, match_mode: str, bridge_kind: str,
             bridge_lib: Optional[str], device: str,
             max_steps_per_episode: Optional[int], event_window: int,
             worker_target=None, full_cycle: Optional[FullCycleSettings] = None,
             dispatch_chunk: int = 0, placement_bonus: Optional[dict] = None,
             collector: str = "process", pool_slots: Optional[list[int]] = None,
             inference_mode: str = "batched") -> dict:
    """Run the collector benchmark. Returns
    `{count: {"startup_seconds": float, "steady_seconds": float,
    "digest": str}, "all_digests_equal": bool}` where `count` is a worker
    count (`collector="process"`, from `workers`) or an env-pool slot count
    (`collector="batched"`, from `pool_slots`). With `full_cycle` set, each
    entry additionally carries a `"full_cycle"` dict (see
    `_run_full_cycle_update` plus `host_peak_rss_bytes`/`host_peak_rss_method`
    covering the whole collect+update phase, the collection-phase CUDA peaks,
    and `collector`/`pool_slots`/`effective_slots`) and the report carries
    `"rows_and_labels_equal"`: True iff transition rows, truncations, and aux
    label coverage are identical across all counts.

    `collector="batched"` builds ONE persistent pool per slot count and reuses
    it for the warmup and steady rounds (mirroring the process path's
    persistent workers), collecting through
    `batched_b2b.collect_b2b_rollouts_batched` on `device`. `inference_mode`
    is forwarded to it: `"batched"` is the production shape, `"per_row"` the
    batch-composition-independent one.

    `worker_target`, when given, is forwarded to every `ParallelB2bCollector`
    this bench constructs (adversarial round 9, medium finding). It exists
    only for test callers that need to inject a test-only worker function to
    exercise the real spawn-path can-fail property (e.g. proving a genuine
    perturbation in one worker's output still flips the digest) -- the CLI
    never sets it, and production benchmarking always uses the real
    `_b2b_worker_loop`."""
    if collector not in ("process", "batched"):
        raise ValueError(f"unknown collector: {collector!r}")
    counts = list(pool_slots or []) if collector == "batched" else list(workers or [])
    if not counts:
        raise ValueError("--pool-slots must name at least one slot count"
                         if collector == "batched"
                         else "--workers must name at least one worker count")
    env_config = EnvConfig(bridge_kind=bridge_kind, bridge_library_path=bridge_lib,
                           match_mode=match_mode, max_steps_per_episode=max_steps_per_episode,
                           oracle_observation=True, event_history_window=event_window)
    warm_started, effective_model_config = _build_model(env_config, model_config, champion, growth_blocks, device)
    # The persistent production collector constructs each worker model under
    # spawn and loads this detached CPU state snapshot for every collection
    # task, exactly as multi-worker `train_b2b` does.
    state_dict = cpu_state_snapshot(warm_started)
    ppo_config = PPOConfig(match_mode=match_mode, max_steps_per_episode=max_steps_per_episode,
                           device="cpu", collect_dispatch_chunk=int(dispatch_chunk),
                           **(placement_bonus or {}))
    # The batched collector runs in THIS process on `device` (the whole point
    # of the pool), unlike the spawn workers, which are hardcoded to CPU.
    batched_config = replace(ppo_config, device=device, matches_per_iter=int(matches),
                             collector="batched")
    collect_on_cuda = (collector == "batched" and device.startswith("cuda")
                       and torch.cuda.is_available())
    results: dict[int, dict] = {}
    reference_floats: Optional[dict] = None
    float_fields_within_tolerance = True
    float_allclose_violations = 0
    max_float_diff = 0.0
    for count in counts:
        sampler: Optional[_PeakRssSampler] = None
        if full_cycle is not None:
            sampler = _PeakRssSampler()
            sampler.start()
        startup_start = time.perf_counter()
        if collector == "batched":
            pool = make_b2b_pool(env_config, warm_started, batched_config, int(count))
            try:
                collect_b2b_rollouts_batched(env_config, warm_started, batched_config,
                                             base_seed=base_seed, pool=pool,
                                             inference_mode=inference_mode)
                startup_seconds = time.perf_counter() - startup_start
                if collect_on_cuda:
                    torch.cuda.reset_peak_memory_stats()
                steady_start = time.perf_counter()
                batch = collect_b2b_rollouts_batched(env_config, warm_started, batched_config,
                                                     base_seed=base_seed, pool=pool,
                                                     inference_mode=inference_mode)
                steady_seconds = time.perf_counter() - steady_start
            finally:
                pool.close()
        else:
            spawn_collector = ParallelB2bCollector(
                env_config, effective_model_config, ppo_config, count,
                worker_target=worker_target)
            try:
                spawn_collector.start()
                spawn_collector.collect(state_dict, base_seed, matches)
                startup_seconds = time.perf_counter() - startup_start

                steady_start = time.perf_counter()
                batch = spawn_collector.collect(state_dict, base_seed, matches)
                steady_seconds = time.perf_counter() - steady_start
            finally:
                spawn_collector.close()
        # Snapshotted HERE, before `_run_full_cycle_update`'s
        # `reset_peak_memory_stats()` erases the collection phase's peak.
        collect_alloc, collect_reserved = _cuda_peaks(collect_on_cuda)
        results[count] = {
            "startup_seconds": startup_seconds,
            "steady_seconds": steady_seconds,
            "digest": _digest_batch(base_seed, matches, batch),
            "semantic_digest": _semantic_digest_batch(base_seed, matches, batch),
        }
        # Only the two 1-D float fields are retained across counts (a few MB
        # at any realistic match count) — never whole batches.
        floats = {name: np.asarray(getattr(batch, name), dtype=np.float64).copy()
                  for name in _ROLLOUT_TOLERANT_FIELDS}
        if reference_floats is None:
            reference_floats = floats
        else:
            diff = _float_field_diff(reference_floats, floats)
            if diff is None:
                float_fields_within_tolerance = False
            else:
                max_float_diff = max(max_float_diff, diff)
                for name in _ROLLOUT_TOLERANT_FIELDS:
                    a, b = reference_floats[name], floats[name]
                    outside = np.abs(a - b) > (_FLOAT_INVARIANCE_TOL["atol"]
                                               + _FLOAT_INVARIANCE_TOL["rtol"] * np.abs(b))
                    if outside.any():
                        float_fields_within_tolerance = False
                        float_allclose_violations += int(outside.sum())
        if full_cycle is not None:
            fc = _run_full_cycle_update(
                warm_started, batch, matches, steady_seconds, full_cycle,
                match_mode, max_steps_per_episode)
            assert sampler is not None
            peak, method = sampler.stop()
            fc["host_peak_rss_bytes"] = peak
            fc["host_peak_rss_method"] = method
            fc["cuda_peak_collect_allocated_bytes"] = collect_alloc
            fc["cuda_peak_collect_reserved_bytes"] = collect_reserved
            fc["collector"] = collector
            fc["pool_slots"] = int(count) if collector == "batched" else None
            # Slots beyond the match count never receive a command, so this is
            # the number the throughput and memory figures actually describe.
            fc["effective_slots"] = (min(int(count), int(matches))
                                     if collector == "batched" else None)
            results[count]["full_cycle"] = fc
    digests = {r["digest"] for r in results.values()}
    semantic_digests = {r["semantic_digest"] for r in results.values()}
    report = {"results": results, "all_digests_equal": len(digests) <= 1,
             "semantic_digests_equal": len(semantic_digests) <= 1,
             # Reported, never gated: see `_ROLLOUT_TOLERANT_FIELDS`. The
             # exactness claim this bench enforces is the semantic digest.
             "float_fields_within_tolerance": float_fields_within_tolerance,
             "float_allclose_violations": float_allclose_violations,
             "semantics_equal": len(semantic_digests) <= 1,
             "max_float_diff": max_float_diff,
             # A batched forward's float output depends on which rows share
             # its batch, so byte-equality across slot counts is expected only
             # in per_row mode (and for the CPU spawn workers, which are
             # always per-row). Everything else stays exactly equal.
             "exact_invariance_expected": not (collector == "batched"
                                               and inference_mode == "batched"),
             "model_config": effective_model_config,
             "collector": collector,
             "inference_mode": inference_mode if collector == "batched" else None,
             "dispatch_chunk_matches": int(dispatch_chunk)}
    if full_cycle is not None:
        invariant_tuples = {
            tuple(r["full_cycle"][k] for k in _FULL_CYCLE_INVARIANT_KEYS)
            for r in results.values()
        }
        report["rows_and_labels_equal"] = len(invariant_tuples) <= 1
    return report


def _print_table(results: dict[int, dict], label: str = "workers") -> None:
    print(f"{label:>10}  {'startup_s':>10}  {'steady_s':>10}  digest")
    for w in sorted(results):
        r = results[w]
        print(
            f"{w:>10}  {r['startup_seconds']:>10.3f}  "
            f"{r['steady_seconds']:>10.3f}  {r['digest']}")


def _fmt_gib(value) -> str:
    return "-" if value is None else f"{value / (1024 ** 3):.2f}"


def _print_full_cycle_table(results: dict[int, dict], label: str = "workers") -> None:
    print()
    print(f"{label:>10}  {'eff_slots':>9}  {'rows':>8}  {'optimizer_steps':>15}  "
          f"{'matches/s':>9}  {'update_s':>8}  {'approx_kl':>9}  {'clip_frac':>9}  "
          f"{'dealin+':>7}  {'rank_cov':>8}  {'trunc':>5}  "
          f"{'rss_gib':>8}  {'cuda_col_gib':>12}  {'cuda_alloc_gib':>14}  {'cuda_resv_gib':>13}")
    for w in sorted(results):
        fc = results[w]["full_cycle"]

        def _opt(value, spec):
            return "-" if value is None else format(value, spec)

        print(
            f"{w:>10}  {_opt(fc.get('effective_slots'), '>9d')}  "
            f"{fc['transition_rows']:>8}  {fc['optimizer_steps']:>15}  "
            f"{fc['matches_per_second']:>9.3f}  {fc['update_seconds']:>8.3f}  "
            f"{fc['approx_kl']:>9.5f}  {fc['clip_fraction']:>9.5f}  "
            f"{_opt(fc['dealin_positive_rate'], '>7.4f')}  "
            f"{_opt(fc['rank_label_coverage'], '>8.4f')}  "
            f"{fc['truncated_matches']:>5}  "
            f"{_fmt_gib(fc['host_peak_rss_bytes']):>8}  "
            f"{_fmt_gib(fc.get('cuda_peak_collect_allocated_bytes')):>12}  "
            f"{_fmt_gib(fc['cuda_peak_allocated_bytes']):>14}  "
            f"{_fmt_gib(fc['cuda_peak_reserved_bytes']):>13}")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Exact-semantics collector benchmark for B2b rollout collection "
                    "(gates --num-workers / --pool-slots choices for a train_b2b lap)")
    p.add_argument("--champion", type=Path, required=True,
                   help="checkpoint to warm-start from; a raw 39ch champion unless "
                        "--model-growth-blocks > 0, in which case a complete post-B2b anchor")
    p.add_argument("--model-growth-blocks", type=int, default=0,
                   help="deep16-rezero capacity growth: stack this many ReZero residual "
                        "blocks onto --champion; 0 = disabled (default), champion is warm-"
                        "started via the 39ch->B2b surgery path instead")
    p.add_argument("--workers", type=str, default=None,
                   help="comma-separated worker counts to benchmark, e.g. 5,10,20 "
                        "(--collector process; required there)")
    p.add_argument("--collector", choices=("process", "batched"), default="process",
                   help="which collector to bench: 'process' (default) fans matches out "
                        "across spawn workers (--workers); 'batched' drives one env pool "
                        "in this process with a batched forward per round (--pool-slots)")
    p.add_argument("--pool-slots", type=str, default=None,
                   help="comma-separated env-pool slot counts to benchmark with "
                        "--collector batched, e.g. 128,256,320. A slot count above "
                        "--matches is meaningless: only min(slots, matches) slots ever "
                        "activate (reported as effective_slots)")
    p.add_argument("--inference-mode", choices=("batched", "per_row"), default="batched",
                   help="--collector batched only: 'batched' (default) is the production "
                        "one-forward-per-round shape; 'per_row' forwards each row alone, "
                        "which is batch-composition-independent but far slower")
    p.add_argument("--matches", type=int, default=320)
    p.add_argument("--base-seed", type=int, default=0)
    p.add_argument("--match-mode", choices=("classic", "chongci"), default="chongci")
    p.add_argument("--max-steps-per-episode", type=int, default=4000)
    p.add_argument("--bridge-kind", choices=("go", "mock"), default="go")
    p.add_argument("--bridge-lib", type=str, default=None)
    p.add_argument("--device", type=str, default="cpu",
                   help="device to warm-start the model on. With --collector process it is "
                        "only the warm-start device: collection is CPU-bound there (the "
                        "spawn workers hardcode CPU), and that path does NOT cover "
                        "train_b2b's num_workers<=1 direct path, which collects at its "
                        "config's device. With --collector batched this IS the collection "
                        "device — every round's batched forward runs on it")
    p.add_argument("--event-window", type=int, default=128)
    p.add_argument("--dispatch-chunk", type=int, default=0,
                   help="max matches per sequential dispatch round in the collector "
                        "(PPOConfig.collect_dispatch_chunk); bounds per-worker resident "
                        "trajectory memory at ~chunk/workers matches; 0 = single dispatch "
                        "(legacy). data-scale-960 Amendment 2 freezes 320 for that lap")
    p.add_argument("--full-cycle", action="store_true",
                   help="after each worker count's steady collection, run GAE + one real "
                        "ppo_update on a fresh model copy and measure the FULL iteration: "
                        "host peak RSS, CUDA peak allocation, transition rows, optimizer "
                        "steps, throughput, label coverage, truncation, KL, clip fraction "
                        "(data-scale-960 Stage 0 preflight)")
    fc_defaults = FullCycleSettings()
    p.add_argument("--minibatch-size", type=int, default=fc_defaults.minibatch_size,
                   help="PPO minibatch size for the --full-cycle update")
    p.add_argument("--ppo-epochs", type=int, default=fc_defaults.ppo_epochs,
                   help="PPO epochs for the --full-cycle update")
    p.add_argument("--gamma", type=float, default=fc_defaults.gamma,
                   help="discount for the --full-cycle GAE + update")
    p.add_argument("--gae-lambda", type=float, default=fc_defaults.gae_lambda,
                   help="GAE lambda for the --full-cycle update")
    p.add_argument("--lr", type=float, default=fc_defaults.lr,
                   help="learning rate for the --full-cycle update's fresh optimizer")
    p.add_argument("--entropy-coef", type=float, default=fc_defaults.entropy_coef,
                   help="entropy coefficient for the --full-cycle update")
    p.add_argument("--ppo-device", type=str, default=fc_defaults.device,
                   help="device the --full-cycle update runs on (the real lap uses cuda; "
                        "ppo_update moves the whole rollout there, so this is where the "
                        "CUDA peak-memory question is answered)")
    p.add_argument("--update-seed", type=int, default=fc_defaults.update_seed,
                   help="torch seed set before every --full-cycle update so the minibatch "
                        "permutation — and hence the whole update — is identical across "
                        "worker counts")
    p.add_argument("--minibatch-device-transfer", action="store_true",
                   help="run the --full-cycle update with the rollout kept in host "
                        "memory and each minibatch synchronously moved to --ppo-device "
                        "(data-scale-960 Amendment 5; bit-identical update, parity-"
                        "gauntleted; required at 960 on a 24GB card)")
    p.add_argument("--json", type=Path, default=None, help="write the full report as JSON")
    add_model_config_args(p)
    add_placement_bonus_args(p)
    args = p.parse_args()

    # Multi-worker collection moves many shared tensors through spawn queues;
    # torch's default file_descriptor sharing strategy costs one fd per shared
    # tensor and exhausts WSL's default 1024 soft limit (errno 24). Raise the
    # limit and switch this process to the file_system strategy, which shares
    # via named files instead of held-open descriptors.
    raise_file_descriptor_limit()
    torch.multiprocessing.set_sharing_strategy("file_system")

    def _counts(raw):
        return [int(v.strip()) for v in raw.split(",") if v.strip()] if raw else []

    workers = _counts(args.workers)
    pool_slots = _counts(args.pool_slots)
    if args.collector == "batched":
        if not pool_slots:
            p.error("--collector batched requires --pool-slots (e.g. --pool-slots 128,256)")
        if any(s < 1 for s in pool_slots):
            p.error("--pool-slots values must be >= 1")
        if workers:
            p.error("--workers has no meaning with --collector batched; use --pool-slots")
    else:
        if not workers:
            p.error("--workers must name at least one worker count")
        if pool_slots:
            p.error("--pool-slots requires --collector batched")

    # Adversarial round 6, high finding (train_b2b.py): --event-window (this
    # script's own flag) is NOT --model-event-window (model_config_args's
    # flag, default 0) -- threading the effective window straight into
    # model_config_from_args means no intermediate ModelConfig with
    # event_window=0 is ever built while --model-event-output-dim may already
    # be nonzero on the CLI (see model_config_from_args's docstring).
    model_config = model_config_from_args(args, event_window=args.event_window)

    full_cycle = None
    if args.full_cycle:
        full_cycle = FullCycleSettings(
            minibatch_size=args.minibatch_size, ppo_epochs=args.ppo_epochs,
            gamma=args.gamma, gae_lambda=args.gae_lambda, lr=args.lr,
            entropy_coef=args.entropy_coef, device=args.ppo_device,
            update_seed=args.update_seed,
            minibatch_device_transfer=args.minibatch_device_transfer)

    report = run_bench(champion=args.champion, model_config=model_config,
                       growth_blocks=args.model_growth_blocks, workers=workers,
                       matches=args.matches, base_seed=args.base_seed,
                       match_mode=args.match_mode, bridge_kind=args.bridge_kind,
                       bridge_lib=args.bridge_lib, device=args.device,
                       max_steps_per_episode=args.max_steps_per_episode,
                       event_window=args.event_window, full_cycle=full_cycle,
                       dispatch_chunk=args.dispatch_chunk,
                       placement_bonus=placement_bonus_kwargs(args),
                       collector=args.collector, pool_slots=pool_slots,
                       inference_mode=args.inference_mode)
    results = report["results"]
    label = "pool_slots" if args.collector == "batched" else "workers"
    _print_table(results, label)
    if full_cycle is not None:
        _print_full_cycle_table(results, label)
    def _print_groups(key: str) -> None:
        groups: dict[str, list[int]] = {}
        for w, r in results.items():
            groups.setdefault(r[key], []).append(w)
        print(f"differing {label} (grouped by matching {key}):")
        for digest, ws in groups.items():
            print(f"  {digest}: {label}={sorted(ws)}")

    exact_expected = report["exact_invariance_expected"]
    print(f"all_digests_equal: {report['all_digests_equal']}")
    if not report["all_digests_equal"] and exact_expected:
        _print_groups("digest")
    if not exact_expected:
        # Production batched inference: floats move with batch composition by
        # design and by an architecture-dependent amount, so the GATE is the
        # semantic digest (every discrete field, reward, label and telemetry
        # row) and the float spread below is measurement, not a pass/fail.
        print(f"semantic_digests_equal: {report['semantic_digests_equal']}")
        print(f"float_delta (reported, not gated): max_abs_diff="
              f"{report['max_float_diff']:.3e}, elements outside "
              f"atol={_FLOAT_INVARIANCE_TOL['atol']}/rtol={_FLOAT_INVARIANCE_TOL['rtol']}: "
              f"{report['float_allclose_violations']}")
        print(f"semantics_equal: {report['semantics_equal']}")
        if not report["semantic_digests_equal"]:
            _print_groups("semantic_digest")
    ok = report["all_digests_equal"] if exact_expected else report["semantics_equal"]
    if full_cycle is not None:
        print(f"rows_and_labels_equal: {report['rows_and_labels_equal']}")
        ok = ok and report["rows_and_labels_equal"]

    if args.json is not None:
        payload = {
            str(w): {
                "startup_seconds": r["startup_seconds"],
                "steady_seconds": r["steady_seconds"],
                "digest": r["digest"],
                "semantic_digest": r["semantic_digest"],
                **({"full_cycle": r["full_cycle"]} if "full_cycle" in r else {}),
            }
            for w, r in results.items()
        }
        payload["all_digests_equal"] = report["all_digests_equal"]
        payload["semantic_digests_equal"] = report["semantic_digests_equal"]
        payload["float_fields_within_tolerance"] = report["float_fields_within_tolerance"]
        payload["float_allclose_violations"] = report["float_allclose_violations"]
        payload["semantics_equal"] = report["semantics_equal"]
        payload["max_float_diff"] = report["max_float_diff"]
        payload["exact_invariance_expected"] = report["exact_invariance_expected"]
        payload["collector"] = args.collector
        payload["inference_mode"] = report["inference_mode"]
        payload["dispatch_chunk_matches"] = report["dispatch_chunk_matches"]
        if full_cycle is not None:
            payload["rows_and_labels_equal"] = report["rows_and_labels_equal"]
        args.json.write_text(json.dumps(payload, indent=2))

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

"""fh-mj-collect-bench: exact-semantics worker-count benchmark for B2b rollout
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

This benchmark reuses the ACTUAL collection function `train_b2b` calls
(`collect_b2b_rollouts`, see `oracle.py`) and the ACTUAL match-chunking
algorithm `ParallelB2bCollector` uses (`_split_counts`, see
`parallel_rollouts.py`) — it does not reimplement rollout collection. For
each requested worker count it runs COLLECTION ONLY (fixed weights, no PPO
update): matches are split into contiguous, disjoint seed blocks (one block
per worker, exactly as `ParallelB2bCollector.collect` does), each block is
collected via `collect_b2b_rollouts`, and the per-block results are
concatenated in ascending worker-id order — which, because blocks are
contiguous and increasing, IS a concatenation in ascending match-index order
regardless of how many workers were used. That per-worker-count concatenated
batch is hashed into one digest; if every worker count in `--workers`
produces the same digest, the harness proves fan-out doesn't change results.

Worker fan-out here uses `multiprocessing`'s **fork** start method, not the
spawn context `ParallelB2bCollector` uses for real training. The reason is
purely about state inheritance, not RNG safety (each forked/spawned worker
already gets its own independent process and thus its own independent torch
RNG either way): `spawn` starts a fresh interpreter that re-imports every
module from scratch, which drops any test monkeypatch state applied in the
parent — a test that patches `collect_b2b_rollouts` to inject a failure
would silently have no effect on spawned children. `fork` instead inherits
the parent's already-imported (possibly monkeypatched) module state via
copy-on-write memory, so this bench's own tests can patch collection
behavior and see it take effect in the worker. It is also simply simpler:
no state_dict re-serialization is needed to hand the warm-started model to
each worker. Fork-after-threads is generally unsafe with PyTorch's internal
thread pool, so the parent stays single-threaded (`torch.set_num_threads(1)`)
and never runs a forward pass before forking (model warm-start here only
copies tensors, no `model(...)` call) — the same reason each worker also
pins its own thread count to 1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import queue
import sys
import time
import traceback
from dataclasses import replace
from pathlib import Path
from typing import Optional

import numpy as np
import torch

from ..config import EnvConfig
from ..model import PolicyValueNet
from ..oracle import _b2b_model_env_config, build_b2b_model, collect_b2b_rollouts, grow_b2b_model
from ..parallel_rollouts import _split_counts
from ..ppo import PPOConfig, concat_rollout_batches, cpu_state_snapshot
from .model_config_args import add_model_config_args, model_config_from_args

# Per-worker timeout (seconds) for collecting a forked worker's result.
# This is generous relative to a real collection chunk's runtime; it exists
# only to fail loudly on the documented fork failure mode (e.g. a forked
# child deadlocking or dying without reaching the except-block that reports
# errors on `result_q`) instead of hanging the bench forever.
_WORKER_RESULT_TIMEOUT_SECONDS = 600


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


def _collect_chunk(env_config: EnvConfig, model, ppo_config: PPOConfig, seed: int, count: int):
    """One contiguous seed-block's worth of collection, via the real
    collector function. `matches_per_iter`/`device` are pinned to this
    chunk's `count`/CPU — mirrors `_b2b_worker_loop`'s per-task config."""
    torch.set_num_threads(1)
    cfg = replace(ppo_config, matches_per_iter=count, device="cpu")
    return collect_b2b_rollouts(env_config, model, cfg, base_seed=seed)


def _fork_collect_chunk(result_q, worker_id: int, env_config: EnvConfig, model,
                        ppo_config: PPOConfig, seed: int, count: int) -> None:
    """`multiprocessing.Process` target for one seed block. Runs in its own
    forked process (its own independent torch RNG), reusing the same
    already-loaded `model` object via fork's copy-on-write memory — no
    state_dict re-serialization needed."""
    try:
        batch = _collect_chunk(env_config, model, ppo_config, seed, count)
        result_q.put((worker_id, batch, None))
    except Exception:  # noqa: BLE001 - report any worker failure to the parent
        result_q.put((worker_id, None, traceback.format_exc()))


def run_collection(env_config: EnvConfig, model, ppo_config: PPOConfig,
                   base_seed: int, matches: int, num_workers: int):
    """Collect `matches` matches (seeds `base_seed`..`base_seed+matches-1`)
    fanned across `num_workers` contiguous seed blocks (`_split_counts` — the
    SAME chunking `ParallelB2bCollector` uses), concatenated back in
    ascending worker-id order — which, because the blocks are contiguous and
    increasing, is a concatenation in ascending match-index order regardless
    of `num_workers`. Returns `(RolloutBatch, elapsed_seconds)`."""
    counts = _split_counts(matches, max(1, int(num_workers)))
    blocks = []
    offset = 0
    for count in counts:
        if count > 0:
            blocks.append((int(base_seed) + offset, count))
        offset += count
    if not blocks:
        raise ValueError("run_collection: no matches to collect")
    start = time.perf_counter()
    if len(blocks) == 1:
        seed, count = blocks[0]
        batches = [_collect_chunk(env_config, model, ppo_config, seed, count)]
    else:
        ctx = mp.get_context("fork")
        result_q = ctx.Queue()
        procs = []
        for worker_id, (seed, count) in enumerate(blocks):
            proc = ctx.Process(target=_fork_collect_chunk,
                               args=(result_q, worker_id, env_config, model, ppo_config, seed, count),
                               daemon=True)
            proc.start()
            procs.append(proc)
        results: dict[int, object] = {}
        pending = {worker_id for worker_id in range(len(blocks))}
        for _ in procs:
            try:
                worker_id, batch, err = result_q.get(timeout=_WORKER_RESULT_TIMEOUT_SECONDS)
            except queue.Empty:
                for p in procs:
                    p.terminate()
                raise RuntimeError(
                    f"collect-bench: timed out after {_WORKER_RESULT_TIMEOUT_SECONDS}s waiting "
                    f"for worker result(s); worker(s) still pending: {sorted(pending)} "
                    f"(this is the documented fork failure mode — a forked child hung or died "
                    f"without reporting to result_q)"
                )
            if err is not None:
                for p in procs:
                    p.terminate()
                raise RuntimeError(f"collect-bench worker {worker_id} failed:\n{err}")
            results[worker_id] = batch
            pending.discard(worker_id)
        for p in procs:
            p.join(timeout=30)
        batches = [results[i] for i in range(len(blocks))]
    elapsed = time.perf_counter() - start
    batch = concat_rollout_batches(batches, consume=True)
    return batch, elapsed


def _digest_batch(base_seed: int, matches: int, batch) -> str:
    """sha256 over the canonical concatenation of (match seed context,
    obs-row bytes for ALL FOUR per-row observation arrays — planes, scalars,
    action_mask, events/event_lengths — action ids, rewards, dealin labels,
    rank labels, round-outcome telemetry). Row order in `batch` is already
    canonical by match index (see `run_collection`'s docstring), so no
    further per-match sorting is needed — hashing the whole concatenation in
    place respects match-index order for any worker count.

    action_mask, events, and event_lengths are included alongside planes/
    scalars: a fan-out bug isolated to mask or event handling (e.g. a worker
    reusing another worker's event-window buffer, or a stale mask left over
    from a previous match) would leave planes/scalars/actions/rewards
    untouched and pass silently if those two arrays were the only ones
    hashed.
    """
    h = hashlib.sha256()
    h.update(int(base_seed).to_bytes(8, "big", signed=True))
    h.update(int(matches).to_bytes(8, "big", signed=True))
    h.update(np.ascontiguousarray(batch.planes, dtype=np.float32).tobytes())
    h.update(np.ascontiguousarray(batch.scalars, dtype=np.float32).tobytes())
    h.update(np.ascontiguousarray(batch.action_mask, dtype=np.bool_).tobytes())
    h.update(np.ascontiguousarray(batch.actions, dtype=np.int64).tobytes())
    h.update(np.ascontiguousarray(batch.rewards, dtype=np.float32).tobytes())
    events = batch.events if batch.events is not None else np.zeros(0, dtype=np.uint32)
    event_lengths = batch.event_lengths if batch.event_lengths is not None else np.zeros(0, dtype=np.int32)
    h.update(np.ascontiguousarray(events, dtype=np.uint32).tobytes())
    h.update(np.ascontiguousarray(event_lengths, dtype=np.int32).tobytes())
    dealin = batch.dealin_labels if batch.dealin_labels is not None else np.zeros(0, dtype=np.float32)
    rank = batch.rank_labels if batch.rank_labels is not None else np.zeros(0, dtype=np.int64)
    h.update(np.ascontiguousarray(dealin, dtype=np.float32).tobytes())
    h.update(np.ascontiguousarray(rank, dtype=np.int64).tobytes())
    # Round-outcome telemetry: how many of this worker-count's matches hit
    # the step limit instead of reaching a terminal state (a fan-out bug
    # that changed which matches truncate would otherwise be invisible to
    # the arrays above, since a truncated match still emits rows).
    h.update(int(batch.truncated_matches).to_bytes(8, "big", signed=True))
    return h.hexdigest()


def run_bench(*, champion: Path, model_config, growth_blocks: int, workers: list[int],
             matches: int, base_seed: int, match_mode: str, bridge_kind: str,
             bridge_lib: Optional[str], device: str,
             max_steps_per_episode: Optional[int], event_window: int) -> dict:
    """Run the full worker-count benchmark. Returns
    `{worker_count: {"seconds": float, "digest": str}, "all_digests_equal": bool}`."""
    env_config = EnvConfig(bridge_kind=bridge_kind, bridge_library_path=bridge_lib,
                           match_mode=match_mode, max_steps_per_episode=max_steps_per_episode,
                           oracle_observation=True, event_history_window=event_window)
    warm_started, effective_model_config = _build_model(env_config, model_config, champion, growth_blocks, device)
    # Rollout collection here is always CPU-bound (mirrors `_b2b_worker_loop`,
    # which hardcodes `device="cpu"` for every chunk it collects) regardless
    # of `--device` — a fresh CPU copy of the warm-started weights, loaded via
    # a snapshot rather than reusing `warm_started` directly, keeps the
    # collection model off any CUDA device the champion may have been
    # warm-started on. This ALSO matters for fork safety below: forking
    # after a CUDA context has been initialized in the parent is broken, so
    # the parent must never run a forward pass (or otherwise touch CUDA)
    # before the worker fork.
    #
    # IMPORTANT SCOPE NOTE: this bench therefore matches ONLY the MULTI-
    # WORKER production path (`ParallelB2bCollector` / `_b2b_worker_loop`,
    # which hardcodes CPU for every worker). `train_b2b`'s num_workers<=1
    # path calls `collect_b2b_rollouts` directly with the *unmodified*
    # `PPOConfig` and therefore collects at `config.device` — e.g. on GPU,
    # if the run was launched with `--device cuda`. This bench does not
    # cover that single-worker GPU path at all; it only answers "does
    # fan-out across N CPU workers change results", which is the actual
    # decision this bench exists to gate (choosing --num-workers for a
    # multi-worker lap). A single-worker cuda run is out of scope here and
    # that is acceptable.
    model = PolicyValueNet(_b2b_model_env_config(env_config), effective_model_config)
    model.load_state_dict(cpu_state_snapshot(warm_started))
    model.eval()
    torch.set_num_threads(1)
    ppo_config = PPOConfig(match_mode=match_mode, max_steps_per_episode=max_steps_per_episode,
                           device="cpu")
    results: dict[int, dict] = {}
    for w in workers:
        batch, elapsed = run_collection(env_config, model, ppo_config, base_seed, matches, w)
        results[w] = {"seconds": elapsed, "digest": _digest_batch(base_seed, matches, batch)}
    digests = {r["digest"] for r in results.values()}
    return {"results": results, "all_digests_equal": len(digests) <= 1,
           "model_config": effective_model_config}


def _print_table(results: dict[int, dict]) -> None:
    print(f"{'workers':>8}  {'seconds':>10}  digest")
    for w in sorted(results):
        r = results[w]
        print(f"{w:>8}  {r['seconds']:>10.3f}  {r['digest']}")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Exact-semantics worker-count benchmark for B2b rollout collection "
                    "(gates --num-workers choices for a train_b2b lap)")
    p.add_argument("--champion", type=Path, required=True,
                   help="checkpoint to warm-start from; a raw 39ch champion unless "
                        "--model-growth-blocks > 0, in which case a complete post-B2b anchor")
    p.add_argument("--model-growth-blocks", type=int, default=0,
                   help="deep16-rezero capacity growth: stack this many ReZero residual "
                        "blocks onto --champion; 0 = disabled (default), champion is warm-"
                        "started via the 39ch->B2b surgery path instead")
    p.add_argument("--workers", type=str, required=True,
                   help="comma-separated worker counts to benchmark, e.g. 5,10,20")
    p.add_argument("--matches", type=int, default=320)
    p.add_argument("--base-seed", type=int, default=0)
    p.add_argument("--match-mode", choices=("classic", "chongci"), default="chongci")
    p.add_argument("--max-steps-per-episode", type=int, default=4000)
    p.add_argument("--bridge-kind", choices=("go", "mock"), default="go")
    p.add_argument("--bridge-lib", type=str, default=None)
    p.add_argument("--device", type=str, default="cpu",
                   help="device to warm-start the model on before snapshotting to CPU for "
                        "collection; collection itself is always CPU-bound (this bench only "
                        "covers the multi-worker production path, which hardcodes CPU per "
                        "worker — it does NOT cover train_b2b's num_workers<=1 direct path, "
                        "which collects at this config's device, e.g. GPU)")
    p.add_argument("--event-window", type=int, default=128)
    p.add_argument("--json", type=Path, default=None, help="write the full report as JSON")
    add_model_config_args(p)
    args = p.parse_args()

    workers = [int(w.strip()) for w in args.workers.split(",") if w.strip()]
    if not workers:
        p.error("--workers must name at least one worker count")

    base_model_config = model_config_from_args(args)
    model_config = replace(base_model_config, event_window=args.event_window)

    report = run_bench(champion=args.champion, model_config=model_config,
                       growth_blocks=args.model_growth_blocks, workers=workers,
                       matches=args.matches, base_seed=args.base_seed,
                       match_mode=args.match_mode, bridge_kind=args.bridge_kind,
                       bridge_lib=args.bridge_lib, device=args.device,
                       max_steps_per_episode=args.max_steps_per_episode,
                       event_window=args.event_window)
    results = report["results"]
    _print_table(results)
    if report["all_digests_equal"]:
        print("all_digests_equal: True")
    else:
        digest_groups: dict[str, list[int]] = {}
        for w, r in results.items():
            digest_groups.setdefault(r["digest"], []).append(w)
        print("all_digests_equal: False")
        print("differing worker counts (grouped by matching digest):")
        for digest, ws in digest_groups.items():
            print(f"  {digest}: workers={sorted(ws)}")

    if args.json is not None:
        payload = {str(w): {"seconds": r["seconds"], "digest": r["digest"]}
                  for w, r in results.items()}
        payload["all_digests_equal"] = report["all_digests_equal"]
        args.json.write_text(json.dumps(payload, indent=2))

    sys.exit(0 if report["all_digests_equal"] else 1)


if __name__ == "__main__":
    main()

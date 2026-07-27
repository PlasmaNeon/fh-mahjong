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

This benchmark runs through the ACTUAL persistent, spawn-context
`ParallelB2bCollector` that multi-worker `train_b2b` uses. For each requested
worker count it constructs and starts a fresh collector, runs one warmup
collection round (startup timing), then reuses the same live workers for one
steady-state collection round (steady timing and digest). This exercises
spawn-time model construction, state-dict transfer, queues, seed-block
splitting, result ordering, worker reuse, and lifecycle cleanup while keeping
the model weights and match seeds fixed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import fields, replace
from pathlib import Path
from typing import Optional

import numpy as np

from ..config import EnvConfig
from ..oracle import ParallelB2bCollector, _b2b_model_env_config, build_b2b_model, grow_b2b_model
from ..ppo import PPOConfig, RolloutBatch, cpu_state_snapshot
from .model_config_args import add_model_config_args, model_config_from_args


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


def _digest_batch(base_seed: int, matches: int, batch) -> str:
    """Hash every `RolloutBatch` field plus each array's shape and dtype.

    All twelve array fields are consumed by PPO/GAE/auxiliary training.
    `truncated_matches` is also included because `train_b2b` uses it for its
    fail-closed truncation-rate gate. No `RolloutBatch` field is excluded.
    """
    expected_fields = set(_ROLLOUT_DIGEST_ARRAY_FIELDS) | {"truncated_matches"}
    actual_fields = {field.name for field in fields(RolloutBatch)}
    if actual_fields != expected_fields:
        raise RuntimeError(
            "collect-bench digest field list is stale: "
            f"expected {sorted(actual_fields)}, covers {sorted(expected_fields)}")
    h = hashlib.sha256()
    _update_length_prefixed(
        h, json.dumps(
            {"base_seed": int(base_seed), "matches": int(matches)},
            sort_keys=True, separators=(",", ":")).encode())
    for name in _ROLLOUT_DIGEST_ARRAY_FIELDS:
        _update_array_digest(h, name, getattr(batch, name))
    _update_length_prefixed(
        h, json.dumps(
            {"dtype": "int", "field": "truncated_matches", "shape": []},
            sort_keys=True, separators=(",", ":")).encode())
    h.update(int(batch.truncated_matches).to_bytes(8, "big", signed=True))
    return h.hexdigest()


def run_bench(*, champion: Path, model_config, growth_blocks: int, workers: list[int],
             matches: int, base_seed: int, match_mode: str, bridge_kind: str,
             bridge_lib: Optional[str], device: str,
             max_steps_per_episode: Optional[int], event_window: int,
             worker_target=None) -> dict:
    """Run the full worker-count benchmark. Returns
    `{worker_count: {"startup_seconds": float, "steady_seconds": float,
    "digest": str}, "all_digests_equal": bool}`.

    `worker_target`, when given, is forwarded to every `ParallelB2bCollector`
    this bench constructs (adversarial round 9, medium finding). It exists
    only for test callers that need to inject a test-only worker function to
    exercise the real spawn-path can-fail property (e.g. proving a genuine
    perturbation in one worker's output still flips the digest) -- the CLI
    never sets it, and production benchmarking always uses the real
    `_b2b_worker_loop`."""
    env_config = EnvConfig(bridge_kind=bridge_kind, bridge_library_path=bridge_lib,
                           match_mode=match_mode, max_steps_per_episode=max_steps_per_episode,
                           oracle_observation=True, event_history_window=event_window)
    warm_started, effective_model_config = _build_model(env_config, model_config, champion, growth_blocks, device)
    # The persistent production collector constructs each worker model under
    # spawn and loads this detached CPU state snapshot for every collection
    # task, exactly as multi-worker `train_b2b` does.
    state_dict = cpu_state_snapshot(warm_started)
    ppo_config = PPOConfig(match_mode=match_mode, max_steps_per_episode=max_steps_per_episode,
                           device="cpu")
    results: dict[int, dict] = {}
    for w in workers:
        startup_start = time.perf_counter()
        collector = ParallelB2bCollector(
            env_config, effective_model_config, ppo_config, w,
            worker_target=worker_target)
        try:
            collector.start()
            collector.collect(state_dict, base_seed, matches)
            startup_seconds = time.perf_counter() - startup_start

            steady_start = time.perf_counter()
            batch = collector.collect(state_dict, base_seed, matches)
            steady_seconds = time.perf_counter() - steady_start
        finally:
            collector.close()
        results[w] = {
            "startup_seconds": startup_seconds,
            "steady_seconds": steady_seconds,
            "digest": _digest_batch(base_seed, matches, batch),
        }
    digests = {r["digest"] for r in results.values()}
    return {"results": results, "all_digests_equal": len(digests) <= 1,
           "model_config": effective_model_config}


def _print_table(results: dict[int, dict]) -> None:
    print(f"{'workers':>8}  {'startup_s':>10}  {'steady_s':>10}  digest")
    for w in sorted(results):
        r = results[w]
        print(
            f"{w:>8}  {r['startup_seconds']:>10.3f}  "
            f"{r['steady_seconds']:>10.3f}  {r['digest']}")


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
        payload = {
            str(w): {
                "startup_seconds": r["startup_seconds"],
                "steady_seconds": r["steady_seconds"],
                "digest": r["digest"],
            }
            for w, r in results.items()
        }
        payload["all_digests_equal"] = report["all_digests_equal"]
        args.json.write_text(json.dumps(payload, indent=2))

    sys.exit(0 if report["all_digests_equal"] else 1)


if __name__ == "__main__":
    main()

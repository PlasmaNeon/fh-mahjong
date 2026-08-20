"""fh-mj-collect-profile: measurement-only memory profile of the UNCHANGED
B2b collection + update path (data-scale-960 Amendment 4).

The Amendment 3 preflight's clean rerun was cgroup-killed with the bench
master at 33.8GiB anonymous RSS — roughly THREE simultaneous copies of the
960-match dataset — while its chunk-320 workers stayed bounded. The
2026-08-14 consult authorized this measurement (and only after it, one
targeted copy-elimination change): profile the current path at 320 and 640
matches, workers=10, chunk=320, fresh process per run, base-seed-700000
prefixes, and account for master/child RSS, PSS, cgroup current/peak, and
live RolloutBatch field bytes at every checkpoint — after each dispatch,
each outer concatenation field, the collector return, GAE, dtype/device
conversion, and the update.

This driver installs the `memprobe` callback (a no-op everywhere else),
runs EXACTLY ONE collection through the real spawn-context
`ParallelB2bCollector` (no warmup round — the profile wants the memory
shape of a single pass, not startup timing), snapshots per-field
shape/dtype/nbytes/ownership of the returned batch, then optionally runs
the same full-cycle GAE + `ppo_update` the bench runs. The batch digest is
recorded so a later copy-elimination change can prove byte parity against
these exact runs. `tracemalloc` (--tracemalloc) is supplemental per the
amendment: it sees only Python-visible allocations, missing torch/allocator
retention, which is why RSS/PSS/cgroup are the primary accounting.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc as _tracemalloc
from pathlib import Path

import numpy as np
import torch

from ..config import EnvConfig
from ..fdlimit import raise_file_descriptor_limit
from ..memprobe import rss_snapshot, set_memory_probe
from ..oracle import ParallelB2bCollector
from ..ppo import PPOConfig, cpu_state_snapshot
from .collect_bench import (
    FullCycleSettings,
    _PeakRssSampler,
    _ROLLOUT_DIGEST_ARRAY_FIELDS,
    _build_model,
    _digest_batch,
    _run_full_cycle_update,
)
from ..model_config_args import add_model_config_args, model_config_from_args


def _field_accounting(batch) -> dict:
    """Per-field shape/dtype/nbytes/ownership for every RolloutBatch array.

    `ownership` distinguishes an array that owns its buffer ("owned") from a
    view into another object's buffer ("view") — the amendment's copy audit
    needs to know which arrays are independent allocations."""
    out: dict = {}
    for name in _ROLLOUT_DIGEST_ARRAY_FIELDS:
        value = getattr(batch, name)
        if value is None:
            out[name] = None
            continue
        array = np.asarray(value)
        out[name] = {
            "shape": list(array.shape),
            "dtype": array.dtype.str,
            "nbytes": int(array.nbytes),
            "ownership": "owned" if array.base is None else "view",
        }
    out["total_nbytes"] = sum(v["nbytes"] for v in out.values()
                              if isinstance(v, dict))
    return out


def run_profile(*, champion: Path, model_config, growth_blocks: int, workers: int,
                matches: int, base_seed: int, match_mode: str, bridge_kind: str,
                bridge_lib, device: str, max_steps_per_episode, event_window: int,
                dispatch_chunk: int, full_cycle: FullCycleSettings | None,
                use_tracemalloc: bool = False,
                collector_factory=None) -> dict:
    """Profile one collection (+ optional full-cycle update). Returns the
    complete report dict; `collector_factory` exists for tests to substitute
    a spawn-free collector and defaults to the real `ParallelB2bCollector`."""
    env_config = EnvConfig(bridge_kind=bridge_kind, bridge_library_path=bridge_lib,
                           match_mode=match_mode, max_steps_per_episode=max_steps_per_episode,
                           oracle_observation=True, event_history_window=event_window)
    warm_started, effective_model_config = _build_model(
        env_config, model_config, champion, growth_blocks, device)
    state_dict = cpu_state_snapshot(warm_started)
    ppo_config = PPOConfig(match_mode=match_mode, max_steps_per_episode=max_steps_per_episode,
                           device="cpu", collect_dispatch_chunk=int(dispatch_chunk))

    checkpoints: list[dict] = []
    start = time.perf_counter()
    if use_tracemalloc:
        _tracemalloc.start()

    def _record(label: str, info: dict) -> None:
        entry = {"label": label, "elapsed_seconds": time.perf_counter() - start, **info}
        entry.update(rss_snapshot())
        if use_tracemalloc:
            current, peak = _tracemalloc.get_traced_memory()
            entry["tracemalloc_current_bytes"] = int(current)
            entry["tracemalloc_peak_bytes"] = int(peak)
        checkpoints.append(entry)

    sampler = _PeakRssSampler()
    sampler.start()
    set_memory_probe(_record)
    try:
        _record("profile_start", {"matches": matches, "workers": workers,
                                  "dispatch_chunk": dispatch_chunk})
        factory = collector_factory or (lambda: ParallelB2bCollector(
            env_config, effective_model_config, ppo_config, workers))
        collector = factory()
        try:
            collector.start()
            _record("collector_started", {})
            collect_start = time.perf_counter()
            batch = collector.collect(state_dict, base_seed, matches)
            collect_seconds = time.perf_counter() - collect_start
        finally:
            collector.close()
        _record("collector_closed", {})

        report: dict = {
            "matches": int(matches),
            "workers": int(workers),
            "base_seed": int(base_seed),
            "dispatch_chunk": int(dispatch_chunk),
            "collect_seconds": collect_seconds,
            "transition_rows": int(len(batch)),
            "digest": _digest_batch(base_seed, matches, batch),
            "field_accounting": _field_accounting(batch),
        }
        _record("field_accounting_done", {"rows": len(batch)})

        if full_cycle is not None:
            fc = _run_full_cycle_update(
                warm_started, batch, matches, collect_seconds, full_cycle,
                match_mode, max_steps_per_episode)
            report["full_cycle"] = fc
        _record("profile_end", {})
    finally:
        set_memory_probe(None)
        if use_tracemalloc:
            _tracemalloc.stop()
    peak, method = sampler.stop()
    report["host_peak_rss_bytes"] = peak
    report["host_peak_rss_method"] = method
    report["checkpoints"] = checkpoints
    return report


def _fmt_gib(value) -> str:
    return "-" if value is None else f"{value / (1024 ** 3):.2f}"


def _print_checkpoints(checkpoints: list[dict]) -> None:
    print(f"{'elapsed_s':>9}  {'label':<22}  {'master_gib':>10}  {'children_gib':>12}  "
          f"{'pss_gib':>8}  {'cgroup_gib':>10}  detail")
    for c in checkpoints:
        detail = {k: v for k, v in c.items()
                  if k not in ("label", "elapsed_seconds", "master_rss_bytes",
                               "master_hwm_bytes", "master_pss_bytes",
                               "children_rss_bytes", "children_count",
                               "cgroup_current_bytes", "cgroup_peak_bytes",
                               "tracemalloc_current_bytes", "tracemalloc_peak_bytes")}
        print(f"{c['elapsed_seconds']:>9.1f}  {c['label']:<22}  "
              f"{_fmt_gib(c['master_rss_bytes']):>10}  "
              f"{_fmt_gib(c['children_rss_bytes']):>12}  "
              f"{_fmt_gib(c['master_pss_bytes']):>8}  "
              f"{_fmt_gib(c['cgroup_current_bytes']):>10}  "
              f"{json.dumps(detail, sort_keys=True) if detail else ''}")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Measurement-only memory profile of the unchanged B2b collection "
                    "+ update path (data-scale-960 Amendment 4)")
    p.add_argument("--champion", type=Path, required=True)
    p.add_argument("--model-growth-blocks", type=int, default=0)
    p.add_argument("--workers", type=int, default=10)
    p.add_argument("--matches", type=int, required=True,
                   help="Amendment 4 registers 320 and 640 (one fresh process each)")
    p.add_argument("--base-seed", type=int, default=700000,
                   help="Amendment 4 registers base-seed-700000 prefixes")
    p.add_argument("--dispatch-chunk", type=int, default=320)
    p.add_argument("--match-mode", choices=("classic", "chongci"), default="chongci")
    p.add_argument("--max-steps-per-episode", type=int, default=4000)
    p.add_argument("--bridge-kind", choices=("go", "mock"), default="go")
    p.add_argument("--bridge-lib", type=str, default=None)
    p.add_argument("--device", type=str, default="cpu")
    p.add_argument("--event-window", type=int, default=128)
    p.add_argument("--tracemalloc", action="store_true",
                   help="supplemental Python-allocation tracing (primary accounting "
                        "is RSS/PSS/cgroup; tracemalloc cannot see torch/allocator "
                        "retention)")
    p.add_argument("--full-cycle", action="store_true",
                   help="after collection, run the same GAE + ppo_update the bench "
                        "runs, so conversion/update checkpoints are captured")
    fc_defaults = FullCycleSettings()
    p.add_argument("--minibatch-size", type=int, default=fc_defaults.minibatch_size)
    p.add_argument("--ppo-epochs", type=int, default=fc_defaults.ppo_epochs)
    p.add_argument("--gamma", type=float, default=fc_defaults.gamma)
    p.add_argument("--gae-lambda", type=float, default=fc_defaults.gae_lambda)
    p.add_argument("--lr", type=float, default=fc_defaults.lr)
    p.add_argument("--entropy-coef", type=float, default=fc_defaults.entropy_coef)
    p.add_argument("--ppo-device", type=str, default=fc_defaults.device)
    p.add_argument("--update-seed", type=int, default=fc_defaults.update_seed)
    p.add_argument("--minibatch-device-transfer", action="store_true",
                   help="profile the Amendment 5 host-resident update path "
                        "(per-minibatch synchronous device transfer)")
    p.add_argument("--json", type=Path, default=None, help="write the full report as JSON")
    add_model_config_args(p)
    args = p.parse_args()

    raise_file_descriptor_limit()
    torch.multiprocessing.set_sharing_strategy("file_system")
    model_config = model_config_from_args(args, event_window=args.event_window)

    full_cycle = None
    if args.full_cycle:
        full_cycle = FullCycleSettings(
            minibatch_size=args.minibatch_size, ppo_epochs=args.ppo_epochs,
            gamma=args.gamma, gae_lambda=args.gae_lambda, lr=args.lr,
            entropy_coef=args.entropy_coef, device=args.ppo_device,
            update_seed=args.update_seed,
            minibatch_device_transfer=args.minibatch_device_transfer)

    report = run_profile(
        champion=args.champion, model_config=model_config,
        growth_blocks=args.model_growth_blocks, workers=args.workers,
        matches=args.matches, base_seed=args.base_seed,
        match_mode=args.match_mode, bridge_kind=args.bridge_kind,
        bridge_lib=args.bridge_lib, device=args.device,
        max_steps_per_episode=args.max_steps_per_episode,
        event_window=args.event_window, dispatch_chunk=args.dispatch_chunk,
        full_cycle=full_cycle, use_tracemalloc=args.tracemalloc)

    _print_checkpoints(report["checkpoints"])
    fa = report["field_accounting"]
    print(f"\ntransition_rows: {report['transition_rows']}  "
          f"batch_total_gib: {_fmt_gib(fa['total_nbytes'])}  "
          f"host_peak_rss_gib: {_fmt_gib(report['host_peak_rss_bytes'])} "
          f"({report['host_peak_rss_method']})")
    print(f"digest: {report['digest']}")
    if args.json is not None:
        args.json.write_text(json.dumps(report, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()

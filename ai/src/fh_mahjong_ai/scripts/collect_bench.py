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

`--full-cycle` models the trainer's LIFETIME, not one iteration: after the
excluded warmup collection each count runs three consecutive collect + GAE +
`ppo_update` cycles over three consecutive seed blocks, against ONE persistent
model and optimizer (the process arm re-snapshots the updated model for each
cycle exactly as `train_b2b` does). Allocator retention and optimizer-state
growth across the iteration boundary are what those three cycles exist to
measure — a fresh deep copy per cycle would measure neither. Per cycle it
reports host peak RSS, CUDA allocated AND reserved peaks split between
collection and update, transition rows, optimizer steps, collection
throughput, aux label coverage, truncation, KL, and clip fraction, plus an
explicit rows/labels count-invariance check on top of the digest gate.
`ppo_update` moves the ENTIRE rollout onto the update device, so this is the
memory-honest preflight for raising matches_per_iter (collection-only numbers
under-measure both host RAM and CUDA peak). The collection CUDA peak is
snapshotted before the update's `reset_peak_memory_stats()` erases it.

`--collector batched` benches the pool collector
(`batched_b2b.collect_b2b_rollouts_batched`) instead: one process, one
persistent env pool reused for the warmup, every measured cycle and the float
gate, one batched forward per round on `--device`. `--pool-slots` replaces
`--workers`, and the three slot numbers stay distinct: requested (the flag),
allocated (`min(requested, --matches)`, what the pool constructs) and
effective-live (slots that held a match during a round).

Under `--inference-mode batched` the timed sweep is SAMPLED production
inference and is throughput-only: one float32 rounding difference can flip an
action and diverge a match, so digests are not compared across slot counts.
The exactness gate there is `float_gate` (spec G0.1b), which runs GREEDY —
a `per_row` greedy reference plus one greedy candidate per slot count,
compared per field against two-part (p99.9 and max) absolute ceilings, with
the greedy semantic digest required to match byte for byte. `--calibrate`
runs the spec's fixed three-repeat greedy block and prints the
`--float-ceiling` flags for a validation run on a disjoint seed block.
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

# Gate G0.1b: with `--collector batched --inference-mode batched` every slot
# count is collected GREEDILY and compared FIELD BY FIELD against a greedy
# `per_row` reference collected on the same seeds from the same weights.
#
# The gate runs greedy, never sampled. Under sampling a ~4e-5 logit
# perturbation flips an action with probability ~|delta p| per decision; one
# flip diverges the rest of that match, the row counts stop matching and the
# comparison degenerates into `shape_mismatch`. At the G1 row count (~650k
# rows per cycle) that is a structural coin flip, not a signal.
#
# The reference is the `per_row` batched run, not the process collector:
# `ParallelB2bCollector` has no greedy path at all, and G0.1
# (`test_b2b_collector_parity.py`) proves greedy `per_row` byte-identical to
# `collect_b2b_rollouts`. The process collector is therefore covered by
# transitivity, not skipped.
#
# Each ceiling is TWO-PART -- a quantile and a cap -- because max |delta| is an
# extreme-value statistic that grows with row count and with trunk width and
# depth, so a single-max ceiling would be breached by measurement scale rather
# than by a defect. Both parts must hold; the spec forbids widening either
# after the fact. Absolute, not relative: relative error is unstable near 0.
# The legacy atol/rtol count is printed as a diagnostic only.
_FLOAT_GATE_FIELDS = ("legal_logits", "old_logprobs", "values")
_FLOAT_GATE_PARTS = ("p99_9", "max")
_FLOAT_GATE_CEILINGS = {
    "cpu": {
        "legal_logits": {"p99_9": 1e-5, "max": 2e-4},
        "old_logprobs": {"p99_9": 1e-5, "max": 2e-4},
        "values": {"p99_9": 1e-6, "max": 2e-5},
    },
    # CUDA caps for the calibration procedure (spec G0.1b), pre-registered
    # before any CUDA number was seen: one number per field (logits and
    # logprobs 1e-4, values 1e-5), applied as the cap on BOTH parts. The
    # operational threshold comes from `--calibrate` (2x the three-repeat
    # calibration statistic, capped here) and is always far tighter on the
    # quantile part; `--float-ceiling` may set a threshold BELOW these, never
    # above.
    "cuda": {
        "legal_logits": {"p99_9": 1e-4, "max": 1e-4},
        "old_logprobs": {"p99_9": 1e-4, "max": 1e-4},
        "values": {"p99_9": 1e-5, "max": 1e-5},
    },
}
_FLOAT_GATE_PERCENTILES = ((50, "p50"), (95, "p95"), (99, "p99"), (99.9, "p99_9"))

GATE_REFERENCE_NOTE = (
    "the greedy per_row batched run is the reference because ParallelB2bCollector has "
    "no greedy path; G0.1 (test_b2b_collector_parity.py) proves greedy per_row "
    "byte-identical to collect_b2b_rollouts, so the process collector is covered by "
    "transitivity and was NOT skipped")


def float_gate_ceilings(device: str, overrides: Optional[dict] = None) -> dict:
    """Two-part per-field ceilings for `device` (cpu vs cuda caps), shaped
    `{field: {"p99_9": float, "max": float}}`. `overrides` has the same shape
    and may only TIGHTEN a part below its cap."""
    caps = {name: dict(parts) for name, parts
            in _FLOAT_GATE_CEILINGS["cuda" if str(device).startswith("cuda") else "cpu"].items()}
    for name, parts in (overrides or {}).items():
        if name not in caps:
            raise ValueError(f"unknown float-gate field {name!r} (expected one of {_FLOAT_GATE_FIELDS})")
        for part, value in parts.items():
            if part not in _FLOAT_GATE_PARTS:
                raise ValueError(
                    f"unknown float-gate ceiling part {part!r} for {name} "
                    f"(expected one of {_FLOAT_GATE_PARTS})")
            if float(value) > caps[name][part]:
                raise ValueError(
                    f"float-gate ceiling for {name}.{part} may not exceed its cap: "
                    f"{value} > {caps[name][part]}")
            caps[name][part] = float(value)
    return caps


def emission_ordered_logits(sink: list, batch) -> np.ndarray:
    """Reorder a collector's `diagnostics["logits"]` sink (decision order,
    `(match_seed, seat, row)`) into the batch's emission order: matches in seed
    order, seats contiguous, decisions in order within a seat. A stable sort
    on (seed, seat) gives exactly that. Alignment is checked against the
    batch's mask: every illegal entry must carry the finfo.min mask value."""
    order = sorted(range(len(sink)), key=lambda i: (int(sink[i][0]), int(sink[i][1])))
    if len(order) != len(batch):
        raise RuntimeError(f"logits sink has {len(order)} rows, batch has {len(batch)}")
    if not order:
        return np.zeros((0, int(batch.action_mask.shape[1])), dtype=np.float32)
    logits = np.stack([np.asarray(sink[i][2], dtype=np.float32) for i in order])
    illegal = np.asarray(batch.action_mask) == 0
    if not np.all(logits[illegal] <= np.finfo(np.float32).min):
        raise RuntimeError("logits sink is misaligned with the batch's action masks")
    return logits


def float_gate_arrays(batch, logits: np.ndarray) -> dict:
    """The three gated arrays of one collection, float64 copies: legal
    logits (mask==1 entries in emission order), old_logprobs, values."""
    legal = np.asarray(batch.action_mask).astype(bool)
    return {
        "legal_logits": np.asarray(logits, dtype=np.float64)[legal].copy(),
        "old_logprobs": np.asarray(batch.old_logprobs, dtype=np.float64).copy(),
        "values": np.asarray(batch.values, dtype=np.float64).copy(),
    }


def float_field_stats(reference: np.ndarray, current: np.ndarray, ceiling: dict) -> dict:
    """Per-field comparison record for one (reference, candidate) pair.

    `ceiling` is the two-part bound `{"p99_9": float, "max": float}`. BOTH
    parts gate: `passed` requires zero non-finite elements, zero elements
    beyond the max cap, and a p99.9 |delta| within the quantile bound."""
    reference = np.asarray(reference, dtype=np.float64)
    current = np.asarray(current, dtype=np.float64)
    nonfinite = int((~np.isfinite(reference)).sum() + (~np.isfinite(current)).sum())
    ceiling = {part: float(ceiling[part]) for part in _FLOAT_GATE_PARTS}
    out = {"ceiling": ceiling, "element_count": int(current.size),
           "reference_count": int(reference.size), "nonfinite_count": nonfinite,
           "shape_mismatch": reference.shape != current.shape}
    if out["shape_mismatch"]:
        out.update(mismatch_count=None, max_abs_diff=None, beyond_legacy_tol=None,
                   beyond_ceiling=None, p99_9_within_ceiling=False, passed=False,
                   **{label: None for _, label in _FLOAT_GATE_PERCENTILES})
        return out
    diff = np.abs(reference - current)
    finite = np.isfinite(diff)
    d = diff[finite]
    if d.size:
        pct = {label: float(np.percentile(d, q)) for q, label in _FLOAT_GATE_PERCENTILES}
        max_abs = float(d.max())
    else:
        pct = {label: 0.0 for _, label in _FLOAT_GATE_PERCENTILES}
        max_abs = 0.0
    legacy = _FLOAT_INVARIANCE_TOL["atol"] + _FLOAT_INVARIANCE_TOL["rtol"] * np.abs(current)
    bad = int((~finite).sum())
    out.update(mismatch_count=int((d > 0).sum()) + bad,
               max_abs_diff=max_abs,
               beyond_legacy_tol=int((d > legacy[finite]).sum()) + bad,
               beyond_ceiling=int((d > ceiling["max"]).sum()) + bad,
               **pct)
    out["p99_9_within_ceiling"] = bool(pct["p99_9"] <= ceiling["p99_9"])
    out["passed"] = (nonfinite == 0 and out["beyond_ceiling"] == 0
                     and out["p99_9_within_ceiling"])
    return out


def compare_float_fields(reference: dict, current: dict, ceilings: dict) -> dict:
    return {name: float_field_stats(reference[name], current[name], ceilings[name])
            for name in _FLOAT_GATE_FIELDS}


_STAT_MAX_KEYS = ("element_count", "reference_count", "nonfinite_count", "mismatch_count",
                  "beyond_legacy_tol", "beyond_ceiling", "max_abs_diff",
                  "p50", "p95", "p99", "p99_9")


def worst_over_repeats(per_repeat: list[dict], ceilings: dict) -> dict:
    """Per field, the WORST value each statistic takes across repeats.

    This is the "calibration maximum" of spec G0.1b's CUDA procedure (three
    greedy repeats), and for the ordinary one-repeat gate it is that repeat's
    record unchanged. `passed` is the conjunction, so any failing repeat fails
    the field."""
    if not per_repeat:
        raise ValueError("worst_over_repeats needs at least one repeat")
    out: dict = {}
    for name in _FLOAT_GATE_FIELDS:
        stats = [rep[name] for rep in per_repeat]
        if any(st["shape_mismatch"] for st in stats):
            worst = dict(stats[0])
            worst.update(shape_mismatch=True, passed=False, p99_9_within_ceiling=False,
                         mismatch_count=None, max_abs_diff=None, beyond_legacy_tol=None,
                         beyond_ceiling=None,
                         **{label: None for _, label in _FLOAT_GATE_PERCENTILES})
            out[name] = worst
            continue
        worst = {"ceiling": {part: float(ceilings[name][part]) for part in _FLOAT_GATE_PARTS},
                 "shape_mismatch": False,
                 "passed": all(st["passed"] for st in stats),
                 "p99_9_within_ceiling": all(st["p99_9_within_ceiling"] for st in stats)}
        for key in _STAT_MAX_KEYS:
            worst[key] = max(st[key] for st in stats)
        out[name] = worst
    return out


def _format_float_stats(label: str, name: str, st: dict) -> str:
    if st["shape_mismatch"]:
        return (f"  {label} {name}: SHAPE MISMATCH reference={st['reference_count']} "
                f"current={st['element_count']} FAIL")
    ceiling = st["ceiling"]
    return (f"  {label} {name}: n={st['element_count']} nonfinite={st['nonfinite_count']} "
            f"mismatch={st['mismatch_count']} p50={st['p50']:.3e} p95={st['p95']:.3e} "
            f"p99={st['p99']:.3e} p99.9={st['p99_9']:.3e} max={st['max_abs_diff']:.3e} "
            f">legacy(atol={_FLOAT_INVARIANCE_TOL['atol']},rtol={_FLOAT_INVARIANCE_TOL['rtol']})="
            f"{st['beyond_legacy_tol']} "
            f"ceiling(p99.9={ceiling['p99_9']:.1e},max={ceiling['max']:.1e}) "
            f">max_ceiling={st['beyond_ceiling']} "
            f"p99.9_ok={st['p99_9_within_ceiling']} "
            f"{'PASS' if st['passed'] else 'FAIL'}")


def _float_gate_violations(label: str, stats: dict) -> list[str]:
    """Every way a field can fail its two-part bound. Both parts are checked;
    passing one never excuses the other."""
    out = []
    for name in _FLOAT_GATE_FIELDS:
        st = stats[name]
        if st["shape_mismatch"]:
            out.append(f"{label} field={name}: shape mismatch against the greedy per_row "
                       "reference (row counts diverged)")
            continue
        if st["nonfinite_count"]:
            out.append(f"{label} field={name}: {st['nonfinite_count']} non-finite element(s)")
        if st["beyond_ceiling"]:
            out.append(f"{label} field={name}: max_abs_diff={st['max_abs_diff']:.3e} > "
                       f"max ceiling {st['ceiling']['max']:.1e} "
                       f"({st['beyond_ceiling']} element(s))")
        if not st["p99_9_within_ceiling"]:
            out.append(f"{label} field={name}: p99.9={st['p99_9']:.3e} > "
                       f"p99.9 ceiling {st['ceiling']['p99_9']:.1e}")
    return out


def calibration_thresholds(fields: dict, ceilings: dict) -> tuple[dict, list[str]]:
    """Operational two-part thresholds from a calibration block: 2x the
    calibration statistic per part, capped by the registered ceiling
    (spec G0.1b's CUDA procedure). A calibration statistic ABOVE its registered
    cap stops the work — the cap is never widened afterwards, so that case is
    returned as a violation rather than absorbed."""
    thresholds: dict = {}
    violations: list[str] = []
    for name in _FLOAT_GATE_FIELDS:
        st = fields[name]
        thresholds[name] = {}
        if st["shape_mismatch"]:
            violations.append(f"calibration field={name}: shape mismatch — no threshold derivable")
            continue
        if st["nonfinite_count"]:
            violations.append(
                f"calibration field={name}: {st['nonfinite_count']} non-finite element(s)")
        for part in _FLOAT_GATE_PARTS:
            observed = float(st["max_abs_diff"] if part == "max" else st[part])
            cap = float(ceilings[name][part])
            if observed > cap:
                violations.append(
                    f"calibration {name}.{part}={observed:.3e} exceeds the registered cap "
                    f"{cap:.1e} — stop; the cap is never widened")
            thresholds[name][part] = min(2.0 * observed, cap)
    return thresholds, violations


def format_ceiling_flags(thresholds: dict) -> list[str]:
    """The `--float-ceiling` flags that feed `thresholds` straight back into a
    validation run, so nobody hand-derives them."""
    flags = []
    for name in _FLOAT_GATE_FIELDS:
        for part in _FLOAT_GATE_PARTS:
            value = thresholds.get(name, {}).get(part)
            if value is not None:
                flags.append(f"--float-ceiling {name}.{part}={value:.6e}")
    return flags


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


def allocated_slots(requested: int, matches: int) -> int:
    """The slot count the pool actually CONSTRUCTS: `min(requested, matches)`.

    Three slot numbers are distinct and all three are reported (spec change 3):
    **requested** (`--pool-slots`), **allocated** (this — slots beyond the match
    count never receive a command, so allocating them would charge memory and
    env construction to a candidate that can never use them) and
    **effective-live** (`peak_live_slots`: slots that actually held a match
    during a round). At `allocated == matches` the pool never refills, so the
    per-round batch decays monotonically toward 1 and the arm's rows-per-forward
    distribution — not its slot count — is what makes its throughput
    interpretable."""
    return max(1, min(int(requested), int(matches)))


class _ForwardBatchRecorder:
    """Rows per forward: the batch dimension of every top-level `model(...)`
    call inside a phase (spec G1 wants mean / median / p10 rows per forward, a
    batch-size histogram and the round count — without them a missed throughput
    target cannot be told from a scheduling artefact).

    A forward PRE-hook that returns `None` cannot alter the forward's inputs or
    its numerics; it only reads `planes.shape[0]`. Constructing it with
    `model=None` makes it a no-op, which is what the process collector needs:
    its forwards happen inside spawn workers (one batch-1 forward per decision,
    by construction) and are not observable from the master process."""

    def __init__(self, model=None):
        self._model = model
        self.sizes: list[int] = []
        self._handle = None

    def _hook(self, module, args, kwargs):
        planes = args[0] if args else kwargs.get("planes")
        if planes is not None:
            self.sizes.append(int(planes.shape[0]))
        return None

    def __enter__(self):
        if self._model is not None:
            self._handle = self._model.register_forward_pre_hook(self._hook, with_kwargs=True)
        return self

    def __exit__(self, *exc_info):
        if self._handle is not None:
            self._handle.remove()
            self._handle = None
        return False


_BATCH_HISTOGRAM_EDGES = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024)


def batch_size_histogram(sizes) -> list[dict]:
    """Power-of-two buckets over the per-forward row counts, ascending, up to
    the largest observed size. The last edge's bucket is open-ended."""
    if not sizes:
        return []
    peak = max(int(s) for s in sizes)
    buckets = []
    for i, low in enumerate(_BATCH_HISTOGRAM_EDGES):
        high = (_BATCH_HISTOGRAM_EDGES[i + 1] - 1
                if i + 1 < len(_BATCH_HISTOGRAM_EDGES) else None)
        if low > peak:
            break
        label = f"{low}" if high == low else (f"{low}-{high}" if high is not None else f"{low}+")
        count = sum(1 for s in sizes
                    if int(s) >= low and (high is None or int(s) <= high))
        buckets.append({"low": low, "high": high, "label": label, "count": count})
    return buckets


def forward_shape_stats(sizes, pool_rounds=None) -> dict:
    """Rows-per-forward summary for one collection (spec G1)."""
    if not sizes:
        return {"observable": False, "forwards": None, "rows_total": None,
                "rows_per_forward_mean": None, "rows_per_forward_median": None,
                "rows_per_forward_p10": None, "rows_per_forward_min": None,
                "rows_per_forward_max": None, "pool_rounds": pool_rounds,
                "batch_size_histogram": [],
                "note": "process collector: one batch-1 forward per decision inside each "
                        "spawn worker, not observable from the master process"}
    arr = np.asarray(sizes, dtype=np.float64)
    return {"observable": True, "forwards": int(arr.size), "rows_total": int(arr.sum()),
            "rows_per_forward_mean": float(arr.mean()),
            "rows_per_forward_median": float(np.median(arr)),
            "rows_per_forward_p10": float(np.percentile(arr, 10)),
            "rows_per_forward_min": int(arr.min()), "rows_per_forward_max": int(arr.max()),
            "pool_rounds": pool_rounds,
            "batch_size_histogram": batch_size_histogram(sizes)}


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


def _run_full_cycle_update(model, optimizer, batch, matches: int, collect_seconds: float,
                          settings: FullCycleSettings, match_mode: str,
                          max_steps_per_episode: Optional[int]) -> dict:
    """One real training update on `batch`, measured, against the caller's
    PERSISTENT model and optimizer.

    Persistence is the point (spec G1): the trainer keeps one model and one
    optimizer for its whole lifetime, so a fresh deep copy per cycle would
    measure neither the optimizer-state growth nor the allocator retention the
    gate exists to observe. Every benchmarked count still starts from an
    identical deep copy of the warm-started model, and `update_seed` is set
    before each update, so a digest-equal collection still yields a
    count-invariant update."""
    fc: dict = {
        "transition_rows": int(len(batch)),
        "matches_per_second": float(matches) / collect_seconds if collect_seconds > 0 else 0.0,
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
    if use_cuda:
        # The caller has already snapshotted the COLLECTION peak (see
        # `_run_one_cycle`); this reset scopes the numbers below to the update.
        torch.cuda.reset_peak_memory_stats()
    torch.manual_seed(settings.update_seed)
    update_start = time.perf_counter()
    advantages, returns = compute_gae(batch.rewards, batch.values, batch.dones,
                                      settings.gamma, settings.gae_lambda)
    metrics = ppo_update(model, optimizer, batch, advantages, returns, update_config)
    if use_cuda:
        torch.cuda.synchronize()
    fc["update_seconds"] = time.perf_counter() - update_start
    (fc["cuda_peak_update_allocated_bytes"],
     fc["cuda_peak_update_reserved_bytes"]) = _cuda_peaks(use_cuda)
    fc.update(metrics)
    return fc


_FULL_CYCLE_INVARIANT_KEYS = (
    "transition_rows", "truncated_matches",
    "dealin_positive_rate", "rank_label_coverage",
)


# Spec G1: each arm runs ONE excluded warmup collection, then three genuine
# consecutive collect -> PPO cycles on one persistent pool (or one persistent
# spawn collector) and one persistent model/optimizer, over three fixed
# consecutive seed blocks -- the trainer's lifetime, not a fresh deep copy per
# cycle. Allocator retention and optimizer-state growth across the iteration
# boundary are what the count of three exists to measure (the ds960 lap's
# retention failures were iteration-boundary failures).
_FULL_CYCLE_CYCLES = 3

# Spec G0.1b's CUDA procedure: a FIXED three-repeat greedy calibration block.
# On CPU the repeats are identical by construction; on CUDA they measure the
# run-to-run spread that the operational threshold has to cover.
_CALIBRATION_REPEATS = 3


def run_bench(*, champion: Path, model_config, growth_blocks: int,
             workers: Optional[list[int]] = None,
             matches: int, base_seed: int, match_mode: str, bridge_kind: str,
             bridge_lib: Optional[str], device: str,
             max_steps_per_episode: Optional[int], event_window: int,
             worker_target=None, full_cycle: Optional[FullCycleSettings] = None,
             dispatch_chunk: int = 0, placement_bonus: Optional[dict] = None,
             collector: str = "process", pool_slots: Optional[list[int]] = None,
             inference_mode: str = "batched",
             float_ceilings: Optional[dict] = None,
             calibrate: bool = False) -> dict:
    """Run the collector benchmark. Returns
    `{count: {"startup_seconds": float, "steady_seconds": float,
    "digest": str, ...}, "all_digests_equal": bool}` where `count` is a worker
    count (`collector="process"`, from `workers`) or the REQUESTED env-pool
    slot count (`collector="batched"`, from `pool_slots`).

    Slot accounting (spec change 3) is three separate numbers, all reported:
    `requested_slots` (the `--pool-slots` value and the dict key),
    `allocated_slots` (`allocated_slots(requested, matches)` -- what the pool
    actually constructs) and `peak_live_slots` (slots that held a match during
    a round). `forward_shapes` carries spec G1's rows-per-forward summary:
    mean / median / p10, min / max, the pool's round count and a batch-size
    histogram, recorded by a forward PRE-hook that cannot alter numerics.

    With `full_cycle` set, each count runs one excluded warmup collection and
    then `_FULL_CYCLE_CYCLES` consecutive collect + `ppo_update` cycles against
    ONE persistent model and optimizer, over consecutive seed blocks
    (`base_seed + cycle * matches`, mirroring `train_b2b`'s `iter_seed`), and
    the process arm re-snapshots the updated model for each cycle exactly as
    the trainer does. Per-cycle metrics live in `full_cycle["cycles"]`;
    `full_cycle`'s top level carries the phase-wide host RSS peak and the slot
    accounting. `"rows_and_labels_equal"` is True iff transition rows,
    truncations and aux label coverage are identical across all counts, for
    every cycle.

    `collector="batched"` builds ONE persistent pool per slot count and reuses
    it for the warmup, every measured cycle and the float gate (mirroring the
    process path's persistent workers), collecting through
    `batched_b2b.collect_b2b_rollouts_batched` on `device`. `inference_mode`
    is forwarded to it: `"batched"` is the production shape, `"per_row"` the
    batch-composition-independent one.

    With `collector="batched"` and `inference_mode="batched"` the report also
    carries `"float_gate"` (spec G0.1b). THE FLOAT GATE RUNS GREEDY: its
    reference is one `per_row` GREEDY collection, and every candidate feeding
    `compare_float_fields` is a separate GREEDY collection on the same seeds
    and the same (warm-started, never updated) weights. The timed sweep stays
    sampled -- that is production inference -- and is therefore throughput
    only: its digests are not compared across slot counts, because one
    rounding-induced action flip diverges a match and the row counts stop
    matching. `calibrate=True` runs `_CALIBRATION_REPEATS` greedy repeats per
    slot count and derives operational `--float-ceiling` flags from the worst
    observed statistic.

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
    if calibrate and not (collector == "batched" and inference_mode == "batched"):
        raise ValueError("--calibrate applies only to --collector batched "
                         "--inference-mode batched (it calibrates the G0.1b float gate)")
    if (full_cycle is not None and collector == "batched"
            and str(full_cycle.device) != str(device)):
        # One persistent model spans collection and update here, and
        # `ppo_update` assumes the model already sits on `config.device`.
        raise ValueError(
            "--full-cycle with --collector batched keeps ONE persistent model across "
            f"collection and the update, so the update device ({full_cycle.device!r}) "
            f"must equal the collection device ({device!r})")
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
    float_gate: Optional[dict] = None
    gate_reference: Optional[dict] = None
    ceilings: Optional[dict] = None
    gate_repeats = _CALIBRATION_REPEATS if calibrate else 1
    calibration_records: list[dict] = []
    if collector == "batched" and inference_mode == "batched":
        ceilings = float_gate_ceilings(device, float_ceilings)
        ref_slots = allocated_slots(counts[0], matches)
        ref_pool = make_b2b_pool(env_config, warm_started, batched_config, ref_slots)
        ref_start = time.perf_counter()
        try:
            ref_diag: dict = {"logits": []}
            ref_batch = collect_b2b_rollouts_batched(
                env_config, warm_started, batched_config, base_seed=base_seed, pool=ref_pool,
                inference_mode="per_row", action_selection="greedy", diagnostics=ref_diag)
        finally:
            ref_pool.close()
        gate_reference = float_gate_arrays(
            ref_batch, emission_ordered_logits(ref_diag["logits"], ref_batch))
        float_gate = {
            "reference": "per_row",
            "action_selection": "greedy",
            "reference_description": "collect_b2b_rollouts_batched(inference_mode='per_row', "
                                     "action_selection='greedy') on the same seeds and "
                                     f"weights, pool_slots={ref_slots}",
            "reference_note": GATE_REFERENCE_NOTE,
            "reference_seconds": time.perf_counter() - ref_start,
            "reference_rows": int(len(ref_batch)),
            "reference_semantic_digest": _semantic_digest_batch(base_seed, matches, ref_batch),
            "ceilings": ceilings,
            "repeats": gate_repeats,
            "calibrate": bool(calibrate),
            "comparisons": {},
            "violations": [],
            "passed": True,
        }
        del ref_batch, ref_diag
    for count in counts:
        requested = int(count)
        alloc = allocated_slots(requested, matches) if collector == "batched" else None
        phase_sampler: Optional[_PeakRssSampler] = None
        if full_cycle is not None:
            phase_sampler = _PeakRssSampler()
            phase_sampler.start()
        # Persistent for this count's whole phase, as the trainer is for its
        # whole lifetime. Each count starts from an identical deep copy of the
        # warm-started model, so a digest-equal collection still yields a
        # count-invariant update.
        cycle_model = optimizer = None
        if full_cycle is not None:
            cycle_model = copy.deepcopy(warm_started).to(full_cycle.device)
            optimizer = torch.optim.AdamW(cycle_model.parameters(), lr=full_cycle.lr)
        # The batched collector collects with the model it will then update;
        # the process collector's workers load a CPU snapshot of it.
        collect_model = cycle_model if (collector == "batched" and cycle_model is not None) \
            else warm_started
        snapshot = state_dict
        pool = spawn_collector = None
        startup_start = time.perf_counter()
        if collector == "batched":
            pool = make_b2b_pool(env_config, warm_started, batched_config, alloc)
        else:
            spawn_collector = ParallelB2bCollector(
                env_config, effective_model_config, ppo_config, requested,
                worker_target=worker_target)

        def _collect(seed: int, record_shapes: bool = False):
            """One collection through this count's persistent collector.
            Returns (batch, diagnostics, per-forward row counts)."""
            if collector == "batched":
                diag: dict = {}
                with _ForwardBatchRecorder(collect_model if record_shapes else None) as rec:
                    b = collect_b2b_rollouts_batched(
                        env_config, collect_model, batched_config, base_seed=seed,
                        pool=pool, inference_mode=inference_mode, diagnostics=diag)
                return b, diag, rec.sizes
            return spawn_collector.collect(snapshot, seed, matches), {}, []

        try:
            if spawn_collector is not None:
                spawn_collector.start()
            # Warmup: startup timing only, never a measured cycle.
            _collect(base_seed)
            startup_seconds = time.perf_counter() - startup_start

            cycles: list[dict] = []
            for cycle_index in range(_FULL_CYCLE_CYCLES if full_cycle is not None else 1):
                cycle_seed = int(base_seed + cycle_index * int(matches))
                cycle_sampler: Optional[_PeakRssSampler] = None
                if full_cycle is not None:
                    cycle_sampler = _PeakRssSampler()
                    cycle_sampler.start()
                if collect_on_cuda:
                    torch.cuda.reset_peak_memory_stats()
                collect_start = time.perf_counter()
                batch, diag, sizes = _collect(cycle_seed, record_shapes=True)
                collect_seconds = time.perf_counter() - collect_start
                # Snapshotted HERE, before `_run_full_cycle_update`'s
                # `reset_peak_memory_stats()` erases the collection phase's peak.
                collect_alloc, collect_reserved = _cuda_peaks(collect_on_cuda)
                record = {
                    "cycle": cycle_index,
                    "base_seed": cycle_seed,
                    "collect_seconds": collect_seconds,
                    "digest": _digest_batch(cycle_seed, matches, batch),
                    "semantic_digest": _semantic_digest_batch(cycle_seed, matches, batch),
                    "peak_live_slots": diag.get("peak_live_slots"),
                    "forward_shapes": forward_shape_stats(sizes, diag.get("rounds")),
                }
                if full_cycle is not None:
                    assert cycle_model is not None and optimizer is not None
                    record.update(_run_full_cycle_update(
                        cycle_model, optimizer, batch, matches, collect_seconds,
                        full_cycle, match_mode, max_steps_per_episode))
                    record["cuda_peak_collect_allocated_bytes"] = collect_alloc
                    record["cuda_peak_collect_reserved_bytes"] = collect_reserved
                    assert cycle_sampler is not None
                    (record["host_peak_rss_bytes"],
                     record["host_peak_rss_method"]) = cycle_sampler.stop()
                    # The trainer re-snapshots the UPDATED model for the next
                    # iteration's workers (`train_b2b`'s collect branch); the
                    # batched arm needs no snapshot -- it collects with the
                    # very object the update just mutated.
                    if collector == "process":
                        snapshot = cpu_state_snapshot(cycle_model)
                cycles.append(record)
                if cycle_index == 0:
                    first_batch = batch
                else:
                    del batch

            # The gate's candidate is a SEPARATE greedy collection, on the
            # untouched warm-started weights and the same seed block as the
            # greedy reference. It is deliberately outside every timed
            # section: at batch-1 (`per_row`) the reference alone costs about
            # a whole process arm, and folding either into the sweep would
            # charge it to the batched candidate (spec G1).
            per_repeat: list[dict] = []
            semantic_ok = True
            if float_gate is not None:
                for _ in range(gate_repeats):
                    gate_diag: dict = {"logits": []}
                    gate_batch = collect_b2b_rollouts_batched(
                        env_config, warm_started, batched_config, base_seed=base_seed,
                        pool=pool, inference_mode="batched", action_selection="greedy",
                        diagnostics=gate_diag)
                    per_repeat.append(compare_float_fields(
                        gate_reference,
                        float_gate_arrays(
                            gate_batch,
                            emission_ordered_logits(gate_diag["logits"], gate_batch)),
                        ceilings))
                    semantic_ok = semantic_ok and (
                        _semantic_digest_batch(base_seed, matches, gate_batch)
                        == float_gate["reference_semantic_digest"])
                    del gate_batch, gate_diag
        finally:
            if pool is not None:
                pool.close()
            if spawn_collector is not None:
                spawn_collector.close()

        batch = first_batch
        results[requested] = {
            "startup_seconds": startup_seconds,
            "steady_seconds": cycles[0]["collect_seconds"],
            "digest": cycles[0]["digest"],
            "semantic_digest": cycles[0]["semantic_digest"],
            "requested_slots": requested if collector == "batched" else None,
            "allocated_slots": alloc,
            "peak_live_slots": cycles[0]["peak_live_slots"],
            "forward_shapes": cycles[0]["forward_shapes"],
        }
        if float_gate is not None:
            label = f"pool_slots={requested}"
            worst = worst_over_repeats(per_repeat, ceilings)
            violations = _float_gate_violations(label, worst)
            if not semantic_ok:
                violations.append(
                    f"{label}: greedy semantic digest differs from the greedy per_row "
                    "reference")
            float_gate["comparisons"][requested] = {
                "fields": worst, "repeats": len(per_repeat),
                "semantic_matches_reference": semantic_ok}
            float_gate["violations"].extend(violations)
            if violations:
                float_gate["passed"] = False
            calibration_records.extend(per_repeat)
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
            assert phase_sampler is not None
            peak, method = phase_sampler.stop()
            results[requested]["full_cycle"] = {
                "collector": collector,
                "cycles": cycles,
                "cycle_count": len(cycles),
                "host_peak_rss_bytes": peak,
                "host_peak_rss_method": method,
                # Requested / allocated / effective-live, never collapsed into
                # one "slots" number (spec change 3).
                "requested_slots": requested if collector == "batched" else None,
                "allocated_slots": alloc,
                "peak_live_slots": max((c["peak_live_slots"] or 0) for c in cycles)
                                   if collector == "batched" else None,
            }
        del batch, first_batch, floats
    if float_gate is not None and calibrate:
        worst_all = worst_over_repeats(calibration_records, ceilings)
        thresholds, cal_violations = calibration_thresholds(worst_all, ceilings)
        float_gate["calibration"] = {
            "repeats_per_slot_count": gate_repeats,
            "slot_counts": [int(c) for c in counts],
            "worst": worst_all,
            "thresholds": thresholds,
            "ceiling_flags": format_ceiling_flags(thresholds),
            "violations": cal_violations,
        }
        float_gate["violations"].extend(cal_violations)
        if cal_violations:
            float_gate["passed"] = False
    digests = {r["digest"] for r in results.values()}
    semantic_digests = {r["semantic_digest"] for r in results.values()}
    # Under production batched inference the sweep is SAMPLED, so a float32
    # rounding difference can flip one action and diverge the rest of that
    # match: neither the full digest nor the semantic digest is comparable
    # across slot counts, and neither gates. The gate in that mode is the
    # greedy `float_gate` above, whose per-field bounds AND whose
    # `semantic_matches_reference` are exact.
    exact_expected = not (collector == "batched" and inference_mode == "batched")
    report = {"results": results, "all_digests_equal": len(digests) <= 1,
             "semantic_digests_equal": len(semantic_digests) <= 1,
             # Reported, never gated: see `_ROLLOUT_TOLERANT_FIELDS`.
             "float_fields_within_tolerance": float_fields_within_tolerance,
             "float_allclose_violations": float_allclose_violations,
             "semantics_equal": len(semantic_digests) <= 1,
             "max_float_diff": max_float_diff,
             "exact_invariance_expected": exact_expected,
             "sweep_action_selection": "sample",
             "cross_count_gate": "digest" if exact_expected else "float_gate",
             "model_config": effective_model_config,
             "collector": collector,
             "inference_mode": inference_mode if collector == "batched" else None,
             "dispatch_chunk_matches": int(dispatch_chunk),
             # Spec G0.1b hard gate (batched inference only); None otherwise.
             "float_gate": float_gate}
    if full_cycle is not None:
        invariant_tuples = {
            tuple(cycle[key]
                  for cycle in r["full_cycle"]["cycles"]
                  for key in _FULL_CYCLE_INVARIANT_KEYS)
            for r in results.values()
        }
        report["rows_and_labels_equal"] = len(invariant_tuples) <= 1
        cycle_digests = {tuple(c["digest"] for c in r["full_cycle"]["cycles"])
                         for r in results.values()}
        # Reported, not gated: cycles after the first collect with weights the
        # update produced, and a CUDA update is not bit-reproducible.
        report["cycle_digests_equal"] = len(cycle_digests) <= 1
    return report
def _opt(value, spec: str) -> str:
    """`format(value, spec)`, or a column-width dash when the value does not
    apply to this collector (slot counts on the process arm, CUDA peaks on a
    CPU phase). Padding the dash keeps the table's columns aligned."""
    if value is not None:
        return format(value, spec)
    width = spec.lstrip("<>^=+- ").split(".")[0]
    return format("-", f">{width}") if width.isdigit() else "-"


def _print_table(results: dict[int, dict], label: str = "workers") -> None:
    print(f"{label:>10}  {'alloc':>6}  {'live':>5}  {'startup_s':>10}  {'steady_s':>10}  "
          f"{'fwd_rows_mean':>13}  digest")
    for w in sorted(results):
        r = results[w]
        shapes = r.get("forward_shapes") or {}
        print(
            f"{w:>10}  {_opt(r.get('allocated_slots'), '>6d')}  "
            f"{_opt(r.get('peak_live_slots'), '>5d')}  "
            f"{r['startup_seconds']:>10.3f}  {r['steady_seconds']:>10.3f}  "
            f"{_opt(shapes.get('rows_per_forward_mean'), '>13.2f')}  {r['digest']}")


def _print_forward_shapes(results: dict[int, dict], label: str = "workers") -> None:
    """Spec G1's rows-per-forward block. Without it a missed throughput target
    cannot be told from a scheduling artefact, and an arm whose mean rows per
    forward fell below 16 was never a valid test of the design."""
    print()
    print("rows per forward (spec G1):")
    for w in sorted(results):
        shapes = results[w].get("forward_shapes") or {}
        if not shapes.get("observable"):
            print(f"  {label}={w}: not observable — {shapes.get('note', 'no forwards recorded')}")
            continue
        print(f"  {label}={w}: forwards={shapes['forwards']} rounds={_opt(shapes['pool_rounds'], 'd')} "
              f"rows_total={shapes['rows_total']} mean={shapes['rows_per_forward_mean']:.2f} "
              f"median={shapes['rows_per_forward_median']:.1f} "
              f"p10={shapes['rows_per_forward_p10']:.1f} "
              f"min={shapes['rows_per_forward_min']} max={shapes['rows_per_forward_max']}")
        buckets = " ".join(f"{b['label']}:{b['count']}"
                           for b in shapes.get("batch_size_histogram", []))
        print(f"    histogram {buckets}")


def _fmt_gib(value) -> str:
    return "-" if value is None else f"{value / (1024 ** 3):.2f}"


def _print_full_cycle_table(results: dict[int, dict], label: str = "workers") -> None:
    """One row per (count, cycle). Per-cycle, never only an aggregate: the
    three cycles exist to expose allocator retention and optimizer-state
    growth across the iteration boundary, which an average hides."""
    print()
    print(f"{label:>10}  {'req':>5}  {'alloc':>5}  {'live':>5}  {'cyc':>3}  {'seed':>9}  "
          f"{'rows':>8}  {'opt_steps':>9}  {'collect_s':>9}  {'matches/s':>9}  "
          f"{'update_s':>8}  {'approx_kl':>9}  {'clip_frac':>9}  {'dealin+':>7}  "
          f"{'rank_cov':>8}  {'trunc':>5}  {'rss_gib':>7}  {'col_alloc':>9}  "
          f"{'col_resv':>8}  {'upd_alloc':>9}  {'upd_resv':>8}")
    for w in sorted(results):
        fc = results[w]["full_cycle"]
        for cyc in fc["cycles"]:
            print(
                f"{w:>10}  {_opt(fc.get('requested_slots'), '>5d')}  "
                f"{_opt(fc.get('allocated_slots'), '>5d')}  "
                f"{_opt(cyc.get('peak_live_slots'), '>5d')}  "
                f"{cyc['cycle']:>3}  {cyc['base_seed']:>9}  "
                f"{cyc['transition_rows']:>8}  {cyc['optimizer_steps']:>9}  "
                f"{cyc['collect_seconds']:>9.3f}  {cyc['matches_per_second']:>9.3f}  "
                f"{cyc['update_seconds']:>8.3f}  {cyc['approx_kl']:>9.5f}  "
                f"{cyc['clip_fraction']:>9.5f}  "
                f"{_opt(cyc['dealin_positive_rate'], '>7.4f')}  "
                f"{_opt(cyc['rank_label_coverage'], '>8.4f')}  "
                f"{cyc['truncated_matches']:>5}  "
                f"{_fmt_gib(cyc['host_peak_rss_bytes']):>7}  "
                f"{_fmt_gib(cyc['cuda_peak_collect_allocated_bytes']):>9}  "
                f"{_fmt_gib(cyc['cuda_peak_collect_reserved_bytes']):>8}  "
                f"{_fmt_gib(cyc['cuda_peak_update_allocated_bytes']):>9}  "
                f"{_fmt_gib(cyc['cuda_peak_update_reserved_bytes']):>8}")
        print(f"{'':>10}  phase host RSS peak: {_fmt_gib(fc['host_peak_rss_bytes'])} GiB "
              f"({fc['host_peak_rss_method']})")


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
                   help="comma-separated REQUESTED env-pool slot counts to benchmark with "
                        "--collector batched, e.g. 128,256,320. The pool allocates only "
                        "min(slots, --matches) of them (reported as allocated_slots); the "
                        "slots that actually held a match are reported as peak_live_slots")
    p.add_argument("--inference-mode", choices=("batched", "per_row"), default="batched",
                   help="--collector batched only: 'batched' (default) is the production "
                        "one-forward-per-round shape; 'per_row' forwards each row alone, "
                        "which is batch-composition-independent but far slower")
    p.add_argument("--float-ceiling", action="append", default=[], metavar="FIELD.PART=VALUE",
                   help="--collector batched --inference-mode batched only: tighten one part "
                        "of the G0.1b two-part ceiling below its device cap, e.g. "
                        "--float-ceiling values.p99_9=5e-7. FIELD is legal_logits, "
                        "old_logprobs or values; PART is p99_9 or max; a value above the cap "
                        "is rejected (the cap is never widened). --calibrate prints the exact "
                        "flags to pass here")
    p.add_argument("--calibrate", action="store_true",
                   help="--collector batched --inference-mode batched only: run the fixed "
                        "three-repeat greedy calibration block (spec G0.1b) and print the "
                        "--float-ceiling flags for a validation run on a DISJOINT seed "
                        "block. Operational threshold = 2x the worst observed statistic per "
                        "part, capped by the registered ceiling; an observed value above its "
                        "cap fails the run instead of widening the cap")
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
                   help="model the trainer's lifetime: one excluded warmup collection, then "
                        "three consecutive collect + ppo_update cycles on ONE persistent "
                        "pool/collector and ONE persistent model and optimizer, over three "
                        "consecutive seed blocks. Reports per cycle: host peak RSS, CUDA "
                        "allocated AND reserved peaks split between collection and update, "
                        "transition rows, optimizer steps, throughput, label coverage, "
                        "truncation, KL, clip fraction")
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
                   help="learning rate for the --full-cycle update's persistent optimizer")
    p.add_argument("--entropy-coef", type=float, default=fc_defaults.entropy_coef,
                   help="entropy coefficient for the --full-cycle update")
    p.add_argument("--ppo-device", type=str, default=fc_defaults.device,
                   help="device the --full-cycle update runs on (the real lap uses cuda; "
                        "ppo_update moves the whole rollout there, so this is where the "
                        "CUDA peak-memory question is answered). With --collector batched "
                        "it must equal --device: one persistent model spans both phases")
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

    # FIELD.PART=VALUE: a ceiling has two parts and a bare FIELD=VALUE would
    # silently pick one of them.
    float_ceilings: dict = {}
    for spec in args.float_ceiling:
        if "=" not in spec:
            p.error(f"--float-ceiling expects FIELD.PART=VALUE, got {spec!r}")
        key, value = spec.split("=", 1)
        if "." not in key:
            p.error(f"--float-ceiling expects FIELD.PART=VALUE with PART one of "
                    f"{'/'.join(_FLOAT_GATE_PARTS)}, got {spec!r}")
        name, part = key.rsplit(".", 1)
        try:
            float_ceilings.setdefault(name.strip(), {})[part.strip()] = float(value)
        except ValueError:
            p.error(f"--float-ceiling {spec!r}: VALUE must be a number")
    batched_float_mode = args.collector == "batched" and args.inference_mode == "batched"
    if float_ceilings and not batched_float_mode:
        p.error("--float-ceiling applies only to --collector batched --inference-mode batched")
    if args.calibrate and not batched_float_mode:
        p.error("--calibrate applies only to --collector batched --inference-mode batched")
    try:
        float_gate_ceilings(args.device, float_ceilings)
    except ValueError as exc:
        p.error(str(exc))

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
                       inference_mode=args.inference_mode,
                       float_ceilings=float_ceilings, calibrate=args.calibrate)
    results = report["results"]
    label = "pool_slots" if args.collector == "batched" else "workers"
    _print_table(results, label)
    _print_forward_shapes(results, label)
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
        # Production batched inference, SAMPLED: a float32 rounding difference
        # can flip one action and diverge the rest of that match, so neither
        # digest is comparable across slot counts. This sweep is throughput
        # only; the gate is the greedy float_gate below.
        print("sweep_action_selection: sample (throughput only — digests are NOT "
              "compared across slot counts; the gate is the greedy float_gate)")
        print(f"semantic_digests_equal (reported, not gated): "
              f"{report['semantic_digests_equal']}")
        print(f"float_delta (reported, not gated): max_abs_diff="
              f"{report['max_float_diff']:.3e}, elements outside "
              f"atol={_FLOAT_INVARIANCE_TOL['atol']}/rtol={_FLOAT_INVARIANCE_TOL['rtol']}: "
              f"{report['float_allclose_violations']}")
        print(f"semantics_equal: {report['semantics_equal']}")
        if not report["semantic_digests_equal"]:
            _print_groups("semantic_digest")
    ok = report["all_digests_equal"] if exact_expected else True
    float_gate = report.get("float_gate")
    if float_gate is not None:
        # Spec G0.1b: per field, per slot count, GREEDY, against the greedy
        # per_row reference on the same seeds. Never one collapsed maximum,
        # and never sampled.
        ceilings = float_gate["ceilings"]
        print(f"float_gate (reference: {float_gate['reference']}, "
              f"action_selection={float_gate['action_selection']} -- "
              f"{float_gate['reference_description']}; "
              f"reference_seconds={float_gate['reference_seconds']:.3f}) ceilings: "
              + " ".join(f"{k}=(p99.9 {v['p99_9']:.1e}, max {v['max']:.1e})"
                         for k, v in ceilings.items()))
        print(f"  NOTE: {float_gate['reference_note']}")
        for count in sorted(float_gate["comparisons"]):
            comp = float_gate["comparisons"][count]
            for name in _FLOAT_GATE_FIELDS:
                print(_format_float_stats(f"pool_slots={count}", name, comp["fields"][name]))
            print(f"  pool_slots={count} repeats={comp['repeats']} "
                  f"semantic_matches_reference: {comp['semantic_matches_reference']}")
        calibration = float_gate.get("calibration")
        if calibration is not None:
            print(f"float_gate calibration ({calibration['repeats_per_slot_count']} greedy "
                  f"repeats per slot count, worst over all repeats and slot counts; "
                  f"operational threshold = 2x observed, capped by the registered ceiling):")
            for name in _FLOAT_GATE_FIELDS:
                print(_format_float_stats("calibration", name, calibration["worst"][name]))
            print("  pass these into a VALIDATION run on a disjoint seed block:")
            print("    " + " ".join(calibration["ceiling_flags"]))
        for line in float_gate["violations"]:
            print(f"FLOAT GATE VIOLATION: {line}")
        print(f"float_gate_passed: {float_gate['passed']}")
        ok = ok and bool(float_gate["passed"])
    if full_cycle is not None:
        print(f"rows_and_labels_equal: {report['rows_and_labels_equal']}")
        print(f"cycle_digests_equal (reported): {report['cycle_digests_equal']}")
        # Sampled batched sweeps may legitimately diverge across slot counts,
        # so rows/labels gate only where exactness is expected.
        if exact_expected:
            ok = ok and report["rows_and_labels_equal"]

    if args.json is not None:
        payload = {
            str(w): {
                "startup_seconds": r["startup_seconds"],
                "steady_seconds": r["steady_seconds"],
                "digest": r["digest"],
                "semantic_digest": r["semantic_digest"],
                "requested_slots": r.get("requested_slots"),
                "allocated_slots": r.get("allocated_slots"),
                "peak_live_slots": r.get("peak_live_slots"),
                "forward_shapes": r.get("forward_shapes"),
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
        payload["sweep_action_selection"] = report["sweep_action_selection"]
        payload["cross_count_gate"] = report["cross_count_gate"]
        payload["collector"] = args.collector
        payload["inference_mode"] = report["inference_mode"]
        payload["dispatch_chunk_matches"] = report["dispatch_chunk_matches"]
        payload["float_gate"] = (
            None if report.get("float_gate") is None else {
                **report["float_gate"],
                "comparisons": {str(k): v for k, v in report["float_gate"]["comparisons"].items()},
            })
        if full_cycle is not None:
            payload["rows_and_labels_equal"] = report["rows_and_labels_equal"]
            payload["cycle_digests_equal"] = report["cycle_digests_equal"]
        args.json.write_text(json.dumps(payload, indent=2))

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

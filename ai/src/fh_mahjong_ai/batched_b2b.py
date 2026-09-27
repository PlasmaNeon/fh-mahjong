"""Batched B2b collection: env pool + one batched forward per round.

Same round loop as `batched_selfplay.collect_selfplay_rollouts_batched`
(one pool call per round, per-match numpy RNG, seed-order emission) with
B2b's extra outputs: tail-windowed event histories, hindsight labels from
the pool's `round_outcome`, placement bonus and telemetry. Match-end
semantics come from `train_b2b._finalize_b2b_match`, shared with the
process collector; each round's log-probabilities come from
`ppo.masked_logprobs`, bit-identical per row to the process collector's
`ppo.masked_logprob`, so greedy + `per_row` output is byte-identical to
`collect_b2b_rollouts`.
"""
from __future__ import annotations

import ctypes
import logging
import mmap
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Optional

import numpy as np
import torch

from .config import EnvConfig
from .envpool import PoolCommand, PoolStepResult, make_selfplay_pool
from .model import PolicyValueNet
from .ppo import PPOConfig, RolloutBatch, masked_logprobs
from .train_b2b import (
    _B2B_ROW_KEYS, _B2bMatchState, _check_chongci_outcomes, _finalize_b2b_match,
)

logger = logging.getLogger(__name__)


def make_b2b_pool(env_config: EnvConfig, model: PolicyValueNet, config: PPOConfig, slots: int):
    """Pool whose EnvConfig matches the one `collect_b2b_rollouts` builds:
    oracle observation on, event window bound to the model's."""
    window = int(model.model_config.event_window)
    b2b_env = replace(env_config, oracle_observation=True, event_history_window=window)
    pool = make_selfplay_pool(b2b_env, config, slots)
    if int(pool.env_config.event_history_window) != window:
        pool.close()
        raise RuntimeError(
            f"pool event_history_window {pool.env_config.event_history_window} != "
            f"model event_window {window}")
    if not pool.env_config.oracle_observation:
        pool.close()
        raise RuntimeError("B2b pool must use oracle_observation=True")
    return pool


# EnvConfig fields `make_selfplay_pool` copies verbatim from the caller's
# config. `oracle_observation` and `event_history_window` are deliberately
# absent: `make_b2b_pool` OVERRIDES both (oracle on, window bound to the
# model's), and each has its own dedicated check.
_POOL_PASSTHROUGH_FIELDS = (
    "action_space_size", "plane_shape", "scalar_features", "bridge_kind",
    "bridge_library_path", "chongci_starting_score", "chongci_bust_threshold",
    "chongci_max_hands",
)


def _assert_pool_matches_caller(cfg: EnvConfig, env_config: EnvConfig, config: PPOConfig) -> None:
    """Fail closed when the pool was built from a different EnvConfig than the
    caller passed in. Everything downstream reads `pool.env_config`, so a
    disagreement would silently collect under one simulation while the caller
    (telemetry, labels, resume echo) believes another."""
    for name in _POOL_PASSTHROUGH_FIELDS:
        pool_value, caller_value = getattr(cfg, name), getattr(env_config, name)
        if pool_value != caller_value:
            raise RuntimeError(
                f"env pool was built from a different EnvConfig: {name} is "
                f"{pool_value!r} on the pool, {caller_value!r} on the config passed to "
                "collect_b2b_rollouts_batched (build the pool with make_b2b_pool from "
                "the SAME env_config)")
    if tuple(cfg.learning_seats) != (0, 1, 2, 3):
        raise RuntimeError(
            f"B2b pool must learn all four seats, got learning_seats={cfg.learning_seats!r}")
    if cfg.auto_play_heuristics:
        raise RuntimeError("B2b pool must not auto-play heuristic seats")
    if int(cfg.max_steps_per_episode) != int(config.max_steps_per_episode):
        raise RuntimeError(
            f"pool max_steps_per_episode {cfg.max_steps_per_episode} != PPOConfig "
            f"{config.max_steps_per_episode}")
    if cfg.match_mode != config.match_mode:
        raise RuntimeError(
            f"pool match_mode {cfg.match_mode!r} != PPOConfig {config.match_mode!r}")


class _SlotMatch:
    """One in-flight match on a pool slot."""

    def __init__(self, match_index: int, base_seed: int) -> None:
        self.match_index = match_index
        self.seed = int(base_seed + match_index)
        self.sample_rng = np.random.default_rng([self.seed, 17])
        self.state = _B2bMatchState()
        self.rows: dict[str, list] | None = None   # set at finalize
        self.telemetry: dict | None = None
        self.skipped = False                        # ended at reset: emits nothing


def sample_masked_actions(logits: np.ndarray, masks: np.ndarray, temperature: float,
                          rngs: list) -> list[int]:
    """`sample_masked_action` for a whole round: row i is drawn from the
    temperature-scaled Categorical over its legal actions using ONE
    `rngs[i].random()`, exactly the draw `Generator.choice` makes, so each
    match's generator advances identically. The softmax is summed over the
    full [A] row (illegal entries contribute exact zeros) rather than the
    compacted legal subset, so a probability can differ from the per-row form
    in the last ulp; a draw can only land differently within ~1e-16 of a CDF
    boundary."""
    legal = masks > 0
    if not legal.any(axis=1).all():
        raise RuntimeError("observation has no legal actions")
    scaled = np.where(legal, logits.astype(np.float64) / max(float(temperature), 1e-6), -np.inf)
    cdf = np.exp(scaled - scaled.max(axis=1, keepdims=True)).cumsum(axis=1)
    cdf /= cdf[:, -1:]
    if not np.isfinite(cdf[:, -1]).all():
        raise ValueError("non-finite action probabilities")
    draws = np.fromiter((rng.random() for rng in rngs), dtype=np.float64, count=len(rngs))
    actions = (cdf <= draws[:, None]).sum(axis=1)  # searchsorted(cdf, u, side="right")
    if not legal[np.arange(len(actions)), actions].all():
        raise RuntimeError("sampled an illegal action")
    return actions.tolist()


class _GraphedForward:
    """The batched forward as CUDA-graph replays at bucketed batch sizes.

    The eager forward is launch-bound: ~125 kernels cost ~1.8 ms of host time
    against ~1 ms of GPU work at 320 rows, once per round. A replay is one
    launch. Rows are padded up to the next multiple of `BUCKET` (pad rows are
    zero planes, a zero mask and zero event length; every op is row-wise in
    eval mode, so pad rows reach no real row's output) -- a batch-composition
    change, the float class G0.1b bounds.

    Built per collection call and dropped with it: a captured graph bakes in
    the parameter storage, the TF32/cuDNN algorithm choice and the eval mode
    in force when it was captured, so it must never outlive the call that
    captured it (the float gate pins fp32 around its own collections)."""

    BUCKET = 32

    def __init__(self, model: PolicyValueNet, device, max_rows: int) -> None:
        self.model = model
        self.device = torch.device(device)
        self.capacity = -(-int(max_rows) // self.BUCKET) * self.BUCKET
        self._graphs: dict[int, tuple] = {}
        self._pool = torch.cuda.graph_pool_handle()
        self._static: Optional[tuple] = None
        self._staging: Optional[tuple] = None

    def _allocate(self, planes, scalars, masks, events) -> None:
        cap = self.capacity
        shapes_dtypes = ((planes.shape[1:], torch.float32), (scalars.shape[1:], torch.float32),
                         (masks.shape[1:], torch.int8), (events.shape[1:], torch.int64),
                         ((), torch.int64))
        self._static = tuple(torch.zeros((cap, *shape), dtype=dtype, device=self.device)
                             for shape, dtype in shapes_dtypes)
        self._staging = tuple(torch.zeros((cap, *shape), dtype=dtype).pin_memory()
                              for shape, dtype in shapes_dtypes)

    def _capture(self, b: int):
        inputs = [t[:b] for t in self._static]
        side = torch.cuda.Stream(self.device)
        side.wait_stream(torch.cuda.current_stream(self.device))
        with torch.cuda.stream(side), torch.no_grad():
            for _ in range(3):  # warmup: cuDNN autotuning and lazy init happen here
                self.model(*inputs[:3], events=inputs[3], event_lengths=inputs[4])
        torch.cuda.current_stream(self.device).wait_stream(side)
        graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph, pool=self._pool), torch.no_grad():
            logits, values = self.model(*inputs[:3], events=inputs[3], event_lengths=inputs[4])
            out = torch.cat([logits, values.reshape(b, 1)], dim=1)
        self._graphs[b] = (graph, out)
        return self._graphs[b]

    def __call__(self, planes: np.ndarray, scalars: np.ndarray, masks: np.ndarray,
                 events: np.ndarray, lengths: np.ndarray) -> torch.Tensor:
        """Host [n, A+1] tensor: masked logits then value, for the n rows."""
        return self.fetch(self.launch(planes, scalars, masks, events, lengths))

    @staticmethod
    def fetch(launched: torch.Tensor) -> torch.Tensor:
        """Wait for a `launch` and copy its rows to the host. Until this returns,
        the same instance must not `launch` again (its staging buffers are in use)."""
        # .cpu() synchronises the stream, so the staging buffers are free for
        # the next call's writes.
        return launched.cpu()

    def launch(self, planes: np.ndarray, scalars: np.ndarray, masks: np.ndarray,
               events: np.ndarray, lengths: np.ndarray) -> torch.Tensor:
        """Queue the forward for the n rows and return the device [n, A+1]
        output without waiting for it."""
        n = planes.shape[0]
        if n > self.capacity:
            raise RuntimeError(f"{n} rows exceed the graphed forward's capacity {self.capacity}")
        if self._static is None:
            self._allocate(planes, scalars, masks, events)
        b = -(-n // self.BUCKET) * self.BUCKET
        graph, out = self._graphs.get(b) or self._capture(b)
        for host, stage, static in zip((planes, scalars, masks, events, lengths),
                                       self._staging, self._static):
            staged = stage.numpy()
            staged[:n] = host
            staged[n:b] = 0
            static[:b].copy_(stage[:b], non_blocking=True)
        graph.replay()
        return out[:n]


# Spec G1's phase split. A mid-range throughput result -- say 6x -- is
# uninterpretable without it: 6x could be a scheduling artefact (the forward
# never got big enough), a pool/FFI bound, or a per-decision Python floor that
# no amount of batching removes, and those three have different verdicts. The
# spec's "tunable versus falsified" rule reads straight off these numbers, so
# collecting them only after the fact would cost a second GPU booking.
_PHASE_TIMER_NOTE = (
    "pool_seconds: pool.step/reset -- the FFI call plus the protobuf marshal and parse "
    "(~2.7 MB of planes per round at 320 live rows). "
    "forward_seconds: host->device staging, the forward (a CUDA-graph replay, or the "
    "eager model(...) call off CUDA) and the single device->host transfer, deliberately "
    "spanning all three -- CUDA work is asynchronous, so a timer around the launch alone "
    "would read near zero and charge the forward to whichever later operation happens "
    "to synchronise. "
    "python_seconds: the decision step ONLY -- action choice (per-row sampling with "
    "each match's RNG, or one argmax), one masked_logprobs call for the round, and "
    "appending each row to its match state. "
    "other_seconds = total - pool - forward - python: per-slot bookkeeping, one copy of "
    "the round's live rows, match finalisation and the seed-order flush. "
    "Reported as a residual rather than folded into one of the three, so no timer is "
    "inflated by work that is not what its name says.")


_libc = None


def release_freed_heap() -> bool:
    """Return freed heap pages to the OS (glibc ``malloc_trim(0)``).

    Per-round arrays are a few MB and glibc raises its mmap threshold to the
    size of each mmapped chunk it frees, so after the first rounds they come
    from the brk heap, and freeing them returns nothing to the OS. Called once
    a collection has emitted every match, so the heap high-water mark of
    pinned rounds does not stay resident through the update. Pinning the
    threshold instead cost ~9 s per 320-match collection in page faults. A
    no-op off Linux/glibc; returns whether memory was trimmed.
    """
    global _libc
    if not sys.platform.startswith("linux"):
        return False
    try:
        if _libc is None:
            _libc = ctypes.CDLL("libc.so.6")
        return bool(_libc.malloc_trim(0))
    except (OSError, AttributeError):
        return False


# Row keys whose per-decision entries are arrays, and the batch dtype of each.
_ARRAY_ROW_DTYPES = {"planes": np.float32, "scalars": np.float32,
                     "masks": np.int8, "events": np.uint32}


def _lazy_empty(shape: tuple, dtype) -> np.ndarray:
    """An uninitialized array whose pages are committed only when written.

    On Linux it is an anonymous ``MAP_NORESERVE`` mapping, so an upper-bound
    size far beyond what gets written is not refused by the default overcommit
    heuristic (which rejects a single allocation larger than RAM plus swap).
    Elsewhere it is ``np.empty``, which is also lazily committed for large sizes.
    The mapping is unmapped when the last view of the array is released.
    """
    dtype = np.dtype(dtype)
    nbytes = int(np.prod(shape, dtype=np.int64)) * dtype.itemsize
    noreserve = getattr(mmap, "MAP_NORESERVE", None)
    anonymous = getattr(mmap, "MAP_ANONYMOUS", None)
    if nbytes == 0 or noreserve is None or anonymous is None:
        return np.empty(shape, dtype=dtype)
    try:
        buf = mmap.mmap(-1, nbytes, flags=mmap.MAP_PRIVATE | anonymous | noreserve)
    except (OSError, ValueError):
        # Strict overcommit (vm.overcommit_memory=2) ignores MAP_NORESERVE and
        # can refuse the reservation; np.empty is the same request by another route.
        return np.empty(shape, dtype=dtype)
    return np.frombuffer(buf, dtype=dtype).reshape(shape)


class _ArrayRowSink:
    """Batch buffers that each emitted match is written into once, at its final offset.

    Sized to the hard upper bound (``capacity`` rows = matches x the per-match
    step cap) but committed lazily (``_lazy_empty``), so resident memory is the
    rows actually written. Writing at emission releases a
    match's row views as it goes, so a round array is freed once every match
    holding one of its rows has been emitted, and the batch is built with a
    single copy. Stacking all views at the end instead held the rows and the
    batch at once: a 960-match 192x24 collection went from ~21 GiB to past the
    38 GiB guard at assembly.
    """

    def __init__(self, capacity: int) -> None:
        self.capacity = int(capacity)
        self.rows = 0
        self.buffers: dict[str, np.ndarray] = {}

    def write(self, match_rows: dict[str, list]) -> None:
        n = len(match_rows["actions"])
        if n == 0:
            return
        if self.rows + n > self.capacity:
            raise RuntimeError(f"batched B2b rows exceed the sink capacity "
                               f"({self.rows} + {n} > {self.capacity})")
        for key, dtype in _ARRAY_ROW_DTYPES.items():
            rows = match_rows[key]
            if len(rows) != n:
                raise RuntimeError(f"match has {len(rows)} {key} rows but {n} actions")
            if key not in self.buffers:
                self.buffers[key] = _lazy_empty((self.capacity,) + np.shape(rows[0]), dtype)
            np.stack(rows, out=self.buffers[key][self.rows:self.rows + n])
        self.rows += n

    def arrays(self) -> dict[str, np.ndarray]:
        """The written prefix of each buffer (C-contiguous views)."""
        return {key: buf[:self.rows] for key, buf in self.buffers.items()}


def _collect_pipelined(groups: int, commands_for, group_slots: list, timed_step, observe,
                       launch_forward, finish_round, wedged, unemitted) -> None:
    """The turn loop for `pool_pipeline_groups > 1`.

    Group g's turn: take its pool step, settle it, read back group g-1's forward
    (it ran on the GPU during this step) and decide g-1's actions, then queue g's
    forward. Pool steps run one at a time on a single worker thread, in the same
    group order and with the same commands as a serial loop, so the output does
    not depend on the threading: the thread only lets the Go step (which
    releases the GIL) overlap Python. The next group's step is started as soon as
    its actions are decided -- at the top of the turn when its forward is not in
    flight (three or more groups), else right after it is read back."""
    in_flight: list = [None] * groups  # (pending_rows, masks_r, launched) per group
    stepper = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fh-pool-step")

    def submit(group: int):
        commands = commands_for(group_slots[group])
        return stepper.submit(timed_step, commands) if commands else None

    try:
        group = 0
        step_future = submit(0)
        idle_turns = 0
        while unemitted() or step_future is not None or any(f is not None for f in in_flight):
            stepped = step_future.result() if step_future is not None else None
            nxt = (group + 1) % groups
            early = in_flight[nxt] is None
            step_future = submit(nxt) if early else None
            observed = observe(stepped) if stepped is not None else None
            previous = (group - 1) % groups
            if in_flight[previous] is not None:
                finish_round(*in_flight[previous])
                in_flight[previous] = None
            if not early:
                step_future = submit(nxt)
            if observed is not None:
                pending_rows, arrays = observed
                in_flight[group] = (pending_rows, arrays[2], launch_forward(group, arrays))
            idle_turns = 0 if stepped is not None else idle_turns + 1
            if idle_turns > groups and unemitted():
                raise wedged()
            group = nxt
    finally:
        stepper.shutdown(wait=True)


def collect_b2b_rollouts_batched(env_config: EnvConfig, model: PolicyValueNet,
                                 config: PPOConfig, base_seed: int, pool,
                                 inference_mode: str = "batched",
                                 action_selection: str = "sample",
                                 diagnostics: Optional[dict] = None) -> RolloutBatch:
    """`env_config` is the caller's view of the simulation; the pool's own
    `pool.env_config` is what actually runs, and the two are asserted
    compatible up front (`_assert_pool_matches_caller`).

    `diagnostics` (tests and `fh-mj-collect-bench` only) receives
    `pool_slots` (allocated), `effective_slots`, `peak_live_slots`, `rounds`,
    `forward_rows` (live rows per forward, padding excluded; 1 per row under
    `per_row`), `skipped_matches`, `match_rows` and `timers` (see
    `_PHASE_TIMER_NOTE`);
    if the caller pre-creates `diagnostics["logits"]` as a list, every
    decision's masked logits row is appended to it as
    `(match_seed, seat, np.ndarray[A])` in decision order (gate G0.1b).

    `match_rows` is `[[match_seed, emitted_rows], ...]` in EMISSION order —
    the per-match row attribution the bench's sampled-sweep sanity check
    gates on (a row credited to the wrong match is invisible to every other
    check under sampling, because sampled digests are not comparable across
    slot counts). `skipped_matches` counts matches that ended at reset and so
    emitted neither rows nor telemetry."""
    # cuDNN autotuning: the per-round batch size drifts (1..slots), and the
    # heuristic algorithm choice for these small (H=42, W=1) convolutions is
    # ~1.8x slower than the tuned one at production batch sizes. Each new batch
    # size is tuned once per process (~20 s over a first 320-slot
    # collection), then cached. Tuning picks by timing, so the chosen
    # algorithms -- and hence batched-mode floats -- can differ between
    # processes; that is the same float class G0.1b already bounds for batch
    # composition, and greedy + per_row stays byte-exact.
    previous = torch.backends.cudnn.benchmark
    torch.backends.cudnn.benchmark = True
    try:
        return _collect_b2b_rollouts_batched(env_config, model, config, base_seed, pool,
                                             inference_mode, action_selection, diagnostics)
    finally:
        torch.backends.cudnn.benchmark = previous


def _collect_b2b_rollouts_batched(env_config: EnvConfig, model: PolicyValueNet,
                                  config: PPOConfig, base_seed: int, pool,
                                  inference_mode: str, action_selection: str,
                                  diagnostics: Optional[dict]) -> RolloutBatch:
    if inference_mode not in ("batched", "per_row"):
        raise ValueError(f"unknown inference_mode: {inference_mode}")
    if action_selection not in ("sample", "greedy"):
        raise ValueError(f"action_selection must be 'sample' or 'greedy', got {action_selection!r}")
    cfg: EnvConfig = pool.env_config
    window = int(model.model_config.event_window)
    if int(cfg.event_history_window) != window:
        raise RuntimeError(
            f"pool event_history_window {cfg.event_history_window} != model event_window {window}")
    if not cfg.oracle_observation:
        raise RuntimeError("B2b pool must use oracle_observation=True")
    # `env_config` is otherwise unused -- every read below goes through
    # `pool.env_config` -- so without this it would be possible to pass a
    # config that disagrees with the pool's and never find out.
    _assert_pool_matches_caller(cfg, env_config, config)
    total = int(config.matches_per_iter)
    device = config.device
    temperature = config.sample_temperature
    chongci = config.match_mode == "chongci"
    bonus_on = config.placement_bonus_values is not None
    effective_slots = min(int(pool.slots), total)
    logger.info("batched B2b collector: pool_slots=%d matches=%d effective_slots=%d "
                "inference_mode=%s", pool.slots, total, effective_slots, inference_mode)
    model.eval()
    logits_sink = diagnostics.get("logits") if diagnostics is not None else None
    peak_live_slots = 0
    forward_rows: list[int] = []
    rounds = 0
    # See `_PHASE_TIMER_NOTE`. Accumulated unconditionally, not behind
    # `diagnostics`: a handful of perf_counter calls per ROUND (never per row)
    # is far below measurement noise, and making them conditional would mean
    # the timed path and the production path were not the same path.
    pool_seconds = 0.0
    forward_seconds = 0.0
    python_seconds = 0.0
    collect_start = time.perf_counter()

    active: dict[int, _SlotMatch] = {}
    pending_action: dict[int, int] = {}
    completed: dict[int, _SlotMatch] = {}
    next_match = 0
    emit_next = 0
    rows_l: dict[str, list] = {key: [] for key in _B2B_ROW_KEYS if key not in _ARRAY_ROW_DTYPES}
    # A match emits at most one row per step, so matches x step cap bounds the batch.
    sink = _ArrayRowSink(total * int(config.max_steps_per_episode))
    match_telemetry: list[dict] = []
    truncated_matches = 0
    completed_matches = 0
    outcomes_seen = 0
    # Per-match row attribution in EMISSION order, plus the count of matches
    # that ended at reset (those emit neither rows nor telemetry, exactly as
    # the process collector skips them). Under sampling this is the only thing
    # that can catch rows credited to the wrong match: sampled digests are not
    # comparable across slot counts, so nothing else looks at the mapping.
    match_rows: list[tuple[int, int]] = []
    skipped_matches = 0

    def flush_in_seed_order() -> None:
        nonlocal emit_next, skipped_matches
        while emit_next in completed:
            sm = completed.pop(emit_next)
            emit_next += 1
            if sm.skipped:
                skipped_matches += 1
                continue
            sink.write(sm.rows)
            for key in _B2B_ROW_KEYS:
                if key not in _ARRAY_ROW_DTYPES:
                    rows_l[key].extend(sm.rows[key])
            match_rows.append((sm.seed, len(sm.rows["actions"])))
            match_telemetry.append(sm.telemetry)

    groups = int(config.pool_pipeline_groups)
    if groups < 1:
        raise ValueError(f"pool_pipeline_groups must be >= 1, got {groups}")
    groups = min(groups, effective_slots)
    # Slot g, g+groups, g+2*groups, ... belong to group g. With one group every
    # round steps every slot and runs one forward (the default). With more, the
    # groups take turns: while the GPU runs one group's forward, the pool steps
    # the next group, so Go stepping and the forward overlap. Which rows share a
    # forward changes -- the batch-composition float class -- so the group count
    # is part of the lineage, like pool_slots.
    group_slots = [list(range(g, effective_slots, groups)) for g in range(groups)]
    use_graphs = inference_mode == "batched" and torch.device(device).type == "cuda"
    graphed = [(_GraphedForward(model, device, len(slots)) if use_graphs else None)
               for slots in group_slots]

    def commands_for(slots: list[int]) -> list:
        nonlocal next_match
        commands = []
        for slot in slots:
            if slot in pending_action:
                commands.append(PoolCommand(slot=slot, action_id=pending_action.pop(slot)))
            elif slot not in active and next_match < total:
                sm = _SlotMatch(next_match, base_seed)
                next_match += 1
                active[slot] = sm
                commands.append(PoolCommand(slot=slot, reset_seed=sm.seed))
        return commands

    def timed_step(commands: list) -> tuple:
        """`pool.step` and its wall time. Runs on the stepping thread when
        groups > 1, so it touches nothing but the pool."""
        pool_start = time.perf_counter()
        result = pool.step(commands)
        return result, time.perf_counter() - pool_start

    def step_and_observe(commands: list):
        return observe(timed_step(commands))

    def observe(stepped: tuple):
        """Settle every stepped slot's bookkeeping; returns the round's live
        rows (or None) as the arrays the forward consumes."""
        nonlocal pool_seconds, rounds, peak_live_slots, truncated_matches
        nonlocal completed_matches, outcomes_seen
        result: PoolStepResult
        result, seconds = stepped
        pool_seconds += seconds
        rounds += 1
        peak_live_slots = max(peak_live_slots, len(active))

        live = []  # (slot, sm, seat, pool row)
        for meta in result.slots:
            sm = active.get(meta.slot)
            if sm is None:
                continue
            if meta.error:
                raise RuntimeError(
                    f"env pool slot {meta.slot} (match seed {sm.seed}) failed: {meta.error}")
            ms = sm.state
            if (meta.terminated or meta.truncated) and not any(ms.seat_actions):
                # Ended at reset (no decision was ever taken): the process
                # collector skips such a match entirely — no rows, no telemetry.
                if bonus_on:
                    raise RuntimeError(
                        f"placement bonus: match seed {sm.seed} ended at reset "
                        "(no four-seat terminal standing) — fail closed")
                del active[meta.slot]
                sm.skipped = True
                completed[sm.match_index] = sm
                continue
            ms.credit_step_rewards(meta.step_rewards)
            if ms.record_outcome(meta.round_outcome):
                outcomes_seen += 1
            if meta.terminated or meta.truncated:
                del active[meta.slot]
                ms.truncated = bool(meta.truncated)
                if ms.truncated:
                    truncated_matches += 1
                else:
                    completed_matches += 1
                sm.rows, sm.telemetry = _finalize_b2b_match(ms, config, cfg, sm.seed)
                sm.state = None
                completed[sm.match_index] = sm
                continue
            if not meta.has_observation:
                continue
            live.append((meta.slot, sm, int(meta.seat), result.row_of_slot[meta.slot]))
        flush_in_seed_order()
        if not live:
            return None

        # ONE writable copy of the round's live rows per array; every decision
        # keeps views into these until its match is emitted into the sink, so a
        # round array is freed once every match holding one of its rows has been
        # emitted. (A match still running pins every round it was live in either
        # way: it makes a decision in each.)
        # Event rows are the pool's (rows, window) grid: newest events
        # oldest-first, zero-padded, with the kept count alongside.
        idx = np.fromiter((entry[3] for entry in live), dtype=np.int64, count=len(live))
        planes_r = np.ascontiguousarray(result.planes[idx], dtype=np.float32)
        scalars_r = np.ascontiguousarray(result.scalars[idx], dtype=np.float32)
        masks_r = np.ascontiguousarray(result.action_masks[idx], dtype=np.int8)
        if window > 0:
            events_r = np.ascontiguousarray(result.event_grid[idx], dtype=np.uint32)
            lengths_r = np.asarray(result.event_counts, dtype=np.int64)[idx]
        else:
            events_r = np.zeros((len(live), 0), dtype=np.uint32)
            lengths_r = np.zeros(len(live), dtype=np.int64)
        pending_rows = [
            (slot, sm, seat, planes_r[i], scalars_r[i], masks_r[i], events_r[i], int(lengths_r[i]))
            for i, (slot, sm, seat, _) in enumerate(live)]
        return pending_rows, (planes_r, scalars_r, masks_r, events_r, lengths_r)

    def launch_forward(group: int, arrays: tuple):
        """Queue (graphed) or run the round's forward. Returns what
        `finish_round` needs to read the logits and values back."""
        nonlocal forward_seconds
        planes_r, scalars_r, masks_r, events_r, lengths_r = arrays
        n = planes_r.shape[0]
        if inference_mode == "batched":
            forward_rows.append(n)
        else:
            forward_rows.extend([1] * n)
        forward_start = time.perf_counter()
        launched = None
        if graphed[group] is not None:
            launched = graphed[group].launch(*arrays)
        elif inference_mode == "batched":
            with torch.no_grad():
                logits_t, values_t = model(
                    torch.from_numpy(planes_r).to(device), torch.from_numpy(scalars_r).to(device),
                    torch.from_numpy(masks_r).to(device),
                    events=torch.from_numpy(events_r.astype(np.int64)).to(device),
                    event_lengths=torch.from_numpy(lengths_r).to(device))
                launched = torch.cat([logits_t, values_t.reshape(n, 1)], dim=1).cpu()
        forward_seconds += time.perf_counter() - forward_start
        return launched

    def finish_round(pending_rows: list, masks_r: np.ndarray, launched) -> None:
        nonlocal forward_seconds, python_seconds
        # ONE device->host transfer per round: logits and values are
        # concatenated on the device into a single [B, A+1] tensor and copied
        # once, then sliced on the host. Every op below (sampling,
        # masked_logprobs) runs on CPU tensors; per-row `.item()`/log_prob on
        # device tensors would be one CUDA sync per decision, which is exactly
        # the batch-1 shape this collector exists to remove. Concatenation and
        # slicing copy bytes, so the floats are the ones the forward produced.
        #
        # The cat REQUIRES logits and values to share a dtype: enabling AMP on
        # this forward (values fp32, logits fp16, or vice versa) would make
        # torch.cat raise, or promote and change the bytes. Split the transfer
        # before adding AMP here.
        forward_start = time.perf_counter()
        if inference_mode == "batched":
            host = _GraphedForward.fetch(launched) if launched.is_cuda else launched
            # .contiguous(): every row reduced by masked_logprobs must be a
            # contiguous [A] run, exactly as the per-row form saw it.
            logits_host = host[:, :-1].contiguous()
            values_rows = host[:, -1].numpy().astype(np.float32).tolist()
        else:  # per_row: batch-composition-independent floats
            logits_list, values_rows = [], []
            for _, _, _, planes_np, scalars_np, mask_np, row_events, ev_len in pending_rows:
                with torch.no_grad():
                    logits_1, value_1 = model(
                        torch.from_numpy(planes_np).unsqueeze(0).to(device),
                        torch.from_numpy(scalars_np).unsqueeze(0).to(device),
                        torch.from_numpy(mask_np).unsqueeze(0).to(device),
                        events=torch.from_numpy(row_events.astype(np.int64)).unsqueeze(0).to(device),
                        event_lengths=torch.tensor([ev_len], dtype=torch.int64, device=device),
                    )
                logits_list.append(logits_1[0].detach().cpu())
                values_rows.append(float(value_1.reshape(-1)[0].item()))
            logits_host = torch.stack(logits_list)
        forward_seconds += time.perf_counter() - forward_start

        # Action choice and old_logprobs for the whole round at once. Greedy
        # argmax and masked_logprobs are row-wise and bit-identical to their
        # per-row forms; sampling draws once per row from each match's own
        # RNG stream.
        python_start = time.perf_counter()
        if action_selection == "greedy":
            actions = torch.argmax(logits_host, dim=1).tolist()
        else:
            actions = sample_masked_actions(logits_host.numpy(), masks_r, temperature,
                                            [row[1].sample_rng for row in pending_rows])
        with torch.no_grad():
            logprobs = masked_logprobs(logits_host, temperature, actions)
        if logits_sink is not None:
            logits_sink.extend((row[1].seed, row[2], logits_host[i].numpy().copy())
                               for i, row in enumerate(pending_rows))
        for i, (slot, sm, seat, planes_np, scalars_np, mask_np, row_events, ev_len) \
                in enumerate(pending_rows):
            action = actions[i]
            ms = sm.state
            ms.seat_planes[seat].append(planes_np)
            ms.seat_scalars[seat].append(scalars_np)
            ms.seat_masks[seat].append(mask_np)
            ms.seat_actions[seat].append(action)
            ms.seat_logprobs[seat].append(logprobs[i])
            ms.seat_values[seat].append(values_rows[i])
            ms.seat_rewards[seat].append(0.0)
            ms.seat_events[seat].append(row_events)
            ms.seat_lengths[seat].append(ev_len)
            ms.seat_hand_ids[seat].append(ms.hand_id)
            pending_action[slot] = action
        python_seconds += time.perf_counter() - python_start

    def wedged() -> RuntimeError:
        return RuntimeError(f"env pool wedged: {len(active)} slots active, "
                            f"{total - emit_next} matches unemitted")

    if groups == 1:
        while emit_next < total:
            commands = commands_for(group_slots[0])
            if not commands:
                raise wedged()
            observed = step_and_observe(commands)
            if observed is not None:
                pending_rows, arrays = observed
                finish_round(pending_rows, arrays[2], launch_forward(0, arrays))
    else:
        _collect_pipelined(groups, commands_for, group_slots, timed_step, observe,
                           launch_forward, finish_round, wedged,
                           lambda: emit_next < total)

    # NOT the outer collection wall time: this stops before the RolloutBatch
    # np.stack/astype assembly below, which the caller's `collect_seconds` does
    # include (~1-2% of outer). Phase fractions quoted against a spec threshold
    # written in terms of collection wall time must be reconciled to the OUTER
    # denominator, not to this one.
    total_seconds = time.perf_counter() - collect_start
    _check_chongci_outcomes(chongci, completed_matches, outcomes_seen)
    if diagnostics is not None:
        diagnostics.update(pool_slots=int(pool.slots), effective_slots=effective_slots,
                           peak_live_slots=peak_live_slots, rounds=rounds,
                           forward_rows=forward_rows,
                           skipped_matches=skipped_matches,
                           match_rows=[[int(seed), int(n)] for seed, n in match_rows],
                           timers={
                               "pool_seconds": pool_seconds,
                               "forward_seconds": forward_seconds,
                               "python_seconds": python_seconds,
                               "other_seconds": (total_seconds - pool_seconds
                                                 - forward_seconds - python_seconds),
                               "total_seconds": total_seconds,
                               "note": _PHASE_TIMER_NOTE,
                           })
    if not rows_l["actions"]:
        raise RuntimeError("collect_b2b_rollouts_batched produced no decisions")
    release_freed_heap()
    arrays = sink.arrays()
    return RolloutBatch(
        planes=arrays["planes"],
        scalars=arrays["scalars"],
        action_mask=arrays["masks"],
        actions=np.asarray(rows_l["actions"], dtype=np.int64),
        old_logprobs=np.asarray(rows_l["logprobs"], dtype=np.float32),
        values=np.asarray(rows_l["values"], dtype=np.float32),
        rewards=np.asarray(rows_l["rewards"], dtype=np.float32),
        dones=np.asarray(rows_l["dones"], dtype=np.float32),
        truncated_matches=truncated_matches,
        events=arrays["events"],
        event_lengths=np.asarray(rows_l["lengths"], dtype=np.int32),
        dealin_labels=np.asarray(rows_l["dealin"], dtype=np.float32),
        rank_labels=np.asarray(rows_l["rank"], dtype=np.int64),
        match_telemetry=match_telemetry,
    )

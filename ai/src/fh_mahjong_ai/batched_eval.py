"""Duplicate-seat evaluation through the env pool with one batched forward per round.

The sequential evaluator (`evaluate.evaluate_duplicate_seats`) plays one match at a time
with a batch-1 forward per decision. Here each seat rotation runs every seed through one
env pool: the Go side auto-plays the three heuristic opponents, so each round returns one
learner decision per live slot, and a single forward picks every greedy action. Episodes
are recorded into the same `_SeatEvalAccumulator`, in seed order, and assembled by the same
`aggregate_duplicate_seat_reports`, so the report has the sequential evaluator's shape.

`inference_mode="per_row"` runs the forward one row at a time with the sequential
evaluator's exact tensors, which makes the whole report byte-identical to it (the
exactness test). `"batched"` (the default) is the fast path: batch composition and, on
CUDA, graph replays change floats by summation order, so a near-tied greedy argmax can
flip. Reports record the evaluator (`evaluator` field), and `fh-mj-compare` pairs only
reports with the same evaluator record.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence

import numpy as np
import torch

from .config import EnvConfig
from .envpool import GoEnvPool, InProcessEnvPool, PoolCommand
from .evaluate import (
    _SeatEvalAccumulator,
    _default_large_loss_threshold,
    _normalize_match_mode,
    _snapshot_bridge_library,
    aggregate_duplicate_seat_reports,
)
from .types import Transition

INFERENCE_MODES = ("batched", "per_row")
SYMMETRIES = ("none", "suits")


def _rewards(values) -> np.ndarray:
    """The single-env bridge's reward decoding: an empty vector reads as four zeros."""
    decoded = np.asarray(values, dtype=np.float32)
    return np.zeros(4, dtype=np.float32) if decoded.size == 0 else decoded


@dataclass
class _SlotEpisode:
    index: int
    seed: int
    fresh: bool = True
    reset_rewards: Optional[np.ndarray] = None
    episode: list = field(default_factory=list)
    choice_infos: list = field(default_factory=list)
    learner_action_ids: list = field(default_factory=list)
    pending_action: Optional[int] = None


class _GreedyForward:
    """Greedy actions for a round's live rows, batched or one row at a time.

    With `symmetry="suits"` every row is also evaluated under the five other suit
    permutations (`suit_symmetry`), each permuted copy's log-probabilities are mapped back
    to the original actions, and the greedy action maximises their mean.
    """

    def __init__(self, model, device: str, inference_mode: str, max_rows: int,
                 symmetry: str = "none") -> None:
        self.model = model
        self.device = torch.device(device)
        self.inference_mode = inference_mode
        self.symmetry = symmetry
        self.wants_events = bool(getattr(model, "wants_events", False))
        self.graphed = None
        if (inference_mode == "batched" and self.device.type == "cuda" and self.wants_events):
            from .batched_b2b import _GraphedForward
            copies = 6 if symmetry == "suits" else 1
            self.graphed = _GraphedForward(model, device, max_rows * copies)

    def _tensors(self, planes, scalars, masks, events, lengths):
        to = lambda a: torch.from_numpy(np.ascontiguousarray(a)).to(self.device)  # noqa: E731
        ev = ln = None
        if self.wants_events:
            ev, ln = to(events.astype(np.int64)), to(lengths.astype(np.int64))
        return to(planes), to(scalars), to(masks), ev, ln

    @torch.inference_mode()
    def _logits(self, planes, scalars, masks, events, lengths) -> torch.Tensor:
        """Host [n, A] masked logits for the n rows."""
        if self.inference_mode == "per_row":
            rows = []
            for i in range(planes.shape[0]):
                p, s, m, ev, ln = self._tensors(planes[i:i + 1], scalars[i:i + 1], masks[i:i + 1],
                                                events[i:i + 1], lengths[i:i + 1])
                logits, _ = self.model(p, s, m, events=ev, event_lengths=ln)
                rows.append(logits.cpu())
            return torch.cat(rows)
        if self.graphed is not None:
            host = self.graphed(planes, scalars, masks, events.astype(np.int64),
                                lengths.astype(np.int64))
            return host[:, :-1]
        p, s, m, ev, ln = self._tensors(planes, scalars, masks, events, lengths)
        logits, _ = self.model(p, s, m, events=ev, event_lengths=ln)
        return logits.cpu()

    def __call__(self, planes, scalars, masks, events, lengths) -> list[int]:
        if self.symmetry == "none":
            return torch.argmax(self._logits(planes, scalars, masks, events, lengths), dim=1).tolist()
        from .suit_symmetry import SUIT_PERMUTATIONS, permute_rows, unpermute_action_values
        n = planes.shape[0]
        views = [permute_rows(planes, scalars, masks, events, perm) for perm in SUIT_PERMUTATIONS]
        stacked = [np.concatenate(parts) for parts in zip(*views)]
        logits = self._logits(stacked[0], stacked[1], stacked[2], stacked[3],
                              np.tile(lengths, len(SUIT_PERMUTATIONS)))
        logp = torch.log_softmax(logits.double(), dim=1).numpy()
        total = np.zeros((n, logp.shape[1]), dtype=np.float64)
        for k, perm in enumerate(SUIT_PERMUTATIONS):
            total += unpermute_action_values(logp[k * n:(k + 1) * n], perm)
        total[masks == 0] = -np.inf
        return np.argmax(total, axis=1).tolist()


def _evaluate_seat(model, seeds: Sequence[int], seat: int, cfg: EnvConfig, slots: int,
                   acc: _SeatEvalAccumulator, forward: _GreedyForward,
                   timers: Dict[str, float]) -> None:
    pool = GoEnvPool(cfg, slots) if cfg.bridge_kind == "go" else InProcessEnvPool(cfg, slots)
    window = int(cfg.event_history_window)
    results: dict[int, Optional[dict]] = {}
    active: dict[int, _SlotEpisode] = {}
    next_index = 0
    total = len(seeds)
    try:
        while len(results) < total:
            commands = []
            for slot in range(pool.slots):
                st = active.get(slot)
                if st is not None:
                    if st.pending_action is not None:
                        commands.append(PoolCommand(slot=slot, action_id=st.pending_action))
                elif next_index < total:
                    st = _SlotEpisode(next_index, int(seeds[next_index]))
                    active[slot] = st
                    next_index += 1
                    commands.append(PoolCommand(slot=slot, reset_seed=st.seed))
            t0 = time.perf_counter()
            result = pool.step(commands)
            timers["pool_seconds"] += time.perf_counter() - t0
            timers["rounds"] += 1

            live: list[tuple[_SlotEpisode, int]] = []
            for meta in result.slots:
                st = active.get(meta.slot)
                if st is None:
                    continue
                if meta.error:
                    raise RuntimeError(f"env pool slot {meta.slot} (seed {st.seed}) failed: {meta.error}")
                ended = meta.terminated or meta.truncated
                if st.fresh:
                    st.fresh = False
                    st.reset_rewards = _rewards(meta.step_rewards)
                    if ended:
                        # Ended during reset autoplay: recorded exactly as the sequential
                        # evaluator records a terminal reset (no decisions, no reset term).
                        results[st.index] = {"rewards": st.reset_rewards, "episode": [],
                                             "choice_infos": [], "outcome": meta.round_outcome,
                                             "truncated": bool(meta.truncated)}
                        del active[meta.slot]
                        continue
                else:
                    info = {"round_outcome": meta.round_outcome} if meta.round_outcome is not None else {}
                    st.episode.append(Transition(
                        observation=None, action_id=st.pending_action,
                        rewards=_rewards(meta.step_rewards), next_observation=None,
                        terminated=bool(meta.terminated), truncated=bool(meta.truncated), info=info))
                    st.pending_action = None
                    if ended:
                        results[st.index] = {"rewards": _rewards(meta.step_rewards),
                                             "episode": st.episode, "choice_infos": st.choice_infos,
                                             "outcome": meta.round_outcome,
                                             "truncated": bool(meta.truncated),
                                             "reset_rewards": st.reset_rewards,
                                             "learner_action_ids": st.learner_action_ids}
                        del active[meta.slot]
                        continue
                if not meta.has_observation:
                    # The sequential evaluator abandons such a match without recording it.
                    results[st.index] = None
                    del active[meta.slot]
                    continue
                live.append((st, result.row_of_slot[meta.slot]))

            if not live:
                continue
            idx = np.fromiter((row for _, row in live), dtype=np.int64, count=len(live))
            planes = np.ascontiguousarray(result.planes[idx], dtype=np.float32)
            scalars = np.ascontiguousarray(result.scalars[idx], dtype=np.float32)
            masks = np.ascontiguousarray(result.action_masks[idx], dtype=np.int8)
            if window > 0:
                events = np.ascontiguousarray(result.event_grid[idx], dtype=np.uint32)
                lengths = np.asarray(result.event_counts, dtype=np.int64)[idx]
            else:
                events = np.zeros((len(live), 0), dtype=np.uint32)
                lengths = np.zeros(len(live), dtype=np.int64)
            t0 = time.perf_counter()
            actions = forward(planes, scalars, masks, events, lengths)
            timers["forward_seconds"] += time.perf_counter() - t0
            timers["forward_rows"] += len(live)
            for (st, _), action in zip(live, actions):
                st.pending_action = int(action)
                st.learner_action_ids.append(int(action))
                st.choice_infos.append({})
    finally:
        pool.close()

    for i in range(total):
        r = results[i]
        if r is None:
            continue
        acc.record_episode(int(seeds[i]), r["rewards"], r["episode"], r["choice_infos"], r["outcome"],
                           truncated=r["truncated"], reset_rewards=r.get("reset_rewards"),
                           learner_action_ids=r.get("learner_action_ids"))


def evaluate_duplicate_seats_batched(
    model,
    seeds: Sequence[int],
    seats: Sequence[int] = (0, 1, 2, 3),
    bridge_kind: str = "go",
    bridge_library_path: Optional[str] = None,
    device: str = "cpu",
    large_loss_threshold: Optional[float] = None,
    match_mode: str = "classic",
    chongci_starting_score: int = 2000,
    chongci_bust_threshold: int = 0,
    chongci_max_hands: int = 50,
    max_steps_per_episode: Optional[int] = None,
    oracle_observation: bool = False,
    event_history_window: int = 0,
    slots: int = 256,
    inference_mode: str = "batched",
    symmetry: str = "none",
) -> Dict[str, Any]:
    """`evaluate.evaluate_duplicate_seats` through the env pool (greedy, heuristic opponents).

    `symmetry="suits"` averages the policy over the six suit permutations (a different policy
    than the plain checkpoint); the report records it as `policy_transform`.
    """
    if inference_mode not in INFERENCE_MODES:
        raise ValueError(f"inference_mode must be one of {INFERENCE_MODES}, got {inference_mode!r}")
    if symmetry not in SYMMETRIES:
        raise ValueError(f"symmetry must be one of {SYMMETRIES}, got {symmetry!r}")
    if slots < 1:
        raise ValueError("slots must be >= 1")
    window = int(event_history_window)
    model_window = int(getattr(getattr(model, "model_config", None), "event_window", 0) or 0)
    if getattr(model, "wants_events", False) and model_window != window:
        raise ValueError(f"model event window {model_window} != event_history_window {window}")
    normalized = _normalize_match_mode(match_mode)
    threshold = (float(large_loss_threshold) if large_loss_threshold is not None
                 else _default_large_loss_threshold(normalized))
    model.eval()
    library_path, bridge_sha, snapshot = _snapshot_bridge_library(bridge_kind, bridge_library_path)
    seat_list = list(seats)
    effective_slots = min(int(slots), len(seeds)) or 1
    forward = _GreedyForward(model, device, inference_mode, effective_slots, symmetry)
    timers = {"pool_seconds": 0.0, "forward_seconds": 0.0, "rounds": 0, "forward_rows": 0}
    started = time.perf_counter()
    seat_reports = []
    try:
        for seat in seat_list:
            cfg = EnvConfig(bridge_kind=bridge_kind, bridge_library_path=library_path,
                            learning_seats=(seat,), auto_play_heuristics=True, match_mode=normalized,
                            chongci_starting_score=chongci_starting_score,
                            chongci_bust_threshold=chongci_bust_threshold,
                            chongci_max_hands=chongci_max_hands,
                            oracle_observation=oracle_observation, event_history_window=window)
            if max_steps_per_episode is not None:
                cfg.max_steps_per_episode = int(max_steps_per_episode)
            acc = _SeatEvalAccumulator(seat, normalized, threshold, chongci_starting_score,
                                       chongci_bust_threshold, chongci_max_hands)
            _evaluate_seat(model, seeds, seat, cfg, effective_slots, acc, forward, timers)
            seat_reports.append(acc.report())
    finally:
        if snapshot is not None:
            snapshot.cleanup()
    report = aggregate_duplicate_seat_reports(
        seat_reports, seeds=seeds, seat_list=seat_list, normalized_match_mode=normalized,
        chongci_starting_score=chongci_starting_score, chongci_bust_threshold=chongci_bust_threshold,
        chongci_max_hands=chongci_max_hands, max_steps_per_episode=max_steps_per_episode,
        oracle_observation=oracle_observation, event_history_window=window,
        bridge_lib_sha256=bridge_sha)
    report["evaluator"] = {"kind": "batched-pool", "slots": effective_slots,
                           "inference_mode": inference_mode}
    if symmetry != "none":
        report["policy_transform"] = {"symmetry": symmetry}
    report["evaluator_timing"] = {**timers, "wall_seconds": time.perf_counter() - started}
    return report

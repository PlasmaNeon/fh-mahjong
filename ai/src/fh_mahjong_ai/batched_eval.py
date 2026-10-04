"""Seat-rotated evaluation through the env pool with one batched forward per policy per round.

The sequential evaluator (`evaluate.evaluate_policy_online`) plays one match at a time with a
batch-1 forward per decision. Here every (seat, seed) match runs through an env pool:

- Heuristic table: the Go side auto-plays the three heuristic opponents, so each round returns
  one learner decision per live slot and one forward picks every action. The pool's learning
  seat is fixed, so each seat rotation gets its own pool.
- Strong table (`opponent_model`): all four seats are pool learning seats and one pool runs every
  seat's matches. Each round's rows split by acting seat: the candidate's rows go through its
  forward, the other seats' rows through the opponent model's. Every seat's transition is
  recorded, as the sequential strong table records them.

Episodes are tallied by the same `_SeatEvalAccumulator`, in seed order, so reports have the
sequential evaluator's shape.

`inference_mode="per_row"` runs each row through the sequential policies' exact computation
(`TorchGreedyPolicy`, and `SuitAveragedGreedyPolicy` under a symmetry), which makes the report
byte-identical to the sequential one (the exactness tests). `"batched"` (the default) is the fast
path: batch composition and, on CUDA, graph replays change floats by summation order, so a
near-tied greedy argmax can flip. Reports record the evaluator (`evaluator` field), and
`fh-mj-compare` pairs only reports with the same evaluator record.

Sampled opponents (`OpponentSampling`) draw with serving's sampler from one RNG per match, seeded
from (sample seed, learning seat, wall seed), so a report does not depend on slot scheduling. The
sequential evaluator has no sampled-opponent mode.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

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
from .serving import family_sampling_actions, sample_from_logits
from .types import Transition

INFERENCE_MODES = ("batched", "per_row")
SYMMETRIES = ("none", "suits", "faces")
VIEWS_PER_FORWARD = 6


@dataclass(frozen=True)
class OpponentSampling:
    """Serving's sampler settings for strong-table opponents (`CheckpointPolicy` semantics)."""

    temperature: float
    top_k: int = 0
    action_family: str = "all"
    seed: int = 1

    def __post_init__(self) -> None:
        if not np.isfinite(self.temperature) or self.temperature <= 0.0:
            raise ValueError("opponent sampling temperature must be finite and > 0")
        if self.top_k < 0:
            raise ValueError("opponent sampling top_k must be >= 0")

    def record(self) -> Dict[str, Any]:
        return {"temperature": float(self.temperature), "top_k": int(self.top_k),
                "action_family": self.action_family, "seed": int(self.seed),
                "rng": "per-match (seed, learning seat, wall seed)"}

    def match_rng(self, learning_seat: int, wall_seed: int) -> np.random.Generator:
        return np.random.default_rng([int(self.seed), int(learning_seat), int(wall_seed)])


def _rewards(values) -> np.ndarray:
    """The single-env bridge's reward decoding: an empty vector reads as four zeros."""
    decoded = np.asarray(values, dtype=np.float32)
    return np.zeros(4, dtype=np.float32) if decoded.size == 0 else decoded


def _model_window(model) -> int:
    if not getattr(model, "wants_events", False):
        return 0
    return int(getattr(getattr(model, "model_config", None), "event_window", 0) or 0)


def _rewindow(events: np.ndarray, lengths: np.ndarray, window: int):
    """Each row's newest min(length, window) events, oldest-first and zero-padded -- the event
    row the sequential policies build from an observation's history for a `window` model."""
    if events.shape[1] == window:
        return events, lengths
    if events.shape[1] < window:
        raise ValueError(f"table event window {events.shape[1]} is narrower than the model's {window}")
    kept = np.minimum(lengths, window)
    out = np.zeros((events.shape[0], window), dtype=events.dtype)
    for i, (n, k) in enumerate(zip(lengths.tolist(), kept.tolist())):
        if k:
            out[i, :k] = events[i, n - k:n]
    return out, kept


@dataclass
class _SlotEpisode:
    index: int
    seat: int
    seed: int
    rng: Optional[np.random.Generator] = None
    fresh: bool = True
    reset_rewards: Optional[np.ndarray] = None
    episode: list = field(default_factory=list)
    choice_infos: list = field(default_factory=list)
    learner_action_ids: list = field(default_factory=list)
    pending_action: Optional[int] = None


class _GreedyForward:
    """One policy's actions for a round's rows, batched or one row at a time.

    With `symmetry="suits"` every row is also evaluated under the five other suit
    permutations, with `symmetry="faces"` under all 72 face symmetries
    (`suit_symmetry.SYMMETRY_GROUPS`); each transformed copy's log-probabilities are mapped
    back to the original actions, and the greedy action maximises their mean
    (`suit_symmetry.suit_averaged_log_probs`). Views go through the net `VIEWS_PER_FORWARD`
    at a time, so a `faces` forward has the shape of a `suits` one (72 views x 256 slots in one
    forward does not fit a 24 GB card).

    Rows arrive with the table's event window; a model with a narrower window sees each row's
    newest events, as `TorchGreedyPolicy` builds them. With `sampling` set (symmetry "none"
    only) actions are drawn with serving's sampler from the per-row RNGs passed in.
    """

    def __init__(self, model, device: str, inference_mode: str, max_rows: int,
                 symmetry: str = "none", sampling: Optional[OpponentSampling] = None) -> None:
        if sampling is not None and symmetry != "none":
            raise ValueError("sampling supports symmetry 'none' only")
        self.model = model
        self.device = torch.device(device)
        self.inference_mode = inference_mode
        self.symmetry = symmetry
        self.sampling = sampling
        self.wants_events = bool(getattr(model, "wants_events", False))
        self.window = _model_window(model)
        self.graphed = None
        if (inference_mode == "batched" and self.device.type == "cuda" and self.wants_events):
            from .batched_b2b import _GraphedForward
            from .suit_symmetry import SYMMETRY_GROUPS
            copies = min(len(SYMMETRY_GROUPS.get(symmetry, (None,))), VIEWS_PER_FORWARD)
            self.graphed = _GraphedForward(model, device, max_rows * copies)

    def _tensors(self, planes, scalars, masks, events, lengths):
        to = lambda a: torch.from_numpy(np.ascontiguousarray(a)).to(self.device)  # noqa: E731
        ev = ln = None
        if self.wants_events:
            ev, ln = to(events.astype(np.int64)), to(lengths.astype(np.int64))
        return to(planes), to(scalars), to(masks), ev, ln

    @torch.inference_mode()
    def _forward(self, planes, scalars, masks, events, lengths) -> torch.Tensor:
        """Host [n, A] masked logits for the n rows, in one forward."""
        if self.graphed is not None:
            host = self.graphed(planes, scalars, masks, events.astype(np.int64),
                                lengths.astype(np.int64))
            return host[:, :-1]
        p, s, m, ev, ln = self._tensors(planes, scalars, masks, events, lengths)
        logits, _ = self.model(p, s, m, events=ev, event_lengths=ln)
        return logits.cpu()

    def _logits(self, planes, scalars, masks, events, lengths) -> torch.Tensor:
        if self.inference_mode == "per_row":
            return torch.cat([self._forward(planes[i:i + 1], scalars[i:i + 1], masks[i:i + 1],
                                            events[i:i + 1], lengths[i:i + 1])
                              for i in range(planes.shape[0])])
        return self._forward(planes, scalars, masks, events, lengths)

    def _averaged(self, planes, scalars, masks, events, lengths) -> np.ndarray:
        """float64 [n, A]: the mean over the views of the log-probabilities, illegal -inf."""
        from .suit_symmetry import SYMMETRY_GROUPS, stack_views, unpermute_action_values
        group = SYMMETRY_GROUPS[self.symmetry]
        n = planes.shape[0]
        total = np.zeros(masks.shape, dtype=np.float64)
        for first in range(0, len(group), VIEWS_PER_FORWARD):
            chunk = group[first:first + VIEWS_PER_FORWARD]
            p, s, m, e = stack_views(planes, scalars, masks, events, chunk)
            logits = self._forward(p, s, m, e, np.tile(lengths, len(chunk)))
            logp = torch.log_softmax(logits.double(), dim=1).numpy()
            for k, perm in enumerate(chunk):
                total += unpermute_action_values(logp[k * n:(k + 1) * n], perm)
        total /= len(group)
        total[masks == 0] = -np.inf
        return total

    def __call__(self, planes, scalars, masks, events, lengths, rngs=None) -> list[int]:
        if self.wants_events:
            events, lengths = _rewindow(events, lengths, self.window)
        if self.symmetry != "none":
            if self.inference_mode == "per_row":
                # One forward per row over its views: SuitAveragedGreedyPolicy's computation.
                total = np.concatenate([
                    self._averaged(planes[i:i + 1], scalars[i:i + 1], masks[i:i + 1],
                                   events[i:i + 1], lengths[i:i + 1])
                    for i in range(planes.shape[0])])
            else:
                total = self._averaged(planes, scalars, masks, events, lengths)
            return np.argmax(total, axis=1).tolist()
        logits = self._logits(planes, scalars, masks, events, lengths)
        greedy = torch.argmax(logits, dim=1).tolist()
        if self.sampling is None:
            return greedy
        sampling = self.sampling
        host = logits.numpy()
        actions = []
        for i, rng in enumerate(rngs):
            candidates = family_sampling_actions(np.flatnonzero(masks[i]).tolist(),
                                                 sampling.action_family)
            actions.append(sample_from_logits(host[i], candidates, sampling.temperature,
                                              sampling.top_k, rng) if candidates else greedy[i])
        return actions


def _round_rows(result, live: list[tuple[_SlotEpisode, int]], window: int):
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
    return planes, scalars, masks, events, lengths


def _play(jobs: Sequence[tuple[int, int]], cfg: EnvConfig, slots: int, forward: _GreedyForward,
          opponent: Optional[_GreedyForward], timers: Dict[str, float],
          progress: Optional[Callable[[int], None]] = None) -> list[Optional[dict]]:
    """Play every (learning seat, wall seed) job through one pool; one result per job, None for
    a match the sequential evaluator abandons without recording. Without `opponent` the pool
    returns only the learning seat's decisions (the heuristic table), so every job shares the
    pool's learning seat."""
    pool = GoEnvPool(cfg, slots) if cfg.bridge_kind == "go" else InProcessEnvPool(cfg, slots)
    window = int(cfg.event_history_window)
    sampling = opponent.sampling if opponent is not None else None
    results: dict[int, Optional[dict]] = {}
    active: dict[int, _SlotEpisode] = {}
    next_index = 0
    total = len(jobs)

    def finish(slot: int, st: _SlotEpisode, result: Optional[dict]) -> None:
        results[st.index] = result
        del active[slot]
        if progress is not None:
            progress(1)

    try:
        while len(results) < total:
            commands = []
            for slot in range(pool.slots):
                st = active.get(slot)
                if st is not None:
                    if st.pending_action is not None:
                        commands.append(PoolCommand(slot=slot, action_id=st.pending_action))
                elif next_index < total:
                    seat, seed = jobs[next_index]
                    st = _SlotEpisode(next_index, int(seat), int(seed))
                    if sampling is not None:
                        st.rng = sampling.match_rng(st.seat, st.seed)
                    active[slot] = st
                    next_index += 1
                    commands.append(PoolCommand(slot=slot, reset_seed=st.seed))
            t0 = time.perf_counter()
            result = pool.step(commands)
            timers["pool_seconds"] += time.perf_counter() - t0
            timers["rounds"] += 1

            learner: list[tuple[_SlotEpisode, int]] = []
            others: list[tuple[_SlotEpisode, int]] = []
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
                        finish(meta.slot, st, {"rewards": st.reset_rewards, "episode": [],
                                               "choice_infos": [], "outcome": meta.round_outcome,
                                               "truncated": bool(meta.truncated)})
                        continue
                else:
                    info = {"round_outcome": meta.round_outcome} if meta.round_outcome is not None else {}
                    st.episode.append(Transition(
                        observation=None, action_id=st.pending_action,
                        rewards=_rewards(meta.step_rewards), next_observation=None,
                        terminated=bool(meta.terminated), truncated=bool(meta.truncated), info=info))
                    st.pending_action = None
                    if ended:
                        finish(meta.slot, st, {"rewards": _rewards(meta.step_rewards),
                                               "episode": st.episode, "choice_infos": st.choice_infos,
                                               "outcome": meta.round_outcome,
                                               "truncated": bool(meta.truncated),
                                               "reset_rewards": st.reset_rewards,
                                               "learner_action_ids": st.learner_action_ids})
                        continue
                if not meta.has_observation:
                    # The sequential evaluator abandons such a match without recording it.
                    finish(meta.slot, st, None)
                    continue
                row = (st, result.row_of_slot[meta.slot])
                (learner if opponent is None or int(meta.seat) == st.seat else others).append(row)

            if learner:
                t0 = time.perf_counter()
                actions = forward(*_round_rows(result, learner, window))
                timers["forward_seconds"] += time.perf_counter() - t0
                timers["forward_rows"] += len(learner)
                for (st, _), action in zip(learner, actions):
                    st.pending_action = int(action)
                    st.learner_action_ids.append(int(action))
                    st.choice_infos.append({})
            if others:
                t0 = time.perf_counter()
                actions = opponent(*_round_rows(result, others, window),
                                   rngs=[st.rng for st, _ in others])
                timers["opponent_forward_seconds"] += time.perf_counter() - t0
                timers["opponent_forward_rows"] += len(others)
                for (st, _), action in zip(others, actions):
                    st.pending_action = int(action)
    finally:
        pool.close()
    return [results[i] for i in range(total)]


def _record(acc: _SeatEvalAccumulator, seeds: Sequence[int], results: Sequence[Optional[dict]]) -> None:
    for seed, r in zip(seeds, results):
        if r is None:
            continue
        acc.record_episode(int(seed), r["rewards"], r["episode"], r["choice_infos"], r["outcome"],
                           truncated=r["truncated"], reset_rewards=r.get("reset_rewards"),
                           learner_action_ids=r.get("learner_action_ids"))


def evaluate_seats_batched(
    model,
    seat_seeds: Mapping[int, Sequence[int]],
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
    lookahead_version: int = 0,
    slots: int = 256,
    inference_mode: str = "batched",
    symmetry: str = "none",
    opponent_model=None,
    opponent_sampling: Optional[OpponentSampling] = None,
    progress: Optional[Callable[[int], None]] = None,
) -> Dict[str, Any]:
    """Greedy play of `model` in each seat of `seat_seeds` ({seat: wall seeds}) through the env pool.

    Returns `seat_reports` ({seat: the `evaluate_policy_online` report for that seat and its
    seeds}), the `evaluator` record, `evaluator_timing` and `bridge_lib_sha256`. With
    `opponent_model` the other three seats play that model (greedy, or sampled with
    `opponent_sampling`) instead of the heuristic bots. `progress(n)` is called as matches end.
    """
    if inference_mode not in INFERENCE_MODES:
        raise ValueError(f"inference_mode must be one of {INFERENCE_MODES}, got {inference_mode!r}")
    if symmetry not in SYMMETRIES:
        raise ValueError(f"symmetry must be one of {SYMMETRIES}, got {symmetry!r}")
    if slots < 1:
        raise ValueError("slots must be >= 1")
    if opponent_sampling is not None and opponent_model is None:
        raise ValueError("opponent_sampling needs opponent_model")
    window = int(event_history_window)
    if getattr(model, "wants_events", False) and _model_window(model) != window:
        raise ValueError(f"model event window {_model_window(model)} != event_history_window {window}")
    if opponent_model is not None and _model_window(opponent_model) > window:
        raise ValueError(f"opponent event window {_model_window(opponent_model)} exceeds "
                         f"event_history_window {window}; its histories would be truncated")
    for role, net in (("model", model), ("opponent", opponent_model)):
        version = int(getattr(getattr(net, "model_config", None), "lookahead_version", 0) or 0)
        if net is not None and version != int(lookahead_version):
            # One env encodes every seat's observation, so all seats share the version.
            raise ValueError(f"{role} lookahead_version {version} != lookahead_version {lookahead_version}")
    normalized = _normalize_match_mode(match_mode)
    threshold = (float(large_loss_threshold) if large_loss_threshold is not None
                 else _default_large_loss_threshold(normalized))
    model.eval()
    if opponent_model is not None:
        opponent_model.eval()
    seat_list = list(seat_seeds)
    strong = opponent_model is not None
    jobs_per_pool = (sum(len(seat_seeds[s]) for s in seat_list) if strong
                     else max((len(seat_seeds[s]) for s in seat_list), default=0))
    effective_slots = min(int(slots), jobs_per_pool) or 1
    forward = _GreedyForward(model, device, inference_mode, effective_slots, symmetry)
    opponent = (_GreedyForward(opponent_model, device, inference_mode, effective_slots,
                               sampling=opponent_sampling) if strong else None)
    timers = {"pool_seconds": 0.0, "forward_seconds": 0.0, "rounds": 0, "forward_rows": 0}
    if strong:
        timers.update(opponent_forward_seconds=0.0, opponent_forward_rows=0)
    library_path, bridge_sha, snapshot = _snapshot_bridge_library(bridge_kind, bridge_library_path)

    def config(learning_seats) -> EnvConfig:
        cfg = EnvConfig(bridge_kind=bridge_kind, bridge_library_path=library_path,
                        learning_seats=tuple(learning_seats), auto_play_heuristics=not strong,
                        match_mode=normalized, chongci_starting_score=chongci_starting_score,
                        chongci_bust_threshold=chongci_bust_threshold,
                        chongci_max_hands=chongci_max_hands,
                        oracle_observation=oracle_observation, event_history_window=window,
                        lookahead_version=int(lookahead_version))
        if max_steps_per_episode is not None:
            cfg.max_steps_per_episode = int(max_steps_per_episode)
        return cfg

    started = time.perf_counter()
    results: dict[int, list[Optional[dict]]] = {}
    try:
        if strong:
            jobs = [(seat, seed) for seat in seat_list for seed in seat_seeds[seat]]
            flat = _play(jobs, config((0, 1, 2, 3)), effective_slots, forward, opponent, timers,
                         progress)
            offset = 0
            for seat in seat_list:
                results[seat] = flat[offset:offset + len(seat_seeds[seat])]
                offset += len(seat_seeds[seat])
        else:
            for seat in seat_list:
                jobs = [(seat, seed) for seed in seat_seeds[seat]]
                results[seat] = _play(jobs, config((seat,)), effective_slots, forward, None,
                                      timers, progress)
    finally:
        if snapshot is not None:
            snapshot.cleanup()
    seat_reports = {}
    for seat in seat_list:
        acc = _SeatEvalAccumulator(seat, normalized, threshold, chongci_starting_score,
                                   chongci_bust_threshold, chongci_max_hands)
        _record(acc, seat_seeds[seat], results[seat])
        seat_reports[seat] = acc.report()
    return {
        "seat_reports": seat_reports,
        "evaluator": {"kind": "batched-pool", "slots": effective_slots,
                      "inference_mode": inference_mode},
        "evaluator_timing": {**timers, "wall_seconds": time.perf_counter() - started},
        "bridge_lib_sha256": bridge_sha,
    }


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
    lookahead_version: int = 0,
    slots: int = 256,
    inference_mode: str = "batched",
    symmetry: str = "none",
    opponent_model=None,
    opponents: Optional[Dict[str, Any]] = None,
    opponent_sampling: Optional[OpponentSampling] = None,
) -> Dict[str, Any]:
    """`evaluate.evaluate_duplicate_seats` through the env pool (greedy).

    With `opponent_model` (and its identity record `opponents`, required with it) this is
    `evaluate.evaluate_duplicate_seats_policy`'s strong table, report shape included.
    `symmetry="suits"` averages the policy over the six suit permutations (a different policy
    than the plain checkpoint); the report records it as `policy_transform`.
    """
    if (opponent_model is None) != (opponents is None):
        raise ValueError("opponent_model and opponents must be given together")
    seat_list = list(seats)
    normalized = _normalize_match_mode(match_mode)
    window = int(event_history_window)
    run = evaluate_seats_batched(
        model, {seat: list(seeds) for seat in seat_list}, bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path, device=device,
        large_loss_threshold=large_loss_threshold, match_mode=normalized,
        chongci_starting_score=chongci_starting_score, chongci_bust_threshold=chongci_bust_threshold,
        chongci_max_hands=chongci_max_hands, max_steps_per_episode=max_steps_per_episode,
        oracle_observation=oracle_observation, event_history_window=window,
        lookahead_version=lookahead_version, slots=slots,
        inference_mode=inference_mode, symmetry=symmetry, opponent_model=opponent_model,
        opponent_sampling=opponent_sampling)
    report = aggregate_duplicate_seat_reports(
        [run["seat_reports"][seat] for seat in seat_list], seeds=seeds, seat_list=seat_list,
        normalized_match_mode=normalized, chongci_starting_score=chongci_starting_score,
        chongci_bust_threshold=chongci_bust_threshold, chongci_max_hands=chongci_max_hands,
        max_steps_per_episode=max_steps_per_episode, oracle_observation=oracle_observation,
        event_history_window=window, bridge_lib_sha256=run["bridge_lib_sha256"],
        policy_fields=opponent_model is not None, opponents=opponents,
        lookahead_version=int(lookahead_version))
    report["evaluator"] = run["evaluator"]
    if symmetry != "none":
        report["policy_transform"] = {"symmetry": symmetry}
    report["evaluator_timing"] = run["evaluator_timing"]
    return report

"""Tests for the determinized champion-rollout search (`search.py`).

All fakes live here; no FFI / bridge is touched. `FakeCheckpointPolicy` scripts
priors + value-head outputs keyed on a recognizable tag stored in an
observation's first scalar. `FakeSearchPool` replays a scripted per-candidate
sequence of `SlotMeta`s (clone `slot` belongs to candidate `slot // K`), which
decouples the pool's scripting from whatever action the searcher's greedy
argmax happens to pick.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pytest

from fh_mahjong_ai.envpool import PoolCommand, SlotMeta
from fh_mahjong_ai.searchpool import SearchStepResult
from fh_mahjong_ai.search import SearchConfig, SearchPolicy
from fh_mahjong_ai.types import Observation

# Small fixed dimensions shared by all fakes.
A = 5            # action-space size
C, H, W = 1, 1, 1  # plane shape
S = 2            # scalar features; scalars[0] carries the value-head tag


def _obs(seat: int, prior_tag: float, mask: Sequence[int]) -> Observation:
    planes = np.zeros((C, H, W), dtype=np.float32)
    scalars = np.zeros((S,), dtype=np.float32)
    scalars[0] = prior_tag
    action_mask = np.asarray(mask, dtype=np.int8)
    return Observation(seat=seat, planes=planes, scalars=scalars, action_mask=action_mask)


@dataclass
class _Served:
    action_id: int
    value: float


class FakeCheckpointPolicy:
    """Priors and value head keyed on ``scalars[0]`` (a float tag).

    ``prior_by_tag[tag]`` -> length-A array of action probabilities.
    ``value_by_tag[tag]`` -> scalar value-head output.
    Records every ``evaluate_batch`` call's batch size so tests can assert the
    searcher batches live clones instead of looping one row at a time.
    """

    def __init__(self, prior_by_tag: dict[float, Sequence[float]],
                 value_by_tag: Optional[dict[float, float]] = None,
                 default_value: float = 0.0) -> None:
        self.prior_by_tag = {float(k): np.asarray(v, dtype=np.float32) for k, v in prior_by_tag.items()}
        self.value_by_tag = {float(k): float(v) for k, v in (value_by_tag or {}).items()}
        self.default_value = float(default_value)
        self.batch_sizes: list[int] = []

    def _lookup_prior(self, tag: float) -> np.ndarray:
        if tag in self.prior_by_tag:
            return self.prior_by_tag[tag]
        return np.full((A,), 1.0 / A, dtype=np.float32)

    def choose(self, observation: Observation) -> _Served:
        tag = float(observation.scalars[0])
        prior = self._lookup_prior(tag)
        return _Served(action_id=int(np.argmax(prior)), value=self.value_by_tag.get(tag, self.default_value))

    def evaluate_batch(self, planes, scalars, action_masks):
        # The searcher must always call us with batched (4-D plane) inputs.
        assert planes.ndim == 4, f"evaluate_batch expected batched planes, got ndim={planes.ndim}"
        assert scalars.ndim == 2 and action_masks.ndim == 2
        n = planes.shape[0]
        self.batch_sizes.append(n)
        probs = np.zeros((n, A), dtype=np.float32)
        values = np.zeros((n,), dtype=np.float32)
        for i in range(n):
            tag = float(scalars[i, 0])
            probs[i] = self._lookup_prior(tag)
            values[i] = self.value_by_tag.get(tag, self.default_value)
        return probs, values


@dataclass
class SlotSpec:
    """One scripted step outcome for a clone."""
    reward: float = 0.0
    terminated: bool = False
    truncated: bool = False
    round_ended: bool = False
    tag: float = 0.0        # obs tag (drives the value head on bootstrap rows)
    error: str = ""

    @property
    def has_observation(self) -> bool:
        # Terminal / errored steps carry no observation; round-end and
        # truncation both carry a bootstrap observation row.
        return not (self.terminated or bool(self.error))


class FakeSearchPool:
    """Replays ``per_candidate[c]`` for every clone of candidate ``c``.

    ``step`` advances each acting slot through its own script independently, so
    clones that finished early simply stop being stepped.
    """

    def __init__(self, per_candidate: list[list[SlotSpec]], K: int, seat: int) -> None:
        self.per_candidate = per_candidate
        self.K = K
        self.seat = seat
        self._slot_step: dict[int, int] = defaultdict(int)
        self.closed = False
        self.step_calls = 0

    def step(self, commands: Sequence[PoolCommand]) -> SearchStepResult:
        self.step_calls += 1
        metas: list[SlotMeta] = []
        round_ended: dict[int, bool] = {}
        live: list[tuple[int, SlotSpec]] = []
        for cmd in commands:
            slot = int(cmd.slot)
            if cmd.action_id is None:  # skip command -> clone already done
                continue
            c = slot // self.K
            idx = self._slot_step[slot]
            self._slot_step[slot] += 1
            script = self.per_candidate[c]
            spec = script[idx] if idx < len(script) else SlotSpec(terminated=True)
            rewards = np.zeros(4, dtype=np.float32)
            rewards[self.seat] = spec.reward
            metas.append(SlotMeta(
                slot=slot, seat=self.seat, terminated=spec.terminated,
                truncated=spec.truncated, step_rewards=rewards,
                has_observation=spec.has_observation, error=spec.error,
            ))
            round_ended[slot] = spec.round_ended and not spec.terminated
            if spec.has_observation:
                live.append((slot, spec))

        rows = len(live)
        planes = np.zeros((rows, C, H, W), dtype=np.float32)
        scalars = np.zeros((rows, S), dtype=np.float32)
        masks = np.ones((rows, A), dtype=np.int8)
        row_of_slot: dict[int, int] = {}
        for i, (slot, spec) in enumerate(live):
            scalars[i, 0] = spec.tag
            row_of_slot[slot] = i
        return SearchStepResult(
            slots=metas, planes=planes, scalars=scalars, action_masks=masks,
            row_of_slot=row_of_slot, round_ended=round_ended,
        )

    def close(self) -> None:
        self.closed = True


def _factory_from(pool: FakeSearchPool):
    calls = {"count": 0}

    def factory(num_clones: int, seed: int, max_rollout_decisions: int):
        calls["count"] += 1
        return pool

    return factory, calls


# --- tests -----------------------------------------------------------------


def test_degenerate_single_candidate_equals_greedy():
    # Prior mass 1.0 on a single action -> one candidate -> no search at all.
    policy = FakeCheckpointPolicy({0.0: [0, 1, 0, 0, 0]})
    called = {"hit": False}

    def factory(*args, **kwargs):
        called["hit"] = True
        raise AssertionError("pool factory must not be called for a single candidate")

    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=2))
    obs = _obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1])
    choice = searcher.choose(obs)

    assert choice.action_id == 1                 # == greedy argmax of the prior
    assert choice.info["source"] != "search"
    assert called["hit"] is False
    assert searcher.fallback_count == 0


def test_search_prefers_higher_scoring_candidate():
    # A (id 1) has the higher prior, but B (id 2)'s rollouts earn more reward.
    policy = FakeCheckpointPolicy({0.0: [0, 0.6, 0.4, 0, 0]})
    K = 2
    per_candidate = [
        [SlotSpec(reward=0.0), SlotSpec(reward=1.0, terminated=True)],  # cand 0 -> action 1, total 1.0
        [SlotSpec(reward=0.0), SlotSpec(reward=5.0, terminated=True)],  # cand 1 -> action 2, total 5.0
    ]
    pool = FakeSearchPool(per_candidate, K=K, seat=0)
    factory, calls = _factory_from(pool)

    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=K))
    choice = searcher.choose(_obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    assert calls["count"] == 1
    assert choice.info["source"] == "search"
    assert choice.info["greedy_action_id"] == 1
    assert choice.action_id == 2                 # search overrides the greedy prior
    assert pool.closed is True
    assert choice.info["scores"] == pytest.approx([1.0, 5.0])


def test_fail_open_on_pool_error():
    policy = FakeCheckpointPolicy({0.0: [0, 0.6, 0.4, 0, 0]})

    def factory(*args, **kwargs):
        raise RuntimeError("boom")

    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=2))
    choice = searcher.choose(_obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    assert choice.action_id == 1                 # greedy fallback
    assert choice.info["source"] != "search"
    assert searcher.fallback_count == 1


def test_round_end_uses_value_bootstrap():
    # Equal accumulated rewards; the winner is decided purely by the value head
    # of the returned next-hand (round-end) observation.
    TAG_A, TAG_B = 11.0, 22.0
    policy = FakeCheckpointPolicy(
        {0.0: [0, 0.6, 0.4, 0, 0]},
        value_by_tag={TAG_A: 0.1, TAG_B: 1.0},
    )
    K = 2
    per_candidate = [
        [SlotSpec(reward=0.0), SlotSpec(reward=0.0, round_ended=True, tag=TAG_A)],
        [SlotSpec(reward=0.0), SlotSpec(reward=0.0, round_ended=True, tag=TAG_B)],
    ]
    pool = FakeSearchPool(per_candidate, K=K, seat=0)
    factory, _ = _factory_from(pool)

    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=K))
    choice = searcher.choose(_obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    assert choice.info["source"] == "search"
    assert choice.action_id == 2                 # id 2 wins only via the value bootstrap
    assert choice.info["scores"] == pytest.approx([0.1, 1.0])


def test_truncation_scored_with_cap_value():
    # Candidate A truncates at the cap with a high cap value; candidate B
    # terminates with a moderate reward. A must win -> truncation contributes
    # the cap value, not zero.
    CAP = 33.0
    policy = FakeCheckpointPolicy(
        {0.0: [0, 0.6, 0.4, 0, 0]},
        value_by_tag={CAP: 1.0},
    )
    K = 2
    per_candidate = [
        [SlotSpec(reward=0.0, truncated=True, tag=CAP)],    # cand 0 -> action 1, score = cap value 1.0
        [SlotSpec(reward=0.3, terminated=True)],            # cand 1 -> action 2, score = 0.3
    ]
    pool = FakeSearchPool(per_candidate, K=K, seat=0)
    factory, _ = _factory_from(pool)

    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=K))
    choice = searcher.choose(_obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    assert choice.info["source"] == "search"
    assert choice.action_id == 1                 # only true if cap value (1.0) > 0.3
    assert choice.info["scores"] == pytest.approx([1.0, 0.3])


def test_chunk_invariance_batches_live_clones():
    # The searcher must batch all live clones through one evaluate_batch call.
    policy = FakeCheckpointPolicy({0.0: [0, 0.6, 0.4, 0, 0]})
    K = 2
    per_candidate = [
        [SlotSpec(reward=0.0), SlotSpec(reward=1.0, terminated=True)],
        [SlotSpec(reward=0.0), SlotSpec(reward=1.0, terminated=True)],
    ]
    pool = FakeSearchPool(per_candidate, K=K, seat=0)
    factory, _ = _factory_from(pool)

    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=K))
    searcher.choose(_obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    # 2 candidates * K=2 = 4 clones, all live after the first (apply) step ->
    # a single batched evaluate_batch call of size 4. A per-clone loop would
    # only ever produce batch size 1.
    assert max(policy.batch_sizes) == 4

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
        # Mirror serving.CheckpointPolicy.evaluate_batch: an all-zero mask row is
        # rejected (masked softmax over no legal actions -> NaN). Bootstrap rows
        # must therefore be mask-sanitized by the searcher before reaching us.
        no_legal = np.flatnonzero(~action_masks.astype(bool).any(axis=1))
        if no_legal.size:
            raise ValueError(f"observation {int(no_legal[0])} has no legal actions")
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
    mask: Optional[Sequence[int]] = None  # per-row action mask; None -> all ones
    seat: Optional[int] = None  # seat of the obs this step RETURNS; None -> pool seat

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
            # ``spec.seat`` is the seat of the observation this step RETURNS (the
            # seat that will act next); it drives the searcher's root-decision
            # horizon counting. Rewards always credit the fixed pool/root seat.
            obs_seat = self.seat if spec.seat is None else spec.seat
            metas.append(SlotMeta(
                slot=slot, seat=obs_seat, terminated=spec.terminated,
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
            if spec.mask is not None:
                masks[i] = np.asarray(spec.mask, dtype=np.int8)
            row_of_slot[slot] = i
        return SearchStepResult(
            slots=metas, planes=planes, scalars=scalars, action_masks=masks,
            row_of_slot=row_of_slot, round_ended=round_ended,
        )

    def close(self) -> None:
        self.closed = True


def _factory_from(pool: FakeSearchPool):
    calls = {"count": 0, "num_clones": None, "seed": None,
             "max_rollout_decisions": None, "determinizations": None, "root_seat": None}

    def factory(num_clones: int, seed: int, max_rollout_decisions: int,
                determinizations: int, root_seat: int | None = None):
        calls["count"] += 1
        calls["num_clones"] = num_clones
        calls["seed"] = seed
        calls["max_rollout_decisions"] = max_rollout_decisions
        calls["determinizations"] = determinizations
        calls["root_seat"] = root_seat
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

    # gamma=1.0 pins the undiscounted convention this test's exact scores encode.
    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=K, discount_gamma=1.0))
    choice = searcher.choose(_obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    assert calls["count"] == 1
    assert choice.info["source"] == "search"
    assert choice.info["greedy_action_id"] == 1
    assert choice.action_id == 2                 # search overrides the greedy prior
    assert pool.closed is True
    assert choice.info["scores"] == pytest.approx([1.0, 5.0])


def test_pool_factory_receives_determinizations_K():
    # LEAK 2 plumbing: SearchPolicy must pass the determinization count K through
    # to the pool factory (as the clone count M*K and the explicit
    # `determinizations` arg) so the Go pool can pair worlds by k.
    policy = FakeCheckpointPolicy({0.0: [0, 0.6, 0.4, 0, 0]})
    K = 5
    per_candidate = [
        [SlotSpec(reward=1.0, terminated=True)],
        [SlotSpec(reward=2.0, terminated=True)],
    ]
    pool = FakeSearchPool(per_candidate, K=K, seat=2)
    factory, calls = _factory_from(pool)

    searcher = SearchPolicy(policy, factory,
                            SearchConfig(num_determinizations=K, seed=123, max_rollout_decisions=77))
    searcher.choose(_obs(seat=2, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    assert calls["count"] == 1
    assert calls["determinizations"] == K
    assert calls["num_clones"] == len(per_candidate) * K  # M candidates x K
    assert calls["seed"] == 123
    assert calls["max_rollout_decisions"] == 77
    # The search root must be pinned to the observation's seat explicitly, so the
    # Go pool roots on the seat being searched rather than currentActionSeat().
    assert calls["root_seat"] == 2


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

    # gamma=1.0 pins the undiscounted convention this test's exact scores encode.
    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=K, discount_gamma=1.0))
    choice = searcher.choose(_obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    assert choice.info["source"] == "search"
    assert choice.action_id == 2                 # id 2 wins only via the value bootstrap
    assert choice.info["scores"] == pytest.approx([0.1, 1.0])


def test_bootstrap_row_real_mask_consumed_as_is():
    # The Go pool now emits bootstrap rows at the root's GENUINE next decision with
    # a REAL (non-empty) action mask. The searcher passes that mask through
    # unchanged; values are mask-independent, so the value bootstrap lands and the
    # non-empty mask satisfies evaluate_batch's no-legal-actions guard.
    TAG_A, TAG_B = 11.0, 22.0
    REAL_MASK = [1, 0, 1, 0, 0]  # a genuine root decision's mask (>=1 legal action)
    policy = FakeCheckpointPolicy(
        {0.0: [0, 0.6, 0.4, 0, 0]},
        value_by_tag={TAG_A: 0.1, TAG_B: 1.0},
    )
    K = 2
    per_candidate = [
        [SlotSpec(reward=0.0), SlotSpec(reward=0.0, round_ended=True, tag=TAG_A, mask=REAL_MASK)],
        [SlotSpec(reward=0.0), SlotSpec(reward=0.0, round_ended=True, tag=TAG_B, mask=REAL_MASK)],
    ]
    pool = FakeSearchPool(per_candidate, K=K, seat=0)
    factory, _ = _factory_from(pool)

    # gamma=1.0 pins the undiscounted convention this test's exact scores encode.
    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=K, discount_gamma=1.0))
    choice = searcher.choose(_obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    assert choice.info["source"] == "search"      # value bootstrap consumed as-is
    assert choice.action_id == 2                   # id 2 wins only via the value bootstrap
    assert choice.info["scores"] == pytest.approx([0.1, 1.0])


def test_bootstrap_row_zero_mask_fails_open():
    # A zero-mask bootstrap row is a CONTRACT VIOLATION now that the pool bootstraps
    # only at genuine root decisions. The searcher no longer sanitizes it, so
    # evaluate_batch's no-legal-actions guard raises and the whole search fails open
    # to greedy (source="greedy", one fallback counted) — the correct response.
    TAG_A, TAG_B = 11.0, 22.0
    policy = FakeCheckpointPolicy(
        {0.0: [0, 0.6, 0.4, 0, 0]},
        value_by_tag={TAG_A: 0.1, TAG_B: 1.0},
    )
    K = 2
    ZERO_MASK = [0, 0, 0, 0, 0]
    per_candidate = [
        [SlotSpec(reward=0.0), SlotSpec(reward=0.0, round_ended=True, tag=TAG_A, mask=ZERO_MASK)],
        [SlotSpec(reward=0.0), SlotSpec(reward=0.0, round_ended=True, tag=TAG_B, mask=ZERO_MASK)],
    ]
    pool = FakeSearchPool(per_candidate, K=K, seat=0)
    factory, _ = _factory_from(pool)

    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=K, discount_gamma=1.0))
    choice = searcher.choose(_obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    assert choice.info["source"] == "greedy"      # fail-open, NOT the sanitized path
    assert choice.action_id == 1                  # greedy argmax of the prior
    assert searcher.fallback_count == 1


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

    # gamma=1.0 pins the undiscounted convention this test's exact scores encode
    # (the truncation is on the FIRST apply, so at gamma<1 its bootstrap would be
    # gamma^1 * cap value; test_horizon_counting covers the discounted case).
    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=K, discount_gamma=1.0))
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


def test_unequal_horizon_discounted_ranking_flips():
    # Regression for the discount fix: two candidates whose UNDISCOUNTED and
    # DISCOUNTED rankings DISAGREE. Candidate A earns a small immediate reward
    # and ends the round at horizon 0 with a big (one-step-ahead) value
    # bootstrap; candidate B earns a larger reward but only far down a chain of
    # ROOT-seat decisions, so discounting erodes it below A.
    #
    #   A (id 1): apply reward 1.0, round_ended, bootstrap V=3.0
    #     undiscounted = 1.0 + 3.0                     = 4.0
    #     discounted   = 1.0 + gamma^1 * 3.0           = 1.0 + 0.99*3.0 = 3.97
    #   B (id 2): 7 empty root decisions, then reward 4.1 terminated at horizon 7
    #     undiscounted = 4.1                           = 4.1   (> A)
    #     discounted   = gamma^7 * 4.1                 = 3.82  (< A)
    # Undiscounted picks B; discounted picks A. Pre-fix code (undiscounted) picks
    # B -> this assertion is the RED evidence.
    TAG_BIG = 44.0
    policy = FakeCheckpointPolicy(
        {0.0: [0, 0.6, 0.4, 0, 0]},
        value_by_tag={TAG_BIG: 3.0},
    )
    K = 1
    per_candidate = [
        [SlotSpec(reward=1.0, round_ended=True, tag=TAG_BIG)],           # A
        [SlotSpec(reward=0.0), SlotSpec(reward=0.0), SlotSpec(reward=0.0),
         SlotSpec(reward=0.0), SlotSpec(reward=0.0), SlotSpec(reward=0.0),
         SlotSpec(reward=0.0), SlotSpec(reward=4.1, terminated=True)],   # B
    ]
    pool = FakeSearchPool(per_candidate, K=K, seat=0)
    factory, _ = _factory_from(pool)

    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=K))  # gamma=0.99
    choice = searcher.choose(_obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    assert choice.info["source"] == "search"
    assert choice.action_id == 1                 # discounted winner (A), NOT undiscounted B
    a, b = choice.info["scores"]
    assert a == pytest.approx(1.0 + 0.99 * 3.0)          # 3.97
    assert b == pytest.approx((0.99 ** 7) * 4.1)         # 3.82
    assert a > b                                          # discounted A beats B


def test_gamma_one_reproduces_undiscounted_sum():
    # Anchor for part (b): gamma=1.0 collapses every weight to 1, so the score is
    # the raw reward sum plus the raw bootstrap -- identical to the pre-fix code.
    # Reward chain over several root decisions + a round-end value bootstrap.
    TAG = 7.0
    policy = FakeCheckpointPolicy(
        {0.0: [0, 0.6, 0.4, 0, 0]},
        value_by_tag={TAG: 2.5},
    )
    K = 1
    per_candidate = [
        [SlotSpec(reward=1.0), SlotSpec(reward=2.0),
         SlotSpec(reward=0.5, round_ended=True, tag=TAG)],   # sum 3.5 + V 2.5 = 6.0
        [SlotSpec(reward=0.0, terminated=True)],
    ]
    pool = FakeSearchPool(per_candidate, K=K, seat=0)
    factory, _ = _factory_from(pool)

    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=K, discount_gamma=1.0))
    choice = searcher.choose(_obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    assert choice.info["scores"][0] == pytest.approx(1.0 + 2.0 + 0.5 + 2.5)  # 6.0, undiscounted


def test_horizon_counting_exact_gamma_exponents():
    # Non-root steps must NOT advance the horizon; only ROOT-seat decisions do.
    # Root seat = 0. Each SlotSpec's `seat` is the seat of the obs it RETURNS
    # (i.e. who acts on the NEXT step), which is what drives horizon counting.
    #
    #   step 0 (apply, root decision 0): reward r0 at gamma^0; returns a NON-root
    #           obs (seat 1) -> the next decision is not the root's.
    #   step 1 (non-root decision):      reward r1 at gamma^0 (same chunk 0);
    #           returns a ROOT obs (seat 0) -> the next decision IS the root's.
    #   step 2 (root decision 1):        reward r2 at gamma^1, then terminated.
    #
    #   score = r0 + r1 + gamma * r2
    gamma = 0.99
    r0, r1, r2 = 1.0, 2.0, 4.0
    policy = FakeCheckpointPolicy({0.0: [0, 0.6, 0.4, 0, 0]})
    K = 1
    per_candidate = [
        [SlotSpec(reward=r0, seat=1),                 # -> next decision is seat 1 (non-root)
         SlotSpec(reward=r1, seat=0),                 # -> next decision is seat 0 (root)
         SlotSpec(reward=r2, terminated=True)],       # root decision 1, then terminal
        [SlotSpec(reward=0.0, terminated=True)],      # trivial second candidate
    ]
    pool = FakeSearchPool(per_candidate, K=K, seat=0)
    factory, _ = _factory_from(pool)

    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=K, discount_gamma=gamma))
    choice = searcher.choose(_obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    expected = r0 + r1 + gamma * r2               # non-root step 1 stays in chunk 0
    assert choice.info["scores"][0] == pytest.approx(expected)


def test_python_cutoff_excludes_foreign_seat_row_from_bootstrap():
    # Regression for adversarial round 5: Go defers ITS cap to the root seat's
    # next decision, so a clone can still be mid-foreign-seat-turn when the
    # PYTHON loop's own defensive bound (2*max_rollout_decisions + 32) expires.
    # Value-bootstrapping that foreign-seat row would feed the champion value
    # head an out-of-distribution input -- the same OOD failure the Go-side
    # round-4 fix eliminated. The fix: such a clone must be EXCLUDED from its
    # candidate's mean (the same `errored` drop path used for real errors),
    # never value-bootstrapped.
    #
    # Candidate id=2 (the prior's argmax / greedy action) terminates on the
    # very first apply with reward 5.0. Candidate id=1 never terminates and
    # sits on a foreign seat (seat=1, root seat=0) for the whole rollout, so
    # the Python bound fires while its row is still foreign. Pre-fix, that
    # foreign row would be value-bootstrapped with a deliberately huge value
    # (999.0), swamping id=2's 5.0 and flipping the winner to id=1 -- WRONG.
    # Post-fix, id=1's sole clone is excluded (all-clones-errored for that
    # candidate), and since id=1 isn't the greedy action it scores -inf, so
    # id=2 (5.0) correctly wins.
    FOREIGN_TAG = 42.0
    policy = FakeCheckpointPolicy(
        {0.0: [0, 0.4, 0.6, 0, 0]},          # argmax/greedy = action 2
        value_by_tag={FOREIGN_TAG: 999.0},    # huge decoy value for the OOD row
    )
    K = 1
    max_rollout_decisions = 2
    # Loop bound is 2*max_rollout_decisions + 32 = 36 iterations, plus the
    # initial "apply" step, needs script indices 0..36 (37 entries) to stay
    # live the whole time; pad generously.
    foreign_script = [
        SlotSpec(reward=0.0, seat=1, tag=FOREIGN_TAG) for _ in range(40)
    ]
    # order = argsort(-prior) -> [2, 1] (0.6 before 0.4)
    per_candidate = [
        [SlotSpec(reward=5.0, terminated=True)],  # candidate id=2 (greedy)
        foreign_script,                            # candidate id=1 (foreign at cutoff)
    ]
    pool = FakeSearchPool(per_candidate, K=K, seat=0)
    factory, _ = _factory_from(pool)

    searcher = SearchPolicy(
        policy, factory,
        SearchConfig(num_determinizations=K, discount_gamma=1.0,
                     max_rollout_decisions=max_rollout_decisions),
    )
    choice = searcher.choose(_obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    assert choice.info["source"] == "search"
    assert choice.info["greedy_action_id"] == 2
    assert choice.action_id == 2                  # id=1's decoy value must NOT win
    scores = choice.info["scores"]
    assert scores[0] == pytest.approx(5.0)         # candidate id=2
    assert scores[1] == float("-inf")              # candidate id=1: excluded, not greedy
    assert searcher.fallback_count == 1            # all-clones-errored fallback counted


def test_foreign_rows_between_boundary_and_bootstrap():
    # Models the redesigned Go contract: after a round boundary the pool surfaces
    # ORDINARY foreign-seat rows (round_ended=False) until the root's next GENUINE
    # decision, which is the round_ended bootstrap row (seat == root, real mask).
    # None of the intervening foreign rows are root decisions, so the horizon stays
    # at 0 and the bootstrap carries gamma^1 -- all rewards in chunk 0.
    #
    #   score = r0 + r1 + r2 + gamma^1 * V(bootstrap)
    gamma = 0.99
    r0, r1, r2 = 1.0, 2.0, 0.5
    TAG = 7.0
    policy = FakeCheckpointPolicy(
        {0.0: [0, 0.6, 0.4, 0, 0]},
        value_by_tag={TAG: 3.0},
    )
    REAL_MASK = [1, 1, 0, 0, 0]
    K = 1
    per_candidate = [
        [SlotSpec(reward=r0, seat=1),                 # apply: next actor foreign seat 1 (post-boundary)
         SlotSpec(reward=r1, seat=2),                 # foreign seat 1 acts, next foreign seat 2
         SlotSpec(reward=r2, round_ended=True, seat=0, tag=TAG, mask=REAL_MASK)],  # root bootstrap
        [SlotSpec(reward=0.0, terminated=True)],      # trivial second candidate
    ]
    pool = FakeSearchPool(per_candidate, K=K, seat=0)
    factory, _ = _factory_from(pool)

    searcher = SearchPolicy(policy, factory, SearchConfig(num_determinizations=K, discount_gamma=gamma))
    choice = searcher.choose(_obs(seat=0, prior_tag=0.0, mask=[1, 1, 1, 1, 1]))

    expected = r0 + r1 + r2 + gamma * 3.0
    assert choice.info["scores"][0] == pytest.approx(expected)

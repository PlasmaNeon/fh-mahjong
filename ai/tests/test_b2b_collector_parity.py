"""Collector parity gates for the batched-b2b-collector work (spec G0).

The three `test_process_collector_golden_digest*` tests (gate G0.0) pin
`collect_b2b_rollouts` output — every RolloutBatch field plus
match_telemetry — to hashes recorded from `origin/main`'s PRE-REFACTOR
collector. If one fails, the process collector's output changed; that is a
bug in the refactor, never a reason to update a constant.

Three configurations, because the refactor moved the placement-bonus block
and the hindsight-label branches into the shared `_finalize_b2b_match`, and
the cross-collector gates below cannot pin moved code — both collectors call
it, so comparing them to each other is circular:

  A  bonus off, every match completing        (the default path)
  B  bonus ON                                 (fail-closed checks,
                                               placement_utilities, the
                                               bonus.sum() check, the
                                               trajectory_returns minus-bonus)
  C  truncations and a bust                   (`rank == -1` and `rank == 4`
                                               in _assemble_hindsight_labels)
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.placement_bonus import PLACEMENT_RESHAPE_VALUES
from fh_mahjong_ai.ppo import PPOConfig, masked_logprob, masked_policy_distribution
from fh_mahjong_ai.scripts.collect_bench import (
    _digest_batch, compare_float_fields, emission_ordered_logits, float_gate_arrays,
    float_gate_ceilings,
)
from fh_mahjong_ai.train_b2b import (
    _B2bMatchState, _check_chongci_outcomes, _finalize_b2b_match, collect_b2b_rollouts,
)

from conftest import SMALL_MODEL

GOLDEN_MATCHES = 3
GOLDEN_BASE_SEED = 4242
GOLDEN_MAX_STEPS = 20000
GOLDEN_BATCH_DIGEST = "b422b1d389f56b4a30ed5dac5789075555ce6174cb9f24dc412b55e478f7c1e0"
GOLDEN_TELEMETRY_SHA256 = "a757d5ec33e5c3f2c512c7d96fdb1b094c4cfd0537babfa8ddcadd1e3136dbd9"

# Golden B: the same env, model and seed block as A with the placement bonus
# ON. Values are the ratified PLACEMENT_RESHAPE_VALUES; lambda is 0.5 — the
# placement-reshape lap calibrated lambda per run rather than registering one
# number, and this golden only has to exercise the moved block, not replicate
# that lap. Any non-degenerate lambda would do; 0.5 matches the G0.3 fixtures
# below.
GOLDEN_B_BONUS = dict(placement_bonus_values=PLACEMENT_RESHAPE_VALUES,
                      placement_bonus_lambda=0.5)
GOLDEN_B_BATCH_DIGEST = "9cde62befbc55d2e8610ade402b3cce3e34485b9c1b77a5c2329dab21745c920"
GOLDEN_B_TELEMETRY_SHA256 = "d4cb57fd1f230329522cebe9012286afe29d4fe6da1f6338eccfcf5b18d8c732"

# Golden C: seeds 9000..9007 at max_steps 4900, bonus off. The bust threshold
# is 1500, not the 1000 the G0.1 block below uses: under SAMPLED selection (the
# only mode origin/main's collector has — greedy was added by this branch) the
# 1000-threshold block busts nobody, so it would leave `rank == 4` unpinned.
# At 1500 the block truncates 5 matches and busts one seat in 9007, so both
# label branches are covered.
GOLDEN_C_BASE_SEED = 9000
GOLDEN_C_MATCHES = 8
GOLDEN_C_MAX_STEPS = 4900
GOLDEN_C_BUST_THRESHOLD = 1500
GOLDEN_C_TRUNCATED = 5
GOLDEN_C_BATCH_DIGEST = "9914565ce67e3deaa260e09aedb58010d1d34d980934048f8cc2b38d3efd4251"
GOLDEN_C_TELEMETRY_SHA256 = "3dcd404a3ff8ad47c52d82454d18eab0d7487cdc15345ba7a8952701186b0a3f"


def _golden_env_and_model(**env_overrides):
    env = EnvConfig(**{"bridge_kind": "go", "event_history_window": 8,
                       "oracle_observation": True,
                       "max_steps_per_episode": GOLDEN_MAX_STEPS, **env_overrides})
    torch.manual_seed(0)
    model = PolicyValueNet(EnvConfig(bridge_kind="go"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    return env, model


def golden_digests(batch, base_seed=GOLDEN_BASE_SEED, matches=GOLDEN_MATCHES) -> tuple[str, str]:
    tel = hashlib.sha256(json.dumps(batch.match_telemetry, sort_keys=True).encode()).hexdigest()
    return _digest_batch(base_seed, matches, batch), tel


def test_process_collector_golden_digest():
    env, model = _golden_env_and_model()
    cfg = PPOConfig(device="cpu", matches_per_iter=GOLDEN_MATCHES,
                    max_steps_per_episode=GOLDEN_MAX_STEPS, match_mode="chongci")
    batch = collect_b2b_rollouts(env, model, cfg, base_seed=GOLDEN_BASE_SEED)
    assert golden_digests(batch) == (GOLDEN_BATCH_DIGEST, GOLDEN_TELEMETRY_SHA256)


def test_process_collector_golden_digest_with_placement_bonus():
    """Golden B. The frozen lineage runs the placement bonus ON, and the whole
    bonus block moved into `_finalize_b2b_match` — unpinned by anything else
    here, since both collectors call the moved code."""
    env, model = _golden_env_and_model()
    cfg = PPOConfig(device="cpu", matches_per_iter=GOLDEN_MATCHES,
                    max_steps_per_episode=GOLDEN_MAX_STEPS, match_mode="chongci",
                    **GOLDEN_B_BONUS)
    batch = collect_b2b_rollouts(env, model, cfg, base_seed=GOLDEN_BASE_SEED)
    assert golden_digests(batch) == (GOLDEN_B_BATCH_DIGEST, GOLDEN_B_TELEMETRY_SHA256)
    # Not vacuous: the bonus really was applied, and it moved the byte stream.
    assert batch.truncated_matches == 0
    assert len(batch.match_telemetry) == GOLDEN_MATCHES
    for tel in batch.match_telemetry:
        assert any(b != 0.0 for b in tel["bonus"])
        assert abs(sum(tel["bonus"])) < 1e-6
    assert golden_digests(batch)[0] != GOLDEN_BATCH_DIGEST


def test_process_collector_golden_digest_with_truncation_and_busts():
    """Golden C: pins the `rank == -1` (truncated) and `rank == 4` (busted)
    branches of `_assemble_hindsight_labels`, which moved into the shared
    finalizer with everything else."""
    env, model = _golden_env_and_model(max_steps_per_episode=GOLDEN_C_MAX_STEPS,
                                       chongci_bust_threshold=GOLDEN_C_BUST_THRESHOLD)
    cfg = PPOConfig(device="cpu", matches_per_iter=GOLDEN_C_MATCHES,
                    max_steps_per_episode=GOLDEN_C_MAX_STEPS, match_mode="chongci")
    batch = collect_b2b_rollouts(env, model, cfg, base_seed=GOLDEN_C_BASE_SEED)
    assert golden_digests(batch, GOLDEN_C_BASE_SEED, GOLDEN_C_MATCHES) == \
        (GOLDEN_C_BATCH_DIGEST, GOLDEN_C_TELEMETRY_SHA256)
    # Not vacuous: both label branches are actually exercised.
    assert batch.truncated_matches == GOLDEN_C_TRUNCATED
    assert int((batch.rank_labels == -1).sum()) > 0
    assert int((batch.rank_labels == 4).sum()) > 0
    assert sum(t["busts"] for t in batch.match_telemetry) > 0
    assert float(batch.dealin_labels.sum()) > 0.0


# ---------------------------------------------------------------------------
# T2 building blocks: shared logprob helper, greedy selection, shared finalizer
# ---------------------------------------------------------------------------


def test_masked_logprob_matches_batched_categorical_expression():
    """The helper must reproduce the collector's original [1, A] expression
    bit-for-bit (the golden digest hashes old_logprobs)."""
    g = torch.Generator().manual_seed(7)
    for temperature in (1.0, 0.7, 1e-9):
        logits = torch.randn(204, generator=g)
        logits[torch.rand(204, generator=g) < 0.5] = torch.finfo(torch.float32).min
        legal = torch.nonzero(logits > torch.finfo(torch.float32).min).flatten()
        for action in legal[:5].tolist():
            batched = logits.unsqueeze(0) / max(temperature, 1e-6)
            expected = float(masked_policy_distribution(batched).log_prob(torch.tensor([action]))[0])
            assert masked_logprob(logits, temperature, action) == expected


def test_greedy_selection_is_deterministic_and_argmax():
    env, model = _golden_env_and_model()
    cfg = PPOConfig(device="cpu", matches_per_iter=1, max_steps_per_episode=GOLDEN_MAX_STEPS,
                    match_mode="chongci")
    a = collect_b2b_rollouts(env, model, cfg, base_seed=GOLDEN_BASE_SEED, action_selection="greedy")
    b = collect_b2b_rollouts(env, model, cfg, base_seed=GOLDEN_BASE_SEED, action_selection="greedy")
    assert golden_digests(a) == golden_digests(b)
    sampled = collect_b2b_rollouts(env, model, cfg, base_seed=GOLDEN_BASE_SEED)
    assert golden_digests(a) != golden_digests(sampled)
    n_legal = a.action_mask.astype(np.int64).sum(axis=1)
    assert np.all(a.action_mask[np.arange(len(a)), a.actions] == 1)
    assert np.all(a.old_logprobs >= np.log(1.0 / n_legal).astype(np.float32) - 1e-5)
    model.eval()
    with torch.no_grad():
        logits, _ = model(torch.from_numpy(a.planes), torch.from_numpy(a.scalars),
                          torch.from_numpy(a.action_mask),
                          events=torch.from_numpy(a.events.astype(np.int64)),
                          event_lengths=torch.from_numpy(a.event_lengths.astype(np.int64)))
    assert np.array_equal(logits.argmax(dim=1).numpy(), a.actions)
    with pytest.raises(ValueError, match="action_selection"):
        collect_b2b_rollouts(env, model, cfg, base_seed=GOLDEN_BASE_SEED, action_selection="argmax")


def _hand_state(decisions_per_seat, hand_ids_per_seat, net, truncated=False, outcomes=None):
    ms = _B2bMatchState()
    for k, (n, hids) in enumerate(zip(decisions_per_seat, hand_ids_per_seat)):
        assert len(hids) == n
        for i in range(n):
            ms.seat_planes[k].append(np.full((1, 1, 1), k * 10 + i, np.float32))
            ms.seat_scalars[k].append(np.full((2,), k, np.float32))
            ms.seat_masks[k].append(np.ones((3,), np.int8))
            ms.seat_actions[k].append(k * 100 + i)
            ms.seat_logprobs[k].append(-float(i + 1))
            ms.seat_values[k].append(float(k))
            ms.seat_rewards[k].append(0.5 * i)
            ms.seat_events[k].append(np.zeros(4, np.uint32))
            ms.seat_lengths[k].append(i)
            ms.seat_hand_ids[k].append(hids[i])
    ms.match_net = np.asarray(net, dtype=np.float64)
    ms.hand_outcomes = dict(outcomes or {})
    ms.hand_id = len(ms.hand_outcomes)
    ms.truncated = truncated
    return ms


def test_finalize_emits_seat_contiguous_rows_and_labels():
    cfg = EnvConfig(bridge_kind="mock", chongci_starting_score=1000, chongci_bust_threshold=0)
    config = PPOConfig(device="cpu", match_mode="chongci")
    outcomes = {0: {"is_draw": False, "win_type_name": "ACTION_RON", "discarder_seat": 2},
                1: {"is_draw": True}}
    ms = _hand_state([2, 0, 3, 1], [[0, 1], [], [0, 0, 1], [1]],
                     net=[0.5, -0.2, -1.0, 0.7], outcomes=outcomes)
    rows, tel = _finalize_b2b_match(ms, config, cfg, seed=99)
    assert rows["actions"] == [0, 1, 200, 201, 202, 300]
    assert rows["dones"] == [0.0, 1.0, 0.0, 0.0, 1.0, 1.0]
    assert rows["rewards"] == [0.0, 0.5, 0.0, 0.5, 1.0, 0.0]
    assert rows["lengths"] == [0, 1, 0, 1, 2, 0]
    assert rows["logprobs"] == [-1.0, -2.0, -1.0, -2.0, -3.0, -1.0]
    # seat 2 dealt in on hand 0 (its two hand-0 rows), nobody else
    assert rows["dealin"] == [0.0, 0.0, 1.0, 1.0, 0.0, 0.0]
    # scores 1500, 800, 0 (bust: <= 0), 1700 -> ranks seat0=1, seat2=4, seat3=0
    assert tel["final_scores"] == [1500, 800, 0, 1700]
    assert tel["busts"] == 1 and tel["truncated"] is False and tel["seed"] == 99
    assert rows["rank"] == [1, 1, 4, 4, 4, 0]
    assert np.allclose(tel["bonus"], 0.0)
    assert tel["trajectory_returns"] == [0.5, 0.0, 1.5, 0.0]
    assert all(len(rows[k]) == 6 for k in rows)


def test_finalize_truncated_masks_rank_and_bonus_fails_closed():
    cfg = EnvConfig(bridge_kind="mock")
    ms = _hand_state([1, 1, 1, 1], [[0]] * 4, net=[0, 0, 0, 0], truncated=True)
    rows, tel = _finalize_b2b_match(ms, PPOConfig(device="cpu", match_mode="chongci"), cfg, seed=1)
    assert rows["rank"] == [-1, -1, -1, -1] and tel["truncated"] is True
    bonus_cfg = PPOConfig(device="cpu", match_mode="chongci",
                          placement_bonus_values=PLACEMENT_RESHAPE_VALUES, placement_bonus_lambda=0.5)
    with pytest.raises(RuntimeError, match="placement bonus.*truncat"):
        _finalize_b2b_match(_hand_state([1, 1, 1, 1], [[0]] * 4, [0, 0, 0, 0], truncated=True),
                            bonus_cfg, cfg, seed=1)
    with pytest.raises(RuntimeError, match="zero-decision"):
        _finalize_b2b_match(_hand_state([1, 0, 1, 1], [[0], [], [0], [0]], [0, 0, 0, 0]),
                            bonus_cfg, cfg, seed=1)
    # bonus lands on each seat's last row and sums to zero
    ms = _hand_state([2, 1, 1, 1], [[0, 0], [0], [0], [0]], net=[0.4, 0.2, -0.3, -0.3])
    rows, tel = _finalize_b2b_match(ms, bonus_cfg, cfg, seed=5)
    assert abs(sum(tel["bonus"])) < 1e-6
    assert rows["rewards"][0] == 0.0
    assert rows["rewards"][1] == pytest.approx(0.5 + tel["bonus"][0])
    assert rows["rewards"][2] == pytest.approx(tel["bonus"][1])


def test_check_chongci_outcomes():
    _check_chongci_outcomes(False, 3, 0)
    _check_chongci_outcomes(True, 0, 0)
    _check_chongci_outcomes(True, 3, 1)
    with pytest.raises(RuntimeError, match="no round outcomes"):
        _check_chongci_outcomes(True, 3, 0)


# ---------------------------------------------------------------------------
# T3 gates G0.1-G0.4: collect_b2b_rollouts vs collect_b2b_rollouts_batched
# ---------------------------------------------------------------------------
#
# Block: seeds 9000..9007, max_steps 4900, bust threshold 1000 — found
# empirically: seed 9002 needs 4915 steps (the only truncated match) and
# seed 9005 finishes 960/5080/1000/960 (three busts). Every other match
# completes. Each 8-match run costs ~45 s on CPU, so runs are module-scoped.

import fh_mahjong_ai.batched_b2b as batched_b2b_module  # noqa: E402
import fh_mahjong_ai.train_b2b as train_b2b_module  # noqa: E402
from fh_mahjong_ai.batched_b2b import collect_b2b_rollouts_batched, make_b2b_pool  # noqa: E402
from fh_mahjong_ai.types import Observation, StepResult  # noqa: E402

BLOCK_BASE_SEED = 9000
BLOCK_MATCHES = 8
BLOCK_MAX_STEPS = 4900
BLOCK_BUST_THRESHOLD = 1000
BLOCK_TRUNCATED_SEED = 9002
BLOCK_BUST_SEED = 9005
FLOAT_TOL = dict(atol=1e-6, rtol=1e-5)
# Spec G0.1b hard ceilings (absolute max |delta| vs the per-row/process
# reference on CPU): legal logits 5e-5, old_logprobs 5e-5, values 5e-6,
# non-finite count 0. Registered constants; never widen them.
G01B_CEILINGS = {"legal_logits": 5e-5, "old_logprobs": 5e-5, "values": 5e-6}


def _block_env_and_model(**env_overrides):
    env = EnvConfig(**{"bridge_kind": "go", "event_history_window": 8,
                       "oracle_observation": True, "max_steps_per_episode": BLOCK_MAX_STEPS,
                       "chongci_bust_threshold": BLOCK_BUST_THRESHOLD, **env_overrides})
    torch.manual_seed(0)
    model = PolicyValueNet(EnvConfig(bridge_kind="go"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    return env, model


def _block_config(matches=BLOCK_MATCHES, **overrides):
    return PPOConfig(**{"device": "cpu", "matches_per_iter": matches,
                        "max_steps_per_episode": BLOCK_MAX_STEPS, "match_mode": "chongci",
                        **overrides})


def _capturing_finalizer(store: dict):
    """Wrap _finalize_b2b_match to record each match's hand bookkeeping (G0.4)."""
    def wrapped(ms, config, cfg, seed):
        store[int(seed)] = {
            "hand_ids": [list(h) for h in ms.seat_hand_ids],
            "hand_outcomes": {int(k): v for k, v in ms.hand_outcomes.items()},
            "hand_id": int(ms.hand_id),
            "match_net": ms.match_net.copy(),
        }
        return _finalize_b2b_match(ms, config, cfg, seed)
    return wrapped


def _run_process(env, model, cfg, base_seed, action_selection="greedy", capture=None,
                 diagnostics=None, **_):
    with pytest.MonkeyPatch.context() as mp:
        if capture is not None:
            mp.setattr(train_b2b_module, "_finalize_b2b_match", _capturing_finalizer(capture))
        return collect_b2b_rollouts(env, model, cfg, base_seed=base_seed,
                                    action_selection=action_selection, diagnostics=diagnostics)


def _run_batched(env, model, cfg, base_seed, action_selection="greedy", slots=3,
                 inference_mode="per_row", capture=None, diagnostics=None):
    pool = make_b2b_pool(env, model, cfg, slots)
    try:
        with pytest.MonkeyPatch.context() as mp:
            if capture is not None:
                mp.setattr(batched_b2b_module, "_finalize_b2b_match",
                           _capturing_finalizer(capture))
            return collect_b2b_rollouts_batched(
                env, model, cfg, base_seed=base_seed, pool=pool,
                inference_mode=inference_mode, action_selection=action_selection,
                diagnostics=diagnostics)
    finally:
        pool.close()


COLLECTORS = [pytest.param(_run_process, id="process"),
              pytest.param(_run_batched, id="batched")]


def _digests(batch, base_seed=BLOCK_BASE_SEED, matches=BLOCK_MATCHES):
    tel = hashlib.sha256(json.dumps(batch.match_telemetry, sort_keys=True).encode()).hexdigest()
    return _digest_batch(base_seed, matches, batch), tel


@pytest.fixture(scope="module")
def block_process_greedy():
    """(batch, finalizer capture, emission-ordered masked logits [N, A])."""
    env, model = _block_env_and_model()
    capture: dict = {}
    diag: dict = {"logits": []}
    batch = _run_process(env, model, _block_config(), BLOCK_BASE_SEED, capture=capture,
                         diagnostics=diag)
    return batch, capture, emission_ordered_logits(diag["logits"], batch)


@pytest.fixture(scope="module")
def block_batched_per_row_greedy():
    env, model = _block_env_and_model()
    capture: dict = {}
    batch = _run_batched(env, model, _block_config(), BLOCK_BASE_SEED, slots=7,
                         inference_mode="per_row", capture=capture)
    return batch, capture


@pytest.fixture(scope="module")
def block_batched_mode_greedy():
    """(batch, emission-ordered masked logits [N, A])."""
    env, model = _block_env_and_model()
    diag: dict = {"logits": []}
    batch = _run_batched(env, model, _block_config(), BLOCK_BASE_SEED, slots=7,
                         inference_mode="batched", diagnostics=diag)
    return batch, emission_ordered_logits(diag["logits"], batch)


@pytest.fixture(scope="module")
def sampled_digests_by_slots():
    env, model = _block_env_and_model()
    out = {}
    for slots in (1, 7, 64):
        batch = _run_batched(env, model, _block_config(), BLOCK_BASE_SEED, "sample",
                             slots=slots, inference_mode="per_row")
        assert len(batch.match_telemetry) == BLOCK_MATCHES
        out[slots] = _digests(batch)
    return out


def test_block_has_truncated_and_bust_matches(block_process_greedy):
    batch, _, _ = block_process_greedy
    by_seed = {t["seed"]: t for t in batch.match_telemetry}
    assert batch.truncated_matches == 1
    assert by_seed[BLOCK_TRUNCATED_SEED]["truncated"] is True
    assert by_seed[BLOCK_BUST_SEED]["busts"] >= 1
    assert len(batch.match_telemetry) == BLOCK_MATCHES


def test_g0_1_greedy_per_row_is_byte_identical(block_process_greedy,
                                               block_batched_per_row_greedy):
    process, _, _ = block_process_greedy
    batched, _ = block_batched_per_row_greedy
    assert _digests(batched) == _digests(process)
    assert batched.match_telemetry == process.match_telemetry


def test_g0_1b_greedy_batched_mode_numeric_parity(block_process_greedy,
                                                  block_batched_mode_greedy):
    process, _, process_logits = block_process_greedy
    batched, batched_logits = block_batched_mode_greedy
    for name in ("planes", "scalars", "action_mask", "actions", "rewards", "dones",
                 "events", "event_lengths", "dealin_labels", "rank_labels"):
        assert np.array_equal(getattr(batched, name), getattr(process, name)), name
    assert batched.truncated_matches == process.truncated_matches
    assert batched.match_telemetry == process.match_telemetry
    assert np.allclose(batched.old_logprobs, process.old_logprobs, **FLOAT_TOL)
    assert np.allclose(batched.values, process.values, **FLOAT_TOL)
    # Hard-bounded per-field gate (spec G0.1b): LEGAL logits, old_logprobs and
    # values each against their own absolute ceiling; no non-finite values.
    assert float_gate_ceilings("cpu") == G01B_CEILINGS
    assert process_logits.shape == batched_logits.shape == (len(process), 204)
    legal = process.action_mask.astype(bool)
    assert np.all(np.isfinite(process_logits[legal])) and np.all(np.isfinite(batched_logits[legal]))
    stats = compare_float_fields(float_gate_arrays(process, process_logits),
                                 float_gate_arrays(batched, batched_logits), G01B_CEILINGS)
    measured = {name: st["max_abs_diff"] for name, st in stats.items()}
    print(f"G0.1b measured max |delta| (test net, CPU): {measured}")
    for name, ceiling in G01B_CEILINGS.items():
        st = stats[name]
        assert st["element_count"] > 0, name
        assert st["nonfinite_count"] == 0, name
        assert st["max_abs_diff"] <= ceiling, (name, st)
        assert st["beyond_ceiling"] == 0, name
        assert st["passed"], name
    assert stats["legal_logits"]["element_count"] == int(legal.sum())


@pytest.mark.parametrize("slots", [7, 64])
def test_g0_2_sampled_slot_count_invariance(sampled_digests_by_slots, slots):
    assert sampled_digests_by_slots[slots] == sampled_digests_by_slots[1]


def test_g0_2_effective_slots_is_capped_at_matches(caplog):
    # 64-slot pool over a 2-match block: only 2 slots ever receive a command.
    env, model = _block_env_and_model(max_steps_per_episode=GOLDEN_MAX_STEPS)
    cfg = _block_config(matches=2, max_steps_per_episode=GOLDEN_MAX_STEPS)
    pool = make_b2b_pool(env, model, cfg, 64)
    seen_slots = set()
    real_step = pool.step

    def spy(commands):
        seen_slots.update(c.slot for c in commands)
        return real_step(commands)

    pool.step = spy
    try:
        with caplog.at_level("INFO", logger="fh_mahjong_ai.batched_b2b"):
            collect_b2b_rollouts_batched(env, model, cfg, base_seed=BLOCK_BASE_SEED, pool=pool)
    finally:
        pool.close()
    assert seen_slots == {0, 1}
    assert "effective_slots=2" in caplog.text


# --- G0.3: placement-bonus fail-closed parity ------------------------------

BONUS = dict(placement_bonus_values=PLACEMENT_RESHAPE_VALUES, placement_bonus_lambda=0.5)


@pytest.mark.parametrize("runner", COLLECTORS)
def test_g0_3_bonus_truncated_match_raises(runner):
    env, model = _block_env_and_model()
    cfg = _block_config(matches=1, **BONUS)
    with pytest.raises(RuntimeError, match="placement bonus.*truncat"):
        runner(env, model, cfg, BLOCK_TRUNCATED_SEED)


@pytest.fixture(scope="module")
def bonus_block_by_collector():
    # Two completing matches with the bonus on, from each collector.
    env, model = _block_env_and_model()
    cfg = _block_config(matches=2, **BONUS)
    return {"process": _run_process(env, model, cfg, BLOCK_BASE_SEED),
            "batched": _run_batched(env, model, cfg, BLOCK_BASE_SEED, slots=2)}


def test_g0_3_bonus_completing_block_sums_to_zero_and_matches(bonus_block_by_collector,
                                                              block_process_greedy):
    process = bonus_block_by_collector["process"]
    batched = bonus_block_by_collector["batched"]
    assert _digests(batched, matches=2) == _digests(process, matches=2)
    plain, _, _ = block_process_greedy
    plain_by_seed = {t["seed"]: t for t in plain.match_telemetry}
    assert len(process.match_telemetry) == 2
    for tel in process.match_telemetry:
        assert abs(sum(tel["bonus"])) < 1e-6
        assert any(b != 0.0 for b in tel["bonus"])
        assert tel["trajectory_returns"] == pytest.approx(
            plain_by_seed[tel["seed"]]["trajectory_returns"])
        assert tel["final_scores"] == plain_by_seed[tel["seed"]]["final_scores"]


# Scripted-bridge scenarios: the Go bridge cannot end a match at reset, and a
# zero-decision seat needs a scripted match. The same factory is installed on
# train_b2b (process collector) and envpool (InProcessEnvPool) so both
# collectors play the identical script.

STUB_ENV = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True)


class _ScriptedBridge:
    def __init__(self, config, resets, step_results):
        self.config = config
        self._resets = dict(resets)          # seed -> StepResult
        self._step_results = list(step_results)
        self.last_reset_result = None

    def reset(self, seed=None):
        self.last_reset_result = self._resets[int(seed)]
        return self.last_reset_result.observation

    def step(self, action_id):
        return self._step_results.pop(0)

    def close(self):
        pass


def _stub_obs(seat=0):
    mask = np.zeros(204, dtype=np.int8)
    mask[1] = 1
    return Observation(seat=seat, planes=np.zeros((51, 42, 1), dtype=np.float32),
                       scalars=np.zeros(58, dtype=np.float32), action_mask=mask)


def _stub_model():
    torch.manual_seed(0)
    return PolicyValueNet(EnvConfig(bridge_kind="mock"),
                          ModelConfig(**SMALL_MODEL, event_window=8,
                                      privileged_critic=True, aux_heads=True))


def _install_scripted_bridge(monkeypatch, resets, step_results):
    import fh_mahjong_ai.envpool as envpool_module

    def factory(cfg):
        return _ScriptedBridge(cfg, resets, list(step_results))
    monkeypatch.setattr(train_b2b_module, "build_bridge", factory)
    monkeypatch.setattr(envpool_module, "build_bridge", factory)


def _reset_result(terminated, seat=0):
    return StepResult(observation=_stub_obs(seat), rewards=np.zeros(4, np.float32),
                      terminated=terminated)


def _terminal_step(rewards=(0.0, 0.0, 0.0, 0.0)):
    return StepResult(observation=_stub_obs(), rewards=np.asarray(rewards, np.float32),
                      terminated=True, info={"round_outcome": {"is_draw": True}})


@pytest.mark.parametrize("runner", COLLECTORS)
def test_g0_3_bonus_zero_decision_seat_raises(runner, monkeypatch):
    _install_scripted_bridge(monkeypatch, {1: _reset_result(False)}, [_terminal_step()])
    cfg = PPOConfig(device="cpu", matches_per_iter=1, match_mode="chongci", **BONUS)
    with pytest.raises(RuntimeError, match="zero-decision"):
        runner(STUB_ENV, _stub_model(), cfg, 1, slots=1)


@pytest.mark.parametrize("runner", COLLECTORS)
def test_g0_3_bonus_reset_terminal_raises(runner, monkeypatch):
    _install_scripted_bridge(monkeypatch, {1: _reset_result(True)}, [])
    cfg = PPOConfig(device="cpu", matches_per_iter=1, match_mode="chongci", **BONUS)
    with pytest.raises(RuntimeError, match="ended at reset"):
        runner(STUB_ENV, _stub_model(), cfg, 1, slots=1)


@pytest.mark.parametrize("runner", COLLECTORS)
def test_reset_terminal_without_bonus_is_skipped(runner, monkeypatch):
    # Seed 1 ends at reset (no rows, no telemetry); seed 2 plays one decision.
    _install_scripted_bridge(monkeypatch, {1: _reset_result(True), 2: _reset_result(False)},
                             [_terminal_step((0.1, -0.1, 0.0, 0.0))])
    cfg = PPOConfig(device="cpu", matches_per_iter=2, match_mode="chongci")
    batch = runner(STUB_ENV, _stub_model(), cfg, 1, slots=1)
    assert len(batch) == 1
    assert [t["seed"] for t in batch.match_telemetry] == [2]
    assert batch.rewards.tolist() == pytest.approx([0.1])
    assert batch.match_telemetry[0]["final_scores"] == [2100, 1900, 2000, 2000]


# --- G0.4: ordered hand outcomes and hand_id assignment --------------------


def test_g0_4_hand_outcomes_and_hand_ids_match_process(block_process_greedy,
                                                       block_batched_per_row_greedy):
    process, p_cap, _ = block_process_greedy
    batched, b_cap = block_batched_per_row_greedy
    expected_seeds = list(range(BLOCK_BASE_SEED, BLOCK_BASE_SEED + BLOCK_MATCHES))
    assert sorted(p_cap) == sorted(b_cap) == expected_seeds
    for seed in expected_seeds:
        p, b = p_cap[seed], b_cap[seed]
        assert b["hand_id"] == p["hand_id"] >= 1, seed
        assert list(p["hand_outcomes"]) == list(range(p["hand_id"]))
        assert b["hand_outcomes"] == p["hand_outcomes"], seed   # ordered payloads
        assert b["hand_ids"] == p["hand_ids"], seed             # per-seat hand_id per decision
        assert np.array_equal(b["match_net"], p["match_net"]), seed
        assert not any(hid >= p["hand_id"] for h in p["hand_ids"] for hid in h) or \
            seed == BLOCK_TRUNCATED_SEED
    assert np.array_equal(batched.dealin_labels, process.dealin_labels)
    assert np.array_equal(batched.rank_labels, process.rank_labels)
    assert (process.rank_labels == -1).sum() > 0  # the truncated match's rows
    assert (process.rank_labels == 4).sum() > 0   # bust rank


def test_make_b2b_pool_binds_window_and_oracle():
    env = EnvConfig(bridge_kind="mock", event_history_window=3, oracle_observation=False,
                    chongci_bust_threshold=123, chongci_max_hands=5)
    model = _stub_model()
    cfg = PPOConfig(device="cpu", matches_per_iter=2, match_mode="chongci",
                    max_steps_per_episode=77)
    pool = make_b2b_pool(env, model, cfg, 2)
    try:
        pc = pool.env_config
        assert pc.event_history_window == 8 and pc.oracle_observation is True
        assert pc.chongci_bust_threshold == 123 and pc.chongci_max_hands == 5
        assert pc.max_steps_per_episode == 77 and pc.learning_seats == (0, 1, 2, 3)
        pool.env_config = EnvConfig(bridge_kind="mock", event_history_window=4)
        with pytest.raises(RuntimeError, match="event_history_window"):
            collect_b2b_rollouts_batched(env, model, cfg, base_seed=1, pool=pool)
        pool.env_config = pc
        with pytest.raises(ValueError, match="inference_mode"):
            collect_b2b_rollouts_batched(env, model, cfg, base_seed=1, pool=pool,
                                         inference_mode="nope")
        with pytest.raises(ValueError, match="action_selection"):
            collect_b2b_rollouts_batched(env, model, cfg, base_seed=1, pool=pool,
                                         action_selection="argmax")
    finally:
        pool.close()


# --- G0.6: two-iteration training parity ----------------------------------
#
# Same recipe, same seeds, both collectors: the batch a collector hands to
# GAE, the advantages GAE returns, the reported metrics, and the model AND
# optimizer state after EACH iteration must all match. Greedy selection is
# injected on both sides (sampling draws from different RNG streams by
# design -- see the spec's "What changes semantically"), and the batched
# side realigns the GLOBAL torch RNG after collecting: `collect_b2b_rollouts`
# seeds it once per match as a side effect, and `ppo_update`'s minibatch
# permutation reads it. That stream is not collector output, so this gate
# compares the update under an identical permutation rather than treating
# the side effect as semantics.
#
# Per-iteration state is captured by wrapping `train_state._save_train_state`
# (train_b2b calls it as `train_state.X`, so the patch reaches the call) with
# `train_state_every=1`: the wrapper clones the live model and optimizer
# state_dicts before delegating to the real save.

import fh_mahjong_ai.train_b2b as train_b2b_wiring  # noqa: E402
import fh_mahjong_ai.train_state as train_state_module  # noqa: E402
from fh_mahjong_ai.train_b2b import train_b2b  # noqa: E402

from conftest import b2b_model_config, save_champion39  # noqa: E402

PARITY_ITERATIONS = 2
PARITY_MATCHES = 3
PARITY_BASE_SEED = 9100


def _parity_config(collector, **overrides):
    return PPOConfig(device="cpu", iterations=PARITY_ITERATIONS,
                     matches_per_iter=PARITY_MATCHES, ppo_epochs=1, minibatch_size=64,
                     max_steps_per_episode=GOLDEN_MAX_STEPS, match_mode="chongci",
                     num_workers=1, collector=collector, pool_slots=2, **overrides)


def _greedy_process(env_config, model, config, base_seed):
    return collect_b2b_rollouts(env_config, model, config, base_seed=base_seed,
                                action_selection="greedy")


def _greedy_batched(inference_mode):
    def collect(env_config, model, config, base_seed, pool, **kwargs):
        batch = collect_b2b_rollouts_batched(
            env_config, model, config, base_seed=base_seed, pool=pool,
            inference_mode=inference_mode, action_selection="greedy", **kwargs)
        torch.manual_seed(int(base_seed + config.matches_per_iter - 1))
        return batch
    return collect


def _clone_tensors(state_dict: dict) -> dict:
    return {k: v.detach().cpu().clone() for k, v in state_dict.items()}


def _clone_optimizer(optimizer) -> dict:
    """Optimizer state_dict with every tensor (moments, step counters) cloned
    to CPU; param_groups copied minus the parameter index lists."""
    sd = optimizer.state_dict()
    state = {}
    for idx, entry in sd["state"].items():
        state[idx] = {k: (v.detach().cpu().clone() if torch.is_tensor(v) else v)
                      for k, v in entry.items()}
    groups = [{k: v for k, v in g.items() if k != "params"} for g in sd["param_groups"]]
    return {"state": state, "param_groups": groups}


def _optimizer_tensors(opt_state: dict) -> dict:
    """Flat name -> tensor over every optimizer moment and step counter."""
    out = {}
    for idx, entry in opt_state["state"].items():
        for k, v in entry.items():
            if torch.is_tensor(v):
                out[f"state.{idx}.{k}"] = v
    return out




@pytest.fixture(scope="module")
def parity_champion(tmp_path_factory):
    """ONE 39ch champion shared by every G0.6 run: a per-run champion would be
    a different random net, so the runs could never match."""
    torch.manual_seed(0)
    _, champion = save_champion39(tmp_path_factory.mktemp("g06_champion"))
    return champion


def _run_training_parity(tmp_path, champion, collector, inference_mode="per_row"):
    """One two-iteration run. Returns a dict: `final` (saved iter_002 model
    state), `gae` (per-iteration GAE inputs/outputs), `batches` (the rollout
    each iteration collected), `states` (per-iteration (model, optimizer)
    state clones captured at save time), `history` (reported metrics)."""
    env = EnvConfig(bridge_kind="go", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=GOLDEN_MAX_STEPS, match_mode="chongci")
    gae_calls: list[tuple] = []
    batches: list = []
    states: list[tuple[dict, dict]] = []
    real_compute_gae = train_b2b_wiring.compute_gae
    real_save = train_state_module._save_train_state

    def recording_gae(rewards, values, dones, gamma, gae_lambda):
        advantages, returns = real_compute_gae(rewards, values, dones, gamma, gae_lambda)
        gae_calls.append((rewards.copy(), values.copy(), dones.copy(),
                          advantages.copy(), returns.copy()))
        return advantages, returns

    def capturing_save(path, model, optimizer, *args, **kwargs):
        states.append((_clone_tensors(model.state_dict()), _clone_optimizer(optimizer)))
        return real_save(path, model, optimizer, *args, **kwargs)

    def recording_process(env_config, model, config, base_seed):
        batch = _greedy_process(env_config, model, config, base_seed)
        batches.append(batch)
        return batch

    greedy_batched = _greedy_batched(inference_mode)

    def recording_batched(env_config, model, config, base_seed, pool, **kwargs):
        batch = greedy_batched(env_config, model, config, base_seed, pool, **kwargs)
        batches.append(batch)
        return batch

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(train_b2b_wiring, "compute_gae", recording_gae)
        mp.setattr(train_state_module, "_save_train_state", capturing_save)
        mp.setattr(train_b2b_wiring, "collect_b2b_rollouts", recording_process)
        mp.setattr(batched_b2b_module, "collect_b2b_rollouts_batched", recording_batched)
        torch.manual_seed(0)   # deterministic warm-start surgery
        history = train_b2b(env, b2b_model_config(), champion, tmp_path / "ckpt",
                            _parity_config(collector), base_seed=PARITY_BASE_SEED,
                            train_state_every=1)
    final = torch.load(tmp_path / "ckpt" / f"iter_{PARITY_ITERATIONS:03d}.pt",
                       map_location="cpu")["model"]
    assert len(gae_calls) == len(batches) == len(states) == len(history) == PARITY_ITERATIONS
    assert all(any(k.startswith("state.") for k in _optimizer_tensors(o)) for _, o in states)
    return {"final": final, "gae": gae_calls, "batches": batches, "states": states,
            "history": history}


@pytest.fixture(scope="module")
def training_parity_process(tmp_path_factory, parity_champion):
    return _run_training_parity(tmp_path_factory.mktemp("g06_process"),
                                parity_champion, "process")


@pytest.fixture(scope="module")
def training_parity_batched_per_row(tmp_path_factory, parity_champion):
    return _run_training_parity(tmp_path_factory.mktemp("g06_per_row"),
                                parity_champion, "batched", inference_mode="per_row")


@pytest.fixture(scope="module")
def training_parity_batched_mode(tmp_path_factory, parity_champion):
    return _run_training_parity(tmp_path_factory.mktemp("g06_batched"),
                                parity_champion, "batched", inference_mode="batched")


G06_UPDATE_TOL = 1e-5   # registered: max |delta| per parameter and per optimizer moment


def _assert_metrics(process_history, batched_history, exact: bool):
    for i, (p, b) in enumerate(zip(process_history, batched_history)):
        assert p.keys() == b.keys(), f"iteration {i + 1}"
        for key in p:
            if exact or isinstance(p[key], (int, bool, str)) or p[key] is None:
                assert p[key] == b[key], f"iteration {i + 1}: {key}"
            else:
                assert abs(float(p[key]) - float(b[key])) <= G06_UPDATE_TOL, \
                    f"iteration {i + 1}: {key} {p[key]} vs {b[key]}"


def test_g0_6_training_parity_per_row_is_byte_equal(training_parity_process,
                                                    training_parity_batched_per_row):
    process, batched = training_parity_process, training_parity_batched_per_row
    for i, (p, b) in enumerate(zip(process["gae"], batched["gae"])):
        for name, pa, ba in zip(("rewards", "values", "dones", "advantages", "returns"), p, b):
            assert np.array_equal(pa, ba), f"iteration {i + 1}: {name}"
    for i, (pb, bb) in enumerate(zip(process["batches"], batched["batches"])):
        assert _digests(pb, PARITY_BASE_SEED, PARITY_MATCHES) == \
            _digests(bb, PARITY_BASE_SEED, PARITY_MATCHES), f"iteration {i + 1}: rollout"
    # Model AND optimizer state after EACH iteration, every tensor byte-equal.
    for i, ((pm, po), (bm, bo)) in enumerate(zip(process["states"], batched["states"])):
        assert pm.keys() == bm.keys(), f"iteration {i + 1}"
        for key, tensor in pm.items():
            assert torch.equal(tensor, bm[key]), f"iteration {i + 1}: model {key}"
        pt, bt = _optimizer_tensors(po), _optimizer_tensors(bo)
        assert pt.keys() == bt.keys() and pt, f"iteration {i + 1}"
        for key, tensor in pt.items():
            assert torch.equal(tensor, bt[key]), f"iteration {i + 1}: optimizer {key}"
        assert po["param_groups"] == bo["param_groups"], f"iteration {i + 1}"
    _assert_metrics(process["history"], batched["history"], exact=True)
    assert process["final"].keys() == batched["final"].keys()
    for key, tensor in process["final"].items():
        assert torch.equal(tensor, batched["final"][key]), key
    # The run must actually have trained: iteration 2's weights differ from
    # iteration 1's inputs, so byte-equality above is not vacuous.
    assert not np.array_equal(process["gae"][0][3], process["gae"][1][3])
    (m1, o1), (m2, o2) = process["states"]
    assert any(not torch.equal(m1[k], m2[k]) for k in m1)
    assert any(not torch.equal(_optimizer_tensors(o1)[k], _optimizer_tensors(o2)[k])
               for k in _optimizer_tensors(o1))


def test_g0_6_training_parity_batched_mode_within_tolerance(training_parity_process,
                                                            training_parity_batched_mode):
    process, batched = training_parity_process, training_parity_batched_mode
    for i, (p, b) in enumerate(zip(process["gae"], batched["gae"])):
        # Rewards and dones are discrete facts about the match; only the
        # value estimates (and hence advantages/returns) may move.
        assert np.array_equal(p[0], b[0]), f"iteration {i + 1}: rewards"
        assert np.array_equal(p[2], b[2]), f"iteration {i + 1}: dones"
        for name, pa, ba in zip(("values", "advantages", "returns"), p[1:2] + p[3:], b[1:2] + b[3:]):
            assert np.allclose(pa, ba, atol=1e-5), f"iteration {i + 1}: {name}"
    # Rollout floats per iteration within the G0.1b ceilings; every other
    # field exact.
    for i, (pb, bb) in enumerate(zip(process["batches"], batched["batches"])):
        for name in ("planes", "scalars", "action_mask", "actions", "rewards", "dones",
                     "events", "event_lengths", "dealin_labels", "rank_labels"):
            assert np.array_equal(getattr(pb, name), getattr(bb, name)), f"iteration {i + 1}: {name}"
        assert pb.match_telemetry == bb.match_telemetry, f"iteration {i + 1}"
        for name in ("old_logprobs", "values"):
            diff = np.abs(getattr(pb, name).astype(np.float64) - getattr(bb, name).astype(np.float64))
            assert np.all(np.isfinite(getattr(bb, name))), f"iteration {i + 1}: {name}"
            assert diff.max() <= G01B_CEILINGS[name], f"iteration {i + 1}: {name} {diff.max()}"
    # Model AND optimizer state after EACH iteration within the registered
    # update tolerance, per parameter and per moment.
    for i, ((pm, po), (bm, bo)) in enumerate(zip(process["states"], batched["states"])):
        assert pm.keys() == bm.keys(), f"iteration {i + 1}"
        worst_model = worst_opt = 0.0
        for key, tensor in pm.items():
            assert tensor.shape == bm[key].shape, f"iteration {i + 1}: model {key}"
            if tensor.is_floating_point():
                delta = float((tensor - bm[key]).abs().max()) if tensor.numel() else 0.0
                worst_model = max(worst_model, delta)
                assert delta <= G06_UPDATE_TOL, f"iteration {i + 1}: model {key} max|delta|={delta}"
            else:
                assert torch.equal(tensor, bm[key]), f"iteration {i + 1}: model {key}"
        pt, bt = _optimizer_tensors(po), _optimizer_tensors(bo)
        assert pt.keys() == bt.keys() and pt, f"iteration {i + 1}"
        for key, tensor in pt.items():
            if tensor.is_floating_point():
                delta = float((tensor - bt[key]).abs().max()) if tensor.numel() else 0.0
                worst_opt = max(worst_opt, delta)
                assert delta <= G06_UPDATE_TOL, f"iteration {i + 1}: optimizer {key} max|delta|={delta}"
            else:
                assert torch.equal(tensor, bt[key]), f"iteration {i + 1}: optimizer {key}"
        assert po["param_groups"] == bo["param_groups"], f"iteration {i + 1}"
        print(f"G0.6 batched-mode iteration {i + 1}: max|delta| model={worst_model:.3e} "
              f"optimizer={worst_opt:.3e}")
    _assert_metrics(process["history"], batched["history"], exact=False)
    for key, tensor in process["final"].items():
        assert torch.allclose(tensor, batched["final"][key], atol=G06_UPDATE_TOL), key

"""Collector parity gates for the batched-b2b-collector work (spec G0).

`test_process_collector_golden_digest` pins `collect_b2b_rollouts` output
(every RolloutBatch field + match_telemetry) to hashes recorded from `main`
before any refactor. If it fails, the process collector's output changed —
that is a bug, never a reason to update the constants.
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
from fh_mahjong_ai.scripts.collect_bench import _digest_batch
from fh_mahjong_ai.train_b2b import (
    _B2bMatchState, _check_chongci_outcomes, _finalize_b2b_match, collect_b2b_rollouts,
)

from conftest import SMALL_MODEL

GOLDEN_MATCHES = 3
GOLDEN_BASE_SEED = 4242
GOLDEN_MAX_STEPS = 20000
GOLDEN_BATCH_DIGEST = "b422b1d389f56b4a30ed5dac5789075555ce6174cb9f24dc412b55e478f7c1e0"
GOLDEN_TELEMETRY_SHA256 = "a757d5ec33e5c3f2c512c7d96fdb1b094c4cfd0537babfa8ddcadd1e3136dbd9"


def _golden_env_and_model():
    env = EnvConfig(bridge_kind="go", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=GOLDEN_MAX_STEPS)
    torch.manual_seed(0)
    model = PolicyValueNet(EnvConfig(bridge_kind="go"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    return env, model


def golden_digests(batch) -> tuple[str, str]:
    tel = hashlib.sha256(json.dumps(batch.match_telemetry, sort_keys=True).encode()).hexdigest()
    return _digest_batch(GOLDEN_BASE_SEED, GOLDEN_MATCHES, batch), tel


def test_process_collector_golden_digest():
    env, model = _golden_env_and_model()
    cfg = PPOConfig(device="cpu", matches_per_iter=GOLDEN_MATCHES,
                    max_steps_per_episode=GOLDEN_MAX_STEPS, match_mode="chongci")
    batch = collect_b2b_rollouts(env, model, cfg, base_seed=GOLDEN_BASE_SEED)
    assert golden_digests(batch) == (GOLDEN_BATCH_DIGEST, GOLDEN_TELEMETRY_SHA256)


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

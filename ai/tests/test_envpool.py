from dataclasses import asdict
from types import SimpleNamespace

import numpy as np
import pytest

from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.types import Observation, StepResult


def _pool(slots):
    from fh_mahjong_ai.envpool import make_selfplay_pool
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    cfg = PPOConfig(match_mode="classic", max_steps_per_episode=64, device="cpu")
    return make_selfplay_pool(env_cfg, cfg, slots)


def test_inprocess_pool_reset_and_step_shapes():
    from fh_mahjong_ai.envpool import PoolCommand
    pool = _pool(2)
    try:
        result = pool.step([PoolCommand(slot=0, reset_seed=11), PoolCommand(slot=1, reset_seed=12)])
        assert [m.slot for m in result.slots] == [0, 1]
        rows = sum(1 for m in result.slots if m.has_observation)
        assert result.planes.shape == (rows, 51, 42, 1)
        assert result.action_masks.shape[0] == rows
        assert set(result.row_of_slot) == {m.slot for m in result.slots if m.has_observation}
        # step the first live slot with its first legal action
        live = [m for m in result.slots if m.has_observation]
        if live:
            slot = live[0].slot
            mask = result.action_masks[result.row_of_slot[slot]]
            action = int(np.flatnonzero(mask > 0)[0])
            result2 = pool.step([PoolCommand(slot=slot, action_id=action)])
            assert result2.slots[0].slot == slot
            assert result2.slots[0].step_rewards.shape[-1] >= 1
    finally:
        pool.close()


def test_inprocess_pool_same_seed_same_first_obs():
    from fh_mahjong_ai.envpool import PoolCommand
    pool_a, pool_b = _pool(1), _pool(1)
    try:
        ra = pool_a.step([PoolCommand(slot=0, reset_seed=33)])
        rb = pool_b.step([PoolCommand(slot=0, reset_seed=33)])
        assert ra.slots[0].has_observation == rb.slots[0].has_observation
        if ra.slots[0].has_observation:
            np.testing.assert_array_equal(ra.planes, rb.planes)
            np.testing.assert_array_equal(ra.action_masks, rb.action_masks)
    finally:
        pool_a.close()
        pool_b.close()


# --- round-outcome plumbing (spec change 1 / gate G0.4) --------------------
#
# The pool used to DROP `SlotState.round_outcome` (the "pool wrapper drops
# round_outcome" trap recorded against the ds960 lap). B2b's hindsight labels
# are a function of the ORDERED outcome sequence and the hand ids it closes,
# so these compare the whole sequence against the single-env bridge path —
# `outcomes_seen > 0` is not a pass.


def _go_lib_available() -> bool:
    from fh_mahjong_ai.bridge import resolve_bridge_library
    return resolve_bridge_library(EnvConfig(bridge_kind="go")).exists()


requires_go_lib = pytest.mark.skipif(
    not _go_lib_available(), reason="Go bridge library not built"
)

# chongci_max_hands=3 keeps a full match at ~300 decisions (two nonterminal
# hand boundaries + the terminal hand) instead of the 50-hand default.
CHONGCI_MAX_HANDS = 3
FULL_MATCH_SEEDS = (7, 11, 13)
# Empirically located by scanning max_steps_per_episode under this action
# loop: 195 truncates ON a hand boundary, so the truncating step itself
# carries the pending outcome; 200 truncates mid-hand after a completed one.
TRUNCATION_CASES = ((7, 195), (7, 200), (11, 200))


def _b2b_env_config(max_steps, *, window=8):
    """The EnvConfig shape `collect_b2b_rollouts` simulates under."""
    return EnvConfig(bridge_kind="go", match_mode="chongci",
                     learning_seats=(0, 1, 2, 3), auto_play_heuristics=False,
                     max_steps_per_episode=max_steps, oracle_observation=True,
                     event_history_window=window, chongci_max_hands=CHONGCI_MAX_HANDS)


def _ordered_outcomes_single(config, seed, rng):
    """Ordered round_outcome payloads from the single-env CtypesGoBridge path."""
    from fh_mahjong_ai.bridge import build_bridge
    bridge = build_bridge(config)
    outcomes = []
    try:
        observation = bridge.reset(seed=seed)
        reset_result = bridge.last_reset_result
        if reset_result is not None and reset_result.info.get("round_outcome"):
            outcomes.append(reset_result.info["round_outcome"])
        while True:
            legal = np.flatnonzero(np.asarray(observation.action_mask) > 0)
            result = bridge.step(int(rng.choice(legal)))
            if result.info.get("round_outcome"):
                outcomes.append(result.info["round_outcome"])
            if result.terminated or result.truncated:
                return outcomes, [bool(result.terminated), bool(result.truncated)]
            observation = result.observation
    finally:
        bridge.close()


def _ordered_outcomes_pool(pool, seed, rng):
    """The same sequence through the pool, acting off the pool's own masks."""
    from fh_mahjong_ai.envpool import PoolCommand
    outcomes = []
    result = pool.step([PoolCommand(slot=0, reset_seed=seed)])
    while True:
        meta = result.slots[0]
        if meta.round_outcome is not None:
            outcomes.append(meta.round_outcome)
        if meta.terminated or meta.truncated:
            return outcomes, [bool(meta.terminated), bool(meta.truncated)]
        mask = result.action_masks[result.row_of_slot[0]]
        action = int(rng.choice(np.flatnonzero(mask > 0)))
        result = pool.step([PoolCommand(slot=0, action_id=action)])


@requires_go_lib
@pytest.mark.parametrize("seed", FULL_MATCH_SEEDS)
def test_go_pool_round_outcome_sequence_matches_single_env(seed):
    # Built through make_selfplay_pool, so a dropped chongci_max_hands would
    # run the pool match to 50 hands and diverge from the single env here.
    from fh_mahjong_ai.envpool import make_selfplay_pool
    config = _b2b_env_config(20000)
    ppo_config = PPOConfig(match_mode="chongci", max_steps_per_episode=20000, device="cpu")
    expected, expected_flags = _ordered_outcomes_single(
        config, seed, np.random.default_rng(seed))
    pool = make_selfplay_pool(config, ppo_config, 1)
    try:
        actual, actual_flags = _ordered_outcomes_pool(pool, seed, np.random.default_rng(seed))
    finally:
        pool.close()
    assert actual == expected
    assert actual_flags == expected_flags == [True, False]
    # premise: the terminal hand plus at least one NONTERMINAL hand boundary.
    assert len(expected) == CHONGCI_MAX_HANDS


@requires_go_lib
@pytest.mark.parametrize("seed,max_steps", TRUNCATION_CASES)
def test_go_pool_round_outcome_sequence_matches_single_env_on_truncation(seed, max_steps):
    from fh_mahjong_ai.envpool import GoEnvPool
    config = _b2b_env_config(max_steps)
    expected, expected_flags = _ordered_outcomes_single(
        config, seed, np.random.default_rng(seed))
    pool = GoEnvPool(config, slots=1)
    try:
        actual, actual_flags = _ordered_outcomes_pool(pool, seed, np.random.default_rng(seed))
    finally:
        pool.close()
    assert actual == expected
    assert actual_flags == expected_flags == [False, True]
    # premise: truncation lands AFTER at least one completed hand.
    assert len(expected) >= 1


def test_go_pool_decode_round_outcome_unset_is_none():
    # Decode-level, no Go library needed: an unset proto field decodes as None
    # (never an empty dict), a set one as the bridge's own payload.
    from fh_mahjong_ai.bridge import CtypesGoBridge
    from fh_mahjong_ai.envpool import GoEnvPool
    from fh_mahjong_ai.generated.proto import game_pb2

    config = EnvConfig(bridge_kind="go", event_history_window=0)

    class _Stub:
        env_config = config

    response = game_pb2.EnvPoolStepResponse()
    quiet = response.slots.add()
    quiet.slot = 0
    loud = response.slots.add()
    loud.slot = 1
    loud.terminated = True
    loud.round_outcome.winner_seat = 2
    loud.round_outcome.win_type = game_pb2.ACTION_TSUMO
    loud.round_outcome.total_score = 24
    payout = loud.round_outcome.payouts.add()
    payout.seat = 2
    payout.amount = 24

    decoded = GoEnvPool._decode_response(_Stub(), response)
    assert decoded.slots[0].round_outcome is None
    assert decoded.slots[1].round_outcome == CtypesGoBridge._decode_round_outcome(
        None, loud.round_outcome)
    assert decoded.slots[1].round_outcome["winner_seat"] == 2
    assert decoded.slots[1].round_outcome["win_type_name"] == "ACTION_TSUMO"


class _StubBridge:
    """Bridge whose reset/step results the test dictates."""

    def __init__(self, config, reset_result, step_results):
        self.config = config
        self._reset_result = reset_result
        self._step_results = list(step_results)
        self.last_reset_result = None

    def reset(self, seed=None):
        self.last_reset_result = self._reset_result
        return self._reset_result.observation

    def step(self, action_id):
        return self._step_results.pop(0)

    def close(self):
        pass


def _stub_observation():
    mask = np.zeros(4, dtype=np.int8)
    mask[1] = 1
    return Observation(seat=0, planes=np.zeros((1, 1, 1), dtype=np.float32),
                       scalars=np.zeros(2, dtype=np.float32), action_mask=mask)


def _stub_pool(monkeypatch, reset_result, step_results):
    import fh_mahjong_ai.envpool as envpool_module
    config = EnvConfig(bridge_kind="mock", plane_shape=(1, 1, 1), scalar_features=2,
                       action_space_size=4)
    monkeypatch.setattr(envpool_module, "build_bridge",
                        lambda cfg: _StubBridge(cfg, reset_result, step_results))
    return envpool_module.InProcessEnvPool(config, 1)


def test_inprocess_pool_forwards_round_outcome(monkeypatch):
    from fh_mahjong_ai.envpool import PoolCommand
    outcome = {"is_draw": False, "winner_seat": 1, "win_type": 6,
               "win_type_name": "ACTION_TSUMO", "discarder_seat": 0,
               "total_score": 12, "payouts": [{"seat": 1, "amount": 12}]}
    reset_result = StepResult(observation=_stub_observation(),
                              rewards=np.zeros(4, dtype=np.float32), terminated=False,
                              info={"reset": True})
    step_results = [
        StepResult(observation=_stub_observation(), rewards=np.zeros(4, dtype=np.float32),
                   terminated=False, info={}),
        StepResult(observation=_stub_observation(), rewards=np.zeros(4, dtype=np.float32),
                   terminated=False, info={"round_outcome": outcome}),
    ]
    pool = _stub_pool(monkeypatch, reset_result, step_results)
    try:
        assert pool.step([PoolCommand(slot=0, reset_seed=1)]).slots[0].round_outcome is None
        assert pool.step([PoolCommand(slot=0, action_id=1)]).slots[0].round_outcome is None
        assert pool.step([PoolCommand(slot=0, action_id=1)]).slots[0].round_outcome == outcome
        # a skipped slot reports no outcome
        assert pool.step([PoolCommand(slot=0)]).slots[0].round_outcome is None
    finally:
        pool.close()


def test_inprocess_pool_forwards_reset_terminal_round_outcome(monkeypatch):
    # The reset-terminal case no chongci config constructs on the Go bridge: a
    # match already over when it is reset still carries its outcome, and the
    # placement-bonus fail-closed check downstream depends on seeing it.
    from fh_mahjong_ai.envpool import PoolCommand
    outcome = {"is_draw": True, "winner_seat": 0, "win_type": 0,
               "win_type_name": "ACTION_UNSPECIFIED", "discarder_seat": 0,
               "total_score": 0, "payouts": []}
    reset_result = StepResult(observation=_stub_observation(),
                              rewards=np.zeros(4, dtype=np.float32), terminated=True,
                              info={"reset": True, "round_outcome": outcome})
    pool = _stub_pool(monkeypatch, reset_result, [])
    try:
        meta = pool.step([PoolCommand(slot=0, reset_seed=1)]).slots[0]
        assert meta.terminated and not meta.has_observation
        assert meta.round_outcome == outcome
    finally:
        pool.close()


def test_make_selfplay_pool_env_config_matches_process_collector(monkeypatch):
    # make_selfplay_pool used to drop the three chongci_* fields, so a pooled
    # match would be simulated under different rules than the process
    # collector's. Compare the WHOLE EnvConfig against the one
    # collect_b2b_rollouts hands to build_bridge.
    from fh_mahjong_ai import train_b2b
    from fh_mahjong_ai.envpool import make_selfplay_pool

    window = 8
    env_config = EnvConfig(bridge_kind="mock", match_mode="chongci",
                           max_steps_per_episode=64, oracle_observation=True,
                           event_history_window=window, chongci_starting_score=1500,
                           chongci_bust_threshold=-500, chongci_max_hands=7)
    ppo_config = PPOConfig(match_mode="chongci", max_steps_per_episode=64, device="cpu")

    class _Captured(Exception):
        def __init__(self, config):
            self.config = config

    def _capture(config):
        raise _Captured(config)

    # Patch on the module that CALLS build_bridge (ai/CLAUDE.md, "Patching
    # across the training modules").
    monkeypatch.setattr(train_b2b, "build_bridge", _capture)
    model = SimpleNamespace(model_config=SimpleNamespace(event_window=window),
                            eval=lambda: None)
    with pytest.raises(_Captured) as excinfo:
        train_b2b.collect_b2b_rollouts(env_config, model, ppo_config, base_seed=0)

    pool = make_selfplay_pool(env_config, ppo_config, 1)
    try:
        assert asdict(pool.env_config) == asdict(excinfo.value.config)
    finally:
        pool.close()
    assert pool.env_config.chongci_starting_score == 1500
    assert pool.env_config.chongci_bust_threshold == -500
    assert pool.env_config.chongci_max_hands == 7

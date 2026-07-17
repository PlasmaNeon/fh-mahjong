import os

import numpy as np
import pytest

from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.envpool import PoolCommand, PoolStepResult

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library"
)


def test_search_step_result_extends_pool_step_result():
    from fh_mahjong_ai.searchpool import SearchStepResult

    base = PoolStepResult(
        slots=[],
        planes=np.zeros((0, 39, 42, 1), dtype=np.float32),
        scalars=np.zeros((0, 58), dtype=np.float32),
        action_masks=np.zeros((0, 204), dtype=np.int8),
        row_of_slot={},
    )
    result = SearchStepResult(
        slots=base.slots, planes=base.planes, scalars=base.scalars,
        action_masks=base.action_masks, row_of_slot=base.row_of_slot,
        round_ended={0: True, 1: False},
    )
    assert isinstance(result, PoolStepResult)
    assert result.round_ended == {0: True, 1: False}


def test_searchpool_reuses_envpool_helpers():
    # Requires importing (not duplicating) the envpool dataclasses, and since
    # B2a the whole response decode: step() delegates to
    # GoEnvPool._decode_response instead of importing _empty_result for a
    # duplicated inline decode (which silently dropped event rows).
    import fh_mahjong_ai.envpool as envpool_module
    import fh_mahjong_ai.searchpool as searchpool_module

    assert searchpool_module.PoolCommand is envpool_module.PoolCommand
    assert searchpool_module.SlotMeta is envpool_module.SlotMeta
    assert searchpool_module.PoolStepResult is envpool_module.PoolStepResult
    assert searchpool_module.GoEnvPool is envpool_module.GoEnvPool


def _chongci_config() -> EnvConfig:
    return EnvConfig(
        bridge_kind="go",
        match_mode="chongci",
        oracle_observation=False,
        max_steps_per_episode=64,
    )


@requires_go_lib
def test_go_search_pool_step_shapes_and_determinism():
    from fh_mahjong_ai.bridge import CtypesGoBridge
    from fh_mahjong_ai.searchpool import GoSearchPool

    config = _chongci_config()
    with CtypesGoBridge(config) as bridge:
        bridge.reset(seed=101)

        pool_a = GoSearchPool(bridge, clones=4, seed=7, max_rollout_decisions=64)
        try:
            commands = []
            # First step: discover legal actions per clone via a probe step is not
            # possible without an observation; GoSearchPool clones the *current*
            # decision, so all 4 slots share the same legal action mask as the
            # live bridge's current observation.
            observation = bridge.last_reset_result.observation
            action = int(np.flatnonzero(observation.action_mask > 0)[0])
            for slot in range(4):
                commands.append(PoolCommand(slot=slot, action_id=action))
            result_a = pool_a.step(commands)
        finally:
            pool_a.close()

        assert len({m.slot for m in result_a.slots}) == 4
        assert result_a.planes.shape[1:] == (39, 42, 1)
        assert result_a.planes.shape[0] == len(result_a.row_of_slot)

        pool_b = GoSearchPool(bridge, clones=4, seed=7, max_rollout_decisions=64)
        try:
            result_b = pool_b.step(commands)
        finally:
            pool_b.close()

        np.testing.assert_array_equal(result_a.planes, result_b.planes)
        np.testing.assert_array_equal(result_a.scalars, result_b.scalars)
        np.testing.assert_array_equal(result_a.action_masks, result_b.action_masks)
        assert [(m.slot, m.seat, m.terminated, m.truncated, m.has_observation) for m in result_a.slots] == \
            [(m.slot, m.seat, m.terminated, m.truncated, m.has_observation) for m in result_b.slots]

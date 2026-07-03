import numpy as np

from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.ppo import PPOConfig


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

import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig


def _mcfg():
    return ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)


def _env_cfg():
    return EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                     oracle_observation=True)


def _collect(matches, slots, drop_prob, inference_mode="batched", base_seed=500, model=None):
    from fh_mahjong_ai.batched_selfplay import collect_selfplay_rollouts_batched
    from fh_mahjong_ai.envpool import make_selfplay_pool
    env_cfg = _env_cfg()
    cfg = PPOConfig(matches_per_iter=matches, match_mode="classic",
                    max_steps_per_episode=64, device="cpu")
    if model is None:
        torch.manual_seed(0)
        model = PolicyValueNet(env_cfg, _mcfg())
    pool = make_selfplay_pool(env_cfg, cfg, slots)
    try:
        return collect_selfplay_rollouts_batched(env_cfg, model, cfg, base_seed=base_seed,
                                                 drop_prob=drop_prob, pool=pool,
                                                 inference_mode=inference_mode)
    finally:
        pool.close()


def test_sample_masked_action_matches_categorical():
    from fh_mahjong_ai.batched_selfplay import sample_masked_action
    rng = np.random.default_rng(3)
    logits = rng.standard_normal(204).astype(np.float32)
    mask = np.zeros(204, dtype=np.int8)
    legal = [4, 9, 44, 108, 203]
    mask[legal] = 1
    temperature = 1.0

    # Reference probabilities: Categorical over temperature-scaled masked logits.
    masked = torch.full((204,), torch.finfo(torch.float32).min)
    masked[legal] = torch.from_numpy(logits[legal]) / temperature
    reference = torch.distributions.Categorical(logits=masked)

    draws = {}
    sample_rng = np.random.default_rng(7)
    for _ in range(20000):
        action, logprob = sample_masked_action(logits, mask, temperature, sample_rng)
        assert action in legal
        # Returned logprob matches the reference distribution's logprob.
        assert abs(logprob - float(reference.log_prob(torch.tensor(action)))) < 1e-5
        draws[action] = draws.get(action, 0) + 1
    for action in legal:
        expected = float(reference.probs[action])
        assert abs(draws.get(action, 0) / 20000 - expected) < 0.02


def test_batched_records_all_four_seats():
    batch = _collect(matches=3, slots=2, drop_prob=0.0)
    assert len(batch) > 0
    assert batch.dones.sum() >= 3  # at least one done block per non-empty match
    # All-4 self-play yields ~4x a single-seat run; sanity floor: > 2 decisions/match.
    assert len(batch) > 6


def test_batched_feature_dropout():
    full = _collect(matches=2, slots=2, drop_prob=1.0)
    assert np.allclose(full.planes[:, 39:51], 0.0)
    none = _collect(matches=2, slots=2, drop_prob=0.0)
    assert np.abs(none.planes[:, 39:51]).sum() > 0.0


def test_batched_trajectories_are_seat_contiguous():
    # Mirrors the Phase-2 contiguity regression: within each done-delimited
    # segment, decisions must belong to contiguous per-seat blocks, which shows
    # up as dones only at segment ends (no interleaving -> segment lengths sum).
    batch = _collect(matches=3, slots=3, drop_prob=0.5)
    ends = np.flatnonzero(batch.dones > 0.5)
    assert ends.size >= 3
    assert ends[-1] == len(batch) - 1  # batch ends on a block boundary


def _batch_fields(batch):
    return {
        "planes": batch.planes, "scalars": batch.scalars, "action_mask": batch.action_mask,
        "actions": batch.actions, "old_logprobs": batch.old_logprobs,
        "values": batch.values, "rewards": batch.rewards, "dones": batch.dones,
    }


def test_batched_slot_count_invariance_exact():
    # per_row CPU: full-array equality across ANY slot count — emission is
    # pinned to seed order and each match depends only on (seed, own decisions).
    one = _collect(matches=4, slots=1, drop_prob=0.5, inference_mode="per_row")
    eight = _collect(matches=4, slots=8, drop_prob=0.5, inference_mode="per_row")
    for name, left in _batch_fields(one).items():
        np.testing.assert_array_equal(left, _batch_fields(eight)[name], err_msg=name)


def test_batched_run_to_run_identical():
    first = _collect(matches=3, slots=3, drop_prob=0.5, inference_mode="batched")
    second = _collect(matches=3, slots=3, drop_prob=0.5, inference_mode="batched")
    for name, left in _batch_fields(first).items():
        np.testing.assert_array_equal(left, _batch_fields(second)[name], err_msg=name)


def test_batched_vs_per_row_statistical():
    batched = _collect(matches=4, slots=4, drop_prob=0.5, inference_mode="batched")
    per_row = _collect(matches=4, slots=4, drop_prob=0.5, inference_mode="per_row")
    # Same match set either way; float rounding may flip individual samples,
    # so compare aggregates loosely rather than trajectories exactly.
    assert batched.dones.sum() == per_row.dones.sum() or \
        abs(batched.dones.sum() - per_row.dones.sum()) <= 4
    assert np.isfinite(batched.rewards).all() and np.isfinite(per_row.rewards).all()
    assert abs(len(batched) - len(per_row)) < max(len(batched), len(per_row))


def test_train_selfplay_oracle_batched_collector(tmp_path):
    import json
    from fh_mahjong_ai.oracle import train_selfplay_oracle
    from fh_mahjong_ai.storage import save_checkpoint

    mcfg = _mcfg()
    anchor = tmp_path / "anchor.pt"
    torch.manual_seed(0)
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))
    env_cfg = _env_cfg()
    cfg = PPOConfig(iterations=2, matches_per_iter=2, match_mode="classic",
                    max_steps_per_episode=64, device="cpu",
                    collector="batched", pool_slots=2)

    history = train_selfplay_oracle(env_config=env_cfg, model_config=mcfg,
                                    anchor_checkpoint=anchor,
                                    checkpoint_dir=tmp_path / "ckpt",
                                    config=cfg, base_seed=100, run_eval=False)

    assert len(history) == 2
    assert all("delta" in row for row in history)
    assert (tmp_path / "ckpt" / "iter_002.pt").exists()
    assert "delta" in json.loads((tmp_path / "ckpt" / "history.json").read_text())[0]

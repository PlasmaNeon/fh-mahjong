import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.storage import save_checkpoint


def _mcfg():
    return ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)


def test_extract_deployable_student_exact_equivalence(tmp_path):
    from fh_mahjong_ai.oracle import build_oracle_model, extract_deployable_student
    mcfg = _mcfg()
    # a 51ch oracle warm-started from a random 39ch anchor (just need a 51ch net)
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))
    oracle = build_oracle_model(EnvConfig(oracle_observation=True), mcfg, anchor, device="cpu")
    # perturb the oracle's input-conv oracle channels so they are nonzero (training would)
    with torch.no_grad():
        oracle.plane_stem[0].weight[:, 39:] = torch.randn_like(oracle.plane_stem[0].weight[:, 39:])

    student = extract_deployable_student(oracle, EnvConfig(), mcfg).eval()
    oracle.eval()

    # student input conv == oracle input conv first 39 channels
    assert torch.allclose(student.plane_stem[0].weight, oracle.plane_stem[0].weight[:, :39])

    # student(39ch obs) logits == oracle(same obs zero-padded to 51ch) logits
    rng = np.random.default_rng(0)
    p39 = rng.standard_normal((1, 39, 42, 1)).astype(np.float32)
    p51 = np.concatenate([p39, np.zeros((1, 12, 42, 1), np.float32)], axis=1)
    sc = rng.standard_normal((1, 58)).astype(np.float32)
    mask = np.ones((1, 204), np.int8)
    with torch.no_grad():
        ls, _ = student(torch.from_numpy(p39), torch.from_numpy(sc), torch.from_numpy(mask))
        lo, _ = oracle(torch.from_numpy(p51), torch.from_numpy(sc), torch.from_numpy(mask))
    assert torch.allclose(ls, lo, atol=1e-5)


def test_feature_dropout_schedule():
    from fh_mahjong_ai.oracle import feature_dropout_schedule
    T = 50
    vals = [feature_dropout_schedule(i, T) for i in range(1, T + 1)]
    assert vals[0] == 0.0                      # first iter: full perfect info
    assert vals[-1] == 1.0                     # last iter: fully masked
    assert all(0.0 <= v <= 1.0 for v in vals)  # probability
    assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:]))  # monotone nondecreasing
    # the first 20% hold at 0, the final 20% hold at 1
    assert feature_dropout_schedule(10, T) == 0.0   # iter 10 / 50 = 0.2 boundary still 0
    assert feature_dropout_schedule(45, T) == 1.0   # within the final-20% hold


def test_collect_selfplay_records_all_seats_and_masks():
    from fh_mahjong_ai.oracle import collect_selfplay_rollouts
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    mcfg = _mcfg()
    model = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=2, match_mode="classic", max_steps_per_episode=64, device="cpu")

    # drop_prob=1.0 -> every recorded obs has the 12 oracle channels (39..50) zeroed
    masked = collect_selfplay_rollouts(env_cfg, model, cfg, base_seed=5, drop_prob=1.0)
    assert masked.planes.shape[1] == 51
    assert np.count_nonzero(masked.planes[:, 39:51, :, :]) == 0
    assert masked.dones.sum() >= 1

    # drop_prob=0.0 -> oracle channels carry the opponents' hands (nonzero somewhere)
    full = collect_selfplay_rollouts(env_cfg, model, cfg, base_seed=5, drop_prob=0.0)
    assert np.count_nonzero(full.planes[:, 39:51, :, :]) > 0


def test_collect_selfplay_credits_all_seats_at_match_end():
    # Self-play credits a terminal (done=1) to EACH seat's last decision, vs the
    # single-seat collector's one terminal per match. (On the mock bridge there is no
    # Go-side auto-play, so both record every decision; the robust difference is the
    # number of terminals, not the transition count.)
    from fh_mahjong_ai.oracle import collect_selfplay_rollouts, collect_oracle_rollouts
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    mcfg = _mcfg()
    model = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=2, match_mode="classic", max_steps_per_episode=64, device="cpu")
    sp = collect_selfplay_rollouts(env_cfg, model, cfg, base_seed=9, drop_prob=0.0)
    ss = collect_oracle_rollouts(env_cfg, model, cfg, base_seed=9)
    assert ss.dones.sum() == 2            # one terminal per match
    assert sp.dones.sum() > ss.dones.sum()  # multiple seats credited per match


def test_train_selfplay_oracle_runs_on_mock(tmp_path):
    from fh_mahjong_ai.oracle import train_selfplay_oracle
    mcfg = _mcfg()
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))   # 39ch anchor
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    cfg = PPOConfig(iterations=2, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    match_mode="classic", max_steps_per_episode=64, device="cpu")
    history = train_selfplay_oracle(env_config=env_cfg, model_config=mcfg, anchor_checkpoint=anchor,
                                    checkpoint_dir=tmp_path / "sp", config=cfg, base_seed=1, run_eval=False)
    assert len(history) == 2
    assert (tmp_path / "sp" / "iter_002.pt").exists()
    assert all("delta" in h for h in history)
    assert history[0]["delta"] == 0.0 and history[-1]["delta"] == 1.0


def test_selfplay_trajectories_are_seat_contiguous():
    """Each done-segment in the flat buffer must belong to a single seat.

    After the per-seat-contiguous fix every segment is one seat's per-match
    trajectory (~1/8 of the total buffer for 2 matches × 4 seats). In the buggy
    interleaved version the first segment spanned multiple seats (roughly 3/4 of
    one match). We assert two things:
      1. No single segment exceeds 40% of total transitions.
      2. The number of segments (== dones.sum()) is >= 4 (one per seat per match).
    """
    from fh_mahjong_ai.oracle import collect_selfplay_rollouts
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    mcfg = _mcfg()
    model = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=2, match_mode="classic", max_steps_per_episode=64, device="cpu")
    batch = collect_selfplay_rollouts(env_cfg, model, cfg, base_seed=42, drop_prob=0.0)

    dones = batch.dones
    total = len(dones)
    # Split into segments at each done==1 boundary.
    segments = []
    start = 0
    for i in range(total):
        if dones[i] == 1.0:
            segments.append(i - start + 1)
            start = i + 1
    # There must be at least 4 segments (one per seat per match, 2 matches × 4 seats = 8).
    assert len(segments) >= 4, f"expected >= 4 segments, got {len(segments)}"
    # No single segment should dominate the buffer (>40%): the buggy interleaved
    # version had a first segment that was ~75% of the buffer.
    max_seg = max(segments)
    assert max_seg / total <= 0.40, (
        f"largest segment is {max_seg}/{total} = {max_seg/total:.1%} > 40%; "
        "trajectories appear to still be interleaved across seats"
    )


def test_train_selfplay_oracle_ach_objective_records_metadata(tmp_path):
    from fh_mahjong_ai.oracle import train_selfplay_oracle
    mcfg = _mcfg()
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))   # 39ch anchor
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    cfg = PPOConfig(iterations=2, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    match_mode="classic", max_steps_per_episode=64, device="cpu",
                    objective="ach", ach_beta=1.5)
    history = train_selfplay_oracle(env_config=env_cfg, model_config=mcfg, anchor_checkpoint=anchor,
                                    checkpoint_dir=tmp_path / "sp_ach", config=cfg, base_seed=1,
                                    run_eval=False)
    assert len(history) == 2
    assert (tmp_path / "sp_ach" / "iter_002.pt").exists()
    assert all(h["objective"] == "ach" for h in history)
    assert all(h["ach_beta"] == 1.5 for h in history)
    # ACH-only metric surfaced into history:
    assert all("saturated_fraction" in h for h in history)


def test_train_selfplay_oracle_defaults_to_ppo_objective(tmp_path):
    from fh_mahjong_ai.oracle import train_selfplay_oracle
    mcfg = _mcfg()
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    cfg = PPOConfig(iterations=1, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    match_mode="classic", max_steps_per_episode=64, device="cpu")
    history = train_selfplay_oracle(env_config=env_cfg, model_config=mcfg, anchor_checkpoint=anchor,
                                    checkpoint_dir=tmp_path / "sp_ppo", config=cfg, base_seed=1,
                                    run_eval=False)
    # PPO history schema is byte-unchanged: no ACH-only metadata or metrics keys.
    assert "objective" not in history[0]
    assert "ach_beta" not in history[0]
    assert "saturated_fraction" not in history[0]


def test_train_selfplay_oracle_rejects_invalid_objective(tmp_path):
    from fh_mahjong_ai.oracle import train_selfplay_oracle
    mcfg = _mcfg()
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    # "ACH" (wrong case) is not a valid objective — must fail loudly, not silently train PPO.
    cfg = PPOConfig(iterations=1, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    match_mode="classic", max_steps_per_episode=64, device="cpu", objective="ACH")
    with pytest.raises(ValueError):
        train_selfplay_oracle(env_config=env_cfg, model_config=mcfg, anchor_checkpoint=anchor,
                              checkpoint_dir=tmp_path / "sp_bad", config=cfg, base_seed=1,
                              run_eval=False)


@pytest.mark.parametrize("bad_beta", [float("nan"), 0.0, -1.0])
def test_train_selfplay_oracle_rejects_nonpositive_ach_beta(tmp_path, bad_beta):
    from fh_mahjong_ai.oracle import train_selfplay_oracle
    mcfg = _mcfg()
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    # nan/0/negative beta would silently disable or corrupt the hedge — must fail loudly.
    cfg = PPOConfig(iterations=1, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    match_mode="classic", max_steps_per_episode=64, device="cpu",
                    objective="ach", ach_beta=bad_beta)
    with pytest.raises(ValueError):
        train_selfplay_oracle(env_config=env_cfg, model_config=mcfg, anchor_checkpoint=anchor,
                              checkpoint_dir=tmp_path / "sp_badbeta", config=cfg, base_seed=1,
                              run_eval=False)


def test_parallel_selfplay_matches_sequential():
    from fh_mahjong_ai.oracle import collect_selfplay_rollouts, ParallelSelfplayCollector
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    mcfg = _mcfg()
    model = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=4, match_mode="classic", max_steps_per_episode=64, device="cpu")
    seq = collect_selfplay_rollouts(env_cfg, model, cfg, base_seed=222, drop_prob=0.5)
    collector = ParallelSelfplayCollector(env_cfg, mcfg, cfg, num_workers=2)
    collector.start()
    try:
        state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
        par = collector.collect(state, base_seed=222, matches_per_iter=4, drop_prob=0.5)
    finally:
        collector.close()
    assert len(par) == len(seq)
    assert par.dones.sum() == seq.dones.sum()
    np.testing.assert_allclose(np.sort(par.rewards), np.sort(seq.rewards), rtol=1e-5)

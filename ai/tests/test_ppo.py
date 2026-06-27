from __future__ import annotations

import numpy as np
import pytest
import torch

from fh_mahjong_ai.evaluate import episode_reward_vector
from fh_mahjong_ai.ppo import PPOConfig, masked_policy_distribution
from fh_mahjong_ai.types import Observation, Transition


def _dummy_transition(rewards):
    obs = Observation(seat=0, planes=np.zeros((1, 1, 1), dtype=np.float32),
                      scalars=np.zeros(1, dtype=np.float32),
                      action_mask=np.ones(1, dtype=np.int8), metadata={})
    return Transition(observation=obs, action_id=0,
                      rewards=np.asarray(rewards, dtype=np.float32),
                      next_observation=obs, terminated=False, truncated=False, info={})


def test_episode_reward_vector_sums_per_step_rewards():
    episode = [
        _dummy_transition([0.0, 0.0, 0.0, 0.0]),
        _dummy_transition([1.5, -0.5, 0.0, -1.0]),
        _dummy_transition([0.5, 0.0, -0.5, 0.0]),
    ]
    total = episode_reward_vector(episode, fallback_rewards=np.zeros(4, dtype=np.float32))
    np.testing.assert_allclose(total, [2.0, -0.5, -0.5, -1.0], rtol=1e-6)


def test_episode_reward_vector_empty_uses_fallback():
    total = episode_reward_vector([], fallback_rewards=np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32))
    np.testing.assert_allclose(total, [0.1, 0.2, 0.3, 0.4], rtol=1e-6)


def test_episode_reward_vector_adds_reset_reward_for_nonempty_episode():
    ep = [_dummy_transition([1.0, 0.0, 0.0, -1.0])]
    total = episode_reward_vector(ep, fallback_rewards=np.zeros(4, dtype=np.float32),
                                  reset_rewards=np.array([0.5, 0.0, 0.0, -0.5], dtype=np.float32))
    np.testing.assert_allclose(total, [1.5, 0.0, 0.0, -1.5], rtol=1e-6)


def test_episode_reward_vector_ignores_reset_reward_when_empty():
    total = episode_reward_vector([], fallback_rewards=np.array([0.2, 0.0, 0.0, -0.2], dtype=np.float32),
                                  reset_rewards=np.array([9.0, 9.0, 9.0, 9.0], dtype=np.float32))
    np.testing.assert_allclose(total, [0.2, 0.0, 0.0, -0.2], rtol=1e-6)


def test_ppo_config_defaults():
    cfg = PPOConfig()
    assert cfg.gamma == 0.99
    assert 0.0 < cfg.clip_eps < 1.0
    assert cfg.ppo_epochs >= 1


def test_masked_distribution_zeros_illegal_actions():
    # logits already masked the way PolicyValueNet.forward produces them
    neg = torch.finfo(torch.float32).min
    masked_logits = torch.tensor([[0.5, neg, 0.7, neg]])
    dist = masked_policy_distribution(masked_logits)
    probs = dist.probs[0]
    assert probs[1].item() == pytest.approx(0.0, abs=1e-6)
    assert probs[3].item() == pytest.approx(0.0, abs=1e-6)
    assert probs[0].item() + probs[2].item() == pytest.approx(1.0, abs=1e-6)
    assert torch.isfinite(dist.entropy()).all()


def test_masked_distribution_single_legal_action_has_zero_entropy():
    neg = torch.finfo(torch.float32).min
    masked_logits = torch.tensor([[neg, 1.0, neg]])
    dist = masked_policy_distribution(masked_logits)
    assert dist.entropy().item() == pytest.approx(0.0, abs=1e-5)
    assert dist.probs[0, 1].item() == pytest.approx(1.0, abs=1e-6)


from fh_mahjong_ai.ppo import compute_gae


def test_gae_lambda1_gamma1_single_match_is_monte_carlo():
    rewards = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    values = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    dones = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    adv, ret = compute_gae(rewards, values, dones, gamma=1.0, gae_lambda=1.0)
    np.testing.assert_allclose(ret, [6.0, 5.0, 3.0], rtol=1e-6)
    np.testing.assert_allclose(adv, [6.0, 5.0, 3.0], rtol=1e-6)


def test_gae_resets_at_match_boundary():
    rewards = np.array([1.0, 5.0], dtype=np.float32)
    values = np.array([0.0, 0.0], dtype=np.float32)
    dones = np.array([1.0, 1.0], dtype=np.float32)
    adv, ret = compute_gae(rewards, values, dones, gamma=1.0, gae_lambda=1.0)
    np.testing.assert_allclose(ret, [1.0, 5.0], rtol=1e-6)


from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import RolloutBatch, ppo_update


def _tiny_model():
    env = EnvConfig(action_space_size=4, plane_shape=(2, 3, 1), scalar_features=4)
    mcfg = ModelConfig(channels=4, residual_blocks=1, plane_feature_dim=8,
                       scalar_hidden_dim=8, trunk_hidden_dim=8, value_hidden_dim=8, q_hidden_dim=8)
    return PolicyValueNet(env, mcfg), env


def _synthetic_batch(env, n=16):
    rng = np.random.default_rng(0)
    mask = np.ones((n, env.action_space_size), dtype=np.int8)
    return RolloutBatch(
        planes=rng.standard_normal((n, *env.plane_shape)).astype(np.float32),
        scalars=rng.standard_normal((n, env.scalar_features)).astype(np.float32),
        action_mask=mask,
        actions=rng.integers(0, env.action_space_size, size=n).astype(np.int64),
        old_logprobs=np.full(n, -1.386, dtype=np.float32),  # log(1/4)
        values=np.zeros(n, dtype=np.float32),
        rewards=rng.standard_normal(n).astype(np.float32),
        dones=np.zeros(n, dtype=np.float32),
    )


def test_ppo_update_returns_finite_metrics():
    model, env = _tiny_model()
    batch = _synthetic_batch(env)
    adv = np.ones(len(batch), dtype=np.float32)
    ret = np.zeros(len(batch), dtype=np.float32)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    metrics = ppo_update(model, opt, batch, adv, ret, PPOConfig(minibatch_size=8, ppo_epochs=2, device="cpu"))
    for key in ("policy_loss", "value_loss", "entropy", "approx_kl", "clip_fraction"):
        assert np.isfinite(metrics[key])


def test_ppo_update_increases_prob_of_positive_advantage_action():
    model, env = _tiny_model()
    n = 8
    mask = np.ones((n, env.action_space_size), dtype=np.int8)
    planes = np.zeros((n, *env.plane_shape), dtype=np.float32)
    scalars = np.zeros((n, env.scalar_features), dtype=np.float32)
    with torch.no_grad():
        logits, _ = model(torch.zeros(1, *env.plane_shape), torch.zeros(1, env.scalar_features),
                          torch.ones(1, env.action_space_size, dtype=torch.int8))
        old_lp = float(masked_policy_distribution(logits).log_prob(torch.tensor([2]))[0])
    batch = RolloutBatch(
        planes=planes, scalars=scalars, action_mask=mask,
        actions=np.full(n, 2, dtype=np.int64),
        old_logprobs=np.full(n, old_lp, dtype=np.float32),
        values=np.zeros(n, dtype=np.float32),
        rewards=np.zeros(n, dtype=np.float32),
        dones=np.zeros(n, dtype=np.float32),
    )
    adv = np.ones(n, dtype=np.float32)
    ret = np.zeros(n, dtype=np.float32)
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    ppo_update(model, opt, batch, adv, ret, PPOConfig(minibatch_size=8, ppo_epochs=5, entropy_coef=0.0, normalize_advantages=False, device="cpu"))
    with torch.no_grad():
        logits, _ = model(torch.zeros(1, *env.plane_shape), torch.zeros(1, env.scalar_features),
                          torch.ones(1, env.action_space_size, dtype=torch.int8))
        new_lp = float(masked_policy_distribution(logits).log_prob(torch.tensor([2]))[0])
    assert new_lp > old_lp


from fh_mahjong_ai.ppo import collect_rollouts
from fh_mahjong_ai.ppo import concat_rollout_batches


def test_collect_rollouts_mock_shapes_and_done_at_match_end():
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    learner = PolicyValueNet(env_cfg, mcfg)
    frozen = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=2, match_mode="classic", max_steps_per_episode=64, device="cpu")

    batch = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=123)
    n = len(batch)
    assert n > 0
    for arr in (batch.planes, batch.scalars, batch.action_mask, batch.actions,
                batch.old_logprobs, batch.values, batch.rewards, batch.dones):
        assert arr.shape[0] == n
    assert batch.dones.sum() >= 1
    assert set(np.unique(batch.dones)).issubset({0.0, 1.0})


def test_collect_rollouts_is_reproducible_with_same_seed():
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    learner = PolicyValueNet(env_cfg, mcfg)
    frozen = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=3, match_mode="classic", max_steps_per_episode=64, device="cpu")
    a = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=4242)
    b = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=4242)
    assert len(a) == len(b)
    np.testing.assert_allclose(a.rewards, b.rewards, rtol=1e-6)
    np.testing.assert_array_equal(a.actions, b.actions)


def test_concat_rollout_batches_preserves_rows_and_dones():
    env = EnvConfig(action_space_size=4, plane_shape=(2, 3, 1), scalar_features=4)
    b1 = _synthetic_batch(env, n=5)
    b2 = _synthetic_batch(env, n=7)
    b1.dones[-1] = 1.0
    b2.dones[-1] = 1.0
    merged = concat_rollout_batches([b1, b2])
    assert len(merged) == 12
    assert merged.planes.shape == (12, *env.plane_shape)
    assert merged.dones.sum() == 2.0


def test_concat_rollout_batches_raises_when_all_empty():
    with pytest.raises(RuntimeError):
        concat_rollout_batches([])


from fh_mahjong_ai.ppo import train_ppo
from fh_mahjong_ai.storage import save_checkpoint


def test_train_ppo_persists_history_each_iteration_survives_interruption(tmp_path, monkeypatch):
    import json
    import fh_mahjong_ai.ppo as ppo_mod

    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    # Simulate a crash partway through iteration 2 (after iteration 1 completed).
    real_gae = ppo_mod.compute_gae
    calls = {"n": 0}

    def flaky_gae(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("simulated interruption")
        return real_gae(*args, **kwargs)

    monkeypatch.setattr(ppo_mod, "compute_gae", flaky_gae)

    ckpt = tmp_path / "ppo"
    cfg = PPOConfig(iterations=3, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    eval_interval=100, match_mode="classic", max_steps_per_episode=64, device="cpu")
    with pytest.raises(RuntimeError):
        train_ppo(
            env_config=env_cfg, model_config=mcfg, init_checkpoint=init,
            checkpoint_dir=ckpt, config=cfg, base_seed=1000, run_eval=False,
        )

    # The completed iteration's metrics must survive the crash.
    history_path = ckpt / "history.json"
    assert history_path.exists()
    history = json.loads(history_path.read_text())
    assert len(history) == 1
    assert history[0]["iteration"] == 1
    assert np.isfinite(history[0]["policy_loss"])
    assert (ckpt / "iter_001.pt").exists()


def test_train_ppo_e2e_mock_writes_checkpoint(tmp_path):
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    cfg = PPOConfig(iterations=2, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    eval_interval=100, match_mode="classic", max_steps_per_episode=64, device="cpu")
    metrics = train_ppo(
        env_config=env_cfg, model_config=mcfg, init_checkpoint=init,
        checkpoint_dir=tmp_path / "ppo", config=cfg, base_seed=1000, run_eval=False,
    )
    assert len(metrics) == 2
    assert (tmp_path / "ppo" / "iter_002.pt").exists()
    assert all(np.isfinite(m["policy_loss"]) for m in metrics)


def test_train_ppo_parallel_mock_writes_checkpoint(tmp_path):
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    cfg = PPOConfig(iterations=1, matches_per_iter=4, ppo_epochs=1, minibatch_size=8,
                    eval_interval=100, match_mode="classic", max_steps_per_episode=64,
                    device="cpu", num_workers=2)
    metrics = train_ppo(
        env_config=env_cfg, model_config=mcfg, init_checkpoint=init,
        checkpoint_dir=tmp_path / "ppo", config=cfg, base_seed=1000, run_eval=False,
    )
    assert len(metrics) == 1
    assert (tmp_path / "ppo" / "iter_001.pt").exists()
    assert np.isfinite(metrics[0]["policy_loss"])


def test_cli_train_ppo_mock(tmp_path, monkeypatch):
    import sys
    from fh_mahjong_ai.scripts import train_ppo as cli

    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    argv = [
        "fh-mj-train-ppo",
        "--init-checkpoint", str(init),
        "--checkpoint-dir", str(tmp_path / "ppo"),
        "--iterations", "1", "--matches-per-iter", "2", "--ppo-epochs", "1",
        "--minibatch-size", "8", "--match-mode", "classic", "--bridge-kind", "mock",
        "--max-steps-per-episode", "64", "--no-eval",
        "--model-channels", "8", "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    assert (tmp_path / "ppo" / "iter_001.pt").exists()

    # history is persisted even with eval disabled, and carries no eval keys
    import json
    history = json.loads((tmp_path / "ppo" / "history.json").read_text())
    assert len(history) == 1
    assert "eval_mean_reward" not in history[0]


def test_cli_train_ppo_parallel_mock(tmp_path, monkeypatch):
    import sys
    from fh_mahjong_ai.scripts import train_ppo as cli

    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    argv = [
        "fh-mj-train-ppo",
        "--init-checkpoint", str(init),
        "--checkpoint-dir", str(tmp_path / "ppo"),
        "--iterations", "1", "--matches-per-iter", "4", "--ppo-epochs", "1",
        "--minibatch-size", "8", "--match-mode", "classic", "--bridge-kind", "mock",
        "--max-steps-per-episode", "64", "--no-eval", "--num-workers", "2",
        "--model-channels", "8", "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    assert (tmp_path / "ppo" / "iter_001.pt").exists()


def test_train_ppo_eval_error_recorded_and_logged_single_line(tmp_path, monkeypatch, capsys):
    import fh_mahjong_ai.ppo as ppo_mod

    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    def _boom(*args, **kwargs):
        raise ValueError("eval blew up\nwith a second line")

    monkeypatch.setattr(ppo_mod, "evaluate_duplicate_seats", _boom)

    cfg = PPOConfig(iterations=1, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    eval_interval=1, eval_seeds=2, match_mode="classic",
                    max_steps_per_episode=64, device="cpu")
    history = train_ppo(
        env_config=env_cfg, model_config=mcfg, init_checkpoint=init,
        checkpoint_dir=tmp_path / "ppo", config=cfg, base_seed=1000, run_eval=True,
    )
    # eval failure must be recorded, not abort training
    assert "eval_error" in history[0]
    assert "eval_mean_reward" not in history[0]

    out = capsys.readouterr().out
    iter_lines = [ln for ln in out.splitlines() if ln.startswith("iter 1:")]
    assert len(iter_lines) == 1
    # the full (multi-line) error message must stay on a single log line
    assert "eval blew up" in iter_lines[0]
    assert "with a second line" in iter_lines[0]


def test_cli_train_ppo_writes_history_json_with_eval(tmp_path, monkeypatch, capsys):
    import json
    import sys
    from fh_mahjong_ai.scripts import train_ppo as cli

    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    ckpt_dir = tmp_path / "ppo"
    argv = [
        "fh-mj-train-ppo",
        "--init-checkpoint", str(init),
        "--checkpoint-dir", str(ckpt_dir),
        "--iterations", "1", "--matches-per-iter", "2", "--ppo-epochs", "1",
        "--minibatch-size", "8", "--match-mode", "classic", "--bridge-kind", "mock",
        "--max-steps-per-episode", "64",
        "--eval-interval", "1", "--eval-seeds", "2", "--eval-start-seed", "870000",
        "--model-channels", "8", "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()

    history_path = ckpt_dir / "history.json"
    assert history_path.exists()
    history = json.loads(history_path.read_text())
    assert isinstance(history, list)
    assert len(history) == 1
    entry = history[0]
    # eval ran on iteration 1 (eval_interval=1); eval metrics must be persisted
    assert "eval_mean_reward" in entry
    assert "eval_mean_reward_ci95" in entry
    assert "eval_large_loss_rate" in entry
    for key in ("eval_mean_reward", "eval_mean_reward_ci95", "eval_large_loss_rate"):
        assert np.isfinite(entry[key])

    # eval metrics must also reach the per-iteration training log
    out = capsys.readouterr().out
    iter_lines = [ln for ln in out.splitlines() if ln.startswith("iter 1:")]
    assert len(iter_lines) == 1
    assert "eval_mean_reward=" in iter_lines[0]
    assert "eval_ci95=" in iter_lines[0]


from fh_mahjong_ai.ppo import _seat_step_reward


def test_seat_step_reward_reads_per_seat_vector():
    # env emits a per-seat reward vector; learning seat 0 picks index 0
    assert _seat_step_reward(np.array([-1.4, 0.1, 0.1, 1.2], dtype=np.float32), 0) == pytest.approx(-1.4, abs=1e-6)
    assert _seat_step_reward([0.0, 0.0, 0.0, 0.0], 0) == 0.0
    assert _seat_step_reward(np.zeros(0, dtype=np.float32), 0) == 0.0  # degenerate -> 0


def test_train_ppo_invokes_iteration_callback(tmp_path):
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))
    cfg = PPOConfig(iterations=2, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    eval_interval=100, match_mode="classic", max_steps_per_episode=64, device="cpu")

    seen: list = []
    train_ppo(
        env_config=env_cfg, model_config=mcfg, init_checkpoint=init,
        checkpoint_dir=tmp_path / "ppo", config=cfg, base_seed=7, run_eval=False,
        iteration_callback=lambda m: seen.append(dict(m)),
    )
    assert [m["iteration"] for m in seen] == [1, 2]
    assert all("mean_reward" in m for m in seen)


def test_cli_train_ppo_mlflow_wiring(tmp_path, monkeypatch):
    import contextlib
    import sys
    from fh_mahjong_ai.scripts import train_ppo as cli

    calls = {"start_run": 0, "log_params": 0, "log_metrics": 0, "log_artifact": 0, "enabled": None}

    @contextlib.contextmanager
    def fake_start_run(enabled, **kwargs):
        calls["start_run"] += 1
        calls["enabled"] = enabled
        if not enabled:
            yield None
            return
        run = type("R", (), {"info": type("I", (), {"run_id": "test-run"})()})()
        yield run

    monkeypatch.setattr(cli, "start_run", fake_start_run)
    monkeypatch.setattr(cli, "log_params", lambda *a, **k: calls.__setitem__("log_params", calls["log_params"] + 1))
    monkeypatch.setattr(cli, "log_metrics", lambda *a, **k: calls.__setitem__("log_metrics", calls["log_metrics"] + 1))
    monkeypatch.setattr(cli, "log_artifact", lambda *a, **k: calls.__setitem__("log_artifact", calls["log_artifact"] + 1))

    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    argv = [
        "fh-mj-train-ppo",
        "--init-checkpoint", str(init),
        "--checkpoint-dir", str(tmp_path / "ppo"),
        "--iterations", "2", "--matches-per-iter", "2", "--ppo-epochs", "1",
        "--minibatch-size", "8", "--match-mode", "classic", "--bridge-kind", "mock",
        "--max-steps-per-episode", "64", "--no-eval", "--mlflow",
        "--model-channels", "8", "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()

    assert calls["enabled"] is True
    assert calls["log_params"] == 1
    assert calls["log_metrics"] == 2  # one per iteration via the callback
    assert calls["log_artifact"] >= 1  # history.json (+ final checkpoint)


def test_cli_train_ppo_mlflow_failure_does_not_abort_training(tmp_path, monkeypatch, capsys):
    import contextlib
    import sys
    from fh_mahjong_ai.scripts import train_ppo as cli

    attempts = {"log_metrics": 0}

    @contextlib.contextmanager
    def fake_start_run(enabled, **kwargs):
        run = type("R", (), {"info": type("I", (), {"run_id": "x"})()})()
        yield run if enabled else None

    def boom_log_metrics(*a, **k):
        attempts["log_metrics"] += 1
        raise RuntimeError("mlflow backend down")

    monkeypatch.setattr(cli, "start_run", fake_start_run)
    monkeypatch.setattr(cli, "log_params", lambda *a, **k: None)
    monkeypatch.setattr(cli, "log_metrics", boom_log_metrics)
    monkeypatch.setattr(cli, "log_artifact", lambda *a, **k: None)

    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    argv = [
        "fh-mj-train-ppo",
        "--init-checkpoint", str(init),
        "--checkpoint-dir", str(tmp_path / "ppo"),
        "--iterations", "3", "--matches-per-iter", "2", "--ppo-epochs", "1",
        "--minibatch-size", "8", "--match-mode", "classic", "--bridge-kind", "mock",
        "--max-steps-per-episode", "64", "--no-eval", "--mlflow",
        "--model-channels", "8", "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()  # must NOT raise despite MLflow failing

    # all 3 iterations + checkpoints completed even though tracking blew up
    assert (tmp_path / "ppo" / "iter_003.pt").exists()
    assert (tmp_path / "ppo" / "history.json").exists()
    # tracking self-disabled after the first failure (no repeated attempts/spam)
    assert attempts["log_metrics"] == 1
    assert "MLflow logging failed" in capsys.readouterr().err


def _ppo_mlflow_argv(tmp_path, init, iterations):
    return [
        "fh-mj-train-ppo",
        "--init-checkpoint", str(init),
        "--checkpoint-dir", str(tmp_path / "ppo"),
        "--iterations", str(iterations), "--matches-per-iter", "2", "--ppo-epochs", "1",
        "--minibatch-size", "8", "--match-mode", "classic", "--bridge-kind", "mock",
        "--max-steps-per-episode", "64", "--no-eval", "--mlflow",
        "--model-channels", "8", "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ]


def test_cli_train_ppo_mlflow_init_failure_falls_back_to_untracked(tmp_path, monkeypatch, capsys):
    import sys
    from fh_mahjong_ai.scripts import train_ppo as cli

    def boom_start_run(enabled, **kwargs):
        raise RuntimeError("cannot connect to tracking server")

    def must_not_log(*a, **k):
        raise AssertionError("logging attempted despite failed MLflow init")

    monkeypatch.setattr(cli, "start_run", boom_start_run)
    monkeypatch.setattr(cli, "log_params", must_not_log)
    monkeypatch.setattr(cli, "log_metrics", must_not_log)
    monkeypatch.setattr(cli, "log_artifact", must_not_log)

    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    monkeypatch.setattr(sys, "argv", _ppo_mlflow_argv(tmp_path, init, 2))
    cli.main()  # must NOT raise despite MLflow init blowing up

    assert (tmp_path / "ppo" / "iter_002.pt").exists()
    assert "MLflow init failed" in capsys.readouterr().err


def test_cli_train_ppo_mlflow_finalization_failure_is_tolerated(tmp_path, monkeypatch, capsys):
    import sys
    from fh_mahjong_ai.scripts import train_ppo as cli

    class CMExitRaises:
        def __enter__(self):
            return type("R", (), {"info": type("I", (), {"run_id": "x"})()})()

        def __exit__(self, *exc):
            raise RuntimeError("end_run failed")

    monkeypatch.setattr(cli, "start_run", lambda enabled, **kwargs: CMExitRaises())
    monkeypatch.setattr(cli, "log_params", lambda *a, **k: None)
    monkeypatch.setattr(cli, "log_metrics", lambda *a, **k: None)
    monkeypatch.setattr(cli, "log_artifact", lambda *a, **k: None)

    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    monkeypatch.setattr(sys, "argv", _ppo_mlflow_argv(tmp_path, init, 2))
    cli.main()  # must NOT raise despite MLflow __exit__ blowing up after training

    assert (tmp_path / "ppo" / "iter_002.pt").exists()
    assert (tmp_path / "ppo" / "history.json").exists()
    assert "MLflow finalization failed" in capsys.readouterr().err


def test_cli_train_ppo_mlflow_marks_failed_run_on_training_error(tmp_path, monkeypatch):
    import sys
    from fh_mahjong_ai.scripts import train_ppo as cli

    seen = {"exc_type": "unset"}

    class RecordingCM:
        def __enter__(self):
            return type("R", (), {"info": type("I", (), {"run_id": "x"})()})()

        def __exit__(self, exc_type, exc, tb):
            seen["exc_type"] = exc_type
            return False  # do not suppress

    def boom_train(*a, **k):
        raise RuntimeError("training blew up")

    monkeypatch.setattr(cli, "start_run", lambda enabled, **kwargs: RecordingCM())
    monkeypatch.setattr(cli, "log_params", lambda *a, **k: None)
    monkeypatch.setattr(cli, "log_metrics", lambda *a, **k: None)
    monkeypatch.setattr(cli, "log_artifact", lambda *a, **k: None)
    monkeypatch.setattr(cli, "train_ppo", boom_train)

    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    monkeypatch.setattr(sys, "argv", _ppo_mlflow_argv(tmp_path, init, 2))
    # real training failure must still propagate...
    with pytest.raises(RuntimeError, match="training blew up"):
        cli.main()
    # ...and MLflow finalization must see it (so the run is marked FAILED, not FINISHED)
    assert seen["exc_type"] is RuntimeError

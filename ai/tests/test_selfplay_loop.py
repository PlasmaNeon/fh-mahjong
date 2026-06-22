from __future__ import annotations

from pathlib import Path

import pytest

from fh_mahjong_ai.selfplay_loop import (
    GateOutcome,
    GateThresholds,
    confirm_promote,
    gate_decision,
    screen_pass,
)


def _report(mean, ci95, large_loss, positive):
    return {
        "mean_reward": mean,
        "mean_reward_ci95": ci95,
        "large_loss_rate": large_loss,
        "positive_reward_rate": positive,
    }


def test_screen_pass_allows_candidate_within_margin():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand = _report(-0.03, 0.05, 0.2, 0.45)
    assert screen_pass(cand, best, GateThresholds()) is True


def test_screen_pass_rejects_candidate_below_margin():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand = _report(-0.2, 0.05, 0.2, 0.45)
    assert screen_pass(cand, best, GateThresholds()) is False


def test_confirm_promote_requires_ci_separation():
    best = _report(0.0, 0.05, 0.2, 0.45)
    # candidate mean higher but CI overlaps best mean -> not promoted
    overlap = _report(0.04, 0.06, 0.2, 0.45)
    assert confirm_promote(overlap, best, GateThresholds()) is False
    # candidate CI-separated above best -> promoted
    separated = _report(0.2, 0.05, 0.2, 0.45)
    assert confirm_promote(separated, best, GateThresholds()) is True


def test_confirm_promote_rejects_large_loss_regression():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand = _report(0.3, 0.05, 0.25, 0.45)  # CI-separated but worse tail risk
    assert confirm_promote(cand, best, GateThresholds()) is False


def test_confirm_promote_rejects_positive_rate_drop():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand = _report(0.3, 0.05, 0.2, 0.40)  # positive drop 0.05 > positive_eps 0.02
    assert confirm_promote(cand, best, GateThresholds()) is False


def test_gate_decision_rejects_on_screen_without_confirm():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand_screen = _report(-0.5, 0.05, 0.2, 0.45)
    called = {"confirm": False}

    def confirm_evaluator():
        called["confirm"] = True
        return cand_screen, best

    outcome, cc, bc = gate_decision(cand_screen, best, GateThresholds(), confirm_evaluator)
    assert outcome is GateOutcome.REJECTED_SCREEN
    assert called["confirm"] is False
    assert cc is None and bc is None


def test_gate_decision_promotes_on_confirm():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand_screen = _report(0.1, 0.05, 0.2, 0.45)
    cand_confirm = _report(0.2, 0.05, 0.2, 0.45)
    best_confirm = _report(0.0, 0.05, 0.2, 0.45)

    outcome, cc, bc = gate_decision(
        cand_screen, best, GateThresholds(), lambda: (cand_confirm, best_confirm)
    )
    assert outcome is GateOutcome.PROMOTED
    assert cc == cand_confirm and bc == best_confirm


def test_gate_decision_rejects_on_confirm():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand_screen = _report(0.1, 0.05, 0.2, 0.45)
    cand_confirm = _report(0.02, 0.06, 0.2, 0.45)  # CI overlaps
    best_confirm = _report(0.0, 0.05, 0.2, 0.45)

    outcome, _, _ = gate_decision(
        cand_screen, best, GateThresholds(), lambda: (cand_confirm, best_confirm)
    )
    assert outcome is GateOutcome.REJECTED_CONFIRM


from fh_mahjong_ai.selfplay_loop import LoopLedger


def test_ledger_save_load_round_trip(tmp_path: Path):
    ledger = LoopLedger(
        path=tmp_path / "ledger.json",
        iteration=0,
        fixed_init="/init.pt",
        base_data=["/base"],
        current_best="/init.pt",
        accumulated_selfplay=[],
    )
    ledger.save()
    loaded = LoopLedger.load(tmp_path / "ledger.json")
    assert loaded.iteration == 0
    assert loaded.current_best == "/init.pt"
    assert loaded.base_data == ["/base"]


def test_ledger_record_promotion_updates_best_and_cache(tmp_path: Path):
    ledger = LoopLedger(
        path=tmp_path / "ledger.json",
        iteration=1,
        fixed_init="/init.pt",
        base_data=["/base"],
        current_best="/init.pt",
        accumulated_selfplay=["/sp1"],
    )
    ledger.current_best_eval = {"screen": {"mean_reward": 0.0}, "confirm": {"mean_reward": 0.0}}
    ledger.record_promotion(
        candidate="/iter1/candidate/epoch_003.pt",
        screen={"mean_reward": 0.1},
        confirm={"mean_reward": 0.2},
    )
    assert ledger.current_best == "/iter1/candidate/epoch_003.pt"
    assert ledger.current_best_eval["confirm"]["mean_reward"] == 0.2
    assert ledger.consecutive_non_promotions == 0
    assert ledger.history[-1]["decision"] == "promoted"


def test_ledger_record_rejection_increments_patience(tmp_path: Path):
    ledger = LoopLedger(
        path=tmp_path / "ledger.json",
        iteration=1,
        fixed_init="/init.pt",
        base_data=["/base"],
        current_best="/init.pt",
        accumulated_selfplay=["/sp1"],
    )
    ledger.record_rejection(
        candidate="/iter1/candidate/epoch_003.pt",
        outcome="rejected_screen",
        screen={"mean_reward": -0.5},
        confirm=None,
    )
    assert ledger.current_best == "/init.pt"
    assert ledger.consecutive_non_promotions == 1
    assert ledger.history[-1]["decision"] == "rejected_screen"


from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.selfplay_loop import LoopConfig, evaluate_checkpoint
from fh_mahjong_ai.storage import save_checkpoint


def _tiny_env_model():
    # The mock bridge emits default observation dims (39x42x1 / 58 / 204); use a
    # small ModelConfig for speed but keep the default EnvConfig dims so the model
    # matches the bridge.
    env = EnvConfig(bridge_kind="mock")
    model = ModelConfig(
        channels=8, residual_blocks=1, plane_feature_dim=16,
        scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16,
    )
    return env, model


def test_loop_config_defaults():
    cfg = LoopConfig(
        run_dir=Path("/tmp/run"),
        fixed_init="/init.pt",
        base_data=["/base"],
        initial_best="/init.pt",
    )
    assert cfg.iterations == 5
    assert cfg.screen_seeds == 80
    assert cfg.confirm_seeds == 240
    assert cfg.match_mode == "chongci"


def test_evaluate_checkpoint_returns_gate_metric_keys(tmp_path: Path):
    env, model_cfg = _tiny_env_model()
    ckpt = tmp_path / "m.pt"
    save_checkpoint(ckpt, PolicyValueNet(env, model_cfg))

    report = evaluate_checkpoint(
        checkpoint=ckpt,
        seeds=[1, 2],
        env_config=env,
        model_config=model_cfg,
        device="cpu",
    )
    for key in ("mean_reward", "mean_reward_ci95", "large_loss_rate", "positive_reward_rate"):
        assert key in report


from fh_mahjong_ai.selfplay_loop import generate_iteration_selfplay
from fh_mahjong_ai.storage import read_transition_arrays


def test_generate_iteration_selfplay_writes_shards(tmp_path: Path):
    env, _ = _tiny_env_model()  # bridge_kind="mock"
    # On the mock bridge all seats must be controlled; use random for every seat.
    out = generate_iteration_selfplay(
        env_config=env,
        out_dir=tmp_path / "sp",
        episodes=2,
        start_seed=500,
        best_checkpoint=None,
        seat_policy_values=["0=random", "1=random", "2=random", "3=random"],
        device="cpu",
    )
    arrays = read_transition_arrays(out, keys=("action_ids",))
    assert arrays["action_ids"].shape[0] > 0


from fh_mahjong_ai.selfplay_loop import run_iteration


def test_run_iteration_mock_updates_ledger(tmp_path: Path):
    env, model_cfg = _tiny_env_model()  # bridge_kind="mock"
    init = tmp_path / "init.pt"
    save_checkpoint(init, PolicyValueNet(env, model_cfg))

    cfg = LoopConfig(
        run_dir=tmp_path / "run",
        fixed_init=str(init),
        base_data=[],            # mock: no base data; train on the iteration's self-play only
        initial_best=str(init),
        iterations=1,
        episodes_per_iter=3,
        screen_seeds=2,
        confirm_seeds=2,
        epochs=1,
        batch_size=4,
        match_mode="classic",
        device="cpu",
        bridge_kind="mock",
        max_steps_per_episode=None,
        seat_policy_template=["0=random", "1=random", "2=random", "3=random"],
    )
    ledger = LoopLedger(
        path=cfg.run_dir / "ledger.json",
        iteration=0,
        fixed_init=cfg.fixed_init,
        base_data=cfg.base_data,
        current_best=cfg.initial_best,
        accumulated_selfplay=[],
    )

    outcome = run_iteration(cfg, ledger, env, model_cfg)
    assert outcome in {GateOutcome.PROMOTED, GateOutcome.REJECTED_SCREEN, GateOutcome.REJECTED_CONFIRM}
    # an iteration always appends one history record and one accumulated self-play dir
    assert len(ledger.history) == 1
    assert len(ledger.accumulated_selfplay) == 1
    assert (cfg.run_dir / "iter1" / "candidate").exists()


from fh_mahjong_ai.selfplay_loop import run_loop


def test_run_loop_runs_iterations_and_is_resumable(tmp_path: Path):
    env, model_cfg = _tiny_env_model()
    init = tmp_path / "init.pt"
    save_checkpoint(init, PolicyValueNet(env, model_cfg))

    cfg = LoopConfig(
        run_dir=tmp_path / "run",
        fixed_init=str(init),
        base_data=[],
        initial_best=str(init),
        iterations=2,
        episodes_per_iter=2,
        screen_seeds=2,
        confirm_seeds=2,
        epochs=1,
        batch_size=4,
        match_mode="classic",
        device="cpu",
        bridge_kind="mock",
        max_steps_per_episode=None,
        seat_policy_template=["0=random", "1=random", "2=random", "3=random"],
    )

    ledger = run_loop(cfg, env, model_cfg)
    assert ledger.iteration == 2
    assert (cfg.run_dir / "ledger.json").exists()

    # Resume is a no-op once iterations are exhausted.
    resumed = run_loop(cfg, env, model_cfg, resume=True)
    assert resumed.iteration == 2

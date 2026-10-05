import os

import pytest

from conftest import SMALL_MODEL
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import checkpoint_lookahead_version, model_config_metadata, save_checkpoint

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library")
B2B = dict(**SMALL_MODEL, event_window=8, privileged_critic=True, aux_heads=True)


def _v1_checkpoint(tmp_path):
    model = PolicyValueNet(EnvConfig(lookahead_version=1), ModelConfig(**B2B, lookahead_version=1))
    path = tmp_path / "v1.pt"
    save_checkpoint(path, model, metadata={"model_config": model_config_metadata(model.model_config)})
    return model, path


def test_checkpoint_lookahead_version_reads_metadata(tmp_path):
    _, path = _v1_checkpoint(tmp_path)
    assert checkpoint_lookahead_version(path) == 1
    legacy = tmp_path / "legacy.pt"
    save_checkpoint(legacy, PolicyValueNet(EnvConfig(), ModelConfig(**SMALL_MODEL)))
    assert checkpoint_lookahead_version(legacy) == 0


@requires_go_lib
def test_batched_eval_runs_and_records_version(tmp_path):
    from fh_mahjong_ai.batched_eval import evaluate_duplicate_seats_batched
    model, _ = _v1_checkpoint(tmp_path)
    report = evaluate_duplicate_seats_batched(
        model, seeds=[1, 2], bridge_library_path=os.environ["FH_MAHJONG_BRIDGE_LIB"],
        match_mode="chongci", chongci_max_hands=2, max_steps_per_episode=4000,
        event_history_window=8, lookahead_version=1, slots=2)
    assert report["lookahead_version"] == 1
    with pytest.raises(ValueError, match="lookahead"):
        evaluate_duplicate_seats_batched(
            model, seeds=[1], bridge_library_path=os.environ["FH_MAHJONG_BRIDGE_LIB"],
            event_history_window=8, lookahead_version=0, slots=1)


def test_evaluate_cli_rejects_lookahead_outside_batched_duplicate_seats(tmp_path, monkeypatch, capsys):
    import fh_mahjong_ai.scripts.evaluate as cli
    _, path = _v1_checkpoint(tmp_path)
    monkeypatch.setattr("sys.argv", ["fh-mj-evaluate", "--checkpoint", str(path), "--duplicate-seats",
                                     "--online-episodes", "1", "--model-event-window", "8",
                                     "--event-history-window", "8"])
    with pytest.raises(SystemExit):
        cli.main()
    assert "batched duplicate-seat evaluator" in capsys.readouterr().err
    monkeypatch.setattr("sys.argv", ["fh-mj-evaluate", "--checkpoint", str(path), "--duplicate-seats",
                                     "--batched-eval-slots", "2", "--lookahead-version", "0"])
    with pytest.raises(SystemExit):
        cli.main()
    assert "disagrees with the checkpoint" in capsys.readouterr().err


def test_benchmark_policies_carry_and_match_lookahead_version(tmp_path):
    from fh_mahjong_ai.scripts.benchmark import _build_policies
    _, v1 = _v1_checkpoint(tmp_path)
    v0_model = PolicyValueNet(EnvConfig(), ModelConfig(**B2B))
    v0 = tmp_path / "v0.pt"
    save_checkpoint(v0, v0_model, metadata={"model_config": model_config_metadata(v0_model.model_config)})
    *_, version = _build_policies(v1, "cpu", "none", None)
    assert version == 1
    # A v0 opponent at the v1 table is adapted; a v1 opponent at a v0 table is refused.
    _, _, opponents, _, version = _build_policies(v1, "cpu", "none", v0)
    assert version == 1 and opponents["lookahead_adapter"]["plane_channels"] == 39
    with pytest.raises(ValueError, match="lookahead_version"):
        _build_policies(v0, "cpu", "none", v1)

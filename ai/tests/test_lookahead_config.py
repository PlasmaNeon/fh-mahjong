import dataclasses
import os

import numpy as np
import pytest

from fh_mahjong_ai.config import EnvConfig, ModelConfig, observation_plane_channels

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library")


def test_plane_shape_resolves_from_version():
    assert EnvConfig().plane_shape == (39, 42, 1)
    assert EnvConfig(oracle_observation=True).plane_shape == (51, 42, 1)
    assert EnvConfig(lookahead_version=1).plane_shape == (52, 42, 1)
    assert EnvConfig(lookahead_version=1, oracle_observation=True).plane_shape == (64, 42, 1)
    assert EnvConfig(lookahead_version=1).policy_channels == 52
    assert EnvConfig(oracle_observation=True).policy_channels == 39
    assert observation_plane_channels(True, 1) == 64


def test_replace_toggling_oracle_reresolves_version_one():
    base = EnvConfig(lookahead_version=1)
    assert dataclasses.replace(base, oracle_observation=True).plane_shape == (64, 42, 1)
    oracle = EnvConfig(lookahead_version=1, oracle_observation=True)
    assert dataclasses.replace(oracle, oracle_observation=False).plane_shape == (52, 42, 1)


def test_version_zero_keeps_explicit_shapes():
    assert EnvConfig(plane_shape=(51, 42, 1)).plane_shape == (51, 42, 1)
    assert EnvConfig(plane_shape=(2, 3, 1)).plane_shape == (2, 3, 1)


def test_bad_versions_and_shapes_raise():
    with pytest.raises(ValueError, match="lookahead_version"):
        EnvConfig(lookahead_version=2)
    with pytest.raises(ValueError, match="plane_shape"):
        EnvConfig(lookahead_version=1, plane_shape=(40, 42, 1))
    with pytest.raises(ValueError, match="lookahead_version"):
        ModelConfig(lookahead_version=3)


def test_legacy_resume_echo_reads_version_zero():
    from fh_mahjong_ai.ppo import PPOConfig
    from fh_mahjong_ai.train_state import _train_b2b_config_echo, _validate_resume_config_echo
    current = _train_b2b_config_echo(PPOConfig(), ModelConfig(), EnvConfig())
    legacy = {section: dict(values) for section, values in current.items()}
    del legacy["env_config"]["lookahead_version"]
    del legacy["model_config"]["lookahead_version"]
    _validate_resume_config_echo(current, legacy)  # admitted: legacy runs had no look-ahead
    changed = _train_b2b_config_echo(PPOConfig(), ModelConfig(lookahead_version=1),
                                     EnvConfig(lookahead_version=1))
    with pytest.raises(Exception, match="lookahead_version"):
        _validate_resume_config_echo(changed, current)


@requires_go_lib
def test_go_bridge_emits_version_one_planes():
    from fh_mahjong_ai.bridge import build_bridge
    from fh_mahjong_ai.env import MahjongEnv
    config = EnvConfig(bridge_kind="go", bridge_library_path=os.environ["FH_MAHJONG_BRIDGE_LIB"],
                       learning_seats=(0, 1, 2, 3), auto_play_heuristics=False, lookahead_version=1)
    observation = MahjongEnv(config, build_bridge(config)).reset(seed=5)
    assert observation.planes.shape == (52, 42, 1)
    assert np.any(observation.planes[39:52] != 0)


def test_train_cli_threads_lookahead_version(monkeypatch, tmp_path):
    import fh_mahjong_ai.scripts.train_b2b as cli
    seen = {}
    monkeypatch.setattr(cli, "train_b2b", lambda **kwargs: seen.update(kwargs))
    monkeypatch.setattr("sys.argv", [
        "fh-mj-train-b2b", "--champion", str(tmp_path / "init.pt"),
        "--checkpoint-dir", str(tmp_path / "ckpt"), "--event-window", "8",
        "--lookahead-version", "1", "--bridge-kind", "mock"])
    cli.main()
    assert seen["env_config"].lookahead_version == 1
    assert seen["env_config"].plane_shape == (64, 42, 1)
    assert seen["model_config"].lookahead_version == 1


def test_stale_bridge_without_lookahead_planes_raises():
    from fh_mahjong_ai.bridge import BridgeError, CtypesGoBridge
    from fh_mahjong_ai.generated.proto import game_pb2

    class _Stub:
        pass

    stub = _Stub()
    stub.config = EnvConfig(bridge_kind="go", lookahead_version=1, oracle_observation=True)
    stale = game_pb2.SeatObservation(  # a pre-look-ahead bridge ignores the field: 51 channels
        seat=0, planes=[0.0] * (51 * 42), plane_channels=51, plane_height=42, plane_width=1,
        scalars=[0.0] * 58, action_mask=bytes(204))
    with pytest.raises(BridgeError, match="predates look-ahead"):
        CtypesGoBridge._decode_observation(stub, stale)

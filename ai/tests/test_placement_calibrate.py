import json

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import save_checkpoint
from fh_mahjong_ai.placement_bonus import PLACEMENT_RESHAPE_VALUES
from fh_mahjong_ai.scripts.placement_calibrate import run_calibration

# `tests` has no __init__.py so it is not importable as a package; the brief
# permits copying the SMALL_MODEL dict literal instead of importing it from
# tests.test_b2b_training. Keep in sync with ai/tests/conftest.py's SMALL_MODEL.
SMALL_MODEL = dict(
    channels=16,
    residual_blocks=1,
    plane_feature_dim=32,
    scalar_hidden_dim=16,
    trunk_hidden_dim=32,
    value_hidden_dim=16,
    q_hidden_dim=16,
)


def test_run_calibration_mock_classic(tmp_path):
    # Raw 39ch champion exactly as test_b2b_training._champion builds it.
    env39 = EnvConfig(bridge_kind="mock")
    save_checkpoint(tmp_path / "champion.pt", PolicyValueNet(env39, ModelConfig(**SMALL_MODEL)))
    env = EnvConfig(bridge_kind="mock", match_mode="classic", event_history_window=8,
                    oracle_observation=True, max_steps_per_episode=64)
    mcfg = ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True, aux_heads=True)
    out = tmp_path / "calib.json"
    report = run_calibration(env, mcfg, tmp_path / "champion.pt", output=out, matches=2,
                             require_matches=2, base_seed=720000, num_workers=1,
                             collect_dispatch_chunk=0, k=0.5, gamma=0.99, gae_lambda=0.95,
                             device="cpu")
    assert report["calibration"]["num_matches"] == 2 and report["calibration"]["num_records"] == 8
    assert report["gates"]["all_pass"] in (True, False)
    assert report["collection_digest"] and report["values"] == list(PLACEMENT_RESHAPE_VALUES)
    assert json.loads(out.read_text())["calibration"]["lambda"] == report["calibration"]["lambda"]

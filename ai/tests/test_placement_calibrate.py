import json

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import save_checkpoint
from fh_mahjong_ai.placement_bonus import PLACEMENT_RESHAPE_VALUES
from fh_mahjong_ai.scripts.placement_calibrate import run_calibration
from conftest import SMALL_MODEL


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
    assert report["calibration"]["lambda"] > 0
    assert report["bonus_rms"] > 0
    assert report["gates"]["rms_ratio"] != 1.0
    assert report["collection_digest"] and report["values"] == list(PLACEMENT_RESHAPE_VALUES)
    assert json.loads(out.read_text())["calibration"]["lambda"] == report["calibration"]["lambda"]

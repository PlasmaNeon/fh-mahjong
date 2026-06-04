from __future__ import annotations

from pathlib import Path

import numpy as np
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.serve_policy import PolicyHolder, observation_from_json
from fh_mahjong_ai.serving import CheckpointPolicy, run_bridge_serving_smoke
from fh_mahjong_ai.storage import save_checkpoint
from fh_mahjong_ai.types import Observation


def _checkpoint(tmp_path: Path) -> Path:
    path = tmp_path / "model.pt"
    save_checkpoint(path, PolicyValueNet(EnvConfig(), ModelConfig()), step=7)
    return path


def test_checkpoint_policy_selects_legal_masked_action(tmp_path: Path) -> None:
    policy = CheckpointPolicy.from_checkpoint(_checkpoint(tmp_path))
    mask = np.zeros(204, dtype=np.int8)
    mask[5:8] = 1
    observation = Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(42, dtype=np.float32),
        action_mask=mask,
    )

    action = policy.choose(observation)

    assert action.action_id in observation.legal_actions
    assert action.checkpoint_step == 7


def test_checkpoint_policy_rejects_empty_mask(tmp_path: Path) -> None:
    policy = CheckpointPolicy.from_checkpoint(_checkpoint(tmp_path))
    observation = Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(42, dtype=np.float32),
        action_mask=np.zeros(204, dtype=np.int8),
    )

    try:
        policy.choose(observation)
    except ValueError as exc:
        assert "no legal actions" in str(exc)
    else:
        raise AssertionError("expected empty mask to be rejected")


def test_serving_smoke_uses_bridge_validation(tmp_path: Path) -> None:
    policy = CheckpointPolicy.from_checkpoint(_checkpoint(tmp_path))

    report = run_bridge_serving_smoke(policy, episodes=2, start_seed=3, bridge_kind="mock", max_decisions=4)

    assert report["episodes"] == 2
    assert report["decisions"] > 0


def test_policy_holder_hot_swaps_checkpoint(tmp_path: Path) -> None:
    first = tmp_path / "a.pt"
    second = tmp_path / "b.pt"
    save_checkpoint(first, PolicyValueNet(EnvConfig(), ModelConfig()), step=1)
    save_checkpoint(second, PolicyValueNet(EnvConfig(), ModelConfig()), step=2)

    holder = PolicyHolder(
        CheckpointPolicy.from_checkpoint(first),
        manifest_path=tmp_path / "manifest.json",
    )
    assert holder.policy.checkpoint_step == 1

    holder.reload(checkpoint=str(second))
    assert holder.policy.checkpoint_step == 2
    assert holder.policy.checkpoint_path == second


def test_policy_holder_failed_reload_keeps_previous(tmp_path: Path) -> None:
    good = tmp_path / "good.pt"
    save_checkpoint(good, PolicyValueNet(EnvConfig(), ModelConfig()), step=5)
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(good), manifest_path=tmp_path / "m.json")

    try:
        holder.reload(checkpoint=str(tmp_path / "does_not_exist.pt"))
    except Exception:
        pass
    else:
        raise AssertionError("expected reload of a missing checkpoint to fail")

    # The previous model is still serving.
    assert holder.policy.checkpoint_step == 5
    assert holder.policy.checkpoint_path == good


def test_observation_from_json_validates_shapes() -> None:
    payload = {
        "seat": 1,
        "planes": np.zeros((39, 42, 1), dtype=np.float32).tolist(),
        "scalars": np.zeros(42, dtype=np.float32).tolist(),
        "action_mask": np.ones(204, dtype=np.int8).tolist(),
    }

    observation = observation_from_json(payload)

    assert observation.seat == 1
    assert observation.planes.shape == (39, 42, 1)
    assert observation.action_mask.shape == (204,)

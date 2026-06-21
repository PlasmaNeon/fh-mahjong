from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.train_branch_preference_policy import (
    BranchPreferenceTrainConfig,
    train_branch_preference_policy,
)
from fh_mahjong_ai.storage import save_checkpoint


def test_train_branch_preference_policy_writes_checkpoint_and_report(tmp_path: Path) -> None:
    env_config = EnvConfig(action_space_size=16, plane_shape=(2, 3, 1), scalar_features=4)
    model_config = ModelConfig(
        channels=4,
        residual_blocks=1,
        plane_feature_dim=8,
        scalar_hidden_dim=8,
        trunk_hidden_dim=8,
        value_hidden_dim=8,
        q_hidden_dim=8,
        pool_planes=False,
    )
    data_dir = tmp_path / "branch-cf"
    data_dir.mkdir()
    rows = 8
    rng = np.random.default_rng(0)
    np.savez(
        data_dir / "transitions-00000.npz",
        planes=rng.standard_normal((rows, *env_config.plane_shape)).astype(np.float32),
        scalars=rng.standard_normal((rows, env_config.scalar_features)).astype(np.float32),
        action_mask=np.ones((rows, env_config.action_space_size), dtype=np.int8),
        action_ids=np.zeros(rows, dtype=np.int64),
        pairwise_preferred_action_ids=np.asarray([1, 2, 3, 4, 5, 6, 7, 8], dtype=np.int64),
        pairwise_avoided_action_ids=np.asarray([8, 7, 6, 5, 4, 3, 2, 1], dtype=np.int64),
        pairwise_reward_delta_targets=np.linspace(0.1, 0.8, rows, dtype=np.float32),
        episode_index=np.arange(rows, dtype=np.int64),
    )
    (data_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "format": "npz_shards",
                "compressed": False,
                "shard_size": rows,
                "transitions": rows,
                "shards": [{"path": "transitions-00000.npz", "transitions": rows}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    init_checkpoint = tmp_path / "anchor.pt"
    save_checkpoint(init_checkpoint, PolicyValueNet(env_config, model_config), step=3)
    report_path = tmp_path / "reports" / "branch_pref.json"
    checkpoint_dir = tmp_path / "checkpoints"

    report = train_branch_preference_policy(
        data_paths=[data_dir],
        init_checkpoint=init_checkpoint,
        checkpoint_dir=checkpoint_dir,
        config=BranchPreferenceTrainConfig(
            batch_size=4,
            learning_rate=1e-3,
            epochs=1,
            steps_per_epoch=2,
            validation_mod=2,
            device="cpu",
            q_weight=0.25,
            anchor_kl_weight=0.01,
            reward_gap_weight=0.5,
        ),
        model_config=model_config,
        report_output=report_path,
    )

    assert report["method"] == "branch_preference_policy"
    assert report["init_checkpoint_step"] == 3
    assert report["validation"]["rows"] > 0
    assert "policy_rank" in report["validation"]
    assert (checkpoint_dir / "epoch_001.pt").exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["rows"] == rows

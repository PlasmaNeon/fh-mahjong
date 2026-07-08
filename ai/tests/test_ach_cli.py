from __future__ import annotations

import json
from pathlib import Path

import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import save_checkpoint
import fh_mahjong_ai.scripts.train_selfplay_oracle as cli


def test_cli_threads_ach_objective_into_training(tmp_path, monkeypatch):
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))   # 39ch anchor
    ckpt = tmp_path / "sp"
    argv = [
        "fh-mj-train-selfplay-oracle",
        "--anchor-checkpoint", str(anchor),
        "--checkpoint-dir", str(ckpt),
        "--bridge-kind", "mock",
        "--match-mode", "classic",
        "--max-steps-per-episode", "64",
        "--iterations", "1",
        "--matches-per-iter", "2",
        "--num-workers", "1",
        "--ppo-epochs", "1",
        "--minibatch-size", "8",
        "--device", "cpu",
        "--objective", "ach",
        "--ach-beta", "1.25",
        "--model-channels", "8",
        "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "16",
        "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "16",
        "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ]
    monkeypatch.setattr("sys.argv", argv)
    cli.main()
    history = json.loads((ckpt / "history.json").read_text())
    assert history[0]["objective"] == "ach"
    assert history[0]["ach_beta"] == 1.25

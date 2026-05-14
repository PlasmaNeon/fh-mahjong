from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fh_mahjong_ai.scripts.train_bc import train_bc
from fh_mahjong_ai.storage import write_transitions_jsonl
from fh_mahjong_ai.types import Observation, Transition


def _make_dataset(path: Path, n: int = 20) -> None:
    """Write n fake transitions that are valid for training."""
    transitions = []
    for i in range(n):
        obs = Observation(
            seat=0,
            planes=np.random.default_rng(i).standard_normal((39, 42, 1)).astype(np.float32),
            scalars=np.random.default_rng(i).standard_normal(29).astype(np.float32),
            action_mask=np.ones(204, dtype=np.int8),
        )
        transitions.append(
            Transition(
                observation=obs,
                action_id=i % 204,
                rewards=np.zeros(4, dtype=np.float32),
                next_observation=obs,
                terminated=(i == n - 1),
                info={
                    "episode_index": i // 5,
                    "terminal_rewards": np.asarray([5, -2, -1, -2], dtype=np.float32),
                },
            )
        )
    write_transitions_jsonl(path, transitions)


def test_train_bc_runs_and_saves_checkpoint(tmp_path: Path) -> None:
    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    _make_dataset(data_path, n=20)

    metrics = train_bc(
        data_path=data_path,
        checkpoint_dir=ckpt_dir,
        epochs=2,
        batch_size=8,
        learning_rate=1e-3,
        device="cpu",
        log_interval=1,
    )

    assert len(metrics) > 0
    assert (ckpt_dir / "epoch_002.pt").exists()


def test_train_bc_writes_validation_report(tmp_path: Path) -> None:
    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    report_path = tmp_path / "reports" / "bc.json"
    _make_dataset(data_path, n=20)

    train_bc(
        data_path=data_path,
        checkpoint_dir=ckpt_dir,
        epochs=1,
        batch_size=8,
        learning_rate=1e-3,
        device="cpu",
        validation_fraction=0.25,
        split_seed=2,
        report_path=report_path,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["method"] == "behavior_cloning"
    assert report["train_transitions"] == 15
    assert report["validation_transitions"] == 5
    assert report["epochs"][0]["validation"]["total_transitions"] == 5
    assert (ckpt_dir / "epoch_001.pt").exists()


def test_train_bc_respects_resume(tmp_path: Path) -> None:
    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    _make_dataset(data_path, n=20)

    train_bc(data_path=data_path, checkpoint_dir=ckpt_dir, epochs=1, batch_size=8, device="cpu")
    assert (ckpt_dir / "epoch_001.pt").exists()

    # Resume from epoch 1, train to epoch 2
    metrics = train_bc(
        data_path=data_path,
        checkpoint_dir=ckpt_dir,
        epochs=2,
        batch_size=8,
        device="cpu",
        resume=True,
    )
    assert (ckpt_dir / "epoch_002.pt").exists()

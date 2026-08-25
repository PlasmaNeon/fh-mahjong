from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fh_mahjong_ai.scripts.train_bc import train_bc
from fh_mahjong_ai.storage import read_transitions_jsonl, write_transitions_jsonl, write_transitions_npz_shards
from fh_mahjong_ai.types import Observation, Transition


def _make_dataset(path: Path, n: int = 20) -> None:
    """Write n fake transitions that are valid for training."""
    transitions = []
    for i in range(n):
        obs = Observation(
            seat=0,
            planes=np.random.default_rng(i).standard_normal((39, 42, 1)).astype(np.float32),
            scalars=np.random.default_rng(i).standard_normal(42).astype(np.float32),
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


def test_train_bc_runs_from_npz_shards(tmp_path: Path) -> None:
    data_path = tmp_path / "data.jsonl"
    shard_dir = tmp_path / "shards"
    ckpt_dir = tmp_path / "checkpoints"
    _make_dataset(data_path, n=20)
    write_transitions_npz_shards(shard_dir, read_transitions_jsonl(data_path), shard_size=7)

    train_bc(
        data_path=shard_dir,
        checkpoint_dir=ckpt_dir,
        epochs=1,
        batch_size=8,
        learning_rate=1e-3,
        device="cpu",
        validation_fraction=0.25,
        split_seed=2,
    )

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


def test_train_bc_accepts_model_config_and_records_it(tmp_path: Path) -> None:
    import json

    import torch
    from fh_mahjong_ai.config import ModelConfig
    from fh_mahjong_ai.model import infer_model_config

    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    report_path = tmp_path / "report.json"
    _make_dataset(data_path, n=20)
    model_config = ModelConfig(channels=8, residual_blocks=2, kernel_width=1,
                               event_window=8, privileged_critic=True, aux_heads=True)
    train_bc(data_path=data_path, checkpoint_dir=ckpt_dir, epochs=1, batch_size=8,
             device="cpu", model_config=model_config, report_path=report_path)
    payload = torch.load(ckpt_dir / "epoch_001.pt", map_location="cpu")
    assert payload["metadata"]["model_config"]["kernel_width"] == 1
    assert infer_model_config(payload["model"], payload["metadata"]) == model_config
    assert "event_encoder.gru.weight_ih_l0" in payload["model"]

    report = json.loads(report_path.read_text(encoding="utf-8"))
    epoch_report = report["epochs"][0]
    assert epoch_report["validation_events"] == "zeroed"
    assert isinstance(epoch_report["validation"], dict)
    assert "agreement_rate" in epoch_report["validation"]


def test_train_bc_default_model_config_is_unchanged(tmp_path: Path) -> None:
    import torch
    from fh_mahjong_ai.config import ModelConfig

    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    _make_dataset(data_path, n=20)
    train_bc(data_path=data_path, checkpoint_dir=ckpt_dir, epochs=1, batch_size=8, device="cpu")
    payload = torch.load(ckpt_dir / "epoch_001.pt", map_location="cpu")
    assert payload["metadata"]["model_config"] == ModelConfig().__dict__


def test_bc_checkpoint_initialises_a_scratch_b2b_run_with_matching_logits(tmp_path: Path) -> None:
    """End-to-end across the two stages the scratch lap actually runs: a real
    `fh-mj-train-bc` checkpoint, loaded by `fh-mj-train-b2b --init-from-bc`,
    must reproduce the BC policy's logits at step 0.

    The per-function unit tests build their BC checkpoint by hand from an
    untrained `PolicyValueNet`; only this one proves the file `train_bc`
    itself writes (its metadata block, its key names, its trained weights) is
    what `build_scratch_model` accepts. The BC net is forwarded with
    `events=None` (how BC trains); the scratch net gets a real event batch,
    and parity holds because `trunk.0`'s event columns are zeroed.
    """
    import torch
    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.storage import load_checkpoint
    from fh_mahjong_ai.train_b2b import build_scratch_model

    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    _make_dataset(data_path, n=20)
    cfg = ModelConfig(channels=8, residual_blocks=2, kernel_width=1, event_window=8,
                      privileged_critic=True, aux_heads=True)
    train_bc(data_path=data_path, checkpoint_dir=ckpt_dir, epochs=1, batch_size=8,
             device="cpu", model_config=cfg)
    bc_path = ckpt_dir / "epoch_001.pt"

    scratch = build_scratch_model(EnvConfig(bridge_kind="mock"), cfg, bc_checkpoint=bc_path)
    bc_model = PolicyValueNet(EnvConfig(bridge_kind="mock"), cfg)
    load_checkpoint(bc_path, bc_model)
    bc_model.eval()

    rng = np.random.default_rng(19)
    planes = torch.from_numpy(rng.random((4, 39, 42, 1), dtype=np.float32))
    scalars = torch.from_numpy(rng.random((4, 58), dtype=np.float32))
    mask = torch.ones((4, 204), dtype=torch.int8)
    events = torch.from_numpy(rng.integers(0, 0x10000, size=(4, 8), dtype=np.uint32).astype(np.int64))
    lengths = torch.full((4,), 8, dtype=torch.int64)

    with torch.no_grad():
        expected, _ = bc_model(planes, scalars, mask)  # BC's own forward: events=None
        got, _ = scratch(planes, scalars, mask, events=events, event_lengths=lengths)
    assert torch.allclose(expected, got, atol=1e-5)

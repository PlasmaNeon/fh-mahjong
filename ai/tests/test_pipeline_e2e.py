"""End-to-end pipeline test using mock bridge."""
from __future__ import annotations

from pathlib import Path

from fh_mahjong_ai.scripts.run_pipeline import run_pipeline


def test_full_pipeline_mock(tmp_path: Path) -> None:
    report = run_pipeline(
        episodes=4,
        start_seed=1,
        epochs=2,
        batch_size=8,
        eval_episodes=2,
        bridge_kind="mock",
        output_dir=tmp_path,
        device="cpu",
    )

    # Data was generated
    assert (tmp_path / "data" / "heuristic.jsonl").exists()

    # Model was trained and checkpointed
    assert (tmp_path / "checkpoints" / "epoch_002.pt").exists()

    # Evaluation ran
    assert "agreement_rate" in report
    assert "online_avg_reward" in report
    assert 0.0 <= report["agreement_rate"] <= 1.0

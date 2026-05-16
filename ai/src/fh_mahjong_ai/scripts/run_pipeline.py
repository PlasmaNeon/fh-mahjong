"""Orchestrate the full BC pipeline: generate → train → evaluate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.evaluate import compute_action_agreement, evaluate_duplicate_seats
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.generate_data import generate_dataset
from fh_mahjong_ai.scripts.train_bc import train_bc
from fh_mahjong_ai.storage import load_checkpoint, read_transitions


def run_pipeline(
    episodes: int = 100,
    start_seed: int = 1,
    epochs: int = 10,
    batch_size: int = 64,
    eval_episodes: int = 20,
    bridge_kind: str = "go",
    bridge_library_path: Optional[Path] = None,
    output_dir: Path = Path("output"),
    device: str = "cpu",
    validation_fraction: float = 0.2,
    split_seed: int = 0,
    report_output: Optional[Path] = None,
) -> dict:
    """Run the full pipeline and return a combined report."""
    data_dir = output_dir / "data"
    ckpt_dir = output_dir / "checkpoints"
    report_dir = output_dir / "reports"
    data_path = data_dir / "heuristic.jsonl"
    if report_output is None:
        report_output = report_dir / "pipeline_report.json"

    # Step 1: Generate data
    print("=" * 40)
    print("STEP 1: Generating heuristic trajectories")
    print("=" * 40)
    gen_stats = generate_dataset(
        episodes=episodes,
        start_seed=start_seed,
        output_path=data_path,
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
    )
    print(f"Generated {gen_stats['transitions']} transitions")

    # Step 2: Train BC
    print("\n" + "=" * 40)
    print("STEP 2: Training behavior cloning model")
    print("=" * 40)
    metrics = train_bc(
        data_path=data_path,
        checkpoint_dir=ckpt_dir,
        epochs=epochs,
        batch_size=batch_size,
        device=device,
        log_interval=max(1, (gen_stats["transitions"] // batch_size) // 5),
        validation_fraction=validation_fraction,
        split_seed=split_seed,
        report_path=report_dir / "bc_training.json",
    )

    # Step 3: Evaluate
    print("\n" + "=" * 40)
    print("STEP 3: Evaluating trained model")
    print("=" * 40)
    model = PolicyValueNet(EnvConfig(), ModelConfig()).to(device)
    latest_ckpt = sorted(ckpt_dir.glob("epoch_*.pt"))[-1]
    load_checkpoint(latest_ckpt, model)

    transitions = read_transitions(data_path)
    offline_report = compute_action_agreement(model, transitions, device=device)
    print(f"Action agreement: {offline_report['agreement_rate']:.2%}")
    print(f"Top-3 agreement: {offline_report['top3_agreement_rate']:.2%}")
    for family, family_report in offline_report["family_agreement"].items():
        print(
            f"{family} agreement: {family_report['agreement_rate']:.2%} "
            f"top-3={family_report['top3_agreement_rate']:.2%} "
            f"n={family_report['total']}"
        )

    online_report = {"avg_reward": 0.0, "win_count": 0, "episodes": 0}
    if eval_episodes > 0:
        eval_seeds = list(range(10000, 10000 + eval_episodes))
        online_report = evaluate_duplicate_seats(
            model=model,
            seeds=eval_seeds,
            bridge_kind=bridge_kind,
            bridge_library_path=bridge_library_path,
            device=device,
        )
        print(f"Online avg reward: {online_report['avg_reward']}")
        print(f"Online wins: {online_report['win_count']}/{online_report['episodes']}")
        print(f"Online large-loss rate: {online_report['large_loss_rate']:.2%}")

    report = {
        "data_transitions": gen_stats["transitions"],
        "data_manifest_path": gen_stats["manifest_path"],
        "bc_training_report_path": str(report_dir / "bc_training.json"),
        "pipeline_report_path": str(report_output),
        "final_loss": metrics[-1].loss if metrics else 0.0,
        "agreement_rate": offline_report["agreement_rate"],
        "top3_agreement_rate": offline_report["top3_agreement_rate"],
        "family_agreement": offline_report["family_agreement"],
        "online_avg_reward": online_report["avg_reward"],
        "online_wins": online_report["win_count"],
        "online_episodes": online_report["episodes"],
        "online_large_loss_rate": online_report.get("large_loss_rate", 0.0),
        "online_action_family_counts": online_report.get("action_family_counts", {}),
    }
    write_pipeline_report(report_output, report)
    return report


def write_pipeline_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full BC pipeline")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--start-seed", type=int, default=1)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--eval-episodes", type=int, default=20)
    parser.add_argument("--bridge-lib", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--split-seed", type=int, default=0)
    parser.add_argument("--report-output", type=Path, default=None)
    args = parser.parse_args()

    report = run_pipeline(
        episodes=args.episodes,
        start_seed=args.start_seed,
        epochs=args.epochs,
        batch_size=args.batch_size,
        eval_episodes=args.eval_episodes,
        bridge_kind="go",
        bridge_library_path=args.bridge_lib,
        output_dir=args.output_dir,
        device=args.device,
        validation_fraction=args.validation_fraction,
        split_seed=args.split_seed,
        report_output=args.report_output,
    )

    print("\n" + "=" * 40)
    print("PIPELINE COMPLETE")
    print("=" * 40)
    for k, v in report.items():
        print(f"  {k}: {v}")
    print(f"  report_output: {args.report_output or args.output_dir / 'reports' / 'pipeline_report.json'}")


if __name__ == "__main__":
    main()

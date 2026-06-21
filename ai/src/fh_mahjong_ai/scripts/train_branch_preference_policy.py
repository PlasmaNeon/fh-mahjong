"""Train policy/Q heads to propose exact preferred branch-CF actions."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
import torch
from torch import nn

from fh_mahjong_ai.branch_cf_calibration import action_ranks, label_rank_summary, preference_summary
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.global_ev import concatenate_array_sets, episode_split_indices
from fh_mahjong_ai.mlflow_tracking import DEFAULT_EXPERIMENT_NAME, log_artifact, log_metrics, log_params, start_run
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args, model_config_params
from fh_mahjong_ai.storage import load_checkpoint, read_transition_arrays, save_checkpoint


BRANCH_POLICY_ARRAY_KEYS = (
    "planes",
    "scalars",
    "action_mask",
    "pairwise_preferred_action_ids",
    "pairwise_avoided_action_ids",
    "pairwise_reward_delta_targets",
    "episode_index",
)


@dataclass(frozen=True)
class BranchPreferenceTrainConfig:
    batch_size: int = 1024
    learning_rate: float = 5e-5
    weight_decay: float = 1e-4
    epochs: int = 1
    steps_per_epoch: Optional[int] = None
    validation_mod: int = 10
    validation_remainder: int = 0
    seed: int = 0
    device: str = "cpu"
    freeze_encoder: bool = True
    policy_weight: float = 1.0
    q_weight: float = 0.0
    anchor_kl_weight: float = 0.05
    reward_gap_weight: float = 0.0
    reward_gap_clip: float = 2.0


def train_branch_preference_policy(
    data_paths: Sequence[Path],
    init_checkpoint: Path,
    checkpoint_dir: Path,
    config: BranchPreferenceTrainConfig,
    model_config: Optional[ModelConfig] = None,
    max_transitions: Optional[int] = None,
    report_output: Optional[Path] = None,
    mlflow_enabled: bool = False,
    mlflow_tracking_uri: Optional[str] = None,
    mlflow_experiment: str = DEFAULT_EXPERIMENT_NAME,
    mlflow_run_name: Optional[str] = None,
) -> dict[str, Any]:
    arrays = load_branch_policy_arrays(data_paths, max_transitions=max_transitions)
    train_indices, validation_indices = episode_split_indices(
        arrays["episode_index"],
        validation_mod=config.validation_mod,
        validation_remainder=config.validation_remainder,
    )
    env_config = EnvConfig(
        plane_shape=tuple(int(dim) for dim in arrays["planes"].shape[1:]),
        scalar_features=int(arrays["scalars"].shape[1]),
        action_space_size=int(arrays["action_mask"].shape[1]),
    )
    model_config = model_config or ModelConfig()
    model = PolicyValueNet(env_config, model_config).to(config.device)
    anchor_model = PolicyValueNet(env_config, model_config).to(config.device)
    init_step = load_checkpoint(init_checkpoint, model)
    load_checkpoint(init_checkpoint, anchor_model)
    anchor_model.eval()
    for param in anchor_model.parameters():
        param.requires_grad_(False)
    if config.freeze_encoder:
        freeze_non_action_heads(model, train_q=config.q_weight > 0.0)
    optimizer = torch.optim.AdamW(
        [param for param in model.parameters() if param.requires_grad],
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    rng = np.random.default_rng(config.seed)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    effective_batch = min(max(1, int(config.batch_size)), int(train_indices.size))
    steps_per_epoch = config.steps_per_epoch or max(1, int(train_indices.size) // effective_batch)
    history: list[dict[str, float | int]] = []

    with start_run(
        enabled=mlflow_enabled,
        experiment_name=mlflow_experiment,
        tracking_uri=mlflow_tracking_uri,
        run_name=mlflow_run_name,
        tags={"stage": "training", "method": "branch_preference_policy"},
    ) as mlflow_run:
        if mlflow_run is not None:
            log_params(
                {
                    "method": "branch_preference_policy",
                    "data_paths": ",".join(str(path) for path in data_paths),
                    "init_checkpoint": init_checkpoint,
                    "init_checkpoint_step": init_step,
                    "checkpoint_dir": checkpoint_dir,
                    "rows": int(arrays["planes"].shape[0]),
                    "train_rows": int(train_indices.size),
                    "validation_rows": int(validation_indices.size),
                    "max_transitions": max_transitions,
                    **asdict(config),
                    **model_config_params(model_config),
                }
            )

        for epoch in range(1, config.epochs + 1):
            model.train()
            latest: dict[str, float | int] = {}
            for step in range(1, steps_per_epoch + 1):
                batch_indices = rng.choice(train_indices, size=effective_batch, replace=train_indices.size < effective_batch)
                latest = train_step(model, anchor_model, optimizer, arrays, batch_indices, config)
                if step == 1 or step % 20 == 0 or step == steps_per_epoch:
                    print(
                        f"epoch {epoch}/{config.epochs} step {step}/{steps_per_epoch} "
                        f"loss={latest['loss']:.5f} policy={latest['policy_loss']:.5f} "
                        f"q={latest['q_loss']:.5f} kl={latest['anchor_kl_loss']:.5f}",
                        flush=True,
                    )
                if mlflow_run is not None:
                    log_metrics({f"train_{key}": value for key, value in latest.items()}, step=(epoch - 1) * steps_per_epoch + step)

            train_report = evaluate_branch_policy(model, arrays, train_indices, config.device)
            validation_report = evaluate_branch_policy(model, arrays, validation_indices, config.device)
            row = {
                "epoch": int(epoch),
                **latest,
                "train_policy_argmax_preferred_rate": train_report["argmax"]["policy_preferred_action_rate"],
                "validation_policy_argmax_preferred_rate": validation_report["argmax"]["policy_preferred_action_rate"],
                "validation_policy_top3_preferred_rate": validation_report["policy_rank"]["by_top_k"]["3"]["preferred_rate"],
                "validation_policy_top5_preferred_rate": validation_report["policy_rank"]["by_top_k"]["5"]["preferred_rate"],
                "validation_q_argmax_preferred_rate": validation_report["argmax"]["q_preferred_action_rate"],
            }
            history.append(row)
            print(
                f"--- epoch {epoch} "
                f"policy_argmax={validation_report['argmax']['policy_preferred_action_rate']:.4f} "
                f"top3={validation_report['policy_rank']['by_top_k']['3']['preferred_rate']:.4f} "
                f"top5={validation_report['policy_rank']['by_top_k']['5']['preferred_rate']:.4f} "
                f"q_argmax={validation_report['argmax']['q_preferred_action_rate']:.4f}",
                flush=True,
            )
            if mlflow_run is not None:
                log_metrics(row, step=epoch)
            checkpoint_path = checkpoint_dir / f"epoch_{epoch:03d}.pt"
            save_checkpoint(checkpoint_path, model, optimizer, step=epoch)
            if mlflow_run is not None:
                log_artifact(checkpoint_path, artifact_path="checkpoints")

        final_train = evaluate_branch_policy(model, arrays, train_indices, config.device)
        final_validation = evaluate_branch_policy(model, arrays, validation_indices, config.device)
        report: dict[str, Any] = {
            "schema_version": 1,
            "method": "branch_preference_policy",
            "data_paths": [str(path) for path in data_paths],
            "init_checkpoint": str(init_checkpoint),
            "init_checkpoint_step": int(init_step),
            "checkpoint_dir": str(checkpoint_dir),
            "final_checkpoint": str(checkpoint_dir / f"epoch_{config.epochs:03d}.pt"),
            "rows": int(arrays["planes"].shape[0]),
            "train_rows": int(train_indices.size),
            "validation_rows": int(validation_indices.size),
            "train": final_train,
            "validation": final_validation,
            "history": history,
            "config": asdict(config),
            "model_config": model_config_params(model_config),
        }
        if report_output is not None:
            report_output.parent.mkdir(parents=True, exist_ok=True)
            report_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if mlflow_run is not None:
                log_artifact(report_output, artifact_path="reports")
        if mlflow_run is not None:
            print(f"MLflow run: {mlflow_run.info.run_id}")
    return report


def load_branch_policy_arrays(data_paths: Sequence[Path], max_transitions: Optional[int] = None) -> dict[str, np.ndarray]:
    loaded = [
        read_transition_arrays(path, keys=BRANCH_POLICY_ARRAY_KEYS, limit=max_transitions)
        for path in data_paths
    ]
    return concatenate_array_sets(loaded)


def freeze_non_action_heads(model: PolicyValueNet, train_q: bool) -> None:
    for name, param in model.named_parameters():
        trainable = name.startswith("policy_head.")
        if train_q:
            trainable = trainable or name.startswith("q_head.")
        param.requires_grad_(trainable)


def train_step(
    model: PolicyValueNet,
    anchor_model: PolicyValueNet,
    optimizer: torch.optim.Optimizer,
    arrays: dict[str, np.ndarray],
    indices: np.ndarray,
    config: BranchPreferenceTrainConfig,
) -> dict[str, float]:
    planes = torch.from_numpy(arrays["planes"][indices].astype(np.float32, copy=False)).to(config.device)
    scalars = torch.from_numpy(arrays["scalars"][indices].astype(np.float32, copy=False)).to(config.device)
    action_mask = torch.from_numpy(arrays["action_mask"][indices].astype(np.int8, copy=False)).to(config.device)
    preferred = torch.from_numpy(arrays["pairwise_preferred_action_ids"][indices].astype(np.int64, copy=False)).to(config.device)
    gaps = torch.from_numpy(
        np.clip(arrays["pairwise_reward_delta_targets"][indices].astype(np.float32, copy=False), 0.0, config.reward_gap_clip)
    ).to(config.device)
    weights = 1.0 + float(config.reward_gap_weight) * gaps

    logits, _ = model(planes, scalars, action_mask)
    policy_loss = weighted_cross_entropy(logits, preferred, weights)
    q_loss = torch.zeros((), dtype=policy_loss.dtype, device=policy_loss.device)
    if config.q_weight > 0.0:
        q_values, _ = model.q_values(planes, scalars, action_mask)
        q_loss = weighted_cross_entropy(q_values, preferred, weights)
    anchor_kl = torch.zeros((), dtype=policy_loss.dtype, device=policy_loss.device)
    if config.anchor_kl_weight > 0.0:
        with torch.no_grad():
            anchor_logits, _ = anchor_model(planes, scalars, action_mask)
            anchor_probs = torch.softmax(anchor_logits, dim=-1)
        log_probs = torch.log_softmax(logits, dim=-1)
        per_row_kl = torch.sum(anchor_probs * (torch.log(anchor_probs.clamp_min(1e-8)) - log_probs), dim=-1)
        anchor_kl = (per_row_kl * weights).sum() / weights.clamp_min(1e-6).sum()
    loss = config.policy_weight * policy_loss + config.q_weight * q_loss + config.anchor_kl_weight * anchor_kl

    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
    optimizer.step()
    return {
        "loss": float(loss.item()),
        "policy_loss": float(policy_loss.item()),
        "q_loss": float(q_loss.item()),
        "anchor_kl_loss": float(anchor_kl.item()),
    }


def weighted_cross_entropy(logits: torch.Tensor, targets: torch.Tensor, weights: torch.Tensor) -> torch.Tensor:
    losses = nn.functional.cross_entropy(logits, targets, reduction="none")
    return (losses * weights).sum() / weights.clamp_min(1e-6).sum()


@torch.inference_mode()
def evaluate_branch_policy(
    model: PolicyValueNet,
    arrays: dict[str, np.ndarray],
    indices: np.ndarray,
    device: str,
    batch_size: int = 4096,
    top_ks: tuple[int, ...] = (3, 5, 10, 20),
) -> dict[str, Any]:
    model.eval()
    policy_scores: list[np.ndarray] = []
    q_scores: list[np.ndarray] = []
    for start in range(0, int(indices.size), batch_size):
        batch_indices = indices[start : start + batch_size]
        planes = torch.from_numpy(arrays["planes"][batch_indices].astype(np.float32, copy=False)).to(device)
        scalars = torch.from_numpy(arrays["scalars"][batch_indices].astype(np.float32, copy=False)).to(device)
        action_mask = torch.from_numpy(arrays["action_mask"][batch_indices].astype(np.int8, copy=False)).to(device)
        logits, _ = model(planes, scalars, action_mask)
        q_values, _ = model.q_values(planes, scalars, action_mask)
        policy_scores.append(logits.detach().cpu().numpy().astype(np.float32))
        q_scores.append(q_values.detach().cpu().numpy().astype(np.float32))
    policy = np.concatenate(policy_scores, axis=0)
    q = np.concatenate(q_scores, axis=0)
    preferred = arrays["pairwise_preferred_action_ids"][indices].astype(np.int64, copy=False)
    avoided = arrays["pairwise_avoided_action_ids"][indices].astype(np.int64, copy=False)
    gaps = arrays["pairwise_reward_delta_targets"][indices].astype(np.float32, copy=False)
    mask = arrays["action_mask"][indices].astype(np.int8, copy=False)
    policy_ranks = action_ranks(policy, mask, descending=True)
    q_ranks = action_ranks(q, mask, descending=True)
    rows = np.arange(preferred.shape[0], dtype=np.int64)
    return {
        "rows": int(preferred.shape[0]),
        "policy_logits": preference_summary(policy[rows, preferred], policy[rows, avoided], gaps),
        "q_values": preference_summary(q[rows, preferred], q[rows, avoided], gaps),
        "argmax": {
            "policy_preferred_action_rate": float(np.mean(np.argmax(policy, axis=1) == preferred)) if preferred.size else 0.0,
            "policy_avoided_action_rate": float(np.mean(np.argmax(policy, axis=1) == avoided)) if preferred.size else 0.0,
            "q_preferred_action_rate": float(np.mean(np.argmax(q, axis=1) == preferred)) if preferred.size else 0.0,
            "q_avoided_action_rate": float(np.mean(np.argmax(q, axis=1) == avoided)) if preferred.size else 0.0,
        },
        "policy_rank": label_rank_summary(policy_ranks, preferred, avoided, gaps, top_ks),
        "q_rank": label_rank_summary(q_ranks, preferred, avoided, gaps, top_ks),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train policy/Q heads to propose exact preferred branch-CF actions")
    parser.add_argument("--data", type=Path, action="append", required=True)
    parser.add_argument("--init-checkpoint", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--steps-per-epoch", type=int, default=None)
    parser.add_argument("--validation-mod", type=int, default=10)
    parser.add_argument("--validation-remainder", type=int, default=0)
    parser.add_argument("--max-transitions", type=int, default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--train-encoder", action="store_true", help="Train the shared encoder/trunk instead of only heads.")
    parser.add_argument("--policy-weight", type=float, default=1.0)
    parser.add_argument("--q-weight", type=float, default=0.0)
    parser.add_argument("--anchor-kl-weight", type=float, default=0.05)
    parser.add_argument("--reward-gap-weight", type=float, default=0.0)
    parser.add_argument("--reward-gap-clip", type=float, default=2.0)
    parser.add_argument("--mlflow", action="store_true")
    parser.add_argument("--mlflow-tracking-uri", type=str, default=None)
    parser.add_argument("--mlflow-experiment", type=str, default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--mlflow-run-name", type=str, default=None)
    add_model_config_args(parser)
    args = parser.parse_args()

    config = BranchPreferenceTrainConfig(
        batch_size=args.batch_size,
        learning_rate=args.lr,
        weight_decay=args.weight_decay,
        epochs=args.epochs,
        steps_per_epoch=args.steps_per_epoch,
        validation_mod=args.validation_mod,
        validation_remainder=args.validation_remainder,
        seed=args.seed,
        device=args.device,
        freeze_encoder=not args.train_encoder,
        policy_weight=args.policy_weight,
        q_weight=args.q_weight,
        anchor_kl_weight=args.anchor_kl_weight,
        reward_gap_weight=args.reward_gap_weight,
        reward_gap_clip=args.reward_gap_clip,
    )
    report = train_branch_preference_policy(
        data_paths=args.data,
        init_checkpoint=args.init_checkpoint,
        checkpoint_dir=args.checkpoint_dir,
        config=config,
        model_config=model_config_from_args(args),
        max_transitions=args.max_transitions,
        report_output=args.report_output,
        mlflow_enabled=args.mlflow,
        mlflow_tracking_uri=args.mlflow_tracking_uri,
        mlflow_experiment=args.mlflow_experiment,
        mlflow_run_name=args.mlflow_run_name,
    )
    validation = report["validation"]
    print(f"Rows: {report['rows']}")
    print(f"Validation policy argmax preferred: {validation['argmax']['policy_preferred_action_rate']:.2%}")
    print(f"Validation policy top-3 preferred:  {validation['policy_rank']['by_top_k']['3']['preferred_rate']:.2%}")
    print(f"Validation policy top-5 preferred:  {validation['policy_rank']['by_top_k']['5']['preferred_rate']:.2%}")
    if args.report_output is not None:
        print(f"Report saved to {args.report_output}")


if __name__ == "__main__":
    main()

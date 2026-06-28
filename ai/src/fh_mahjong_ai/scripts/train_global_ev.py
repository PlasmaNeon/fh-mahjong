"""Train a visible-state global EV predictor for Chongci rewards."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.global_ev import (
    GLOBAL_EV_ARRAY_KEYS,
    GLOBAL_EV_OPTIONAL_ARRAY_KEYS,
    ActionGlobalEVNet,
    BRANCH_ACTION_EV_ARRAY_KEYS,
    BRANCH_ACTION_EV_OPTIONAL_ARRAY_KEYS,
    GlobalEVMetrics,
    GlobalEVNet,
    branch_action_ev_arrays,
    concatenate_array_sets,
    constant_baseline_metrics,
    episode_split_indices,
    global_ev_targets,
    regression_metrics,
)
from fh_mahjong_ai.mlflow_tracking import DEFAULT_EXPERIMENT_NAME, log_artifact, log_metrics, log_params, start_run
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args, model_config_params
from fh_mahjong_ai.storage import load_checkpoint, read_transition_arrays, save_checkpoint


@dataclass(frozen=True)
class GlobalEVTrainConfig:
    batch_size: int = 2048
    learning_rate: float = 1e-4
    weight_decay: float = 1e-4
    epochs: int = 1
    steps_per_epoch: Optional[int] = None
    validation_mod: int = 10
    validation_remainder: int = 0
    seed: int = 0
    device: str = "cpu"
    action_conditioned: bool = False
    branch_cf_action_targets: bool = False
    branch_cf_pairwise_weight: float = 0.0
    branch_cf_pairwise_margin: float = 0.0
    branch_cf_pairwise_reward_gap_weight: float = 0.0
    branch_cf_pairwise_reward_gap_margin_scale: float = 0.0
    branch_cf_pairwise_reward_gap_clip: float = 2.0
    reward_shaping: str = "raw"
    placement_values: tuple = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)


def train_global_ev(
    data_paths: Sequence[Path],
    checkpoint_dir: Path,
    config: GlobalEVTrainConfig,
    env_config: Optional[EnvConfig] = None,
    model_config: Optional[ModelConfig] = None,
    max_transitions: Optional[int] = None,
    report_output: Optional[Path] = None,
    mlflow_enabled: bool = False,
    mlflow_tracking_uri: Optional[str] = None,
    mlflow_experiment: str = DEFAULT_EXPERIMENT_NAME,
    mlflow_run_name: Optional[str] = None,
    init_checkpoint: Optional[Path] = None,
) -> dict[str, object]:
    if config.branch_cf_action_targets and not config.action_conditioned:
        raise ValueError("branch-CF action targets require action_conditioned=True")
    if config.branch_cf_pairwise_weight > 0.0 and not config.branch_cf_action_targets:
        raise ValueError("branch-CF pairwise ranking requires branch_cf_action_targets=True")
    arrays = load_global_ev_arrays(
        data_paths,
        max_transitions=max_transitions,
        branch_cf_action_targets=config.branch_cf_action_targets,
    )
    targets = global_ev_targets(
        arrays,
        reward_shaping=config.reward_shaping,
        placement_values=config.placement_values,
    )
    train_indices, validation_indices = episode_split_indices(
        arrays["episode_index"],
        validation_mod=config.validation_mod,
        validation_remainder=config.validation_remainder,
    )

    env_config = env_config or infer_env_config(arrays)
    model_config = model_config or ModelConfig()
    model = (
        ActionGlobalEVNet(env_config, model_config)
        if config.action_conditioned
        else GlobalEVNet(env_config, model_config)
    ).to(config.device)
    init_step: Optional[int] = None
    if init_checkpoint is not None:
        init_step = load_checkpoint(init_checkpoint, model)
        print(f"Loaded init checkpoint {init_checkpoint} from epoch {init_step}", flush=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    rng = np.random.default_rng(config.seed)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    effective_batch = min(max(1, int(config.batch_size)), int(train_indices.size))
    steps_per_epoch = config.steps_per_epoch or max(1, int(train_indices.size) // effective_batch)
    pair_train_indices, pair_validation_indices = branch_pair_split_indices(
        arrays,
        validation_mod=config.validation_mod,
        validation_remainder=config.validation_remainder,
    )
    effective_pair_batch = (
        min(max(1, int(config.batch_size) // 2), int(pair_train_indices.size))
        if config.branch_cf_pairwise_weight > 0.0
        else 0
    )
    history: list[dict[str, float | int]] = []

    with start_run(
        enabled=mlflow_enabled,
        experiment_name=mlflow_experiment,
        tracking_uri=mlflow_tracking_uri,
        run_name=mlflow_run_name,
        tags={"stage": "training", "method": "global_ev"},
    ) as mlflow_run:
        if mlflow_run is not None:
            log_params(
                {
                    "method": "global_ev",
                    "action_conditioned": config.action_conditioned,
                    "branch_cf_action_targets": config.branch_cf_action_targets,
                    "data_paths": ",".join(str(path) for path in data_paths),
                    "checkpoint_dir": checkpoint_dir,
                    "transitions": int(targets.shape[0]),
                    "train_transitions": int(train_indices.size),
                    "validation_transitions": int(validation_indices.size),
                    "target_mean": float(np.mean(targets)),
                    "target_std": float(np.std(targets)),
                    "max_transitions": max_transitions,
                    "init_checkpoint": init_checkpoint,
                    "init_checkpoint_step": init_step,
                    **asdict(config),
                    **model_config_params(model_config),
                }
            )

        for epoch in range(1, config.epochs + 1):
            model.train()
            latest_loss = 0.0
            latest_regression_loss = 0.0
            latest_pairwise_loss = 0.0
            latest_pairwise_count = 0
            for step in range(1, steps_per_epoch + 1):
                batch_indices = rng.choice(train_indices, size=effective_batch, replace=train_indices.size < effective_batch)
                pair_indices = (
                    rng.choice(
                        pair_train_indices,
                        size=effective_pair_batch,
                        replace=pair_train_indices.size < effective_pair_batch,
                    )
                    if effective_pair_batch > 0
                    else None
                )
                step_metrics = train_step(
                    model,
                    optimizer,
                    arrays,
                    targets,
                    batch_indices,
                    config.device,
                    pair_indices=pair_indices,
                    pairwise_weight=config.branch_cf_pairwise_weight,
                    pairwise_margin=config.branch_cf_pairwise_margin,
                    pairwise_reward_gap_weight=config.branch_cf_pairwise_reward_gap_weight,
                    pairwise_reward_gap_margin_scale=config.branch_cf_pairwise_reward_gap_margin_scale,
                    pairwise_reward_gap_clip=config.branch_cf_pairwise_reward_gap_clip,
                )
                latest_loss = float(step_metrics["loss"])
                latest_regression_loss = float(step_metrics["regression_loss"])
                latest_pairwise_loss = float(step_metrics["pairwise_loss"])
                latest_pairwise_count = int(step_metrics["pairwise_count"])
                if step == 1 or step % 20 == 0 or step == steps_per_epoch:
                    print(
                        f"epoch {epoch}/{config.epochs} step {step}/{steps_per_epoch} "
                        f"loss={latest_loss:.5f} reg={latest_regression_loss:.5f} "
                        f"pairwise={latest_pairwise_loss:.5f}/{latest_pairwise_count}",
                        flush=True,
                    )
                if mlflow_run is not None:
                    log_metrics(
                        {
                            "train_loss": latest_loss,
                            "train_regression_loss": latest_regression_loss,
                            "train_pairwise_loss": latest_pairwise_loss,
                            "train_pairwise_count": latest_pairwise_count,
                        },
                        step=(epoch - 1) * steps_per_epoch + step,
                    )

            train_metrics = evaluate_global_ev(model, arrays, targets, train_indices, config.device)
            validation_metrics = evaluate_global_ev(model, arrays, targets, validation_indices, config.device)
            pairwise_train_metrics = evaluate_branch_pairwise(
                model,
                arrays,
                pair_train_indices,
                config.device,
            )
            pairwise_validation_metrics = evaluate_branch_pairwise(
                model,
                arrays,
                pair_validation_indices,
                config.device,
            )
            row = {
                "epoch": int(epoch),
                "train_loss": latest_loss,
                "train_regression_loss": latest_regression_loss,
                "train_pairwise_loss": latest_pairwise_loss,
                "train_pairwise_count": latest_pairwise_count,
                "train_mae": train_metrics.mae,
                "train_rmse": train_metrics.rmse,
                "train_correlation": train_metrics.correlation,
                "validation_mae": validation_metrics.mae,
                "validation_rmse": validation_metrics.rmse,
                "validation_correlation": validation_metrics.correlation,
                "validation_bias": validation_metrics.bias,
                "branch_pairwise_train_preferred_rate": pairwise_train_metrics["preferred_rate"],
                "branch_pairwise_validation_preferred_rate": pairwise_validation_metrics["preferred_rate"],
                "branch_pairwise_validation_gap_weighted_preferred_rate": pairwise_validation_metrics[
                    "gap_weighted_preferred_rate"
                ],
            }
            history.append(row)
            print(
                f"--- epoch {epoch} "
                f"train_mae={train_metrics.mae:.4f} val_mae={validation_metrics.mae:.4f} "
                f"val_rmse={validation_metrics.rmse:.4f} val_corr={validation_metrics.correlation:.4f} "
                f"pair_pref={pairwise_validation_metrics['preferred_rate']:.4f}",
                flush=True,
            )
            if mlflow_run is not None:
                log_metrics(row, step=epoch)
            checkpoint_path = checkpoint_dir / f"epoch_{epoch:03d}.pt"
            # Persist the training objective so the PPO GRP loader can reject a
            # raw-score checkpoint used where placement potentials are required.
            save_checkpoint(
                checkpoint_path, model, optimizer, step=epoch,
                metadata={
                    "kind": "global_ev",
                    "reward_shaping": config.reward_shaping,
                    "placement_values": list(config.placement_values),
                },
            )
            if mlflow_run is not None:
                log_artifact(checkpoint_path, artifact_path="checkpoints")

        final_train = evaluate_global_ev(model, arrays, targets, train_indices, config.device)
        final_validation = evaluate_global_ev(model, arrays, targets, validation_indices, config.device)
        final_pairwise_train = evaluate_branch_pairwise(model, arrays, pair_train_indices, config.device)
        final_pairwise_validation = evaluate_branch_pairwise(model, arrays, pair_validation_indices, config.device)
        baseline_validation = constant_baseline_metrics(targets[train_indices], targets[validation_indices])
        report: dict[str, object] = {
            "schema_version": 1,
            "method": "branch_action_global_ev"
            if config.branch_cf_action_targets
            else "action_global_ev"
            if config.action_conditioned
            else "global_ev",
            "data_paths": [str(path) for path in data_paths],
            "checkpoint_dir": str(checkpoint_dir),
            "final_checkpoint": str(checkpoint_dir / f"epoch_{config.epochs:03d}.pt"),
            "init_checkpoint": str(init_checkpoint) if init_checkpoint is not None else None,
            "init_checkpoint_step": init_step,
            "transitions": int(targets.shape[0]),
            "train_transitions": int(train_indices.size),
            "validation_transitions": int(validation_indices.size),
            "target_summary": summarize_targets(targets),
            "train": asdict(final_train),
            "validation": asdict(final_validation),
            "branch_pairwise_train": final_pairwise_train,
            "branch_pairwise_validation": final_pairwise_validation,
            "baseline_validation": asdict(baseline_validation),
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
            log_metrics({"global_ev": {"train": report["train"], "validation": report["validation"]}}, step=config.epochs)
            print(f"MLflow run: {mlflow_run.info.run_id}")

    return report


def load_global_ev_arrays(
    data_paths: Sequence[Path],
    max_transitions: Optional[int] = None,
    branch_cf_action_targets: bool = False,
) -> dict[str, np.ndarray]:
    if branch_cf_action_targets:
        loaded = [
            branch_action_ev_arrays(
                read_transition_arrays(
                    path,
                    keys=BRANCH_ACTION_EV_ARRAY_KEYS,
                    optional_keys=BRANCH_ACTION_EV_OPTIONAL_ARRAY_KEYS,
                    limit=max_transitions,
                )
            )
            for path in data_paths
        ]
    else:
        loaded = [
            read_transition_arrays(
                path,
                keys=GLOBAL_EV_ARRAY_KEYS,
                optional_keys=GLOBAL_EV_OPTIONAL_ARRAY_KEYS,
                limit=max_transitions,
            )
            for path in data_paths
        ]
    return concatenate_array_sets(loaded)


def infer_env_config(arrays: dict[str, np.ndarray]) -> EnvConfig:
    planes = arrays["planes"]
    scalars = arrays["scalars"]
    return EnvConfig(
        plane_shape=tuple(int(dim) for dim in planes.shape[1:]),
        scalar_features=int(scalars.shape[1]),
    )


def train_step(
    model: GlobalEVNet | ActionGlobalEVNet,
    optimizer: torch.optim.Optimizer,
    arrays: dict[str, np.ndarray],
    targets: np.ndarray,
    indices: np.ndarray,
    device: str,
    pair_indices: Optional[np.ndarray] = None,
    pairwise_weight: float = 0.0,
    pairwise_margin: float = 0.0,
    pairwise_reward_gap_weight: float = 0.0,
    pairwise_reward_gap_margin_scale: float = 0.0,
    pairwise_reward_gap_clip: float = 2.0,
) -> dict[str, float | int]:
    planes = torch.from_numpy(arrays["planes"][indices]).to(device)
    scalars = torch.from_numpy(arrays["scalars"][indices]).to(device)
    target = torch.from_numpy(targets[indices]).to(device)
    if isinstance(model, ActionGlobalEVNet):
        action_ids = torch.from_numpy(arrays["action_ids"][indices]).to(device)
        prediction = model(planes, scalars, action_ids)
    else:
        prediction = model(planes, scalars)
    regression_loss = torch.nn.functional.smooth_l1_loss(prediction, target)
    pairwise_loss = torch.zeros((), dtype=regression_loss.dtype, device=regression_loss.device)
    pairwise_count = 0
    if (
        pair_indices is not None
        and pairwise_weight > 0.0
        and isinstance(model, ActionGlobalEVNet)
        and pair_indices.size > 0
    ):
        pairwise_loss, pairwise_count = branch_pairwise_margin_loss(
            model,
            arrays,
            pair_indices,
            device,
            margin=pairwise_margin,
            reward_gap_weight=pairwise_reward_gap_weight,
            reward_gap_margin_scale=pairwise_reward_gap_margin_scale,
            reward_gap_clip=pairwise_reward_gap_clip,
        )
    loss = regression_loss + float(pairwise_weight) * pairwise_loss
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
    optimizer.step()
    return {
        "loss": float(loss.item()),
        "regression_loss": float(regression_loss.item()),
        "pairwise_loss": float(pairwise_loss.item()),
        "pairwise_count": int(pairwise_count),
    }


def branch_pair_split_indices(
    arrays: dict[str, np.ndarray],
    validation_mod: int = 10,
    validation_remainder: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    if "branch_role_ids" not in arrays:
        empty = np.zeros(0, dtype=np.int64)
        return empty, empty
    roles = np.asarray(arrays["branch_role_ids"], dtype=np.int8)
    if roles.size % 2 != 0:
        raise ValueError("branch action EV arrays must contain preferred/avoided row pairs")
    pair_count = roles.size // 2
    if pair_count == 0:
        empty = np.zeros(0, dtype=np.int64)
        return empty, empty
    if not np.all(roles[0::2] == 1) or not np.all(roles[1::2] == 0):
        raise ValueError("branch action EV rows must alternate preferred then avoided")
    pair_episode_index = np.asarray(arrays["episode_index"][0::2], dtype=np.int64)
    train_indices, validation_indices = episode_split_indices(
        pair_episode_index,
        validation_mod=validation_mod,
        validation_remainder=validation_remainder,
    )
    return train_indices, validation_indices


def branch_pairwise_margin_loss(
    model: ActionGlobalEVNet,
    arrays: dict[str, np.ndarray],
    pair_indices: np.ndarray,
    device: str,
    margin: float = 0.0,
    reward_gap_weight: float = 0.0,
    reward_gap_margin_scale: float = 0.0,
    reward_gap_clip: float = 2.0,
) -> tuple[torch.Tensor, int]:
    pair_indices = np.asarray(pair_indices, dtype=np.int64)
    if pair_indices.size == 0:
        return torch.zeros((), device=device), 0
    preferred_indices = pair_indices * 2
    avoided_indices = preferred_indices + 1
    planes = torch.from_numpy(arrays["planes"][preferred_indices]).to(device)
    scalars = torch.from_numpy(arrays["scalars"][preferred_indices]).to(device)
    preferred_actions = torch.from_numpy(arrays["action_ids"][preferred_indices]).to(device)
    avoided_actions = torch.from_numpy(arrays["action_ids"][avoided_indices]).to(device)
    preferred_scores = model(planes, scalars, preferred_actions)
    avoided_scores = model(planes, scalars, avoided_actions)
    if "pairwise_reward_delta_targets" in arrays:
        reward_gaps_np = np.asarray(arrays["pairwise_reward_delta_targets"][preferred_indices], dtype=np.float32)
    else:
        seats = np.asarray(arrays["seats"][preferred_indices], dtype=np.int64)
        preferred_rewards = np.asarray(arrays["terminal_rewards"][preferred_indices], dtype=np.float32)
        avoided_rewards = np.asarray(arrays["terminal_rewards"][avoided_indices], dtype=np.float32)
        reward_gaps_np = preferred_rewards[np.arange(preferred_rewards.shape[0]), seats] - avoided_rewards[
            np.arange(avoided_rewards.shape[0]), seats
        ]
    reward_gaps = torch.from_numpy(np.clip(reward_gaps_np, 0.0, float(reward_gap_clip))).to(
        dtype=preferred_scores.dtype,
        device=device,
    )
    required_margin = float(margin) + float(reward_gap_margin_scale) * reward_gaps
    losses = torch.relu(required_margin + avoided_scores - preferred_scores)
    weights = 1.0 + float(reward_gap_weight) * reward_gaps
    return (losses * weights).sum() / weights.clamp_min(1e-6).sum(), int(pair_indices.size)


@torch.inference_mode()
def evaluate_branch_pairwise(
    model: GlobalEVNet | ActionGlobalEVNet,
    arrays: dict[str, np.ndarray],
    pair_indices: np.ndarray,
    device: str,
    batch_size: int = 4096,
) -> dict[str, float | int]:
    if not isinstance(model, ActionGlobalEVNet) or pair_indices.size == 0:
        return {
            "count": 0,
            "preferred_rate": 0.0,
            "gap_weighted_preferred_rate": 0.0,
            "mean_margin": 0.0,
        }
    model.eval()
    preferred_flags: list[np.ndarray] = []
    margins: list[np.ndarray] = []
    gaps: list[np.ndarray] = []
    for start in range(0, int(pair_indices.size), batch_size):
        pair_batch = pair_indices[start : start + batch_size]
        preferred_indices = pair_batch * 2
        avoided_indices = preferred_indices + 1
        planes = torch.from_numpy(arrays["planes"][preferred_indices]).to(device)
        scalars = torch.from_numpy(arrays["scalars"][preferred_indices]).to(device)
        preferred_actions = torch.from_numpy(arrays["action_ids"][preferred_indices]).to(device)
        avoided_actions = torch.from_numpy(arrays["action_ids"][avoided_indices]).to(device)
        preferred_scores = model(planes, scalars, preferred_actions)
        avoided_scores = model(planes, scalars, avoided_actions)
        margin = (preferred_scores - avoided_scores).detach().cpu().numpy()
        margins.append(margin)
        preferred_flags.append((margin > 0.0).astype(np.float32))
        if "pairwise_reward_delta_targets" in arrays:
            gaps.append(np.asarray(arrays["pairwise_reward_delta_targets"][preferred_indices], dtype=np.float32))
        else:
            gaps.append(np.ones_like(margin, dtype=np.float32))
    preferred = np.concatenate(preferred_flags)
    all_margins = np.concatenate(margins)
    all_gaps = np.clip(np.concatenate(gaps), 0.0, None)
    gap_denominator = float(np.sum(all_gaps))
    return {
        "count": int(preferred.size),
        "preferred_rate": float(np.mean(preferred)),
        "gap_weighted_preferred_rate": float(np.sum(preferred * all_gaps) / gap_denominator)
        if gap_denominator > 0.0
        else 0.0,
        "mean_margin": float(np.mean(all_margins)),
    }


@torch.inference_mode()
def evaluate_global_ev(
    model: GlobalEVNet | ActionGlobalEVNet,
    arrays: dict[str, np.ndarray],
    targets: np.ndarray,
    indices: np.ndarray,
    device: str,
    batch_size: int = 4096,
) -> GlobalEVMetrics:
    model.eval()
    predictions: list[np.ndarray] = []
    for start in range(0, int(indices.size), batch_size):
        batch_indices = indices[start : start + batch_size]
        planes = torch.from_numpy(arrays["planes"][batch_indices]).to(device)
        scalars = torch.from_numpy(arrays["scalars"][batch_indices]).to(device)
        if isinstance(model, ActionGlobalEVNet):
            action_ids = torch.from_numpy(arrays["action_ids"][batch_indices]).to(device)
            batch_predictions = model(planes, scalars, action_ids)
        else:
            batch_predictions = model(planes, scalars)
        predictions.append(batch_predictions.detach().cpu().numpy())
    return regression_metrics(np.concatenate(predictions, axis=0), targets[indices])


def summarize_targets(targets: np.ndarray) -> dict[str, float | int]:
    values = np.asarray(targets, dtype=np.float64)
    return {
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "positive_rate": float(np.mean(values > 0.0)),
        "large_loss_rate_le_-0.5": float(np.mean(values <= -0.5)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a visible-state global EV predictor")
    parser.add_argument("--data", type=Path, action="append", required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=2048)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--steps-per-epoch", type=int, default=None)
    parser.add_argument("--validation-mod", type=int, default=10)
    parser.add_argument("--validation-remainder", type=int, default=0)
    parser.add_argument("--max-transitions", type=int, default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument(
        "--reward-shaping",
        choices=("raw", "placement"),
        default="raw",
        help="raw terminal net-score EV target (default) or rank-based placement EV",
    )
    parser.add_argument(
        "--placement-values",
        type=float,
        nargs=4,
        default=(1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0),
        help="placement values for ranks 1..4 when --reward-shaping placement",
    )
    parser.add_argument(
        "--action-conditioned",
        action="store_true",
        help="Train EV(state, action_id) instead of EV(state).",
    )
    parser.add_argument(
        "--branch-cf-action-targets",
        action="store_true",
        help="Read exact branch-CF preferred/avoided branch rewards as action-conditioned targets.",
    )
    parser.add_argument(
        "--branch-cf-pairwise-weight",
        type=float,
        default=0.0,
        help="Add a pairwise margin loss that ranks preferred branch actions above avoided branch actions.",
    )
    parser.add_argument(
        "--branch-cf-pairwise-margin",
        type=float,
        default=0.0,
        help="Base margin for --branch-cf-pairwise-weight.",
    )
    parser.add_argument(
        "--branch-cf-pairwise-reward-gap-weight",
        type=float,
        default=0.0,
        help="Scale branch pairwise row weights by 1 + this value * clipped reward gap.",
    )
    parser.add_argument(
        "--branch-cf-pairwise-reward-gap-margin-scale",
        type=float,
        default=0.0,
        help="Add this value * clipped reward gap to the required branch pairwise margin.",
    )
    parser.add_argument(
        "--branch-cf-pairwise-reward-gap-clip",
        type=float,
        default=2.0,
        help="Maximum reward gap used for branch pairwise weighting and margin scaling.",
    )
    parser.add_argument("--mlflow", action="store_true")
    parser.add_argument("--mlflow-tracking-uri", type=str, default=None)
    parser.add_argument("--mlflow-experiment", type=str, default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--mlflow-run-name", type=str, default=None)
    parser.add_argument("--init-checkpoint", type=Path, default=None)
    add_model_config_args(parser)
    args = parser.parse_args()

    config = GlobalEVTrainConfig(
        batch_size=args.batch_size,
        learning_rate=args.lr,
        weight_decay=args.weight_decay,
        epochs=args.epochs,
        steps_per_epoch=args.steps_per_epoch,
        validation_mod=args.validation_mod,
        validation_remainder=args.validation_remainder,
        seed=args.seed,
        device=args.device,
        action_conditioned=args.action_conditioned,
        branch_cf_action_targets=args.branch_cf_action_targets,
        branch_cf_pairwise_weight=args.branch_cf_pairwise_weight,
        branch_cf_pairwise_margin=args.branch_cf_pairwise_margin,
        branch_cf_pairwise_reward_gap_weight=args.branch_cf_pairwise_reward_gap_weight,
        branch_cf_pairwise_reward_gap_margin_scale=args.branch_cf_pairwise_reward_gap_margin_scale,
        branch_cf_pairwise_reward_gap_clip=args.branch_cf_pairwise_reward_gap_clip,
        reward_shaping=args.reward_shaping,
        placement_values=tuple(args.placement_values),
    )
    report = train_global_ev(
        data_paths=args.data,
        checkpoint_dir=args.checkpoint_dir,
        config=config,
        model_config=model_config_from_args(args),
        max_transitions=args.max_transitions,
        report_output=args.report_output,
        mlflow_enabled=args.mlflow,
        mlflow_tracking_uri=args.mlflow_tracking_uri,
        mlflow_experiment=args.mlflow_experiment,
        mlflow_run_name=args.mlflow_run_name,
        init_checkpoint=args.init_checkpoint,
    )
    validation = report["validation"]
    baseline_validation = report["baseline_validation"]
    print(f"Transitions: {report['transitions']}")
    print(f"Validation MAE:  {validation['mae']:.4f}")
    print(f"Validation RMSE: {validation['rmse']:.4f}")
    print(f"Validation Corr: {validation['correlation']:.4f}")
    print(f"Baseline MAE:    {baseline_validation['mae']:.4f}")
    if args.report_output is not None:
        print(f"Report saved to {args.report_output}")


if __name__ == "__main__":
    main()

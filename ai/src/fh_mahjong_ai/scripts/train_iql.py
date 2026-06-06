"""Discrete implicit Q-learning on saved Mahjong trajectories."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np
import torch

from fh_mahjong_ai.buffer import ArrayReplayBuffer, CompositeReplayBuffer, ReplayBuffer
from fh_mahjong_ai.config import DiscreteIQLConfig, EnvConfig, ModelConfig, TrainConfig
from fh_mahjong_ai.data import backfill_returns, backfill_steps_to_done, compute_steps_to_done
from fh_mahjong_ai.mlflow_tracking import DEFAULT_EXPERIMENT_NAME, log_artifact, log_metrics, log_params, start_run
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.risk_filter import (
    RiskCase,
    RiskWeightReport,
    apply_risk_case_weights,
    load_risk_cases_from_paired_trace_reports,
)
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args, model_config_params
from fh_mahjong_ai.storage import (
    is_sharded_transition_dataset,
    load_checkpoint,
    load_compatible_checkpoint,
    read_transition_arrays,
    read_transitions,
    save_checkpoint,
)
from fh_mahjong_ai.trainer import DiscreteIQLMetrics, DiscreteIQLTrainer

IQL_ARRAY_KEYS = (
    "seats",
    "planes",
    "scalars",
    "action_mask",
    "action_ids",
    "rewards",
    "next_planes",
    "next_scalars",
    "next_action_mask",
    "terminated",
    "truncated",
    "episode_index",
    "terminal_rewards",
)
OPTIONAL_IQL_ARRAY_KEYS = (
    "decision_indices",
    "sample_weights",
    "pairwise_preferred_action_ids",
    "pairwise_avoided_action_ids",
    "pairwise_weights",
    "pairwise_reward_delta_targets",
)
PAIRWISE_ARRAY_KEYS = (
    "seats",
    "planes",
    "scalars",
    "action_mask",
    "action_ids",
    "episode_index",
    "terminal_rewards",
)


def train_iql(
    data_path: Path | Sequence[Path],
    checkpoint_dir: Path,
    epochs: int = 10,
    batch_size: int = 64,
    learning_rate: float = 1e-4,
    gamma: float = 0.99,
    target_mode: str = "mc",
    expectile: float = 0.7,
    temperature: float = 1.0,
    max_weight: float = 20.0,
    q_weight: float = 1.0,
    value_weight: float = 1.0,
    policy_weight: float = 1.0,
    bc_weight: float = 1.0,
    cql_weight: float = 0.0,
    target_update_interval: int = 25,
    target_tau: float = 0.005,
    large_loss_threshold: Optional[float] = None,
    large_loss_penalty: float = 0.0,
    large_loss_weight: float = 1.0,
    pairwise_weight: float = 0.0,
    pairwise_margin: float = 0.0,
    pairwise_q_weight: float = 0.0,
    pairwise_q_margin: float = 0.0,
    pairwise_reward_delta_weight: float = 0.0,
    pairwise_reward_delta_margin_scale: float = 0.0,
    pairwise_reward_delta_clip: float = 2.0,
    large_loss_aux_weight: float = 0.0,
    large_loss_severity_weight: float = 0.0,
    large_loss_aux_detach: bool = False,
    large_loss_bc_weight: float = 0.0,
    external_risk_checkpoint: Optional[Path] = None,
    external_risk_policy_weight: float = 0.0,
    external_risk_policy_threshold: float = 0.6,
    external_risk_policy_family: str = "all",
    external_risk_policy_severity_weight: float = 0.0,
    pairwise_replay_multiplier: int = 0,
    pairwise_data_paths: Optional[Sequence[Path]] = None,
    risk_trace_reports: Optional[Sequence[Path]] = None,
    risk_trace_weight: float = 1.0,
    risk_trace_dataset_start_seeds: Optional[Sequence[int]] = None,
    risk_trace_worst_delta_count: int = 0,
    risk_trace_counterfactual_labels: bool = False,
    risk_trace_min_counterfactual_reward_gap: float = 0.0,
    risk_trace_filter_datasets: bool = False,
    risk_trace_context_radius: int = 0,
    max_transitions: Optional[int] = None,
    device: str = "cpu",
    log_interval: int = 10,
    init_checkpoint: Optional[Path] = None,
    init_q_from_policy: bool = False,
    partial_init_checkpoint: bool = False,
    resume: bool = False,
    mlflow_enabled: bool = False,
    mlflow_tracking_uri: Optional[str] = None,
    mlflow_experiment: str = DEFAULT_EXPERIMENT_NAME,
    mlflow_run_name: Optional[str] = None,
    model_config: Optional[ModelConfig] = None,
) -> List[DiscreteIQLMetrics]:
    """Train a conservative discrete IQL model from one or more fixed trajectory datasets."""
    data_paths = normalize_data_paths(data_path)
    pairwise_paths = [Path(path) for path in (pairwise_data_paths or [])]
    if pairwise_paths and target_mode.lower() != "mc":
        raise ValueError("--pairwise-data is only supported with MC targets because it omits next-state TD fields")
    risk_cases = load_risk_cases_from_paired_trace_reports(
        list(risk_trace_reports or []),
        large_loss_threshold=large_loss_threshold,
        worst_delta_count=risk_trace_worst_delta_count,
        include_counterfactual_labels=risk_trace_counterfactual_labels,
        min_counterfactual_reward_gap=risk_trace_min_counterfactual_reward_gap,
    )
    buf, transition_count, dataset_transition_counts = load_iql_replay_buffer(
        data_paths,
        max_transitions=max_transitions,
        risk_cases=risk_cases,
        risk_weight=risk_trace_weight,
        risk_dataset_start_seeds=risk_trace_dataset_start_seeds,
        apply_risk_cases=bool(risk_cases)
        and (risk_trace_weight > 1.0 or pairwise_weight > 0.0 or pairwise_q_weight > 0.0),
        pairwise_replay_multiplier=pairwise_replay_multiplier,
        pairwise_data_paths=pairwise_paths,
        risk_filter_datasets=risk_trace_filter_datasets,
        risk_context_radius=risk_trace_context_radius,
    )
    if transition_count <= 0:
        raise ValueError(f"no transitions loaded from {data_paths}")

    env_config = EnvConfig()
    model_config = model_config or ModelConfig()
    model = PolicyValueNet(env_config, model_config).to(device)
    target_model = PolicyValueNet(env_config, model_config).to(device)
    external_risk_model: Optional[PolicyValueNet] = None
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)

    start_epoch = 0
    partial_init_report: Optional[dict[str, object]] = None
    if init_checkpoint is not None:
        if partial_init_checkpoint:
            _, partial_init_report = load_compatible_checkpoint(init_checkpoint, model)
            print(
                "Partial checkpoint init: "
                f"loaded={partial_init_report['loaded_keys']} "
                f"missing={len(partial_init_report['missing_keys'])} "
                f"skipped={len(partial_init_report['skipped_keys'])}"
            )
        else:
            load_checkpoint(init_checkpoint, model)
        if init_q_from_policy:
            model.initialize_q_head_from_policy()

    if resume:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoints = sorted(checkpoint_dir.glob("epoch_*.pt"))
        if checkpoints:
            start_epoch = load_checkpoint(checkpoints[-1], model, optimizer)

    target_model.load_state_dict(model.state_dict())
    target_model.eval()
    if external_risk_checkpoint is not None:
        external_risk_model = PolicyValueNet(env_config, model_config).to(device)
        load_checkpoint(external_risk_checkpoint, external_risk_model)
        external_risk_model.eval()
        for param in external_risk_model.parameters():
            param.requires_grad_(False)

    train_config = TrainConfig(
        batch_size=min(batch_size, len(buf)),
        learning_rate=learning_rate,
        device=device,
    )
    iql_config = DiscreteIQLConfig(
        gamma=gamma,
        target_mode=target_mode,
        expectile=expectile,
        temperature=temperature,
        max_weight=max_weight,
        q_weight=q_weight,
        value_weight=value_weight,
        policy_weight=policy_weight,
        bc_weight=bc_weight,
        cql_weight=cql_weight,
        target_update_interval=target_update_interval,
        target_tau=target_tau,
        large_loss_threshold=large_loss_threshold,
        large_loss_penalty=large_loss_penalty,
        large_loss_weight=large_loss_weight,
        pairwise_weight=pairwise_weight,
        pairwise_margin=pairwise_margin,
        pairwise_q_weight=pairwise_q_weight,
        pairwise_q_margin=pairwise_q_margin,
        pairwise_reward_delta_weight=pairwise_reward_delta_weight,
        pairwise_reward_delta_margin_scale=pairwise_reward_delta_margin_scale,
        pairwise_reward_delta_clip=pairwise_reward_delta_clip,
        large_loss_aux_weight=large_loss_aux_weight,
        large_loss_severity_weight=large_loss_severity_weight,
        large_loss_aux_detach=large_loss_aux_detach,
        large_loss_bc_weight=large_loss_bc_weight,
        external_risk_policy_weight=external_risk_policy_weight,
        external_risk_policy_threshold=external_risk_policy_threshold,
        external_risk_policy_family=external_risk_policy_family,
        external_risk_policy_severity_weight=external_risk_policy_severity_weight,
    )
    trainer = DiscreteIQLTrainer(
        model,
        target_model,
        optimizer,
        train_config,
        iql_config,
        external_risk_model=external_risk_model,
    )

    steps_per_epoch = max(1, len(buf) // batch_size)
    all_metrics: List[DiscreteIQLMetrics] = []

    with start_run(
        enabled=mlflow_enabled,
        experiment_name=mlflow_experiment,
        tracking_uri=mlflow_tracking_uri,
        run_name=mlflow_run_name,
        tags={"stage": "training", "method": "discrete_iql"},
    ) as mlflow_run:
        if mlflow_run is not None:
            log_params(
                {
                    "method": "discrete_iql",
                    "data_path": data_paths[0] if len(data_paths) == 1 else ",".join(str(path) for path in data_paths),
                    "data_paths": ",".join(str(path) for path in data_paths),
                    "dataset_transition_counts": ",".join(str(count) for count in dataset_transition_counts),
                    "checkpoint_dir": checkpoint_dir,
                    "epochs": epochs,
                    "start_epoch": start_epoch,
                    "batch_size": train_config.batch_size,
                    "learning_rate": learning_rate,
                    "gamma": gamma,
                    "target_mode": target_mode,
                    "expectile": expectile,
                    "temperature": temperature,
                    "max_weight": max_weight,
                    "q_weight": q_weight,
                    "value_weight": value_weight,
                    "policy_weight": policy_weight,
                    "bc_weight": bc_weight,
                    "cql_weight": cql_weight,
                    "target_update_interval": target_update_interval,
                    "target_tau": target_tau,
                    "large_loss_threshold": large_loss_threshold,
                    "large_loss_penalty": large_loss_penalty,
                    "large_loss_weight": large_loss_weight,
                    "pairwise_weight": pairwise_weight,
                    "pairwise_margin": pairwise_margin,
                    "pairwise_q_weight": pairwise_q_weight,
                    "pairwise_q_margin": pairwise_q_margin,
                    "pairwise_reward_delta_weight": pairwise_reward_delta_weight,
                    "pairwise_reward_delta_margin_scale": pairwise_reward_delta_margin_scale,
                    "pairwise_reward_delta_clip": pairwise_reward_delta_clip,
                    "large_loss_aux_weight": large_loss_aux_weight,
                    "large_loss_severity_weight": large_loss_severity_weight,
                    "large_loss_aux_detach": large_loss_aux_detach,
                    "large_loss_bc_weight": large_loss_bc_weight,
                    "external_risk_checkpoint": external_risk_checkpoint,
                    "external_risk_policy_weight": external_risk_policy_weight,
                    "external_risk_policy_threshold": external_risk_policy_threshold,
                    "external_risk_policy_family": external_risk_policy_family,
                    "external_risk_policy_severity_weight": external_risk_policy_severity_weight,
                    "pairwise_replay_multiplier": pairwise_replay_multiplier,
                    "pairwise_data_paths": ",".join(str(path) for path in pairwise_paths),
                    "risk_trace_reports": ",".join(str(path) for path in (risk_trace_reports or [])),
                    "risk_trace_weight": risk_trace_weight,
                    "risk_trace_dataset_start_seeds": ",".join(str(seed) for seed in (risk_trace_dataset_start_seeds or [])),
                    "risk_trace_worst_delta_count": risk_trace_worst_delta_count,
                    "risk_trace_counterfactual_labels": risk_trace_counterfactual_labels,
                    "risk_trace_min_counterfactual_reward_gap": risk_trace_min_counterfactual_reward_gap,
                    "risk_trace_filter_datasets": risk_trace_filter_datasets,
                    "risk_trace_context_radius": risk_trace_context_radius,
                    "risk_trace_cases": len(risk_cases),
                    "max_transitions": max_transitions,
                    "device": device,
                    "transitions": transition_count,
                    "init_checkpoint": init_checkpoint,
                    "init_q_from_policy": init_q_from_policy,
                    "partial_init_checkpoint": partial_init_checkpoint,
                    "partial_init_loaded_keys": partial_init_report["loaded_keys"] if partial_init_report else None,
                    "partial_init_missing_keys": len(partial_init_report["missing_keys"]) if partial_init_report else None,
                    "partial_init_skipped_keys": len(partial_init_report["skipped_keys"]) if partial_init_report else None,
                    **model_config_params(model_config),
                }
            )

        for epoch in range(start_epoch + 1, epochs + 1):
            epoch_loss = 0.0
            latest_metrics = None
            for step in range(1, steps_per_epoch + 1):
                metrics = trainer.train_step(buf)
                latest_metrics = metrics
                all_metrics.append(metrics)
                epoch_loss += metrics.loss

                global_step = (epoch - 1) * steps_per_epoch + step
                if global_step % target_update_interval == 0:
                    trainer.update_target_network()

                if global_step % log_interval == 0:
                    print(
                        f"epoch {epoch}/{epochs}  step {step}/{steps_per_epoch}  "
                        f"loss={metrics.loss:.4f}  q={metrics.q_loss:.4f}  "
                        f"value={metrics.value_loss:.4f}  policy={metrics.policy_loss:.4f}  "
                        f"bc={metrics.bc_loss:.4f}  cql={metrics.cql_loss:.4f}  "
                        f"pairwise={metrics.pairwise_loss:.4f}/{metrics.pairwise_count}  "
                        f"pairwise_q={metrics.pairwise_q_loss:.4f}  "
                        f"ll_aux={metrics.large_loss_aux_loss:.4f}  "
                        f"ll_sev={metrics.large_loss_severity_loss:.4f}  "
                        f"ll_bc={metrics.large_loss_bc_loss:.4f}/{metrics.large_loss_bc_count}  "
                        f"ext_risk={metrics.external_risk_policy_loss:.4f}  "
                        f"adv={metrics.avg_advantage:.4f}  "
                        f"weight={metrics.avg_weight:.3f}  sample_weight={metrics.avg_sample_weight:.3f}"
                    )

            trainer.update_target_network()
            avg_loss = epoch_loss / steps_per_epoch
            print(f"--- epoch {epoch} avg_loss={avg_loss:.4f}")

            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            checkpoint_path = checkpoint_dir / f"epoch_{epoch:03d}.pt"
            save_checkpoint(checkpoint_path, model, optimizer, step=epoch)
            if mlflow_run is not None and latest_metrics is not None:
                log_metrics(
                    {
                        "train": {
                            "avg_loss": avg_loss,
                            "last_loss": latest_metrics.loss,
                            "last_q_loss": latest_metrics.q_loss,
                            "last_value_loss": latest_metrics.value_loss,
                            "last_policy_loss": latest_metrics.policy_loss,
                            "last_bc_loss": latest_metrics.bc_loss,
                            "last_cql_loss": latest_metrics.cql_loss,
                            "last_pairwise_loss": latest_metrics.pairwise_loss,
                            "last_pairwise_q_loss": latest_metrics.pairwise_q_loss,
                            "last_large_loss_aux_loss": latest_metrics.large_loss_aux_loss,
                            "last_large_loss_severity_loss": latest_metrics.large_loss_severity_loss,
                            "last_large_loss_bc_loss": latest_metrics.large_loss_bc_loss,
                            "last_large_loss_bc_count": latest_metrics.large_loss_bc_count,
                            "last_external_risk_policy_loss": latest_metrics.external_risk_policy_loss,
                            "last_external_risk_policy_probability": latest_metrics.external_risk_policy_probability,
                            "last_external_risk_policy_mass": latest_metrics.external_risk_policy_mass,
                            "last_large_loss_target_rate": latest_metrics.large_loss_target_rate,
                            "last_avg_large_loss_probability": latest_metrics.avg_large_loss_probability,
                            "last_avg_large_loss_severity": latest_metrics.avg_large_loss_severity,
                            "last_avg_q": latest_metrics.avg_q,
                            "last_avg_v": latest_metrics.avg_v,
                            "last_avg_target_q": latest_metrics.avg_target_q,
                            "last_avg_advantage": latest_metrics.avg_advantage,
                            "last_avg_weight": latest_metrics.avg_weight,
                            "last_max_weight": latest_metrics.max_weight,
                            "last_avg_sample_weight": latest_metrics.avg_sample_weight,
                            "last_max_sample_weight": latest_metrics.max_sample_weight,
                            "last_pairwise_count": latest_metrics.pairwise_count,
                        }
                    },
                    step=epoch,
                )
                log_artifact(checkpoint_path, artifact_path="checkpoints")

        if mlflow_run is not None:
            print(f"MLflow run: {mlflow_run.info.run_id}")

    return all_metrics


def normalize_data_paths(data_path: Path | Sequence[Path]) -> list[Path]:
    if isinstance(data_path, (str, Path)):
        return [Path(data_path)]
    paths = [Path(path) for path in data_path]
    if not paths:
        raise ValueError("at least one data path is required")
    return paths


def load_iql_replay_buffer(
    data_paths: Sequence[Path],
    max_transitions: Optional[int] = None,
    risk_cases: Sequence[RiskCase] = (),
    risk_weight: float = 1.0,
    risk_dataset_start_seeds: Optional[Sequence[int]] = None,
    apply_risk_cases: bool = False,
    pairwise_replay_multiplier: int = 0,
    pairwise_data_paths: Optional[Sequence[Path]] = None,
    risk_filter_datasets: bool = False,
    risk_context_radius: int = 0,
) -> tuple[ReplayBuffer | ArrayReplayBuffer | CompositeReplayBuffer, int, list[int]]:
    buffers: list[ReplayBuffer | ArrayReplayBuffer] = []
    counts: list[int] = []
    risk_reports: list[RiskWeightReport] = []
    start_seeds = list(risk_dataset_start_seeds or [])

    for path_index, path in enumerate(data_paths):
        dataset_start_seed = start_seeds[path_index] if path_index < len(start_seeds) else None
        if is_sharded_transition_dataset(path):
            arrays = read_transition_arrays(
                path,
                keys=IQL_ARRAY_KEYS,
                optional_keys=OPTIONAL_IQL_ARRAY_KEYS,
                limit=max_transitions,
            )
            if "steps_to_done" not in arrays:
                arrays["steps_to_done"] = compute_steps_to_done(
                    arrays["episode_index"],
                    np.logical_or(arrays["terminated"], arrays["truncated"]),
                )
            if apply_risk_cases:
                risk_reports.append(
                    apply_risk_case_weights(
                        arrays,
                        risk_cases,
                        weight=risk_weight,
                        dataset_start_seed=dataset_start_seed,
                    )
                )
            indices = np.arange(arrays["action_ids"].shape[0], dtype=np.int64)
            if risk_filter_datasets and path_index > 0 and apply_risk_cases:
                indices = risk_context_indices(arrays, radius=risk_context_radius)
                if indices.size == 0:
                    print(f"risk trace filtered replay source={path} rows=0 skipped")
                    continue
                print(f"risk trace filtered replay source={path} rows={indices.size} radius={risk_context_radius}")
            buffer = ArrayReplayBuffer(
                arrays=arrays,
                indices=indices,
            )
            if pairwise_replay_multiplier > 0 and "pairwise_weights" in arrays:
                pairwise_indices = np.flatnonzero(np.asarray(arrays["pairwise_weights"]) > 0.0).astype(np.int64)
                if pairwise_indices.size > 0:
                    auxiliary_indices = np.repeat(pairwise_indices, int(pairwise_replay_multiplier)).astype(np.int64)
                    buffers.append(ArrayReplayBuffer(arrays=arrays, indices=auxiliary_indices))
                    counts.append(len(auxiliary_indices))
                    print(
                        "pairwise replay "
                        f"source={path} rows={pairwise_indices.size} "
                        f"multiplier={pairwise_replay_multiplier} expanded={len(auxiliary_indices)}"
                    )
        else:
            transitions = read_transitions(path)
            if max_transitions is not None:
                transitions = transitions[: max(0, int(max_transitions))]
            backfill_returns(transitions)
            backfill_steps_to_done(transitions)
            if apply_risk_cases:
                arrays = read_transition_arrays(
                    path,
                    optional_keys=OPTIONAL_IQL_ARRAY_KEYS,
                    limit=max_transitions,
                )
                risk_report = apply_risk_case_weights(
                    arrays,
                    risk_cases,
                    weight=risk_weight,
                    dataset_start_seed=dataset_start_seed,
                )
                risk_reports.append(risk_report)
                for transition, sample_weight in zip(transitions, arrays["sample_weights"].tolist()):
                    transition.info["sample_weight"] = float(sample_weight)
                if risk_filter_datasets and path_index > 0:
                    keep_indices = set(int(index) for index in risk_context_indices(arrays, radius=risk_context_radius).tolist())
                    transitions = [transition for index, transition in enumerate(transitions) if index in keep_indices]
                    if not transitions:
                        print(f"risk trace filtered replay source={path} rows=0 skipped")
                        continue
                    print(f"risk trace filtered replay source={path} rows={len(transitions)} radius={risk_context_radius}")
            buffer = ReplayBuffer(capacity=len(transitions))
            buffer.extend(transitions)

        buffers.append(buffer)
        counts.append(len(buffer))

    for path in pairwise_data_paths or []:
        arrays = read_transition_arrays(
            path,
            keys=PAIRWISE_ARRAY_KEYS,
            optional_keys=OPTIONAL_IQL_ARRAY_KEYS,
            limit=max_transitions,
        )
        if "pairwise_weights" not in arrays:
            print(f"pairwise auxiliary replay source={path} rows=0 skipped")
            continue
        row_count = arrays["action_ids"].shape[0]
        arrays["sample_weights"] = np.zeros(arrays["action_ids"].shape[0], dtype=np.float32)
        arrays.setdefault("steps_to_done", np.zeros(row_count, dtype=np.int32))
        arrays.setdefault("rewards", np.zeros((row_count, 4), dtype=np.float32))
        arrays.setdefault("next_planes", arrays["planes"].copy())
        arrays.setdefault("next_scalars", arrays["scalars"].copy())
        arrays.setdefault("next_action_mask", arrays["action_mask"].copy())
        arrays.setdefault("terminated", np.zeros(row_count, dtype=np.bool_))
        arrays.setdefault("truncated", np.zeros(row_count, dtype=np.bool_))
        pairwise_indices = np.flatnonzero(np.asarray(arrays["pairwise_weights"]) > 0.0).astype(np.int64)
        if pairwise_indices.size == 0:
            print(f"pairwise auxiliary replay source={path} rows=0 skipped")
            continue
        buffer = ArrayReplayBuffer(arrays=arrays, indices=pairwise_indices)
        buffers.append(buffer)
        counts.append(len(buffer))
        print(f"pairwise auxiliary replay source={path} rows={len(buffer)}")

    transition_count = int(sum(counts))
    if transition_count <= 0:
        raise ValueError(f"no transitions loaded from {data_paths}")
    for index, report in enumerate(risk_reports):
        print(
            "risk trace weighting "
            f"dataset={index} cases={report.cases} matched_cases={report.matched_cases} "
            f"weighted_transitions={report.weighted_transitions} "
            f"pairwise_cases={report.pairwise_cases} pairwise_transitions={report.pairwise_transitions} "
            f"matched_by={report.matched_by}"
        )
    if len(buffers) == 1:
        return buffers[0], transition_count, counts
    return CompositeReplayBuffer(buffers), transition_count, counts


def risk_context_indices(arrays: dict[str, np.ndarray], radius: int = 0) -> np.ndarray:
    matches = np.asarray(arrays.get("risk_case_matches", np.zeros(arrays["action_ids"].shape[0], dtype=np.bool_)))
    if not np.any(matches):
        return np.asarray([], dtype=np.int64)
    matched_indices = np.flatnonzero(matches).astype(np.int64)
    radius = max(0, int(radius))
    if radius == 0 or "decision_indices" not in arrays:
        return matched_indices

    episode_indices = np.asarray(arrays["episode_index"], dtype=np.int64)
    seats = np.asarray(arrays["seats"], dtype=np.int64)
    decision_indices = np.asarray(arrays["decision_indices"], dtype=np.int64)
    keep = matches.copy()
    for index in matched_indices.tolist():
        keep |= (
            (episode_indices == episode_indices[index])
            & (seats == seats[index])
            & (np.abs(decision_indices - decision_indices[index]) <= radius)
        )
    return np.flatnonzero(keep).astype(np.int64)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train discrete IQL model")
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        action="append",
        help="JSONL or sharded trajectory data. Repeat to mix heuristic and self-play datasets.",
    )
    parser.add_argument("--checkpoint-dir", type=Path, default=Path("checkpoints/iql"))
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--target-mode", choices=("mc", "td"), default="mc")
    parser.add_argument("--expectile", type=float, default=0.7)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--max-weight", type=float, default=20.0)
    parser.add_argument("--q-weight", type=float, default=1.0)
    parser.add_argument("--value-weight", type=float, default=1.0)
    parser.add_argument("--policy-weight", type=float, default=1.0)
    parser.add_argument("--bc-weight", type=float, default=1.0)
    parser.add_argument("--cql-weight", type=float, default=0.0)
    parser.add_argument("--target-update-interval", type=int, default=25)
    parser.add_argument("--target-tau", type=float, default=0.005)
    parser.add_argument(
        "--large-loss-threshold",
        type=float,
        default=None,
        help="Optional return threshold below which IQL targets receive extra downside penalty.",
    )
    parser.add_argument(
        "--large-loss-penalty",
        type=float,
        default=0.0,
        help="Extra utility penalty multiplier for returns below --large-loss-threshold.",
    )
    parser.add_argument(
        "--large-loss-weight",
        type=float,
        default=1.0,
        help="Loss multiplier for transitions with returns at or below --large-loss-threshold.",
    )
    parser.add_argument(
        "--pairwise-weight",
        type=float,
        default=0.0,
        help="Loss multiplier for paired trace preference margin loss.",
    )
    parser.add_argument(
        "--pairwise-margin",
        type=float,
        default=0.0,
        help="Required policy-logit margin for preferred trace action over avoided trace action.",
    )
    parser.add_argument(
        "--pairwise-q-weight",
        type=float,
        default=0.0,
        help="Loss multiplier for paired trace Q-value preference margin loss.",
    )
    parser.add_argument(
        "--pairwise-q-margin",
        type=float,
        default=0.0,
        help="Required Q-value margin for preferred trace action over avoided trace action.",
    )
    parser.add_argument(
        "--pairwise-reward-delta-weight",
        type=float,
        default=0.0,
        help="Scale pairwise row weights by 1 + this value * clipped reward-gap target.",
    )
    parser.add_argument(
        "--pairwise-reward-delta-margin-scale",
        type=float,
        default=0.0,
        help="Add this value * clipped reward-gap target to pairwise policy/Q margins.",
    )
    parser.add_argument(
        "--pairwise-reward-delta-clip",
        type=float,
        default=2.0,
        help="Maximum reward-gap target used by pairwise reward-delta weighting and margin scaling.",
    )
    parser.add_argument(
        "--large-loss-aux-weight",
        type=float,
        default=0.0,
        help="Loss multiplier for the auxiliary large-loss probability head.",
    )
    parser.add_argument(
        "--large-loss-severity-weight",
        type=float,
        default=0.0,
        help="Loss multiplier for the auxiliary large-loss severity head.",
    )
    parser.add_argument(
        "--large-loss-aux-detach",
        action="store_true",
        help="Train large-loss auxiliary heads from detached trunk features so they do not shape policy/Q features.",
    )
    parser.add_argument(
        "--large-loss-bc-weight",
        type=float,
        default=0.0,
        help="Extra behavior-cloning loss weight applied only to transitions at or below --large-loss-threshold.",
    )
    parser.add_argument(
        "--external-risk-checkpoint",
        type=Path,
        default=None,
        help="Frozen action-risk checkpoint used as a training-side policy regularizer.",
    )
    parser.add_argument(
        "--external-risk-policy-weight",
        type=float,
        default=0.0,
        help="Weight for penalizing policy probability on actions the frozen risk critic marks risky.",
    )
    parser.add_argument(
        "--external-risk-policy-threshold",
        type=float,
        default=0.6,
        help="Risk probability threshold above which legal actions contribute to the external-risk policy loss.",
    )
    parser.add_argument(
        "--external-risk-policy-family",
        type=str,
        default="all",
        help="Action family to regularize with the frozen risk critic, for example all or discard.",
    )
    parser.add_argument(
        "--external-risk-policy-severity-weight",
        type=float,
        default=0.0,
        help="Optional severity contribution in the external-risk policy loss.",
    )
    parser.add_argument(
        "--pairwise-replay-multiplier",
        type=int,
        default=0,
        help="Repeat matched pairwise preference rows into an auxiliary replay source this many times.",
    )
    parser.add_argument(
        "--pairwise-data",
        type=Path,
        action="append",
        default=[],
        help=(
            "Direct pairwise auxiliary NPZ shard. Rows contribute pairwise preferred/avoided "
            "margin losses only; normal IQL sample weights are zeroed."
        ),
    )
    parser.add_argument(
        "--risk-trace-report",
        type=Path,
        action="append",
        default=[],
        help="Paired trace report whose first-divergence high-risk cases should receive extra sample weight.",
    )
    parser.add_argument(
        "--risk-trace-weight",
        type=float,
        default=1.0,
        help="Sample-weight multiplier for transitions matching --risk-trace-report cases.",
    )
    parser.add_argument(
        "--risk-trace-dataset-start-seed",
        type=int,
        action="append",
        default=[],
        help="Dataset start seed for each --data path, used to map risk report seeds to episode_index.",
    )
    parser.add_argument(
        "--risk-trace-worst-delta-count",
        type=int,
        default=0,
        help="Also include this many worst reward-delta first-divergence cases per trace report.",
    )
    parser.add_argument(
        "--risk-trace-counterfactual-labels",
        action="store_true",
        help="Also load paired-trace counterfactual preferred/avoided first-divergence labels.",
    )
    parser.add_argument(
        "--risk-trace-min-counterfactual-reward-gap",
        type=float,
        default=0.0,
        help="Minimum absolute reward gap required for --risk-trace-counterfactual-labels.",
    )
    parser.add_argument(
        "--risk-trace-filter-datasets",
        action="store_true",
        help="For data paths after the first input, train only on exact risk-trace matches plus optional local context.",
    )
    parser.add_argument(
        "--risk-trace-context-radius",
        type=int,
        default=0,
        help="Decision-index radius to keep around exact risk-trace matches when --risk-trace-filter-datasets is set.",
    )
    parser.add_argument(
        "--max-transitions",
        type=int,
        default=None,
        help="Optional row limit per data path. With repeated --data, the limit applies to each dataset.",
    )
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--log-interval", type=int, default=10)
    parser.add_argument("--init-checkpoint", type=Path, default=None, help="Optional BC/IQL checkpoint to warm-start from")
    parser.add_argument(
        "--init-q-from-policy",
        action="store_true",
        help="Copy BC policy logits into q_head. Off by default because policy logits are not reward-scaled.",
    )
    parser.add_argument(
        "--partial-init-checkpoint",
        action="store_true",
        help="Load only compatible tensors from --init-checkpoint for explicit architecture ablations.",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--mlflow", action="store_true", help="Log training params, metrics, and artifacts to MLflow")
    parser.add_argument("--mlflow-tracking-uri", type=str, default=None)
    parser.add_argument("--mlflow-experiment", type=str, default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--mlflow-run-name", type=str, default=None)
    add_model_config_args(parser)
    args = parser.parse_args()

    print("Loading data from:")
    for path in args.data:
        print(f"  {path}")
    metrics = train_iql(
        data_path=args.data,
        checkpoint_dir=args.checkpoint_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        gamma=args.gamma,
        target_mode=args.target_mode,
        expectile=args.expectile,
        temperature=args.temperature,
        max_weight=args.max_weight,
        q_weight=args.q_weight,
        value_weight=args.value_weight,
        policy_weight=args.policy_weight,
        bc_weight=args.bc_weight,
        cql_weight=args.cql_weight,
        target_update_interval=args.target_update_interval,
        target_tau=args.target_tau,
        large_loss_threshold=args.large_loss_threshold,
        large_loss_penalty=args.large_loss_penalty,
        large_loss_weight=args.large_loss_weight,
        pairwise_weight=args.pairwise_weight,
        pairwise_margin=args.pairwise_margin,
        pairwise_q_weight=args.pairwise_q_weight,
        pairwise_q_margin=args.pairwise_q_margin,
        pairwise_reward_delta_weight=args.pairwise_reward_delta_weight,
        pairwise_reward_delta_margin_scale=args.pairwise_reward_delta_margin_scale,
        pairwise_reward_delta_clip=args.pairwise_reward_delta_clip,
        large_loss_aux_weight=args.large_loss_aux_weight,
        large_loss_severity_weight=args.large_loss_severity_weight,
        large_loss_aux_detach=args.large_loss_aux_detach,
        large_loss_bc_weight=args.large_loss_bc_weight,
        external_risk_checkpoint=args.external_risk_checkpoint,
        external_risk_policy_weight=args.external_risk_policy_weight,
        external_risk_policy_threshold=args.external_risk_policy_threshold,
        external_risk_policy_family=args.external_risk_policy_family,
        external_risk_policy_severity_weight=args.external_risk_policy_severity_weight,
        pairwise_replay_multiplier=args.pairwise_replay_multiplier,
        pairwise_data_paths=args.pairwise_data,
        risk_trace_reports=args.risk_trace_report,
        risk_trace_weight=args.risk_trace_weight,
        risk_trace_dataset_start_seeds=args.risk_trace_dataset_start_seed,
        risk_trace_worst_delta_count=args.risk_trace_worst_delta_count,
        risk_trace_counterfactual_labels=args.risk_trace_counterfactual_labels,
        risk_trace_min_counterfactual_reward_gap=args.risk_trace_min_counterfactual_reward_gap,
        risk_trace_filter_datasets=args.risk_trace_filter_datasets,
        risk_trace_context_radius=args.risk_trace_context_radius,
        max_transitions=args.max_transitions,
        device=args.device,
        log_interval=args.log_interval,
        init_checkpoint=args.init_checkpoint,
        init_q_from_policy=args.init_q_from_policy,
        partial_init_checkpoint=args.partial_init_checkpoint,
        resume=args.resume,
        mlflow_enabled=args.mlflow,
        mlflow_tracking_uri=args.mlflow_tracking_uri,
        mlflow_experiment=args.mlflow_experiment,
        mlflow_run_name=args.mlflow_run_name,
        model_config=model_config_from_args(args),
    )
    print(f"Training complete. Final loss: {metrics[-1].loss:.4f}")


if __name__ == "__main__":
    main()

"""Evaluate checkpoint preferences on exact branch-counterfactual shards."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch

from fh_mahjong_ai.branch_cf_calibration import (
    BRANCH_CF_ARRAY_KEYS,
    branch_cf_diagnostics,
    family_pair_counts,
    lower_is_better_preference_summary,
    preference_summary,
    proposal_rerank_diagnostics,
)
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.mlflow_tracking import DEFAULT_EXPERIMENT_NAME, log_artifact, log_metrics, log_params, start_run
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import load_checkpoint, read_transition_arrays


def compute_branch_cf_calibration(
    checkpoint: Path,
    data_path: Path,
    batch_size: int = 4096,
    device: str = "cpu",
    max_transitions: int | None = None,
    proposal_top_ks: tuple[int, ...] = (3, 5, 10, 20),
) -> dict[str, Any]:
    arrays = read_transition_arrays(data_path, keys=BRANCH_CF_ARRAY_KEYS, limit=max_transitions)
    model = PolicyValueNet(EnvConfig(), ModelConfig())
    step = load_checkpoint(checkpoint, model)
    model.to(device)
    model.eval()

    preferred_actions = arrays["pairwise_preferred_action_ids"].astype(np.int64, copy=False)
    avoided_actions = arrays["pairwise_avoided_action_ids"].astype(np.int64, copy=False)
    reward_gaps = arrays["pairwise_reward_delta_targets"].astype(np.float32, copy=False)
    total = int(preferred_actions.shape[0])
    effective_batch_size = max(1, int(batch_size))

    policy_preferred: list[np.ndarray] = []
    policy_avoided: list[np.ndarray] = []
    q_preferred: list[np.ndarray] = []
    q_avoided: list[np.ndarray] = []
    risk_preferred: list[np.ndarray] = []
    risk_avoided: list[np.ndarray] = []
    severity_preferred: list[np.ndarray] = []
    severity_avoided: list[np.ndarray] = []
    policy_argmax: list[np.ndarray] = []
    q_argmax: list[np.ndarray] = []
    policy_scores: list[np.ndarray] = []
    q_scores: list[np.ndarray] = []
    risk_scores: list[np.ndarray] = []

    with torch.inference_mode():
        for start in range(0, total, effective_batch_size):
            end = min(start + effective_batch_size, total)
            planes = torch.from_numpy(arrays["planes"][start:end].astype(np.float32, copy=False)).to(device)
            scalars = torch.from_numpy(arrays["scalars"][start:end].astype(np.float32, copy=False)).to(device)
            mask = torch.from_numpy(arrays["action_mask"][start:end].astype(np.int8, copy=False)).to(device)
            preferred = torch.from_numpy(preferred_actions[start:end]).to(device)
            avoided = torch.from_numpy(avoided_actions[start:end]).to(device)

            logits, _ = model(planes, scalars, mask)
            q_values, _ = model.q_values(planes, scalars, mask)
            policy_preferred.append(logits.gather(1, preferred.unsqueeze(1)).squeeze(1).cpu().numpy())
            policy_avoided.append(logits.gather(1, avoided.unsqueeze(1)).squeeze(1).cpu().numpy())
            q_preferred.append(q_values.gather(1, preferred.unsqueeze(1)).squeeze(1).cpu().numpy())
            q_avoided.append(q_values.gather(1, avoided.unsqueeze(1)).squeeze(1).cpu().numpy())
            policy_argmax.append(torch.argmax(logits, dim=1).cpu().numpy())
            q_argmax.append(torch.argmax(q_values, dim=1).cpu().numpy())
            policy_scores.append(logits.cpu().numpy().astype(np.float32))
            q_scores.append(q_values.cpu().numpy().astype(np.float32))

            if hasattr(model, "action_risk_predictions"):
                risk_logits, severity = model.action_risk_predictions(planes, scalars, mask)
                risk_probs = torch.sigmoid(risk_logits)
                risk_scores.append(risk_probs.cpu().numpy().astype(np.float32))
                risk_preferred.append(risk_probs.gather(1, preferred.unsqueeze(1)).squeeze(1).cpu().numpy())
                risk_avoided.append(risk_probs.gather(1, avoided.unsqueeze(1)).squeeze(1).cpu().numpy())
                severity_preferred.append(severity.gather(1, preferred.unsqueeze(1)).squeeze(1).cpu().numpy())
                severity_avoided.append(severity.gather(1, avoided.unsqueeze(1)).squeeze(1).cpu().numpy())

    policy_preferred_array = np.concatenate(policy_preferred).astype(np.float32)
    policy_avoided_array = np.concatenate(policy_avoided).astype(np.float32)
    q_preferred_array = np.concatenate(q_preferred).astype(np.float32)
    q_avoided_array = np.concatenate(q_avoided).astype(np.float32)
    policy_argmax_array = np.concatenate(policy_argmax).astype(np.int64)
    q_argmax_array = np.concatenate(q_argmax).astype(np.int64)
    policy_scores_array = np.concatenate(policy_scores).astype(np.float32)
    q_scores_array = np.concatenate(q_scores).astype(np.float32)
    risk_scores_array = np.concatenate(risk_scores).astype(np.float32) if risk_scores else None

    report: dict[str, Any] = {
        "schema_version": 1,
        "checkpoint": str(checkpoint),
        "checkpoint_step": step,
        "data": str(data_path),
        "device": device,
        "rows": total,
        "max_transitions": max_transitions,
        "family_pair_counts": family_pair_counts(preferred_actions, avoided_actions),
        "reward_gap": {
            "mean": float(np.mean(reward_gaps)) if reward_gaps.size else 0.0,
            "median": float(np.median(reward_gaps)) if reward_gaps.size else 0.0,
            "max": float(np.max(reward_gaps)) if reward_gaps.size else 0.0,
        },
        "policy_logits": preference_summary(policy_preferred_array, policy_avoided_array, reward_gaps),
        "q_values": preference_summary(q_preferred_array, q_avoided_array, reward_gaps),
        "argmax": {
            "policy_preferred_action_rate": float(np.mean(policy_argmax_array == preferred_actions)) if total else 0.0,
            "policy_avoided_action_rate": float(np.mean(policy_argmax_array == avoided_actions)) if total else 0.0,
            "q_preferred_action_rate": float(np.mean(q_argmax_array == preferred_actions)) if total else 0.0,
            "q_avoided_action_rate": float(np.mean(q_argmax_array == avoided_actions)) if total else 0.0,
        },
        "proposal_rerank": proposal_rerank_diagnostics(
            preferred_actions,
            avoided_actions,
            reward_gaps,
            policy_scores_array,
            q_scores_array,
            arrays["action_mask"].astype(np.int8, copy=False),
            risk_scores=risk_scores_array,
            top_ks=proposal_top_ks,
        ),
    }
    if risk_preferred:
        risk_preferred_array = np.concatenate(risk_preferred).astype(np.float32)
        risk_avoided_array = np.concatenate(risk_avoided).astype(np.float32)
        severity_preferred_array = np.concatenate(severity_preferred).astype(np.float32)
        severity_avoided_array = np.concatenate(severity_avoided).astype(np.float32)
        report["action_risk_probability_lower_is_better"] = lower_is_better_preference_summary(
            risk_preferred_array,
            risk_avoided_array,
            reward_gaps,
        )
        report["action_risk_severity_lower_is_better"] = lower_is_better_preference_summary(
            severity_preferred_array,
            severity_avoided_array,
            reward_gaps,
        )
        report["diagnostics"] = branch_cf_diagnostics(
            preferred_actions,
            avoided_actions,
            reward_gaps,
            policy_preferred_array - policy_avoided_array,
            q_preferred_array - q_avoided_array,
            arrays["scalars"].astype(np.float32, copy=False),
            risk_margins=risk_avoided_array - risk_preferred_array,
        )
    else:
        report["diagnostics"] = branch_cf_diagnostics(
            preferred_actions,
            avoided_actions,
            reward_gaps,
            policy_preferred_array - policy_avoided_array,
            q_preferred_array - q_avoided_array,
            arrays["scalars"].astype(np.float32, copy=False),
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate checkpoint ranking on branch-CF pairwise shards")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--max-transitions", type=int, default=None)
    parser.add_argument(
        "--proposal-top-k",
        type=int,
        action="append",
        default=[],
        help="Policy top-k candidate sizes for proposal/rerank diagnostics. Repeat for multiple k values.",
    )
    parser.add_argument("--report-output", type=Path, default=None)
    parser.add_argument("--mlflow", action="store_true")
    parser.add_argument("--mlflow-tracking-uri", type=str, default=None)
    parser.add_argument("--mlflow-experiment", type=str, default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--mlflow-run-name", type=str, default=None)
    args = parser.parse_args()

    report = compute_branch_cf_calibration(
        checkpoint=args.checkpoint,
        data_path=args.data,
        batch_size=args.batch_size,
        device=args.device,
        max_transitions=args.max_transitions,
        proposal_top_ks=tuple(args.proposal_top_k or [3, 5, 10, 20]),
    )
    with start_run(
        enabled=args.mlflow,
        experiment_name=args.mlflow_experiment,
        tracking_uri=args.mlflow_tracking_uri,
        run_name=args.mlflow_run_name,
        tags={"stage": "branch_cf_calibration"},
    ) as mlflow_run:
        if mlflow_run is not None:
            log_params(
                {
                    "checkpoint": args.checkpoint,
                    "checkpoint_step": report["checkpoint_step"],
                    "data": args.data,
                    "rows": report["rows"],
                    "batch_size": args.batch_size,
                    "device": args.device,
                    "max_transitions": args.max_transitions,
                }
            )
            log_metrics({"branch_cf": report})
        if args.report_output is not None:
            args.report_output.parent.mkdir(parents=True, exist_ok=True)
            args.report_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if mlflow_run is not None:
                log_artifact(args.report_output, artifact_path="reports")
        if mlflow_run is not None:
            print(f"MLflow run: {mlflow_run.info.run_id}")

    print(f"Rows:                  {report['rows']}")
    print(f"Policy preferred rate: {report['policy_logits']['preferred_rate']:.2%}")
    print(f"Q preferred rate:      {report['q_values']['preferred_rate']:.2%}")
    if "action_risk_probability_lower_is_better" in report:
        print(
            "Risk lower rate:       "
            f"{report['action_risk_probability_lower_is_better']['preferred_rate']:.2%}"
        )
    if args.report_output is not None:
        print(f"Report saved to {args.report_output}")


if __name__ == "__main__":
    main()

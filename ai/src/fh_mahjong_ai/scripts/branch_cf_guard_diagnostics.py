"""Evaluate risk-guard choices against exact branch-CF labels."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch

from fh_mahjong_ai.branch_cf_calibration import (
    BRANCH_CF_ARRAY_KEYS,
    guard_choice_diagnostics,
    oracle_preferred_filter_diagnostics,
)
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.policies import RiskGuardedPolicy
from fh_mahjong_ai.storage import load_checkpoint, read_transition_arrays
from fh_mahjong_ai.types import Observation


def compute_guard_diagnostics(
    anchor_checkpoint: Path,
    risk_checkpoint: Path,
    data_path: Path,
    anchor_risk_thresholds: list[float],
    candidate_risk_threshold: float = 0.45,
    min_risk_reduction: float = 0.1,
    max_policy_logit_gap: float = 3.0,
    severity_weight: float = 0.0,
    selection_mode: str = "policy_nearest",
    oracle_max_policy_logit_gaps: list[float | None] | None = None,
    device: str = "cpu",
    max_transitions: int | None = None,
) -> dict[str, Any]:
    arrays = read_transition_arrays(data_path, keys=BRANCH_CF_ARRAY_KEYS, limit=max_transitions)
    anchor_model = PolicyValueNet(EnvConfig(), ModelConfig())
    risk_model = PolicyValueNet(EnvConfig(), ModelConfig())
    anchor_step = load_checkpoint(anchor_checkpoint, anchor_model)
    risk_step = load_checkpoint(risk_checkpoint, risk_model)
    anchor_model.to(device).eval()
    risk_model.to(device).eval()

    preferred = arrays["pairwise_preferred_action_ids"].astype(np.int64, copy=False)
    avoided = arrays["pairwise_avoided_action_ids"].astype(np.int64, copy=False)
    gaps = arrays["pairwise_reward_delta_targets"].astype(np.float32, copy=False)
    reports: dict[str, Any] = {}
    scored_anchor_actions, anchor_logits, risk_probabilities = score_anchor_and_risk(
        anchor_model,
        risk_model,
        arrays,
        device,
    )
    oracle_gap_sweep = (
        oracle_max_policy_logit_gaps
        if oracle_max_policy_logit_gaps is not None
        else [max_policy_logit_gap, 3.0, 6.0, 12.0, 24.0, None]
    )
    for threshold in anchor_risk_thresholds:
        policy = RiskGuardedPolicy(
            anchor_model=anchor_model,
            risk_model=risk_model,
            anchor_risk_threshold=threshold,
            candidate_risk_threshold=candidate_risk_threshold,
            min_risk_reduction=min_risk_reduction,
            max_policy_logit_gap=max_policy_logit_gap,
            severity_weight=severity_weight,
            selection_mode=selection_mode,
            device=device,
        )
        guard_anchor_actions: list[int] = []
        guarded_actions: list[int] = []
        sources: list[str] = []
        for index in range(preferred.shape[0]):
            observation = Observation(
                seat=0,
                planes=arrays["planes"][index].astype(np.float32, copy=False),
                scalars=arrays["scalars"][index].astype(np.float32, copy=False),
                action_mask=arrays["action_mask"][index].astype(np.int8, copy=False),
            )
            choice = policy.choose(observation)
            info = choice.info or {}
            guard_anchor_actions.append(int(info.get("anchor_action_id", choice.action_id)))
            guarded_actions.append(int(choice.action_id))
            sources.append(str(info.get("source", "anchor")))
        threshold_report = guard_choice_diagnostics(
            preferred,
            avoided,
            gaps,
            np.asarray(guard_anchor_actions, dtype=np.int64),
            np.asarray(guarded_actions, dtype=np.int64),
            np.asarray(sources, dtype=object),
        )
        threshold_report["preferred_filter_diagnostics"] = preferred_filter_diagnostics(
            preferred,
            avoided,
            gaps,
            scored_anchor_actions,
            anchor_logits,
            risk_probabilities,
            anchor_risk_threshold=float(threshold),
            candidate_risk_threshold=float(candidate_risk_threshold),
            min_risk_reduction=float(min_risk_reduction),
            max_policy_logit_gap=float(max_policy_logit_gap),
        )
        threshold_report["oracle_preferred_filter_diagnostics"] = oracle_preferred_filter_diagnostics(
            preferred,
            avoided,
            gaps,
            scored_anchor_actions,
            anchor_logits,
            risk_probabilities,
            anchor_risk_threshold=float(threshold),
            candidate_risk_threshold=float(candidate_risk_threshold),
            min_risk_reduction=float(min_risk_reduction),
            max_policy_logit_gaps=oracle_gap_sweep,
        )
        reports[str(threshold)] = threshold_report

    return {
        "schema_version": 1,
        "anchor_checkpoint": str(anchor_checkpoint),
        "anchor_step": anchor_step,
        "risk_checkpoint": str(risk_checkpoint),
        "risk_step": risk_step,
        "data": str(data_path),
        "rows": int(preferred.shape[0]),
        "device": device,
        "guard_config": {
            "anchor_risk_thresholds": anchor_risk_thresholds,
            "candidate_risk_threshold": candidate_risk_threshold,
            "min_risk_reduction": min_risk_reduction,
            "max_policy_logit_gap": max_policy_logit_gap,
            "severity_weight": severity_weight,
            "selection_mode": selection_mode,
            "oracle_max_policy_logit_gaps": oracle_gap_sweep,
            "max_transitions": max_transitions,
        },
        "reports_by_anchor_risk_threshold": reports,
    }


def score_anchor_and_risk(
    anchor_model: PolicyValueNet,
    risk_model: PolicyValueNet,
    arrays: dict[str, np.ndarray],
    device: str,
    batch_size: int = 4096,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    anchor_actions: list[np.ndarray] = []
    logits_list: list[np.ndarray] = []
    risk_list: list[np.ndarray] = []
    total = int(arrays["pairwise_preferred_action_ids"].shape[0])
    with torch.inference_mode():
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            planes = torch.from_numpy(arrays["planes"][start:end].astype(np.float32, copy=False)).to(device)
            scalars = torch.from_numpy(arrays["scalars"][start:end].astype(np.float32, copy=False)).to(device)
            mask = torch.from_numpy(arrays["action_mask"][start:end].astype(np.int8, copy=False)).to(device)
            logits, _ = anchor_model(planes, scalars, mask)
            risk_logits, _ = risk_model.action_risk_predictions(planes, scalars, mask)
            logits_list.append(logits.cpu().numpy().astype(np.float32))
            risk_list.append(torch.sigmoid(risk_logits).cpu().numpy().astype(np.float32))
            anchor_actions.append(torch.argmax(logits, dim=1).cpu().numpy().astype(np.int64))
    return (
        np.concatenate(anchor_actions).astype(np.int64),
        np.concatenate(logits_list).astype(np.float32),
        np.concatenate(risk_list).astype(np.float32),
    )


def preferred_filter_diagnostics(
    preferred_action_ids: np.ndarray,
    avoided_action_ids: np.ndarray,
    reward_gaps: np.ndarray,
    anchor_action_ids: np.ndarray,
    anchor_logits: np.ndarray,
    risk_probabilities: np.ndarray,
    anchor_risk_threshold: float,
    candidate_risk_threshold: float,
    min_risk_reduction: float,
    max_policy_logit_gap: float,
) -> dict[str, Any]:
    rows = np.arange(preferred_action_ids.shape[0], dtype=np.int64)
    preferred_risk = risk_probabilities[rows, preferred_action_ids]
    anchor_risk = risk_probabilities[rows, anchor_action_ids]
    preferred_logit = anchor_logits[rows, preferred_action_ids]
    anchor_logit = anchor_logits[rows, anchor_action_ids]
    risk_reduction = anchor_risk - preferred_risk
    logit_gap = anchor_logit - preferred_logit
    anchor_avoided = anchor_action_ids == avoided_action_ids
    anchor_trigger = anchor_risk >= float(anchor_risk_threshold)
    candidate_risk_pass = preferred_risk <= float(candidate_risk_threshold)
    risk_reduction_pass = risk_reduction >= float(min_risk_reduction)
    logit_gap_pass = logit_gap <= float(max_policy_logit_gap)
    all_pass = anchor_avoided & anchor_trigger & candidate_risk_pass & risk_reduction_pass & logit_gap_pass
    return {
        "anchor_avoided_count": int(np.count_nonzero(anchor_avoided)),
        "anchor_avoided_trigger_count": int(np.count_nonzero(anchor_avoided & anchor_trigger)),
        "preferred_candidate_risk_pass_count": int(np.count_nonzero(anchor_avoided & candidate_risk_pass)),
        "preferred_risk_reduction_pass_count": int(np.count_nonzero(anchor_avoided & risk_reduction_pass)),
        "preferred_logit_gap_pass_count": int(np.count_nonzero(anchor_avoided & logit_gap_pass)),
        "preferred_all_filters_pass_count": int(np.count_nonzero(all_pass)),
        "preferred_all_filters_pass_reward_gap": numeric_summary(reward_gaps[all_pass]),
        "anchor_avoided_reward_gap": numeric_summary(reward_gaps[anchor_avoided]),
        "anchor_avoided_anchor_risk": numeric_summary(anchor_risk[anchor_avoided]),
        "anchor_avoided_preferred_risk": numeric_summary(preferred_risk[anchor_avoided]),
        "anchor_avoided_risk_reduction": numeric_summary(risk_reduction[anchor_avoided]),
        "anchor_avoided_logit_gap": numeric_summary(logit_gap[anchor_avoided]),
    }


def numeric_summary(values: np.ndarray) -> dict[str, float | int | None]:
    values = np.asarray(values, dtype=np.float32)
    if values.size == 0:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare risk-guard choices with exact branch-CF labels")
    parser.add_argument("--anchor-checkpoint", type=Path, required=True)
    parser.add_argument("--risk-checkpoint", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--anchor-risk-threshold", type=float, action="append", default=[])
    parser.add_argument("--candidate-risk-threshold", type=float, default=0.45)
    parser.add_argument("--min-risk-reduction", type=float, default=0.1)
    parser.add_argument("--max-policy-logit-gap", type=float, default=3.0)
    parser.add_argument("--severity-weight", type=float, default=0.0)
    parser.add_argument("--selection-mode", choices=("lowest_risk", "policy_nearest"), default="policy_nearest")
    parser.add_argument(
        "--oracle-max-policy-logit-gap",
        type=float,
        action="append",
        default=[],
        help="Policy logit-gap caps for exact preferred-branch upper-bound diagnostics. Use -1 for no cap.",
    )
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--max-transitions", type=int, default=None)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()

    report = compute_guard_diagnostics(
        anchor_checkpoint=args.anchor_checkpoint,
        risk_checkpoint=args.risk_checkpoint,
        data_path=args.data,
        anchor_risk_thresholds=args.anchor_risk_threshold or [0.6],
        candidate_risk_threshold=args.candidate_risk_threshold,
        min_risk_reduction=args.min_risk_reduction,
        max_policy_logit_gap=args.max_policy_logit_gap,
        severity_weight=args.severity_weight,
        selection_mode=args.selection_mode,
        oracle_max_policy_logit_gaps=[
            None if value < 0.0 else float(value)
            for value in args.oracle_max_policy_logit_gap
        ]
        or None,
        device=args.device,
        max_transitions=args.max_transitions,
    )
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for threshold, threshold_report in report["reports_by_anchor_risk_threshold"].items():
        print(
            f"threshold={threshold} changed={threshold_report['changed_count']} "
            f"rescues={threshold_report['rescue_count']} harms={threshold_report['harm_count']} "
            f"known_delta={threshold_report['known_reward_delta_sum']:.4f}"
        )
    print(f"Report saved to {args.report_output}")


if __name__ == "__main__":
    main()

"""Generate exact branch labels at paired-trace failure states."""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from fh_mahjong_ai.action_catalog import action_family
from fh_mahjong_ai.branch_counterfactuals import best_worst_branch_label, branch_pair_rows_to_arrays
from fh_mahjong_ai.bridge import build_bridge
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.env import MahjongEnv
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.policies import TorchGreedyPolicy
from fh_mahjong_ai.scripts.build_counterfactual_risk_data import write_counterfactual_shard
from fh_mahjong_ai.scripts.generate_data import current_git_commit
from fh_mahjong_ai.scripts.generate_sampled_branch_counterfactuals import family_counts, summarize_branch_results
from fh_mahjong_ai.model_config_args import add_model_config_args, model_config_from_args
from fh_mahjong_ai.storage import load_checkpoint
from fh_mahjong_ai.types import BranchResult, Observation


@dataclass(frozen=True)
class TargetCase:
    seed: int
    seat: int
    decision_index: int
    source_index: int
    actual_delta: float | None = None
    predicted_delta: float | None = None
    left_action_id: int | None = None
    right_action_id: int | None = None
    left_action_label: str | None = None
    right_action_label: str | None = None


def generate_targeted_branch_counterfactual_dataset(
    report_path: Path,
    output_dir: Path,
    anchor_checkpoint: Path,
    case_source: str = "worst_false_positive_cases",
    max_cases: int = 0,
    bridge_kind: str = "go",
    bridge_library_path: Path | None = None,
    match_mode: str = "chongci",
    max_steps_per_episode: int = 0,
    chongci_starting_score: int = 2000,
    chongci_bust_threshold: int = 0,
    chongci_max_hands: int = 50,
    device: str = "cpu",
    model_config: ModelConfig | None = None,
    min_reward_gap: float = 0.0,
    large_loss_threshold: float | None = None,
    high_risk_only: bool = False,
    action_families: Sequence[str] | None = None,
    max_branch_actions: int = 0,
    branch_stop_at_round_end: bool = True,
    branch_max_decisions: int = 0,
    progress_every: int = 0,
    seed: int = 1,
) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    targets = load_target_cases(report, case_source=case_source, max_cases=max_cases)
    if not targets:
        raise ValueError(f"no target cases found in {report_path} source={case_source}")

    model = PolicyValueNet(EnvConfig(), model_config or ModelConfig())
    checkpoint_step = load_checkpoint(anchor_checkpoint, model)
    model.to(device)
    model.eval()
    policy = TorchGreedyPolicy(model, device=device)
    rng = np.random.default_rng(seed)

    rows: list[tuple[Observation, Any, dict[str, Any]]] = []
    branch_calls = 0
    branch_results = 0
    skipped_missing_decision = 0
    skipped_not_enough_actions = 0
    skipped_no_label = 0
    steps = 0
    started_at = time.time()
    targets_by_pair = group_targets_by_seed_seat(targets)

    for seed_seat, pair_targets in targets_by_pair.items():
        episode_seed, seat = seed_seat
        pending = {case.decision_index: case for case in pair_targets}
        config = EnvConfig(
            bridge_kind=bridge_kind,
            bridge_library_path=bridge_library_path,
            learning_seats=(int(seat),),
            auto_play_heuristics=True,
            max_steps_per_episode=max_steps_per_episode,
            match_mode=match_mode,
            chongci_starting_score=chongci_starting_score,
            chongci_bust_threshold=chongci_bust_threshold,
            chongci_max_hands=chongci_max_hands,
        )
        bridge = build_bridge(config)
        env = MahjongEnv(config, bridge=bridge)
        try:
            observation = env.reset(seed=episode_seed)
            reset_result = env.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                skipped_missing_decision += len(pending)
                continue

            while observation.legal_actions and pending:
                if int(observation.seat) != int(seat):
                    raise RuntimeError(f"expected controlled seat {seat}, got {observation.seat}")
                decision_index = int(observation.metadata.get("decision_index", -1))
                target = pending.pop(decision_index, None)
                if target is not None:
                    branch_actions = select_target_branch_actions(
                        observation,
                        target,
                        action_families=action_families,
                        max_branch_actions=max_branch_actions,
                        rng=rng,
                    )
                    if len(branch_actions) < 2:
                        skipped_not_enough_actions += 1
                    else:
                        branch_calls += 1
                        if should_log_progress(progress_every, branch_calls):
                            log_progress(
                                "branch_start",
                                seed=episode_seed,
                                seat=seat,
                                decision_index=decision_index,
                                rows=len(rows),
                                branch_calls=branch_calls,
                                branch_actions=branch_actions,
                                elapsed_seconds=time.time() - started_at,
                            )
                        results = bridge.evaluate_branches(
                            branch_actions,
                            stop_at_round_end=branch_stop_at_round_end,
                            max_decisions=branch_max_decisions,
                        )
                        branch_results += len(results)
                        label = best_worst_branch_label(
                            observation,
                            results,
                            min_reward_gap=min_reward_gap,
                            large_loss_threshold=large_loss_threshold,
                            high_risk_only=high_risk_only,
                            action_families=action_families,
                        )
                        if label is None:
                            skipped_no_label += 1
                        else:
                            rows.append(
                                (
                                    observation,
                                    label,
                                    {
                                        "episode_index": episode_seed,
                                        "acting_seat": int(observation.seat),
                                        "source_index": target.source_index,
                                        "target_actual_delta": target.actual_delta,
                                        "target_predicted_delta": target.predicted_delta,
                                        "left_action_id": target.left_action_id,
                                        "right_action_id": target.right_action_id,
                                        "left_action_label": target.left_action_label,
                                        "right_action_label": target.right_action_label,
                                        "branch_actions": branch_actions,
                                    },
                                )
                            )
                        if should_log_progress(progress_every, branch_calls):
                            log_progress(
                                "branch_done",
                                seed=episode_seed,
                                seat=seat,
                                decision_index=decision_index,
                                rows=len(rows),
                                branch_calls=branch_calls,
                                branch_results=branch_results,
                                skipped_no_label=skipped_no_label,
                                **summarize_branch_results(results),
                                elapsed_seconds=time.time() - started_at,
                            )

                choice = policy.choose(observation)
                step_result = env.step(int(choice.action_id))
                steps += 1
                observation = step_result.observation
                if step_result.terminated or step_result.truncated:
                    break
            skipped_missing_decision += len(pending)
        finally:
            env.close()

    arrays = branch_pair_rows_to_arrays(rows)
    metadata: dict[str, Any] = {
        "source": "go_targeted_paired_trace_branch_evaluation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": current_git_commit(),
        "report_path": str(report_path),
        "case_source": case_source,
        "anchor_checkpoint": str(anchor_checkpoint),
        "anchor_checkpoint_step": int(checkpoint_step),
        "target_cases": len(targets),
        "rows": len(rows),
        "steps": int(steps),
        "branch_calls": int(branch_calls),
        "branch_results": int(branch_results),
        "skipped_missing_decision": int(skipped_missing_decision),
        "skipped_not_enough_actions": int(skipped_not_enough_actions),
        "skipped_no_label": int(skipped_no_label),
        "min_reward_gap": float(min_reward_gap),
        "large_loss_threshold": None if large_loss_threshold is None else float(large_loss_threshold),
        "high_risk_only": bool(high_risk_only),
        "action_families": None if action_families is None else list(action_families),
        "max_branch_actions": int(max_branch_actions),
        "branch_stop_at_round_end": bool(branch_stop_at_round_end),
        "branch_max_decisions": int(branch_max_decisions),
        "match_mode": match_mode,
        "controlled_seats": sorted({case.seat for case in targets}),
        "elapsed_seconds": time.time() - started_at,
        "mean_reward_gap": float(np.mean(arrays["pairwise_reward_delta_targets"])),
        "max_reward_gap": float(np.max(arrays["pairwise_reward_delta_targets"])),
        "preferred_family_counts": family_counts(arrays["pairwise_preferred_action_ids"]),
        "avoided_family_counts": family_counts(arrays["pairwise_avoided_action_ids"]),
    }
    return write_counterfactual_shard(output_dir, arrays, metadata)


def load_target_cases(report: dict[str, Any], case_source: str, max_cases: int = 0) -> list[TargetCase]:
    raw_cases = extract_raw_cases(report, case_source)
    cases: list[TargetCase] = []
    for index, raw in enumerate(raw_cases):
        case = target_case_from_payload(raw, source_index=index)
        if case is not None:
            cases.append(case)
        if max_cases > 0 and len(cases) >= max_cases:
            break
    return cases


def extract_raw_cases(report: dict[str, Any], case_source: str) -> list[dict[str, Any]]:
    if case_source in report and isinstance(report[case_source], list):
        return [case for case in report[case_source] if isinstance(case, dict)]
    summary = report.get("summary")
    if isinstance(summary, dict) and case_source in summary and isinstance(summary[case_source], list):
        return [case for case in summary[case_source] if isinstance(case, dict)]
    if case_source == "pairs":
        pairs = report.get("pairs", [])
        return [pair for pair in pairs if isinstance(pair, dict)]
    raise ValueError(f"case source {case_source!r} not found in report")


def target_case_from_payload(raw: dict[str, Any], source_index: int) -> TargetCase | None:
    decision_index = raw.get("decision_index")
    if decision_index is None:
        divergence = raw.get("first_divergence") or {}
        if isinstance(divergence, dict):
            left_step = divergence.get("left") or {}
            right_step = divergence.get("right") or {}
            decision_index = (right_step or left_step).get("decision_index")
    if decision_index is None:
        return None
    left_action_id = first_int_value(raw, "left_action_id", "anchor_action_id")
    right_action_id = first_int_value(raw, "right_action_id", "candidate_action_id")
    if left_action_id is None or right_action_id is None:
        divergence = raw.get("first_divergence") or {}
        if isinstance(divergence, dict):
            left_step = divergence.get("left") or {}
            right_step = divergence.get("right") or {}
            if left_action_id is None and isinstance(left_step, dict):
                left_action_id = maybe_int(left_step.get("action_id"))
            if right_action_id is None and isinstance(right_step, dict):
                right_action_id = maybe_int(right_step.get("action_id"))
    return TargetCase(
        seed=int(raw["seed"]),
        seat=int(raw["seat"]),
        decision_index=int(decision_index),
        source_index=int(source_index),
        actual_delta=maybe_float(raw.get("actual_delta", raw.get("reward_delta"))),
        predicted_delta=maybe_float(raw.get("predicted_delta")),
        left_action_id=left_action_id,
        right_action_id=right_action_id,
        left_action_label=first_str_value(raw, "left_action_label", "anchor_action_label"),
        right_action_label=first_str_value(raw, "right_action_label", "candidate_action_label"),
    )


def select_target_branch_actions(
    observation: Observation,
    target: TargetCase,
    action_families: Sequence[str] | None,
    max_branch_actions: int,
    rng: np.random.Generator,
) -> list[int]:
    legal_actions = [int(action_id) for action_id in observation.legal_actions]
    allowed = None if action_families is None else {str(family) for family in action_families}
    selected = [
        action_id
        for action_id in legal_actions
        if allowed is None or action_family(action_id) in allowed
    ]
    required = {
        action_id
        for action_id in (target.left_action_id, target.right_action_id)
        if action_id is not None and action_id in legal_actions
    }
    if max_branch_actions > 0 and len(selected) > max_branch_actions:
        selected_set = set(int(action_id) for action_id in rng.choice(selected, size=max_branch_actions, replace=False))
        selected_set.update(required)
        selected = sorted(selected_set)
    else:
        selected = sorted(set(selected) | required)
    return selected


def group_targets_by_seed_seat(cases: Sequence[TargetCase]) -> dict[tuple[int, int], list[TargetCase]]:
    grouped: dict[tuple[int, int], list[TargetCase]] = {}
    for case in cases:
        grouped.setdefault((case.seed, case.seat), []).append(case)
    return {
        key: sorted(values, key=lambda case: case.decision_index)
        for key, values in sorted(grouped.items())
    }


def parse_action_families(values: Sequence[str]) -> tuple[str, ...] | None:
    if not values or any(value == "all" for value in values):
        return None
    return tuple(str(value) for value in values)


def maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def first_int_value(raw: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = maybe_int(raw.get(key))
        if value is not None:
            return value
    return None


def first_str_value(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str):
            return value
    return None


def should_log_progress(progress_every: int, branch_calls: int) -> bool:
    return progress_every > 0 and branch_calls % progress_every == 0


def log_progress(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), file=sys.stderr, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate exact branch labels at paired-trace failure states")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--case-source", type=str, default="worst_false_positive_cases")
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--anchor-checkpoint", type=Path, required=True)
    parser.add_argument("--bridge-kind", choices=["go", "mock"], default="go")
    parser.add_argument("--bridge-library-path", type=Path, default=None)
    parser.add_argument("--match-mode", choices=["classic", "chongci"], default="chongci")
    parser.add_argument("--max-steps-per-episode", type=int, default=0)
    parser.add_argument("--chongci-starting-score", type=int, default=2000)
    parser.add_argument("--chongci-bust-threshold", type=int, default=0)
    parser.add_argument("--chongci-max-hands", type=int, default=50)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--min-reward-gap", type=float, default=0.0)
    parser.add_argument("--large-loss-threshold", type=float, default=None)
    parser.add_argument("--high-risk-only", action="store_true")
    parser.add_argument(
        "--action-family",
        action="append",
        default=[],
        choices=["all", "discard", "chii", "pon", "kan", "win", "pass", "haitei"],
        help="Restrict branch labels to this action family. Repeatable. Default all.",
    )
    parser.add_argument("--max-branch-actions", type=int, default=0)
    parser.add_argument("--branch-through-match-end", action="store_true")
    parser.add_argument("--branch-max-decisions", type=int, default=0)
    parser.add_argument("--progress-every", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1)
    add_model_config_args(parser)
    args = parser.parse_args()

    manifest = generate_targeted_branch_counterfactual_dataset(
        report_path=args.report,
        output_dir=args.output_dir,
        anchor_checkpoint=args.anchor_checkpoint,
        case_source=args.case_source,
        max_cases=args.max_cases,
        bridge_kind=args.bridge_kind,
        bridge_library_path=args.bridge_library_path,
        match_mode=args.match_mode,
        max_steps_per_episode=args.max_steps_per_episode,
        chongci_starting_score=args.chongci_starting_score,
        chongci_bust_threshold=args.chongci_bust_threshold,
        chongci_max_hands=args.chongci_max_hands,
        device=args.device,
        model_config=model_config_from_args(args),
        min_reward_gap=args.min_reward_gap,
        large_loss_threshold=args.large_loss_threshold,
        high_risk_only=args.high_risk_only,
        action_families=parse_action_families(args.action_family),
        max_branch_actions=args.max_branch_actions,
        branch_stop_at_round_end=not args.branch_through_match_end,
        branch_max_decisions=args.branch_max_decisions,
        progress_every=args.progress_every,
        seed=args.seed,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

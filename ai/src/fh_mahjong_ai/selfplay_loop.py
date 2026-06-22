from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping, Optional, Tuple


class GateOutcome(str, Enum):
    PROMOTED = "promoted"
    REJECTED_SCREEN = "rejected_screen"
    REJECTED_CONFIRM = "rejected_confirm"


@dataclass
class GateThresholds:
    screen_margin: float = 0.05
    large_loss_eps: float = 0.0
    positive_eps: float = 0.02


def screen_pass(candidate: Mapping[str, float], best: Mapping[str, float], thresholds: GateThresholds) -> bool:
    return float(candidate["mean_reward"]) >= float(best["mean_reward"]) - thresholds.screen_margin


def confirm_promote(candidate: Mapping[str, float], best: Mapping[str, float], thresholds: GateThresholds) -> bool:
    ci_separated = (
        float(candidate["mean_reward"]) - float(candidate["mean_reward_ci95"])
    ) >= float(best["mean_reward"])
    large_loss_ok = float(candidate["large_loss_rate"]) <= float(best["large_loss_rate"]) + thresholds.large_loss_eps
    positive_ok = (
        float(candidate["positive_reward_rate"]) >= float(best["positive_reward_rate"]) - thresholds.positive_eps
    )
    return ci_separated and large_loss_ok and positive_ok


def gate_decision(
    candidate_screen: Mapping[str, float],
    best_screen: Mapping[str, float],
    thresholds: GateThresholds,
    confirm_evaluator: Callable[[], Tuple[Mapping[str, float], Mapping[str, float]]],
) -> Tuple[GateOutcome, Optional[Mapping[str, float]], Optional[Mapping[str, float]]]:
    """Two-stage gate. confirm_evaluator is only invoked when the screen passes."""
    if not screen_pass(candidate_screen, best_screen, thresholds):
        return GateOutcome.REJECTED_SCREEN, None, None
    candidate_confirm, best_confirm = confirm_evaluator()
    if confirm_promote(candidate_confirm, best_confirm, thresholds):
        return GateOutcome.PROMOTED, candidate_confirm, best_confirm
    return GateOutcome.REJECTED_CONFIRM, candidate_confirm, best_confirm

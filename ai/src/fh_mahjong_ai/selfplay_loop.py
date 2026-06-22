from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple


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


@dataclass
class LoopLedger:
    path: Path
    iteration: int
    fixed_init: str
    base_data: List[str]
    current_best: str
    accumulated_selfplay: List[str]
    current_best_eval: Dict[str, Any] = None  # {"screen": {...}, "confirm": {...}}
    history: List[Dict[str, Any]] = None
    consecutive_non_promotions: int = 0

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        if self.current_best_eval is None:
            self.current_best_eval = {}
        if self.history is None:
            self.history = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "iteration": self.iteration,
            "fixed_init": self.fixed_init,
            "base_data": self.base_data,
            "current_best": self.current_best,
            "accumulated_selfplay": self.accumulated_selfplay,
            "current_best_eval": self.current_best_eval,
            "history": self.history,
            "consecutive_non_promotions": self.consecutive_non_promotions,
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "LoopLedger":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            path=path,
            iteration=int(data["iteration"]),
            fixed_init=str(data["fixed_init"]),
            base_data=list(data["base_data"]),
            current_best=str(data["current_best"]),
            accumulated_selfplay=list(data["accumulated_selfplay"]),
            current_best_eval=dict(data.get("current_best_eval", {})),
            history=list(data.get("history", [])),
            consecutive_non_promotions=int(data.get("consecutive_non_promotions", 0)),
        )

    def record_promotion(self, candidate: str, screen: Dict[str, Any], confirm: Dict[str, Any]) -> None:
        self.current_best = candidate
        self.current_best_eval = {"screen": screen, "confirm": confirm}
        self.consecutive_non_promotions = 0
        self.history.append(
            {
                "iteration": self.iteration,
                "candidate": candidate,
                "screen_metrics": screen,
                "confirm_metrics": confirm,
                "decision": GateOutcome.PROMOTED.value,
            }
        )
        self.save()

    def record_rejection(
        self,
        candidate: str,
        outcome: str,
        screen: Dict[str, Any],
        confirm: Optional[Dict[str, Any]],
    ) -> None:
        self.consecutive_non_promotions += 1
        self.history.append(
            {
                "iteration": self.iteration,
                "candidate": candidate,
                "screen_metrics": screen,
                "confirm_metrics": confirm,
                "decision": outcome,
            }
        )
        self.save()

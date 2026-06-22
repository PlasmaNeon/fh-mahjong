from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .config import EnvConfig, ModelConfig
from .evaluate import evaluate_duplicate_seats
from .model import PolicyValueNet
from .storage import load_checkpoint


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


@dataclass
class LoopConfig:
    run_dir: Path
    fixed_init: str
    base_data: List[str]
    initial_best: str
    iterations: int = 5
    episodes_per_iter: int = 300
    start_seed: int = 810000
    seed_stride: int = 10000
    screen_seeds: int = 80
    confirm_seeds: int = 240
    eval_start_seed: int = 870000
    epochs: int = 4
    batch_size: int = 256
    lr: float = 1e-4
    patience: int = 3
    match_mode: str = "chongci"
    device: str = "cpu"
    bridge_kind: str = "go"
    bridge_library_path: Optional[str] = None
    max_steps_per_episode: Optional[int] = 4000
    seat_policy_template: Sequence[str] = (
        "0=checkpoint:{best}",
        "1=checkpoint:{best}",
        "3=random",
    )
    thresholds: GateThresholds = None

    def __post_init__(self) -> None:
        self.run_dir = Path(self.run_dir)
        if self.thresholds is None:
            self.thresholds = GateThresholds()


def evaluate_checkpoint(
    checkpoint: Path,
    seeds: Sequence[int],
    env_config: EnvConfig,
    model_config: ModelConfig,
    device: str = "cpu",
    match_mode: str = "classic",
    bridge_kind: str = "mock",
    bridge_library_path: Optional[str] = None,
    large_loss_threshold: Optional[float] = -1.0,
    max_steps_per_episode: Optional[int] = None,
) -> Dict[str, Any]:
    """Load a checkpoint and return its duplicate-seat report (top-level gate metrics)."""
    model = PolicyValueNet(env_config, model_config).to(device)
    load_checkpoint(Path(checkpoint), model)
    model.eval()
    return evaluate_duplicate_seats(
        model=model,
        seeds=list(seeds),
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        device=device,
        large_loss_threshold=large_loss_threshold,
        match_mode=match_mode,
        max_steps_per_episode=max_steps_per_episode,
    )

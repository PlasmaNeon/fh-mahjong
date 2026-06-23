from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .config import EnvConfig, ModelConfig
from .evaluate import evaluate_duplicate_seats
from .model import PolicyValueNet
from .scripts.generate_selfplay import (
    build_bridge,
    build_runtime_policies,
    collect_mixed_selfplay_episodes,
    resolve_seat_policies,
)
from .scripts.train_iql import train_iql
from .storage import load_checkpoint, write_transitions_npz_shards


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
    stream_training: bool = False
    stream_shuffle_buffer: int = 50000
    stream_workers: int = 2
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


def generate_iteration_selfplay(
    env_config: EnvConfig,
    out_dir: Path,
    episodes: int,
    start_seed: int,
    best_checkpoint: Optional[str],
    seat_policy_values: Sequence[str],
    device: str = "cpu",
) -> Path:
    """Generate one iteration's mixed self-play shards; returns the shard directory.

    The current best checkpoint path must already be substituted into
    ``seat_policy_values`` (see ``run_iteration``); ``best_checkpoint`` is accepted
    for symmetry/logging only.
    """
    out_dir = Path(out_dir)
    seat_policies = resolve_seat_policies(list(seat_policy_values), bridge_kind=env_config.bridge_kind)
    controlled_seats = tuple(spec.seat for spec in seat_policies if spec.controlled)
    config = EnvConfig(
        action_space_size=env_config.action_space_size,
        plane_shape=env_config.plane_shape,
        scalar_features=env_config.scalar_features,
        bridge_kind=env_config.bridge_kind,
        bridge_library_path=env_config.bridge_library_path,
        learning_seats=controlled_seats,
        auto_play_heuristics=True,
        max_steps_per_episode=env_config.max_steps_per_episode,
        match_mode=env_config.match_mode,
        chongci_starting_score=env_config.chongci_starting_score,
        chongci_bust_threshold=env_config.chongci_bust_threshold,
        chongci_max_hands=env_config.chongci_max_hands,
    )
    runtime_policies = build_runtime_policies(seat_policies, device=device, seed=start_seed)
    bridge = build_bridge(config)
    try:
        transitions = collect_mixed_selfplay_episodes(
            config=config,
            bridge=bridge,
            runtime_policies=runtime_policies,
            episodes=episodes,
            start_seed=start_seed,
        )
    finally:
        close = getattr(bridge, "close", None)
        if callable(close):
            close()
    write_transitions_npz_shards(out_dir, transitions)
    return out_dir


def _seat_policies_for_iteration(template: Sequence[str], best_checkpoint: str) -> List[str]:
    return [value.replace("{best}", str(best_checkpoint)) for value in template]


def run_iteration(
    config: LoopConfig,
    ledger: LoopLedger,
    env_config: EnvConfig,
    model_config: ModelConfig,
) -> GateOutcome:
    """Run one self-play -> train -> gate iteration; mutate and persist the ledger."""
    iteration = ledger.iteration + 1
    ledger.iteration = iteration
    iter_dir = config.run_dir / f"iter{iteration}"

    # 1. Generate self-play with the current best policy.
    seat_values = _seat_policies_for_iteration(config.seat_policy_template, ledger.current_best)
    selfplay_dir = generate_iteration_selfplay(
        env_config=env_config,
        out_dir=iter_dir / "selfplay",
        episodes=config.episodes_per_iter,
        start_seed=config.start_seed + iteration * config.seed_stride,
        best_checkpoint=ledger.current_best,
        seat_policy_values=seat_values,
        device=config.device,
    )
    ledger.accumulated_selfplay.append(str(selfplay_dir))
    ledger.save()

    # 2. Train a fresh candidate from the fixed init on all accumulated data.
    candidate_dir = iter_dir / "candidate"
    data_paths = [Path(p) for p in (ledger.base_data + ledger.accumulated_selfplay)]
    train_iql(
        data_path=data_paths,
        checkpoint_dir=candidate_dir,
        epochs=config.epochs,
        batch_size=config.batch_size,
        learning_rate=config.lr,
        init_checkpoint=Path(config.fixed_init) if config.fixed_init else None,
        device=config.device,
        model_config=model_config,
        stream=config.stream_training,
        stream_shuffle_buffer=config.stream_shuffle_buffer,
        stream_workers=config.stream_workers,
    )
    candidate = candidate_dir / f"epoch_{config.epochs:03d}.pt"

    # 3. Two-stage CI gate.
    def _eval(ckpt: str, seeds_count: int) -> Dict[str, Any]:
        seeds = list(range(config.eval_start_seed, config.eval_start_seed + seeds_count))
        return evaluate_checkpoint(
            checkpoint=Path(ckpt),
            seeds=seeds,
            env_config=env_config,
            model_config=model_config,
            device=config.device,
            match_mode=config.match_mode,
            bridge_kind=config.bridge_kind,
            bridge_library_path=config.bridge_library_path,
            max_steps_per_episode=config.max_steps_per_episode,
        )

    best_screen = ledger.current_best_eval.get("screen") or _eval(ledger.current_best, config.screen_seeds)
    ledger.current_best_eval["screen"] = best_screen
    candidate_screen = _eval(str(candidate), config.screen_seeds)

    def _confirm_evaluator():
        best_confirm = ledger.current_best_eval.get("confirm") or _eval(ledger.current_best, config.confirm_seeds)
        ledger.current_best_eval["confirm"] = best_confirm
        candidate_confirm = _eval(str(candidate), config.confirm_seeds)
        return candidate_confirm, best_confirm

    outcome, cand_confirm, _best_confirm = gate_decision(
        candidate_screen, best_screen, config.thresholds, _confirm_evaluator
    )

    if outcome is GateOutcome.PROMOTED:
        ledger.record_promotion(str(candidate), candidate_screen, dict(cand_confirm))
    else:
        ledger.record_rejection(
            str(candidate),
            outcome.value,
            candidate_screen,
            dict(cand_confirm) if cand_confirm is not None else None,
        )
    return outcome


def run_loop(
    config: LoopConfig,
    env_config: EnvConfig,
    model_config: ModelConfig,
    resume: bool = False,
) -> LoopLedger:
    ledger_path = config.run_dir / "ledger.json"
    if resume and ledger_path.exists():
        ledger = LoopLedger.load(ledger_path)
    else:
        ledger = LoopLedger(
            path=ledger_path,
            iteration=0,
            fixed_init=config.fixed_init,
            base_data=list(config.base_data),
            current_best=config.initial_best,
            accumulated_selfplay=[],
        )
        ledger.save()

    while ledger.iteration < config.iterations:
        if ledger.consecutive_non_promotions >= config.patience:
            print(
                f"stopping: {ledger.consecutive_non_promotions} consecutive non-promotions "
                f">= patience {config.patience}"
            )
            break
        outcome = run_iteration(config, ledger, env_config, model_config)
        print(f"iteration {ledger.iteration}: {outcome.value} (best={ledger.current_best})")
    return ledger

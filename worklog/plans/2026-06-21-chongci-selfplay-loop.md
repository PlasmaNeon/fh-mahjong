# Chongci Self-Play Improvement Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CI-gated mixed self-play improvement loop (`fh-mj-selfplay-loop`) that, each iteration, generates self-play with the current best policy, trains a fresh IQL candidate on all accumulated data, and promotes it only on a confidence-interval-confirmed improvement.

**Architecture:** A Python package module (`selfplay_loop.py`) with pure, unit-tested gate logic and a resumable JSON ledger, plus a thin CLI. It orchestrates the existing library functions — `collect_mixed_selfplay_episodes` + `write_transitions_npz_shards` (generation), `train_iql` (training), `evaluate_duplicate_seats` (evaluation) — so the whole loop is testable on the mock bridge. The deployed "current best" only changes on a CI-confirmed gain, making the loop monotonic (it cannot regress the agent).

**Tech Stack:** Python 3.12 (uv-managed), PyTorch, NumPy, the existing `fh_mahjong_ai` package, `pytest`.

**Spec:** `worklog/specs/2026-06-21-chongci-selfplay-loop-design.md`

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `ai/src/fh_mahjong_ai/selfplay_loop.py` | Gate logic, ledger, config, eval/generation helpers, `run_iteration`/`run_loop` | Create |
| `ai/src/fh_mahjong_ai/scripts/selfplay_loop.py` | `fh-mj-selfplay-loop` CLI | Create |
| `ai/tests/test_selfplay_loop.py` | Unit tests for gate, ledger, helpers, and a mock-bridge iteration/loop | Create |
| `ai/pyproject.toml` | Register the `fh-mj-selfplay-loop` entry point | Modify |
| `ai/AGENTS.md` | Document the module, CLI, and tests | Modify |

All commands run from the repo root with `uv run --project ai ...`. Run a single test with `uv run --project ai pytest ai/tests/test_selfplay_loop.py::<name> -v`.

---

## Task 1: Gate logic (pure, tested)

**Files:**
- Create: `ai/src/fh_mahjong_ai/selfplay_loop.py`
- Test: `ai/tests/test_selfplay_loop.py`

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/test_selfplay_loop.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from fh_mahjong_ai.selfplay_loop import (
    GateOutcome,
    GateThresholds,
    confirm_promote,
    gate_decision,
    screen_pass,
)


def _report(mean, ci95, large_loss, positive):
    return {
        "mean_reward": mean,
        "mean_reward_ci95": ci95,
        "large_loss_rate": large_loss,
        "positive_reward_rate": positive,
    }


def test_screen_pass_allows_candidate_within_margin():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand = _report(-0.03, 0.05, 0.2, 0.45)
    assert screen_pass(cand, best, GateThresholds()) is True


def test_screen_pass_rejects_candidate_below_margin():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand = _report(-0.2, 0.05, 0.2, 0.45)
    assert screen_pass(cand, best, GateThresholds()) is False


def test_confirm_promote_requires_ci_separation():
    best = _report(0.0, 0.05, 0.2, 0.45)
    # candidate mean higher but CI overlaps best mean -> not promoted
    overlap = _report(0.04, 0.06, 0.2, 0.45)
    assert confirm_promote(overlap, best, GateThresholds()) is False
    # candidate CI-separated above best -> promoted
    separated = _report(0.2, 0.05, 0.2, 0.45)
    assert confirm_promote(separated, best, GateThresholds()) is True


def test_confirm_promote_rejects_large_loss_regression():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand = _report(0.3, 0.05, 0.25, 0.45)  # CI-separated but worse tail risk
    assert confirm_promote(cand, best, GateThresholds()) is False


def test_confirm_promote_rejects_positive_rate_drop():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand = _report(0.3, 0.05, 0.2, 0.40)  # positive drop 0.05 > positive_eps 0.02
    assert confirm_promote(cand, best, GateThresholds()) is False


def test_gate_decision_rejects_on_screen_without_confirm():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand_screen = _report(-0.5, 0.05, 0.2, 0.45)
    called = {"confirm": False}

    def confirm_evaluator():
        called["confirm"] = True
        return cand_screen, best

    outcome, cc, bc = gate_decision(cand_screen, best, GateThresholds(), confirm_evaluator)
    assert outcome is GateOutcome.REJECTED_SCREEN
    assert called["confirm"] is False
    assert cc is None and bc is None


def test_gate_decision_promotes_on_confirm():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand_screen = _report(0.1, 0.05, 0.2, 0.45)
    cand_confirm = _report(0.2, 0.05, 0.2, 0.45)
    best_confirm = _report(0.0, 0.05, 0.2, 0.45)

    outcome, cc, bc = gate_decision(
        cand_screen, best, GateThresholds(), lambda: (cand_confirm, best_confirm)
    )
    assert outcome is GateOutcome.PROMOTED
    assert cc == cand_confirm and bc == best_confirm


def test_gate_decision_rejects_on_confirm():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand_screen = _report(0.1, 0.05, 0.2, 0.45)
    cand_confirm = _report(0.02, 0.06, 0.2, 0.45)  # CI overlaps
    best_confirm = _report(0.0, 0.05, 0.2, 0.45)

    outcome, _, _ = gate_decision(
        cand_screen, best, GateThresholds(), lambda: (cand_confirm, best_confirm)
    )
    assert outcome is GateOutcome.REJECTED_CONFIRM
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k "screen or confirm or gate_decision" -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fh_mahjong_ai.selfplay_loop'`.

- [ ] **Step 3: Implement the gate logic**

Create `ai/src/fh_mahjong_ai/selfplay_loop.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k "screen or confirm or gate_decision" -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/selfplay_loop.py ai/tests/test_selfplay_loop.py
git commit -m "feat(selfplay-loop): two-stage CI promotion gate"
```

---

## Task 2: Resumable ledger

**Files:**
- Modify: `ai/src/fh_mahjong_ai/selfplay_loop.py`
- Test: `ai/tests/test_selfplay_loop.py`

- [ ] **Step 1: Write the failing tests**

Append to `ai/tests/test_selfplay_loop.py`:

```python
from fh_mahjong_ai.selfplay_loop import LoopLedger


def test_ledger_save_load_round_trip(tmp_path: Path):
    ledger = LoopLedger(
        path=tmp_path / "ledger.json",
        iteration=0,
        fixed_init="/init.pt",
        base_data=["/base"],
        current_best="/init.pt",
        accumulated_selfplay=[],
    )
    ledger.save()
    loaded = LoopLedger.load(tmp_path / "ledger.json")
    assert loaded.iteration == 0
    assert loaded.current_best == "/init.pt"
    assert loaded.base_data == ["/base"]


def test_ledger_record_promotion_updates_best_and_cache(tmp_path: Path):
    ledger = LoopLedger(
        path=tmp_path / "ledger.json",
        iteration=1,
        fixed_init="/init.pt",
        base_data=["/base"],
        current_best="/init.pt",
        accumulated_selfplay=["/sp1"],
    )
    ledger.current_best_eval = {"screen": {"mean_reward": 0.0}, "confirm": {"mean_reward": 0.0}}
    ledger.record_promotion(
        candidate="/iter1/candidate/epoch_003.pt",
        screen={"mean_reward": 0.1},
        confirm={"mean_reward": 0.2},
    )
    assert ledger.current_best == "/iter1/candidate/epoch_003.pt"
    assert ledger.current_best_eval["confirm"]["mean_reward"] == 0.2
    assert ledger.consecutive_non_promotions == 0
    assert ledger.history[-1]["decision"] == "promoted"


def test_ledger_record_rejection_increments_patience(tmp_path: Path):
    ledger = LoopLedger(
        path=tmp_path / "ledger.json",
        iteration=1,
        fixed_init="/init.pt",
        base_data=["/base"],
        current_best="/init.pt",
        accumulated_selfplay=["/sp1"],
    )
    ledger.record_rejection(
        candidate="/iter1/candidate/epoch_003.pt",
        outcome="rejected_screen",
        screen={"mean_reward": -0.5},
        confirm=None,
    )
    assert ledger.current_best == "/init.pt"
    assert ledger.consecutive_non_promotions == 1
    assert ledger.history[-1]["decision"] == "rejected_screen"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k ledger -q`
Expected: FAIL with `ImportError: cannot import name 'LoopLedger'`.

- [ ] **Step 3: Implement the ledger**

Append to `ai/src/fh_mahjong_ai/selfplay_loop.py` (add `import json` and `from pathlib import Path` and `from typing import Any, Dict, List` to the existing imports at the top of the file):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k ledger -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/selfplay_loop.py ai/tests/test_selfplay_loop.py
git commit -m "feat(selfplay-loop): resumable JSON ledger with promotion/rejection records"
```

---

## Task 3: Loop config + checkpoint evaluation helper

**Files:**
- Modify: `ai/src/fh_mahjong_ai/selfplay_loop.py`
- Test: `ai/tests/test_selfplay_loop.py`

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_selfplay_loop.py`:

```python
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.selfplay_loop import LoopConfig, evaluate_checkpoint
from fh_mahjong_ai.storage import save_checkpoint


def _tiny_env_model():
    env = EnvConfig(action_space_size=8, plane_shape=(2, 3, 1), scalar_features=4, bridge_kind="mock")
    model = ModelConfig(
        channels=4, residual_blocks=1, plane_feature_dim=8,
        scalar_hidden_dim=8, trunk_hidden_dim=8, value_hidden_dim=8,
    )
    return env, model


def test_loop_config_defaults():
    cfg = LoopConfig(
        run_dir=Path("/tmp/run"),
        fixed_init="/init.pt",
        base_data=["/base"],
        initial_best="/init.pt",
    )
    assert cfg.iterations == 5
    assert cfg.screen_seeds == 80
    assert cfg.confirm_seeds == 240
    assert cfg.match_mode == "chongci"


def test_evaluate_checkpoint_returns_gate_metric_keys(tmp_path: Path):
    env, model_cfg = _tiny_env_model()
    ckpt = tmp_path / "m.pt"
    save_checkpoint(ckpt, PolicyValueNet(env, model_cfg))

    report = evaluate_checkpoint(
        checkpoint=ckpt,
        seeds=[1, 2],
        env_config=env,
        model_config=model_cfg,
        device="cpu",
    )
    for key in ("mean_reward", "mean_reward_ci95", "large_loss_rate", "positive_reward_rate"):
        assert key in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k "loop_config or evaluate_checkpoint" -q`
Expected: FAIL with `ImportError: cannot import name 'LoopConfig'`.

- [ ] **Step 3: Implement config + eval helper**

Append to `ai/src/fh_mahjong_ai/selfplay_loop.py` (add to the top-of-file imports: `from typing import Sequence`; and `from .config import EnvConfig, ModelConfig`; `from .model import PolicyValueNet`; `from .storage import load_checkpoint`; `from .evaluate import evaluate_duplicate_seats`):

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k "loop_config or evaluate_checkpoint" -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/selfplay_loop.py ai/tests/test_selfplay_loop.py
git commit -m "feat(selfplay-loop): LoopConfig and checkpoint duplicate-seat eval helper"
```

---

## Task 4: Per-iteration self-play generation helper

**Files:**
- Modify: `ai/src/fh_mahjong_ai/selfplay_loop.py`
- Test: `ai/tests/test_selfplay_loop.py`

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_selfplay_loop.py`:

```python
from fh_mahjong_ai.selfplay_loop import generate_iteration_selfplay
from fh_mahjong_ai.storage import read_transition_arrays


def test_generate_iteration_selfplay_writes_shards(tmp_path: Path):
    env, _ = _tiny_env_model()  # bridge_kind="mock"
    # On the mock bridge all seats must be controlled; use random for every seat.
    out = generate_iteration_selfplay(
        env_config=env,
        out_dir=tmp_path / "sp",
        episodes=2,
        start_seed=500,
        best_checkpoint=None,
        seat_policy_values=["0=random", "1=random", "2=random", "3=random"],
        device="cpu",
    )
    arrays = read_transition_arrays(out, keys=("action_ids",))
    assert arrays["action_ids"].shape[0] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k generate_iteration -q`
Expected: FAIL with `ImportError: cannot import name 'generate_iteration_selfplay'`.

- [ ] **Step 3: Implement the generation helper**

Append to `ai/src/fh_mahjong_ai/selfplay_loop.py` (add imports: `from .scripts.generate_selfplay import resolve_seat_policies, build_runtime_policies, collect_mixed_selfplay_episodes, build_bridge`; `from .storage import write_transitions_npz_shards`):

```python
def generate_iteration_selfplay(
    env_config: EnvConfig,
    out_dir: Path,
    episodes: int,
    start_seed: int,
    best_checkpoint: Optional[str],
    seat_policy_values: Sequence[str],
    device: str = "cpu",
) -> Path:
    """Generate one iteration's mixed self-play shards; returns the shard directory."""
    out_dir = Path(out_dir)
    seat_policies = resolve_seat_policies(list(seat_policy_values), bridge_kind=env_config.bridge_kind)
    controlled_seats = tuple(seat for seat, spec in seat_policies.items() if spec.controlled)
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
```

Note: `resolve_seat_policies` raises if a checkpoint seat policy omits a path, so callers must substitute the real `best_checkpoint` path into the `seat_policy_values` strings before calling (done in Task 5). `best_checkpoint` is accepted here for signature symmetry/logging but the path must already be embedded in `seat_policy_values`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k generate_iteration -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/selfplay_loop.py ai/tests/test_selfplay_loop.py
git commit -m "feat(selfplay-loop): per-iteration mixed self-play generation helper"
```

---

## Task 5: `run_iteration` orchestration

**Files:**
- Modify: `ai/src/fh_mahjong_ai/selfplay_loop.py`
- Test: `ai/tests/test_selfplay_loop.py`

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_selfplay_loop.py`:

```python
from fh_mahjong_ai.selfplay_loop import run_iteration


def test_run_iteration_mock_updates_ledger(tmp_path: Path):
    env, model_cfg = _tiny_env_model()  # bridge_kind="mock"
    init = tmp_path / "init.pt"
    save_checkpoint(init, PolicyValueNet(env, model_cfg))

    cfg = LoopConfig(
        run_dir=tmp_path / "run",
        fixed_init=str(init),
        base_data=[],            # mock: no base data; train on the iteration's self-play only
        initial_best=str(init),
        iterations=1,
        episodes_per_iter=3,
        screen_seeds=2,
        confirm_seeds=2,
        epochs=1,
        batch_size=4,
        match_mode="classic",
        device="cpu",
        bridge_kind="mock",
        max_steps_per_episode=None,
        seat_policy_template=["0=random", "1=random", "2=random", "3=random"],
    )
    ledger = LoopLedger(
        path=cfg.run_dir / "ledger.json",
        iteration=0,
        fixed_init=cfg.fixed_init,
        base_data=cfg.base_data,
        current_best=cfg.initial_best,
        accumulated_selfplay=[],
    )

    outcome = run_iteration(cfg, ledger, env, model_cfg)
    assert outcome in {GateOutcome.PROMOTED, GateOutcome.REJECTED_SCREEN, GateOutcome.REJECTED_CONFIRM}
    # an iteration always appends one history record and one accumulated self-play dir
    assert len(ledger.history) == 1
    assert len(ledger.accumulated_selfplay) == 1
    assert (cfg.run_dir / "iter1" / "candidate").exists()
```

Also add a `seat_policy_template` field to `LoopConfig` (see Step 3).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k run_iteration -q`
Expected: FAIL with `ImportError: cannot import name 'run_iteration'` (or `TypeError` for the new `seat_policy_template` field).

- [ ] **Step 3: Add `seat_policy_template` to LoopConfig and implement `run_iteration`**

In `LoopConfig`, add this field (place it before `thresholds`):

```python
    seat_policy_template: Sequence[str] = (
        "0=checkpoint:{best}",
        "1=checkpoint:{best}",
        "3=random",
    )
```

The default leaves seat 2 to the Go bridge's heuristic auto-play (current-best ×2 + heuristic + random). `{best}` is substituted with the current best checkpoint path each iteration. For the mock bridge (tests), pass an all-controlled template with no `{best}` placeholder.

Add `train_iql` to imports: `from .scripts.train_iql import train_iql`. Then append:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k run_iteration -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/selfplay_loop.py ai/tests/test_selfplay_loop.py
git commit -m "feat(selfplay-loop): run_iteration generate->train->gate orchestration"
```

---

## Task 6: `run_loop` (iterate, patience, resume)

**Files:**
- Modify: `ai/src/fh_mahjong_ai/selfplay_loop.py`
- Test: `ai/tests/test_selfplay_loop.py`

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_selfplay_loop.py`:

```python
from fh_mahjong_ai.selfplay_loop import run_loop


def test_run_loop_runs_iterations_and_is_resumable(tmp_path: Path):
    env, model_cfg = _tiny_env_model()
    init = tmp_path / "init.pt"
    save_checkpoint(init, PolicyValueNet(env, model_cfg))

    cfg = LoopConfig(
        run_dir=tmp_path / "run",
        fixed_init=str(init),
        base_data=[],
        initial_best=str(init),
        iterations=2,
        episodes_per_iter=2,
        screen_seeds=2,
        confirm_seeds=2,
        epochs=1,
        batch_size=4,
        match_mode="classic",
        device="cpu",
        bridge_kind="mock",
        max_steps_per_episode=None,
        seat_policy_template=["0=random", "1=random", "2=random", "3=random"],
    )

    ledger = run_loop(cfg, env, model_cfg)
    assert ledger.iteration == 2
    assert (cfg.run_dir / "ledger.json").exists()

    # Resume is a no-op once iterations are exhausted.
    resumed = run_loop(cfg, env, model_cfg, resume=True)
    assert resumed.iteration == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k run_loop -q`
Expected: FAIL with `ImportError: cannot import name 'run_loop'`.

- [ ] **Step 3: Implement `run_loop`**

Append to `ai/src/fh_mahjong_ai/selfplay_loop.py`:

```python
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
            print(f"stopping: {ledger.consecutive_non_promotions} consecutive non-promotions >= patience {config.patience}")
            break
        outcome = run_iteration(config, ledger, env_config, model_config)
        print(f"iteration {ledger.iteration}: {outcome.value} (best={ledger.current_best})")
    return ledger
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k run_loop -q`
Expected: PASS.

- [ ] **Step 5: Run the whole module test file**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -q`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/selfplay_loop.py ai/tests/test_selfplay_loop.py
git commit -m "feat(selfplay-loop): run_loop with patience and resume"
```

---

## Task 7: CLI `fh-mj-selfplay-loop`

**Files:**
- Create: `ai/src/fh_mahjong_ai/scripts/selfplay_loop.py`
- Modify: `ai/pyproject.toml`
- Test: `ai/tests/test_selfplay_loop.py`

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_selfplay_loop.py`:

```python
def test_cli_runs_loop_on_mock_bridge(tmp_path: Path, monkeypatch):
    import sys
    from fh_mahjong_ai.scripts import selfplay_loop as cli
    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.storage import save_checkpoint

    env = EnvConfig(action_space_size=8, plane_shape=(2, 3, 1), scalar_features=4, bridge_kind="mock")
    model_cfg = ModelConfig(channels=4, residual_blocks=1, plane_feature_dim=8,
                            scalar_hidden_dim=8, trunk_hidden_dim=8, value_hidden_dim=8)
    init = tmp_path / "init.pt"
    save_checkpoint(init, PolicyValueNet(env, model_cfg))

    argv = [
        "fh-mj-selfplay-loop",
        "--run-dir", str(tmp_path / "run"),
        "--fixed-init", str(init),
        "--initial-best", str(init),
        "--iterations", "1",
        "--episodes-per-iter", "2",
        "--screen-seeds", "2",
        "--confirm-seeds", "2",
        "--epochs", "1",
        "--batch-size", "4",
        "--match-mode", "classic",
        "--bridge-kind", "mock",
        "--seat-policy-template", "0=random", "1=random", "2=random", "3=random",
        "--model-channels", "4",
        "--model-residual-blocks", "1",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    assert (tmp_path / "run" / "ledger.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k cli_runs_loop -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fh_mahjong_ai.scripts.selfplay_loop'`.

- [ ] **Step 3: Implement the CLI**

Create `ai/src/fh_mahjong_ai/scripts/selfplay_loop.py`:

```python
"""CLI for the Chongci self-play improvement loop."""
from __future__ import annotations

import argparse
from pathlib import Path

from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args
from fh_mahjong_ai.selfplay_loop import GateThresholds, LoopConfig, run_loop


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Chongci self-play improvement loop")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--fixed-init", type=str, required=True, help="Frozen init checkpoint for every candidate")
    parser.add_argument("--initial-best", type=str, required=True, help="Starting current-best checkpoint")
    parser.add_argument("--base-data", type=str, action="append", default=[], help="Repeatable accumulated base dataset dirs")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--episodes-per-iter", type=int, default=300)
    parser.add_argument("--start-seed", type=int, default=810000)
    parser.add_argument("--seed-stride", type=int, default=10000)
    parser.add_argument("--screen-seeds", type=int, default=80)
    parser.add_argument("--confirm-seeds", type=int, default=240)
    parser.add_argument("--eval-start-seed", type=int, default=870000)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--match-mode", choices=("classic", "chongci"), default="chongci")
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--bridge-kind", choices=("go", "mock"), default="go")
    parser.add_argument("--bridge-lib", type=str, default=None)
    parser.add_argument("--max-steps-per-episode", type=int, default=4000)
    parser.add_argument("--seat-policy-template", nargs="+", default=["0=checkpoint:{best}", "1=checkpoint:{best}", "3=random"])
    parser.add_argument("--screen-margin", type=float, default=0.05)
    parser.add_argument("--large-loss-eps", type=float, default=0.0)
    parser.add_argument("--positive-eps", type=float, default=0.02)
    parser.add_argument("--resume", action="store_true")
    add_model_config_args(parser)
    args = parser.parse_args()

    env_config = EnvConfig(
        bridge_kind=args.bridge_kind,
        bridge_library_path=args.bridge_lib,
        match_mode=args.match_mode,
        max_steps_per_episode=args.max_steps_per_episode,
    )
    model_config = model_config_from_args(args)

    config = LoopConfig(
        run_dir=args.run_dir,
        fixed_init=args.fixed_init,
        base_data=list(args.base_data),
        initial_best=args.initial_best,
        iterations=args.iterations,
        episodes_per_iter=args.episodes_per_iter,
        start_seed=args.start_seed,
        seed_stride=args.seed_stride,
        screen_seeds=args.screen_seeds,
        confirm_seeds=args.confirm_seeds,
        eval_start_seed=args.eval_start_seed,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        patience=args.patience,
        match_mode=args.match_mode,
        device=args.device,
        bridge_kind=args.bridge_kind,
        bridge_library_path=args.bridge_lib,
        max_steps_per_episode=args.max_steps_per_episode,
        seat_policy_template=list(args.seat_policy_template),
        thresholds=GateThresholds(
            screen_margin=args.screen_margin,
            large_loss_eps=args.large_loss_eps,
            positive_eps=args.positive_eps,
        ),
    )
    ledger = run_loop(config, env_config, model_config, resume=args.resume)
    print(f"loop finished at iteration {ledger.iteration}; current best = {ledger.current_best}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Register the entry point**

In `ai/pyproject.toml`, under `[project.scripts]`, add this line after `fh-mj-pipeline`:

```toml
fh-mj-selfplay-loop = "fh_mahjong_ai.scripts.selfplay_loop:main"
```

Then re-sync so the console script and editable install pick up the new module:

```bash
uv sync --project ai --extra dev
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k cli_runs_loop -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/selfplay_loop.py ai/pyproject.toml ai/tests/test_selfplay_loop.py
git commit -m "feat(selfplay-loop): fh-mj-selfplay-loop CLI"
```

---

## Task 8: Docs + full-suite gate

**Files:**
- Modify: `ai/AGENTS.md`

- [ ] **Step 1: Document the module and CLI**

In `ai/AGENTS.md`, add a Key Files bullet near the other `scripts/` entries:

```markdown
- **src/fh_mahjong_ai/selfplay_loop.py** — Chongci self-play improvement loop: pure two-stage CI promotion gate (`screen_pass` / `confirm_promote` / `gate_decision`), resumable JSON `LoopLedger`, `LoopConfig`, and `run_iteration` / `run_loop` that orchestrate generation → fresh-IQL training (from a fixed init on accumulated data) → duplicate-seat gate. Monotonic by design: the current best only changes on a CI-confirmed gain.
- **src/fh_mahjong_ai/scripts/selfplay_loop.py** — CLI `fh-mj-selfplay-loop`: runs N CI-gated self-play iterations, resumable via `--resume`, stopping at `--iterations` or after `--patience` consecutive non-promotions. Reuses the existing (single-env) self-play generation; the loop never edits `best-checkpoints.json` (registry promotion stays manual).
```

And add a tests bullet:

```markdown
- **tests/test_selfplay_loop.py** — Tests for the promotion gate, the resumable ledger, the checkpoint eval and generation helpers, and mock-bridge `run_iteration` / `run_loop` / CLI runs.
```

- [ ] **Step 2: Run the full Python suite**

Run: `uv run --project ai pytest ai/tests -q`
Expected: all PASS (existing tests + the new `test_selfplay_loop.py`).

- [ ] **Step 3: Commit**

```bash
git add ai/AGENTS.md
git commit -m "docs(ai): document fh-mj-selfplay-loop in AGENTS.md"
```

---

## Self-Review Notes

- **Spec coverage:** gate (Task 1), ledger/resume (Task 2), config + eval helper (Task 3), generation reuse (Task 4), iteration flow with fixed-init fresh-IQL on accumulated data + no truncation + eval caching (Task 5), patience/resume loop (Task 6), CLI (Task 7), docs (Task 8). Monotonic-safety property is realized by Task 5's gate-before-promote and Task 2's `record_promotion` only updating `current_best` on PROMOTED.
- **No Go changes**, no registry writes — matches the spec's scope boundaries.
- **Type consistency:** `evaluate_checkpoint` returns a dict with the four gate keys consumed by `screen_pass`/`confirm_promote`; `LoopLedger.current_best_eval` uses `{"screen","confirm"}` consistently across Tasks 2/5; `seat_policy_template` `{best}` substitution defined in Task 5 and defaulted in Tasks 3/7; CLI builds the same `LoopConfig`/`GateThresholds` defined in Tasks 1/3.
- **Mock-bridge note:** tests use all-controlled (`*=random`) seat templates because the mock bridge cannot auto-play heuristic seats; the Go default template uses `{best}` ×2 + random + heuristic (seat 2).

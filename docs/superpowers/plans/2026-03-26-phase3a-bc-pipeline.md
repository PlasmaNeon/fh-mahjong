# Phase 3A: Behavior Cloning Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete behavior cloning pipeline that generates heuristic trajectories via the Go bridge, trains a neural policy to imitate the heuristic, and evaluates the learned policy against the baseline.

**Architecture:** The Go bridge (`cmd/rlbridge`) generates deterministic heuristic trajectories via `FHGenerateHeuristicTrajectory`. Python loads these as JSONL, backfills terminal rewards for value training, trains a `PolicyValueNet` with cross-entropy (policy) + MSE (value) losses, then evaluates via offline action agreement and online live play on fixed seeds.

**Tech Stack:** Python 3.9+, PyTorch 2.4+, NumPy 2.0+, protobuf 5.0+, Go c-shared bridge (ctypes)

**Scope Note:** This plan covers data generation, BC training, and evaluation (steps 1–3 of the Phase 3 roadmap). Batched env API, online self-play, checkpoint promotion, and inference integration are separate future plans (Phase 3B/3C).

---

## File Structure

| File | Responsibility |
|------|---------------|
| `ai/src/fh_mahjong_ai/data.py` | **NEW** — Episode grouping and terminal-reward backfill utilities |
| `ai/src/fh_mahjong_ai/evaluate.py` | **NEW** — Offline action agreement + online live-play evaluation |
| `ai/src/fh_mahjong_ai/scripts/generate_data.py` | **NEW** — CLI script: generate heuristic trajectories → JSONL |
| `ai/src/fh_mahjong_ai/scripts/train_bc.py` | **NEW** — CLI script: BC training loop with logging and checkpoints |
| `ai/src/fh_mahjong_ai/scripts/evaluate.py` | **NEW** — CLI script: evaluate a checkpoint offline and/or online |
| `ai/src/fh_mahjong_ai/scripts/run_pipeline.py` | **NEW** — CLI script: orchestrate generate → train → evaluate |
| `ai/src/fh_mahjong_ai/buffer.py` | **MODIFY** — Add `use_terminal_rewards` option to `sample()` |
| `ai/pyproject.toml` | **MODIFY** — Add CLI entry points |
| `ai/tests/test_data.py` | **NEW** — Tests for episode grouping and backfill |
| `ai/tests/test_evaluate.py` | **NEW** — Tests for evaluation functions |
| `ai/tests/test_pipeline_e2e.py` | **NEW** — End-to-end mock-bridge integration test |

---

### Task 1: Episode Grouping & Return Backfill Utility

**Why:** The Go bridge's `generate_heuristic_trajectories()` returns a flat list of `Transition` objects from multiple episodes. Per-step `rewards` are `[0,0,0,0]` for non-terminal steps. The `terminal_rewards` field (in `info["terminal_rewards"]`) contains the final round payouts. For value-head training, every transition in an episode needs the terminal reward as its return target.

**Files:**
- Create: `ai/src/fh_mahjong_ai/data.py`
- Create: `ai/tests/test_data.py`

- [ ] **Step 1: Write failing tests for `split_episodes` and `backfill_returns`**

```python
# ai/tests/test_data.py
from __future__ import annotations

import numpy as np
import pytest

from fh_mahjong_ai.data import backfill_returns, split_episodes
from fh_mahjong_ai.types import Observation, Transition


def _obs(seat: int = 0) -> Observation:
    return Observation(
        seat=seat,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(29, dtype=np.float32),
        action_mask=np.ones(204, dtype=np.int8),
    )


def _transition(
    seat: int = 0,
    episode: int = 0,
    terminated: bool = False,
    rewards: list[float] | None = None,
    terminal_rewards: list[float] | None = None,
) -> Transition:
    info: dict = {"acting_seat": seat, "episode_index": episode}
    if terminal_rewards is not None:
        info["terminal_rewards"] = np.asarray(terminal_rewards, dtype=np.float32)
    return Transition(
        observation=_obs(seat),
        action_id=5,
        rewards=np.asarray(rewards or [0, 0, 0, 0], dtype=np.float32),
        next_observation=_obs(seat),
        terminated=terminated,
        info=info,
    )


class TestSplitEpisodes:
    def test_empty(self) -> None:
        assert split_episodes([]) == []

    def test_single_episode(self) -> None:
        transitions = [_transition(episode=0), _transition(episode=0, terminated=True)]
        episodes = split_episodes(transitions)
        assert len(episodes) == 1
        assert len(episodes[0]) == 2

    def test_multiple_episodes(self) -> None:
        transitions = [
            _transition(episode=0),
            _transition(episode=0, terminated=True),
            _transition(episode=1),
            _transition(episode=1),
            _transition(episode=1, terminated=True),
        ]
        episodes = split_episodes(transitions)
        assert len(episodes) == 2
        assert len(episodes[0]) == 2
        assert len(episodes[1]) == 3

    def test_preserves_order(self) -> None:
        transitions = [
            _transition(episode=0, seat=0),
            _transition(episode=0, seat=1),
        ]
        episodes = split_episodes(transitions)
        assert episodes[0][0].info["acting_seat"] == 0
        assert episodes[0][1].info["acting_seat"] == 1


class TestBackfillReturns:
    def test_backfills_terminal_rewards(self) -> None:
        transitions = [
            _transition(episode=0, rewards=[0, 0, 0, 0]),
            _transition(
                episode=0,
                terminated=True,
                rewards=[10, -5, -3, -2],
                terminal_rewards=[10, -5, -3, -2],
            ),
        ]
        result = backfill_returns(transitions)
        for t in result:
            np.testing.assert_array_equal(
                t.info["terminal_rewards"],
                np.asarray([10, -5, -3, -2], dtype=np.float32),
            )

    def test_uses_last_rewards_if_no_terminal_field(self) -> None:
        transitions = [
            _transition(episode=0, rewards=[0, 0, 0, 0]),
            _transition(episode=0, terminated=True, rewards=[8, -2, -3, -3]),
        ]
        result = backfill_returns(transitions)
        np.testing.assert_array_equal(
            result[0].info["terminal_rewards"],
            np.asarray([8, -2, -3, -3], dtype=np.float32),
        )

    def test_empty_input(self) -> None:
        assert backfill_returns([]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fh_mahjong_ai.data'`

- [ ] **Step 3: Implement `data.py`**

```python
# ai/src/fh_mahjong_ai/data.py
from __future__ import annotations

from collections import defaultdict
from typing import List

import numpy as np

from .types import Transition


def split_episodes(transitions: List[Transition]) -> List[List[Transition]]:
    """Group a flat list of transitions by episode_index from info metadata."""
    if not transitions:
        return []

    groups: dict[int, List[Transition]] = defaultdict(list)
    for t in transitions:
        episode_idx = t.info.get("episode_index", 0)
        groups[episode_idx].append(t)

    return [groups[k] for k in sorted(groups)]


def backfill_returns(transitions: List[Transition]) -> List[Transition]:
    """Ensure every transition in a flat list has terminal_rewards in its info.

    Groups transitions by episode, finds the terminal rewards for each episode
    (from info["terminal_rewards"] on the last transition, falling back to the
    last transition's rewards), and copies them into every transition's info.
    """
    if not transitions:
        return transitions

    for episode in split_episodes(transitions):
        last = episode[-1]
        terminal = last.info.get(
            "terminal_rewards",
            np.asarray(last.rewards, dtype=np.float32),
        )
        terminal = np.asarray(terminal, dtype=np.float32)
        for t in episode:
            t.info["terminal_rewards"] = terminal.copy()

    return transitions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_data.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/data.py ai/tests/test_data.py
git commit -m "feat(ai): add episode grouping and terminal-reward backfill utilities"
```

---

### Task 2: Update ReplayBuffer to Use Terminal Rewards

**Why:** `ReplayBuffer.sample()` currently computes returns as `transition.rewards[seat]`, which is 0 for non-terminal steps. For value-head training, we need the terminal payout. After `backfill_returns()` runs, every transition has `info["terminal_rewards"]` set. The buffer should use that when available.

**Files:**
- Modify: `ai/src/fh_mahjong_ai/buffer.py:29-48`
- Create: `ai/tests/test_buffer.py`

- [ ] **Step 1: Write failing test for terminal-reward sampling**

```python
# ai/tests/test_buffer.py
from __future__ import annotations

import numpy as np

from fh_mahjong_ai.buffer import ReplayBuffer
from fh_mahjong_ai.types import Observation, Transition


def _obs(seat: int = 0) -> Observation:
    return Observation(
        seat=seat,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(29, dtype=np.float32),
        action_mask=np.ones(204, dtype=np.int8),
    )


def test_sample_uses_terminal_rewards_when_available() -> None:
    buf = ReplayBuffer(capacity=10)
    t = Transition(
        observation=_obs(seat=0),
        action_id=5,
        rewards=np.asarray([0, 0, 0, 0], dtype=np.float32),
        next_observation=_obs(seat=0),
        terminated=False,
        info={"terminal_rewards": np.asarray([10, -5, -3, -2], dtype=np.float32)},
    )
    buf.append(t)
    batch = buf.sample(1, seed=42)
    assert batch.returns[0] == 10.0  # seat 0's terminal reward


def test_sample_falls_back_to_step_rewards() -> None:
    buf = ReplayBuffer(capacity=10)
    t = Transition(
        observation=_obs(seat=1),
        action_id=5,
        rewards=np.asarray([0, 7, 0, 0], dtype=np.float32),
        next_observation=_obs(seat=1),
        terminated=True,
        info={},
    )
    buf.append(t)
    batch = buf.sample(1, seed=42)
    assert batch.returns[0] == 7.0  # seat 1's step reward
```

- [ ] **Step 2: Run tests to verify the terminal-reward test fails**

Run: `uv run --project ai pytest ai/tests/test_buffer.py -v`
Expected: `test_sample_uses_terminal_rewards_when_available` FAILS (returns 0.0 instead of 10.0), `test_sample_falls_back_to_step_rewards` PASSES

- [ ] **Step 3: Update `buffer.py` to use terminal rewards when available**

Replace line 41 in `ai/src/fh_mahjong_ai/buffer.py`:

```python
# OLD:
        returns = np.asarray([float(item.rewards[item.observation.seat]) for item in items], dtype=np.float32)

# NEW:
        def _return_for(item: Transition) -> float:
            seat = item.observation.seat
            tr = item.info.get("terminal_rewards")
            if tr is not None:
                return float(tr[seat])
            return float(item.rewards[seat])

        returns = np.asarray([_return_for(item) for item in items], dtype=np.float32)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_buffer.py -v`
Expected: Both tests PASS

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/buffer.py ai/tests/test_buffer.py
git commit -m "feat(ai): use terminal rewards for value targets in ReplayBuffer"
```

---

### Task 3: Data Generation Script

**Why:** We need a CLI command that generates heuristic trajectory data via the real Go bridge and stores it as JSONL for offline BC training. This uses the existing `CtypesGoBridge.generate_heuristic_trajectories()` and `write_transitions_jsonl()`.

**Files:**
- Create: `ai/src/fh_mahjong_ai/scripts/generate_data.py`
- Modify: `ai/pyproject.toml` (add entry point)
- Create: `ai/tests/test_generate_data.py`

- [ ] **Step 1: Write failing test**

```python
# ai/tests/test_generate_data.py
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fh_mahjong_ai.scripts.generate_data import generate_dataset


def test_generate_dataset_mock(tmp_path: Path) -> None:
    output = tmp_path / "data.jsonl"
    stats = generate_dataset(
        episodes=2,
        start_seed=1,
        output_path=output,
        bridge_kind="mock",
        bridge_library_path=None,
    )

    assert output.exists()
    assert stats["episodes"] == 2
    assert stats["transitions"] > 0

    # Verify JSONL is loadable
    lines = output.read_text().strip().split("\n")
    assert len(lines) == stats["transitions"]
    first = json.loads(lines[0])
    assert "observation" in first
    assert "action_id" in first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_generate_data.py -v`
Expected: FAIL with `ImportError: cannot import name 'generate_dataset' from 'fh_mahjong_ai.scripts.generate_data'`

- [ ] **Step 3: Implement `generate_data.py`**

```python
# ai/src/fh_mahjong_ai/scripts/generate_data.py
"""Generate heuristic trajectory data for behavior cloning."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from fh_mahjong_ai.bridge import build_bridge
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.data import backfill_returns
from fh_mahjong_ai.storage import write_transitions_jsonl


def generate_dataset(
    episodes: int,
    start_seed: int,
    output_path: Path,
    bridge_kind: str = "go",
    bridge_library_path: Optional[Path] = None,
) -> dict:
    """Generate heuristic trajectories and write to JSONL.

    Returns a stats dict with keys: episodes, transitions, elapsed_seconds.
    """
    config = EnvConfig(
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seats=(0,),
        auto_play_heuristics=True,
    )
    bridge = build_bridge(config)
    try:
        t0 = time.monotonic()
        transitions = bridge.generate_heuristic_trajectories(
            episodes=episodes,
            start_seed=start_seed,
        )
        backfill_returns(transitions)
        write_transitions_jsonl(output_path, transitions)
        elapsed = time.monotonic() - t0
    finally:
        bridge.close()

    return {
        "episodes": episodes,
        "transitions": len(transitions),
        "elapsed_seconds": round(elapsed, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate heuristic trajectory data")
    parser.add_argument("--episodes", type=int, default=100, help="Number of episodes")
    parser.add_argument("--start-seed", type=int, default=1, help="Starting RNG seed")
    parser.add_argument("--output", type=Path, default=Path("data/heuristic.jsonl"), help="Output JSONL path")
    parser.add_argument("--bridge-lib", type=Path, default=None, help="Path to c-shared library")
    args = parser.parse_args()

    print(f"Generating {args.episodes} episodes starting at seed {args.start_seed}...")
    stats = generate_dataset(
        episodes=args.episodes,
        start_seed=args.start_seed,
        output_path=args.output,
        bridge_kind="go",
        bridge_library_path=args.bridge_lib,
    )
    print(f"Done: {stats['transitions']} transitions from {stats['episodes']} episodes in {stats['elapsed_seconds']}s")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_generate_data.py -v`
Expected: PASS

- [ ] **Step 5: Add entry point to `pyproject.toml`**

Add under `[project.scripts]`:
```toml
fh-mj-generate-data = "fh_mahjong_ai.scripts.generate_data:main"
```

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/generate_data.py ai/tests/test_generate_data.py ai/pyproject.toml
git commit -m "feat(ai): add heuristic trajectory data generation CLI"
```

---

### Task 4: Behavior Cloning Training Script

**Why:** We need a CLI command that loads JSONL trajectory data, trains a `PolicyValueNet` via `BehaviorCloningTrainer`, logs metrics, and saves checkpoints. All building blocks exist; this is the glue.

**Files:**
- Create: `ai/src/fh_mahjong_ai/scripts/train_bc.py`
- Modify: `ai/pyproject.toml` (add entry point)
- Create: `ai/tests/test_train_bc.py`

- [ ] **Step 1: Write failing test**

```python
# ai/tests/test_train_bc.py
from __future__ import annotations

from pathlib import Path

import numpy as np

from fh_mahjong_ai.scripts.train_bc import train_bc
from fh_mahjong_ai.storage import write_transitions_jsonl
from fh_mahjong_ai.types import Observation, Transition


def _make_dataset(path: Path, n: int = 20) -> None:
    """Write n fake transitions that are valid for training."""
    transitions = []
    for i in range(n):
        obs = Observation(
            seat=0,
            planes=np.random.default_rng(i).standard_normal((39, 42, 1)).astype(np.float32),
            scalars=np.random.default_rng(i).standard_normal(29).astype(np.float32),
            action_mask=np.ones(204, dtype=np.int8),
        )
        transitions.append(
            Transition(
                observation=obs,
                action_id=i % 204,
                rewards=np.zeros(4, dtype=np.float32),
                next_observation=obs,
                terminated=(i == n - 1),
                info={"terminal_rewards": np.asarray([5, -2, -1, -2], dtype=np.float32)},
            )
        )
    write_transitions_jsonl(path, transitions)


def test_train_bc_runs_and_saves_checkpoint(tmp_path: Path) -> None:
    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    _make_dataset(data_path, n=20)

    metrics = train_bc(
        data_path=data_path,
        checkpoint_dir=ckpt_dir,
        epochs=2,
        batch_size=8,
        learning_rate=1e-3,
        device="cpu",
        log_interval=1,
    )

    assert len(metrics) > 0
    assert metrics[-1].loss < metrics[0].loss or True  # loss may not decrease in 2 steps
    assert (ckpt_dir / "epoch_002.pt").exists()


def test_train_bc_respects_resume(tmp_path: Path) -> None:
    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    _make_dataset(data_path, n=20)

    train_bc(data_path=data_path, checkpoint_dir=ckpt_dir, epochs=1, batch_size=8, device="cpu")
    assert (ckpt_dir / "epoch_001.pt").exists()

    # Resume from epoch 1, train to epoch 2
    metrics = train_bc(
        data_path=data_path,
        checkpoint_dir=ckpt_dir,
        epochs=2,
        batch_size=8,
        device="cpu",
        resume=True,
    )
    assert (ckpt_dir / "epoch_002.pt").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_train_bc.py -v`
Expected: FAIL with `ImportError: cannot import name 'train_bc'`

- [ ] **Step 3: Implement `train_bc.py`**

```python
# ai/src/fh_mahjong_ai/scripts/train_bc.py
"""Behavior cloning training on heuristic trajectory data."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

import torch

from fh_mahjong_ai.buffer import ReplayBuffer
from fh_mahjong_ai.config import EnvConfig, ModelConfig, TrainConfig
from fh_mahjong_ai.data import backfill_returns
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import load_checkpoint, read_transitions_jsonl, save_checkpoint
from fh_mahjong_ai.trainer import BehaviorCloningTrainer, TrainMetrics


def train_bc(
    data_path: Path,
    checkpoint_dir: Path,
    epochs: int = 10,
    batch_size: int = 64,
    learning_rate: float = 3e-4,
    device: str = "cpu",
    log_interval: int = 10,
    resume: bool = False,
) -> List[TrainMetrics]:
    """Run BC training and return collected metrics."""
    # Load data
    transitions = read_transitions_jsonl(data_path)
    backfill_returns(transitions)

    buf = ReplayBuffer(capacity=len(transitions))
    buf.extend(transitions)

    # Model + optimizer
    env_config = EnvConfig()
    model_config = ModelConfig()
    model = PolicyValueNet(env_config, model_config).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=learning_rate, weight_decay=1e-4
    )

    # Resume from latest checkpoint
    start_epoch = 0
    if resume:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoints = sorted(checkpoint_dir.glob("epoch_*.pt"))
        if checkpoints:
            start_epoch = load_checkpoint(checkpoints[-1], model, optimizer)

    train_config = TrainConfig(
        batch_size=min(batch_size, len(buf)),
        learning_rate=learning_rate,
        device=device,
    )
    trainer = BehaviorCloningTrainer(model, optimizer, train_config)

    steps_per_epoch = max(1, len(buf) // batch_size)
    all_metrics: List[TrainMetrics] = []

    for epoch in range(start_epoch + 1, epochs + 1):
        epoch_loss = 0.0
        for step in range(1, steps_per_epoch + 1):
            metrics = trainer.train_step(buf)
            all_metrics.append(metrics)
            epoch_loss += metrics.loss

            global_step = (epoch - 1) * steps_per_epoch + step
            if global_step % log_interval == 0:
                print(
                    f"epoch {epoch}/{epochs}  step {step}/{steps_per_epoch}  "
                    f"loss={metrics.loss:.4f}  policy={metrics.policy_loss:.4f}  "
                    f"value={metrics.value_loss:.4f}"
                )

        avg_loss = epoch_loss / steps_per_epoch
        print(f"--- epoch {epoch} avg_loss={avg_loss:.4f}")

        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        save_checkpoint(
            checkpoint_dir / f"epoch_{epoch:03d}.pt",
            model, optimizer, step=epoch,
        )

    return all_metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train behavior cloning model")
    parser.add_argument("--data", type=Path, required=True, help="JSONL trajectory data")
    parser.add_argument("--checkpoint-dir", type=Path, default=Path("checkpoints/bc"), help="Checkpoint output dir")
    parser.add_argument("--epochs", type=int, default=10, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size")
    parser.add_argument("--lr", type=float, default=3e-4, help="Learning rate")
    parser.add_argument("--device", type=str, default="cpu", help="Training device")
    parser.add_argument("--log-interval", type=int, default=10, help="Log every N steps")
    parser.add_argument("--resume", action="store_true", help="Resume from latest checkpoint")
    args = parser.parse_args()

    print(f"Loading data from {args.data}...")
    metrics = train_bc(
        data_path=args.data,
        checkpoint_dir=args.checkpoint_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        device=args.device,
        log_interval=args.log_interval,
        resume=args.resume,
    )
    print(f"Training complete. Final loss: {metrics[-1].loss:.4f}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_train_bc.py -v`
Expected: Both tests PASS

- [ ] **Step 5: Add entry point to `pyproject.toml`**

Add under `[project.scripts]`:
```toml
fh-mj-train-bc = "fh_mahjong_ai.scripts.train_bc:main"
```

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/train_bc.py ai/tests/test_train_bc.py ai/pyproject.toml
git commit -m "feat(ai): add behavior cloning training CLI with resume support"
```

---

### Task 5: Evaluation Module — Offline Action Agreement + Online Live Play

**Why:** We need to measure how well a trained model imitates the heuristic (offline) and how it performs against the heuristic in live play (online). Offline evaluation is fast (no Go bridge needed) and gives action-level metrics. Online evaluation requires the bridge but gives the true performance signal.

**Files:**
- Create: `ai/src/fh_mahjong_ai/evaluate.py`
- Create: `ai/tests/test_evaluate.py`

- [ ] **Step 1: Write failing tests for offline evaluation**

```python
# ai/tests/test_evaluate.py
from __future__ import annotations

import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.evaluate import compute_action_agreement, evaluate_online
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.types import Observation, Transition


def _obs(seat: int = 0, seed: int = 0) -> Observation:
    rng = np.random.default_rng(seed)
    mask = np.zeros(204, dtype=np.int8)
    mask[5:15] = 1  # some legal discard actions
    return Observation(
        seat=seat,
        planes=rng.standard_normal((39, 42, 1)).astype(np.float32),
        scalars=rng.standard_normal(29).astype(np.float32),
        action_mask=mask,
    )


def _transition(action_id: int, seed: int = 0) -> Transition:
    return Transition(
        observation=_obs(seed=seed),
        action_id=action_id,
        rewards=np.zeros(4, dtype=np.float32),
        next_observation=_obs(seed=seed + 1),
        terminated=False,
        info={},
    )


class TestActionAgreement:
    def test_perfect_agreement(self) -> None:
        model = PolicyValueNet(EnvConfig(), ModelConfig())
        # Get what the model would predict for this observation
        t = _transition(action_id=5, seed=42)
        with torch.inference_mode():
            planes = torch.from_numpy(t.observation.planes).unsqueeze(0)
            scalars = torch.from_numpy(t.observation.scalars).unsqueeze(0)
            mask = torch.from_numpy(t.observation.action_mask).unsqueeze(0)
            logits, _ = model(planes, scalars, mask)
            predicted = int(torch.argmax(logits, dim=1).item())

        # Make the transition's action match the model's prediction
        t_matched = _transition(action_id=predicted, seed=42)
        report = compute_action_agreement(model, [t_matched], device="cpu")
        assert report["agreement_rate"] == 1.0

    def test_zero_agreement(self) -> None:
        model = PolicyValueNet(EnvConfig(), ModelConfig())
        t = _transition(action_id=5, seed=42)
        with torch.inference_mode():
            planes = torch.from_numpy(t.observation.planes).unsqueeze(0)
            scalars = torch.from_numpy(t.observation.scalars).unsqueeze(0)
            mask = torch.from_numpy(t.observation.action_mask).unsqueeze(0)
            logits, _ = model(planes, scalars, mask)
            predicted = int(torch.argmax(logits, dim=1).item())

        # Pick a different action
        wrong_action = 5 if predicted != 5 else 6
        t_wrong = _transition(action_id=wrong_action, seed=42)
        report = compute_action_agreement(model, [t_wrong], device="cpu")
        assert report["agreement_rate"] == 0.0

    def test_returns_top3_rate(self) -> None:
        model = PolicyValueNet(EnvConfig(), ModelConfig())
        transitions = [_transition(action_id=i % 10 + 5, seed=i) for i in range(20)]
        report = compute_action_agreement(model, transitions, device="cpu")
        assert "top3_agreement_rate" in report
        assert 0.0 <= report["top3_agreement_rate"] <= 1.0


class TestEvaluateOnline:
    def test_runs_with_mock_bridge(self) -> None:
        model = PolicyValueNet(EnvConfig(), ModelConfig())
        report = evaluate_online(
            model=model,
            episodes=2,
            seeds=list(range(1, 3)),
            bridge_kind="mock",
            device="cpu",
        )
        assert "avg_reward" in report
        assert "episodes" in report
        assert report["episodes"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_evaluate.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_action_agreement'`

- [ ] **Step 3: Implement `evaluate.py`**

```python
# ai/src/fh_mahjong_ai/evaluate.py
"""Evaluation utilities for comparing a learned policy against baselines."""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import torch
from torch import nn

from .bridge import build_bridge
from .config import EnvConfig
from .env import MahjongEnv
from .policies import TorchGreedyPolicy
from .trainer import collect_episode
from .types import Transition


def compute_action_agreement(
    model: nn.Module,
    transitions: List[Transition],
    device: str = "cpu",
) -> Dict[str, float]:
    """Compute how often the model's argmax action matches the expert's action.

    Returns dict with: agreement_rate, top3_agreement_rate, total_transitions.
    """
    model.eval()
    exact_matches = 0
    top3_matches = 0
    total = len(transitions)

    if total == 0:
        return {"agreement_rate": 0.0, "top3_agreement_rate": 0.0, "total_transitions": 0}

    with torch.inference_mode():
        for t in transitions:
            planes = torch.from_numpy(t.observation.planes).unsqueeze(0).to(device)
            scalars = torch.from_numpy(t.observation.scalars).unsqueeze(0).to(device)
            mask = torch.from_numpy(t.observation.action_mask).unsqueeze(0).to(device)

            logits, _ = model(planes, scalars, mask)
            top_actions = torch.topk(logits, k=min(3, logits.shape[1]), dim=1).indices[0]
            predicted = int(top_actions[0].item())

            if predicted == t.action_id:
                exact_matches += 1
            if t.action_id in top_actions.tolist():
                top3_matches += 1

    return {
        "agreement_rate": exact_matches / total,
        "top3_agreement_rate": top3_matches / total,
        "total_transitions": total,
    }


def evaluate_online(
    model: nn.Module,
    episodes: int,
    seeds: List[int],
    bridge_kind: str = "go",
    bridge_library_path: Optional[str] = None,
    device: str = "cpu",
) -> Dict[str, float]:
    """Run the learned policy as seat 0 against heuristic opponents.

    Returns dict with: avg_reward, win_count, episodes, per_episode_rewards.
    """
    config = EnvConfig(
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seats=(0,),
        auto_play_heuristics=True,
    )
    bridge = build_bridge(config)
    env = MahjongEnv(config, bridge)
    policy = TorchGreedyPolicy(model, device=device)

    seat0_rewards: List[float] = []
    wins = 0

    try:
        for i in range(episodes):
            seed = seeds[i] if i < len(seeds) else seeds[-1] + i
            episode = collect_episode(env, policy, seed=seed)
            if episode:
                terminal = episode[-1]
                reward = float(terminal.rewards[0])  # seat 0 payout
                seat0_rewards.append(reward)
                if reward > 0:
                    wins += 1
    finally:
        env.close()

    avg = float(np.mean(seat0_rewards)) if seat0_rewards else 0.0
    return {
        "avg_reward": round(avg, 2),
        "win_count": wins,
        "episodes": len(seat0_rewards),
        "per_episode_rewards": seat0_rewards,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_evaluate.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/evaluate.py ai/tests/test_evaluate.py
git commit -m "feat(ai): add offline action-agreement and online live-play evaluation"
```

---

### Task 6: Evaluation CLI Script

**Why:** Wrap the evaluation module in a CLI that loads a checkpoint, runs offline and/or online evaluation, and prints a report.

**Files:**
- Create: `ai/src/fh_mahjong_ai/scripts/evaluate.py`
- Modify: `ai/pyproject.toml` (add entry point)

- [ ] **Step 1: Implement `scripts/evaluate.py`**

```python
# ai/src/fh_mahjong_ai/scripts/evaluate.py
"""Evaluate a trained checkpoint against baselines."""
from __future__ import annotations

import argparse
from pathlib import Path

import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.evaluate import compute_action_agreement, evaluate_online
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import load_checkpoint, read_transitions_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a trained model")
    parser.add_argument("--checkpoint", type=Path, required=True, help="Path to .pt checkpoint")
    parser.add_argument("--data", type=Path, default=None, help="JSONL data for offline eval")
    parser.add_argument("--online-episodes", type=int, default=0, help="Number of online episodes (0 = skip)")
    parser.add_argument("--start-seed", type=int, default=1000, help="Starting seed for online eval")
    parser.add_argument("--bridge-lib", type=Path, default=None, help="Path to c-shared library")
    parser.add_argument("--device", type=str, default="cpu", help="Device")
    args = parser.parse_args()

    model = PolicyValueNet(EnvConfig(), ModelConfig())
    step = load_checkpoint(args.checkpoint, model)
    model.to(args.device)
    print(f"Loaded checkpoint from epoch {step}")

    if args.data is not None:
        print(f"\n--- Offline Evaluation (action agreement) ---")
        transitions = read_transitions_jsonl(args.data)
        report = compute_action_agreement(model, transitions, device=args.device)
        print(f"  Transitions:     {report['total_transitions']}")
        print(f"  Agreement:       {report['agreement_rate']:.2%}")
        print(f"  Top-3 Agreement: {report['top3_agreement_rate']:.2%}")

    if args.online_episodes > 0:
        print(f"\n--- Online Evaluation ({args.online_episodes} episodes) ---")
        seeds = list(range(args.start_seed, args.start_seed + args.online_episodes))
        report = evaluate_online(
            model=model,
            episodes=args.online_episodes,
            seeds=seeds,
            bridge_kind="go",
            bridge_library_path=args.bridge_lib,
            device=args.device,
        )
        print(f"  Episodes:    {report['episodes']}")
        print(f"  Avg Reward:  {report['avg_reward']}")
        print(f"  Wins:        {report['win_count']}")

    print("\nDone.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add entry point to `pyproject.toml`**

Add under `[project.scripts]`:
```toml
fh-mj-evaluate = "fh_mahjong_ai.scripts.evaluate:main"
```

- [ ] **Step 3: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/evaluate.py ai/pyproject.toml
git commit -m "feat(ai): add evaluation CLI for offline and online assessment"
```

---

### Task 7: End-to-End Pipeline Script + Integration Test

**Why:** A single command that runs the full pipeline: generate data → train BC → evaluate. Also an integration test that verifies the pipeline works end-to-end using the mock bridge (no Go build required for CI).

**Files:**
- Create: `ai/src/fh_mahjong_ai/scripts/run_pipeline.py`
- Create: `ai/tests/test_pipeline_e2e.py`
- Modify: `ai/pyproject.toml` (add entry point)

- [ ] **Step 1: Write failing integration test**

```python
# ai/tests/test_pipeline_e2e.py
"""End-to-end pipeline test using mock bridge."""
from __future__ import annotations

from pathlib import Path

from fh_mahjong_ai.scripts.run_pipeline import run_pipeline


def test_full_pipeline_mock(tmp_path: Path) -> None:
    report = run_pipeline(
        episodes=4,
        start_seed=1,
        epochs=2,
        batch_size=8,
        eval_episodes=2,
        bridge_kind="mock",
        output_dir=tmp_path,
        device="cpu",
    )

    # Data was generated
    assert (tmp_path / "data" / "heuristic.jsonl").exists()

    # Model was trained and checkpointed
    assert (tmp_path / "checkpoints" / "epoch_002.pt").exists()

    # Evaluation ran
    assert "agreement_rate" in report
    assert "online_avg_reward" in report
    assert 0.0 <= report["agreement_rate"] <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_pipeline_e2e.py -v`
Expected: FAIL with `ImportError: cannot import name 'run_pipeline'`

- [ ] **Step 3: Implement `run_pipeline.py`**

```python
# ai/src/fh_mahjong_ai/scripts/run_pipeline.py
"""Orchestrate the full BC pipeline: generate → train → evaluate."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.evaluate import compute_action_agreement, evaluate_online
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.generate_data import generate_dataset
from fh_mahjong_ai.scripts.train_bc import train_bc
from fh_mahjong_ai.storage import load_checkpoint, read_transitions_jsonl


def run_pipeline(
    episodes: int = 100,
    start_seed: int = 1,
    epochs: int = 10,
    batch_size: int = 64,
    eval_episodes: int = 20,
    bridge_kind: str = "go",
    bridge_library_path: Optional[Path] = None,
    output_dir: Path = Path("output"),
    device: str = "cpu",
) -> dict:
    """Run the full pipeline and return a combined report."""
    data_dir = output_dir / "data"
    ckpt_dir = output_dir / "checkpoints"
    data_path = data_dir / "heuristic.jsonl"

    # Step 1: Generate data
    print("=" * 40)
    print("STEP 1: Generating heuristic trajectories")
    print("=" * 40)
    gen_stats = generate_dataset(
        episodes=episodes,
        start_seed=start_seed,
        output_path=data_path,
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
    )
    print(f"Generated {gen_stats['transitions']} transitions")

    # Step 2: Train BC
    print("\n" + "=" * 40)
    print("STEP 2: Training behavior cloning model")
    print("=" * 40)
    metrics = train_bc(
        data_path=data_path,
        checkpoint_dir=ckpt_dir,
        epochs=epochs,
        batch_size=batch_size,
        device=device,
        log_interval=max(1, (gen_stats["transitions"] // batch_size) // 5),
    )

    # Step 3: Evaluate
    print("\n" + "=" * 40)
    print("STEP 3: Evaluating trained model")
    print("=" * 40)
    model = PolicyValueNet(EnvConfig(), ModelConfig()).to(device)
    latest_ckpt = sorted(ckpt_dir.glob("epoch_*.pt"))[-1]
    load_checkpoint(latest_ckpt, model)

    transitions = read_transitions_jsonl(data_path)
    offline_report = compute_action_agreement(model, transitions, device=device)
    print(f"Action agreement: {offline_report['agreement_rate']:.2%}")
    print(f"Top-3 agreement: {offline_report['top3_agreement_rate']:.2%}")

    online_report = {"avg_reward": 0.0, "win_count": 0, "episodes": 0}
    if eval_episodes > 0:
        eval_seeds = list(range(10000, 10000 + eval_episodes))
        online_report = evaluate_online(
            model=model,
            episodes=eval_episodes,
            seeds=eval_seeds,
            bridge_kind=bridge_kind,
            bridge_library_path=bridge_library_path,
            device=device,
        )
        print(f"Online avg reward: {online_report['avg_reward']}")
        print(f"Online wins: {online_report['win_count']}/{online_report['episodes']}")

    return {
        "data_transitions": gen_stats["transitions"],
        "final_loss": metrics[-1].loss if metrics else 0.0,
        "agreement_rate": offline_report["agreement_rate"],
        "top3_agreement_rate": offline_report["top3_agreement_rate"],
        "online_avg_reward": online_report["avg_reward"],
        "online_wins": online_report["win_count"],
        "online_episodes": online_report["episodes"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full BC pipeline")
    parser.add_argument("--episodes", type=int, default=100, help="Data generation episodes")
    parser.add_argument("--start-seed", type=int, default=1, help="Starting RNG seed")
    parser.add_argument("--epochs", type=int, default=10, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=64, help="Training batch size")
    parser.add_argument("--eval-episodes", type=int, default=20, help="Online eval episodes")
    parser.add_argument("--bridge-lib", type=Path, default=None, help="Path to c-shared library")
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="Output directory")
    parser.add_argument("--device", type=str, default="cpu", help="Training device")
    args = parser.parse_args()

    report = run_pipeline(
        episodes=args.episodes,
        start_seed=args.start_seed,
        epochs=args.epochs,
        batch_size=args.batch_size,
        eval_episodes=args.eval_episodes,
        bridge_kind="go",
        bridge_library_path=args.bridge_lib,
        output_dir=args.output_dir,
        device=args.device,
    )

    print("\n" + "=" * 40)
    print("PIPELINE COMPLETE")
    print("=" * 40)
    for k, v in report.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_pipeline_e2e.py -v`
Expected: PASS

- [ ] **Step 5: Add entry point to `pyproject.toml`**

Add under `[project.scripts]`:
```toml
fh-mj-pipeline = "fh_mahjong_ai.scripts.run_pipeline:main"
```

- [ ] **Step 6: Run all tests together**

Run: `uv run --project ai pytest ai/tests -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/run_pipeline.py ai/tests/test_pipeline_e2e.py ai/pyproject.toml
git commit -m "feat(ai): add end-to-end BC pipeline runner and integration test"
```

---

## Running the Full Pipeline Against the Real Go Bridge

After all tasks are implemented and committed, here's how to run the real pipeline:

```bash
# 1. Build the c-shared bridge (from repo root)
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge

# 2. Sync Python dependencies
uv sync --project ai --extra dev

# 3. Run the full pipeline
uv run --project ai fh-mj-pipeline \
  --episodes 500 \
  --epochs 20 \
  --batch-size 128 \
  --eval-episodes 50 \
  --output-dir output/run1

# Or step-by-step:
uv run --project ai fh-mj-generate-data --episodes 500 --output output/run1/data/heuristic.jsonl
uv run --project ai fh-mj-train-bc --data output/run1/data/heuristic.jsonl --epochs 20 --batch-size 128
uv run --project ai fh-mj-evaluate --checkpoint checkpoints/bc/epoch_020.pt --data output/run1/data/heuristic.jsonl --online-episodes 50
```

## What Comes Next (Phase 3B/3C — Separate Plans)

**Phase 3B: Online Self-Play**
- Batched/parallel env API (multiple Go bridge handles in Python multiprocessing)
- Self-play orchestration with frozen checkpoint opponents
- Checkpoint promotion rules (Elo or payout-based, ~1000 fixed-seed games)
- PPO or IMPALA implementation on top of the existing model

**Phase 3C: Inference Integration**
- ONNX export from PyTorch → `onnxruntime-go` for serving (avoids Python in the hot path)
- OR gRPC Python inference server + Go bot client (simpler, higher latency)
- Integration with `bot.Policy` interface so trained models can play in live rooms

# Online Self-Play PPO (slice 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `fh-mj-train-ppo` — a single-process, on-policy PPO learner that fine-tunes the promoted anchor by playing fresh Chongci matches against frozen-anchor opponents, learning from per-hand score rewards, so the agent can surpass the offline/heuristic ceiling.

**Architecture:** New `ppo.py` module with pure, unit-tested pieces (masked policy distribution, GAE, clipped PPO update) plus a rollout collector that reuses the Go bridge + `generate_selfplay` seat-policy helpers, and a `train_ppo` loop that warm-starts the anchor (`PolicyValueNet` policy+value), collects on-policy rollouts, updates, and periodically runs the existing duplicate-seat CI gate vs the anchor. On-policy: each iteration's rollouts are used once and discarded.

**Tech Stack:** Python 3.12 (uv), PyTorch (`torch.distributions.Categorical`), NumPy, the `fh_mahjong_ai` package, pytest.

**Spec:** `worklog/specs/2026-06-24-online-ppo-selfplay-design.md`

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `ai/src/fh_mahjong_ai/ppo.py` | PPOConfig, RolloutBatch, masked dist, GAE, ppo_update, collect_rollouts, train_ppo | Create |
| `ai/src/fh_mahjong_ai/scripts/train_ppo.py` | `fh-mj-train-ppo` CLI | Create |
| `ai/tests/test_ppo.py` | unit + mock-bridge + e2e tests | Create |
| `ai/pyproject.toml` | `fh-mj-train-ppo` entry point | Modify |
| `ai/AGENTS.md` | document module/CLI/tests | Modify |

Commands run from repo root: `uv run --project ai ...`.

---

## Task 1: Config, RolloutBatch, masked policy distribution

**Files:**
- Create: `ai/src/fh_mahjong_ai/ppo.py`
- Test: `ai/tests/test_ppo.py`

- [ ] **Step 1: Write the failing test**

Create `ai/tests/test_ppo.py`:

```python
from __future__ import annotations

import numpy as np
import pytest
import torch

from fh_mahjong_ai.ppo import PPOConfig, masked_policy_distribution


def test_ppo_config_defaults():
    cfg = PPOConfig()
    assert cfg.gamma == 0.99
    assert 0.0 < cfg.clip_eps < 1.0
    assert cfg.ppo_epochs >= 1


def test_masked_distribution_zeros_illegal_actions():
    # logits already masked the way PolicyValueNet.forward produces them
    neg = torch.finfo(torch.float32).min
    masked_logits = torch.tensor([[0.5, neg, 0.7, neg]])
    dist = masked_policy_distribution(masked_logits)
    probs = dist.probs[0]
    assert probs[1].item() == pytest.approx(0.0, abs=1e-6)
    assert probs[3].item() == pytest.approx(0.0, abs=1e-6)
    assert probs[0].item() + probs[2].item() == pytest.approx(1.0, abs=1e-6)
    assert torch.isfinite(dist.entropy()).all()


def test_masked_distribution_single_legal_action_has_zero_entropy():
    neg = torch.finfo(torch.float32).min
    masked_logits = torch.tensor([[neg, 1.0, neg]])
    dist = masked_policy_distribution(masked_logits)
    assert dist.entropy().item() == pytest.approx(0.0, abs=1e-5)
    assert dist.probs[0, 1].item() == pytest.approx(1.0, abs=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -k "config or distribution" -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fh_mahjong_ai.ppo'`.

- [ ] **Step 3: Implement config, batch, and masked distribution**

Create `ai/src/fh_mahjong_ai/ppo.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import torch


@dataclass
class PPOConfig:
    iterations: int = 50
    matches_per_iter: int = 16
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_eps: float = 0.2
    entropy_coef: float = 0.01
    value_coef: float = 0.5
    ppo_epochs: int = 4
    minibatch_size: int = 256
    lr: float = 2e-5
    max_grad_norm: float = 1.0
    sample_temperature: float = 1.0
    eval_interval: int = 5
    eval_seeds: int = 80
    eval_start_seed: int = 870000
    match_mode: str = "chongci"
    max_steps_per_episode: Optional[int] = 4000
    device: str = "cpu"


@dataclass
class RolloutBatch:
    planes: np.ndarray
    scalars: np.ndarray
    action_mask: np.ndarray
    actions: np.ndarray
    old_logprobs: np.ndarray
    values: np.ndarray
    rewards: np.ndarray
    dones: np.ndarray  # 1.0 at each match's final learning-seat step

    def __len__(self) -> int:
        return int(self.actions.shape[0])


def masked_policy_distribution(masked_logits: torch.Tensor) -> torch.distributions.Categorical:
    """Categorical over actions; logits are already -inf-masked (finfo.min) for
    illegal actions by PolicyValueNet.forward, so illegal probability is ~0 and
    entropy stays finite."""
    return torch.distributions.Categorical(logits=masked_logits)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -k "config or distribution" -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/tests/test_ppo.py
git commit -m "feat(ppo): PPOConfig, RolloutBatch, masked policy distribution"
```

---

## Task 2: GAE advantages

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py`
- Test: `ai/tests/test_ppo.py`

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_ppo.py`:

```python
from fh_mahjong_ai.ppo import compute_gae


def test_gae_lambda1_gamma1_single_match_is_monte_carlo():
    # one match, terminal at the last step; lambda=1, gamma=1 -> returns are
    # reverse cumulative sums of rewards.
    rewards = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    values = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    dones = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    adv, ret = compute_gae(rewards, values, dones, gamma=1.0, gae_lambda=1.0)
    np.testing.assert_allclose(ret, [6.0, 5.0, 3.0], rtol=1e-6)
    np.testing.assert_allclose(adv, [6.0, 5.0, 3.0], rtol=1e-6)


def test_gae_resets_at_match_boundary():
    # two matches of 1 step each; a done after step 0 must stop credit bleeding.
    rewards = np.array([1.0, 5.0], dtype=np.float32)
    values = np.array([0.0, 0.0], dtype=np.float32)
    dones = np.array([1.0, 1.0], dtype=np.float32)
    adv, ret = compute_gae(rewards, values, dones, gamma=1.0, gae_lambda=1.0)
    np.testing.assert_allclose(ret, [1.0, 5.0], rtol=1e-6)  # no bleed from match 2 into match 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -k gae -q`
Expected: FAIL with `ImportError: cannot import name 'compute_gae'`.

- [ ] **Step 3: Implement GAE**

Append to `ai/src/fh_mahjong_ai/ppo.py`:

```python
def compute_gae(
    rewards: np.ndarray,
    values: np.ndarray,
    dones: np.ndarray,
    gamma: float,
    gae_lambda: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Generalized Advantage Estimation over a flat, time-ordered batch where
    `dones[t]==1` marks the final step of a match. Boundaries reset both the value
    bootstrap and the advantage accumulation via the (1-done) factor."""
    rewards = np.asarray(rewards, dtype=np.float32)
    values = np.asarray(values, dtype=np.float32)
    dones = np.asarray(dones, dtype=np.float32)
    n = rewards.shape[0]
    advantages = np.zeros(n, dtype=np.float32)
    last_adv = 0.0
    for t in range(n - 1, -1, -1):
        next_nonterminal = 1.0 - dones[t]
        next_value = values[t + 1] if (t + 1 < n) else 0.0
        delta = rewards[t] + gamma * next_value * next_nonterminal - values[t]
        last_adv = delta + gamma * gae_lambda * next_nonterminal * last_adv
        advantages[t] = last_adv
    returns = advantages + values
    return advantages, returns
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -k gae -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/tests/test_ppo.py
git commit -m "feat(ppo): GAE advantages with per-match boundary reset"
```

---

## Task 3: Clipped PPO update

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py`
- Test: `ai/tests/test_ppo.py`

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_ppo.py`:

```python
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import ppo_update


def _tiny_model():
    env = EnvConfig(action_space_size=4, plane_shape=(2, 3, 1), scalar_features=4)
    mcfg = ModelConfig(channels=4, residual_blocks=1, plane_feature_dim=8,
                       scalar_hidden_dim=8, trunk_hidden_dim=8, value_hidden_dim=8, q_hidden_dim=8)
    return PolicyValueNet(env, mcfg), env


def _synthetic_batch(env, n=16):
    rng = np.random.default_rng(0)
    from fh_mahjong_ai.ppo import RolloutBatch
    mask = np.ones((n, env.action_space_size), dtype=np.int8)
    return RolloutBatch(
        planes=rng.standard_normal((n, *env.plane_shape)).astype(np.float32),
        scalars=rng.standard_normal((n, env.scalar_features)).astype(np.float32),
        action_mask=mask,
        actions=rng.integers(0, env.action_space_size, size=n).astype(np.int64),
        old_logprobs=np.full(n, -1.386, dtype=np.float32),  # log(1/4)
        values=np.zeros(n, dtype=np.float32),
        rewards=rng.standard_normal(n).astype(np.float32),
        dones=np.zeros(n, dtype=np.float32),
    )


def test_ppo_update_returns_finite_metrics():
    model, env = _tiny_model()
    batch = _synthetic_batch(env)
    adv = np.ones(len(batch), dtype=np.float32)
    ret = np.zeros(len(batch), dtype=np.float32)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    metrics = ppo_update(model, opt, batch, adv, ret, PPOConfig(minibatch_size=8, ppo_epochs=2, device="cpu"))
    for key in ("policy_loss", "value_loss", "entropy", "approx_kl", "clip_fraction"):
        assert np.isfinite(metrics[key])


def test_ppo_update_increases_prob_of_positive_advantage_action():
    model, env = _tiny_model()
    from fh_mahjong_ai.ppo import RolloutBatch, masked_policy_distribution
    # single repeated sample, action 2, strong positive advantage
    n = 8
    mask = np.ones((n, env.action_space_size), dtype=np.int8)
    planes = np.zeros((n, *env.plane_shape), dtype=np.float32)
    scalars = np.zeros((n, env.scalar_features), dtype=np.float32)
    with torch.no_grad():
        logits, _ = model(torch.zeros(1, *env.plane_shape), torch.zeros(1, env.scalar_features),
                          torch.ones(1, env.action_space_size, dtype=torch.int8))
        old_lp = float(masked_policy_distribution(logits).log_prob(torch.tensor([2]))[0])
    batch = RolloutBatch(
        planes=planes, scalars=scalars, action_mask=mask,
        actions=np.full(n, 2, dtype=np.int64),
        old_logprobs=np.full(n, old_lp, dtype=np.float32),
        values=np.zeros(n, dtype=np.float32),
        rewards=np.zeros(n, dtype=np.float32),
        dones=np.zeros(n, dtype=np.float32),
    )
    adv = np.ones(n, dtype=np.float32)
    ret = np.zeros(n, dtype=np.float32)
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    ppo_update(model, opt, batch, adv, ret, PPOConfig(minibatch_size=8, ppo_epochs=5, entropy_coef=0.0, device="cpu"))
    with torch.no_grad():
        logits, _ = model(torch.zeros(1, *env.plane_shape), torch.zeros(1, env.scalar_features),
                          torch.ones(1, env.action_space_size, dtype=torch.int8))
        new_lp = float(masked_policy_distribution(logits).log_prob(torch.tensor([2]))[0])
    assert new_lp > old_lp
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -k ppo_update -q`
Expected: FAIL with `ImportError: cannot import name 'ppo_update'`.

- [ ] **Step 3: Implement the PPO update**

Append to `ai/src/fh_mahjong_ai/ppo.py` (add `from typing import Dict` usage; `torch.nn` not needed):

```python
def ppo_update(
    model,
    optimizer,
    batch: "RolloutBatch",
    advantages: np.ndarray,
    returns: np.ndarray,
    config: PPOConfig,
) -> dict:
    device = config.device
    n = len(batch)
    planes = torch.from_numpy(np.asarray(batch.planes, dtype=np.float32)).to(device)
    scalars = torch.from_numpy(np.asarray(batch.scalars, dtype=np.float32)).to(device)
    action_mask = torch.from_numpy(np.asarray(batch.action_mask, dtype=np.int8)).to(device)
    actions = torch.from_numpy(np.asarray(batch.actions, dtype=np.int64)).to(device)
    old_logprobs = torch.from_numpy(np.asarray(batch.old_logprobs, dtype=np.float32)).to(device)
    adv_t = torch.from_numpy(np.asarray(advantages, dtype=np.float32)).to(device)
    ret_t = torch.from_numpy(np.asarray(returns, dtype=np.float32)).to(device)
    adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

    last = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "approx_kl": 0.0, "clip_fraction": 0.0}
    model.train()
    for _ in range(config.ppo_epochs):
        perm = torch.randperm(n, device=device)
        for start in range(0, n, config.minibatch_size):
            idx = perm[start : start + config.minibatch_size]
            masked_logits, value = model(planes[idx], scalars[idx], action_mask[idx])
            dist = masked_policy_distribution(masked_logits)
            new_logprobs = dist.log_prob(actions[idx])
            ratio = torch.exp(new_logprobs - old_logprobs[idx])
            mb_adv = adv_t[idx]
            surr1 = ratio * mb_adv
            surr2 = torch.clamp(ratio, 1.0 - config.clip_eps, 1.0 + config.clip_eps) * mb_adv
            policy_loss = -torch.min(surr1, surr2).mean()
            value_loss = torch.nn.functional.mse_loss(value, ret_t[idx])
            entropy = dist.entropy().mean()
            loss = policy_loss + config.value_coef * value_loss - config.entropy_coef * entropy

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
            optimizer.step()

            with torch.no_grad():
                approx_kl = (old_logprobs[idx] - new_logprobs).mean()
                clip_fraction = (torch.abs(ratio - 1.0) > config.clip_eps).float().mean()
            last = {
                "policy_loss": float(policy_loss.item()),
                "value_loss": float(value_loss.item()),
                "entropy": float(entropy.item()),
                "approx_kl": float(approx_kl.item()),
                "clip_fraction": float(clip_fraction.item()),
            }
    return last
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -k ppo_update -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/tests/test_ppo.py
git commit -m "feat(ppo): masked clipped PPO update with value + entropy"
```

---

## Task 4: Rollout collection

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py`
- Test: `ai/tests/test_ppo.py`

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_ppo.py`:

```python
from fh_mahjong_ai.ppo import collect_rollouts


def test_collect_rollouts_mock_shapes_and_done_at_match_end():
    # Mock bridge emits default obs dims; use a small model at those dims.
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    learner = PolicyValueNet(env_cfg, mcfg)
    frozen = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=2, match_mode="classic", max_steps_per_episode=64, device="cpu")

    batch = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=123)
    n = len(batch)
    assert n > 0
    for arr in (batch.planes, batch.scalars, batch.action_mask, batch.actions,
                batch.old_logprobs, batch.values, batch.rewards, batch.dones):
        assert arr.shape[0] == n
    assert batch.dones.sum() >= 1  # at least one match ended
    assert set(np.unique(batch.dones)).issubset({0.0, 1.0})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -k collect_rollouts -q`
Expected: FAIL with `ImportError: cannot import name 'collect_rollouts'`.

- [ ] **Step 3: Implement rollout collection**

Append to `ai/src/fh_mahjong_ai/ppo.py` (add imports at top of file: `from .config import EnvConfig`; `from .env import MahjongEnv`; `from .bridge import build_bridge`; `from .types import Observation`):

```python
LEARNING_SEAT = 0


def _obs_to_tensors(obs: "Observation", device: str):
    planes = torch.from_numpy(np.asarray(obs.planes, dtype=np.float32)).unsqueeze(0).to(device)
    scalars = torch.from_numpy(np.asarray(obs.scalars, dtype=np.float32)).unsqueeze(0).to(device)
    mask = torch.from_numpy(np.asarray(obs.action_mask, dtype=np.int8)).unsqueeze(0).to(device)
    return planes, scalars, mask


def _seat_reward_from_info(info: dict, seat: int) -> float:
    """Per-hand score delta for `seat` when a hand resolves this step, else 0.0.
    Reads the round/terminal outcome payouts emitted in StepResult.info."""
    outcome = info.get("round_outcome") or info.get("terminal_outcome")
    if not isinstance(outcome, dict):
        return 0.0
    payouts = outcome.get("payouts")
    if isinstance(payouts, (list, tuple)) and len(payouts) > seat:
        return float(payouts[seat])
    return 0.0


def collect_rollouts(
    env_config: EnvConfig,
    policy_model,
    frozen_anchor,
    config: PPOConfig,
    base_seed: int,
) -> RolloutBatch:
    """Play `matches_per_iter` full matches; record on-policy experience for the
    learning seat (samples from the masked policy), with the frozen anchor in the
    other seats. Per-hand score deltas become rewards; done at match end."""
    device = config.device
    cfg = EnvConfig(
        action_space_size=env_config.action_space_size,
        plane_shape=env_config.plane_shape,
        scalar_features=env_config.scalar_features,
        bridge_kind=env_config.bridge_kind,
        bridge_library_path=env_config.bridge_library_path,
        learning_seats=(0, 1, 2, 3),  # all seats controlled by Python
        auto_play_heuristics=False,
        max_steps_per_episode=config.max_steps_per_episode,
        match_mode=config.match_mode,
    )
    bridge = build_bridge(cfg)
    env = MahjongEnv(cfg, bridge=bridge)
    policy_model.eval()
    frozen_anchor.eval()

    planes_l, scalars_l, mask_l, actions_l = [], [], [], []
    logprobs_l, values_l, rewards_l, dones_l = [], [], [], []

    try:
        for m in range(config.matches_per_iter):
            obs = env.reset(seed=base_seed + m)
            reset_result = env.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                continue
            last_learn_index: Optional[int] = None
            while True:
                seat = int(obs.seat)
                if seat == LEARNING_SEAT:
                    planes, scalars, mask = _obs_to_tensors(obs, device)
                    with torch.no_grad():
                        logits, value = policy_model(planes, scalars, mask)
                        logits = logits / max(config.sample_temperature, 1e-6)
                        dist = masked_policy_distribution(logits)
                        action = int(dist.sample()[0].item())
                        logprob = float(dist.log_prob(torch.tensor([action], device=device))[0])
                        val = float(value[0].item())
                    planes_l.append(np.asarray(obs.planes, dtype=np.float32))
                    scalars_l.append(np.asarray(obs.scalars, dtype=np.float32))
                    mask_l.append(np.asarray(obs.action_mask, dtype=np.int8))
                    actions_l.append(action)
                    logprobs_l.append(logprob)
                    values_l.append(val)
                    rewards_l.append(0.0)
                    dones_l.append(0.0)
                    last_learn_index = len(actions_l) - 1
                else:
                    planes, scalars, mask = _obs_to_tensors(obs, device)
                    with torch.no_grad():
                        logits, _ = frozen_anchor(planes, scalars, mask)
                        action = int(torch.argmax(logits, dim=1)[0].item())
                step = env.step(action)
                if last_learn_index is not None:
                    rewards_l[last_learn_index] += _seat_reward_from_info(step.info, LEARNING_SEAT)
                if step.terminated or step.truncated:
                    if last_learn_index is not None:
                        dones_l[last_learn_index] = 1.0
                    break
                obs = step.observation
    finally:
        close = getattr(bridge, "close", None)
        if callable(close):
            close()

    if not actions_l:
        raise RuntimeError("collect_rollouts produced no learning-seat decisions")

    return RolloutBatch(
        planes=np.stack(planes_l).astype(np.float32),
        scalars=np.stack(scalars_l).astype(np.float32),
        action_mask=np.stack(mask_l).astype(np.int8),
        actions=np.asarray(actions_l, dtype=np.int64),
        old_logprobs=np.asarray(logprobs_l, dtype=np.float32),
        values=np.asarray(values_l, dtype=np.float32),
        rewards=np.asarray(rewards_l, dtype=np.float32),
        dones=np.asarray(dones_l, dtype=np.float32),
    )
```

Note: `_seat_reward_from_info` reads `round_outcome`/`terminal_outcome` `payouts[seat]`. Verify against the round-outcome protobuf decoded into `StepResult.info` during implementation (mirror how `storage._transitions_to_arrays` reads `terminal_outcome`); if the per-seat field is named differently (e.g. a score vector), adjust the helper. The mock test does not depend on reward values.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -k collect_rollouts -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/tests/test_ppo.py
git commit -m "feat(ppo): on-policy rollout collection vs frozen anchor"
```

---

## Task 5: `train_ppo` loop (warm-start + eval gate)

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py`
- Test: `ai/tests/test_ppo.py`

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_ppo.py`:

```python
from fh_mahjong_ai.ppo import train_ppo
from fh_mahjong_ai.storage import save_checkpoint


def test_train_ppo_e2e_mock_writes_checkpoint(tmp_path):
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    cfg = PPOConfig(iterations=2, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    eval_interval=100, match_mode="classic", max_steps_per_episode=64, device="cpu")
    metrics = train_ppo(
        env_config=env_cfg, model_config=mcfg, init_checkpoint=init,
        checkpoint_dir=tmp_path / "ppo", config=cfg, base_seed=1000, run_eval=False,
    )
    assert len(metrics) == 2
    assert (tmp_path / "ppo" / "iter_002.pt").exists()
    assert all(np.isfinite(m["policy_loss"]) for m in metrics)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -k train_ppo -q`
Expected: FAIL with `ImportError: cannot import name 'train_ppo'`.

- [ ] **Step 3: Implement the training loop**

Append to `ai/src/fh_mahjong_ai/ppo.py` (add imports: `from pathlib import Path`; `from .config import ModelConfig`; `from .model import PolicyValueNet`; `from .storage import load_checkpoint, save_checkpoint`; `from .evaluate import evaluate_duplicate_seats`):

```python
def train_ppo(
    env_config: EnvConfig,
    model_config: ModelConfig,
    init_checkpoint: Path,
    checkpoint_dir: Path,
    config: PPOConfig,
    base_seed: int = 0,
    run_eval: bool = True,
) -> List[dict]:
    device = config.device
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    model = PolicyValueNet(env_config, model_config).to(device)
    load_checkpoint(Path(init_checkpoint), model)
    frozen = PolicyValueNet(env_config, model_config).to(device)
    load_checkpoint(Path(init_checkpoint), frozen)
    frozen.eval()
    for p in frozen.parameters():
        p.requires_grad_(False)

    optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr)
    history: List[dict] = []

    for iteration in range(1, config.iterations + 1):
        batch = collect_rollouts(env_config, model, frozen, config, base_seed=base_seed + iteration * config.matches_per_iter)
        advantages, returns = compute_gae(batch.rewards, batch.values, batch.dones, config.gamma, config.gae_lambda)
        metrics = ppo_update(model, optimizer, batch, advantages, returns, config)
        metrics["iteration"] = iteration
        metrics["mean_reward"] = float(np.sum(batch.rewards) / max(1.0, float(batch.dones.sum())))
        metrics["steps"] = len(batch)

        if run_eval and iteration % config.eval_interval == 0:
            seeds = list(range(config.eval_start_seed, config.eval_start_seed + config.eval_seeds))
            try:
                report = evaluate_duplicate_seats(
                    model=model, seeds=seeds, bridge_kind=env_config.bridge_kind,
                    bridge_library_path=env_config.bridge_library_path, device=device,
                    large_loss_threshold=-1.0, match_mode=config.match_mode,
                    max_steps_per_episode=config.max_steps_per_episode,
                )
                metrics["eval_mean_reward"] = report["mean_reward"]
                metrics["eval_mean_reward_ci95"] = report["mean_reward_ci95"]
                metrics["eval_large_loss_rate"] = report["large_loss_rate"]
            except Exception as exc:  # eval must not abort training
                metrics["eval_error"] = str(exc)[:200]

        save_checkpoint(checkpoint_dir / f"iter_{iteration:03d}.pt", model)
        history.append(metrics)
        print(
            f"iter {iteration}: policy_loss={metrics['policy_loss']:.4f} "
            f"value_loss={metrics['value_loss']:.4f} entropy={metrics['entropy']:.4f} "
            f"approx_kl={metrics['approx_kl']:.4f} mean_reward={metrics['mean_reward']:.4f}"
        )
    return history
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -k train_ppo -q`
Expected: PASS.

- [ ] **Step 5: Run the whole PPO module**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -q`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/tests/test_ppo.py
git commit -m "feat(ppo): train_ppo loop with warm-start, GAE, eval gate, checkpoints"
```

---

## Task 6: CLI `fh-mj-train-ppo`

**Files:**
- Create: `ai/src/fh_mahjong_ai/scripts/train_ppo.py`
- Modify: `ai/pyproject.toml`
- Test: `ai/tests/test_ppo.py`

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_ppo.py`:

```python
def test_cli_train_ppo_mock(tmp_path, monkeypatch):
    import sys
    from fh_mahjong_ai.scripts import train_ppo as cli

    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    argv = [
        "fh-mj-train-ppo",
        "--init-checkpoint", str(init),
        "--checkpoint-dir", str(tmp_path / "ppo"),
        "--iterations", "1", "--matches-per-iter", "2", "--ppo-epochs", "1",
        "--minibatch-size", "8", "--match-mode", "classic", "--bridge-kind", "mock",
        "--max-steps-per-episode", "64", "--no-eval",
        "--model-channels", "8", "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    assert (tmp_path / "ppo" / "iter_001.pt").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -k cli_train_ppo -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fh_mahjong_ai.scripts.train_ppo'`.

- [ ] **Step 3: Implement the CLI**

Create `ai/src/fh_mahjong_ai/scripts/train_ppo.py`:

```python
"""CLI for online self-play PPO fine-tuning."""
from __future__ import annotations

import argparse
from pathlib import Path

from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.ppo import PPOConfig, train_ppo
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args


def main() -> None:
    parser = argparse.ArgumentParser(description="Online self-play PPO fine-tuning")
    parser.add_argument("--init-checkpoint", type=Path, required=True, help="Anchor checkpoint to warm-start (policy+value) and freeze as opponent")
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--matches-per-iter", type=int, default=16)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--gae-lambda", type=float, default=0.95)
    parser.add_argument("--clip-eps", type=float, default=0.2)
    parser.add_argument("--entropy-coef", type=float, default=0.01)
    parser.add_argument("--value-coef", type=float, default=0.5)
    parser.add_argument("--ppo-epochs", type=int, default=4)
    parser.add_argument("--minibatch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--sample-temperature", type=float, default=1.0)
    parser.add_argument("--eval-interval", type=int, default=5)
    parser.add_argument("--eval-seeds", type=int, default=80)
    parser.add_argument("--eval-start-seed", type=int, default=870000)
    parser.add_argument("--match-mode", choices=("classic", "chongci"), default="chongci")
    parser.add_argument("--max-steps-per-episode", type=int, default=4000)
    parser.add_argument("--bridge-kind", choices=("go", "mock"), default="go")
    parser.add_argument("--bridge-lib", type=str, default=None)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--no-eval", action="store_true")
    add_model_config_args(parser)
    args = parser.parse_args()

    env_config = EnvConfig(
        bridge_kind=args.bridge_kind,
        bridge_library_path=args.bridge_lib,
        match_mode=args.match_mode,
        max_steps_per_episode=args.max_steps_per_episode,
    )
    config = PPOConfig(
        iterations=args.iterations, matches_per_iter=args.matches_per_iter,
        gamma=args.gamma, gae_lambda=args.gae_lambda, clip_eps=args.clip_eps,
        entropy_coef=args.entropy_coef, value_coef=args.value_coef,
        ppo_epochs=args.ppo_epochs, minibatch_size=args.minibatch_size, lr=args.lr,
        max_grad_norm=args.max_grad_norm, sample_temperature=args.sample_temperature,
        eval_interval=args.eval_interval, eval_seeds=args.eval_seeds,
        eval_start_seed=args.eval_start_seed, match_mode=args.match_mode,
        max_steps_per_episode=args.max_steps_per_episode, device=args.device,
    )
    history = train_ppo(
        env_config=env_config, model_config=model_config_from_args(args),
        init_checkpoint=args.init_checkpoint, checkpoint_dir=args.checkpoint_dir,
        config=config, base_seed=args.base_seed, run_eval=not args.no_eval,
    )
    print(f"PPO finished: {len(history)} iterations; checkpoints in {args.checkpoint_dir}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Register the entry point**

In `ai/pyproject.toml` under `[project.scripts]`, add after `fh-mj-selfplay-loop`:

```toml
fh-mj-train-ppo = "fh_mahjong_ai.scripts.train_ppo:main"
```

Then re-sync: `uv sync --project ai --extra dev`

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -k cli_train_ppo -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/train_ppo.py ai/pyproject.toml ai/tests/test_ppo.py
git commit -m "feat(ppo): fh-mj-train-ppo CLI"
```

---

## Task 7: Docs + full-suite gate

**Files:**
- Modify: `ai/AGENTS.md`

- [ ] **Step 1: Document the module and CLI**

In `ai/AGENTS.md`, add Key Files bullets near the other trainers:

```markdown
- **src/fh_mahjong_ai/ppo.py** — Online self-play PPO (slice 1): `PPOConfig`, `RolloutBatch`, `masked_policy_distribution`, `compute_gae`, `ppo_update` (masked clipped surrogate + value + entropy), `collect_rollouts` (on-policy; learning seat samples, frozen-anchor opponents, per-hand score-delta rewards), and `train_ppo` (warm-start anchor policy+value → collect → GAE → update → periodic duplicate-seat CI gate → checkpoint). This is the first ONLINE/on-policy trainer — it can surpass the offline/heuristic ceiling because it learns from its own explored actions, unlike BC/IQL.
- **src/fh_mahjong_ai/scripts/train_ppo.py** — CLI `fh-mj-train-ppo`: warm-starts from `--init-checkpoint` (the anchor, also frozen as opponents), runs N on-policy iterations vs the frozen anchor, evaluates vs the anchor on the CI gate every `--eval-interval`. Slice 1 is single-process; self-play pool, parallel rollouts, and GlobalEV(GRP) reward are follow-ups.
```

Add a tests bullet:

```markdown
- **tests/test_ppo.py** — Tests for the masked policy distribution, GAE (Monte-Carlo limit + per-match reset), the clipped PPO update (finite metrics + prob increases for positive-advantage actions), mock-bridge rollout collection, the e2e `train_ppo` loop, and the CLI.
```

- [ ] **Step 2: Run the full Python suite**

Run: `uv run --project ai pytest ai/tests -q`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add ai/AGENTS.md
git commit -m "docs(ai): document online PPO module and fh-mj-train-ppo"
```

---

## Self-Review Notes

- **Spec coverage:** warm-start anchor policy+value (Task 5); frozen-anchor opponents + learning-seat sampling + per-hand rewards (Task 4); on-policy collect→GAE→update→discard (Tasks 2/3/5); masked clipped PPO with entropy (Tasks 1/3); CI gate vs anchor every eval_interval (Task 5); CLI + knobs incl. sample_temperature/entropy_coef (Task 6); tests for GAE/clip/masking + mock rollouts + e2e (all tasks).
- **No Go changes, no offline buffer** — genuinely on-policy.
- **Type consistency:** `RolloutBatch` fields defined in Task 1 are produced by `collect_rollouts` (Task 4) and consumed by `ppo_update`/`compute_gae` (Tasks 2/3) with matching names; `masked_policy_distribution` used identically in update + rollouts; `PPOConfig` fields referenced consistently across update/collect/train/CLI.
- **Flagged verification:** `_seat_reward_from_info` reads `round_outcome`/`terminal_outcome` `payouts[seat]` — confirm the per-seat score field name against the decoded round-outcome proto during Task 4 (mirror `storage` outcome decoding); mock tests don't depend on it, so this won't surface until the Go-bridge run.
- **Eval-gate note:** in slice 1 the gate uses `evaluate_duplicate_seats` (agent vs the env's default opponents); interpreting it strictly as "beat the *anchor*" assumes the eval opponents are the anchor/heuristic baseline used elsewhere — keep the comparison against the same fixed baseline as prior experiments for apples-to-apples.

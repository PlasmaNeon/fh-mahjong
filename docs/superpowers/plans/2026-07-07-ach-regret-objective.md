# ACH Regret Objective Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a clipped-NeuRD / ACH regret objective as a drop-in alternative to PPO in the self-play + feature-dropout pipeline, selectable by config.

**Architecture:** A new `ach.py` module provides `ach_update` with the exact same signature as `ppo_update`; it reuses `masked_policy_distribution` and the PPO minibatch/epoch/grad-clip machinery, changing only the per-sample policy loss (regret-matching on logits with a hedge threshold `β`). `train_selfplay_oracle` selects the update function by `config.objective`; a CLI flag exposes it. `RolloutBatch` is unchanged.

**Tech Stack:** Python 3, PyTorch, NumPy, pytest (`uv run --project ai pytest`).

## Global Constraints

- `ach_update` signature is IDENTICAL to `ppo_update(model, optimizer, batch, advantages, returns, config) -> dict` — a drop-in.
- `RolloutBatch` is NOT modified: the hedge reads the current logit from the forward pass; the importance ratio uses the already-stored `old_logprobs`.
- PPO default is preserved: `PPOConfig.objective` defaults to `"ppo"`, and the `objective="ppo"` path is byte-unchanged.
- Reuse `masked_policy_distribution`, `compute_gae`, and the existing minibatch / `ppo_epochs` / grad-norm-clip / optimizer-step loop.
- The deployable artifact stays a true 39ch net extracted from the 51ch net and evaluated non-oracle — unchanged by this work.
- No Go changes. Python only, under `ai/src/fh_mahjong_ai/`.
- Run `uv run --project ai pytest` after Python changes.
- The A/B training run is operational (box scripts, Phase-B pattern) and is NOT part of this plan — the plan delivers only the reviewable repo objective + wiring + tests.

## File Structure

- `ai/src/fh_mahjong_ai/ppo.py` — MODIFY: two new `PPOConfig` fields (`objective`, `ach_beta`). Nothing else changes here.
- `ai/src/fh_mahjong_ai/ach.py` — CREATE: `ach_policy_loss` (pure, gradient-testable helper) + `ach_update` (drop-in update).
- `ai/src/fh_mahjong_ai/oracle.py` — MODIFY: `train_selfplay_oracle` selects `update_fn` by `config.objective` and records `objective`/`ach_beta` in history.
- `ai/src/fh_mahjong_ai/scripts/train_selfplay_oracle.py` — MODIFY: add `--objective` / `--ach-beta`, thread into `PPOConfig`.
- `ai/tests/test_ach.py` — CREATE: objective unit tests (Tasks 1).
- `ai/tests/test_oracle_phase2.py` — MODIFY: trainer-wiring tests (Task 2).
- `ai/tests/test_ach_cli.py` — CREATE: CLI end-to-end mock test (Task 3).

---

### Task 1: ACH objective (`ach.py`) + `PPOConfig` fields

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (add two fields to `PPOConfig`, after `device: str = "cpu"` at line 119)
- Create: `ai/src/fh_mahjong_ai/ach.py`
- Test: `ai/tests/test_ach.py`

**Interfaces:**
- Consumes: `PPOConfig` (ppo.py:93), `RolloutBatch` (ppo.py:122, fields `planes, scalars, action_mask, actions, old_logprobs, values, rewards, dones`), `masked_policy_distribution(masked_logits)` (ppo.py:170).
- Produces:
  - `ach_policy_loss(masked_logits: torch.Tensor, actions: torch.Tensor, weights: torch.Tensor, beta: float) -> tuple[torch.Tensor, torch.Tensor]` returning `(loss, saturated_mask)`.
  - `ach_update(model, optimizer, batch: RolloutBatch, advantages: np.ndarray, returns: np.ndarray, config: PPOConfig) -> dict` with metrics keys `policy_loss, value_loss, entropy, approx_kl, clip_fraction, saturated_fraction, mean_abs_logit`.
  - `PPOConfig.objective: str = "ppo"`, `PPOConfig.ach_beta: float = 2.0`.

- [ ] **Step 1: Add the two `PPOConfig` fields**

In `ai/src/fh_mahjong_ai/ppo.py`, inside the `PPOConfig` dataclass, immediately after the line `device: str = "cpu"` (line 119), add:

```python
    objective: str = "ppo"       # "ppo" | "ach" (selects the policy update)
    ach_beta: float = 2.0        # hedge/logit trust-region threshold when objective="ach"
```

- [ ] **Step 2: Write the failing tests for the objective**

Create `ai/tests/test_ach.py`:

```python
from __future__ import annotations

import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig, RolloutBatch, masked_policy_distribution
from fh_mahjong_ai.ach import ach_policy_loss, ach_update


def _tiny_model():
    env = EnvConfig(action_space_size=4, plane_shape=(2, 3, 1), scalar_features=4)
    mcfg = ModelConfig(channels=4, residual_blocks=1, plane_feature_dim=8,
                       scalar_hidden_dim=8, trunk_hidden_dim=8, value_hidden_dim=8, q_hidden_dim=8)
    return PolicyValueNet(env, mcfg), env


def _synthetic_batch(env, n=16):
    rng = np.random.default_rng(0)
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


def test_hedge_threshold_blocks_saturated_logit_gradient():
    # Sample 0: taken-action logit 3.0 > beta 2.0 with positive weight -> saturated -> grad ~0.
    # Sample 1: taken-action logit 1.0 < beta with positive weight -> not saturated ->
    #           loss = -(y_eff*w).mean() so grad = -w/n = -1/2.
    logits = torch.tensor([[3.0, 0.0, 0.0, 0.0],
                           [1.0, 0.0, 0.0, 0.0]], requires_grad=True)
    actions = torch.tensor([0, 0])
    weights = torch.tensor([1.0, 1.0])
    loss, saturated = ach_policy_loss(logits, actions, weights, beta=2.0)
    loss.backward()
    assert bool(saturated[0]) is True and bool(saturated[1]) is False
    assert abs(logits.grad[0, 0].item()) < 1e-7
    assert logits.grad[1, 0].item() == pytest.approx(-0.5)


def test_neurd_reduction_grad_equals_advantage_when_beta_infinite():
    # beta = +inf -> nothing saturates -> taken-logit grad = -adv/n (regret/replicator update).
    logits = torch.tensor([[0.5, 0.0, 0.0, 0.0],
                           [0.2, 0.0, 0.0, 0.0]], requires_grad=True)
    actions = torch.tensor([0, 0])
    adv = torch.tensor([0.7, -0.4])
    loss, saturated = ach_policy_loss(logits, actions, adv, beta=float("inf"))
    loss.backward()
    assert not bool(saturated.any())
    assert logits.grad[0, 0].item() == pytest.approx(-0.7 / 2)
    assert logits.grad[1, 0].item() == pytest.approx(0.4 / 2)


def test_ach_update_increases_prob_of_positive_advantage_action():
    model, env = _tiny_model()
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
    ach_update(model, opt, batch, adv, ret,
               PPOConfig(minibatch_size=8, ppo_epochs=5, entropy_coef=0.0,
                         normalize_advantages=False, ach_beta=2.0, device="cpu"))
    with torch.no_grad():
        logits, _ = model(torch.zeros(1, *env.plane_shape), torch.zeros(1, env.scalar_features),
                          torch.ones(1, env.action_space_size, dtype=torch.int8))
        new_lp = float(masked_policy_distribution(logits).log_prob(torch.tensor([2]))[0])
    assert new_lp > old_lp


def test_ach_update_metrics_finite_and_does_not_mutate_batch():
    model, env = _tiny_model()
    batch = _synthetic_batch(env)
    planes_before = batch.planes.copy()
    actions_before = batch.actions.copy()
    adv = np.ones(len(batch), dtype=np.float32)
    ret = np.zeros(len(batch), dtype=np.float32)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    metrics = ach_update(model, opt, batch, adv, ret,
                         PPOConfig(minibatch_size=8, ppo_epochs=2, device="cpu"))
    for key in ("policy_loss", "value_loss", "entropy", "approx_kl",
                "clip_fraction", "saturated_fraction", "mean_abs_logit"):
        assert np.isfinite(metrics[key]), key
    np.testing.assert_array_equal(batch.planes, planes_before)
    np.testing.assert_array_equal(batch.actions, actions_before)


def test_ach_update_handles_minibatch_not_dividing_n_and_normalization():
    model, env = _tiny_model()
    batch = _synthetic_batch(env, n=16)
    adv = np.linspace(-1.0, 1.0, len(batch)).astype(np.float32)
    ret = np.zeros(len(batch), dtype=np.float32)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    # minibatch_size=5 does not divide 16; normalize_advantages=True must run cleanly.
    metrics = ach_update(model, opt, batch, adv, ret,
                         PPOConfig(minibatch_size=5, ppo_epochs=1,
                                   normalize_advantages=True, device="cpu"))
    assert np.isfinite(metrics["policy_loss"])
    assert 0.0 <= metrics["saturated_fraction"] <= 1.0
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_ach.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fh_mahjong_ai.ach'` (module not created yet).

- [ ] **Step 4: Implement `ach.py`**

Create `ai/src/fh_mahjong_ai/ach.py`:

```python
"""Clipped-NeuRD / ACH (Actor-Critic Hedge) policy update.

Drop-in alternative to ``ppo_update``: identical signature and the same
minibatch / epoch / grad-norm-clip / optimizer-step machinery. The only
difference is the policy loss. Where PPO's clipped surrogate yields a logit
gradient carrying a softmax ``(1 - pi)`` factor (vanilla policy gradient),
NeuRD makes the taken action's LOGIT gradient equal the advantage, so logits
accumulate advantage the way CFR accumulates regret. The ACH ``hedge``
threshold ``beta`` bounds logit magnitude (a trust region replacing PPO's
ratio clip), and a PPO-style clipped importance ratio (``clip_eps``) corrects
for off-policy drift when the batch is reused across epochs.
"""
from __future__ import annotations

import numpy as np
import torch

from .ppo import PPOConfig, RolloutBatch, masked_policy_distribution


def ach_policy_loss(masked_logits: torch.Tensor, actions: torch.Tensor,
                    weights: torch.Tensor, beta: float):
    """NeuRD/ACH policy loss on a minibatch.

    ``weights`` is the per-sample effective replicator weight ``w_t`` (the
    importance-corrected advantage). The loss is ``-(y_eff * weights).mean()``
    where ``y_eff`` is the taken action's logit, so the gradient on that logit
    is ``-weights / n`` — gradient descent adds ``weights`` to the logit. When
    the logit is already saturated beyond ``+/-beta`` in the direction
    ``weights`` would push it, its gradient is zeroed (the hedge threshold).

    Returns ``(loss, saturated_mask)``.
    """
    y_t = masked_logits.gather(1, actions.unsqueeze(1)).squeeze(1)
    saturated = ((y_t >= beta) & (weights > 0)) | ((y_t <= -beta) & (weights < 0))
    y_eff = torch.where(saturated, y_t.detach(), y_t)
    loss = -(y_eff * weights).mean()
    return loss, saturated


def ach_update(model, optimizer, batch: RolloutBatch,
               advantages: np.ndarray, returns: np.ndarray,
               config: PPOConfig) -> dict:
    device = config.device
    n = len(batch)
    planes = torch.from_numpy(np.asarray(batch.planes, dtype=np.float32)).to(device)
    scalars = torch.from_numpy(np.asarray(batch.scalars, dtype=np.float32)).to(device)
    action_mask = torch.from_numpy(np.asarray(batch.action_mask, dtype=np.int8)).to(device)
    actions = torch.from_numpy(np.asarray(batch.actions, dtype=np.int64)).to(device)
    old_logprobs = torch.from_numpy(np.asarray(batch.old_logprobs, dtype=np.float32)).to(device)
    adv_t = torch.from_numpy(np.asarray(advantages, dtype=np.float32)).to(device)
    ret_t = torch.from_numpy(np.asarray(returns, dtype=np.float32)).to(device)
    if config.normalize_advantages:
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

    beta = config.ach_beta
    last = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "approx_kl": 0.0,
            "clip_fraction": 0.0, "saturated_fraction": 0.0, "mean_abs_logit": 0.0}
    model.train()
    for _ in range(config.ppo_epochs):
        perm = torch.randperm(n, device=device)
        for start in range(0, n, config.minibatch_size):
            idx = perm[start : start + config.minibatch_size]
            masked_logits, value = model(planes[idx], scalars[idx], action_mask[idx])
            dist = masked_policy_distribution(masked_logits)
            new_logprobs = dist.log_prob(actions[idx])
            ratio = torch.exp(new_logprobs - old_logprobs[idx])
            rho = torch.clamp(ratio, 1.0 - config.clip_eps, 1.0 + config.clip_eps)
            w = rho * adv_t[idx]

            policy_loss, saturated = ach_policy_loss(masked_logits, actions[idx], w, beta)
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
                saturated_fraction = saturated.float().mean()
                y_t = masked_logits.gather(1, actions[idx].unsqueeze(1)).squeeze(1)
                mean_abs_logit = y_t.abs().mean()
            last = {
                "policy_loss": float(policy_loss.item()),
                "value_loss": float(value_loss.item()),
                "entropy": float(entropy.item()),
                "approx_kl": float(approx_kl.item()),
                "clip_fraction": float(clip_fraction.item()),
                "saturated_fraction": float(saturated_fraction.item()),
                "mean_abs_logit": float(mean_abs_logit.item()),
            }
    return last
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_ach.py -q`
Expected: PASS (5 tests).

- [ ] **Step 6: Run the full AI suite to confirm no regressions**

Run: `uv run --project ai pytest -q`
Expected: PASS — all pre-existing tests still green (adding two defaulted `PPOConfig` fields and a new module changes no existing behavior).

- [ ] **Step 7: Commit**

```bash
git add ai/src/fh_mahjong_ai/ach.py ai/src/fh_mahjong_ai/ppo.py ai/tests/test_ach.py
git commit -m "feat(ach): clipped-NeuRD ACH policy update (drop-in for ppo_update)"
```

---

### Task 2: Wire `train_selfplay_oracle` to select the objective

**Files:**
- Modify: `ai/src/fh_mahjong_ai/oracle.py` (`train_selfplay_oracle`, lines 472-526; the `ppo_update` call is at line 510)
- Test: `ai/tests/test_oracle_phase2.py` (add two tests)

**Interfaces:**
- Consumes: `ach_update` (from Task 1, `fh_mahjong_ai.ach`), `PPOConfig.objective` / `PPOConfig.ach_beta` (Task 1), existing `ppo_update` (ppo.py:203).
- Produces: `train_selfplay_oracle` history dicts additionally carry `"objective"` and `"ach_beta"`; when `config.objective == "ach"` the update is `ach_update`.

- [ ] **Step 1: Write the failing tests**

Append to `ai/tests/test_oracle_phase2.py`:

```python
def test_train_selfplay_oracle_ach_objective_records_metadata(tmp_path):
    from fh_mahjong_ai.oracle import train_selfplay_oracle
    mcfg = _mcfg()
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))   # 39ch anchor
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    cfg = PPOConfig(iterations=2, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    match_mode="classic", max_steps_per_episode=64, device="cpu",
                    objective="ach", ach_beta=1.5)
    history = train_selfplay_oracle(env_config=env_cfg, model_config=mcfg, anchor_checkpoint=anchor,
                                    checkpoint_dir=tmp_path / "sp_ach", config=cfg, base_seed=1,
                                    run_eval=False)
    assert len(history) == 2
    assert (tmp_path / "sp_ach" / "iter_002.pt").exists()
    assert all(h["objective"] == "ach" for h in history)
    assert all(h["ach_beta"] == 1.5 for h in history)
    # ACH-only metric surfaced into history:
    assert all("saturated_fraction" in h for h in history)


def test_train_selfplay_oracle_defaults_to_ppo_objective(tmp_path):
    from fh_mahjong_ai.oracle import train_selfplay_oracle
    mcfg = _mcfg()
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    cfg = PPOConfig(iterations=1, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    match_mode="classic", max_steps_per_episode=64, device="cpu")
    history = train_selfplay_oracle(env_config=env_cfg, model_config=mcfg, anchor_checkpoint=anchor,
                                    checkpoint_dir=tmp_path / "sp_ppo", config=cfg, base_seed=1,
                                    run_eval=False)
    assert history[0]["objective"] == "ppo"
    # PPO path must not surface the ACH-only metric.
    assert "saturated_fraction" not in history[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_oracle_phase2.py -q -k "ach_objective or defaults_to_ppo"`
Expected: FAIL — `KeyError: 'objective'` (history does not yet record `objective`/`ach_beta`).

- [ ] **Step 3: Add the import and select the update function**

In `ai/src/fh_mahjong_ai/oracle.py`, add to the imports near the top (the existing PPO import block around line 21 is `from .ppo import (RolloutBatch, PPOConfig, compute_gae, concat_rollout_batches, ppo_update, ...)`), add a new import line directly below it:

```python
from .ach import ach_update
```

Then in `train_selfplay_oracle`, immediately after `optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr)` (line 485), add:

```python
    update_fn = ach_update if config.objective == "ach" else ppo_update
```

- [ ] **Step 4: Use `update_fn` and record the metadata**

In `train_selfplay_oracle`, change the update call at line 510 from:

```python
            metrics = ppo_update(model, optimizer, batch, advantages, returns, config)
```

to:

```python
            metrics = update_fn(model, optimizer, batch, advantages, returns, config)
```

Then, immediately after `metrics["steps"] = len(batch)` (line 514) and before `save_checkpoint(...)` (line 515), add:

```python
            metrics["objective"] = config.objective
            metrics["ach_beta"] = config.ach_beta
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_oracle_phase2.py -q`
Expected: PASS — the two new tests plus every pre-existing Phase-2 test.

- [ ] **Step 6: Run the full AI suite**

Run: `uv run --project ai pytest -q`
Expected: PASS — no regressions.

- [ ] **Step 7: Commit**

```bash
git add ai/src/fh_mahjong_ai/oracle.py ai/tests/test_oracle_phase2.py
git commit -m "feat(ach): select ACH vs PPO objective in train_selfplay_oracle"
```

---

### Task 3: CLI flags `--objective` / `--ach-beta`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/train_selfplay_oracle.py` (argparse block lines 13-37; `PPOConfig(...)` construction lines 46-52)
- Test: `ai/tests/test_ach_cli.py`

**Interfaces:**
- Consumes: `train_selfplay_oracle` with objective wiring (Task 2), `PPOConfig.objective` / `PPOConfig.ach_beta` (Task 1).
- Produces: `fh-mj-train-selfplay-oracle --objective {ppo,ach} --ach-beta FLOAT`, threaded into `PPOConfig`.

- [ ] **Step 1: Write the failing test**

Create `ai/tests/test_ach_cli.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import save_checkpoint
import fh_mahjong_ai.scripts.train_selfplay_oracle as cli


def test_cli_threads_ach_objective_into_training(tmp_path, monkeypatch):
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))   # 39ch anchor
    ckpt = tmp_path / "sp"
    argv = [
        "fh-mj-train-selfplay-oracle",
        "--anchor-checkpoint", str(anchor),
        "--checkpoint-dir", str(ckpt),
        "--bridge-kind", "mock",
        "--match-mode", "classic",
        "--max-steps-per-episode", "64",
        "--iterations", "1",
        "--matches-per-iter", "2",
        "--num-workers", "1",
        "--ppo-epochs", "1",
        "--minibatch-size", "8",
        "--device", "cpu",
        "--objective", "ach",
        "--ach-beta", "1.25",
        "--model-channels", "8",
        "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "16",
        "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "16",
        "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ]
    monkeypatch.setattr("sys.argv", argv)
    cli.main()
    history = json.loads((ckpt / "history.json").read_text())
    assert history[0]["objective"] == "ach"
    assert history[0]["ach_beta"] == 1.25
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_ach_cli.py -q`
Expected: FAIL — argparse error `unrecognized arguments: --objective ach --ach-beta 1.25`.

- [ ] **Step 3: Add the CLI arguments**

In `ai/src/fh_mahjong_ai/scripts/train_selfplay_oracle.py`, after the `--base-seed` argument (line 37), add:

```python
    p.add_argument("--objective", choices=("ppo", "ach"), default="ppo",
                   help="policy update objective: PPO clipped surrogate (default) or ACH regret")
    p.add_argument("--ach-beta", type=float, default=2.0,
                   help="ACH hedge/logit trust-region threshold (used when --objective ach)")
```

- [ ] **Step 4: Thread the arguments into `PPOConfig`**

In the same file, in the `PPOConfig(...)` construction (lines 46-52), add the two fields to the end of the call — change the final line `pool_slots=args.pool_slots)` to:

```python
                       pool_slots=args.pool_slots,
                       objective=args.objective, ach_beta=args.ach_beta)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_ach_cli.py -q`
Expected: PASS.

- [ ] **Step 6: Run the full AI suite**

Run: `uv run --project ai pytest -q`
Expected: PASS — no regressions.

- [ ] **Step 7: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/train_selfplay_oracle.py ai/tests/test_ach_cli.py
git commit -m "feat(ach): --objective/--ach-beta CLI flags for fh-mj-train-selfplay-oracle"
```

---

## Notes for the implementer

- `mean_abs_logit` is intentionally the mean absolute value of the **taken action's** logit `y_t` (always a legal action), not of all logits — the masked illegal logits are `finfo.min` and would swamp the mean. This metric plus `saturated_fraction` are the health signals for tuning `β` during the operational A/B run.
- Do NOT add any field to `RolloutBatch`. If you find yourself wanting one, re-read Task 1: the hedge threshold reads the current-forward logit, and the importance ratio uses the existing `old_logprobs`.
- The operational A/B run (warm-start ACH vs PPO control from `iter_275`) is not in this plan; it runs on the box via the established Phase-B script pattern once this merges.
```

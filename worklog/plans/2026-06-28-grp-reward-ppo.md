# GRP-Shaped Reward for Online PPO — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PPO optimize a GRP-predicted placement signal (a frozen `GlobalEVNet`'s per-step placement-value delta) instead of myopic per-hand score, to break the parity plateau.

**Architecture:** A frozen GRP model (`GlobalEVNet`, trained offline by the existing `fh-mj-train-global-ev`) scores each learner state's expected final placement. `collect_rollouts`, when a GRP model is supplied, replaces the per-hand score reward with `g_{t+1} − g_t` per step and `realized_placement − g_last` at terminal (realized placement from the per-seat cumulative net). Eval gains a placement metric. Gated by `PPOConfig.grp_checkpoint` (None = current behavior).

**Tech Stack:** Python + PyTorch (`fh_mahjong_ai`), `uv`, multiprocessing (spawn). Reuses `global_ev.py`, `data.placement_shaped_returns`, `evaluate.episode_reward_vector`. No Go/proto changes.

## Global Constraints

- **`grp_checkpoint is None` (default) is byte-identical to the current score-reward behavior** — the regression guard. All existing `collect_rollouts`/PPO/eval tests pass unchanged.
- GRP is **frozen**: `eval()` + `requires_grad_(False)`; all GRP forwards under `torch.no_grad()`.
- GRP target is **placement** (`placement_values = (1.0, 1/3, -1/3, -1.0)`), via `data.placement_shaped_returns`.
- `realized_placement` at terminal is derived from the per-seat **cumulative net** (sum of `step.rewards` over the match, which telescopes to net), NOT a single terminal step.
- The GRP `GlobalEVNet` is constructed with the **same `ModelConfig` as the policy** (document this; load fails fast on mismatch).
- LEARNING_SEAT == 0 (existing constant).
- Reward changes are training-signal only; the net eval metric stays unchanged for anchor comparability — the placement metric is **added alongside**, not replacing it.
- Test commands: `uv run --project ai pytest ai/tests/<file>::<test> -q`.
- Commit trailer (every commit): `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Branch: `claude/ppo-grp-reward` (off main).

## File Structure

- `ai/src/fh_mahjong_ai/ppo.py` — MODIFY: `PPOConfig` (grp fields); `collect_rollouts` (optional `grp_model` + GRP-delta reward path); `train_ppo` (load/freeze GRP, fail-fast, thread to collectors).
- `ai/src/fh_mahjong_ai/parallel_rollouts.py` — MODIFY: ship frozen GRP `state_dict` to workers; workers build + use it.
- `ai/src/fh_mahjong_ai/evaluate.py` — MODIFY: add `episode_placement` helper + a placement metric in the duplicate-seat report.
- `ai/src/fh_mahjong_ai/scripts/train_ppo.py` — MODIFY: `--grp-checkpoint` flag; thread through; MLflow placement.
- `ai/tests/test_ppo.py`, `ai/tests/test_parallel_rollouts.py`, `ai/tests/test_evaluate.py` — tests.

Phase 1 (train + validate the GRP model) uses the **existing** `fh-mj-train-global-ev` CLI and is an operational step (see the end), not new code — it already reports `regression_metrics` vs `constant_baseline_metrics`.

---

## Task 1: GRP-delta reward in collect_rollouts + PPOConfig fields

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (`PPOConfig` ~line 21; `collect_rollouts` ~line 200-306)
- Test: `ai/tests/test_ppo.py`

**Interfaces:**
- Produces:
  - `PPOConfig.grp_checkpoint: Optional[Path] = None`, `PPOConfig.grp_placement_values: tuple = (1.0, 1.0/3.0, -1.0/3.0, -1.0)`.
  - `collect_rollouts(env_config, policy_model, frozen_anchor, config, base_seed, opponents=None, grp_model=None)` — when `grp_model` is a `GlobalEVNet`, the learning-seat reward is the GRP placement-delta (per step `g_{t+1}-g_t`; terminal `realized_placement - g_last`); when `None`, the current score reward is used unchanged.
- Consumes: `global_ev.GlobalEVNet`, `data.placement_shaped_returns`.

- [ ] **Step 1: Write the failing tests**

Add to `ai/tests/test_ppo.py`:

```python
from fh_mahjong_ai.global_ev import GlobalEVNet


class _StubGRP:
    """Returns g = step * call_count (unbounded increment) so every consecutive
    GRP delta is exactly `step` — lets us assert exact GRP-delta rewards."""
    def __init__(self, step=0.25):
        self._step = step
        self._i = 0
    def __call__(self, planes, scalars):
        import torch
        v = self._step * self._i
        self._i += 1
        return torch.tensor([float(v)])
    def eval(self):
        return self


def test_ppo_config_grp_defaults():
    cfg = PPOConfig()
    assert cfg.grp_checkpoint is None
    assert len(cfg.grp_placement_values) == 4


def test_collect_rollouts_grp_none_matches_score_reward():
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    learner = PolicyValueNet(env_cfg, mcfg)
    frozen = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=3, match_mode="classic", max_steps_per_episode=64, device="cpu")
    a = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=11)
    b = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=11, grp_model=None)
    np.testing.assert_array_equal(a.actions, b.actions)
    np.testing.assert_allclose(a.rewards, b.rewards, rtol=1e-6)


def test_collect_rollouts_grp_reward_is_placement_delta():
    # mock bridge: GRP returns an increasing sequence; assert intermediate rewards are g_{t+1}-g_t
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    learner = PolicyValueNet(env_cfg, mcfg)
    frozen = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=1, match_mode="classic", max_steps_per_episode=64, device="cpu")
    grp = _StubGRP(step=0.25)
    batch = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=5, grp_model=grp)
    # learner decisions in one match -> non-terminal rewards equal consecutive GRP diffs (0.25 each),
    # except the final decision (realized_placement - g_last). The mock is single learner seat per match.
    assert len(batch) >= 2
    # all non-final rewards equal 0.25 (g step), within float tolerance
    np.testing.assert_allclose(batch.rewards[:-1], 0.25, atol=1e-5)
    assert batch.dones[-1] == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_ppo_config_grp_defaults ai/tests/test_ppo.py::test_collect_rollouts_grp_reward_is_placement_delta -q`
Expected: FAIL (`AttributeError: grp_checkpoint` / `TypeError: unexpected keyword 'grp_model'`).

- [ ] **Step 3: Add the PPOConfig fields**

In `ai/src/fh_mahjong_ai/ppo.py`, in `PPOConfig`, add after the pool fields (before `device`):

```python
    grp_checkpoint: Optional[Path] = None
    grp_placement_values: tuple = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)
    device: str = "cpu"
```

- [ ] **Step 4: Add the GRP-delta reward path to `collect_rollouts`**

Add the import near the top of `ppo.py`:

```python
from .data import placement_shaped_returns
```

Change the signature to accept `grp_model`:

```python
def collect_rollouts(
    env_config: EnvConfig,
    policy_model,
    frozen_anchor,
    config: PPOConfig,
    base_seed: int,
    opponents: Optional[list] = None,
    grp_model=None,
) -> RolloutBatch:
```

Inside the match loop, maintain per-match GRP bookkeeping. At the start of each match (right after the existing per-match setup), add:

```python
            match_indices: list[int] = []   # rewards_l indices for this match (GRP path)
            match_g: list[float] = []        # GRP placement value at each learner decision
            cum_net = np.zeros(4, dtype=np.float32)  # per-seat cumulative net (telescopes to match net)
```

In the learner-seat branch, after appending the decision (where `last_learn_index` is set), record the GRP value when active:

```python
                    last_learn_index = len(actions_l) - 1
                    if grp_model is not None:
                        with torch.no_grad():
                            g = float(grp_model(planes, scalars)[0])
                        match_indices.append(last_learn_index)
                        match_g.append(g)
```

After `step = env.step(action)`, accumulate net (GRP path) instead of the score reward:

```python
                step = env.step(action)
                if grp_model is not None:
                    cum_net += np.asarray(step.rewards, dtype=np.float32)[:4] if np.asarray(step.rewards).size else 0.0
                elif last_learn_index is not None:
                    rewards_l[last_learn_index] += _seat_step_reward(step.rewards, LEARNING_SEAT)
```

At terminal (where `dones_l[last_learn_index] = 1.0` is set), when GRP active, fill the match's GRP-delta rewards:

```python
                if step.terminated or step.truncated:
                    if last_learn_index is not None:
                        dones_l[last_learn_index] = 1.0
                    if grp_model is not None and match_indices:
                        realized = float(placement_shaped_returns(
                            cum_net[None, :], config.grp_placement_values)[0, LEARNING_SEAT])
                        for k, idx in enumerate(match_indices):
                            if k + 1 < len(match_g):
                                rewards_l[idx] = match_g[k + 1] - match_g[k]
                            else:
                                rewards_l[idx] = realized - match_g[k]
                    break
                obs = step.observation
```

(The `rewards_l.append(0.0)` at decision time stays; the GRP path overwrites those entries at match end. The score path keeps using `+=` as before.)

- [ ] **Step 5: Run the tests**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -q`
Expected: PASS (new GRP tests + all existing — the `grp_model=None` default path is unchanged).

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/tests/test_ppo.py
git commit -m "feat(ppo): GRP placement-delta reward in collect_rollouts (opt-in)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: train_ppo loads/freezes GRP + threads it to collection

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (`train_ppo` ~line 324)
- Test: `ai/tests/test_ppo.py`

**Interfaces:**
- Produces: `train_ppo` builds a frozen `GlobalEVNet` from `config.grp_checkpoint` (same `model_config`), passes it to the sequential `collect_rollouts` and to the parallel collector (as a state_dict); fails fast if the checkpoint is missing/incompatible.
- Consumes: `collect_rollouts(..., grp_model=)` (Task 1); `ParallelRolloutCollector(..., grp_state_dict=)` (Task 3); `global_ev.GlobalEVNet`, `storage.load_checkpoint`.

- [ ] **Step 1: Write the failing test**

Add to `ai/tests/test_ppo.py`:

```python
def test_train_ppo_with_grp_mock(tmp_path):
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))
    grp = tmp_path / "grp.pt"
    save_checkpoint(grp, GlobalEVNet(env_cfg, mcfg))
    cfg = PPOConfig(iterations=2, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    eval_interval=100, match_mode="classic", max_steps_per_episode=64,
                    device="cpu", grp_checkpoint=grp)
    metrics = train_ppo(env_config=env_cfg, model_config=mcfg, init_checkpoint=init,
                        checkpoint_dir=tmp_path / "ppo", config=cfg, base_seed=3, run_eval=False)
    assert len(metrics) == 2
    assert all(np.isfinite(m["policy_loss"]) for m in metrics)


def test_train_ppo_missing_grp_fails_fast(tmp_path):
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))
    cfg = PPOConfig(iterations=1, matches_per_iter=2, match_mode="classic",
                    max_steps_per_episode=64, device="cpu", grp_checkpoint=tmp_path / "nope.pt")
    with pytest.raises((FileNotFoundError, RuntimeError, ValueError)):
        train_ppo(env_config=env_cfg, model_config=mcfg, init_checkpoint=init,
                  checkpoint_dir=tmp_path / "ppo", config=cfg, base_seed=1, run_eval=False)
```

Add the import at the top of `test_ppo.py` if missing: `from fh_mahjong_ai.global_ev import GlobalEVNet` (also used in Task 1).

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_train_ppo_with_grp_mock ai/tests/test_ppo.py::test_train_ppo_missing_grp_fails_fast -q`
Expected: FAIL (GRP not loaded; no fail-fast).

- [ ] **Step 3: Add a GRP loader helper + wire into train_ppo**

In `ppo.py`, add the import:

```python
from .global_ev import GlobalEVNet
```

Add a helper near `build_opponent_nets`:

```python
def load_grp_model(env_config, model_config, grp_checkpoint, device="cpu"):
    """Load a frozen GlobalEVNet GRP model (same ModelConfig as the policy)."""
    grp = GlobalEVNet(env_config, model_config).to(device)
    load_checkpoint(Path(grp_checkpoint), grp)
    grp.eval()
    for p in grp.parameters():
        p.requires_grad_(False)
    return grp
```

In `train_ppo`, after the existing config validation (the pool guards), build the GRP model:

```python
    grp_model = None
    if config.grp_checkpoint is not None:
        grp_model = load_grp_model(env_config, model_config, config.grp_checkpoint, device)
```

(`load_checkpoint` raising on a missing/incompatible file gives the fail-fast.)

Pass `grp_model` to the sequential `collect_rollouts` calls (both the `pool_max_size>1` and the plain branch):

```python
            elif config.pool_max_size > 1:
                opponents = build_opponent_nets(env_config, model_config, pool_states, device)
                batch = collect_rollouts(env_config, model, frozen, config, base_seed=iter_seed, opponents=opponents, grp_model=grp_model)
            else:
                batch = collect_rollouts(env_config, model, frozen, config, base_seed=iter_seed, grp_model=grp_model)
```

For the parallel branch, build + pass the GRP state_dict to the collector (collector support is Task 3):

```python
        if config.num_workers > 1:
            from .parallel_rollouts import ParallelRolloutCollector
            grp_state = None
            if grp_model is not None:
                grp_state = {k: v.detach().cpu() for k, v in grp_model.state_dict().items()}
            collector = ParallelRolloutCollector(
                env_config, model_config, config, config.num_workers, grp_state_dict=grp_state,
            )
            collector.start()
```

- [ ] **Step 4: Run the tests**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -q`
Expected: PASS (GRP train e2e + fail-fast; existing tests unaffected — `grp_checkpoint` defaults None).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/tests/test_ppo.py
git commit -m "feat(ppo): train_ppo loads frozen GRP + threads to collection (fail-fast)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Parallel collector ships the frozen GRP

**Files:**
- Modify: `ai/src/fh_mahjong_ai/parallel_rollouts.py`
- Test: `ai/tests/test_parallel_rollouts.py`

**Interfaces:**
- Produces: `ParallelRolloutCollector(env_config, model_config, ppo_config, num_workers, grp_state_dict=None)`; workers rebuild a frozen `GlobalEVNet` from `grp_state_dict` (once at startup) and pass it to `collect_rollouts`.
- Consumes: `load_grp_model` / `GlobalEVNet`, `collect_rollouts(..., grp_model=)` (Tasks 1-2).

- [ ] **Step 1: Write the failing test**

Add to `ai/tests/test_parallel_rollouts.py`:

```python
def test_parallel_grp_matches_sequential():
    from fh_mahjong_ai.global_ev import GlobalEVNet
    from fh_mahjong_ai.ppo import load_grp_model
    import tempfile, os
    from fh_mahjong_ai.storage import save_checkpoint

    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = _small_model_cfg()
    learner = PolicyValueNet(env_cfg, mcfg)
    frozen = PolicyValueNet(env_cfg, mcfg)
    grp_net = GlobalEVNet(env_cfg, mcfg)
    grp_state = {k: v.detach().cpu() for k, v in grp_net.state_dict().items()}
    cfg = PPOConfig(matches_per_iter=4, match_mode="classic", max_steps_per_episode=64, device="cpu")

    grp_net.eval()
    seq = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=222, grp_model=grp_net)

    collector = ParallelRolloutCollector(env_cfg, mcfg, cfg, num_workers=2, grp_state_dict=grp_state)
    collector.start()
    try:
        par = collector.collect(_cpu_state_dict(learner), [_cpu_state_dict(frozen)], base_seed=222, matches_per_iter=4)
    finally:
        collector.close()
    assert len(par) == len(seq)
    np.testing.assert_allclose(np.sort(par.rewards), np.sort(seq.rewards), rtol=1e-5)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai pytest ai/tests/test_parallel_rollouts.py::test_parallel_grp_matches_sequential -q`
Expected: FAIL (`TypeError: unexpected keyword 'grp_state_dict'`).

- [ ] **Step 3: Update the collector + worker**

In `parallel_rollouts.py`, import the loader:

```python
from .ppo import PPOConfig, RolloutBatch, build_opponent_nets, collect_rollouts, concat_rollout_batches, load_grp_model
```

`__init__` gains `grp_state_dict=None`:

```python
    def __init__(self, env_config, model_config, ppo_config, num_workers, grp_state_dict=None):
        ...
        self.grp_state_dict = grp_state_dict
```

Pass it to workers in `start()` (add to the `args=` tuple), and update `_worker_loop` signature to accept it and build the GRP once:

```python
def _worker_loop(env_config, model_config, ppo_config, grp_state_dict, task_q, result_q):
    import torch
    from .model import PolicyValueNet
    torch.set_num_threads(1)
    learner = PolicyValueNet(env_config, model_config)
    grp_model = None
    if grp_state_dict is not None:
        from .global_ev import GlobalEVNet
        grp_model = GlobalEVNet(env_config, model_config)
        grp_model.load_state_dict(grp_state_dict)
        grp_model.eval()
        for p in grp_model.parameters():
            p.requires_grad_(False)
    while True:
        task = task_q.get()
        if task is None:
            return
        worker_id, learner_state_dict, pool_states, base_seed, matches = task
        try:
            learner.load_state_dict(learner_state_dict)
            opponents = build_opponent_nets(env_config, model_config, pool_states, device="cpu")
            cfg = replace(ppo_config, matches_per_iter=matches, device="cpu")
            batch = collect_rollouts(env_config, learner, opponents[0], cfg, base_seed=base_seed,
                                     opponents=opponents, grp_model=grp_model)
            result_q.put((worker_id, batch, None))
        except Exception:  # noqa: BLE001
            result_q.put((worker_id, None, traceback.format_exc()))
```

Update the `start()` Process `args` to include `self.grp_state_dict`:

```python
            p = self._ctx.Process(
                target=_worker_loop,
                args=(self.env_config, self.model_config, self.ppo_config,
                      self.grp_state_dict, self._task_q, self._result_q),
                daemon=True,
            )
```

- [ ] **Step 4: Run the parallel suite**

Run: `uv run --project ai pytest ai/tests/test_parallel_rollouts.py -q`
Expected: PASS (new GRP determinism test + existing — `grp_state_dict=None` default unchanged).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/parallel_rollouts.py ai/tests/test_parallel_rollouts.py
git commit -m "feat(ppo): parallel collector ships the frozen GRP model

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Placement eval metric

**Files:**
- Modify: `ai/src/fh_mahjong_ai/evaluate.py`
- Test: `ai/tests/test_evaluate.py` (or `ai/tests/test_ppo.py` if a focused unit test fits better)

**Interfaces:**
- Produces: `episode_placement(episode, fallback_rewards, learning_seat, placement_values) -> float` — the learning seat's placement value from the episode's per-seat net; and a `mean_placement` (+`mean_placement_ci95`) field in the duplicate-seat report.
- Consumes: `episode_reward_vector` (existing), `data.placement_shaped_returns`.

- [ ] **Step 1: Write the failing test**

Add to `ai/tests/test_evaluate.py`:

```python
import numpy as np
from fh_mahjong_ai.evaluate import episode_placement


def test_episode_placement_ranks_learning_seat():
    # learning seat 0 has the highest net -> placement value 1.0
    ep = [_grp_dummy_transition([3.0, 1.0, -1.0, -3.0])]
    pv = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)
    val = episode_placement(ep, fallback_rewards=np.zeros(4, dtype=np.float32),
                            learning_seat=0, placement_values=pv)
    assert val == 1.0
    # learning seat 3 has the lowest -> -1.0
    val3 = episode_placement(ep, fallback_rewards=np.zeros(4, dtype=np.float32),
                             learning_seat=3, placement_values=pv)
    assert val3 == -1.0
```

Add a small dummy-transition helper at the top of `test_evaluate.py` if one doesn't exist:

```python
from fh_mahjong_ai.types import Observation, Transition
def _grp_dummy_transition(rewards):
    o = Observation(seat=0, planes=np.zeros((1, 1, 1), dtype=np.float32),
                    scalars=np.zeros(1, dtype=np.float32),
                    action_mask=np.ones(1, dtype=np.int8), metadata={})
    return Transition(observation=o, action_id=0, rewards=np.asarray(rewards, dtype=np.float32),
                      next_observation=o, terminated=True, truncated=False, info={})
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai pytest ai/tests/test_evaluate.py::test_episode_placement_ranks_learning_seat -q`
Expected: FAIL (`ImportError: episode_placement`).

- [ ] **Step 3: Add `episode_placement` + the report field**

In `evaluate.py`, add (near `episode_reward_vector`):

```python
from .data import placement_shaped_returns


def episode_placement(episode, fallback_rewards, learning_seat, placement_values) -> float:
    """The learning seat's placement value (rank) from the episode's per-seat net."""
    net = episode_reward_vector(episode, fallback_rewards, num_seats=4)
    shaped = placement_shaped_returns(np.asarray(net, dtype=np.float32)[None, :], placement_values)
    return float(shaped[0, learning_seat])
```

In the duplicate-seat online eval, accumulate per-episode placement alongside the existing reward, and add `mean_placement` / `mean_placement_ci95` to the report using the existing `reward_summary` helper. In `record_episode` (the closure that already computes `reward`), also compute:

```python
        placement = episode_placement(episode, rewards, learning_seat,
                                      (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0))
        seat_placements.append(placement)
```

(initialize `seat_placements: list[float] = []` next to `seat_rewards`), and in the report dict add:

```python
        "mean_placement": reward_summary(seat_placements)["mean"],
        "mean_placement_ci95": reward_summary(seat_placements)["ci95"],
```

Thread `seat_placements` up through `evaluate_duplicate_seats` the same way `per_episode_rewards` is aggregated, exposing `mean_placement` in the top-level duplicate-seat report.

- [ ] **Step 4: Run the tests**

Run: `uv run --project ai pytest ai/tests/test_evaluate.py -q`
Expected: PASS (new placement test + existing eval tests).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/evaluate.py ai/tests/test_evaluate.py
git commit -m "feat(eval): placement metric alongside net in duplicate-seat eval

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: CLI flags + MLflow

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/train_ppo.py`
- Test: `ai/tests/test_ppo.py`

**Interfaces:**
- Produces: `--grp-checkpoint` on `fh-mj-train-ppo`, passed into `PPOConfig.grp_checkpoint`.

- [ ] **Step 1: Write the failing test**

Add to `ai/tests/test_ppo.py` (mirrors the existing CLI mock test, adding `--grp-checkpoint`):

```python
def test_cli_train_ppo_grp(tmp_path, monkeypatch):
    import sys
    from fh_mahjong_ai.scripts import train_ppo as cli
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"; save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))
    grp = tmp_path / "grp.pt"; save_checkpoint(grp, GlobalEVNet(env_cfg, mcfg))
    argv = [
        "fh-mj-train-ppo", "--init-checkpoint", str(init), "--checkpoint-dir", str(tmp_path / "ppo"),
        "--iterations", "1", "--matches-per-iter", "2", "--ppo-epochs", "1", "--minibatch-size", "8",
        "--match-mode", "classic", "--bridge-kind", "mock", "--max-steps-per-episode", "64", "--no-eval",
        "--grp-checkpoint", str(grp),
        "--model-channels", "8", "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16", "--model-q-hidden-dim", "16",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    assert (tmp_path / "ppo" / "iter_001.pt").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_cli_train_ppo_grp -q`
Expected: FAIL (`unrecognized arguments: --grp-checkpoint`).

- [ ] **Step 3: Add the flag**

In `scripts/train_ppo.py`, add the argument near `--init-checkpoint`:

```python
    parser.add_argument("--grp-checkpoint", type=Path, default=None,
                        help="Frozen GlobalEVNet GRP checkpoint; reward becomes the placement-value delta")
```

Pass it into `PPOConfig(...)`:

```python
        pool_max_size=args.pool_max_size, pool_snapshot_interval=args.pool_snapshot_interval,
        grp_checkpoint=args.grp_checkpoint,
        device=args.device,
    )
```

- [ ] **Step 4: Run the test**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_cli_train_ppo_grp -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/train_ppo.py ai/tests/test_ppo.py
git commit -m "feat(ppo): --grp-checkpoint CLI flag

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Full-suite verification + docs

**Files:**
- Modify: `ai/AGENTS.md`

- [ ] **Step 1: Full PPO + parallel + eval suites**

Run: `uv run --project ai pytest ai/tests/test_ppo.py ai/tests/test_parallel_rollouts.py ai/tests/test_evaluate.py -q`
Expected: PASS

- [ ] **Step 2: Full Python suite (no regressions)**

Run: `uv run --project ai pytest ai/tests/ -q`
Expected: PASS

- [ ] **Step 3: Update AGENTS.md**

In `ai/AGENTS.md`, document: `PPOConfig.grp_checkpoint` / `--grp-checkpoint` makes the learning-seat reward the GRP (GlobalEVNet) placement-value delta (`g_{t+1}-g_t`, terminal `realized_placement - g_last`) instead of per-hand score; GRP is trained offline via `fh-mj-train-global-ev` with `reward_shaping="placement"` and frozen; the duplicate-seat eval now reports `mean_placement` alongside the net metric; `grp_checkpoint=None` is the unchanged score-reward default.

- [ ] **Step 4: Commit**

```bash
git add ai/AGENTS.md
git commit -m "docs(ai): document GRP-shaped PPO reward + placement eval

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Phase 1 (operational, before the GRP PPO run) — train + validate the GRP model

Uses existing tooling; run on the GPU box:

1. Generate anchor self-play trajectories (existing data-gen via the Go bridge, anchor playing all seats), Chongci, carrying `terminal_rewards` + seats.
2. Train the GRP: `fh-mj-train-global-ev` on that data with placement targets (`reward_shaping="placement"`), same `ModelConfig` as the policy → frozen GRP `.pt`.
3. **Validation gate:** confirm the run's reported `regression_metrics` beat `constant_baseline_metrics` on the held-out split. If GRP cannot predict placement better than a constant, STOP — it carries no signal and the GRP-PPO run would be pointless.

## Phase 2 (operational) — the GRP-shaped PPO run

```
fh-mj-train-ppo --init-checkpoint <anchor> --checkpoint-dir <run>/ckpt \
  --iterations 80 --matches-per-iter 256 --num-workers 12 --match-mode chongci \
  --device cuda --no-eval --base-seed <seed> --grp-checkpoint <grp.pt> \
  --mlflow --mlflow-run-name grp-ppo
```

Then eval milestone checkpoints with `fh-mj-evaluate --duplicate-seats ... --match-mode chongci` and compare **mean_placement** (the new objective) and **mean_reward** (net, vs the anchor baseline `+0.0059 ± 0.0372`). Compute the anchor's `mean_placement` baseline too. Success = GRP-PPO exceeds the anchor on placement without regressing net.

**Memory note:** GRP adds a frozen net per worker. Keep `--num-workers` ≤ 12 (with `pool_max_size=1`) to stay within the 31 GB box ceiling that bit the 4-config sweep.

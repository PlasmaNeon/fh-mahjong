# PPO Self-Play Opponent Pool (Tier 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Train the PPO learning seat against a pool of frozen neural opponents (anchor + past-learner snapshots) sampled per opponent-seat per match, instead of a single frozen anchor.

**Architecture:** `collect_rollouts` gains an additive `opponents` list param (default `None` → current single-anchor behavior). `train_ppo` owns a pool of CPU `state_dict`s (seeded with the anchor, snapshotting the learner every N iters, capped). A shared `build_opponent_nets` helper turns the pool into frozen nets, used by both the sequential path and the parallel workers. The parallel collector ships the pool each iteration.

**Tech Stack:** Python + PyTorch (`fh_mahjong_ai`), `uv`, multiprocessing (spawn). No Go, no proto changes.

## Global Constraints

- **`pool_max_size == 1` is byte-identical to current single-anchor training** — the regression guard. Default `pool_max_size = 1`.
- Reward (dense per-hand) and observation encoding are **unchanged** — the promoted anchor and eval baseline stay valid.
- Determinism: parallel collection must equal sequential over the same seeds (opponent assignment uses a per-match NumPy RNG seeded by the match seed, separate from the learner's `torch.manual_seed`).
- Opponents are frozen: `eval()` + `requires_grad_(False)`.
- Test commands:
  - `uv run --project ai pytest ai/tests/test_ppo.py -q`
  - `uv run --project ai pytest ai/tests/test_parallel_rollouts.py -q`
- Commit message footer (every commit):
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```
- Branch: `claude/ppo-selfplay-pool` (off main; #94–#97 merged).

## File Structure

- `ai/src/fh_mahjong_ai/ppo.py` — MODIFY: `PPOConfig` (2 fields); `collect_rollouts` (additive `opponents` param + per-match opponent sampling); add `build_opponent_nets`; `train_ppo` (pool management + sequential/parallel wiring + `pool_size` metric).
- `ai/src/fh_mahjong_ai/parallel_rollouts.py` — MODIFY: collector `__init__` drops `frozen_state_dict`; `collect` takes `pool_states`; worker builds opponents from the shipped pool.
- `ai/src/fh_mahjong_ai/scripts/train_ppo.py` — MODIFY: `--pool-max-size` / `--pool-snapshot-interval` flags; add `pool_size` to `_MLFLOW_METRIC_KEYS`.
- `ai/tests/test_ppo.py` — MODIFY: opponent-pool tests.
- `ai/tests/test_parallel_rollouts.py` — MODIFY: update to new collector signatures + parallel==sequential-with-pool test.
- `ai/AGENTS.md` — MODIFY: document the pool.

---

## Task 1: PPOConfig pool fields + opponent sampling in collect_rollouts

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (`PPOConfig` ~line 21-41; `collect_rollouts` ~line 200-287)
- Test: `ai/tests/test_ppo.py`

**Interfaces:**
- Produces:
  - `PPOConfig.pool_max_size: int = 1`, `PPOConfig.pool_snapshot_interval: int = 10`.
  - `collect_rollouts(env_config, policy_model, frozen_anchor, config, base_seed, opponents=None)` — when `opponents` is `None` it behaves exactly as today (uses `frozen_anchor` for every non-learner seat). When `opponents` is a non-empty list of nets, each opponent seat (1,2,3) is assigned a pool member per match via `np.random.default_rng(base_seed + m)`.

- [ ] **Step 1: Write the failing tests**

Add to `ai/tests/test_ppo.py`:

```python
def test_ppo_config_has_pool_defaults():
    cfg = PPOConfig()
    assert cfg.pool_max_size == 1
    assert cfg.pool_snapshot_interval == 10


def _small_env_model():
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    return env_cfg, mcfg


def test_collect_rollouts_pool_size_one_matches_single_anchor():
    env_cfg, mcfg = _small_env_model()
    learner = PolicyValueNet(env_cfg, mcfg)
    frozen = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=3, match_mode="classic", max_steps_per_episode=64, device="cpu")
    a = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=321)                      # default path
    b = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=321, opponents=[frozen])  # size-1 pool
    assert len(a) == len(b)
    np.testing.assert_array_equal(a.actions, b.actions)
    np.testing.assert_allclose(a.rewards, b.rewards, rtol=1e-6)


def test_collect_rollouts_with_pool_is_deterministic():
    env_cfg, mcfg = _small_env_model()
    learner = PolicyValueNet(env_cfg, mcfg)
    pool = [PolicyValueNet(env_cfg, mcfg), PolicyValueNet(env_cfg, mcfg), PolicyValueNet(env_cfg, mcfg)]
    cfg = PPOConfig(matches_per_iter=4, match_mode="classic", max_steps_per_episode=64, device="cpu")
    a = collect_rollouts(env_cfg, learner, pool[0], cfg, base_seed=77, opponents=pool)
    b = collect_rollouts(env_cfg, learner, pool[0], cfg, base_seed=77, opponents=pool)
    np.testing.assert_array_equal(a.actions, b.actions)
    np.testing.assert_allclose(a.rewards, b.rewards, rtol=1e-6)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_ppo_config_has_pool_defaults ai/tests/test_ppo.py::test_collect_rollouts_with_pool_is_deterministic -q`
Expected: FAIL (`AttributeError: ... pool_max_size` / `TypeError: ... unexpected keyword 'opponents'`).

- [ ] **Step 3: Add the PPOConfig fields**

In `ai/src/fh_mahjong_ai/ppo.py`, in `PPOConfig`, add after `num_workers: int = 1`:

```python
    num_workers: int = 1
    pool_max_size: int = 1
    pool_snapshot_interval: int = 10
    device: str = "cpu"
```

- [ ] **Step 4: Add the `opponents` param + per-match sampling to `collect_rollouts`**

Change the signature:

```python
def collect_rollouts(
    env_config: EnvConfig,
    policy_model,
    frozen_anchor,
    config: PPOConfig,
    base_seed: int,
    opponents: Optional[list] = None,
) -> RolloutBatch:
```

Replace the `policy_model.eval()` / `frozen_anchor.eval()` lines with a pool setup:

```python
    policy_model.eval()
    pool = list(opponents) if opponents else [frozen_anchor]
    for net in pool:
        net.eval()
```

Inside the match loop, right after `torch.manual_seed(int(base_seed + m))`, assign opponents for this match:

```python
            torch.manual_seed(int(base_seed + m))
            # Opponent assignment uses a separate NumPy RNG so it never perturbs
            # the learner's torch sampling stream (keeps pool-size-1 byte-identical
            # to the single-anchor path) and stays reproducible across the
            # sequential and parallel collectors.
            opp_rng = np.random.default_rng(int(base_seed + m))
            seat_opponent = {s: pool[int(opp_rng.integers(len(pool)))] for s in (1, 2, 3)}
```

In the `else` (non-learner) branch, use the assigned opponent instead of `frozen_anchor`:

```python
                else:
                    net = seat_opponent.get(seat, pool[0])
                    with torch.no_grad():
                        logits, _ = net(planes, scalars, mask)
                        action = int(torch.argmax(logits, dim=1)[0].item())
```

- [ ] **Step 5: Run the new + existing collect tests**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -q`
Expected: PASS (new pool tests pass; existing `collect_rollouts`/reproducibility/e2e tests still pass — the default `opponents=None` path and learner torch stream are unchanged).

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/tests/test_ppo.py
git commit -m "feat(ppo): opponent pool sampling in collect_rollouts (opt-in)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Pool management in train_ppo + build_opponent_nets

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (add `build_opponent_nets`; `train_ppo` ~line 290-377)
- Test: `ai/tests/test_ppo.py`

**Interfaces:**
- Produces:
  - `build_opponent_nets(env_config, model_config, pool_states, device="cpu") -> list` — builds a frozen (`eval()` + no-grad) `PolicyValueNet` per `state_dict` in `pool_states`.
  - `train_ppo` maintains `pool_states: list[dict]` (index 0 = anchor, snapshot the learner every `pool_snapshot_interval` iters, cap `pool_max_size`, evict oldest snapshot keeping index 0); records `metrics["pool_size"]`; passes `pool_states` to the parallel collector and `opponents` to the sequential `collect_rollouts` when `pool_max_size > 1`.
- Consumes: `collect_rollouts(..., opponents=)` (Task 1); `ParallelRolloutCollector(env_config, model_config, ppo_config, num_workers)` + `collect(learner_state, pool_states, base_seed, matches)` (Task 3).

- [ ] **Step 1: Write the failing test**

Add to `ai/tests/test_ppo.py`:

```python
from fh_mahjong_ai.ppo import build_opponent_nets


def test_build_opponent_nets_are_frozen():
    env_cfg, mcfg = _small_env_model()
    states = [PolicyValueNet(env_cfg, mcfg).state_dict() for _ in range(3)]
    nets = build_opponent_nets(env_cfg, mcfg, states, device="cpu")
    assert len(nets) == 3
    assert all(not any(p.requires_grad for p in n.parameters()) for n in nets)


def test_train_ppo_pool_grows_and_caps(tmp_path):
    env_cfg, mcfg = _small_env_model()
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))
    # snapshot every iter, cap at 3 (anchor + 2 snapshots)
    cfg = PPOConfig(iterations=5, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    eval_interval=100, match_mode="classic", max_steps_per_episode=64,
                    device="cpu", pool_max_size=3, pool_snapshot_interval=1)
    metrics = train_ppo(env_config=env_cfg, model_config=mcfg, init_checkpoint=init,
                        checkpoint_dir=tmp_path / "ppo", config=cfg, base_seed=5, run_eval=False)
    sizes = [m["pool_size"] for m in metrics]
    assert sizes[0] == 2          # anchor + first snapshot
    assert max(sizes) == 3        # capped
    assert sizes[-1] == 3
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_build_opponent_nets_are_frozen ai/tests/test_ppo.py::test_train_ppo_pool_grows_and_caps -q`
Expected: FAIL (`ImportError: build_opponent_nets` / `KeyError: 'pool_size'`).

- [ ] **Step 3: Add `build_opponent_nets`**

In `ai/src/fh_mahjong_ai/ppo.py`, add near `train_ppo` (after `collect_rollouts`):

```python
def build_opponent_nets(env_config, model_config, pool_states, device="cpu"):
    """Build a frozen PolicyValueNet for each opponent state_dict in the pool.
    Shared by the sequential trainer and the parallel workers so both construct
    opponents identically."""
    nets = []
    for state in pool_states:
        net = PolicyValueNet(env_config, model_config).to(device)
        net.load_state_dict(state)
        net.eval()
        for p in net.parameters():
            p.requires_grad_(False)
        nets.append(net)
    return nets
```

- [ ] **Step 4: Wire pool management into `train_ppo`**

Replace the frozen-state line + collector construction + the loop's rollout block. After `frozen` is built and frozen, define the pool seed and hoist `frozen_state`:

```python
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr)
    history: List[dict] = []
    history_path = checkpoint_dir / HISTORY_FILENAME
    _write_history_atomic(history_path, history)

    frozen_state = {k: v.detach().cpu() for k, v in frozen.state_dict().items()}
    pool_states: List[dict] = [frozen_state]  # index 0 = anchor, always kept

    collector: Optional["ParallelRolloutCollector"] = None
    try:
        if config.num_workers > 1:
            from .parallel_rollouts import ParallelRolloutCollector
            collector = ParallelRolloutCollector(
                env_config, model_config, config, config.num_workers,
            )
            collector.start()

        for iteration in range(1, config.iterations + 1):
            iter_seed = base_seed + iteration * config.matches_per_iter

            # Grow the opponent pool with a snapshot of the current learner.
            if config.pool_max_size > 1 and iteration % config.pool_snapshot_interval == 0:
                pool_states.append({k: v.detach().cpu() for k, v in model.state_dict().items()})
                if len(pool_states) > config.pool_max_size:
                    pool_states.pop(1)  # evict oldest snapshot; keep anchor at index 0

            if collector is not None:
                learner_state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
                batch = collector.collect(learner_state, pool_states, iter_seed, config.matches_per_iter)
            elif config.pool_max_size > 1:
                opponents = build_opponent_nets(env_config, model_config, pool_states, device)
                batch = collect_rollouts(env_config, model, frozen, config, base_seed=iter_seed, opponents=opponents)
            else:
                batch = collect_rollouts(env_config, model, frozen, config, base_seed=iter_seed)

            advantages, returns = compute_gae(batch.rewards, batch.values, batch.dones, config.gamma, config.gae_lambda)
            metrics = ppo_update(model, optimizer, batch, advantages, returns, config)
            metrics["iteration"] = iteration
            metrics["mean_reward"] = float(np.sum(batch.rewards) / max(1.0, float(batch.dones.sum())))
            metrics["steps"] = len(batch)
            metrics["pool_size"] = len(pool_states)
```

(Leave the rest of the loop — eval block, checkpoint save, history write, print, `iteration_callback` — unchanged. Remove the old `frozen_state = {...}` line that previously lived inside the `if config.num_workers > 1` block, since it's now hoisted above.)

- [ ] **Step 5: Run tests**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -q`
Expected: PASS (new pool tests pass; existing sequential e2e tests pass — `pool_max_size` defaults to 1 so the `else` branch runs the unchanged single-anchor path).

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/tests/test_ppo.py
git commit -m "feat(ppo): train_ppo opponent pool (snapshot/evict) + build_opponent_nets

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Parallel collector ships the pool

**Files:**
- Modify: `ai/src/fh_mahjong_ai/parallel_rollouts.py`
- Test: `ai/tests/test_parallel_rollouts.py`

**Interfaces:**
- Produces:
  - `ParallelRolloutCollector(env_config, model_config, ppo_config, num_workers)` (no `frozen_state_dict`).
  - `collect(learner_state_dict, pool_states, base_seed, matches_per_iter) -> RolloutBatch`.
- Consumes: `collect_rollouts(..., opponents=)` and `build_opponent_nets` (Tasks 1-2).

- [ ] **Step 1: Update the existing tests + add the pool determinism test**

In `ai/tests/test_parallel_rollouts.py`:

(a) Update the collector constructor calls — drop the frozen state_dict, and pass `pool_states` to `collect`. Replace the three `ParallelRolloutCollector(env_cfg, mcfg, _cpu_state_dict(frozen), cfg, num_workers=...)` constructions with `ParallelRolloutCollector(env_cfg, mcfg, cfg, num_workers=...)`, and replace `collector.collect(_cpu_state_dict(learner), base_seed=900, matches_per_iter=4)` with `collector.collect(_cpu_state_dict(learner), [_cpu_state_dict(frozen)], base_seed=900, matches_per_iter=4)` (single-member pool = the frozen anchor). In `test_collector_propagates_worker_exception`, call `collector.collect(_cpu_state_dict(bad), [_cpu_state_dict(frozen)], base_seed=1, matches_per_iter=2)`.

(b) Add a parallel-with-pool determinism test:

```python
def test_parallel_with_pool_matches_sequential():
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = _small_model_cfg()
    learner = PolicyValueNet(env_cfg, mcfg)
    pool_nets = [PolicyValueNet(env_cfg, mcfg), PolicyValueNet(env_cfg, mcfg)]
    pool_states = [_cpu_state_dict(n) for n in pool_nets]
    cfg = PPOConfig(matches_per_iter=4, match_mode="classic", max_steps_per_episode=64, device="cpu")

    seq = collect_rollouts(env_cfg, learner, pool_nets[0], cfg, base_seed=1234, opponents=pool_nets)

    collector = ParallelRolloutCollector(env_cfg, mcfg, cfg, num_workers=2)
    collector.start()
    try:
        par = collector.collect(_cpu_state_dict(learner), pool_states, base_seed=1234, matches_per_iter=4)
    finally:
        collector.close()

    assert len(par) == len(seq)
    assert par.dones.sum() == seq.dones.sum() == 4.0
    np.testing.assert_allclose(np.sort(par.rewards), np.sort(seq.rewards), rtol=1e-5)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai pytest ai/tests/test_parallel_rollouts.py::test_parallel_with_pool_matches_sequential -q`
Expected: FAIL (`TypeError` on the new constructor/`collect` signatures).

- [ ] **Step 3: Update the collector + worker**

In `ai/src/fh_mahjong_ai/parallel_rollouts.py`:

Update the import line to include the helper:

```python
from .ppo import PPOConfig, RolloutBatch, build_opponent_nets, collect_rollouts, concat_rollout_batches
```

Rewrite `_worker_loop` to build opponents from the shipped pool:

```python
def _worker_loop(env_config, model_config, ppo_config, task_q, result_q):
    import torch

    from .model import PolicyValueNet

    torch.set_num_threads(1)
    learner = PolicyValueNet(env_config, model_config)

    while True:
        task = task_q.get()
        if task is None:
            return
        worker_id, learner_state_dict, pool_states, base_seed, matches = task
        try:
            learner.load_state_dict(learner_state_dict)
            opponents = build_opponent_nets(env_config, model_config, pool_states, device="cpu")
            cfg = replace(ppo_config, matches_per_iter=matches, device="cpu")
            batch = collect_rollouts(
                env_config, learner, opponents[0], cfg, base_seed=base_seed, opponents=opponents,
            )
            result_q.put((worker_id, batch, None))
        except Exception:  # noqa: BLE001 - report any worker failure to the parent
            result_q.put((worker_id, None, traceback.format_exc()))
```

Update `__init__` (drop `frozen_state_dict`):

```python
    def __init__(self, env_config: EnvConfig, model_config: ModelConfig,
                 ppo_config: PPOConfig, num_workers: int) -> None:
        if num_workers < 1:
            raise ValueError("num_workers must be >= 1")
        self.env_config = env_config
        self.model_config = model_config
        self.ppo_config = ppo_config
        self.num_workers = int(num_workers)
        self._ctx = mp.get_context("spawn")
        self._task_q = None
        self._result_q = None
        self._procs: List[mp.process.BaseProcess] = []
```

Update `start()` worker args (drop `self.frozen_state_dict`):

```python
            p = self._ctx.Process(
                target=_worker_loop,
                args=(self.env_config, self.model_config, self.ppo_config,
                      self._task_q, self._result_q),
                daemon=True,
            )
```

Update `collect` to take + ship `pool_states`:

```python
    def collect(self, learner_state_dict, pool_states, base_seed: int, matches_per_iter: int) -> RolloutBatch:
        counts = _split_counts(matches_per_iter, self.num_workers)
        offset = 0
        dispatched = 0
        for worker_id, count in enumerate(counts):
            if count == 0:
                continue
            self._task_q.put((worker_id, learner_state_dict, pool_states, int(base_seed + offset), int(count)))
            offset += count
            dispatched += 1
        # ... (rest of the gather loop unchanged)
```

(The gather/`close` logic below is unchanged.)

- [ ] **Step 4: Run the parallel suite**

Run: `uv run --project ai pytest ai/tests/test_parallel_rollouts.py -q`
Expected: PASS (all updated tests + the new pool determinism test).

- [ ] **Step 5: Run the PPO suite (parallel train path)**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -q`
Expected: PASS (the `num_workers>1` train_ppo tests now use the new collector signature).

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/parallel_rollouts.py ai/tests/test_parallel_rollouts.py
git commit -m "feat(ppo): parallel collector ships the opponent pool

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: CLI flags + MLflow pool_size

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/train_ppo.py`
- Test: `ai/tests/test_ppo.py`

**Interfaces:**
- Produces: `--pool-max-size` (default 1), `--pool-snapshot-interval` (default 10) on `fh-mj-train-ppo`; `pool_size` added to `_MLFLOW_METRIC_KEYS`.

- [ ] **Step 1: Write the failing test**

Add to `ai/tests/test_ppo.py`:

```python
def test_cli_train_ppo_pool_grows(tmp_path, monkeypatch):
    import json
    import sys
    from fh_mahjong_ai.scripts import train_ppo as cli

    env_cfg, mcfg = _small_env_model()
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    argv = [
        "fh-mj-train-ppo",
        "--init-checkpoint", str(init),
        "--checkpoint-dir", str(tmp_path / "ppo"),
        "--iterations", "3", "--matches-per-iter", "2", "--ppo-epochs", "1",
        "--minibatch-size", "8", "--match-mode", "classic", "--bridge-kind", "mock",
        "--max-steps-per-episode", "64", "--no-eval",
        "--pool-max-size", "3", "--pool-snapshot-interval", "1",
        "--model-channels", "8", "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    history = json.loads((tmp_path / "ppo" / "history.json").read_text())
    assert history[-1]["pool_size"] >= 2  # pool grew beyond the anchor
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_cli_train_ppo_pool_grows -q`
Expected: FAIL (`error: unrecognized arguments: --pool-max-size`).

- [ ] **Step 3: Add the CLI flags + MLflow key**

In `ai/src/fh_mahjong_ai/scripts/train_ppo.py`, add `pool_size` to the metric keys tuple:

```python
_MLFLOW_METRIC_KEYS = (
    "policy_loss", "value_loss", "entropy", "approx_kl", "clip_fraction",
    "mean_reward", "steps", "pool_size", "eval_mean_reward", "eval_mean_reward_ci95",
    "eval_large_loss_rate",
)
```

Add the arguments next to `--num-workers`:

```python
    parser.add_argument("--pool-max-size", type=int, default=1,
                        help="opponent pool size: anchor + past-self snapshots (1 = single anchor)")
    parser.add_argument("--pool-snapshot-interval", type=int, default=10,
                        help="add a learner snapshot to the opponent pool every N iterations")
```

Pass them into `PPOConfig(...)` (next to `num_workers=args.num_workers`):

```python
        max_steps_per_episode=args.max_steps_per_episode, num_workers=args.num_workers,
        pool_max_size=args.pool_max_size, pool_snapshot_interval=args.pool_snapshot_interval,
        device=args.device,
    )
```

- [ ] **Step 4: Run the test**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_cli_train_ppo_pool_grows -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/train_ppo.py ai/tests/test_ppo.py
git commit -m "feat(ppo): --pool-max-size / --pool-snapshot-interval CLI + mlflow pool_size

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Full-suite verification + docs

**Files:**
- Modify: `ai/AGENTS.md`

- [ ] **Step 1: Full PPO + parallel suites**

Run: `uv run --project ai pytest ai/tests/test_ppo.py ai/tests/test_parallel_rollouts.py -q`
Expected: PASS

- [ ] **Step 2: Full Python suite (no regressions)**

Run: `uv run --project ai pytest ai/tests/ -q`
Expected: PASS

- [ ] **Step 3: Update AGENTS.md**

In `ai/AGENTS.md`, document under the PPO section: `train_ppo` trains against an opponent pool (anchor + past-learner snapshots, `--pool-max-size` / `--pool-snapshot-interval`); `pool_max_size=1` is the single-anchor default; opponents are sampled per match/seat deterministically; the parallel collector ships the pool each iteration; `pool_size` is logged to MLflow.

- [ ] **Step 4: Commit**

```bash
git add ai/AGENTS.md
git commit -m "docs(ai): document PPO self-play opponent pool

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Post-Implementation: Tier 2 run

Launch the self-play run (after Tier 1's verdict) against the same anchor baseline:

```
fh-mj-train-ppo --init-checkpoint <anchor> --checkpoint-dir <run>/ckpt \
  --iterations 80 --matches-per-iter 256 --num-workers 16 --match-mode chongci \
  --device cuda --no-eval --base-seed <seed> \
  --pool-max-size 5 --pool-snapshot-interval 10 \
  --mlflow --mlflow-run-name tier2-selfplay-pool
```

Then eval milestone checkpoints with `fh-mj-evaluate --duplicate-seats --online-episodes 120 --start-seed 870000 --match-mode chongci --large-loss-threshold -1.0` and compare to the anchor baseline (`+0.0059 ± 0.0372`). The question it answers: does self-play clear the anchor where the single-anchor run plateaued at parity?

**Memory note:** `pool_max_size × model_size × num_workers` is the per-iteration opponent footprint; if the 31 GB box is tight, lower `--pool-max-size` or `--num-workers`, or implement the ship-on-change optimization from the spec.

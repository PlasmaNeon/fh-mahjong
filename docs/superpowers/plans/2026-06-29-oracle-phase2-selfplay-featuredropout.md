# Oracle Phase 2 — Self-Play Feature-Dropout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Train a deployable 39-channel agent that beats the heuristic anchor, by combining the Suphx perfect-info scaffold (anneal a dropout on the 12 oracle channels) with all-4 symmetric self-play.

**Architecture:** One 51ch `PolicyValueNet`, warm-started from the anchor (`build_oracle_model`), trained by symmetric self-play (all four seats = the current net, all four trajectories recorded) with a per-decision feature-dropout mask annealed δ: 0→1. The deployable artifact is a true 39ch net extracted by slicing the input conv. All work is Python in `ai/src/fh_mahjong_ai/`; the 51ch oracle observation already exists (Phase 1), so there are NO Go changes.

**Tech Stack:** Python/PyTorch, the merged PPO + oracle pipeline.

## Global Constraints

- Deployable artifact is a TRUE 39ch net (extracted), evaluated **non-oracle** vs the anchor — directly comparable to the anchor and every prior 39ch result.
- **Extract exact-equivalence:** the extracted 39ch student's policy logits on a 39ch obs equal the 51ch net's logits on that obs zero-padded to 51ch (atol 1e-5). Inverse of `build_oracle_model`.
- The PPO update runs on the SAME δ-masked observation the policy acted on — record the masked obs.
- Each seat's dense per-hand score delta is credited to THAT seat's last decision (so each seat's reward telescopes to its match net).
- Reuse `build_oracle_model`, the `ParallelOracleCollector` pattern, `compute_gae`/`ppo_update`, `fh-mj-evaluate`. No Go changes.
- Run `uv run --project ai pytest <files>` after each task.
- Anchor checkpoint (4090): `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt` (39ch). Anchor baseline `mean_placement -0.0528`.

**Existing signatures (in `ai/src/fh_mahjong_ai/oracle.py` / `ppo.py`) the tasks reuse:**
- `build_oracle_model(env_config, model_config, anchor_checkpoint, device="cpu") -> PolicyValueNet` (51ch)
- `collect_oracle_rollouts(env_config, model, config, base_seed) -> RolloutBatch`
- `ParallelOracleCollector(env_config, model_config, ppo_config, num_workers)` with `.start()`, `.collect(state_dict, base_seed, matches_per_iter)`, `.close()`
- from `ppo.py`: `RolloutBatch`, `PPOConfig`, `compute_gae`, `ppo_update`, `masked_policy_distribution`, `_obs_to_tensors`, `_seat_step_reward`, `LEARNING_SEAT (=0)`, `concat_rollout_batches`
- from `parallel_rollouts.py`: `_split_counts`
- `PolicyValueNet(env_config, model_config)`; input conv at `model.plane_stem[0].weight` shape `[C, plane_channels, 3, 3]`
- `EnvConfig(oracle_observation=True)` resolves `plane_shape=(51,42,1)`; default is `(39,42,1)`.

---

### Task 1: Feature-dropout schedule

**Files:**
- Modify: `ai/src/fh_mahjong_ai/oracle.py` (add `feature_dropout_schedule`)
- Test: `ai/tests/test_oracle_phase2.py` (new)

**Interfaces:**
- Produces: `feature_dropout_schedule(iteration: int, iterations: int, hold_start_frac: float = 0.2, ramp_frac: float = 0.6) -> float` — δ in [0,1]; 0 for the first `hold_start_frac` of iterations, linear ramp 0→1 over the next `ramp_frac`, 1 afterward. `iteration` is 1-based (matches the training loop's `for iteration in range(1, iterations+1)`).

- [ ] **Step 1: Write the failing test** `ai/tests/test_oracle_phase2.py`:

```python
import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.storage import save_checkpoint


def _mcfg():
    return ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)


def test_feature_dropout_schedule():
    from fh_mahjong_ai.oracle import feature_dropout_schedule
    T = 50
    vals = [feature_dropout_schedule(i, T) for i in range(1, T + 1)]
    assert vals[0] == 0.0                      # first iter: full perfect info
    assert vals[-1] == 1.0                     # last iter: fully masked
    assert all(0.0 <= v <= 1.0 for v in vals)  # probability
    assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:]))  # monotone nondecreasing
    # the first 20% hold at 0, the final 20% hold at 1
    assert feature_dropout_schedule(10, T) == 0.0   # iter 10 / 50 = 0.2 boundary still 0
    assert feature_dropout_schedule(45, T) == 1.0   # within the final-20% hold
```

- [ ] **Step 2: Run it to verify it fails.** `uv run --project ai pytest ai/tests/test_oracle_phase2.py::test_feature_dropout_schedule -q` → FAIL (`feature_dropout_schedule` not defined).

- [ ] **Step 3: Implement** in `ai/src/fh_mahjong_ai/oracle.py` (add after `build_oracle_model`):

```python
def feature_dropout_schedule(iteration: int, iterations: int,
                             hold_start_frac: float = 0.2, ramp_frac: float = 0.6) -> float:
    """Suphx feature-dropout probability delta for a 1-based `iteration` of
    `iterations`: 0 (full perfect info) for the first `hold_start_frac`, a linear
    ramp 0->1 over the next `ramp_frac`, then 1 (pure public-info student)."""
    if iterations <= 1:
        return 1.0
    frac = (iteration - 1) / (iterations - 1)  # 0..1 over the run
    if frac <= hold_start_frac:
        return 0.0
    if frac >= hold_start_frac + ramp_frac:
        return 1.0
    return float((frac - hold_start_frac) / ramp_frac)
```

- [ ] **Step 4: Run it to verify it passes.** Same command → PASS.

- [ ] **Step 5: Commit.**

```bash
git add ai/src/fh_mahjong_ai/oracle.py ai/tests/test_oracle_phase2.py
git commit -m "feat(oracle): feature_dropout_schedule (delta 0->1 anneal)"
```

---

### Task 2: Deployable-student extraction

**Files:**
- Modify: `ai/src/fh_mahjong_ai/oracle.py` (add `extract_deployable_student`)
- Test: `ai/tests/test_oracle_phase2.py`

**Interfaces:**
- Consumes: `build_oracle_model` (Task uses it in the test to make a 51ch net), `PolicyValueNet`, `EnvConfig`.
- Produces: `extract_deployable_student(oracle_model: PolicyValueNet, env_config_39ch: EnvConfig, model_config: ModelConfig) -> PolicyValueNet` — a 39ch net whose every tensor equals the 51ch net's except the input conv, which is the 51ch net's `plane_stem[0].weight[:, :39]`.

- [ ] **Step 1: Write the failing test** in `ai/tests/test_oracle_phase2.py`:

```python
def test_extract_deployable_student_exact_equivalence(tmp_path):
    from fh_mahjong_ai.oracle import build_oracle_model, extract_deployable_student
    mcfg = _mcfg()
    # a 51ch oracle warm-started from a random 39ch anchor (just need a 51ch net)
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))
    oracle = build_oracle_model(EnvConfig(oracle_observation=True), mcfg, anchor, device="cpu")
    # perturb the oracle's input-conv oracle channels so they are nonzero (training would)
    with torch.no_grad():
        oracle.plane_stem[0].weight[:, 39:] = torch.randn_like(oracle.plane_stem[0].weight[:, 39:])

    student = extract_deployable_student(oracle, EnvConfig(), mcfg).eval()
    oracle.eval()

    # student input conv == oracle input conv first 39 channels
    assert torch.allclose(student.plane_stem[0].weight, oracle.plane_stem[0].weight[:, :39])

    # student(39ch obs) logits == oracle(same obs zero-padded to 51ch) logits
    rng = np.random.default_rng(0)
    p39 = rng.standard_normal((1, 39, 42, 1)).astype(np.float32)
    p51 = np.concatenate([p39, np.zeros((1, 12, 42, 1), np.float32)], axis=1)
    sc = rng.standard_normal((1, 58)).astype(np.float32)
    mask = np.ones((1, 204), np.int8)
    with torch.no_grad():
        ls, _ = student(torch.from_numpy(p39), torch.from_numpy(sc), torch.from_numpy(mask))
        lo, _ = oracle(torch.from_numpy(p51), torch.from_numpy(sc), torch.from_numpy(mask))
    assert torch.allclose(ls, lo, atol=1e-5)
```

- [ ] **Step 2: Run it to verify it fails.** `uv run --project ai pytest ai/tests/test_oracle_phase2.py::test_extract_deployable_student_exact_equivalence -q` → FAIL (`extract_deployable_student` not defined).

- [ ] **Step 3: Implement** in `ai/src/fh_mahjong_ai/oracle.py`:

```python
def extract_deployable_student(oracle_model: PolicyValueNet, env_config_39ch: EnvConfig,
                               model_config: ModelConfig) -> PolicyValueNet:
    """Extract the deployable 39-channel policy from a trained 51-channel net. Copy
    every tensor except the first plane conv, and set the 39ch input conv to the
    51ch net's `plane_stem[0].weight[:, :39]`. By construction the student's output
    on a 39ch observation equals the 51ch net's output on that observation
    zero-padded to 51ch (the oracle channels contribute zero when their input is 0).
    Inverse of `build_oracle_model`."""
    oracle_w = oracle_model.plane_stem[0].weight  # [C, 51, 3, 3]
    in_ch = oracle_w.shape[1]
    if in_ch != 51:
        raise ValueError(f"expected a 51-channel oracle net, got input conv with {in_ch} channels")
    student = PolicyValueNet(env_config_39ch, model_config)
    src = oracle_model.state_dict()
    dst = student.state_dict()
    merged = dict(dst)
    for key, val in src.items():
        if key == "plane_stem.0.weight":
            continue  # shape mismatch [C,51,..] vs [C,39,..]; set explicitly below
        if key in dst and val.shape == dst[key].shape:
            merged[key] = val
    student.load_state_dict(merged)
    with torch.no_grad():
        student.plane_stem[0].weight.copy_(oracle_w[:, :39].to(student.plane_stem[0].weight.device))
    student.eval()
    return student
```

- [ ] **Step 4: Run it to verify it passes.** Same command → PASS.

- [ ] **Step 5: Commit.**

```bash
git add ai/src/fh_mahjong_ai/oracle.py ai/tests/test_oracle_phase2.py
git commit -m "feat(oracle): extract_deployable_student (51ch -> exact 39ch)"
```

---

### Task 3: Self-play rollout collector

**Files:**
- Modify: `ai/src/fh_mahjong_ai/oracle.py` (add `collect_selfplay_rollouts`)
- Test: `ai/tests/test_oracle_phase2.py`

**Interfaces:**
- Consumes: `EnvConfig`, `MahjongEnv`, `build_bridge`, `_obs_to_tensors`, `masked_policy_distribution`, `_seat_step_reward`, `RolloutBatch` (all already imported in `oracle.py`).
- Produces: `collect_selfplay_rollouts(env_config, model, config, base_seed, drop_prob) -> RolloutBatch` — all 4 seats are `model`; every decision is recorded (masked obs); per-seat dense score reward; `done=1` at each seat's final decision.

- [ ] **Step 1: Write the failing tests** in `ai/tests/test_oracle_phase2.py`:

```python
def test_collect_selfplay_records_all_seats_and_masks():
    from fh_mahjong_ai.oracle import collect_selfplay_rollouts
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    mcfg = _mcfg()
    model = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=2, match_mode="classic", max_steps_per_episode=64, device="cpu")

    # drop_prob=1.0 -> every recorded obs has the 12 oracle channels (39..50) zeroed
    masked = collect_selfplay_rollouts(env_cfg, model, cfg, base_seed=5, drop_prob=1.0)
    assert masked.planes.shape[1] == 51
    assert np.count_nonzero(masked.planes[:, 39:51, :, :]) == 0
    assert masked.dones.sum() >= 1

    # drop_prob=0.0 -> oracle channels carry the opponents' hands (nonzero somewhere)
    full = collect_selfplay_rollouts(env_cfg, model, cfg, base_seed=5, drop_prob=0.0)
    assert np.count_nonzero(full.planes[:, 39:51, :, :]) > 0


def test_collect_selfplay_credits_all_seats_at_match_end():
    # Self-play credits a terminal (done=1) to EACH seat's last decision, vs the
    # single-seat collector's one terminal per match. (On the mock bridge there is no
    # Go-side auto-play, so both record every decision; the robust difference is the
    # number of terminals, not the transition count.)
    from fh_mahjong_ai.oracle import collect_selfplay_rollouts, collect_oracle_rollouts
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    mcfg = _mcfg()
    model = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=2, match_mode="classic", max_steps_per_episode=64, device="cpu")
    sp = collect_selfplay_rollouts(env_cfg, model, cfg, base_seed=9, drop_prob=0.0)
    ss = collect_oracle_rollouts(env_cfg, model, cfg, base_seed=9)
    assert ss.dones.sum() == 2            # one terminal per match
    assert sp.dones.sum() > ss.dones.sum()  # multiple seats credited per match
```

- [ ] **Step 2: Run them to verify they fail.** `uv run --project ai pytest ai/tests/test_oracle_phase2.py -k selfplay -q` → FAIL (`collect_selfplay_rollouts` not defined).

- [ ] **Step 3: Implement** in `ai/src/fh_mahjong_ai/oracle.py` (after `collect_oracle_rollouts`):

```python
def collect_selfplay_rollouts(env_config: EnvConfig, model: PolicyValueNet,
                              config: PPOConfig, base_seed: int, drop_prob: float) -> RolloutBatch:
    """Symmetric self-play PPO rollouts: all four seats are the SAME `model`, each
    sampling on-policy; every seat's transitions are recorded. Feature-dropout: with
    probability `drop_prob`, the 12 oracle channels (planes 39..50) of the obs the
    model sees are zeroed AND the masked obs is recorded (so the PPO update matches
    what the policy acted on). Each seat's dense per-hand score delta is credited to
    that seat's last decision so its reward telescopes to its match net; `done=1` at
    each seat's final decision."""
    device = config.device
    cfg = EnvConfig(
        action_space_size=env_config.action_space_size,
        plane_shape=env_config.plane_shape,
        scalar_features=env_config.scalar_features,
        bridge_kind=env_config.bridge_kind,
        bridge_library_path=env_config.bridge_library_path,
        learning_seats=(0, 1, 2, 3),
        auto_play_heuristics=False,
        max_steps_per_episode=config.max_steps_per_episode,
        match_mode=config.match_mode,
        oracle_observation=env_config.oracle_observation,
    )
    bridge = build_bridge(cfg)
    env = MahjongEnv(cfg, bridge=bridge)
    model.eval()
    oracle_lo, oracle_hi = 39, 51  # oracle channels to mask
    planes_l, scalars_l, mask_l, actions_l = [], [], [], []
    logprobs_l, values_l, rewards_l, dones_l = [], [], [], []
    try:
        for m in range(config.matches_per_iter):
            obs = env.reset(seed=base_seed + m)
            torch.manual_seed(int(base_seed + m))
            mask_rng = np.random.default_rng(base_seed + m)  # seeded -> parallel == sequential
            reset_result = env.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                continue
            last_idx = [None, None, None, None]  # per-seat last recorded decision index
            while True:
                seat = int(obs.seat)
                planes_np = np.asarray(obs.planes, dtype=np.float32).copy()
                if planes_np.shape[0] >= oracle_hi and mask_rng.random() < drop_prob:
                    planes_np[oracle_lo:oracle_hi] = 0.0  # feature-dropout
                planes = torch.from_numpy(planes_np).unsqueeze(0).to(device)
                scalars = torch.from_numpy(np.asarray(obs.scalars, dtype=np.float32)).unsqueeze(0).to(device)
                amask = torch.from_numpy(np.asarray(obs.action_mask, dtype=np.int8)).unsqueeze(0).to(device)
                with torch.no_grad():
                    logits, value = model(planes, scalars, amask)
                    logits = logits / max(config.sample_temperature, 1e-6)
                    dist = masked_policy_distribution(logits)
                    action = int(dist.sample()[0].item())
                    logprob = float(dist.log_prob(torch.tensor([action], device=device))[0])
                    val = float(value[0].item())
                planes_l.append(planes_np)  # record the MASKED obs
                scalars_l.append(np.asarray(obs.scalars, dtype=np.float32))
                mask_l.append(np.asarray(obs.action_mask, dtype=np.int8))
                actions_l.append(action)
                logprobs_l.append(logprob)
                values_l.append(val)
                rewards_l.append(0.0)
                dones_l.append(0.0)
                last_idx[seat] = len(actions_l) - 1
                step = env.step(action)
                for k in range(4):
                    if last_idx[k] is not None:
                        rewards_l[last_idx[k]] += _seat_step_reward(step.rewards, k)
                if step.terminated or step.truncated:
                    for k in range(4):
                        if last_idx[k] is not None:
                            dones_l[last_idx[k]] = 1.0
                    break
                obs = step.observation
    finally:
        close = getattr(bridge, "close", None)
        if callable(close):
            close()
    if not actions_l:
        raise RuntimeError("collect_selfplay_rollouts produced no decisions")
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

- [ ] **Step 4: Run them to verify they pass.** `uv run --project ai pytest ai/tests/test_oracle_phase2.py -k selfplay -q` → PASS.

- [ ] **Step 5: Commit.**

```bash
git add ai/src/fh_mahjong_ai/oracle.py ai/tests/test_oracle_phase2.py
git commit -m "feat(oracle): collect_selfplay_rollouts (all-4 self-play + feature-dropout mask)"
```

---

### Task 4: Parallel self-play collector

**Files:**
- Modify: `ai/src/fh_mahjong_ai/oracle.py` (add `_selfplay_worker_loop` + `ParallelSelfplayCollector`)
- Test: `ai/tests/test_oracle_phase2.py`

**Interfaces:**
- Consumes: `collect_selfplay_rollouts` (Task 3), `_split_counts`, `concat_rollout_batches`, `mp`, `replace`, `traceback` (already imported in `oracle.py`).
- Produces: `ParallelSelfplayCollector(env_config, model_config, ppo_config, num_workers)` with `.start()`, `.collect(state_dict, base_seed, matches_per_iter, drop_prob) -> RolloutBatch`, `.close()`.

- [ ] **Step 1: Write the failing test** in `ai/tests/test_oracle_phase2.py`:

```python
def test_parallel_selfplay_matches_sequential():
    from fh_mahjong_ai.oracle import collect_selfplay_rollouts, ParallelSelfplayCollector
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    mcfg = _mcfg()
    model = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=4, match_mode="classic", max_steps_per_episode=64, device="cpu")
    seq = collect_selfplay_rollouts(env_cfg, model, cfg, base_seed=222, drop_prob=0.5)
    collector = ParallelSelfplayCollector(env_cfg, mcfg, cfg, num_workers=2)
    collector.start()
    try:
        state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
        par = collector.collect(state, base_seed=222, matches_per_iter=4, drop_prob=0.5)
    finally:
        collector.close()
    assert len(par) == len(seq)
    assert par.dones.sum() == seq.dones.sum()
    np.testing.assert_allclose(np.sort(par.rewards), np.sort(seq.rewards), rtol=1e-5)
```

- [ ] **Step 2: Run it to verify it fails.** `uv run --project ai pytest ai/tests/test_oracle_phase2.py::test_parallel_selfplay_matches_sequential -q` → FAIL (`ParallelSelfplayCollector` not defined).

- [ ] **Step 3: Implement** in `ai/src/fh_mahjong_ai/oracle.py` (after `ParallelOracleCollector`). This mirrors `ParallelOracleCollector` exactly, except the worker runs `collect_selfplay_rollouts` and the task tuple carries `drop_prob`:

```python
def _selfplay_worker_loop(env_config, model_config, ppo_config, task_q, result_q):
    import torch as _torch

    from .model import PolicyValueNet as _PVN

    _torch.set_num_threads(1)
    model = _PVN(env_config, model_config)
    while True:
        task = task_q.get()
        if task is None:
            return
        worker_id, state_dict, base_seed, matches, drop_prob = task
        try:
            model.load_state_dict(state_dict)
            cfg = replace(ppo_config, matches_per_iter=matches, device="cpu")
            batch = collect_selfplay_rollouts(env_config, model, cfg, base_seed=base_seed, drop_prob=drop_prob)
            result_q.put((worker_id, batch, None))
        except Exception:  # noqa: BLE001
            result_q.put((worker_id, None, traceback.format_exc()))


class ParallelSelfplayCollector:
    """Spawn-context worker pool for all-4 self-play feature-dropout rollouts,
    concatenated into one RolloutBatch. Mirrors ParallelOracleCollector; the task
    additionally carries the feature-dropout probability `drop_prob`."""

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
        self._procs = []

    def start(self) -> None:
        self._task_q = self._ctx.Queue()
        self._result_q = self._ctx.Queue()
        self._procs = []
        for _ in range(self.num_workers):
            p = self._ctx.Process(
                target=_selfplay_worker_loop,
                args=(self.env_config, self.model_config, self.ppo_config,
                      self._task_q, self._result_q),
                daemon=True,
            )
            p.start()
            self._procs.append(p)

    def collect(self, state_dict, base_seed: int, matches_per_iter: int, drop_prob: float) -> RolloutBatch:
        counts = _split_counts(matches_per_iter, self.num_workers)
        offset = 0
        dispatched = 0
        for worker_id, count in enumerate(counts):
            if count == 0:
                continue
            self._task_q.put((worker_id, state_dict, int(base_seed + offset), int(count), float(drop_prob)))
            offset += count
            dispatched += 1
        results: dict = {}
        received = 0
        while received < dispatched:
            try:
                worker_id, batch, err = self._result_q.get(timeout=30.0)
            except _queue.Empty:
                if any(p.exitcode is not None for p in self._procs):
                    self.close()
                    raise RuntimeError("a self-play rollout worker exited unexpectedly during collect")
                continue
            if err is not None:
                self.close()
                raise RuntimeError(f"self-play rollout worker {worker_id} failed:\n{err}")
            results[worker_id] = batch
            received += 1
        ordered = [results[w] for w in sorted(results)]
        return concat_rollout_batches(ordered)

    def close(self) -> None:
        if not self._procs:
            return
        for _ in self._procs:
            try:
                self._task_q.put(None)
            except Exception:  # noqa: BLE001
                pass
        for p in self._procs:
            p.join(timeout=10)
            if p.is_alive():
                p.terminate()
        self._procs = []
```

- [ ] **Step 4: Run it to verify it passes.** Same command → PASS.

- [ ] **Step 5: Commit.**

```bash
git add ai/src/fh_mahjong_ai/oracle.py ai/tests/test_oracle_phase2.py
git commit -m "feat(oracle): ParallelSelfplayCollector (parallel == sequential)"
```

---

### Task 5: Training loop + CLI

**Files:**
- Modify: `ai/src/fh_mahjong_ai/oracle.py` (add `train_selfplay_oracle`)
- Create: `ai/src/fh_mahjong_ai/scripts/train_selfplay_oracle.py`
- Modify: `ai/pyproject.toml` (`[project.scripts]`)
- Test: `ai/tests/test_oracle_phase2.py`

**Interfaces:**
- Consumes: `build_oracle_model`, `feature_dropout_schedule`, `collect_selfplay_rollouts`, `ParallelSelfplayCollector`, `compute_gae`, `ppo_update`, `save_checkpoint`, `json` (already imported in `oracle.py`); `PPOConfig.num_workers` (exists, default 1).
- Produces: `train_selfplay_oracle(env_config, model_config, anchor_checkpoint, checkpoint_dir, config, base_seed=0, run_eval=False) -> list[dict]`; CLI `fh-mj-train-selfplay-oracle`.

- [ ] **Step 1: Write the failing test** in `ai/tests/test_oracle_phase2.py`:

```python
def test_train_selfplay_oracle_runs_on_mock(tmp_path):
    from fh_mahjong_ai.oracle import train_selfplay_oracle
    mcfg = _mcfg()
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))   # 39ch anchor
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    cfg = PPOConfig(iterations=2, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    match_mode="classic", max_steps_per_episode=64, device="cpu")
    history = train_selfplay_oracle(env_config=env_cfg, model_config=mcfg, anchor_checkpoint=anchor,
                                    checkpoint_dir=tmp_path / "sp", config=cfg, base_seed=1, run_eval=False)
    assert len(history) == 2
    assert (tmp_path / "sp" / "iter_002.pt").exists()
    assert all("delta" in h for h in history)
    assert history[0]["delta"] == 0.0 and history[-1]["delta"] == 1.0
```

- [ ] **Step 2: Run it to verify it fails.** `uv run --project ai pytest ai/tests/test_oracle_phase2.py::test_train_selfplay_oracle_runs_on_mock -q` → FAIL (`train_selfplay_oracle` not defined).

- [ ] **Step 3: Implement `train_selfplay_oracle`** in `ai/src/fh_mahjong_ai/oracle.py`:

```python
def train_selfplay_oracle(env_config: EnvConfig, model_config: ModelConfig, anchor_checkpoint: Path,
                          checkpoint_dir: Path, config: PPOConfig, base_seed: int = 0,
                          run_eval: bool = False) -> list[dict]:
    """All-4 self-play feature-dropout training. Warm-start a 51ch net from the
    anchor; each iteration set delta from feature_dropout_schedule, collect self-play
    rollouts with that mask probability, then compute_gae + ppo_update. Saves the
    51ch checkpoint per iter (extract the deployable 39ch student post-hoc / at eval
    time)."""
    device = config.device
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    model = build_oracle_model(env_config, model_config, anchor_checkpoint, device)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr)
    history: list[dict] = []
    collector = None
    if getattr(config, "num_workers", 1) > 1:
        collector = ParallelSelfplayCollector(env_config, model_config, config, config.num_workers)
        collector.start()
    try:
        for iteration in range(1, config.iterations + 1):
            delta = feature_dropout_schedule(iteration, config.iterations)
            iter_seed = base_seed + iteration * config.matches_per_iter
            if collector is not None:
                state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
                batch = collector.collect(state, iter_seed, config.matches_per_iter, delta)
            else:
                batch = collect_selfplay_rollouts(env_config, model, config, base_seed=iter_seed, drop_prob=delta)
            advantages, returns = compute_gae(batch.rewards, batch.values, batch.dones,
                                              config.gamma, config.gae_lambda)
            metrics = ppo_update(model, optimizer, batch, advantages, returns, config)
            metrics["iteration"] = iteration
            metrics["delta"] = delta
            metrics["mean_reward"] = float(np.sum(batch.rewards) / max(1.0, float(batch.dones.sum())))
            metrics["steps"] = len(batch)
            save_checkpoint(checkpoint_dir / f"iter_{iteration:03d}.pt", model)
            history.append(metrics)
            (checkpoint_dir / "history.json").write_text(json.dumps(history))
            print(f"iter {iteration}: delta={delta:.3f} policy_loss={metrics['policy_loss']:.4f} "
                  f"value_loss={metrics['value_loss']:.4f} entropy={metrics['entropy']:.4f} "
                  f"mean_reward={metrics['mean_reward']:.4f}")
    finally:
        if collector is not None:
            collector.close()
    return history
```

- [ ] **Step 4: Run it to verify it passes.** Same command → PASS.

- [ ] **Step 5: Add the CLI** `ai/src/fh_mahjong_ai/scripts/train_selfplay_oracle.py` (mirror `scripts/train_oracle.py`):

```python
"""CLI for Phase-2 self-play feature-dropout oracle training."""
from __future__ import annotations
import argparse
from pathlib import Path
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.oracle import train_selfplay_oracle
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args


def main() -> None:
    p = argparse.ArgumentParser(description="Phase-2 self-play feature-dropout oracle training")
    p.add_argument("--anchor-checkpoint", type=Path, required=True, help="39ch anchor to warm-start from")
    p.add_argument("--checkpoint-dir", type=Path, required=True)
    p.add_argument("--iterations", type=int, default=50)
    p.add_argument("--matches-per-iter", type=int, default=256)
    p.add_argument("--num-workers", type=int, default=1,
                   help="parallel self-play rollout workers (1 = sequential)")
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--entropy-coef", type=float, default=0.0)
    p.add_argument("--ppo-epochs", type=int, default=2)
    p.add_argument("--minibatch-size", type=int, default=256)
    p.add_argument("--max-grad-norm", type=float, default=0.5)
    p.add_argument("--match-mode", choices=("classic", "chongci"), default="chongci")
    p.add_argument("--max-steps-per-episode", type=int, default=4000)
    p.add_argument("--bridge-kind", choices=("go", "mock"), default="go")
    p.add_argument("--bridge-lib", type=str, default=None)
    p.add_argument("--device", type=str, default="cpu")
    p.add_argument("--base-seed", type=int, default=0)
    add_model_config_args(p)
    args = p.parse_args()
    env_config = EnvConfig(bridge_kind=args.bridge_kind, bridge_library_path=args.bridge_lib,
                           match_mode=args.match_mode, max_steps_per_episode=args.max_steps_per_episode,
                           oracle_observation=True)
    config = PPOConfig(iterations=args.iterations, matches_per_iter=args.matches_per_iter,
                       gamma=args.gamma, lr=args.lr, entropy_coef=args.entropy_coef,
                       ppo_epochs=args.ppo_epochs, minibatch_size=args.minibatch_size,
                       max_grad_norm=args.max_grad_norm, match_mode=args.match_mode,
                       max_steps_per_episode=args.max_steps_per_episode, device=args.device,
                       num_workers=args.num_workers)
    train_selfplay_oracle(env_config=env_config, model_config=model_config_from_args(args),
                          anchor_checkpoint=args.anchor_checkpoint, checkpoint_dir=args.checkpoint_dir,
                          config=config, base_seed=args.base_seed, run_eval=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Register the CLI** in `ai/pyproject.toml` under `[project.scripts]` (next to `fh-mj-train-oracle`):

```toml
fh-mj-train-selfplay-oracle = "fh_mahjong_ai.scripts.train_selfplay_oracle:main"
```

- [ ] **Step 7: Run the test + CLI smoke.**

Run: `uv run --project ai pytest ai/tests/test_oracle_phase2.py -q` → all PASS
Run: `uv run --project ai fh-mj-train-selfplay-oracle --anchor-checkpoint /tmp/none 2>&1 | head` → prints a usage/error about the missing `--checkpoint-dir` or missing anchor file (confirms the entry point is registered).

- [ ] **Step 8: Commit.**

```bash
git add ai/src/fh_mahjong_ai/oracle.py ai/src/fh_mahjong_ai/scripts/train_selfplay_oracle.py ai/pyproject.toml ai/tests/test_oracle_phase2.py
git commit -m "feat(oracle): train_selfplay_oracle + fh-mj-train-selfplay-oracle CLI"
```

---

### Task 6: Deployable eval (`fh-mj-evaluate --from-oracle`)

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/evaluate.py`
- Test: `ai/tests/test_evaluate.py`

**Interfaces:**
- Consumes: `extract_deployable_student` (Task 2), `build_oracle_model`/`PolicyValueNet`, `EnvConfig`.
- Produces: a `--from-oracle` flag that loads a 51ch checkpoint, extracts the 39ch student, and evaluates it NON-oracle.

- [ ] **Step 1: Inspect** `ai/src/fh_mahjong_ai/scripts/evaluate.py`. At ~line 104 it builds `model = PolicyValueNet(EnvConfig(...), model_config)` then `load_checkpoint(args.checkpoint, model)`. For `--from-oracle`, instead: build a 51ch net (`PolicyValueNet(EnvConfig(oracle_observation=True), model_config)`), `load_checkpoint` the 51ch checkpoint into it, then `model = extract_deployable_student(oracle_net, EnvConfig(), model_config)`. The online eval must run NON-oracle (`oracle_observation=False`), which is the default eval path — do NOT pass `oracle_observation=True` here (that is Phase-1's `--oracle`).

- [ ] **Step 2: Write the failing test** in `ai/tests/test_evaluate.py`:

```python
def test_evaluate_cli_from_oracle_extracts_39ch(tmp_path, monkeypatch):
    import sys
    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.storage import save_checkpoint
    from fh_mahjong_ai.scripts import evaluate as ev
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    # a 51ch oracle-style checkpoint
    ckpt = tmp_path / "selfplay.pt"
    save_checkpoint(ckpt, PolicyValueNet(EnvConfig(oracle_observation=True), mcfg))
    argv = ["fh-mj-evaluate", "--checkpoint", str(ckpt), "--from-oracle",
            "--online-episodes", "1", "--match-mode", "classic",
            "--model-channels", "8", "--model-residual-blocks", "1",
            "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
            "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16", "--model-q-hidden-dim", "16",
            "--report-output", str(tmp_path / "rep.json")]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr("fh_mahjong_ai.evaluate.build_bridge",
                        lambda cfg: __import__("fh_mahjong_ai.bridge", fromlist=["MockMahjongBridge"]).MockMahjongBridge(cfg))
    ev.main()  # must not raise: a 39ch student runs in the non-oracle (39ch) eval
    assert (tmp_path / "rep.json").exists()
```

(Mirror the existing mock-bridge monkeypatch pattern already used by the `--oracle` test in this file; adjust the import line to match that test if it differs.)

- [ ] **Step 3: Run it to verify it fails.** `uv run --project ai pytest ai/tests/test_evaluate.py::test_evaluate_cli_from_oracle_extracts_39ch -q` → FAIL (`--from-oracle` unknown).

- [ ] **Step 4: Implement** in `scripts/evaluate.py`:
  1. Add `parser.add_argument("--from-oracle", action="store_true", help="checkpoint is a 51ch oracle/self-play net; extract the deployable 39ch student and eval non-oracle")`.
  2. Replace the model-build block so that when `args.from_oracle`:
     ```python
     from fh_mahjong_ai.oracle import extract_deployable_student
     oracle_net = PolicyValueNet(EnvConfig(oracle_observation=True), model_config)
     step = load_checkpoint(args.checkpoint, oracle_net)
     model = extract_deployable_student(oracle_net, EnvConfig(), model_config)
     ```
     else the existing `model = PolicyValueNet(EnvConfig(), model_config); step = load_checkpoint(...)`.
  3. Leave the online-eval call as the non-oracle default (do not set `oracle_observation`). `--from-oracle` and `--oracle` are mutually exclusive in meaning; if both are passed, prefer `--from-oracle` (it already yields a 39ch student) and ignore `--oracle`.

- [ ] **Step 5: Run it to verify it passes.** `uv run --project ai pytest ai/tests/test_evaluate.py::test_evaluate_cli_from_oracle_extracts_39ch -q` → PASS.

- [ ] **Step 6: Regression.** `uv run --project ai pytest ai/tests/test_evaluate.py -q` → PASS (existing eval paths unchanged).

- [ ] **Step 7: Commit.**

```bash
git add ai/src/fh_mahjong_ai/scripts/evaluate.py ai/tests/test_evaluate.py
git commit -m "feat(ai): fh-mj-evaluate --from-oracle (extract + eval deployable 39ch student)"
```

---

### Task 7: Train + gate runbook (no code; execute on the 4090)

**Files:** none (operational).

- [ ] **Step 1: Sync + train** (no Go rebuild — Python only):

```bash
# on wsl (4090)
cd /root/fh-mahjong && git fetch origin <branch-or-main> && git checkout <branch> && git pull
ANCHOR=/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
LIB=/root/fh-mahjong/build/libfh_mahjong_bridge.so
cd /root/fh-mahjong/ai
FH_MAHJONG_BRIDGE_LIB=$LIB uv run fh-mj-train-selfplay-oracle \
  --anchor-checkpoint "$ANCHOR" --checkpoint-dir /root/fh-mahjong-runs/oracle-phase2/ckpt \
  --iterations 50 --matches-per-iter 256 --num-workers 5 --match-mode chongci \
  --max-steps-per-episode 4000 --lr 2e-5 --entropy-coef 0 --ppo-epochs 2 --max-grad-norm 0.5 \
  --bridge-kind go --device cuda
```

- [ ] **Step 2: Eval the deployable student** at intervals (catch divergence) and at the end, paired vs the anchor baseline `-0.0528`:

```bash
FH_MAHJONG_BRIDGE_LIB=$LIB uv run fh-mj-evaluate \
  --checkpoint /root/fh-mahjong-runs/oracle-phase2/ckpt/iter_050.pt --from-oracle \
  --duplicate-seats --online-episodes 120 --start-seed 870000 --match-mode chongci \
  --chongci-max-hands 50 --max-steps-per-episode 4000 --large-loss-threshold -1.0 --device cuda \
  --report-output /root/fh-mahjong-runs/oracle-phase2/eval-iter050.json
```

- [ ] **Step 3: Verdict.** Compute the paired placement diff (deployable student vs anchor, identical seeds, per `paired_analysis.py`) for the late checkpoints. Since two non-stationarities stack, watch the δ-ramp region and the δ=1 tail; the deployable agent of interest is from the δ=1 tail. **PASS = the deployable 39ch student significantly beats the anchor on `mean_placement`.** If it diverges (placement collapses as δ→1), abort and consider the past-snapshot stability fallback (out of scope here).

---

## Notes for the implementer

- No Go rebuild is needed: the 51ch oracle observation already exists from Phase 1; this is all Python.
- The mock bridge sizes random planes from `config.plane_shape`, so `EnvConfig(oracle_observation=True)` (51ch) tests run without the Go binary.
- Determinism (parallel == sequential) relies on the per-match `mask_rng = np.random.default_rng(base_seed + m)` plus `torch.manual_seed(base_seed + m)`; keep both seeded per match.

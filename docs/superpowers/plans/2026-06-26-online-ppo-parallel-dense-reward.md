# Online PPO: Parallel Rollouts + Dense Per-Hand Reward — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the online PPO learner a dense per-hand reward and parallel rollout collection so a warm-started run can beat the frozen heuristic anchor under the CI gate.

**Architecture:** (1) The Go env emits a **per-decision running-score delta** as the step reward in Chongci mode — this telescopes exactly to the match net-change, so credit lands on the decision that caused each win/deal-in. (2) A Python `ParallelRolloutCollector` runs full self-play matches across a persistent `multiprocessing` (spawn) pool of CPU-inference workers, reusing the existing `collect_rollouts` as the per-worker unit; the main process concatenates the batches and does the PPO update on GPU.

**Tech Stack:** Go 1.25 (`rlenv` package, cgo bridge), Python 3 + PyTorch (`fh_mahjong_ai`), `uv` for env management, protobuf (NO proto change in this plan).

## Global Constraints

- **No proto change.** Reuse `EnvStepResponse.rewards` (already decoded by the Python bridge). Do not run protoc.
- **No regressions.** Classic match mode reward behavior must be byte-identical. Offline trajectory generation (`GenerateHeuristicTrajectory`) must keep `TerminalRewards` = match net-change. `core/game.go` must never import `rules/`.
- **`num_workers == 1` is the sequential path** and must be behavior-preserving: every existing `ai/tests/test_ppo.py` test passes unchanged.
- **Reward scale:** per-seat score delta / 1000.0 (same scale as the existing `roundRewards`/`matchEndRewards`).
- **Test commands:**
  - Go: `go test ./rlenv/ -run <TestName> -count=1`
  - Python: `uv run --project ai pytest ai/tests/<file>::<test> -q`
- **Commit message footer (every commit):**
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```
- **Branch:** `claude/ppo-parallel-dense-reward` (already checked out).

## File Structure

- `rlenv/env.go` — MODIFY: add `lastScores` field; add `snapshotScores`, `scoreDelta`, `scoreDeltaReward` helpers; rewrite `advanceToDecision` reward returns; snapshot scores in `Reset`; preserve match-net in `GenerateHeuristicTrajectory`.
- `rlenv/env_test.go` — MODIFY: add dense-reward + reconciliation tests and offline-preservation test.
- `ai/src/fh_mahjong_ai/evaluate.py` — MODIFY: add `episode_reward_vector` helper; sum per-step rewards per episode.
- `ai/src/fh_mahjong_ai/ppo.py` — MODIFY: per-match reproducible seeding in `collect_rollouts`; add `concat_rollout_batches`; add `num_workers` to `PPOConfig`; wire parallel path into `train_ppo`.
- `ai/src/fh_mahjong_ai/parallel_rollouts.py` — CREATE: `ParallelRolloutCollector`, `_split_counts`, `_worker_loop`.
- `ai/src/fh_mahjong_ai/scripts/train_ppo.py` — MODIFY: add `--num-workers` CLI flag.
- `ai/tests/test_ppo.py` — MODIFY: eval-sum helper test, seeding/concat tests, train_ppo num_workers e2e, CLI flag.
- `ai/tests/test_parallel_rollouts.py` — CREATE: parallel collector tests.

---

## Task 1: Dense per-hand reward in the Go env (score-delta)

**Files:**
- Modify: `rlenv/env.go` (struct `Env` ~line 13; `Reset` ~line 31; `advanceToDecision` ~line 317; helpers near `roundRewards` ~line 590)
- Test: `rlenv/env_test.go`

**Interfaces:**
- Produces: Chongci `EnvStepResponse.rewards` = per-seat running-score delta since the previous decision (`Players[i].Score` delta / 1000). Classic unchanged. Sum of all step rewards over a match == `matchEndRewards` (net-change). Reset reward = zeros.
- Consumes: existing `roundRewards`, `matchEndRewards`, `emptyObservation`, `roundOutcome`, `e.game.State.Players[i].Score`.

- [ ] **Step 1: Write the failing test**

Add to `rlenv/env_test.go` (package `rlenv`, so it can read `e.game` and call unexported funcs). Also add `"math"` to the test imports if not present.

```go
func TestChongciStepEmitsDensePerHandReward(t *testing.T) {
	env := New(&pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       8192,
		MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig:      &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 3},
	})
	reset, err := env.Reset(&pb.EnvResetRequest{Seed: 12345, Config: env.config})
	if err != nil {
		t.Fatalf("reset: %v", err)
	}

	sum := make([]float32, 4)
	for i, r := range reset.Rewards {
		sum[i] += r
	}

	sawNonZeroIntermediate := false
	obs := reset.Observation
	terminated := reset.Terminated
	truncated := reset.Truncated
	for !terminated && !truncated {
		seat := obs.Seat
		action := env.heuristic.ChooseAction(env.game.State, seat)
		if action == nil {
			t.Fatalf("nil heuristic action for seat %d", seat)
		}
		actionID, ok := encodeAction(env.game.State, seat, action)
		if !ok {
			t.Fatalf("cannot encode action for seat %d", seat)
		}
		step, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(actionID)})
		if err != nil {
			t.Fatalf("step: %v", err)
		}
		nonZero := false
		for i, r := range step.Rewards {
			sum[i] += r
			if r != 0 {
				nonZero = true
			}
		}
		if !step.Terminated && !step.Truncated && nonZero {
			sawNonZeroIntermediate = true
		}
		obs = step.Observation
		terminated = step.Terminated
		truncated = step.Truncated
	}

	if truncated {
		t.Fatalf("3-hand chongci match should terminate, not truncate")
	}
	if !sawNonZeroIntermediate {
		t.Fatalf("expected at least one non-zero intermediate per-hand reward")
	}

	net := matchEndRewards(env.game.State)
	for i := range sum {
		if math.Abs(float64(sum[i]-net[i])) > 1e-4 {
			t.Fatalf("seat %d: sum of per-step rewards %.6f != match net %.6f", i, sum[i], net[i])
		}
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `go test ./rlenv/ -run TestChongciStepEmitsDensePerHandReward -count=1`
Expected: FAIL — today intermediate rewards are all zero (so `sawNonZeroIntermediate` is false) and the sum reconciliation fails because the terminal step returns `matchEndRewards` while intermediates are zero.

- [ ] **Step 3: Write minimal implementation**

In `rlenv/env.go`, add the `lastScores` field to the `Env` struct:

```go
type Env struct {
	config        *pb.EnvConfig
	game          *core.Game
	heuristic     bot.Policy
	learningSeats map[uint32]bool
	decisionCount uint64
	baseSeed      uint64
	lastScores    []int32
}
```

Add helpers near `roundRewards` (anywhere in the file):

```go
func snapshotScores(state *pb.GameState) []int32 {
	scores := make([]int32, 4)
	if state == nil {
		return scores
	}
	for i := 0; i < 4 && i < len(state.Players); i++ {
		if state.Players[i] != nil {
			scores[i] = state.Players[i].Score
		}
	}
	return scores
}

func scoreDelta(cur, prev []int32) []float32 {
	delta := make([]float32, 4)
	for i := range delta {
		c, p := int32(0), int32(0)
		if i < len(cur) {
			c = cur[i]
		}
		if i < len(prev) {
			p = prev[i]
		}
		delta[i] = float32(c-p) / 1000.0
	}
	return delta
}

// scoreDeltaReward returns the per-seat running-score change since the previous
// decision and advances the snapshot. For classic mode (Score stays 0) this is
// always zeros; for Chongci it is the dense per-hand reward and telescopes to the
// match net-change.
func (e *Env) scoreDeltaReward() []float32 {
	cur := snapshotScores(e.game.State)
	delta := scoreDelta(cur, e.lastScores)
	e.lastScores = cur
	return delta
}
```

In `Reset`, snapshot scores right after `e.game.Start()` and before `advanceToDecision`:

```go
	if err := e.game.Start(); err != nil {
		return nil, err
	}
	e.lastScores = snapshotScores(e.game.State)
	stepResponse, err := e.advanceToDecision()
```

Rewrite the reward returns in `advanceToDecision` to use `e.scoreDeltaReward()` for the Chongci-reachable paths (MATCH_END, MaxDecisions truncation, learning-seat decision). Leave the **classic** round-end path returning `roundRewards` unchanged:

```go
func (e *Env) advanceToDecision() (*pb.EnvStepResponse, error) {
	for {
		if e.game.State.Phase == pb.GamePhase_PHASE_MATCH_END {
			return &pb.EnvStepResponse{
				Observation: emptyObservation(e.game.State, e.decisionCount),
				Rewards:     e.scoreDeltaReward(),
				Terminated:  true,
			}, nil
		}

		if e.game.State.Phase == pb.GamePhase_PHASE_ROUND_END {
			if e.game.State.MatchMode == pb.MatchMode_MATCH_MODE_CHONGCI {
				if err := e.readyAllPlayersForNextRound(); err != nil {
					return nil, err
				}
				continue
			}
			return &pb.EnvStepResponse{
				Observation:  emptyObservation(e.game.State, e.decisionCount),
				Rewards:      roundRewards(e.game.State),
				Terminated:   true,
				RoundOutcome: roundOutcome(e.game.State),
			}, nil
		}

		if e.config.MaxDecisions > 0 && e.decisionCount >= uint64(e.config.MaxDecisions) {
			return &pb.EnvStepResponse{
				Observation: emptyObservation(e.game.State, e.decisionCount),
				Rewards:     e.scoreDeltaReward(),
				Truncated:   true,
			}, nil
		}

		if seat, ok := e.currentLearningSeat(); ok {
			observation, err := encodeObservation(e.game.State, seat, e.decisionCount)
			if err != nil {
				return nil, err
			}
			return &pb.EnvStepResponse{
				Observation: observation,
				Rewards:     e.scoreDeltaReward(),
			}, nil
		}

		if e.config.AutoPlayHeuristics {
			if seat, ok := e.currentHeuristicSeat(); ok {
				action := e.heuristic.ChooseAction(e.game.State, seat)
				if action == nil {
					return nil, fmt.Errorf("heuristic returned nil action for seat %d", seat)
				}
				e.decisionCount++
				if err := e.game.ProcessPlayerAction(seat, action); err != nil {
					return nil, err
				}
				continue
			}
		}

		if e.game.State.Phase == pb.GamePhase_PHASE_WAIT_DISCARDS {
			if err := e.assertInterruptsReadyToResolve(); err != nil {
				return nil, err
			}
			e.game.ResolveInterrupts()
			continue
		}

		if !e.config.AutoPlayHeuristics {
			return nil, fmt.Errorf("non-learning seat is waiting for input while auto heuristics are disabled: %s", e.decisionStateSummary())
		}

		return nil, fmt.Errorf("no actionable seat found: %s", e.decisionStateSummary())
	}
}
```

Note: the classic round-end return is unchanged (`roundRewards` + `RoundOutcome`); classic `Score` stays 0 so `scoreDeltaReward` would be zeros there anyway, and classic terminates at the first round-end.

- [ ] **Step 4: Run test to verify it passes**

Run: `go test ./rlenv/ -run TestChongciStepEmitsDensePerHandReward -count=1`
Expected: PASS

- [ ] **Step 5: Run the full rlenv suite to check for regressions**

Run: `go test ./rlenv/ -count=1`
Expected: PASS (all existing tests, including `TestGenerateHeuristicTrajectoryDeterministic` which asserts classic intermediate rewards are `{0,0,0,0}` — unchanged because classic `Score` stays 0).

- [ ] **Step 6: Commit**

```bash
git add rlenv/env.go rlenv/env_test.go
git commit -m "feat(rlenv): dense per-hand reward via running-score delta (chongci)

advanceToDecision now returns the per-seat Score delta since the previous
decision as the step reward in Chongci mode; it telescopes exactly to the
match net-change. Classic mode is unchanged (Score stays 0; round-end still
returns roundRewards).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Preserve offline match-net TerminalRewards

**Files:**
- Modify: `rlenv/env.go` — `GenerateHeuristicTrajectory` (~line 231; the post-loop `TerminalRewards` assignment ~line 305)
- Test: `rlenv/env_test.go`

**Interfaces:**
- Produces: for Chongci trajectories, every `TrajectorySample.TerminalRewards` == `matchEndRewards(finalState)` (match net-change), regardless of the now-dense per-step `Rewards`. Classic unchanged.
- Consumes: `matchEndRewards`, `env.game.State`.

**Why:** the offline pipeline derives returns from `terminal_rewards` (`data.placement_shaped_returns`, `backfill_returns`). With dense rewards the final step now carries only the last segment's delta, so we must source terminal rewards from the match net explicitly to avoid an offline regression.

- [ ] **Step 1: Write the failing test**

Add to `rlenv/env_test.go`:

```go
func TestGenerateHeuristicTrajectoryChongciTerminalRewardsAreMatchNet(t *testing.T) {
	env := New(nil)
	dataset, err := env.GenerateHeuristicTrajectory(&pb.TrajectoryRequest{
		Episodes:  1,
		StartSeed: 777,
		Config: &pb.EnvConfig{
			LearningSeats:      []uint32{0, 1, 2, 3},
			AutoPlayHeuristics: false,
			MaxDecisions:       8192,
			MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
			ChongciConfig:      &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 3},
		},
	})
	if err != nil {
		t.Fatalf("generate: %v", err)
	}
	if len(dataset.Samples) == 0 {
		t.Fatalf("expected samples")
	}

	// Terminal rewards must sum to ~0 across seats (zero-sum net-change) and be
	// consistent across all samples — the signature of match-net, not a single
	// hand's per-seat delta.
	terminal := dataset.Samples[len(dataset.Samples)-1].TerminalRewards
	if len(terminal) != 4 {
		t.Fatalf("expected 4 terminal rewards, got %v", terminal)
	}
	var total float32
	for _, r := range terminal {
		total += r
	}
	if math.Abs(float64(total)) > 1e-3 {
		t.Fatalf("chongci net-change terminal rewards should sum to ~0, got %v (sum %.6f)", terminal, total)
	}
	for _, s := range dataset.Samples {
		if !almostEqualSlices(s.TerminalRewards, terminal) {
			t.Fatalf("all samples must share the match-net terminal rewards; got %v vs %v", s.TerminalRewards, terminal)
		}
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `go test ./rlenv/ -run TestGenerateHeuristicTrajectoryChongciTerminalRewardsAreMatchNet -count=1`
Expected: FAIL — with dense rewards, `finalRewards` (= last step's delta) is a single segment, not the zero-sum match net, so the sum-to-zero assertion fails.

- [ ] **Step 3: Write minimal implementation**

In `GenerateHeuristicTrajectory`, after the per-episode rollout loop and before the `for _, sample := range episodeSamples` block, override `finalRewards` with the match net for Chongci:

```go
		// Dense per-step rewards now flow through Step; terminal rewards used by
		// the offline pipeline must remain the match net-change.
		if env.game.State.MatchMode == pb.MatchMode_MATCH_MODE_CHONGCI &&
			env.game.State.Phase == pb.GamePhase_PHASE_MATCH_END {
			finalRewards = matchEndRewards(env.game.State)
		}

		for _, sample := range episodeSamples {
			sample.TerminalRewards = append([]float32(nil), finalRewards...)
```

(The existing `for _, sample := range episodeSamples` loop body stays as-is.)

- [ ] **Step 4: Run test to verify it passes**

Run: `go test ./rlenv/ -run TestGenerateHeuristicTrajectoryChongciTerminalRewardsAreMatchNet -count=1`
Expected: PASS

- [ ] **Step 5: Run the full rlenv suite**

Run: `go test ./rlenv/ -count=1`
Expected: PASS (including the existing classic and Chongci trajectory tests).

- [ ] **Step 6: Commit**

```bash
git add rlenv/env.go rlenv/env_test.go
git commit -m "fix(rlenv): keep offline TerminalRewards = match net after dense reward

GenerateHeuristicTrajectory now sources Chongci terminal rewards from
matchEndRewards so the offline pipeline's return shaping is unchanged, even
though per-step Rewards are now dense.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Eval sums per-step rewards per episode

**Files:**
- Modify: `ai/src/fh_mahjong_ai/evaluate.py` (add module-level helper; use it in the `record_episode` closure at ~line 459-468)
- Test: `ai/tests/test_ppo.py`

**Interfaces:**
- Produces: `episode_reward_vector(episode, fallback_rewards, num_seats=4) -> np.ndarray` — total per-seat reward summed over an episode's transitions; falls back to `fallback_rewards` when the episode has no transitions (reset-terminated).
- Consumes: `Transition.rewards` (already collected into the `episode` list during eval).

**Why:** dense per-step rewards mean the terminal step no longer carries the whole-match net; eval must sum the per-step rewards to recover the match outcome. For classic and old-sparse Chongci this equals the previous terminal reward, so eval numbers stay comparable.

- [ ] **Step 1: Write the failing test**

Add to `ai/tests/test_ppo.py`:

```python
from fh_mahjong_ai.evaluate import episode_reward_vector
from fh_mahjong_ai.types import Observation, Transition


def _dummy_transition(rewards):
    obs = Observation(seat=0, planes=np.zeros((1, 1, 1), dtype=np.float32),
                      scalars=np.zeros(1, dtype=np.float32),
                      action_mask=np.ones(1, dtype=np.int8), metadata={})
    return Transition(observation=obs, action_id=0,
                      rewards=np.asarray(rewards, dtype=np.float32),
                      next_observation=obs, terminated=False, truncated=False, info={})


def test_episode_reward_vector_sums_per_step_rewards():
    episode = [
        _dummy_transition([0.0, 0.0, 0.0, 0.0]),
        _dummy_transition([1.5, -0.5, 0.0, -1.0]),
        _dummy_transition([0.5, 0.0, -0.5, 0.0]),
    ]
    total = episode_reward_vector(episode, fallback_rewards=np.zeros(4, dtype=np.float32))
    np.testing.assert_allclose(total, [2.0, -0.5, -0.5, -1.0], rtol=1e-6)


def test_episode_reward_vector_empty_uses_fallback():
    total = episode_reward_vector([], fallback_rewards=np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32))
    np.testing.assert_allclose(total, [0.1, 0.2, 0.3, 0.4], rtol=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_episode_reward_vector_sums_per_step_rewards -q`
Expected: FAIL with `ImportError: cannot import name 'episode_reward_vector'`.

- [ ] **Step 3: Write minimal implementation**

Add the helper near the top of `ai/src/fh_mahjong_ai/evaluate.py` (after imports):

```python
def episode_reward_vector(episode, fallback_rewards, num_seats: int = 4) -> np.ndarray:
    """Total per-seat reward summed over an episode's transitions. With dense
    per-step rewards this recovers the match outcome; with sparse terminal-only
    rewards it equals the terminal reward. Empty episodes (reset-terminated) fall
    back to the provided terminal rewards."""
    if not episode:
        return np.asarray(fallback_rewards, dtype=np.float32)
    total = np.zeros(num_seats, dtype=np.float32)
    for t in episode:
        r = np.asarray(t.rewards, dtype=np.float32)
        n = min(num_seats, r.shape[-1]) if r.ndim >= 1 else 0
        total[:n] += r[:n]
    return total
```

Then change `record_episode` to use the summed vector. Replace:

```python
        reward = float(rewards[learning_seat])
```

with:

```python
        reward = float(episode_reward_vector(episode, rewards)[learning_seat])
```

(`record_episode` already receives both `rewards` — the terminal/fallback vector — and `episode` — the list of transitions.)

- [ ] **Step 4: Run the helper tests**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_episode_reward_vector_sums_per_step_rewards ai/tests/test_ppo.py::test_episode_reward_vector_empty_uses_fallback -q`
Expected: PASS

- [ ] **Step 5: Run the eval test suite for regressions**

Run: `uv run --project ai pytest ai/tests/test_evaluate.py -q`
Expected: PASS (classic/mock eval reward equals terminal reward because intermediate rewards are zero — summing is a no-op there). If `ai/tests/test_evaluate.py` does not exist, run `uv run --project ai pytest ai/tests/ -k evaluate -q` instead.

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/evaluate.py ai/tests/test_ppo.py
git commit -m "feat(eval): sum per-step rewards per episode for dense reward

episode_reward_vector recovers the match outcome from dense per-step rewards;
equals the terminal reward when rewards are sparse, so classic/old eval numbers
are unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Reproducible per-match seeding + batch concatenation

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (`collect_rollouts` ~line 199; add `concat_rollout_batches` near `RolloutBatch`)
- Test: `ai/tests/test_ppo.py`

**Interfaces:**
- Produces:
  - `collect_rollouts` becomes reproducible: identical `(env_config, model weights, config, base_seed)` → identical `RolloutBatch` (per-match `torch.manual_seed`).
  - `concat_rollout_batches(batches: list[RolloutBatch]) -> RolloutBatch` — concatenates along axis 0, skipping empty batches, raising if all empty.
- Consumes: `RolloutBatch`, `np.concatenate`.

- [ ] **Step 1: Write the failing test**

Add to `ai/tests/test_ppo.py`:

```python
from fh_mahjong_ai.ppo import concat_rollout_batches


def test_collect_rollouts_is_reproducible_with_same_seed():
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    learner = PolicyValueNet(env_cfg, mcfg)
    frozen = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=3, match_mode="classic", max_steps_per_episode=64, device="cpu")
    a = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=4242)
    b = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=4242)
    assert len(a) == len(b)
    np.testing.assert_allclose(a.rewards, b.rewards, rtol=1e-6)
    np.testing.assert_array_equal(a.actions, b.actions)


def test_concat_rollout_batches_preserves_rows_and_dones():
    env = EnvConfig(action_space_size=4, plane_shape=(2, 3, 1), scalar_features=4)
    b1 = _synthetic_batch(env, n=5)
    b2 = _synthetic_batch(env, n=7)
    b1.dones[-1] = 1.0
    b2.dones[-1] = 1.0
    merged = concat_rollout_batches([b1, b2])
    assert len(merged) == 12
    assert merged.planes.shape == (12, *env.plane_shape)
    assert merged.dones.sum() == 2.0


def test_concat_rollout_batches_raises_when_all_empty():
    with pytest.raises(RuntimeError):
        concat_rollout_batches([])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_concat_rollout_batches_preserves_rows_and_dones -q`
Expected: FAIL with `ImportError: cannot import name 'concat_rollout_batches'`.

- [ ] **Step 3: Write minimal implementation**

In `ai/src/fh_mahjong_ai/ppo.py`, add `concat_rollout_batches` after the `RolloutBatch` dataclass:

```python
def concat_rollout_batches(batches: List["RolloutBatch"]) -> "RolloutBatch":
    """Concatenate per-worker rollout batches into one flat batch. Empty batches
    are skipped; raises if there is nothing to concatenate. Each match is
    self-contained (dones=1 at its final step), so GAE over the concatenation is
    correct without any boundary fix-up."""
    nonempty = [b for b in batches if len(b) > 0]
    if not nonempty:
        raise RuntimeError("concat_rollout_batches: no rollout data")
    return RolloutBatch(
        planes=np.concatenate([b.planes for b in nonempty], axis=0),
        scalars=np.concatenate([b.scalars for b in nonempty], axis=0),
        action_mask=np.concatenate([b.action_mask for b in nonempty], axis=0),
        actions=np.concatenate([b.actions for b in nonempty], axis=0),
        old_logprobs=np.concatenate([b.old_logprobs for b in nonempty], axis=0),
        values=np.concatenate([b.values for b in nonempty], axis=0),
        rewards=np.concatenate([b.rewards for b in nonempty], axis=0),
        dones=np.concatenate([b.dones for b in nonempty], axis=0),
    )
```

In `collect_rollouts`, seed torch per match for reproducibility. Change the loop body start:

```python
        for m in range(config.matches_per_iter):
            obs = env.reset(seed=base_seed + m)
            torch.manual_seed(int(base_seed + m))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_collect_rollouts_is_reproducible_with_same_seed ai/tests/test_ppo.py::test_concat_rollout_batches_preserves_rows_and_dones ai/tests/test_ppo.py::test_concat_rollout_batches_raises_when_all_empty -q`
Expected: PASS

- [ ] **Step 5: Run the full PPO suite for regressions**

Run: `uv run --project ai pytest ai/tests/test_ppo.py -q`
Expected: PASS (existing tests unaffected; seeding does not change shapes/dones).

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/tests/test_ppo.py
git commit -m "feat(ppo): reproducible per-match seeding + concat_rollout_batches

collect_rollouts now seeds torch per match (reproducible rollouts), and
concat_rollout_batches merges per-worker batches for parallel collection.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: ParallelRolloutCollector

**Files:**
- Create: `ai/src/fh_mahjong_ai/parallel_rollouts.py`
- Test: `ai/tests/test_parallel_rollouts.py`

**Interfaces:**
- Produces:
  - `_split_counts(total: int, workers: int) -> list[int]` — even split with remainder on the first workers (e.g. `_split_counts(5, 2) == [3, 2]`).
  - `ParallelRolloutCollector(env_config, model_config, frozen_state_dict, ppo_config, num_workers)` with `start()`, `collect(learner_state_dict, base_seed, matches_per_iter) -> RolloutBatch`, `close()`.
- Consumes: `collect_rollouts`, `concat_rollout_batches` (Task 4), `PolicyValueNet`, `PPOConfig`.

**Design:** persistent spawn-context workers. Each worker builds its bridge + learner/frozen nets once, sets `torch.set_num_threads(1)`, then loops on a task queue. Per iteration the collector partitions `matches_per_iter` into contiguous disjoint seed blocks (so the union of seeds equals the sequential run's seeds), broadcasts the learner `state_dict`, and concatenates the returned batches in worker order. Worker exceptions propagate as `RuntimeError` and shut the pool down.

- [ ] **Step 1: Write the failing test**

Create `ai/tests/test_parallel_rollouts.py`:

```python
from __future__ import annotations

import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig, collect_rollouts
from fh_mahjong_ai.parallel_rollouts import ParallelRolloutCollector, _split_counts


def test_split_counts_even_and_remainder():
    assert _split_counts(8, 4) == [2, 2, 2, 2]
    assert _split_counts(5, 2) == [3, 2]
    assert _split_counts(2, 4) == [1, 1, 0, 0]


def _small_model_cfg():
    return ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)


def _cpu_state_dict(model):
    return {k: v.detach().cpu() for k, v in model.state_dict().items()}


def test_parallel_matches_sequential_rewards():
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = _small_model_cfg()
    learner = PolicyValueNet(env_cfg, mcfg)
    frozen = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=4, match_mode="classic", max_steps_per_episode=64, device="cpu")

    seq = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=900)

    collector = ParallelRolloutCollector(env_cfg, mcfg, _cpu_state_dict(frozen), cfg, num_workers=2)
    collector.start()
    try:
        par = collector.collect(_cpu_state_dict(learner), base_seed=900, matches_per_iter=4)
    finally:
        collector.close()

    assert len(par) == len(seq)
    assert par.dones.sum() == seq.dones.sum() == 4.0
    np.testing.assert_allclose(np.sort(par.rewards), np.sort(seq.rewards), rtol=1e-5)


def test_collector_propagates_worker_exception():
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = _small_model_cfg()
    frozen = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=2, match_mode="classic", max_steps_per_episode=64, device="cpu")

    collector = ParallelRolloutCollector(env_cfg, mcfg, _cpu_state_dict(frozen), cfg, num_workers=1)
    collector.start()
    try:
        # A state_dict from an incompatible model shape makes load_state_dict raise in the worker.
        bad = PolicyValueNet(EnvConfig(action_space_size=8, plane_shape=(2, 3, 1), scalar_features=4),
                             _small_model_cfg())
        with pytest.raises(RuntimeError):
            collector.collect(_cpu_state_dict(bad), base_seed=1, matches_per_iter=2)
    finally:
        collector.close()


def test_collector_close_joins_workers():
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = _small_model_cfg()
    frozen = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=2, match_mode="classic", max_steps_per_episode=64, device="cpu")
    collector = ParallelRolloutCollector(env_cfg, mcfg, _cpu_state_dict(frozen), cfg, num_workers=2)
    collector.start()
    collector.close()
    assert all(not p.is_alive() for p in collector._procs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_parallel_rollouts.py::test_split_counts_even_and_remainder -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fh_mahjong_ai.parallel_rollouts'`.

- [ ] **Step 3: Write minimal implementation**

Create `ai/src/fh_mahjong_ai/parallel_rollouts.py`:

```python
from __future__ import annotations

import multiprocessing as mp
import traceback
from dataclasses import replace
from typing import Dict, List, Optional

from .config import EnvConfig, ModelConfig
from .ppo import PPOConfig, RolloutBatch, collect_rollouts, concat_rollout_batches


def _split_counts(total: int, workers: int) -> List[int]:
    """Even split of `total` matches across `workers`, remainder on the first
    workers. The cumulative offsets give contiguous, disjoint seed blocks whose
    union equals the sequential run's seed range."""
    base, rem = divmod(int(total), int(workers))
    return [base + (1 if i < rem else 0) for i in range(workers)]


def _worker_loop(env_config, model_config, frozen_state_dict, ppo_config, task_q, result_q):
    import torch

    from .model import PolicyValueNet

    torch.set_num_threads(1)
    learner = PolicyValueNet(env_config, model_config)
    frozen = PolicyValueNet(env_config, model_config)
    frozen.load_state_dict(frozen_state_dict)
    frozen.eval()

    while True:
        task = task_q.get()
        if task is None:
            return
        worker_id, learner_state_dict, base_seed, matches = task
        try:
            learner.load_state_dict(learner_state_dict)
            cfg = replace(ppo_config, matches_per_iter=matches)
            batch = collect_rollouts(env_config, learner, frozen, cfg, base_seed=base_seed)
            result_q.put((worker_id, batch, None))
        except Exception:  # noqa: BLE001 - report any worker failure to the parent
            result_q.put((worker_id, None, traceback.format_exc()))


class ParallelRolloutCollector:
    """Persistent spawn-context worker pool that collects full self-play matches
    in parallel (CPU inference) and concatenates them into one RolloutBatch."""

    def __init__(self, env_config: EnvConfig, model_config: ModelConfig,
                 frozen_state_dict, ppo_config: PPOConfig, num_workers: int) -> None:
        if num_workers < 1:
            raise ValueError("num_workers must be >= 1")
        self.env_config = env_config
        self.model_config = model_config
        self.frozen_state_dict = frozen_state_dict
        self.ppo_config = ppo_config
        self.num_workers = int(num_workers)
        self._ctx = mp.get_context("spawn")
        self._task_q = None
        self._result_q = None
        self._procs: List[mp.process.BaseProcess] = []

    def start(self) -> None:
        self._task_q = self._ctx.Queue()
        self._result_q = self._ctx.Queue()
        self._procs = []
        for _ in range(self.num_workers):
            p = self._ctx.Process(
                target=_worker_loop,
                args=(self.env_config, self.model_config, self.frozen_state_dict,
                      self.ppo_config, self._task_q, self._result_q),
                daemon=True,
            )
            p.start()
            self._procs.append(p)

    def collect(self, learner_state_dict, base_seed: int, matches_per_iter: int) -> RolloutBatch:
        counts = _split_counts(matches_per_iter, self.num_workers)
        offset = 0
        dispatched = 0
        for worker_id, count in enumerate(counts):
            if count == 0:
                continue
            self._task_q.put((worker_id, learner_state_dict, int(base_seed + offset), int(count)))
            offset += count
            dispatched += 1

        results: Dict[int, RolloutBatch] = {}
        for _ in range(dispatched):
            worker_id, batch, err = self._result_q.get()
            if err is not None:
                self.close()
                raise RuntimeError(f"rollout worker {worker_id} failed:\n{err}")
            results[worker_id] = batch
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_parallel_rollouts.py -q`
Expected: PASS (4 tests). Spawn-context workers import torch fresh — the suite may take ~10-30s.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/parallel_rollouts.py ai/tests/test_parallel_rollouts.py
git commit -m "feat(ppo): ParallelRolloutCollector for parallel self-play rollouts

Persistent spawn-context pool of CPU-inference workers, each reusing
collect_rollouts on a disjoint seed block; main concatenates the batches.
Deterministically matches the sequential collector over the same seeds.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Wire num_workers into train_ppo and the CLI

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (`PPOConfig` ~line 21; `train_ppo` ~line 256)
- Modify: `ai/src/fh_mahjong_ai/scripts/train_ppo.py`
- Test: `ai/tests/test_ppo.py`

**Interfaces:**
- Consumes: `ParallelRolloutCollector` (Task 5).
- Produces: `PPOConfig.num_workers` (default 1); `train_ppo` uses the parallel collector when `num_workers > 1`, else the sequential `collect_rollouts`; CLI `--num-workers`.

- [ ] **Step 1: Write the failing test**

Add to `ai/tests/test_ppo.py`:

```python
def test_train_ppo_parallel_mock_writes_checkpoint(tmp_path):
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)
    init = tmp_path / "anchor.pt"
    save_checkpoint(init, PolicyValueNet(env_cfg, mcfg))

    cfg = PPOConfig(iterations=1, matches_per_iter=4, ppo_epochs=1, minibatch_size=8,
                    eval_interval=100, match_mode="classic", max_steps_per_episode=64,
                    device="cpu", num_workers=2)
    metrics = train_ppo(
        env_config=env_cfg, model_config=mcfg, init_checkpoint=init,
        checkpoint_dir=tmp_path / "ppo", config=cfg, base_seed=1000, run_eval=False,
    )
    assert len(metrics) == 1
    assert (tmp_path / "ppo" / "iter_001.pt").exists()
    assert np.isfinite(metrics[0]["policy_loss"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_train_ppo_parallel_mock_writes_checkpoint -q`
Expected: FAIL with `TypeError` (unexpected keyword `num_workers`).

- [ ] **Step 3: Write minimal implementation**

In `PPOConfig`, add the field (with the other ints, before `device`):

```python
    num_workers: int = 1
```

In `train_ppo`, add the parallel branch. After building `frozen` and `optimizer`, before the loop:

```python
    collector: Optional["ParallelRolloutCollector"] = None
    if config.num_workers > 1:
        from .parallel_rollouts import ParallelRolloutCollector
        frozen_state = {k: v.detach().cpu() for k, v in frozen.state_dict().items()}
        collector = ParallelRolloutCollector(
            env_config, model_config, frozen_state, config, config.num_workers,
        )
        collector.start()
```

Wrap the existing loop body's rollout call. Replace:

```python
        batch = collect_rollouts(
            env_config, model, frozen, config,
            base_seed=base_seed + iteration * config.matches_per_iter,
        )
```

with:

```python
        iter_seed = base_seed + iteration * config.matches_per_iter
        if collector is not None:
            learner_state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
            batch = collector.collect(learner_state, iter_seed, config.matches_per_iter)
        else:
            batch = collect_rollouts(env_config, model, frozen, config, base_seed=iter_seed)
```

Wrap the whole `for iteration` loop in `try` / `finally` so the pool is always closed:

```python
    try:
        for iteration in range(1, config.iterations + 1):
            ...  # existing loop body (with the rollout change above)
    finally:
        if collector is not None:
            collector.close()
    return history
```

(`Optional` is already imported in `ppo.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_train_ppo_parallel_mock_writes_checkpoint -q`
Expected: PASS

- [ ] **Step 5: Add the CLI flag**

In `ai/src/fh_mahjong_ai/scripts/train_ppo.py`, add the argument next to `--matches-per-iter`:

```python
    parser.add_argument("--num-workers", type=int, default=1,
                        help="parallel rollout workers (1 = sequential)")
```

and pass it into the `PPOConfig(...)` construction:

```python
        num_workers=args.num_workers,
```

- [ ] **Step 6: Write the CLI failing test**

Add to `ai/tests/test_ppo.py` (mirrors `test_cli_train_ppo_mock` with `--num-workers 2`):

```python
def test_cli_train_ppo_parallel_mock(tmp_path, monkeypatch):
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
        "--iterations", "1", "--matches-per-iter", "4", "--ppo-epochs", "1",
        "--minibatch-size", "8", "--match-mode", "classic", "--bridge-kind", "mock",
        "--max-steps-per-episode", "64", "--no-eval", "--num-workers", "2",
        "--model-channels", "8", "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "16", "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "16", "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    assert (tmp_path / "ppo" / "iter_001.pt").exists()
```

- [ ] **Step 7: Run the CLI test**

Run: `uv run --project ai pytest ai/tests/test_ppo.py::test_cli_train_ppo_parallel_mock -q`
Expected: PASS

- [ ] **Step 8: Run the full PPO + parallel suites**

Run: `uv run --project ai pytest ai/tests/test_ppo.py ai/tests/test_parallel_rollouts.py -q`
Expected: PASS (all tests, including the unchanged `num_workers=1` ones).

- [ ] **Step 9: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/src/fh_mahjong_ai/scripts/train_ppo.py ai/tests/test_ppo.py
git commit -m "feat(ppo): num_workers wiring for train_ppo + CLI

train_ppo uses ParallelRolloutCollector when num_workers>1 (sequential
otherwise); fh-mj-train-ppo gains --num-workers. Pool is closed in finally.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Full-suite verification + AGENTS.md docs

**Files:**
- Modify: `ai/AGENTS.md` (PPO/rollout section), `rlenv/AGENTS.md` (reward semantics) — reflect dense reward + parallel collection.

- [ ] **Step 1: Run the full Go rlenv suite**

Run: `go test ./rlenv/ -count=1`
Expected: PASS

- [ ] **Step 2: Run the full Go suite (no regressions elsewhere)**

Run: `go test ./... -count=1`
Expected: PASS

- [ ] **Step 3: Run the full Python suite**

Run: `uv run --project ai pytest ai/tests/ -q`
Expected: PASS

- [ ] **Step 4: Update AGENTS.md docs**

In `rlenv/AGENTS.md`, document: Chongci step reward is the per-seat running-score delta (dense, telescopes to match net); classic is unchanged; offline `TerminalRewards` remains match-net.

In `ai/AGENTS.md`, document: `collect_rollouts` is reproducible (per-match seeding); `ParallelRolloutCollector` parallelizes full-match rollouts (CPU workers + GPU learner); `PPOConfig.num_workers` and `--num-workers` enable it; eval sums per-step rewards.

- [ ] **Step 5: Commit**

```bash
git add ai/AGENTS.md rlenv/AGENTS.md
git commit -m "docs(rl): dense reward + parallel rollout collection

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Post-Implementation: Validation Sequence (cheap → expensive)

These are run by the user / operator on the GPU box, not part of the unit-test gate:

1. **Smoke (real bridge):** short PPO run with `--num-workers 8 --matches-per-iter 64 --iterations 2 --match-mode chongci` against the frozen anchor; confirm non-zero dense rewards in logs and no worker crashes.
2. **Campaign:** warm-started PPO vs frozen anchor with dense reward + hundreds of matches/iter, judged by the duplicate-seat CI gate (`mean_reward` ± `ci95`, `large_loss_rate`, `positive_reward_rate`).
3. **Decision:** if PPO beats the anchor → the self-play pool / GRP reward follow-ups become worth building. If not, next levers are exploration (entropy/temperature) and more iterations — not more infra.

## Deviations from the spec (noted for the record)

- **Reward mechanism upgraded to score-delta.** The spec described accumulating `roundRewards` (per-hand payouts). During planning I found `Players[i].Score` is the authoritative Chongci running score and `net_change = final_score − starting_score`. Using the per-decision score delta telescopes *exactly* to the match net, which guarantees the reconciliation invariant and captures any instant (kong/flower) score adjustments that `RoundResult.Payouts` might omit. Same scale (/1000), strictly more correct.
- **Two consumer-side changes the spec did not enumerate** were required to avoid regressions: (Task 3) eval must **sum** per-step rewards (it previously read only the terminal step), and (Task 2) the offline trajectory generator must keep `TerminalRewards` = match-net.
- **No `dense_reward` / `placement_bonus` proto/config flags.** Dense reward is the corrected behavior (the old zero-intermediate Chongci stream was effectively a dropped signal) and eval-summing makes it backward-compatible, so no toggle is needed and no proto change is incurred. The **placement bonus** (your "future direction") is intentionally **not** built now (YAGNI); the clean extension point is the `MATCH_END` return in `advanceToDecision`, where a ranking term could be added to the score-delta reward behind a future config flag.

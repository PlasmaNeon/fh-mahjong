# Oracle Guiding — Phase 2: Self-Play Feature-Dropout — Design

**Status:** approved design, ready for implementation plan.

## Goal

Produce a **deployable, imperfect-information** agent that beats the heuristic
anchor on placement, by combining two levers in one training run:

1. **Perfect-information scaffold (Suphx feature-dropout):** start with the
   opponents'-hands channels available, then anneal them away so the final agent
   plays on public information only.
2. **All-4 symmetric self-play:** all four seats are the current agent (copies of
   itself), co-evolving — so the opponent is never a fixed ceiling (unlike the
   heuristic).

The deployable artifact is a true 39-channel network, evaluated **non-oracle**
against the anchor (`mean_placement -0.0528`).

## Background

Phase 1 (merged, PR #117/#119) proved partial observability is a real lever: a
perfect-information oracle significantly beats the anchor (peak paired
`+0.126 ±0.068`, robustly lower large-loss). A deployable student can't *see* the
hidden hands, so it's bounded by the best 39ch public-info policy — but the Suphx
result is that a perfect-info early phase scaffolds a better public-info policy
than training on public info alone. We have never trained via self-play (every run
used a fixed heuristic or frozen anchor opponent); combining self-play with the
scaffold is the untried piece of the Suphx/Mortal recipe.

## Honest risks (accepted)

- **Two non-stationarities at once:** self-play (opponents shift as the agent
  learns; 4-player imperfect-info can cycle/drift) AND the δ annealing (the agent's
  own inputs disappear). Less stable than one lever. Mitigations: warm-start from
  the anchor, entropy-coef 0, a gentle δ schedule, and frequent intermediate evals
  to abort on divergence. If pure self-play drifts, the fallback is mixing recent
  past-snapshots as some opponents (the Tier-2 pool infra exists).
- **Attribution confound:** a positive result shows the *combination* beats the
  anchor, not which lever did the work. Accepted (goal is to beat the anchor).
- **Ceiling:** as δ→1 the agent may degrade toward the public-info ceiling (≈ the
  anchor). The run is itself the test.

## Global Constraints

- The deployable artifact is a TRUE 39-channel net (extracted from the trained 51ch
  net by slicing the input conv), evaluated with the plain non-oracle eval — so it
  is directly comparable to the anchor and to every prior 39ch result.
- **Exact-equivalence invariant:** the extracted 39ch student's policy logits on a
  39ch observation must EQUAL the 51ch net's logits on that observation zero-padded
  to 51ch (the input conv's first 39 channels are identical; the oracle channels
  contribute zero when their input is zero). This is the deployment correctness
  guarantee and the inverse of Phase-1's `build_oracle_model` warm-start.
- The PPO update must run on the SAME (δ-masked) observation the policy acted on at
  rollout time — record the masked obs.
- Reuse: `build_oracle_model` (warm-start), the `ParallelOracleCollector` pattern,
  `compute_gae` / `ppo_update`, `fh-mj-evaluate`, the duplicate-seat placement eval.
- `go test ./...` after any Go change (none expected — the 51ch oracle observation
  already exists); `uv run --project ai pytest` after Python changes.

## Architecture

One 51ch `PolicyValueNet`, warm-started from the anchor (`build_oracle_model`),
trained by symmetric self-play with a per-decision feature-dropout mask annealed
0 → 1. Six units:

### 1. Self-play rollout collector

`collect_selfplay_rollouts(env_config, model, config, base_seed, drop_prob) ->
RolloutBatch`. Generalizes `collect_oracle_rollouts` from 1 sampled seat to 4:

- Env: `learning_seats=(0,1,2,3)`, `auto_play_heuristics=False`,
  `oracle_observation=True` (51ch). All four seats are the SAME `model`.
- At each decision (any seat): build the obs tensor; with probability `drop_prob`,
  **zero the 12 oracle channels (39–50)** of the planes the model sees; sample the
  action from the masked-obs policy, record `(masked planes, action_mask, action,
  logprob, value)` and a per-seat reward slot.
- Reward: dense per-hand score delta credited to the acting seat
  (`_seat_step_reward(step.rewards, seat)` accumulated to that seat's last decision).
- `done=1` at match end for each seat's final decision.
- Records ALL FOUR seats' transitions (≈4× the data per match), all on-policy for
  the single shared `model`.

### 2. Parallel self-play collector

`ParallelSelfplayCollector` — a spawn-context worker pool mirroring
`ParallelOracleCollector`; ships `(learner_state_dict, base_seed, matches,
drop_prob)`, each worker runs `collect_selfplay_rollouts`. Contiguous/disjoint seed
blocks → parallel == sequential (determinism test).

### 3. Feature-dropout schedule

`feature_dropout_schedule(iteration, iterations, hold_start_frac=0.2,
ramp_frac=0.6) -> float`: δ=0 for the first 20% of iterations (full perfect info),
linear ramp 0→1 over the next 60%, δ=1 (pure public-info self-play) for the final
20%. Monotone nondecreasing, returns a probability in [0,1].

### 4. Deployable-student extraction

`extract_deployable_student(oracle_model_51ch, env_config_39ch, model_config) ->
PolicyValueNet` (39ch). Build a 39ch `PolicyValueNet`; copy every tensor from the
51ch net except `plane_stem.0.weight`; set the 39ch input conv to the 51ch net's
`plane_stem.0.weight[:, :39]`. By construction the student's output on a 39ch obs
equals the 51ch net's output on that obs zero-padded to 51ch. (Inverse of
`build_oracle_model`.)

### 5. Training loop

`train_selfplay_oracle(env_config, model_config, anchor_checkpoint, checkpoint_dir,
config, base_seed, run_eval) -> list[dict]`. Warm-start via `build_oracle_model`;
each iteration: `δ = feature_dropout_schedule(iter, iterations)`, collect (parallel
when `num_workers>1`), `compute_gae` + `ppo_update`, save the 51ch checkpoint and
record `δ` + metrics. Mirrors `train_oracle`.

### 6. Deployable eval

`fh-mj-evaluate --from-oracle`: load a 51ch self-play/oracle checkpoint, run
`extract_deployable_student` to get the 39ch student, then evaluate it
**non-oracle** (39ch, `oracle_observation=False`) duplicate-seat vs the anchor.
This is the gate.

## Data flow

`build_oracle_model` (51ch, anchor warm-start) → per iteration: δ schedule →
`collect_selfplay_rollouts` (4 seats = current net, oracle channels masked w.p. δ,
all 4 trajectories recorded with dense per-seat reward) → `compute_gae` +
`ppo_update` → 51ch checkpoint. Post-run / per interval:
`extract_deployable_student` → 39ch net → non-oracle duplicate-seat placement eval
vs anchor → paired gate verdict.

## Error handling / edge cases

- δ=1 must fully zero the oracle channels (deterministic), so the late-training and
  deployment distributions match.
- A match with zero decisions for a seat contributes nothing for that seat (no
  spurious `done`).
- `extract_deployable_student` asserts the 51ch net's input conv has exactly 51
  input channels (39 public + 12 oracle); any other shape raises.
- If all matches in a parallel batch are empty (degenerate), the worker raises and
  the parent surfaces it (same as `ParallelOracleCollector`).

## Testing

- **collect_selfplay_rollouts:** records all four seats (batch ≈ 4× a single-seat
  run on the same matches); with `drop_prob=1.0` the recorded planes have channels
  39–50 all zero; with `drop_prob=0.0` they carry the opponents' hands.
- **Parallel == sequential:** `ParallelSelfplayCollector(num_workers=2)` equals the
  sequential collector on the same seeds (sorted rewards + length + dones).
- **extract_deployable_student exactness:** the 39ch student's policy logits on a
  random 39ch obs equal the source 51ch net's logits on that obs zero-padded to
  51ch (atol 1e-5).
- **feature_dropout_schedule:** δ(0)=0, δ(iterations-1)=1, monotone nondecreasing,
  values in [0,1].
- **train_selfplay_oracle:** runs ≥2 iters on the mock bridge, writes checkpoints
  and a history with per-iter `delta`.
- **eval --from-oracle:** builds a 39ch student from a 51ch checkpoint and runs the
  non-oracle eval without shape errors.

## Out of scope

- Past-snapshot opponent mixing (stability fallback) — only if pure self-play
  drifts.
- Soft-KL distillation, asymmetric privileged critic (alternative mechanisms not
  chosen).
- Placement/GRP reward (dense per-hand score is the chosen signal).

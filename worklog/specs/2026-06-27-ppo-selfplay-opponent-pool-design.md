# PPO Self-Play Opponent Pool (Tier 2) — Design

**Date:** 2026-06-27
**Status:** Approved (brainstorming → ready for implementation plan)
**Context:** Tier 2 of the online-PPO improvement plan. Tier 1 (retuned hyperparameters:
lower entropy, higher lr) is a config-only run. Tier 2 changes the *opponent*: train PPO
against a pool of past-self checkpoints + the anchor instead of a single frozen anchor, so
it can surpass — not just match — the heuristic.

## Goal

Let `train_ppo` train the learning seat against a **pool of frozen neural opponents** (the
anchor + snapshots of past learners), sampled per opponent-seat per match, instead of a
single frozen anchor. Self-play against a moving set of past selves is the standard way to
drive genuine strategic improvement and avoid overfitting to one fixed opponent (the failure
mode behind the parity plateau).

## Non-Goals (YAGNI)

- **Heuristic-as-opponent.** No Python heuristic policy exists; it is Go-only (env auto-play),
  which would require per-match seat routing between Python-neural and Go-heuristic. Deferred.
- **Prioritized fictitious self-play (PFSP).** Win-rate-weighted opponent sampling is a later
  refinement; v1 uses uniform sampling.
- **Placement-bonus reward.** Kept off — Tier 2 changes only the opponent so the experiment
  isolates one variable and the eval/anchor baseline stay directly comparable.

## Constraints

- Reward (dense per-hand score delta) and observation encoding are **unchanged**, so the
  promoted anchor and the duplicate-seat eval baseline remain valid (no retraining of eval).
- Must work with the existing parallel rollout collector (16 CPU workers + GPU update) and the
  opt-in MLflow tracking, both behavior-preserving when the pool is trivial.
- Determinism: parallel collection must match sequential over the same seeds.

---

## Section 1 — Pool management (`train_ppo`, `ppo.py`)

`train_ppo` owns the canonical opponent pool: a list of CPU `state_dict`s.

- **Seed** the pool with the anchor's `state_dict` at index 0.
- Every `pool_snapshot_interval` iterations (default 10), append a CPU snapshot of the current
  learner's `state_dict`.
- Cap at `pool_max_size` (default 1). When appending would exceed the cap, evict the **oldest
  snapshot** (lowest index > 0); **index 0 (anchor) is always retained**.
- Each iteration the current pool is passed to the collection layer (directly for sequential,
  shipped for parallel).

**Backward compatibility — the key invariant:** `pool_max_size == 1` means the pool is always
`[anchor]` and never grows, so every opponent seat uses the anchor — **byte-identical to the
current single-frozen-anchor training**. This is the default, so existing behavior, the Tier 1
retuned run, and all current tests are unchanged. Tier 2 opts in with
`--pool-max-size 5 --pool-snapshot-interval 10` (anchor + up to 4 past selves).

## Section 2 — Opponent assignment (`collect_rollouts`, `ppo.py`)

`collect_rollouts` takes a **list of opponent nets** instead of a single `frozen_anchor`.

- The learner (seat `LEARNING_SEAT == 0`) samples from its masked policy and records experience
  — unchanged.
- For each match, each opponent seat (1, 2, 3) is assigned a pool index sampled
  **deterministically** from the match seed and seat (e.g. a `np.random.default_rng(base_seed + m)`
  draw, or seat-offset hashing), and uses that net's argmax for every decision in that match.
- The existing per-match `torch.manual_seed(base_seed + m)` keeps learner sampling reproducible;
  opponent assignment uses its own seeded RNG so it is reproducible and identical across the
  sequential and parallel paths.
- When the pool has a single member (anchor), every opponent seat uses the anchor — exactly the
  current behavior.

## Section 3 — Parallel collector (`parallel_rollouts.py`)

- `collect(learner_state_dict, pool_state_dicts, base_seed, matches_per_iter)` ships the learner
  state **and the current pool** (list of `state_dict`s) to each worker each iteration.
- Each worker builds/reloads its learner net + one opponent net per pool slot, then runs the
  same `collect_rollouts` with the same per-match/seat opponent sampling, so **parallel results
  match sequential** over the same seeds.
- Worker exceptions propagate and the pool is closed (existing hardening retained).
- **Memory/transfer note:** the pool is ≤ `pool_max_size` small nets; the per-iteration transfer
  is `pool_max_size × model_size × num_workers`. With the default Chongci model (~22 MB) and 16
  workers this is bounded and tolerable, but if it pressures the 31 GB box the documented
  optimization is **ship-on-change**: keep the anchor in workers, ship only newly added snapshots
  on snapshot iterations rather than the whole pool every iteration. Not built in v1.

## Section 4 — Config / MLflow / CLI

- `PPOConfig`: add `pool_snapshot_interval: int = 10` and `pool_max_size: int = 1` (default
  preserves current single-anchor behavior).
- CLI `fh-mj-train-ppo`: add `--pool-snapshot-interval` and `--pool-max-size`.
- MLflow: log `pool_size` as a per-iteration metric (via the existing iteration callback) so the
  opponent diversity over the run is visible.

## Section 5 — Error handling

- Snapshotting copies the learner `state_dict` to CPU (detached) to avoid holding GPU tensors or
  aliasing live parameters.
- Eviction never removes index 0; a `pool_max_size < 1` is clamped to 1.
- Opponent nets are built in `eval()` mode with `requires_grad_(False)` (as the current frozen
  anchor is), so they never accumulate gradients.

## Section 6 — Testing (TDD)

- **Pool management:** seeded with anchor; a snapshot is added exactly every `pool_snapshot_interval`;
  size never exceeds `pool_max_size`; index 0 (anchor) is always present after eviction.
- **`pool_max_size == 1` regression:** opponents are always the anchor; `collect_rollouts` output
  is identical to the current single-anchor path for the same seeds (byte-for-byte on rewards/
  actions) — guards backward compatibility.
- **Deterministic opponent assignment:** same seeds ⇒ same per-match/seat opponent indices.
- **Parallel == sequential with a non-trivial pool:** `num_workers=2` and a multi-member pool
  produce per-match reward sums matching the sequential collector over the same seed set.
- **`train_ppo` e2e (mock bridge):** with `pool_max_size=3`, `pool_snapshot_interval=1`, the pool
  grows over iterations and training completes with finite losses + checkpoints.

## Success Criteria

- `pool_max_size=1` is behavior-preserving (existing tests + a new regression test pass unchanged).
- With `pool_max_size>1`, the pool grows as specified, opponents are sampled per match/seat, and
  parallel matches sequential deterministically.
- A Tier 2 self-play run (anchor + past selves, dense reward) launches via
  `--pool-max-size 5 --pool-snapshot-interval 10 --mlflow` and is judged against the same anchor
  baseline; the open question it answers is whether self-play clears the anchor where the single-
  anchor run plateaued at parity.

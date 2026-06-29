# Oracle Guiding — Phase 1 (Perfect-Information Oracle + Gate) Design

**Status:** approved design, ready for implementation plan.

## Goal

Break the parity-with-anchor ceiling for the fh-mahjong RL agent using **oracle
guiding** (the Suphx technique). This spec covers **Phase 1 only**: build a
*perfect-information* oracle agent — one that, in addition to its own hand,
observes the three opponents' concealed hands — and measure whether perfect
information lets it **significantly beat the heuristic anchor** on placement.

This is a validate-before-build gate. If a perfect-info agent does **not** beat
the anchor, partial observability is not the ceiling and we stop before building
the (harder) Phase-2 transfer to a deployable imperfect-info student. If it does,
Phase 2 is justified and gets its own spec.

## Background / why this lever

Every reward-and-optimization lever tried (dense per-hand reward, big batches,
self-play pool, entropy/lr tuning, GRP placement reward) plateaued at parity with
the anchor (`mean_placement ≈ -0.0528 ±0.0665`). Suphx and Mortal — the strongest
mahjong AIs — did not use an AlphaStar league; they relied on a strong supervised
bootstrap from expert human play (unavailable for Fenghua's custom ruleset) plus,
in Suphx, **oracle guiding** and GRP. GRP we tested → parity. Oracle guiding is
the remaining Suphx lever that needs **no human data** (entirely self-generated)
and directly attacks the most likely bottleneck: the agent's teacher/opponent is
a weak heuristic, and partial observability caps how far self-play against it can
go.

## Feasibility (validated)

- `internal/rl/observation.go:encodeObservation` runs on `e.game.State` — the
  engine's **authoritative, unredacted** full game state (`internal/rl/env.go:102`).
  Redaction exists only in `internal/api/room.go` (server path), **not** in
  `internal/rl`.
- `PlayerState.closed_hand` (proto field 3) holds every player's concealed tiles;
  the engine populates all four at observation time. The observation builder
  simply chooses to encode only **public** info (open melds, discards, flowers)
  for the three opponents, encoding the closed hand only for `self`.
- The `SeatObservation` proto carries its shape (`plane_channels`, `plane_height`,
  `plane_width`), so adding channels is well-defined on the wire; the Python bridge
  reshapes with `config.plane_shape`, which oracle mode sets to `(51,42,1)`.

Conclusion: the perfect-information signal (opponents' concealed hands) is present
in the env state and merely unencoded. Phase 1 is buildable with a localized
Go-side observation addition plus a proto flag — no human data, no redaction
changes. The wall *order* is not directly available (only `wall_count` +
`wall_seed`); v1 deliberately skips it (opponents' hands are the dominant signal).

## Global Constraints

- `internal/engine/game.go` must never import `internal/rules/` (ruleset-agnostic).
- Proto changes regenerate **both** Go and TypeScript bindings (per repo rule).
- `oracle_observation=false` (default) must be **byte-identical** to today's
  observation: same 39 channels, same values. This is the behavior-preserving
  regression guard.
- Oracle planes are **appended** (suffix), never interleaved, so channels 0–38 of
  an oracle observation equal the normal observation exactly. The opponent-slicing
  and the regression guard both depend on this invariant.
- `go test ./...` after Go changes; `uv run --project ai pytest` after Python.
- Placement eval is the gate metric; chongci eval uses `--max-steps-per-episode 4000`
  so matches terminate (matches `resolve_max_steps_per_episode` now in main).

## Architecture

Five units, each independently testable:

### 1. Oracle observation encoding (Go)

`internal/rl/observation.go`. Mirror the self-hand encoding for the three
opponents, appended after the existing 39 channels:

- channels 39–42 — right opponent (`(seat+1)%4`) closed hand, 4 threshold planes
  via the existing `setThresholdPlanes` helper applied to
  `faceCountsFromTiles(right.ClosedHand)`.
- channels 43–46 — across opponent (`(seat+2)%4`) closed hand.
- channels 47–50 — left opponent (`(seat+3)%4`) closed hand.

`ObservationPlaneChannels` becomes `39` normally and `51` in oracle mode. Encode
the extra planes **only** when oracle mode is on; otherwise emit exactly today's
39 channels. The relative-seat order (right/across/left) mirrors the existing
opponent-public-info ordering.

### 2. Oracle toggle plumbing (proto → Go → Python)

- Proto: add `bool oracle_observation = 6;` to `EnvConfig` (`proto/game.proto`;
  fields 1–5 are used, 6 is the next free tag). Regenerate Go + TS bindings.
- Go: `rl.New(config)` stores the flag; `encodeObservation` (and its callers in
  `env.go`) consult it to size planes and report `plane_channels`.
- Python: `EnvConfig` gains `oracle_observation: bool = False`, serialized into the
  proto `EnvConfig` bytes (`bridge._config_message`) the Go bridge unmarshals
  (`cmd/rlbridge/main.go:38`). The bridge decodes planes with `config.plane_shape`
  (not the message's `plane_channels`), so `EnvConfig.__post_init__` resolves
  `plane_shape` to `(51,42,1)` whenever `oracle_observation` is set and the shape is
  still the 39ch default — keeping oracle mode "just works" and the default path
  byte-identical. Because Go's `emptyObservation` (terminal placeholder) must match,
  the oracle flag is threaded to it too so every observation in an oracle episode is
  51 channels.

### 3. Single-seat oracle rollout collector (Python)

The oracle trains as the **only** Python-controlled seat against the env's
**built-in heuristic** opponents (`auto_play_heuristics=True`, `learning_seats=(0,)`,
`oracle_observation=True`). This is the same opponent the anchor baseline was
measured against (`evaluate_online` runs auto-play heuristics), so the gate is
apples-to-apples and train/eval share one opponent — and it avoids any
dual-plane-shape opponent nets or per-step obs slicing (the oracle is the only net
in the loop).

A new `collect_oracle_rollouts` (mirrors `collect_rollouts`'s PPO bookkeeping but
single-seat): for each learner decision, sample from the 51ch oracle policy and
record planes(51ch)/scalars/mask/action/logprob/value; accumulate the dense
per-hand score delta for seat 0 as reward; `done=1` at match end. The env
auto-advances the heuristic opponents between the learner's decisions, so the
collector never runs an opponent net. Reuses the existing `compute_gae` /
`ppo_update` for the update.

### 4. Oracle model + warm-start (Python)

A `PolicyValueNet` built with `plane_shape=(51,42,1)`. Warm-start from the anchor:
load all same-shape tensors via the existing `load_compatible_checkpoint`
(`storage.py`), which skips the mismatched 39→51 input conv. Then initialize the
input conv so the oracle starts equal to the anchor: copy the anchor's input-conv
weights into the first 39 input channels and **zero** the 12 new channels, so the
oracle's initial policy/value equals the anchor's and it learns to use the extra
channels from there.

### 5. Training + gate (Python, reuse merged PPO)

- Train the oracle (seat 0, 51ch) via `collect_oracle_rollouts` vs the env's
  heuristic opponents, **plain dense score reward** (no GRP — isolates the single
  variable: perfect information), reusing `compute_gae` + `ppo_update`.
- Stable config we trust: `lr 1e-5`, `entropy-coef 0`, `ppo-epochs 2`,
  `gamma 0.99`, `match-mode chongci`, `max-steps-per-episode 4000`, Go bridge /
  CUDA.
- **Gate eval** uses the existing duplicate-seat eval (already auto-play
  heuristics) with **`oracle_observation=True`** so the env emits 51ch obs to the
  oracle and the eval net is built at `plane_shape=(51,42,1)` — exposed via an
  `--oracle` flag on `fh-mj-evaluate`. Compare the oracle's `mean_placement`
  (`--max-steps-per-episode 4000`) to the anchor baseline (`-0.0528`) with a
  **paired test** on identical seeds. **Pass = oracle significantly beats anchor.**

## Data flow

`pb.GameState (all hands)` → `encodeObservation(seat, oracle=true)` → 51-channel
`SeatObservation` (channels 0–38 = normal, 39–50 = opponents' hands relative to the
learner's seat) → proto bytes → Python bridge decodes via `config.plane_shape`
`(51,42,1)` → 51ch oracle net (policy + value); the env auto-plays heuristic
opponents in-engine (no Python opponent net) → `collect_oracle_rollouts` records
the learner's transitions with dense score-delta reward → `compute_gae` +
`ppo_update` → checkpoints → duplicate-seat placement eval with
`oracle_observation=True` vs the anchor baseline → paired gate verdict.

## Error handling / edge cases

- If `oracle_observation` is set but a consumer expects 39 channels (e.g. an
  anchor net), the suffix-append + explicit slice prevents a shape error; a guard
  asserts the oracle channel count is a superset of the opponent's.
- `oracle_observation=false` must not allocate or emit the extra planes (keeps the
  default path and all existing runs byte-identical).
- Warm-start input-conv init must handle the case where the anchor checkpoint's
  input conv has 39 channels exactly; mismatch (other than the expected 39→51)
  raises rather than silently misaligning.

## Testing

- **Go:** oracle-mode obs has 51 channels and channels 0–38 are byte-identical to
  the normal (39ch) obs for the same state (prefix invariant); the three appended
  opponent closed-hand planes equal the opponents' actual `ClosedHand` face counts;
  `oracle_observation=false` emits exactly 39 channels.
- **Python:** with `oracle_observation=True`, `EnvConfig.plane_shape` resolves to
  `(51,42,1)` and the bridge decodes a 51-channel observation to that shape;
  `oracle_observation=False` decodes byte-identically to today (39ch);
  `collect_oracle_rollouts` on the mock bridge produces a valid single-seat
  `RolloutBatch` (non-empty, `done=1` at match end); the warm-start init produces an
  oracle whose initial policy logits equal the anchor's on a normal observation with
  the 12 oracle channels zeroed.

## Out of scope (Phase 2, deferred)

- Transferring the oracle's strength to a deployable imperfect-info student
  (mechanism — asymmetric privileged critic vs Suphx feature-dropout vs
  distillation — chosen once the gate shows how strong the oracle is).
- Wall-composition features (only count/seed available today).
- Run-time policy adaptation (Suphx pMCPA).

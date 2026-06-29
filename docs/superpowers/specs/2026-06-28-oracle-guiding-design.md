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
- The `SeatObservation` proto self-describes its shape (`plane_channels`,
  `plane_height`, `plane_width`), so adding channels is read dynamically by the
  Python bridge.

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
- Python: `EnvConfig` gains `oracle_observation: bool = False`, passed through to
  the proto `EnvConfig` bytes the Go bridge unmarshals (`cmd/rlbridge/main.go:38`).
  The bridge already reads `plane_channels` from each observation, so the decoded
  tensor shape follows automatically.

### 3. Opponent slicing (Python training/eval)

In a match the oracle (seat 0, 51ch) plays vs three frozen anchors (39ch). Because
oracle planes are a suffix, the anchor nets consume `planes[..., :39, :, :]`. Add
the slice in the opponent inference path of `collect_rollouts` (and the eval
opponent path) gated on the oracle channel count exceeding the opponent net's
expected channels. The learner (oracle net) consumes all 51 channels.

### 4. Oracle model + warm-start (Python)

A `PolicyValueNet` built with `plane_shape=(51,42,1)`. Warm-start from the anchor:
load all same-shape tensors via the existing `load_compatible_checkpoint`
(`storage.py`), which skips the mismatched 39→51 input conv. Then initialize the
input conv so the oracle starts equal to the anchor: copy the anchor's input-conv
weights into the first 39 input channels and **zero** the 12 new channels, so the
oracle's initial policy/value equals the anchor's and it learns to use the extra
channels from there.

### 5. Training + gate (Python, reuse merged PPO)

- Train seat 0 (oracle, 51ch) vs three frozen anchors using the existing PPO
  pipeline with **plain dense score reward** (no GRP — avoids a 39ch GRP-net
  channel mismatch and isolates the single variable: perfect information).
- Stable config we trust: `lr 1e-5`, `entropy-coef 0`, `ppo-epochs 2`,
  `gamma 0.99`, `match-mode chongci`, `max-steps-per-episode 4000`, on the Go
  bridge / CUDA.
- Gate: duplicate-seat eval of the oracle (51ch obs, `--max-steps-per-episode
  4000`) vs the anchor baseline (`mean_placement -0.0528`), **paired test** on
  identical seeds. **Pass = oracle significantly beats anchor on mean_placement.**

## Data flow

`pb.GameState (all hands)` → `encodeObservation(seat, oracle=true)` → 51-channel
`SeatObservation` (channels 0–38 = normal, 39–50 = opponents' hands) → proto bytes
→ Python bridge decodes by `plane_channels` → oracle net consumes 51ch (policy +
value); opponent path slices `[:39]` for the anchor nets → PPO update (dense score
reward) → checkpoints → duplicate-seat placement eval vs anchor → gate verdict.

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
- **Python:** bridge decodes a 51-channel oracle observation to the right tensor
  shape; `oracle_observation=False` decodes byte-identically to today; opponent
  slicing feeds 39 channels to a 39ch net without error; warm-start init produces
  an oracle whose initial policy logits equal the anchor's on a normal-prefix
  observation with zeroed oracle channels.

## Out of scope (Phase 2, deferred)

- Transferring the oracle's strength to a deployable imperfect-info student
  (mechanism — asymmetric privileged critic vs Suphx feature-dropout vs
  distillation — chosen once the gate shows how strong the oracle is).
- Wall-composition features (only count/seed available today).
- Run-time policy adaptation (Suphx pMCPA).

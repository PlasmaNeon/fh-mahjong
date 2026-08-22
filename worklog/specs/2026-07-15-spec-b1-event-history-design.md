# Spec B1: Public Event History in the Observation — Design

**Date:** 2026-07-15
**Branch:** `claude/spec-b1-events` (off main @ 8c38ac5)
**Status:** Approved design → implementation plan next

## Context

Spec B of the post-audit rebuild (A: instruments/inputs — DONE, PR #166; B:
representation; C: objective — folded into B2) adds the direction both
literature surveys ranked #1: ordered public event history feeding a causal
event encoder, plus an asymmetric privileged critic with belief auxiliaries.

B splits in two:

- **B1 (this spec):** the data path — Go-side public-event capture, proto,
  bridge, Python decoding. Fully gateable by unit/parity tests; no training.
  Dormant by default (byte-identical observations when disabled), the same
  pattern the oracle phases shipped with.
- **B2 (next spec, after B1 merges):** GRU event encoder fused into
  `PolicyValueNet`, privileged critic (51ch oracle planes + history),
  auxiliary heads (opponent tile-count distributions, danger/ron, categorical
  rank/bust — Spec C rides here), warm-start from iter275 with zero-init new
  paths, screening on `--start-seed 910000`, confirmation gate on
  `--start-seed 950000` via `fh-mj-compare`.

Decisions settled with the user: two specs (B1 → B2); warm-start posture for
B2; Spec C built into B2's critic rather than a separate arm.

## What B1 records

The snapshot planes already summarize WHAT is visible; history adds WHEN and
HOW — discard order, tsumogiri-vs-tedashi cues, call timing — the signals
every modern mahjong agent (Tjong, Mahjax-era baselines, DouZero+/DanZero+
lineage) extracts from sequence encoders.

### Event vocabulary (8 types)

| type | emitted when | face | fromSeat | flags |
|---|---|---|---|---|
| `DRAW` | any wall/dead-wall draw incl. haitei accept | actor's own draws only; UNKNOWN otherwise | — | `haitei` |
| `DISCARD` | tile enters the pond | always (public) | — | `tsumogiri` |
| `CHII` | sequence claim executes | claimed tile's face | discarder | — |
| `PON` | triplet claim executes | face | discarder | — |
| `KAN_OPEN` | direct kan executes | face | discarder | — |
| `KAN_CLOSED` | closed kan declared | face (revealed in Fenghua) | — | — |
| `KAN_UPGRADE` | pon upgraded to kan | face | — | — |
| `FLOWER` | flower revealed (incl. initial pre-game flowers) | flower face | — | — |

Notes:
- **Information legality is enforced at encode time, not capture time:** the
  engine log stores true faces; when rendering the history for observer seat
  S, a `DRAW` event's face is replaced with the UNKNOWN sentinel unless the
  drawing seat == S. Everything else in the table is public by rule
  (discarded/claimed wilds are face-value public per the wild rules).
- **Tsumogiri flag:** set when the discarded tile id equals the discarder's
  `*DrawnTileId` at discard time (the cut-from-draw vs cut-from-hand cue).
- **Haitei refuse** is not an event (rare, near-zero information; revisit only
  if B2's ablations ever care).
- The log **clears at round start** (`StartRound` boundary). Round/match
  context (hand number, scores, winds) already lives in the 58 scalars.

### Wire encoding: one `uint32` per event

Bit layout (LSB first), shared verbatim between Go and Python as the single
source of truth, pinned by cross-language golden tests:

```
bits  0-3   event type   (0=DRAW, 1=DISCARD, 2=CHII, 3=PON, 4=KAN_OPEN,
                          5=KAN_CLOSED, 6=KAN_UPGRADE, 7=FLOWER)
bits  4-5   actor seat, RELATIVE to observer (0=self, 1=right, 2=across, 3=left)
bits  6-11  face index    0-41 per tileFaceIndex42; 63 = UNKNOWN
bits 12-13  from-seat, RELATIVE to observer (calls only; 0 otherwise)
bits 14     flag: tsumogiri
bits 15     flag: haitei
bits 16-31  reserved, must be zero
```

Observer-relative rendering means the same engine log yields four different
encodings — exactly what a per-seat policy needs, and what makes the encoding
a pure function of (log, observer seat).

## Architecture

### Engine (`internal/engine`)

`PublicEventLog` — a plain slice of small structs on `Game`, always on
(capture cost is an append of a 4-field struct; no allocation churn worth a
ring buffer — a round tops out around ~200 events):

```go
type PublicEvent struct {
    Type     PublicEventType // uint8
    Seat     uint32          // absolute; made relative at encode time
    Face     int16           // tileFaceIndex42, -1 = none/unknown-at-source
    FromSeat int32           // absolute discarder for calls; -1 otherwise
    Flags    uint8           // tsumogiri, haitei bits
}
```

- Appended at the SAME call sites that feed `PaipuRecorder` (game.go draw /
  discard / claim / kan / flower paths) but NOT nil-guarded — the log is a
  first-class engine field, present in every game including RL envs, which
  never attach a recorder.
- `StartRound` truncates it.
- `clone.go` copies the slice (values, no shared backing array).
- `RedealUnseen` leaves it untouched: every logged fact is public, and a
  determinization must preserve exactly the public record. (Own-draw faces of
  the SEARCH ROOT seat stay truthful — the root's hand is fixed across
  clones; other seats' draw faces are masked at encode time anyway, so the
  redeal cannot leak.)

### Proto (`proto/game.proto`)

`SeatObservation` gains two fields (append-only, regen Go + Python via
grpc_tools.protoc + TS with `--null-semantics`):

```proto
  repeated uint32 event_history = 12;   // packed events, oldest first
  uint32 event_history_window = 13;     // the window W the env was configured with
```

`EnvConfig` gains `uint32 event_history_window = N` (0 = disabled, the
default). When 0, `SeatObservation` is byte-identical to today's output.
When W > 0, `event_history` carries the LAST min(W, len(log)) events,
oldest first, observer-relative. Default window for B2: **128** (a config
knob, not a constant).

### RL layer (`internal/rl`)

- `encodeObservation` gains the history rendering step (pure function of
  log + seat, applied after the existing plane/scalar encoding; planes and
  scalars are untouched).
- `EnvConfig` plumbing mirrors `oracle_observation` exactly (normalizeConfig,
  Reset propagation, envpool, searchpool clone paths).
- SearchPool: clones inherit the parent log (via `clone.go`); rollout steps
  append to the clone's log naturally since capture lives in the engine.

### Bridge + Python (`ai/`)

- `bridge.py`: `event_history` surfaces as an `np.ndarray[uint32]` next to
  planes/scalars (both ctypes Go bridge and `MockMahjongBridge`, which
  fabricates well-formed packed events when the window is on).
- New `ai/src/fh_mahjong_ai/events.py`: the bit layout mirrored as constants,
  `decode_event(u32) -> Event` / `decode_history(array) -> list[Event]`, and
  an embedding-index helper for B2 (`event_to_token`).
- `EnvConfig` (Python) gains `event_history_window: int = 0`.

## Testing / gate (all pre-merge, no training)

1. **Dormant byte-parity:** window=0 → `SeatObservation` bytes identical to
   pre-B1 for a seeded match replay (the oracle-phase regression pattern).
2. **Cross-language golden:** one seeded Go match with window on; the Go
   packed events, the Python decode, and the `PaipuRecorder` record of the
   same match must agree event-for-event (types, order, faces, flags).
3. **Information legality:** for every observer seat over a full seeded
   match: no `DRAW` event with actor != self carries a real face; every
   own-draw does.
4. **Tsumogiri correctness:** a scripted draw-then-discard-same-tile yields
   the flag; discarding a held tile does not.
5. **Relative-seat rendering:** the same log rendered for seats 0..3 maps
   actors through (actor − observer) mod 4.
6. **Clone/search consistency:** searchpool clones see the parent's public
   record; a clone's post-branch events do not leak back to the parent.
7. **Window truncation:** log longer than W yields the last W, oldest first.
8. Full suites: `go vet ./... && go test ./...`,
   `uv run --project ai pytest`, plus TS bindings regen + `tsc` clean.

## Out of scope (B2)

Model changes, the GRU encoder, privileged critic, auxiliary heads, training,
and any gate runs. B1 changes NOTHING about what any existing net sees:
serving, training, and eval all run with window=0 until B2 flips it on.

## Risks

- Proto regen churn across three languages — mitigated by append-only fields
  and the established regen commands (proto/AGENTS.md).
- Capture call-site drift vs paipu hooks (a future event added to one but not
  the other) — mitigated by the golden cross-check test, which fails if the
  two records diverge.
- Bit-packing mistakes — mitigated by the golden fixture and the reserved-
  bits-zero assertion in both decoders.

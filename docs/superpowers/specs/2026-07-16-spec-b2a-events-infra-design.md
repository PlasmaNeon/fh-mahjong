# Spec B2a: Event History at Scale — Search Honesty + Pool Layout — Design

**Date:** 2026-07-16
**Branch:** `claude/spec-b2a-events-infra` (off main @ feb1485)
**Status:** Approved design → implementation plan next

## Context

B1 (PR #169) landed the event-history data path, dormant at window 0, with
fail-fast guards on every path that cannot carry events. B2a discharges the
two Important findings B1's final review carried forward, so that B2b (GRU
encoder + privileged critic + auxiliaries + training) starts from a
guard-free, honest, at-scale data path. B2a is pure infra: no model or
training changes, gateable entirely by tests.

## 1. Search honesty: `RedealUnseen` event rewrite (B1 finding I-1)

**Problem.** A search clone inherits the parent's event log, whose `DRAW`
events store true faces. `packPublicEvent` masks a draw's face only for
OTHER observers — the drawing seat sees its own faces. After `RedealUnseen`
re-deals every non-acting seat's hand, a clone rollout row encoded for a
non-root acting seat therefore shows that seat draw faces that (a) are
inconsistent with its redealt hand and (b) are correlated with the live
hidden world — the same information-dishonesty class as the fixed
live-baseSeed leak.

**Change.** At the end of `RedealUnseen(actingSeat, seed)`
(internal/engine/redeal.go), rewrite the clone's log in place:

```go
for i := range g.publicEvents {
    if g.publicEvents[i].Type == EventDraw && g.publicEvents[i].Seat != actingSeat {
        g.publicEvents[i].Face = -1
    }
}
```

The acting (root) seat's faces stay truthful — its hand is fixed across
clones by construction. `-1` renders as `EventFaceUnknown` (63) for every
observer, which is exactly what every observer other than the drawer could
already see.

**Tests.**
- Root invariance: the ROOT observer's rendered history is byte-identical
  before vs after the rewrite (masking already hid non-root draw faces from
  the root — proving the rewrite removes exactly the illegal information
  and nothing else).
- Non-root honesty: after redeal, a non-root seat rendering its OWN view
  sees `EventFaceUnknown` for its pre-redeal draws.
- Clone isolation: the live game's log is untouched (the clone's copy is
  rewritten).
- Post-redeal appends: new draws in the clone log render normally (the
  rewrite is a one-shot at redeal time).

## 2. Flat pool row layout (B1 finding I-2)

**Format (approach A: fixed-width rows + explicit counts).** Each
observation row contributes exactly `event_history_window` uint32 slots,
tail-padded, plus a per-row count. An explicit count is REQUIRED because
packed value `0x0` is a valid event (self draw of face 0) — zero-padding
alone is ambiguous. Padding bytes are zeros and are never decoded.

`EnvPoolStepResponse` (proto/game.proto) gains three append-only fields:

```proto
  // Flat event-history buffers for rows with has_observation, matching the
  // planes/scalars row order. uint32 LE [rows, event_history_window],
  // tail-padded; per-row true lengths in event_counts (uint32 LE [rows]).
  // Empty when event_history_window == 0 (dormant, zero cost).
  bytes event_histories = 10;
  bytes event_counts = 11;
  uint32 event_history_window = 12;  // header dim, seeded on first row
```

**Go (`internal/rl/envpool.go`).** `appendObservationRow` seeds
`response.EventHistoryWindow` from the first row (alongside the other
header dims) and, when the window is nonzero, appends
`len(obs.EventHistory)` as a uint32 LE count plus the events tail-padded to
exactly `window` uint32 slots. Shared by EnvPool and SearchPool — the flat
layout stays identical across both pools by construction.

**Python (`ai/src/fh_mahjong_ai/envpool.py`).**
- `GoEnvPool` decodes the two buffers into per-row `np.ndarray[uint32]` of
  TRUE length (slice `[i*W : i*W + count[i]]`), surfaced through
  `PoolStepResult` next to planes/scalars/masks.
- `InProcessEnvPool` passes each bridge observation's `event_history`
  through unchanged (already true-length arrays).
- Both pools produce the same per-row shape, so consumers are
  pool-agnostic.
- Stale-bridge handshake, pool edition: when the configured window is
  nonzero, `GoEnvPool` requires the response header
  `event_history_window` to equal it and raises `BridgeError` naming the
  rebuild command otherwise (mirrors the single-env `CtypesGoBridge`
  handshake from B1).

**Proto regen:** Go + Python (grpc_tools.protoc) + TS (`--null-semantics`),
per proto/AGENTS.md.

## 3. Guard removal → positive tests

All four B1 fail-fast guards are DELETED and replaced by tests proving the
paths now work:

| guard site | replacement test |
|---|---|
| `FHEnvPoolNew` (cmd/rlbridge/main.go) | pool constructs at window>0; rows carry events |
| `NewSearchPool` (internal/rl/searchpool.go) | search pool constructs at window>0; clone rows' histories honest post-redeal (§1) |
| `InProcessEnvPool` (ai/envpool.py) | pool at window>0 yields per-row event arrays |
| `GoEnvPool` (ai/envpool.py) | FFI-gated: pool at window>0 yields rows matching the single-env bridge |

Key positive tests:
- **Pool/single-env parity (Go):** same seed, same env config, window on —
  the pool's flat row for a slot equals the single-env
  `SeatObservation.EventHistory` for the same decision (count and bytes).
- **Rectangularity/padding:** rows with fewer than W events are tail-padded
  with zeros and `event_counts` recovers exactly the true prefix; a row
  whose true first event packs to `0x0` still round-trips (the ambiguity
  case that forced explicit counts).
- **Dormancy:** window 0 → all three new response fields empty; existing
  consumers byte-unaffected.
- **Python decode:** synthetic response buffers decode to the expected
  per-row arrays; count > window or buffer-size mismatch raises loudly.
- The B1 guard regression tests (`TestPoolsRejectEventHistoryWindow`,
  `test_env_pools_reject_event_history_window`,
  `test_go_pool_config_message_carries_window`'s rejection half) are
  REPLACED by their positive counterparts, not merely deleted.

## Out of scope (B2b)

Model changes, RolloutBatch/collector consumption of events, GRU encoder,
privileged critic, auxiliary heads, training, and any gate runs. After B2a,
`event_history_window > 0` flows end-to-end through single envs, env pools,
search pools, and trajectory generation — but nothing trains on it yet.

## Risks

- Padding-sentinel confusion — eliminated by explicit counts (0x0 is a
  valid event; the spec test pins that exact case).
- Layout drift between EnvPool and SearchPool — impossible by construction
  (one shared `appendObservationRow`).
- Rewrite over-masking (root's own faces) or under-masking (non-draw
  events) — pinned by the root-invariance and non-root-honesty tests.

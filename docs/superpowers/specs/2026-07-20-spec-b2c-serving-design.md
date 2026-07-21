# Spec B2c: Serving Integration for the B2b Champion — Design

**Date:** 2026-07-20
**Branch:** `claude/spec-b2c-serving` (off main @ 85273ab)
**Status:** Approved design → implementation plan next

## Context

`iter_075` (event-GRU + privileged critic, B2b) passed the ratified
confirmation gate (+0.0408 ± 0.0203 paired over the champion, tail
significantly better) and is registered in the manifest as the
gate-qualified research champion with `serving_status: blocked_on_b2c`.
It cannot play a real game: the serving path encodes event-free
observations (`rl.EncodeObservation` in `HTTPPolicy`), the Python loader
refuses B2b checkpoints by design, and `/act` carries no events.

B2c is the last gate before deployment. Its scope and acceptance criteria
were jointly agreed with Codex in the canonical consult session (13-item
ratified list, in the SDD ledger): **the eval-vs-serving parity harness is
a hard gate, not a smoke test** — the residual risk after a clean
statistical gate is semantic drift between the event stream evaluation
consumed and the one production serves.

User-set operational gate (2026-07-20): shadow ≥ 50 games / canary ≥ 20
matches (the "light" option; criteria in §6).

## 1. Go: `bot.DecisionContext` + capability interface

New in `internal/bot`:

```go
// DecisionContext is the atomic, room-owned decision snapshot. The room
// builds it under its game lock; policies consume it read-only. A policy
// must never reconstruct event history or count decisions itself.
type DecisionContext struct {
    State         *pb.GameState
    Seat          uint32
    DecisionIndex uint64               // room-owned per-game counter
    Events        []engine.PublicEvent // snapshot COPY of game.PublicEvents(), RAW (unwindowed)
}
// The context carries the RAW event snapshot; each policy applies its OWN
// declared contract (window, version) to it. The room never knows or
// hardcodes any policy's window (Codex correction 1).

// ContextPolicy is the additive capability interface. bot.Policy is
// UNCHANGED (heuristic + training-side callers untouched).
type ContextPolicy interface {
    ChooseActionCtx(ctx *DecisionContext) *pb.PlayerAction
}
```

- The room (internal/api/room.go): where it currently calls
  `BotPolicy.ChooseAction(state, seat)`, it type-asserts `ContextPolicy`
  first; if implemented, it builds the context (copying the event slice)
  and calls `ChooseActionCtx`. Per-seat policies get the same treatment.
- `HTTPPolicy` implements `ContextPolicy`; its legacy `ChooseAction`
  remains (delegates with an empty context) for compatibility. The policy
  OWNS its window/contract: configured at construction (backend env) and
  validated against the policy server's `/healthz` (window + contract
  version must match) at startup and on reload.
- New exported encoder: `rl.EncodeObservationWithEvents(state, seat,
  decisionIndex, events, window)` — thin wrapper over the internal
  `encodeObservation` (nil-oracle), keeping the legality chokepoint single.

### Event contract v1

Constants beside the codec (`internal/rl/eventcodec.go`, mirrored in
`ai/src/fh_mahjong_ai/events.py`):

```
EventContractV1 = 1
window            = policy-declared (iter_075: 128; ≤ MaxEventHistoryWindow)
truncation        = tail (newest events kept)
padding           = zero tail-padding + explicit count
seats             = observer-relative (codec bit layout, wire-stable)
reset             = per round (log cleared at round start)
```

The contract version rides in the `/act` payload and in `/healthz`; a
version mismatch is a fail-closed error on both sides.

## 2. Wire + Python serving

**`/act` payload (additive, backward compatible), COMPACT form (Codex
correction 2):** gains `event_history` (uint32 array holding exactly the
tail-windowed events actually present: `len(event_history) == event_count
<= event_window` — a valid early-round short history is NEVER an error),
`event_count`, `event_window`, `contract_version`. Python pads to the
model window internally. The currently-deployed old-champion
server ignores unknown JSON fields (forward compat during shadow); the
NEW server:

- window-0 model → fields ignored (old champion keeps serving unchanged);
- event model + MISSING fields, `len(event_history) != event_count`,
  `event_count > event_window`, window != the model's, or wrong contract
  version → HTTP 400 with a reason, NEVER a silent zero-history
  inference (short-but-consistent histories are valid);
- heuristic fallback on the Go side stays the safety net in production
  play, but §5's parity/smoke/shadow gates require ZERO fallbacks.

**Metadata-authoritative loading:** `infer_model_config`'s B2b refusal
(B2b round-4 guard) is replaced by reconstruction from checkpoint
metadata. B2c extends the pinned block to the COMPLETE ModelConfig (all
architecture fields, not just the four B2b flags) at train/save time for
new checkpoints, keeping the four-flag `metadata.b2b` fallback for the
already-frozen iter_075; reconstructed configs are CROSS-CHECKED against
the checkpoint's tensor shapes and fail closed on any mismatch, and
B2b-module keys WITHOUT usable metadata still fail closed. `CheckpointPolicy` threads events into every forward
(`evaluate_batch` + single-act paths) exactly like eval's
`TorchGreedyPolicy` (tail-window + length). The B2b eval-CLI fail-fasts
for sampled/search paths stay (still B2c-out-of-scope).

**Ops surface:** `/healthz` gains checkpoint SHA-256, architecture summary
(from metadata), event contract version, event window.
`fh-mj-reload-policy` validates the incoming checkpoint (loadable +
metadata-compatible + same-or-declared window) BEFORE swapping the active
policy; an incompatible reload is rejected with the old policy intact.

## 3. Parity harness (HARD GATE)

Two layers, both required:

1. **Go feature parity** (`internal/bot/remote` or `internal/rl` test):
   for seeded engine states covering the agreed case matrix — no events /
   >128 events (truncation) / round transition (fresh log) / normal turn /
   interrupt decision — the DecisionContext-driven serving encoder output
   is BYTE-EQUAL (planes, scalars, mask, event history, length, metadata
   fields) to the eval path's `encodeObservation` for the same state.
2. **End-to-end action parity**: new CLI `fh-mj-serving-parity` with two
   modes (Codex correction 4): `--in-process` (CheckpointPolicy fed the
   /act-shaped payload; fast, runs in CI on mock/CPU) and `--endpoint URL`
   (the HARD-GATE mode: real HTTP POSTs to the actual /act endpoint of
   the running production image). Both drive seeded bridge states and
   compare against the eval stack (TorchGreedyPolicy on the bridge
   observation): exact feature equality and exact greedy action IDs;
   exact logits on the same hardware, tight tolerance (1e-4) + identical
   actions across CPU/GPU. Zero fallbacks tolerated. The runbook's hard
   gate is the --endpoint mode against the prod image with iter_075.

## 4. Review-tool replay

`internal/review/replay.go` replays matches through the engine, so the
event log regenerates naturally. It switches from `rl.EncodeObservation`
to `rl.EncodeObservationWithEvents(state, seat, idx, game.PublicEvents(),
window)` where `window` comes from the reviewed policy's declared window
(0 for the old champion → byte-identical behavior). The review HTTP client
batches through `/evaluate`, so that endpoint gains the same enriched
per-observation event fields (compact form) with identical validation.

## 5. Shadow mode (code in B2c, activation post-merge)

`bot.ShadowPolicy` wrapper: `{Primary bot.Policy/ContextPolicy, Shadow
ContextPolicy}`. The primary's action is returned to the game; an
IMMUTABLE DEEP CLONE of the context (proto.Clone(GameState) + copied
events — the room mutates the live state as play continues, so a shallow
snapshot would race; Codex correction 3) is enqueued to the shadow
asynchronously (bounded FIFO + single worker goroutine with clean
shutdown via Close(); drop-on-backpressure with a dropped-request
counter — the shadow must never block or affect play), and
the wrapper logs `{decision_index, primary_action, shadow_action,
agree?, shadow_latency_ms, shadow_error?}` per decision plus periodic
aggregates. Wired by env config: `RL_AGENT_SHADOW_POLICY_URL` (backend
constructs the wrapper when set). Disagreement is RECORDED, not judged —
two different policies are expected to disagree.

## 6. Runbook (post-merge, operational; user-approved light gate)

1. Deploy the NEW policy server image (loader + /act support) still
   pointing at the OLD champion — behavior byte-identical (window 0).
2. `fh-mj-serving-parity` against the prod image with iter_075 on sampled
   gate states — hard gate, zero fallbacks.
3. Serving smoke: iter_075 served locally, sampled gate states through
   the full HTTP path, legal actions, zero fallbacks.
4. **Shadow ≥ 50 games**: zero shadow-side errors/fallbacks, p95 shadow
   act latency < 200 ms; disagreement rate recorded to the progress note.
5. **Canary ≥ 20 private-room matches** with iter_075 controlling play:
   zero fallbacks, no crashes/incidents.
6. **Atomic switch**: manifest `current_chongci_reward_trained_best` →
   iter_075 entry (with metadata) + Zeabur deploy in one change;
   iter275 retained as rollback fallback. From then on iter_075 is the
   promotion anchor for future candidates.
7. Record every stage's outcome in the progress note.

## Out of scope

Search-path event support, training changes, any UI work, and Spec C /
ablations (deferred until deployment completes per the consult agreement).

## Risks

- Semantic drift between eval and serving event streams — the entire
  point of the hard parity gate; both layers must pass before any
  deployment step.
- Room-lock contention from context building — the event snapshot copy is
  a small memcpy (≤ ~200 events/round); shadow work is async and bounded.
- /act payload growth (≤ 128 uint32s ≈ 1 KB) — negligible.
- Old-champion regression via the new server image — step 1 of the
  runbook deploys the new image at window 0 first, which must be
  byte-identical (parity layer 1 covers window-0 states too).

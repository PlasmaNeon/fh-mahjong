# Paipu v2: per-decision provenance + supervision trace

**Date:** 2026-08-09 · **Status:** ratified (canonical Codex consult session, gpt-5.6-sol medium) · **Codename:** paipu-v2

## Why

The production-data audit (retirement item 4) found today's paipu records cannot support the
agreed training-data pipeline (human decision rows, BC baselines, agent attribution):

| Checklist item | v1 verdict |
|---|---|
| Checkpoint SHA / model identity | Partial — `policyId` is `<basename>@step<N>` only (`internal/bot/remote/identity.go`); the Python server publishes `checkpoint_sha256` on `/healthz` but Go never decodes it |
| Policy vs fallback identity | Partial — per-seat aggregate counts only; per-decision provenance and the 9 fallback reasons are never stored |
| Rules/build provenance | Partial — hardcoded `"fenghua"`, paipu schema `version: 1`; no server commit, no ruleset/catalog versions; raw proto enum ints embedded |
| Public event history | Reconstructable (wallSeed + actions; the review tool already replays) — acceptable |
| Legal-action context | **Missing** — no action mask stored, and **passes are not recorded at all** (the replayer infers implicit passes) |
| Seat ownership | Captured |
| Terminal outcomes | Partial — no completed/aborted marker inside the paipu JSON; placement only in `match_players` |

Missing labels cannot be backfilled: every match played before this ships is lost training
data. Therefore the **Champion Promotion shadow gate is paused** until v2 is merged, deployed,
and production-smoked.

## Ratified design

1. **Paipu schema `version: 2`.** `PaipuRound.Actions` stays the canonical replay event
   stream, byte-for-byte semantics unchanged — **no injected passes** there.
2. **New `PaipuRound.Decisions []PaipuDecision` supervision trace**, one row per
   player decision:
   - `index` (monotonic within the round), `seat`
   - `chosenId` — catalog action ID (via `rl.EncodeAction`)
   - `legalIds []int` — the **complete** legal action ID set at that decision point
     (via `rl.LegalActions`), captured at **every** decision — discard legality is central
     to BC, not just claim windows. Compact ID lists ≈ tens of KB/match: acceptable.
   - `source` — `human | remote | fallback | heuristic`
   - `fallbackReason` (only when `source == fallback`) — the existing 9-reason taxonomy
     from `internal/bot/remote/http_policy.go`
   - `checkpoint` (only when `source == remote`) — `{name, step, sha256}` taken from the
     **same `/act` response that produced the action** (see §4)
3. **Every successfully processed decision is recorded**, including **pass** (a declined
   claim window), discard, claim (chii/pon/kan), win, flower choice, haitei accept/refuse.
   Automatic draws and automatic flower handling are excluded (not decisions).
   Ordering contract: legal IDs are snapshotted **before** the action is processed; the
   decision row is appended only **after** `ProcessPlayerAction` (or the pass resolution)
   succeeds. Failed/illegal attempts are never recorded.
4. **Atomic per-decision checkpoint provenance.** `serve_policy.py` adds
   `checkpoint_sha256` (+ name/step, already present) to the **`/act` response**; the Go
   `HTTPPolicy` decodes it and returns action + provenance together through an additive
   policy-result capability. `/healthz` is NOT used for per-decision identity (a `/reload`
   can race an action). No mutable "last provenance" state.
5. **`actionCatalogVersion`** pinned in the paipu header alongside `version`. Action IDs are
   not durable labels without a pinned catalog. A new constant in `internal/rl` guards the
   catalog; any change to the action-ID encoding must bump it (enforced by a golden test).
6. **Match-level metadata** added to the paipu header:
   - `status` (`completed | aborted`) + `completionReason` (`match_end | drained | abandoned`)
   - `placements [4]` (competition ranking, same rule as `match_players.placement`)
   - `serverCommit` (ldflags-stamped; `"unknown"` when built without it)
   - `matchMode` (`classic | chongci`) + the chongci config (starting score, bust
     threshold, max hands)
   - `rulesetVersion`, `eventContractVersion` (the B2c event-encoding contract version),
     `protoRevision` (provenance for the embedded proto enum ints)
7. **Compatibility.** Per-seat aggregate counters (`remoteDecisions`, `fallbackDecisions`,
   `automatedDecisions`) and `policyId` are kept and still written; the `Decisions` trace is
   the authoritative provenance record. v1 paipus replay exactly as before.
8. **v2 replay cross-check.** When the review/replay driver consumes a v2 paipu it verifies
   the decision trace against reconstructed state — chosen ID must be legal in the
   reconstructed mask and `legalIds` must equal the reconstructed legal set — and **fails
   loudly** on any disagreement. v1 behavior (inference of implicit passes) is unchanged.
9. **Trusted read path for training.** Future training extraction reads only
   server-recorded `matches.paipu_json` v2 rows — never the `handleUploadPaipu`
   in-memory/`paipu_records` chain, which is admin-writable and outranks the DB on read.
   Documented in AGENTS.md now; enforced when the extractor is built.

Deferred (explicitly out of scope): proto-enum decoupling, `matches.replay_url` cleanup,
crash-recovery reconciler for `in_progress` rows, `paipu_records` vestige removal.

## Architecture

**Where the trace is captured: the room layer, not the engine.** The engine already records
the replay stream internally (`game.go` → `Recorder.Record*`) and stays
provenance-blind (it must not know about bots/HTTP). `internal/api/room.go` is the single
choke point where (a) every action enters (`Engine.ProcessPlayerAction` for humans at
`room.go:655`, the bot loop, and claim-window resolution), (b) provenance is known
(which seat is human, which policy served, whether fallback fired), and (c) pass
resolution happens (claim windows that time out / are declined never reach the engine).

- `PaipuDecision` + `Decisions` live in `internal/engine/paipu.go` as plain data with a
  `RecordDecision` method on `PaipuRecorder` (engine stays import-clean; `internal/rl`
  already imports engine, so catalog encoding happens at the call site in `internal/api`,
  which may import both).
- The room layer snapshots `rl.LegalActions(state, seat)` + encodes the chosen action
  before processing; appends after success.
- `HTTPPolicy` gains a provenance-carrying result (additive; existing `Policy` interface
  callers unaffected — e.g. a `DecideWithProvenance` extension used by the room layer;
  `ShadowPolicy` forwards the **primary's** provenance unchanged).
- `serve_policy.py` `/act` response gains `checkpoint_sha256`; contract validation and
  `fh-mj-serving-parity` accept the additive field.

## Error handling

- Legal-set snapshot failure (`rl.LegalActions` error) must never break live play: log,
  record the decision row with `legalIds: null` + `legalIdsError: true`, continue. The v2
  cross-check treats `legalIdsError` rows as replay-verified only for the chosen action.
- Decision-trace capture is skipped entirely when the recorder is nil (same rule the
  replay stream already follows).
- Missing `checkpoint_sha256` from an older policy server: record `checkpoint.sha256: ""`
  (never fail the action); the production smoke asserts it is non-empty end-to-end.

## Testing

- Engine/recorder: golden v2 paipu JSON round-trip; v1 fixtures still load (version 1,
  no `decisions` key → nil trace, no error).
- Room layer: simulated match covering all decision kinds (discard, chii/pon/kan, win,
  flower, haitei, **explicit pass on a declined claim window**, bot takeover) asserting
  trace contents, ordering contract, and source labels; fallback injection asserting
  `fallbackReason`; remote path asserting per-decision `{name, step, sha256}`.
- Catalog: golden test pinning `actionCatalogVersion` to the current encoding (fails on
  any drift without a version bump).
- Replay: v2 cross-check passes on recorded matches; corrupted-trace fixture fails loudly;
  v1 fixtures replay unchanged.
- Python: `/act` response includes `checkpoint_sha256`; parity tool accepts it.
- Full gates: `go test ./...`, `uv run --project ai pytest -q`, web CI unaffected.

## Rollout gate (blocks the Champion Promotion shadow phase)

Merge → deploy backend + candidate policy service → play one production smoke match with
an RL Agent seat → fetch its paipu and verify: explicit pass rows, full legal sets,
per-decision remote SHA, fallback reasons (if any), and `status: completed` all survive
persistence and reload. Only then does shadow-game accumulation resume.

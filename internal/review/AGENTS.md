# internal/review/

> Reconstructs reviewable decision points from a recorded paipu and
> critiques them against a served champion policy: paipu → decisions →
> `Report`.

## Overview

Given a completed `engine.Paipu`, `ExtractDecisions(paipu, eventWindow)`
re-drives every round through a fresh `engine.Game`, feeding back exactly the
actions the paipu recorded, and returns the catalog-indexed action
(`internal/rl`'s 204-action space) chosen at every point a seat had more than
one legal option. Every `Decision` also carries the 39ch visible
`pb.SeatObservation` the champion policy would have seen at that decision
(`rl.EncodeObservationWithEvents`, never the oracle variant), encoded against
a Chongci-context-dressed clone of the live replay state — see `context.go`
and Design Notes below. `eventWindow` (0 for a champion with no event
history) is forwarded verbatim to `EncodeObservationWithEvents` alongside the
live `r.game.PublicEvents()` log at that decision; with `eventWindow == 0`
this is byte-identical to the old `rl.EncodeObservation` call (see
`internal/rl/serving_parity_test.go`), so callers that don't serve an
event-aware champion just pass 0 and see no behavior change. This is the
input a later champion-policy critique pass scores against.

Any divergence between the paipu and what the engine reproduces — a bad wall
seed, a corrupted tile id, a rules-engine change that alters legality — aborts
replay with an error rather than silently emitting a wrong review. There is
no fallback or best-effort mode: `ExtractDecisions` either returns exact
decisions for the whole paipu or an error.

`BuildReport` (report.go) takes those decisions, batches their observations
through a `PolicyClient` (client.go's `HTTPPolicyClient` POSTs
`{baseURL}/evaluate` in chunks of 256), and assembles a `Report`: per-decision
legal-action probability distributions plus per-seat rollups. Like
`ExtractDecisions`, it never returns a partial report — any extraction or
evaluation failure aborts with an error and a nil `*Report`.

## Key Files

- **replay.go** — `Decision`, `ExtractDecisions`, and the whole replay
  driver. Depends only on `internal/engine` (state machine), `internal/rl`
  (`LegalActions`/`EncodeAction`/`DecodeActionID`, the exported catalog
  wrappers added for this package), `internal/rules` (`FenghuaRuleset`, to
  construct a fresh `engine.Game`), and `internal/tiles` (tile/action
  cloning, face-key comparison). It must not fork rules or state-transition
  logic — every mutation goes through `engine.Game.ProcessPlayerAction` /
  `ResolveInterrupts`, never a re-implementation.
- **context.go** — `isChongciPaipu` and `reviewState`, the encode-time
  context normalization described below.
- **client.go** — `PolicyClient` interface, `PolicyResult`,
  `CheckpointInfo`, and `HTTPPolicyClient` (`NewHTTPPolicyClient(baseURL,
  eventWindow)` — no auth token, equivalent to
  `NewHTTPPolicyClientWithToken(baseURL, eventWindow, "")` — or
  `NewHTTPPolicyClientWithToken(baseURL, eventWindow, token)` for an
  authenticated policy server). Mirrors `internal/bot/remote.HTTPPolicy`'s `/act` request
  encoding (`seat`, `planes`, `scalars`, `action_mask` as ints) but batches
  many observations per `/evaluate` request instead of one, chunking at
  `evaluateChunkSize` (256) and preserving order across chunks. Every chunk
  must report the same `checkpoint_path`/`checkpoint_step` — a mismatch (a
  checkpoint hot-swapped mid-review) is a hard error, never a
  mixed-champion report. Any non-200 response, `"error"` field, or
  per-chunk result-count mismatch aborts the whole `Evaluate` call.
  With `eventWindow > 0`, every observation in the request also gains
  `event_history`/`event_count`/`event_window`/`contract_version`
  (`rl.EventContractV1`) — the compact fields the Python `/evaluate`
  endpoint requires per-observation once the served model's
  `event_window > 0` (see `ai/src/fh_mahjong_ai/scripts/serve_policy.py`'s
  `observation_from_json`). These fields use pointer types
  (`*int`/`*uint32`) with `json:",omitempty"` so a nil pointer (the
  `eventWindow == 0` case) drops the key entirely, keeping the wire format
  byte-identical to before Task 6 — as opposed to plain zero-valued ints,
  which `omitempty` would also drop even when `eventWindow > 0` and the
  count legitimately is 0. `event_history` itself uses the same
  `omitempty`-on-empty-slice trick so it is present only when
  `event_count > 0`.
  - **Bearer-token auth (adversarial round 19)**: when the client was built
    with a non-empty `token` (via `NewHTTPPolicyClientWithToken`),
    `evaluateChunk` sets an `Authorization: Bearer <token>` header on every
    `/evaluate` POST — required as of `serve_policy.py`'s `/evaluate`
    auth gate, which 403s any request without a matching header once
    `--evaluate-token`/`FH_MJ_EVALUATE_TOKEN` is configured server-side. An
    empty token attaches no header at all (never a header with an empty
    bearer value), keeping the wire format byte-identical to before this
    change for callers/tests against an unauthenticated policy stub.
    `internal/api/review.go`'s `handlePostReview` sources this token from
    the `POLICY_SERVER_TOKEN` env var.
  - **`CurrentCheckpointSha256()` (round 21, Finding 2)**: GETs
    `{baseURL}/healthz` (same bearer-token convention as `/evaluate`; a
    short 5s timeout independent of the 120s `/evaluate` client timeout)
    and returns the `checkpoint_sha256` the policy server is CURRENTLY
    serving. `("", err)` when healthz is unreachable, non-2xx, or its body
    isn't a genuine `"ok": true` envelope — callers treat this identically
    to `("", nil)` (healthz reachable but the server predates the field, a
    legacy `serve_policy.py`): both mean "sha unknown". `handlePostReview`
    uses this to key its cache lookup on the checkpoint actually serving
    right now instead of trusting the newest cached row regardless of
    promotion/reload/rollback since the last review.
- **report.go** — `Report`/`ReportDecision`/`ActionProb`/`SeatSummary`/
  `GapRef` (the frontend JSON contract — field names/types must stay
  verbatim, Tasks 6/7 depend on them) and `BuildReport(paipu, client,
  eventWindow)` (`eventWindow` is forwarded to `ExtractDecisions`; the
  caller is responsible for constructing `client` with the same window —
  see `internal/api/review.go`). `ErrUnreviewable`
  wraps `ExtractDecisions` failures so the review HTTP API (a later task) can
  map them to 422 instead of a generic 500. Per decision, `Probs` is filtered
  down to the observation's legal (`ActionMask == 1`) indices, sorted
  descending, and renormalized over that legal subset (a no-op guard — the
  policy server is expected to already zero illegal-action mass). Per-seat
  `TopGaps` are the 5 largest `Actions[0].Prob - ChosenProb` gaps, referencing
  global indices into `Report.Decisions`.
- **replay_test.go** — round-trip tests against heuristic-bot-generated
  paipu (classic single round, chongci multi-round) plus a corrupted-paipu
  divergence test, plus the observation context tests
  (`TestObservationsChongciContextClassic`,
  `TestObservationsChongciRealScores`). `generateHeuristicPaipu`/
  `driveGameWithHeuristics` mirror `cmd/rlpaipu/main.go`'s drive loop; the
  chongci ready-ack flow mirrors `internal/rl/env.go`'s
  `readyAllPlayersForNextRound` (derives a fresh wall seed per hand before
  the final per-round ready ack).
  `TestExtractDecisionsEventWindowZeroMatchesLegacy` /
  `TestExtractDecisionsEventWindowPlumbed` cover Task 6's replay-side
  contract: `eventWindow == 0` produces empty `EventHistory`/zero
  `EventHistoryWindow` on every decision (regression bar); `eventWindow ==
  8` threads through to every decision's observation (bounded history,
  correct window field, and at least one non-empty history — proving
  `game.PublicEvents()` is really reaching the encoder, not silently
  dropped).
- **replay_v2_test.go** — the paipu v2 decision-trace cross-check tests.
  `generateHeuristicPaipuV2`/`driveGameWithHeuristicsTraced` are
  `generateHeuristicPaipu`'s trace-recording twin: they snapshot a
  `engine.PaipuDecision` (legal ids + chosen catalog id, PRE-action) for
  every action fed to the engine except READY, mirroring
  `internal/api/room_decisions.go`'s `snapshotDecision`/`recordDecision`
  (this package cannot import `internal/api` — cycle). Coverage: a
  well-formed v2 paipu replays clean; a tampered `ChosenID` and a corrupted
  `LegalIDs` each abort loudly; a fabricated extra row is caught at round
  end; a trace-stripped v2 paipu produces decisions identical to the v1
  paipu of the same seed (zero behavior change for v1);
  `TestReplayV2CrossCheckAlignsReorderedWindows` pins the seeds whose
  interrupt windows are recorded in a different order than they are
  reconstructed (see Design Notes).
- **report_test.go** — `TestBuildReportAgainstStubServer` runs a full
  heuristic-bot paipu through `BuildReport` against an `httptest.Server`
  stub that returns a uniform distribution over legal actions, verifying the
  report's shape (4 seats, sorted+renormalized legal actions, chosen-prob
  matches the known uniform value). `TestBuildReportServerErrorReturnsNoPartialReport`
  checks a server error aborts with no partial report.
  `TestBuildReportEventWindowZeroPayloadUnchanged` /
  `TestBuildReportEventWindowEightEnrichesPayload` cover Task 6's
  client-side contract: with `eventWindow == 0`, no observation in the
  batched `/evaluate` request carries any of the four compact
  event-history JSON keys (regression bar); with `eventWindow == 8`, every
  observation carries `contract_version == 1`, `event_window == 8`, and
  `event_count <= 8`, with `event_history` present (and length-matching)
  iff `event_count > 0`.
  `TestHTTPClientChunksBatches` calls `HTTPPolicyClient.Evaluate` directly
  with 600 synthetic observations against a stub that echoes a
  request-order-derived value, asserting exactly `ceil(600/256)=3` requests
  and that result order is preserved end to end across chunk boundaries.

## Design Notes

- **Per-round fresh classic game, not one long chongci match.** Each round
  in a paipu carries its own `WallSeed`/`Dealer`/`Deals`/`WildTiles`; nothing
  about a round's replay depends on the original match's `ChongciConfig`
  (which the paipu format does not record), so `replayRound` always
  constructs `engine.NewGame(..., engine.MatchOptions{})` (classic) and
  replays exactly one hand in it. This is what makes chongci paipu
  replayable at all without knowing the original config.
- **Natural vs. forced dealer roll.** `dealTiles()` only consumes an extra
  `mt.GenU32()` call for a *naturally* rolled dealer; calling
  `Game.SetNextDealer` before `Start()` skips that draw and desyncs the wall
  shuffle from a naturally-dealt hand. The first round of any paipu was
  always naturally rolled (nothing has run `finalizeRoundEnd` yet); every
  later chongci round had its dealer forced via `SetNextDealer` inside the
  previous round's `finalizeRoundEnd` (renchan or winner-seat succession), so
  replay must force it too. `replayRound` only calls `SetNextDealer` for
  `roundIdx > 0` — getting this wrong desyncs the deal from action 0 with no
  helpful error, since the wall shuffle silently diverges rather than
  erroring outright (verifyRoundSetup then catches the resulting deal
  mismatch, but the root cause is this asymmetry, not a corrupt paipu).
- **Round-start verification via a throwaway recorder.** `replayRound`
  attaches its own `engine.PaipuRecorder` before `Start()` purely to read
  back `CurrentRound().Deals`/`.WildTiles` — the exact snapshot `dealTiles()`
  captured before any flower-reveal or first-draw mutation touched
  `ClosedHand`. This avoids re-deriving the shuffle/deal logic in this
  package.
- **Decision-anchor semantics.** A turn decision (discard, tsumo, self-kan,
  flower-adjacent choices, haitei accept/refuse) anchors `ActionIndex` to the
  paipu action index it consumed. A declined-interrupt ("pass") decision has
  no paipu record of its own — the format only ever records the *winning*
  interrupt response, never a losing or absent one — so it anchors to the
  index of the discard that opened the interrupt window instead
  (`roundReplayer.lastDiscard`).
- **One decision per seat per interrupt window, not per pending seat.** When
  multiple seats can respond to a discard but only one call wins priority,
  the paipu records only the winner's action; a losing bidder's real
  historical choice is unrecoverable from the format. Replay therefore always
  feeds every non-matching pending seat an implicit pass — this is a genuine
  format limitation, not a driver bug.
- **Divergence-abort policy.** Every verification step (round setup, draw/
  flower system records, recorded-action legality, tile-fidelity) returns an
  error immediately on mismatch; `ExtractDecisions` never partially succeeds.
  If the engine turns out to auto-perform something the paipu also records
  (or vice versa), the fix belongs in this package's cursor handling, never
  in the engine.
- **Paipu v2 decision-trace cross-check (fail-loud).** When a round carries
  a v2 `Decisions` trace, every reconstructed decision point also verifies
  the matching trace row: (a) the row's `ChosenID` must be legal in the
  reconstructed legal set, and (b) its `LegalIDs` must equal the
  reconstructed legal-id set exactly. Rows flagged `LegalIDsError` are
  checked only as far as they were captured (`ChosenID == -1` = encode
  failed, nothing to verify; nil `LegalIDs` = enumeration failed, skip (b)).
  Any mismatch aborts with `paipu v2 decision cross-check failed: round %d
  decision %d seat %d: ...` — never warn-and-continue. A v1 paipu
  (`Decisions == nil`) skips all of this, byte-for-byte unchanged.
- **Trace-vs-reconstruction alignment (do not simplify to a plain cursor).**
  The trace and the reconstruction do not enumerate decision points the same
  way: the trace holds declined interrupts the Actions stream never records;
  the reconstruction holds points the trace never recorded (a timed-out
  interrupt window is not a decision); and *inside one interrupt window the
  two orders differ* — the room layer records rows in response order
  (seat-ascending for bots) while `stepWaitDiscards` always replays the
  winning call first and only then the other seats' passes. A strict
  "next row must belong to this seat" cursor therefore false-fails on
  ~10-18% of real games (10/55 and 12/120 in two heuristic sweeps).
  `crossCheckDecision` instead matches: the row at the cursor wins if it is
  this seat's, otherwise up to `maxTraceLookahead` (2 — an interrupt window
  holds at most 3 same-window rows total, and the cursor always sits on the
  window's oldest unmatched row, so at most 2 further rows can still belong
  to it) following rows are scanned for this seat's
  row *whose chosen id is legal here*. That legality gate is what stops an
  untraced timeout point from stealing the same seat's later row. Points
  with no match consume nothing; rows unmatched at round end are an error.
- **Exact-tile fidelity.** `internal/rl.LegalActions` collapses same-face
  duplicate tiles to one representative id (e.g. the lowest physical id for
  discards). `exactTileAction` clones the matched legal action and
  substitutes the paipu's recorded physical tile id(s) (verifying the seat
  still holds them), so replayed discard piles and melds match the paipu
  tile-for-tile even when the seat held two copies of the same face.
- **rl exports added for this package.** `internal/rl/action.go` gained two
  thin wrappers, `LegalActions` and `EncodeAction`, exposing the
  already-private `legalActionMap`/`encodeAction` so this package resolves
  recorded actions through the exact same legality map the RL bridge uses,
  instead of re-deriving it.
- **Encode-time Chongci-context normalization.** `replayRound` always
  constructs a fresh *classic*-mode `engine.Game` per round (see above), so
  `r.game.State` at decision time always has `MatchMode == CLASSIC` and every
  player's live `Score == 0` — nothing like the Chongci match context
  (`MatchMode`, `HandNum`/`ChongciConfig` progress, per-seat scores) the
  champion policy was trained on (`internal/rl/observation.go`'s
  `setMatchContextScalars`, scalars 42-57). `recordDecision` never encodes
  straight off `r.game.State`; it always calls
  `reviewState(r.game.State, r.paipu, r.roundIdx)` first, which
  `proto.Clone`s the state and overwrites *only* match-context fields
  (`MatchMode`, `HandNum`, `ChongciConfig`, `Players[*].Score`) — it must
  never touch hand/discard/meld/wall state, since the mask and the
  hand-shape planes/scalars must stay faithful to what actually happened.
  - **Classic paipu → "final hand of an all-tied Chongci match."** A classic
    paipu (`isChongciPaipu` returns false: every round's recorded
    `StartingScores` are all-zero) has no real Chongci context to recover,
    so `reviewState` presents it as the *final* hand of a Chongci match with
    every seat's score equal to a nominal `defaultChongciStartingScore`
    (25000): `HandNum == MaxHands` (progress scalar 43 = 1, remaining scalar
    44 = 0) and equal scores (rank scalar 45 = 1.0, gap scalars = 0). This
    was a deliberate product decision (not something recoverable from the
    paipu), made so the champion — trained exclusively on Chongci context —
    is never fed a nonsensical all-zero-score classic context it has never
    seen.
  - **Chongci paipu → real per-round context.** A chongci paipu
    (`isChongciPaipu` true) carries real starting scores per round
    (`PaipuRound.StartingScores`), so `reviewState` sets each seat's `Score`
    to `paipu.Rounds[roundIdx].StartingScores[seat]`, `HandNum` to
    `roundIdx+1` (paipu round indices are 0-based; `engine.Game.HandNum` is
    1-based — "East 1" starts at `HandNum: 1`, see `game.go` `NewGame`), and
    `ChongciConfig.StartingScore` from round 0's recorded starting score.
  - **`MaxHands` approximation.** The paipu format never records the
    original match's `ChongciConfig.MaxHands` cap, so both branches
    approximate it as `len(paipu.Rounds)` — the number of hands the match
    actually played. This is exact for a match that ran to its natural
    `MaxHands` limit and only an approximation (a lower bound) for one that
    ended early (e.g. a bust-out). Revisit if a future paipu format version
    starts recording the original `ChongciConfig`.

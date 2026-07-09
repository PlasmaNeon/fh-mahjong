# internal/review/

> Reconstructs reviewable decision points from a recorded paipu, as the
> foundation for post-game critique (paipu → decisions → champion critique).

## Overview

Given a completed `engine.Paipu`, `ExtractDecisions` re-drives every round
through a fresh `engine.Game`, feeding back exactly the actions the paipu
recorded, and returns the catalog-indexed action (`internal/rl`'s 204-action
space) chosen at every point a seat had more than one legal option. This is
the input a later champion-policy critique pass scores against (`Decision`
currently has no `Observation`; that lands in Task 2 — the field exists now
so downstream code can be written against a stable shape).

Any divergence between the paipu and what the engine reproduces — a bad wall
seed, a corrupted tile id, a rules-engine change that alters legality — aborts
replay with an error rather than silently emitting a wrong review. There is
no fallback or best-effort mode: `ExtractDecisions` either returns exact
decisions for the whole paipu or an error.

## Key Files

- **replay.go** — `Decision`, `ExtractDecisions`, and the whole replay
  driver. Depends only on `internal/engine` (state machine), `internal/rl`
  (`LegalActions`/`EncodeAction`/`DecodeActionID`, the exported catalog
  wrappers added for this package), `internal/rules` (`FenghuaRuleset`, to
  construct a fresh `engine.Game`), and `internal/tiles` (tile/action
  cloning, face-key comparison). It must not fork rules or state-transition
  logic — every mutation goes through `engine.Game.ProcessPlayerAction` /
  `ResolveInterrupts`, never a re-implementation.
- **replay_test.go** — round-trip tests against heuristic-bot-generated
  paipu (classic single round, chongci multi-round) plus a corrupted-paipu
  divergence test. `generateHeuristicPaipu`/`driveGameWithHeuristics` mirror
  `cmd/rlpaipu/main.go`'s drive loop; the chongci ready-ack flow mirrors
  `internal/rl/env.go`'s `readyAllPlayersForNextRound` (derives a fresh wall
  seed per hand before the final per-round ready ack).

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

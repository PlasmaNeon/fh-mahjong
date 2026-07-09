# internal/review/

> Reconstructs reviewable decision points from a recorded paipu, as the
> foundation for post-game critique (paipu → decisions → champion critique).

## Overview

Given a completed `engine.Paipu`, `ExtractDecisions` re-drives every round
through a fresh `engine.Game`, feeding back exactly the actions the paipu
recorded, and returns the catalog-indexed action (`internal/rl`'s 204-action
space) chosen at every point a seat had more than one legal option. Every
`Decision` also carries the 39ch visible `pb.SeatObservation` the champion
policy would have seen at that decision (`rl.EncodeObservation`, never the
oracle variant), encoded against a Chongci-context-dressed clone of the live
replay state — see `context.go` and Design Notes below. This is the input a
later champion-policy critique pass scores against.

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
- **context.go** — `isChongciPaipu` and `reviewState`, the encode-time
  context normalization described below.
- **replay_test.go** — round-trip tests against heuristic-bot-generated
  paipu (classic single round, chongci multi-round) plus a corrupted-paipu
  divergence test, plus the observation context tests
  (`TestObservationsChongciContextClassic`,
  `TestObservationsChongciRealScores`). `generateHeuristicPaipu`/
  `driveGameWithHeuristics` mirror `cmd/rlpaipu/main.go`'s drive loop; the
  chongci ready-ack flow mirrors `internal/rl/env.go`'s
  `readyAllPlayersForNextRound` (derives a fresh wall seed per hand before
  the final per-round ready ack).

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

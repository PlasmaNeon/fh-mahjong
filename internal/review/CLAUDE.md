# internal/review/

> Replays a paipu into decision points and critiques them with a served policy:
> paipu → decisions → `Report` (policy) → study (per-action evaluation and risk).

Feature overview and metric definitions: [`docs/replay-review.md`](../../docs/replay-review.md).

## Key files

- **replay.go** — `ExtractDecisions(paipu, eventWindow)`: re-drives every round through a fresh
  `engine.Game`, feeding the recorded actions, and returns each point where a seat had more than
  one legal option, with its catalog-indexed choices and the public observation
  (`rl.EncodeObservationWithEvents`, never oracle planes). Any divergence aborts; there is no
  partial result. Depends on `engine`, `rl` (legality and encoding), `rules` (to build a game), and
  `tiles`.
- **chongci_context.go** — `isChongciPaipu`, `reviewState`: restores match context for encoding
  (see below).
- **policy_client.go** — `PolicyClient` and `HTTPPolicyClient`: batches observations to
  `/evaluate` in chunks of 256, preserving order. Every chunk must report the same checkpoint
  (a mid-review swap is an error). With `eventWindow > 0` each observation carries
  `event_history`/`event_count`/`event_window`/`contract_version`; at window 0 those keys are
  omitted entirely. Optional bearer token. `CurrentCheckpointSha256()` reads `/healthz` (5 s
  timeout); an error and an unreported sha both mean "unknown".
- **report.go** — `Report` and `BuildReport(paipu, client, eventWindow)`: per-decision legal
  action probabilities (filtered, sorted, renormalized) and per-seat summaries with the five
  largest gaps. JSON field names are a contract with `web/src/features/replay/`. Extraction
  failures wrap `ErrUnreviewable` (→ HTTP 422).
- **study.go** — `BuildStudy` (schema 2): evaluates every legal action on paired unseen worlds
  under the reviewed checkpoint through the round's terminal payout. Defaults: 32 worlds, 128
  risk worlds, seed 20261004, 512 rollout decisions; reconstruction bounded to 4096 decisions.
  Results are mean payout and standard error in Fenghua points. Completed chunks checkpoint and
  are identity-checked on resume.
- **risk.go** — public-information risk: uniform unseen allocations (respecting auto-revealed
  flowers) scored with the authoritative rules; per-opponent and joint ron frequency, contributor
  patterns, pre-draw tsumo opportunity (excluding ordinary flowers; draw source labelled). Zero
  hits do not prove safety.
- **import.go** — validates native Fenghua v1/v2 uploads before any model work (operations,
  source seats, tile ids, envelope size). A standard wild's id must match its face; flower wilds
  are accepted by face.
- **reviewtest/** — the shared `/evaluate` stub for tests.

Decision anchors: a decision's `positionIndex` is the last applied action before the choice;
responses to one discard share a position but have separate decision ids
(`positions_test.go`).

## Design rules

- **One fresh classic game per round.** Each round carries its own seed, dealer, deals, and wilds,
  and the paipu does not record the match's `ChongciConfig`, so each round replays alone.
- **Dealer roll.** A naturally rolled dealer consumes one extra RNG draw; a forced one
  (`SetNextDealer`) does not. The first round and every classic round roll naturally; later
  Chongci rounds force the dealer. `verifyRoundSetup` catches a mismatch through the deal.
- **Fail loud.** Setup, system draws, action legality, tile fidelity, and the v2 trace are all
  verified; any mismatch aborts. If the engine and paipu disagree about an automatic action, fix
  the cursor handling here, never the engine.
- **Passes.** The v1 format records only the winning interrupt response, so other pending seats
  are fed an implicit pass (`inferred`). With a v2 trace, a seat's recorded choice is used
  (`recorded`); a losing bidder's recorded pon is never reported as a pass.
- **v2 trace alignment.** Rows and reconstruction enumerate points differently (traced declined
  interrupts, untraced timeouts, and response order within a window). `crossCheckDecision` takes
  the row at the cursor if it is this seat's, else scans up to 2 rows ahead for this seat's row
  whose chosen id is legal here. Unmatched rows at round end are an error. Do not simplify this to
  a strict cursor: it false-fails on 10–18% of real games.
- **Exact tiles.** `rl.LegalActions` collapses same-face copies; `exactTileAction` substitutes the
  recorded physical ids so replayed rivers and melds match tile for tile.
- **Chongci context.** Encoding always goes through `reviewState`, which clones the state and
  overwrites only `MatchMode`, `HandNum`, `ChongciConfig`, and seat scores. Chongci paipu use each
  round's recorded starting scores (`HandNum` = round index + 1); classic paipu are presented as the
  final hand of an all-tied Chongci match (nominal score 25000). `MaxHands` is approximated as the
  number of rounds played. v2 metadata, when present, is used instead.
- No privileged critic value is used for action evaluation.

## Tests

Round-trip tests against heuristic paipu (classic and Chongci), corrupted-paipu and tampered-trace
aborts, event-window plumbing, reordered interrupt windows, report shape against a stub server,
study evaluation and resume, and anchors. The real-checkpoint smoke uses `FH_REVIEW_SMOKE_URL`.

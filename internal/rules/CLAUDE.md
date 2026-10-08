# internal/rules/

> The Fenghua (奉化) ruleset plugin: wall, legality, interrupt priority, hand evaluation, scoring,
> payouts. Implements `engine.RuleEngine`.

The rules themselves: [`docs/rules/official-rules.md`](../../docs/rules/official-rules.md) and
[`docs/rules/rules.md`](../../docs/rules/rules.md).

## Key files

- **patterns.go** — the 41 stable pattern ids (`Pattern*`, e.g. `PatternPureOneSuit =
  "pure_one_suit"`) and the id → display-name registry. `NewScoreEntry(id, points)` is the only
  way to build a `ScoreEntry`. `rewardPatternIds` marks bonuses (flowers, kong completions) that
  do not count toward the 4-point ron minimum.
- **fh.go** — `FenghuaRuleset`:
  - `GetInitialWall()` — 144 tiles: 4 × (1–9m, 1–9p, 1–9s, 1–7z) + 8 unique flowers.
  - `EvaluateHand()` → (score, breakdown, canWin): a staged pipeline (base and wild bonuses →
    best structural route → honor/suit extremes → flowers → dragons/winds → kong flags → ron
    minimum). Entry order is user-visible. Routes: Independence (base 50 + bonuses), Seven Pairs
    (150 straight / 50 wild + bomb bonuses), Standard (4 melds + pair); the best route wins.
    Ron-only gates live here: the 4-point minimum and Wild Loner (大吊车有搭), which may only win
    by tsumo.
  - Live tsumo scoring infers the winning tile from `DrawnTileId` when called with a 14-tile hand
    and no `winTile`, so wait bonuses still apply.
  - `CalculatePayouts()` — tsumo: each loser pays S×2; ron: discarder S×2, others S×1.
  - `GetValidActions()` — discard, kan, tsumo for the active player. Kan and tsumo require
    `DrawnTileId != nil`, so neither is offered right after a chii/pon.
  - `GetValidInterrupts()` — ron, kan, pon, chii for the other seats.
  - `ResolveInterruptPriority()` — ron (4) > kan (3) > pon (2) > chii (1); ties by ascending seat.
  - `tryRunsCovering` is the single run search behind win shapes and Common Win; a wild fills any
    run position (8m9m+W is 7-8-9).
- **shanten/** — route-by-route shanten and discard analysis.

## Invariants

- Imported by the engine only through `RuleEngine`.
- Normal win shapes need `len(fullHand) + 3·len(openMelds) == 14`; a kan counts as one three-tile
  meld because its replacement draw restores the concealed count. Eight Flowers is the one
  incomplete-hand exception.
- Wilds are jokers only in the concealed hand; in calls, melds, and discards they are face value.
- Four Flowers (四花) needs a complete group (春夏秋冬 or 梅兰菊竹). Own Flower maps both groups
  onto seats with `flowerSeatWind() = ((value-1) % 4) + 1`; never compare a raw flower value with
  `SeatWind`.
- Scoring is invariant under suit permutations, rank reversal, and dragon permutations
  (checked on rollout wins in `internal/rl/observation_symmetry_test.go`).
- `tileToIndex` returns 0 for flowers and its callers index unguarded; do not replace it with
  `tiles.Index34`, which returns −1.
- Every hand-evaluation change gets a case in `fh_test.go`.
- Pattern names are bilingual (e.g. "Common Win (朋胡)"); logic keys off ids only.

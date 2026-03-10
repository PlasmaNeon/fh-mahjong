# rules/

> Fenghua (奉化) ruleset plugin — full hand evaluation, scoring, and payout logic.

## Overview

This package implements `HometownRuleset`, the Fenghua Mahjong ruleset plugin that satisfies the `core.RuleEngine` interface. It contains all region-specific logic: tile deck composition, DFS/DP backtracking hand evaluation for 35+ scoring patterns, wild tile handling, payout calculation, and action/interrupt validation. This is the most complex package in the codebase.

## Key Files

- **fh.go** — `HometownRuleset` struct implementing all `RuleEngine` methods:
  - `GetInitialWall()` — 144 tiles: 4×(1-9m, 1-9p, 1-9s) + 4×(1-7z) + 8 unique flower tiles (1=Spring, 2=Summer, 3=Autumn, 4=Winter, 5=Plum, 6=Orchid, 7=Chrysanthemum, 8=Bamboo)
  - `EvaluateHand()` — Returns (score, []ScoreEntry breakdown, canWin). Evaluates three mutually exclusive routes:
    1. **Independence** (大大胡): 14 disconnected tiles, base 50 + stackable bonuses
    2. **Seven Pairs** (七对): 7 pairs, straight (150) or wild (50) + bomb bonuses
    3. **Standard**: 4 melds + pair, checks Common Win, All Pung, Loner, suit patterns, honor patterns, kong bonuses, dragon/wind pungs, flower bonuses, wait patterns
  - Live tsumo scoring can infer the winning tile from `state.Players[playerSeat].DrawnTileId` when callers pass a 14-tile hand with `winTile=nil`, so wait-pattern bonuses still apply in round results
  - `CalculatePayouts()` — Tsumo: 3 losers pay S×2; Ron: discarder pays S×2, others pay S×1
  - `GetValidActions()` — Discard, Kan, Tsumo for active player. Non-wild flower handling is owned by `core.Game`; revealable flowers are auto-revealed before valid actions reach the client, while wild flowers remain in the closed hand
  - `GetValidInterrupts()` — Ron, Kan, Pon, Chii for other players
  - `ResolveInterruptPriority()` — Ron(4) > Kan(3) > Pon(2) > Chii(1)
  - Helper functions: `isAllPung`, `isAllChow`, `isPureOneSuit`, `isMixedOneSuit`, `isIndependence`, `isSevenPairs`, `hasAllSevenHonors`, `isMissingASuit`, `tilesToTehai34`, `checkChowOnlyMelds`, etc.

- **fh_test.go** — Extensive test suite covering all 35+ patterns:
  - CommonWin, Independence, SevenPairs, Loner, AllPung, MixedOneSuit, PureOneSuit
  - DragonPung, WindPung, OwnFlower, KongBonuses, WaitPatterns, PairCall
  - Wild tile injection (0/1/2/3 wilds), Tame Wild
  - FlowerBonus (4 flowers, 8 flowers)
  - InterruptPriority resolution

## Architecture Notes

- Implements `core.RuleEngine` — imported by `core/` via interface, never directly.
- Scoring uses a route-based approach: Independence, Seven Pairs, and Standard are evaluated independently; the highest-scoring route wins.
- Wild tiles (搭) are tracked via hash maps. The `tilesToTehai34` helper converts tile lists to a 34-element frequency array for DP evaluation.
- The live game sometimes evaluates tsumo hands as 14-tile concealed hands with no explicit `winTile`; wait-pattern scoring therefore depends on `DrawnTileId` being carried in `PlayerState`.
- Ron requires ≥4 points total; Tsumo has no minimum.
- All pattern names include Chinese (e.g., "Common Win (朋胡)") for bilingual display.

# core/

> Game state machine engine and the RuleEngine interface contract.

## Overview

This package contains the ruleset-agnostic game driver (`Game` struct) and the interface that all ruleset plugins must implement (`RuleEngine`). The `Game` struct manages the full lifecycle of a single match: wall initialization, dealing, turn rotation, interrupt resolution, and round-end handling. It delegates all rule-specific logic (hand evaluation, scoring, valid actions) to the injected `RuleEngine`.

## Key Files

- **game.go** — `Game` struct: central state machine
  - `NewGame(ruleset)` — Constructor, injects a RuleEngine
  - `ProcessPlayerAction(seat, action)` — Main entry point from network layer
  - `handleActiveTurnAction()` — Discard, Kan, Flower Reveal, Tsumo
  - `handleInterruptAction()` — Pon, Chii, Ron during WAIT_DISCARDS
  - `ResolveInterrupts()` — Priority resolution after timer/all responses. After Pon/Chii, calls `GetValidActions()` to populate valid actions for the claiming player
  - `ExecuteSystemDraw()` / `ExecuteDeadWallDraw()` — Wall draws. `ExecuteSystemDraw` clears all kong/flower bonus flags at start to prevent stale flags
  - `revealInitialFlowers(dealer)` — Auto-separates flower tiles from all players' hands after dealing. Loops through all 4 seats starting from dealer, moves flowers to `FlowerMelds`, draws replacements from dead wall. Called after `dealTiles()` and after dealer's 14th tile draw
  - `startNextRound()` — Reset for next round (keeps scores)
  - Kong/flower bonus flag lifecycle: `HasBloomingFlowerKong` set after flower reveal + dead wall draw; all flags cleared on next normal `ExecuteSystemDraw`
  - Private fields: `wall`, `wallIndex`, `deadWallIndex`, `interruptQueue`, `interruptTimer`

- **rules.go** — `RuleEngine` interface:
  - `GetInitialWall()` — Generate tile deck
  - `EvaluateHand()` → (score, breakdown, canWin)
  - `CalculatePayouts()` — Tsumo/Ron payment distribution
  - `GetValidActions()` — Legal moves for active player
  - `GetValidInterrupts()` — Legal steal actions for other players
  - `ResolveInterruptPriority()` — Pick winner among competing claims

- **mt19937.go** — Mersenne Twister PRNG for deterministic, reproducible wall shuffles (supports 108, 136, and 144 tile walls)
- **game_test.go** — Unit tests for game loop phases
- **dump_test.go** — Debug helpers

## Subdirectories

- **testdata/** — Binary seed files for deterministic test replays

## Architecture Notes

- **CRITICAL**: `core/` must NEVER import `rules/`. The dependency flows one way: `rules/` implements `core.RuleEngine`.
- `Game.State` is a `*pb.GameState` (Protobuf). All state mutations happen here; the API layer just serializes and broadcasts.
- The interrupt system uses a map queue + timer. The room layer starts the timer; `ResolveInterrupts()` can be called either when all responses arrive or when the timer fires.

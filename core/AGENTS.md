# core/

> Game state machine engine and the RuleEngine interface contract.

## Overview

This package contains the ruleset-agnostic game driver (`Game` struct) and the interface that all ruleset plugins must implement (`RuleEngine`). The `Game` struct manages the full lifecycle of a single match: wall initialization, dealing, turn rotation, interrupt resolution, and round-end handling. It delegates all rule-specific logic (hand evaluation, scoring, valid actions) to the injected `RuleEngine`.

## Key Files

- **game.go** — `Game` struct: central state machine
  - `NewGame(matchID, ruleset, MatchOptions)` — Constructor, injects a RuleEngine and optional match-mode config
  - Optional `Recorder` hook captures paipu events at authoritative game-engine action points
  - `SetWallSeed(seed)` — One-shot deterministic wall seed injection used by replay verification and the RL environment
  - `InterruptQueued(seat)` — Read-only helper for RL wrappers to see which WAIT_DISCARDS responses have already been submitted
  - `ProcessPlayerAction(seat, action)` — Main entry point from network layer
  - `handleActiveTurnAction()` — Discard, Kan, Flower Reveal, Tsumo
  - `handleInterruptAction()` — Pon, Chii, Ron during WAIT_DISCARDS
  - `ResolveInterrupts()` — Priority resolution after timer/all responses. After Pon/Chii, calls `GetValidActions()` to populate valid actions for the claiming player
  - `ExecuteSystemDraw()` / `ExecuteDeadWallDraw()` — Wall draws. `ExecuteSystemDraw` clears all kong/flower bonus flags at start to prevent stale flags
  - Draw-time flower handling is enforced in the game loop: any non-wild flower drawn from the live wall, dead wall, or accepted haitei is auto-revealed immediately, even if multiple revealable flowers are present
  - If a flower/kan supplementary dead-wall draw exhausts the wall, keep `PHASE_ROUND_END`; never restore `PHASE_PLAYER_TURN` with an empty valid-action set
  - Claim-time flower handling matches draw-time behavior: after a Chii/Pon handoff, any non-wild flowers already in the claimer's concealed hand are auto-revealed before valid actions are sent
  - `revealInitialFlowers(dealer)` — Auto-separates flower tiles from all players' hands after dealing. Loops through all 4 seats starting from dealer, moves flowers to `FlowerMelds`, draws replacements from dead wall. Called after `dealTiles()` and after dealer's 14th tile draw
  - `startNextRound()` — Reset for next round (keeps scores)
  - Kong/flower bonus flag lifecycle: `HasBloomingFlowerKong` set after flower reveal + dead wall draw; all flags cleared on next normal `ExecuteSystemDraw`
  - `GameState` now carries round dice details (`dice1`, `dice2`, `dice_sum`) and a live `wangpai_tiles_left` counter for frontend/debug visibility
  - Private fields: `wall`, `wallIndex`, `deadWallIndex`, `interruptQueue`, `interruptTimer`, `wallSeedOverride`

- **paipu.go** — Structured paipu recording support:
  - Paipu JSON DTOs for players, rounds, actions, melds, and results
  - `TileFromId()` to map engine tile IDs back to suit/value pairs for replay export
  - `PaipuRecorder` that tracks the canonical round flow directly from core engine events

- **rules.go** — `RuleEngine` interface:
  - `GetInitialWall()` — Generate tile deck
  - `EvaluateHand()` → (score, breakdown, canWin)
  - `CalculatePayouts()` — Tsumo/Ron payment distribution
  - `GetValidActions()` — Legal moves for active player
  - `GetValidInterrupts()` — Legal steal actions for other players
  - `ResolveInterruptPriority()` — Pick winner among competing claims

- **mt19937.go** — Mersenne Twister PRNG for deterministic, reproducible wall shuffles (supports 108, 136, and 144 tile walls)
  - `SeedFromUint64()` expands a compact uint64 seed into the full MT19937 state for RL/test callers, consuming both 32-bit halves from each SplitMix64 output
- **game_test.go** — Unit tests for game loop phases
- **dump_test.go** — Debug helpers

## Subdirectories

- **testdata/** — Binary seed files for deterministic test replays

## Architecture Notes

- **CRITICAL**: `core/` must NEVER import `rules/`. The dependency flows one way: `rules/` implements `core.RuleEngine`.
- `Game.State` is a `*pb.GameState` (Protobuf). All state mutations happen here; the API layer just serializes and broadcasts.
- Paipu recording lives in `core/` so replay exports observe the same authoritative transitions the live engine uses.
- The interrupt system uses a map queue + timer. The room layer starts the timer; `ResolveInterrupts()` can be called either when all responses arrive or when the timer fires.

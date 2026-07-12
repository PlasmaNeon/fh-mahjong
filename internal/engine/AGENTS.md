# internal/engine/

> Game state machine engine and the RuleEngine interface contract.

## Overview

This package contains the ruleset-agnostic game driver (`Game` struct) and the interface that all ruleset plugins must implement (`RuleEngine`). The `Game` struct manages the full lifecycle of a single match: wall initialization, dealing, turn rotation, interrupt resolution, and round-end handling. It delegates all rule-specific logic (hand evaluation, scoring, valid actions) to the injected `RuleEngine`.

## Key Files

- **game.go** — `Game` struct: central state machine
  - `NewGame(matchID, ruleset, MatchOptions)` — Constructor, injects a RuleEngine and optional match-mode config
  - `CloneForBranch()` — Isolated deterministic copy for RL what-if rollouts; drops recorder/timer so branch evaluation cannot mutate replay logs or schedule async work
  - Optional `Recorder` hook captures paipu events at authoritative game-engine action points
  - `SetWallSeed(seed)` — One-shot deterministic wall seed injection used by replay verification and the RL environment
  - `InterruptQueued(seat)` — Read-only helper for RL wrappers to see which WAIT_DISCARDS responses have already been submitted
  - `ProcessPlayerAction(seat, action)` — Main entry point from network layer
  - `handleActiveTurnAction()` — Discard, Kan, Flower Reveal, Tsumo
  - `handleInterruptAction()` — Pon, Chii, Ron during WAIT_DISCARDS
  - `ResolveInterrupts()` — Priority resolution after timer/all responses. After Pon/Chii, calls `GetValidActions()` to populate valid actions for the claiming player
  - `ExecuteSystemDraw()` / `ExecuteDeadWallDraw()` — Wall draws. `ExecuteSystemDraw` clears all kong/flower bonus flags at start to prevent stale flags
  - **Wall-consumption invariant**: dead-wall (kong/flower) replacement draws descend from the back and, once the wangpai is exhausted, cross past `wangpaiBoundary` into the live wall. `ExecuteSystemDraw` MUST skip any live-wall index already taken by a dead-wall draw (`isTileConsumedByDeadWall`) — otherwise the same physical tile is dispensed twice, producing a phantom duplicate tile id in a hand (corrupts hand counts/scoring and yields duplicate legal actions). Regression-gated by `internal/rl/kan_dup_repro_test.go`
  - Draw-time flower handling is enforced in the game loop: any non-wild flower drawn from the live wall, dead wall, or accepted haitei is auto-revealed immediately, even if multiple revealable flowers are present
  - If a flower/kan supplementary dead-wall draw exhausts the wall or ends a Chongci match, keep the terminal phase; never restore `PHASE_PLAYER_TURN` with an empty valid-action set, including interrupt-Kan claims
  - Claim-time flower handling matches draw-time behavior: after a Chii/Pon handoff, any non-wild flowers already in the claimer's concealed hand are auto-revealed before valid actions are sent
  - `revealInitialFlowers(dealer)` — Auto-separates flower tiles from all players' hands after dealing. Loops through all 4 seats starting from dealer, moves flowers to `FlowerMelds`, draws replacements from dead wall. Called after `dealTiles()` and after dealer's 14th tile draw
  - `startNextRound()` — Reset for next round (keeps scores)
  - Kong/flower bonus flag lifecycle: `HasBloomingFlowerKong` set after flower reveal + dead wall draw; all flags cleared on next normal `ExecuteSystemDraw`
  - `GameState` now carries round dice details (`dice1`, `dice2`, `dice_sum`) and a live `wangpai_tiles_left` counter for frontend/debug visibility
  - `PlayerState.LastDiscardFromDrawn`: public tsumogiri flag; true when the player's most recent discard was their just-drawn tile. Set in the discard handler; persists until their next discard (reset in `startNextRound`). It lives on the player, not on `ActiveDiscard`, because the common no-interrupt discard clears `ActiveDiscard` during the same turn-advance, before the state is broadcast
  - Private fields: `wall`, `wallIndex`, `deadWallIndex`, `interruptQueue`, `interruptTimer`, `wallSeedOverride`
  - `RedealUnseen(actingSeat, seed)` — search determinization: re-deals the 3 opponents' concealed hands + undrawn wall from the acting seat's unseen pool (seeded); visible state and wall geometry fixed; remaps opponents' `DrawnTileId` positionally and clears the interrupt queue (queued responses are hidden info). Also refreshes every non-acting seat's `ValidActions` against its new hand: at an open WAIT_DISCARDS window it recomputes interrupts via `Rules.GetValidInterrupts` (the exact `offerInterrupts` call), applying the same haitei Ron-only restriction via the shared `filterRonOnlyInterrupts` helper so a fork landing inside a haitei window never offers Chii/Pon/Kan; otherwise it clears them — stale interrupt options reference tiles the reshuffle moved, and serving one would corrupt the hand (phantom open meld appended without reducing the closed hand → duplicate tile ids). The refresh recomputes for EVERY non-acting seat regardless of whether its PRE-redeal `ValidActions` were empty: eligibility derives from the hidden hand, so gating on prior non-emptiness would leak the true hidden hands into which seats the rollout re-asks (a seat whose redealt hand newly gains a Ron/Pon/Kan MUST be admitted). A seat whose refreshed interrupts come back empty honestly drops out of the window. Guarded by `TestRedealUnseen_GainingEligibilityAdmitted`. The ACTIVE DISCARDER (`State.ActivePlayer`) is EXCLUDED from the open-window recompute and its `ValidActions` cleared even when its redealt hand matches its own discard: a player never interrupts its own discard (the live `offerInterrupts` always clears the discarder), and since `handleInterruptAction` counts every non-empty `ValidActions` toward window completeness, a phantom discarder interrupt would inflate the expected-response count into a window the live engine can never reach. This matters only when the search root ≠ discarder (the root is already skipped). Guarded by `TestRedealUnseen_DiscarderExcludedFromOpenWindow`. The acting seat's `ValidActions` are untouched (its hand did not move). Clone-only use (`CloneForBranch`).

- **paipu.go** — Structured paipu recording support:
  - Paipu JSON DTOs for players, rounds, actions, melds, and results
  - `PaipuPlayer` carries seat-composition labels for dataset use: `Kind` ("human"/"bot"), `Difficulty` ("heuristic"/"rl"), `PolicyID` (RL serving checkpoint identity). All `omitempty` — absent in old paipu, readers must treat absence as unknown
  - `TileFromId()` to map engine tile IDs back to suit/value pairs for replay export
  - `PaipuRecorder` that tracks the canonical round flow directly from core engine events; `AddPlayerInfo()` records a fully-labelled seat entry, `AddPlayer()` remains for callers without composition info

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

## Subdirectories

- **testdata/** — Binary seed files for deterministic test replays

## Architecture Notes

- **CRITICAL**: `internal/engine` must NEVER import `internal/rules/`. The dependency flows one way: `internal/rules/` implements `engine.RuleEngine`.
- `Game.State` is a `*pb.GameState` (Protobuf). All state mutations happen here; the API layer just serializes and broadcasts.
- Paipu recording lives in `internal/engine/` so replay exports observe the same authoritative transitions the live engine uses.
- The interrupt system uses a map queue + timer. The room layer starts the timer; `ResolveInterrupts()` can be called either when all responses arrive or when the timer fires.
  - **Test gotcha**: `handleInterruptAction()` only auto-resolves once *every* seat with valid actions has responded. A unit test that submits a single claim and starts from a random deal can flake: another seat may coincidentally hold a valid interrupt (e.g. a pon) on the discarded tile, so the lone claim stays queued in `PHASE_WAIT_DISCARDS` and never resolves. Such tests must drive resolution explicitly — see `resolveLoneClaim()` in `game_test.go`, which calls `ResolveInterrupts()` when still waiting (modeling timer expiry with the submitter as sole claimant). For tests asserting exact post-draw board state (wall count, supplement tile), pin the deal with `SetWallSeed(SeedFromUint64(n))`.

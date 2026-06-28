# proto/

> Protocol Buffer schemas — the single source of truth for all cross-language data structures.

## Overview

This directory contains the Protobuf `.proto` definitions and auto-generated Go bindings. Every data type used across Go backend, TypeScript frontend, and future Python AI pipeline is defined here. Changes to game data structures must start in `game.proto`, then regenerate bindings.

## Key Files

- **game.proto** — Core schema defining all game types:
  - `Suit` enum: SOU=1, PIN=2, MAN=3, JIHAI=4, FLOWER=5
  - `Tile`: id, suit, value, is_red
  - `ActionType` enum: DRAW, DISCARD, CHII, PON, KAN, TSUMO, RON, PASS, FLOWER_REVEAL, READY
  - `GamePhase` enum: INIT, DEAL, PLAYER_TURN, WAIT_DISCARDS, ROUND_END
  - Match-mode types: `MatchMode`, `ChongciConfig`, `PlayerStanding`, `MatchEndResult`
  - `GamePhase` adds `PHASE_MATCH_END` terminal value
  - `GameState`, `PlayerState`: full match state
  - `GameState` round-debug fields include `dice_sum`, individual `dice1`/`dice2`, `wangpai_stacks`, and live `wangpai_tiles_left`
  - `GameState.active_discard_from_drawn` (field 24): public, transient tsumogiri marker — true when `active_discard` was the discarder's just-drawn tile; kept in lockstep with `active_discard` via `setActiveDiscard`/`clearActiveDiscard` in `core/game.go`
  - `Meld`, `PlayerAction`: action/meld data
  - `ScoreEntry`, `PlayerPayout`, `RoundResult`, `RoundOutcome`: scoring, payouts, and compact RL round-result metadata
  - RL bridge messages:
    - `EnvConfig`, `SeatObservation`
      - `EnvConfig.match_mode` / `chongci_config` let training choose classic single-hand or Chongci multi-hand simulator mode
    - `EnvResetRequest` / `EnvResetResponse`
    - `EnvStepRequest` / `EnvStepResponse`
    - `BranchEvaluationRequest` / `BranchEvaluationResponse` / `BranchEvaluationResult` for exact same-state candidate-action rollouts through the Go RL bridge; `stop_at_round_end` provides practical hand-EV labels inside multi-hand Chongci contexts
    - `TrajectoryRequest`, `TrajectorySample`, `TrajectoryDataset`
      - `EnvResetResponse.round_outcome` / `EnvStepResponse.round_outcome` carry terminal round metadata when a round ends
      - `TrajectorySample.rewards` carries per-step rewards; `terminal_rewards` and `terminal_outcome` carry final round targets for offline warm-start consumers
- **game.pb.go** — Auto-generated Go bindings (do not edit manually)

## Regeneration Commands

Go bindings:
```bash
protoc --plugin=protoc-gen-go=$(go env GOPATH)/bin/protoc-gen-go --go_out=. --go_opt=paths=source_relative proto/game.proto
```

TypeScript/JS bindings (from project root):
```bash
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```

Python bindings:
```bash
mkdir -p ai/src/fh_mahjong_ai/generated
protoc --python_out=ai/src/fh_mahjong_ai/generated proto/game.proto
```

## Architecture Notes

- Proto enum names (CHII, PON, KAN) are kept as-is in generated code. Use chii/pon/kan only in comments and docs.
- `--null-semantics` is required for JS bindings so `optional` proto3 fields decode as `null` when unset (important for `drawn_tile_id` which can be `0`).
- Imported by: `internal/engine/`, `internal/rules/`, `internal/api/`, `cmd/`, `internal/rl/`, `web/src/proto/`, `ai/src/fh_mahjong_ai/generated/`.

# web/src/proto/

> Auto-generated Protobuf JavaScript/TypeScript bindings.

## Overview

Contains the JS/TS code generated from `proto/game.proto` by `protobufjs`. These files provide type-safe encoding/decoding of all game messages in the browser. Do not edit manually — regenerate from the proto source.

## Key Files

There is a **single** generated binding (protobufjs ES6) — `game.js` + `game.d.ts`.
Both runtime decode (`game.GameState.decode`) and all enum/type access go through
the `game` namespace, e.g. `game.Suit`, `game.ActionType`, `game.MeldDirection`.

- **game.js** — ES6 module with Protobuf message classes (encode/decode/verify) and enums
- **game.d.ts** — TypeScript type declarations for all Protobuf messages and enums
  - `GameState` bindings include round debug fields such as `dice_sum`, `wangpai_stacks`, plus per-die values and live `wangpai_tiles_left`

> Two earlier bindings were removed (2026-06): a ts-proto `game.ts` (only ever
> imported for enums, and it drifted out of sync — missing `Meld.added_tile_id`)
> and a protobufjs CommonJS `game_cjs.js` (imported nowhere). Do not reintroduce
> a second generator; keep one source of truth.

## Regeneration

From project root:
```bash
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```

## Architecture Notes

- `--null-semantics` flag is critical: ensures `optional` proto3 fields decode as `null` when unset (not default values). This matters for fields like `drawn_tile_id` where `0` is a valid tile ID.
- Imported as `import { game } from '../proto/game'` throughout the frontend (no extension; resolves to `game.js`/`game.d.ts`).
- Message classes: `game.GameState`, `game.PlayerAction`, `game.Tile`, `game.Meld`, plus RL bridge messages such as `game.TrajectorySample` with separate `rewards` and `terminalRewards` payloads and branch-evaluation messages for same-state RL counterfactual rollouts.

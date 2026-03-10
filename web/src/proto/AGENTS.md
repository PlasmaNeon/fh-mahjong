# web/src/proto/

> Auto-generated Protobuf JavaScript/TypeScript bindings.

## Overview

Contains the JS/TS code generated from `proto/game.proto` by `protobufjs`. These files provide type-safe encoding/decoding of all game messages in the browser. Do not edit manually — regenerate from the proto source.

## Key Files

- **game.js** — ES6 module with Protobuf message classes (encode/decode/verify)
- **game.d.ts** — TypeScript type declarations for all Protobuf messages
- **game.ts** — TypeScript enum definitions and helpers (if present)
- **game_cjs.js** — CommonJS version of the bindings
  - Current `GameState` bindings include round debug fields such as `dice_sum`, `wangpai_stacks`, plus per-die values and live `wangpai_tiles_left`

## Regeneration

From project root:
```bash
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```

## Architecture Notes

- `--null-semantics` flag is critical: ensures `optional` proto3 fields decode as `null` when unset (not default values). This matters for fields like `drawn_tile_id` where `0` is a valid tile ID.
- Imported as `import { game } from '../proto/game.js'` throughout the frontend.
- Message classes: `game.GameState`, `game.PlayerAction`, `game.Tile`, `game.Meld`, etc.

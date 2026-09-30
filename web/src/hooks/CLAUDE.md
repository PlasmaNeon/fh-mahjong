# web/src/hooks/

> Custom React hooks. The fixed-stage layout hook lives in `web/src/table/stage/`.

## Key Files

- **useMahjongWasm.ts** — Loads `mahjong.wasm` (built from `cmd/wasm`) with the Go runtime
  (`wasm_exec.js`) and exposes `mahjongGetValidActions` plus a ready flag.

  **Unreferenced.** No component imports it; the client takes legal actions from the server's
  `PlayerState.valid_actions`. Revive or delete it — do not assume client-side prediction exists.

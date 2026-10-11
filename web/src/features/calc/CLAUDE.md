# web/src/features/calc/

> Fenghua scoring calculator. Route: `/tools/calc`.

- **Calc.tsx** — the rules debugger: one targetable tile tray for hand, win tile, wild tile, and
  the active meld; renders inside `ToolsShell` with the scoped light tools theme.
- **calcHelpers.ts** — typed tile and meld drafts, notation parse/format (space-separated,
  collects all errors), meld validation, expected hand size, request builders.

## Notes

- `calcHelpers.ts` adapts `utils/tileModel.ts`; never re-implement `TILE_LIBRARY`, parsing, or
  suit ordering (`suitOrder` is the app's single ordering). Its `WIND_OPTIONS` is an English-only
  form-option list, not a duplicate of `utils/winds.ts`.
- Calls `POST /api/v1/tools/calc` (POST-only).
- Uses `theme/base.css` utility classes directly for its dense layout instead of typed primitives
  — a deliberate exception shared with `shanten/`.

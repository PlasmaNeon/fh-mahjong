# web/src/features/shanten/

> Shanten distance calculator tool. Route: `/tools/shanten`.

## Key Files

- **Shanten.tsx** — Shanten calculator UI with the shared Scoring/Shanten tabs (`theme/components/ToolTabs.tsx`) and one hand/wild targetable tray.
- **shantenHelpers.ts** — Shanten-specific helper utilities.

## Architecture Notes

- **`shantenHelpers.ts` is a thin adapter over `utils/tileModel.ts`** — same rule as `calc/`: no local `TILE_LIBRARY`, tile parsing, or suit ordering.
- The backend analysis comes from `internal/rules/shanten`, which also drives the heuristic bot — so a change in shanten semantics shows up both here and in bot play.
- Like `Calc.tsx`, this is an "advanced consumer" of `theme/base.css` utility classes rather than the typed primitives.
- UI spec: `worklog/specs/2026-05-15-shanten-calc-ledger-redesign.md`.

The tool now uses `ToolsShell` and the scoped Direct play light theme: plain shared navigation, blue controls and white work surfaces. Tool tabs identify the page; its accessible title is provided by the shell without an extra decorative heading or duplicate language toggle. Calculation and tile-editing state remain unchanged.

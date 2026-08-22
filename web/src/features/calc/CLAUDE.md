# web/src/features/calc/

> Fenghua hand calculator tool. Route: `/tools/calc`.

## Key Files

- **Calc.tsx** — Typed Fenghua rules debugger with one shared, targetable tile tray for hand, win tile, wild tile, and the active meld.
- **calcHelpers.ts** — Calculator-only helpers: typed draft models for tiles/melds, canonical tile notation parse/format helpers, meld validation, expected hand-size calculation, and request-payload builders.

## Architecture Notes

- **`calcHelpers.ts` is a thin adapter over `utils/tileModel.ts`.** Do not re-implement `TILE_LIBRARY`, tile parsing, or suit ordering here — `suitOrder(suit)` in the shared model is the single suit-ordering function for the whole app.
- `Calc.tsx` is intentionally self-contained and shares no state with gameplay pages; it is a rules-debugging tool, not part of the live match flow.
- Sends `POST /api/v1/calc`. A `GET` on that path returns 404 — the endpoint is POST-only.
- Uses the utility classes from `theme/base.css` directly rather than composing typed primitives; it and `Shanten.tsx` are the deliberate "advanced consumer" exceptions for dense tool layouts.
- UI spec: `worklog/specs/2026-05-15-shanten-calc-ledger-redesign.md`.

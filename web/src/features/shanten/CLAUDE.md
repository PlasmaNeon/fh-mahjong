# web/src/features/shanten/

> Shanten calculator. Route: `/tools/shanten`.

- **Shanten.tsx** — the calculator, with the shared Scoring/Shanten tabs (`ToolTabs`) and one
  hand/wild tray, inside `ToolsShell`.
- **shantenHelpers.ts** — compact notation, single-error parsing; an adapter over
  `utils/tileModel.ts` (never re-implement the tile library, parsing, or suit ordering).

## Notes

- The analysis comes from `internal/rules/shanten`, which also drives the heuristic bot, so a
  semantics change shows up both here and in bot play.
- Like `calc/`, it uses `theme/base.css` utility classes directly.
- Its response parse falls back to `{ error: 'Request failed' }`; switching to
  `utils/apiJson.readJsonBody` would change the message users see.

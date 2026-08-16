# web/src/features/

> Feature folders — each owns its routes, page components, and co-located helpers.

## Overview

Route page components are organized into feature folders corresponding to app domains. Each feature folder owns all source files for that domain: the React page component(s) rendered by React Router, plus co-located helpers, sub-components, and tests. `App.tsx` imports from these folders.

Every page uses the shared Rainy Mahjong Club theme from `web/src/theme/`: ink/rain backdrops, bone-paper work surfaces, jade controls, brass emphasis, and seal-red danger states. Menu pages compose typed primitives from `../../theme`; the live board adds the visual-only `table/table-theme.css` skin while retaining shared geometry.

User-facing feature copy uses the shared `useI18n()` context. English and Simplified Chinese follow the device's first supported language preference, while language controls in the club shell and tool/review pages update that same global context.

## Feature Folders

Each folder has its own `CLAUDE.md` with per-file detail — open the one you are working in.

| Folder | Routes | What it owns |
|---|---|---|
| [`auth/`](auth/CLAUDE.md) | `/login`, `/account` | Sign-in/register ticket, account editing, credentialed-fetch and CSRF helpers |
| [`lobby/`](lobby/CLAUDE.md) | `/`, `/play`, `/room/new` | Club switchboard, Quick Match / Private Table, room creation |
| [`game/`](game/CLAUDE.md) | `/room/:roomId`, `/match/:matchId` | Live match controller, waiting room, and the pure interaction helpers (chii choice, discard mode, rejoin) |
| [`replay/`](replay/CLAUDE.md) | `/replay`, `/replay/:matchId` | Paipu library, replay engine, and the post-game review overlay |
| [`calc/`](calc/CLAUDE.md) | `/tools/calc` | Fenghua scoring debugger |
| [`shanten/`](shanten/CLAUDE.md) | `/tools/shanten` | Shanten distance calculator |
| [`dev/`](dev/CLAUDE.md) | `/tools/table-sample`, `/tools/round-result` | Dev-only previews of real components against mock data |

## Architecture Notes

- All files in a feature folder use `'../../'` to reference `src`-level directories (`proto`, `table`, `contexts`, `hooks`, `theme`, `utils`, `config`). Intra-feature imports use `'./'`.
- `Game.tsx` and `Replay.tsx` do not own seat/discard layout markup — shared table layout belongs in `../../table/`. Both adapt their own state into the same presenter.
- Optional login entry points preserve the current route in `backgroundLocation`; required account, room-create, invitation, and expired-session continuations use direct non-dismissible `/login?returnTo=...` navigation.
- Live round-result payout adapters use explicit `Ready` / `Waiting` labels. Replay adapters leave readiness absent, and the shared overlay must not synthesize a status when none was provided.
- The live gameplay board is intentionally not a canvas; the fixed-stage DOM approach preserves Framer Motion, SVG tiles, and clickable DOM interactions while eliminating viewport-unit drift.
- Tool pages (`calc/`, `shanten/`) are self-contained rules debuggers and share no state with gameplay pages.
- See `../../table/CLAUDE.md` for the shared tabletop presenter, `../../theme/CLAUDE.md` for the design system, and `docs/superpowers/specs/2026-05-15-shanten-calc-ledger-redesign.md` for the calc/shanten UI spec.

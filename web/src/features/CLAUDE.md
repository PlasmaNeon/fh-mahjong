# web/src/features/

> One folder per app domain; each owns its route pages, helpers, and tests.

| Folder | Routes | Owns |
|---|---|---|
| [`auth/`](auth/CLAUDE.md) | `/login`, `/account` | Sign-in/register dialog, account editing, credentialed-fetch helpers |
| [`lobby/`](lobby/CLAUDE.md) | `/`, `/play`, `/room/new` | Quick Match, Private Table entry, invitation links, room creation |
| [`game/`](game/CLAUDE.md) | `/room/:roomId`, `/match/:matchId` | Waiting room and live match controller |
| [`replay/`](replay/CLAUDE.md) | `/replay`, `/replay/:matchId`, `/replay/import/:importId` | Paipu library, replay engine, AI review and study |
| [`calc/`](calc/CLAUDE.md) | `/tools/calc` | Scoring calculator |
| [`shanten/`](shanten/CLAUDE.md) | `/tools/shanten` | Shanten calculator |
| [`dev/`](dev/CLAUDE.md) | `/tools/table-sample`, `/tools/round-result` | Real components against mock data |

## Conventions

- Import `src`-level modules with `'../../'`; intra-feature imports use `'./'`.
- `Game.tsx` and `Replay.tsx` own no seat or discard markup; table layout lives in `../table/`.
- Menu pages compose primitives from `../theme`; copy goes through `useI18n()`.
- Optional login keeps the current route as `backgroundLocation`; required continuations (account,
  room creation, invitations, expired sessions) navigate to `/login?returnTo=...` without a
  dismiss option.
- Live round results show explicit `Ready` / `Waiting`; replay passes no readiness and the shared
  overlay must not invent one.
- The board is DOM on a fixed stage, not a canvas, so Framer Motion, SVG tiles, and clickable
  tiles keep working.
- `calc/` and `shanten/` are self-contained rules debuggers and share no state with gameplay.

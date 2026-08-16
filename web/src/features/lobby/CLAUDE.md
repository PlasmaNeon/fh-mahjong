# web/src/features/lobby/

> Home, matchmaking, and private-room creation. Routes: `/` (Home), `/play` (Lobby), `/room/new` (CreateRoom).

## Key Files

- **Home.tsx** — Compact localized club switchboard with four literal choices (Play, Table Tools, Paipu Replay, Profile) plus a separate language override in the brand row. Decorative slogan, atmospheric description, and menu descriptions are **intentionally absent** — do not re-add them.
- **Lobby.tsx** — Single Play screen for Quick Match and Private Table. An active search must confirm `POST /matchmaking/leave` before the screen returns to idle; `409 match_forming` keeps the player connected rather than dropping them.
- **CreateRoom.tsx** — Auth gate plus protected `POST /rooms`. **It navigates only after the server confirms creation**, so an invite URL can never point at a room that was never created.
- **navigation.ts** — One-shot play-intent helper used by the simplified lobby flow.
- **navigation.test.ts** / **streamlinedNavigation.test.ts** — Coverage for the play-intent handoff and the simplified flow.

## Architecture Notes

- Matchmaking is an in-process queue on a single-process server — there is no Redis, by design.
- The leave-before-idle rule exists because a client that goes idle locally while still queued server-side gets silently matched into a game nobody is watching.

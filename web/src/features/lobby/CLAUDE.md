# web/src/features/lobby/

> Entry and matchmaking. Routes: `/` (Home), `/play` (Lobby).
> Private-table creation and invitation validation live in `../room/`.

## Key files

- **Home.tsx** — renders the Lobby directly on `/`; `/play` stays a compatible entry.
- **Lobby.tsx** — Quick Match and Private Table panels plus invitation-link entry. Leaving an
  active search waits for `POST /matchmaking/leave` to confirm; `409 match_forming` keeps the
  player connected. Navigation locks while a search is queued.
- **playIntent.ts** — one-shot play intent carried across the login overlay; Quick Match sign-in
  returns to the originating route with its mode.

## Notes

- Matchmaking is an in-process server queue; there is no Redis.
- A client that goes idle while still queued server-side would be matched into a game nobody is
  watching — hence leave-before-idle.

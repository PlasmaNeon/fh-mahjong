# web/src/features/lobby/

> Entry, matchmaking, and room creation. Routes: `/` (Home), `/play` (Lobby), `/room/new`
> (CreateRoom).

## Key files

- **Home.tsx** — renders the Lobby directly on `/`; `/play` stays a compatible entry.
- **Lobby.tsx** — Quick Match and Private Table panels plus invitation-link entry. Leaving an
  active search waits for `POST /matchmaking/leave` to confirm; `409 match_forming` keeps the
  player connected. Navigation locks while a search is queued.
- **CreateRoom.tsx** — auth gate plus `POST /rooms`; navigates only after the server confirms, so
  an invite URL never points at a room that does not exist.
- **invitationLink.ts** — accepts same-origin HTTP(S) room links or `/room/:id` paths; rejects
  foreign origins, credentials, query/fragment destinations, and `/room/new`.
- **playIntent.ts** — one-shot play intent carried across the login overlay; Quick Match sign-in
  returns to the originating route with its mode.

## Notes

- Matchmaking is an in-process server queue; there is no Redis.
- A client that goes idle while still queued server-side would be matched into a game nobody is
  watching — hence leave-before-idle.

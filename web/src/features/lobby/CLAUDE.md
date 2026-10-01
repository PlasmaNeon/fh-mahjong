# web/src/features/lobby/

> Home, matchmaking, and private-room creation. Routes: `/` (Home), `/play` (Lobby), `/room/new` (CreateRoom).

## Key Files

- **Home.tsx** — Renders the real Lobby on `/`, exposing matchmaking and room creation immediately. `/play` remains a compatible entry. No decorative slogan or introductory page heading.
- **Lobby.tsx** — Production Direct play entry with two responsive panels for Quick Match and Private Table, plus invitation-link input. An active search must confirm `POST /matchmaking/leave` before the screen returns to idle; `409 match_forming` keeps the player connected rather than dropping them.
- **CreateRoom.tsx** — Auth gate plus protected `POST /rooms`. **It navigates only after the server confirms creation**, so an invite URL can never point at a room that was never created.
- **playIntent.ts** — One-shot play-intent helper used by the simplified lobby flow.
- **playIntent.test.ts** / **Home.test.ts** — Coverage for the play-intent handoff and the simplified flow.

## Architecture Notes

- Matchmaking is an in-process queue on a single-process server — there is no Redis, by design.
- The leave-before-idle rule exists because a client that goes idle locally while still queued server-side gets silently matched into a game nobody is watching.

`invitationLink.ts` validates pasted same-origin HTTP(S) room invitations or `/room/:id` paths; rejects foreign origins, credentials, query/fragment destinations and `/room/new`. `invitationLink.test.ts` covers those navigation boundaries. Home tests cover direct actions, `/play` compatibility, and full navigation locking during matchmaking.

Quick-match sign-in returns to the originating entry route (`/` or `/play`) so its selected game mode is retained across the optional login overlay.

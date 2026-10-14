# web/src/features/room/

> Private-table lifecycle. Routes: `/room/new` and `/room/:roomId`.

- **CreateRoom.tsx** — auth gate and `POST /rooms`; navigates only after creation succeeds.
- **PrivateRoom.tsx** — waiting room, seats, invitations, host settings and Start Match.
  `App.tsx` keys the component by room ID so room-local state resets between links.
- **SeatCard.tsx** — seat plaque with Add AI and advanced AI-type selection: Heuristic plus one
  entry per RL agent from `/api/v1/config` (disabled while that agent is unavailable); a seated
  RL bot shows its agent's label.
- **invitationLink.ts** — accepts same-origin HTTP(S) room links or `/room/:id` paths; used
  by the lobby entry. Rejects foreign origins, credentials, query/fragment destinations,
  and `/room/new`.
- **roomNavigation.ts** — active-match redirects based only on this room's response.
- **privateRoomSession.ts** — stores only the non-sensitive current table ID.
- **rejoinMatch.ts** — intentional-leave marker, scoped to a room and match.
- **rlAgents.ts** — `RLAgentInfo`, `parseRLAgents` (the `/config` `rlAgents` list, malformed
  entries dropped) and `rlSeatLabel` (a seat's agent label; empty id = the default agent).
  `PrivateRoom` polls `/config` every 10 s and sends `rlAgent` with each RL seat assignment.

Room navigation helpers are shared with `../game/Game.tsx`. Keeping them here lets live
play return to its table without making the room depend on the game controller. Preserve
session-storage keys across refactors so existing tabs can still rejoin. Authentication
belongs to `../../contexts/AuthContext.tsx`; browser storage never holds session tokens.

Pure helper tests live beside their implementations. Match actions and live table state
belong to `../game/`; shared table rendering belongs to `../../table/`.

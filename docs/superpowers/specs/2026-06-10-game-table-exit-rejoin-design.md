# Game-table Exit & Rejoin — Design

**Date:** 2026-06-10
**Status:** Approved (pending implementation plan)

## Summary

Add an Exit button to the top-right corner of the in-play game table. Clicking it
asks for confirmation, then returns the player to the waiting room (the private-room
screen) while a bot takes over their seat. The player can rejoin the match at any
time — either from a Rejoin button in the waiting room, or by opening a rejoin link
(which works across devices).

## Background: why this is mostly frontend work

The Go server already implements the exact seat-handoff behavior this feature needs:

- `isAutomatedSeat(seat)` returns `true` whenever **no websocket is connected** for
  that seat (`api/room.go`). The moment a player's socket closes, their seat is
  played by `policyForSeat(seat)` — the configured per-seat policy, the room bot
  policy, or the heuristic fallback.
- On websocket reconnect, the hub matches the JWT's user id against `UserRooms`,
  re-binds the seat to the new client, sends a `seat_assignment`, and replays the
  current board state (`api/ws.go:81-101`).

So "exit → bot plays → rejoin" already works at the protocol level by closing and
reopening the websocket. **No backend changes are required for v1.**

## The core problem the frontend must solve

Two existing reflexes in `web/src/pages/Table.tsx` fight an intentional exit:

- It auto-connects via the stored session on mount (`Table.tsx:38-45`).
- It auto-redirects into the match when game state arrives (`Table.tsx:32-36`).

Left unchanged, exiting to the room would silently reconnect the socket (re-binding
the seat to the human and evicting the bot) and bounce the player straight back into
the match.

## Architecture: the `left-match` marker

A small record persisted in `sessionStorage` under a versioned key
(`mahjong_left_match_v1`) holding `{ roomId, matchId }`. It is written the moment the
player confirms Exit, and it gates `Table.tsx`'s behavior:

| Marker present? | `Table.tsx` behavior |
|---|---|
| Yes (player intentionally left) | Do **not** auto-connect, do **not** auto-redirect. Render the **Rejoin banner**. Socket stays closed → bot keeps the seat. |
| No (normal flow) | Current behavior unchanged — auto-connect + redirect into the match. |

**Clearing the marker:** on Rejoin (player is going back in), or when the room no
longer reports an active match (it ended while the player was away).

**Single source of truth for the banner:** show the Rejoin banner exactly when the
marker is set **and** the room reports an active match.

## Components

### A. Exit button on the game table (`web/src/pages/Game.tsx`)

A small button pinned to the top-right of the game stage. It is placed inside
`game-stage-shell` but **outside** the zoom-scaled `game-stage` element so it renders
at a fixed size regardless of board scaling. Clicking it opens the confirmation modal.

### B. Confirmation modal

Built from the app's existing theme components. Copy:

> **Leave the match?**
> A bot will play your seat while you're away. You can rejoin anytime from the room.
> `[Cancel]`  `[Copy rejoin link]`  `[Leave]`

- **Cancel** — closes the modal; no side effects.
- **Copy rejoin link** — copies `${origin}/room/${roomId}?token=${token}` to the
  clipboard. `roomId` and `token` come from `loadPrivateRoomSession()`.
- **Leave** — writes the `left-match` marker `{ roomId, matchId }`, closes the
  socket, and `navigate('/room/' + roomId)`.

### C. Rejoin banner (`web/src/pages/Table.tsx`)

When the marker is set and the room reports an active match, render a prominent banner
above the (locked) room screen:

> **Match in progress** — a bot is playing your seat.  `[Rejoin]`  `[Copy rejoin link]`

- **Rejoin** — clears the marker, calls `connect(token)`, and
  `navigate('/match/' + matchId)`. The server re-binds the seat and replays the board.
  `matchId` comes from the marker, corroborated by room state.
- The existing seat/config UI remains visible but locked (it already locks once
  `state === 'started'`).

### D. Cross-device rejoin link (`web/src/pages/Table.tsx`)

The rejoin link is `${origin}/room/:roomId?token=<guestJWT>`. Because the server
reclaims a seat purely by matching the JWT's user id on reconnect, carrying the same
token onto a new device is sufficient to reclaim the exact seat — no backend changes.

On `Table.tsx` mount, if a `?token=` query param is present:

1. Save it as the session via `savePrivateRoomSession`.
2. Strip the param from the URL (so the token is not left in browser history).
3. Set the `left-match` marker so the Rejoin banner shows.

This gives both same-browser and cross-device rejoin a single, consistent exit point:
the Rejoin banner, one click to enter.

**Security note:** the rejoin link is a bearer secret — whoever holds it is that
player. This matches the existing trust model of sharing a private-room link among
friends, and the guest token already self-expires via its `exp` claim. A future
hardening step (out of scope) would replace the raw token with a backend-issued
short-lived, single-use rejoin code (`?rejoin=<code>`).

## Edge cases

- **Match ends while the player is away** — room state flips off `started`; the marker
  is cleared and the banner disappears, revealing the normal post-match room.
- **Token expired on rejoin** — reuse the existing `handleAuthFailure` path: clear the
  session and prompt for a name again.
- **Everyone leaves** — the match runs fully bot-driven to completion. Acceptable.

## Out of scope for v1

- **"Seat X left — bot playing" indicator for other players.** The client does not
  currently know which seats are human vs bot; surfacing this needs the server to
  expose per-seat connection status in `GameState`. The bot simply plays. This is a
  clean follow-up, deliberately kept separate from this frontend-only feature.
- **Backend-issued rejoin codes** (the hardening alternative to a raw token in the URL).
- The existing round-result overlay "Exit" button (which navigates to `/` home) is
  left unchanged.

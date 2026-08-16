# web/src/features/game/

> Live match and private-room waiting room. Routes: `/room/:roomId` (Table), `/match/:matchId` (Game).

## Key Files

### Components
- **Game.tsx** — Live match controller. Owns socket/action submission flow, interrupt state, auto-flower-reveal handling, and live round-result action buttons. Adapts backend player state into the shared `TableBoard` / `TableRoundResultOverlay` view models from `../../table/TableScene.tsx`, and keeps fixed 1600x900 stage scaling via `useGameStageLayout()`. Intentional exits clear local game state and close the WebSocket with application code `4000`, letting the server release the seat immediately while ordinary refreshes retain reconnect grace.
- **Table.tsx** — Private-table waiting screen with persistent Share Table, disclosed rules, and one sticky host Start Match action.
- **SeatCard.tsx** — Single seat plaque. Empty seats expose one default Add AI action; AI type is an advanced disclosure.
- **MatchEndOverlay.tsx** — Chongci final standings, Back to Club primary, Watch Replay secondary.
- **ExitMatchButton.tsx** / **GameSettingsButton.tsx** — Leave-match and in-match settings controls.

### Pure helpers (each unit-tested alongside)
- **actionOrdering.ts** — `orderTableActions`: wins first, calls next, Pass last.
- **chiiChoice.ts** — The multi-choice chii state machine: `collapseChiiActions`, `eligibleChiiTileIds`, `resolveChiiTileClick`. Server candidates collapse to **one** `CHII` trigger; after it is pressed, eligible hand faces are selected in two taps and the matching original action (with its canonical tile IDs) is submitted. Duplicate physical copies stay equivalent by suit/value.
- **handTileClick.ts** — `resolveHandTileClick` / `HandTileClickResult`: what a tap on a hand tile means in the current mode.
- **discardMode.ts** — `DiscardMode` plus `parse`/`load`/`save`: the persisted tap-to-discard preference.
- **clearLift.ts** — `shouldClearLift`: when a lifted (selected) tile should drop back.
- **rejoinMatch.ts** — `LeftMatchMarker` serialize/parse/save/load/clear for rejoining after refresh or reconnect.
- **roomNavigation.ts** — `roomActiveRedirectMatchId`: whether a room response should redirect into an active match.
- **privateRoomSession.ts** — Persists **only** the non-sensitive current `tableId` for login/rejoin navigation.

## Architecture Notes

- **Authentication is owned by `contexts/AuthContext.tsx`, not by anything here.** Browser storage never contains a session token; multi-tab play uses the same signed-in account.
- `Game.tsx` does not own seat/discard layout markup — shared table layout belongs in `../../table/`.
- `Game.tsx` defensively auto-submits backend `ACTION_FLOWER_REVEAL` messages and hides that action from the button bar, matching the intended auto-reveal flower UX.
- Action buttons appear contextually: interrupt actions during `PHASE_WAIT_DISCARDS` (phase 3), turn actions during `PHASE_PLAYER_TURN` (phase 2).
- Player perspective: `mySeatId` determines which player renders at the bottom; the others rotate around the table.
- Live round-result payout adapters use explicit `Ready` / `Waiting` labels. Replay adapters leave readiness absent, and the shared overlay must not synthesize a status when none was provided.
- The board is deliberately **not** a canvas — the fixed-stage DOM approach preserves Framer Motion, SVG tiles, and clickable DOM interactions while eliminating viewport-unit drift.
- Preview layout changes on `/tools/table-sample` (see `../dev/`) rather than by deploying a live match.

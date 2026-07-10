# web/src/features/

> Feature folders — each owns its routes, page components, and co-located helpers.

## Overview

Route page components are organized into feature folders corresponding to app domains. Each feature folder owns all source files for that domain: the React page component(s) rendered by React Router, plus co-located helpers, sub-components, and tests. `App.tsx` imports from these folders.

Every non-game page uses the shared "ledger" theme from `web/src/theme/` (IBM Plex, off-white/ink, single teal accent, hairline rules, light/dark via `prefers-color-scheme`); the theme CSS is imported once globally in `main.tsx`. Menu pages (Home, Login, Lobby, CreateRoom, Table) compose typed primitives from `../../theme` (`Page`, `Card`, `Section`, `Button`, `Field`, …). Only the live game/replay board (`Game.tsx`, `Replay.tsx`, `MatchEndOverlay.tsx`) keeps the dark in-game theme.

## Feature Folders

### `auth/`

Authentication pages. Routes: `/login`, `/account`.

- **Login.tsx** — Email/password sign-in and registration form (toggle between modes). Calls runtime-configured auth endpoints via `getApiUrl(...)`. Stores JWT in localStorage. On login, navigates to `/play`. Includes a direct entry link to `/room/new`.
- **Account.tsx** — Account settings page (`/account`). Lets real accounts edit their email and display name; on save stores the returned JWT and calls `connect(newToken)` to refresh the socket. Guests (404/503 from `GET /api/v1/users/me`) see a notice directing them to the sign-in page instead of the form. Linked from the lobby nav (`/play`).

### `lobby/`

Lobby/matchmaking pages. Routes: `/` (Home), `/play` (Lobby), `/room/new` (CreateRoom).

- **Home.tsx** — Landing page. One-click feature buttons (Play, Create Private Room, Scoring Calculator, Shanten Calculator, Login/Account). Reads JWT from `localStorage` to show signed-in state. Built from the shared `PageShell`/`GlassCard`/`Eyebrow`/`PageHeading`/`ButtonLink` primitives.
- **Lobby.tsx** — Matchmaking page. Shows the matchmaking queue and links to the private-room flow. On match found, navigates to `/match/:matchId`.
- **CreateRoom.tsx** — Private-room link generator. Generates a random room id client-side and builds a shareable `/room/:roomId` URL. Lets the user copy the link or open/join immediately. Acts purely as a link generator; seat configuration happens on `/room/:roomId`.

### `calc/`

Fenghua hand calculator tool. Route: `/tools/calc`.

- **Calc.tsx** — Typed Fenghua rules debugger. Posts to `/api/v1/tools/calc`. Uses the shared ledger theme via utility classes from `../../theme/` (imported globally). Header language toggle (English/Chinese). Hybrid editor with canonical notation fields plus local tile palettes for closed hand, win tile, and wild tile. Open meld editing uses an inline per-row palette. Full scoring context: tsumo/ron toggle, seat wind, prevailing wind, flower meld toggles. Cross-links to `/tools/shanten`.
- **calcHelpers.ts** — Calculator-only helpers: typed draft models for tiles/melds, canonical tile notation parse/format helpers, meld validation, expected hand-size calculation, and request-payload builders.

### `shanten/`

Shanten distance calculator tool. Route: `/tools/shanten`.

- **Shanten.tsx** — Shanten calculator UI. Uses the shared ledger theme. Cross-links to `/tools/calc`.
- **shantenHelpers.ts** — Shanten-specific helper utilities.

### `replay/`

Replay viewer. Route: `/replay/:matchId`.

- **Replay.tsx** — Fetches paipu data, advances the local `ReplayEngine`, and adapts replay state into the shared `TableBoard` / `TableRoundResultOverlay` presenter used by live play. Keeps replay transport controls, perspective selector, and "show all hands" toggle in a side panel. Reuses the same fixed-stage scaling system as live play. Also owns the review-mode fetch/generate state (`review`, `reviewStatus`, `reviewError`) and renders `<ReviewPanel/>` as a second stacked section inside the same 280px control panel, plus colored tick marks on the action-progress bar for the selected seat's flagged decisions in the current round.
- **replayEngine.ts** — Stateful replay engine: processes recorded game actions step-by-step and produces board state for each moment in the replay. `jumpToAction(roundIndex, actionIndex)` (`jumpToRound` + a `stepForward` loop) supports deep-linking from the review panel to a specific decision.
- **replayTypes.ts** — TypeScript types for replay data (paipu format, engine state).
- **reviewTypes.ts** — `ReviewReport`/`ReportDecision`/`SeatSummary`/`GapRef` types and `fetchReview`/`generateReview` API calls (`GET`/`POST /api/v1/matches/:matchId/review`). Field names are a cross-task contract with the backend (`internal/review/report.go`) — do not rename without updating that file. `fetchReview` returns `null` on 404 (no report generated yet); both throw `{status, message}` on other non-2xx responses (503 means no policy server is configured).
- **reviewUtils.ts** — Pure helpers consumed by `ReviewPanel.tsx` and covered by `reviewUtils.test.ts`: `decisionSeverity(d, thresholds?)` classifies a decision as `ok`/`disagreement`/`mistake` from the gap between the top and chosen action probability (a chosen action ranked in the top N with non-trivial probability is always exempt, checked before the gap tiers); `decisionGap`; `decisionKey(round, actionIndex)` — the anchor string that ties a `ReportDecision` to the replay engine's `(engine.currentRoundIndex, state.actionIndex)` position (multiple seats can share one key during a call window); `buildDecisionIndex(report)` groups decisions by that key; `selectPanelDecisions`/`selectBarRows` filter/shape decisions for one seat's panel; `actionLabel(actionId)` maps the RL action-catalog id (mirrors `internal/rl/action.go`) to bilingual `{en, zh}` labels; `SEVERITY_THRESHOLDS`/`SEVERITY_COLORS`/`SEVERITY_LABELS` are the default severity contract shared by the bar chart, mistake-summary counts, and progress-bar ticks.
- **ReviewPanel.tsx** — Self-contained review overlay (KillerDucky-style): request-review button with loading/generating/unavailable/error states when no report exists yet; once a report exists, renders the current decision's horizontal probability bar chart (top 8 actions + chosen if outside, chosen row colored by severity, "Champion prefers X (72%)" wording — never "wrong"), a per-seat mistake summary strip (severity counts + clickable `topGaps` entries), an SVG value sparkline with a current-position marker and click-to-jump points, a persistent placement-context caption, and two threshold sliders that override `SEVERITY_THRESHOLDS` (controlled from `Replay.tsx` so the progress-bar ticks stay in sync). Matches `Replay.tsx`'s dark `rgba(17,24,39,0.95)`/emerald inline-style idiom; no CSS frameworks. Bilingual (`en`/`zh`) via the same local-`useState<Lang>` pattern as `calc/Calc.tsx` (each page owns its own instance, not shared state).
- **ReviewPanel.test.ts** — `web/package.json` has no `@testing-library/react` and `vitest.config.ts` runs with `environment: 'node'` (no DOM) and only collects `*.test.ts`. Rather than add a dependency, this renders `ReviewPanel` with `react-dom/server`'s `renderToStaticMarkup` (already a transitive dependency of `react-dom`) against a fixture report and asserts on the resulting HTML string (severity badge text, a bar-row label, the request-review button, the unavailable message).

### `game/`

Live match and private-room waiting room. Routes: `/room/:roomId` (Table), `/match/:matchId` (Game).

- **Game.tsx** — Live match controller. Owns socket/action submission flow, interrupt state, auto-flower reveal handling, and live round-result action buttons. Adapts backend player state into the shared `TableBoard` / `TableRoundResultOverlay` view models from `../../table/TableScene.tsx`. Keeps fixed 1600x900 stage scaling via `useGameStageLayout()`. Uses tab-scoped private-room session helper for refresh reconnects.
- **Table.tsx** — Private-room waiting/seat-configuration screen for `/room/:roomId`. Reads/POSTs `/api/v1/rooms/:roomId/...` for join, get, seat mutation, mode, and start. Renders four `SeatCard` components; host sees AI controls and a "Start Match" button. Subscribes to `lobby_update` envelopes and redirects to `/match/:matchId` on start.
- **SeatCard.tsx** — Single seat-card sub-component. Renders waiting/human/bot states; if `canEdit`, shows "Add AI · Heuristic" buttons for empty seats and a "Remove AI" button for bot seats. Pure presentation; mutations bubble up to `Table.tsx`.
- **MatchEndOverlay.tsx** — Chongci final-standings modal rendered when `gameState.phase === PHASE_MATCH_END`. Offers "Watch Replay" (→ `/replay/:matchId`) and "Leave" (→ `/play`).
- **ExitMatchButton.tsx** — Button component for leaving the active match.
- **privateRoomSession.ts** — Private-room browser session helpers. Persists active guest token, username, and `tableId` in tab-scoped session storage. Decodes JWT expiry to discard stale sessions. Shared by `Table.tsx` and `Game.tsx` so both routes recover the same private-room identity.
- **rejoinMatch.ts** — Logic for rejoining an active match after a page refresh or reconnect.
- **rejoinMatch.test.ts** — Vitest unit tests for the rejoin logic (11 tests).

## Architecture Notes

- All files in a feature folder use `'../../` to reference `src`-level directories (`proto`, `table`, `contexts`, `hooks`, `theme`, `utils`, `config`). Intra-feature imports (files in the same folder) use `'./'`.
- `Game.tsx` consumes `useGameState()` and `useSocket()` from contexts.
- `Game.tsx` and `Replay.tsx` do not own seat/discard layout markup directly; shared table layout belongs in `../../table/`.
- The live gameplay board is intentionally not a canvas; the fixed-stage DOM approach preserves Framer Motion, SVG tiles, and clickable DOM interactions while eliminating viewport-unit drift.
- `Calc.tsx` is intentionally self-contained and does not share state with gameplay pages; it is a rules-debugging tool, not part of the live match flow.
- Player perspective: `mySeatId` determines which player is rendered at the bottom position; others are rotated around the table.
- Action buttons appear contextually: interrupt actions during `PHASE_WAIT_DISCARDS` (phase 3), turn actions during `PHASE_PLAYER_TURN` (phase 2).
- See `../../table/AGENTS.md` for the shared tabletop presenter, `../../theme/AGENTS.md` for the ledger design system, and `docs/superpowers/specs/2026-05-15-shanten-calc-ledger-redesign.md` for the calc/shanten UI spec.

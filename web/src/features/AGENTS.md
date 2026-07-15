# web/src/features/

> Feature folders — each owns its routes, page components, and co-located helpers.

## Overview

Route page components are organized into feature folders corresponding to app domains. Each feature folder owns all source files for that domain: the React page component(s) rendered by React Router, plus co-located helpers, sub-components, and tests. `App.tsx` imports from these folders.

Every page uses the shared Rainy Mahjong Club theme from `web/src/theme/`: ink/rain backdrops, bone-paper work surfaces, jade controls, brass emphasis, and seal-red danger states. Menu pages compose typed primitives from `../../theme`; the live board adds the visual-only `table/table-theme.css` skin while retaining shared geometry.

## Feature Folders

### `auth/`

Authentication pages. Routes: `/login`, `/account`.

- **authClient.ts** — Credentialed fetch/CSRF helpers, safe internal return-path validation, and one-time cleanup of legacy JWT storage
- **AuthTicket.tsx** — Shared sign-in/register ticket. Login accepts one username-or-email field; registration collects the unique friendly username, email, and password
- **Login.tsx** — Invitation-aware login route; validates `returnTo` and resumes `/room/:roomId` automatically after authentication
- **Account.tsx** — Edits the unique username/email and exposes explicit current-device logout

### `lobby/`

Lobby/matchmaking pages. Routes: `/` (Home), `/play` (Lobby), `/room/new` (CreateRoom).

- **Home.tsx** — Asymmetric club entrance with three choices: Play, Table Tools, and Profile.
- **Lobby.tsx** — Single Play screen for Quick Match and Private Table. Active searches must confirm `POST /matchmaking/leave` before the screen returns to idle; `409 match_forming` keeps the player connected.
- **navigation.ts** — One-shot play-intent helper used by the simplified lobby flow.
- **CreateRoom.tsx** — Auth gate plus protected `POST /rooms`; it navigates only after the server confirms creation, so an invite URL can never create state

### `calc/`

Fenghua hand calculator tool. Route: `/tools/calc`.

- **Calc.tsx** — Typed Fenghua rules debugger with one shared, targetable tile tray for hand, win tile, wild tile, and the active meld.
- **calcHelpers.ts** — Calculator-only helpers: typed draft models for tiles/melds, canonical tile notation parse/format helpers, meld validation, expected hand-size calculation, and request-payload builders.

### `shanten/`

Shanten distance calculator tool. Route: `/tools/shanten`.

- **Shanten.tsx** — Shanten calculator UI with the shared Scoring/Shanten tabs and one hand/wild targetable tray.
- **shantenHelpers.ts** — Shanten-specific helper utilities.

### `replay/`

Replay viewer. Route: `/replay/:matchId`.

- **Replay.tsx** — Fetches paipu data, advances the local `ReplayEngine`, and adapts replay state into the shared `TableBoard` / `TableRoundResultOverlay` presenter used by live play. Keeps replay transport controls, perspective selector, and "show all hands" toggle in a lacquer side drawer, which becomes a bottom sheet on narrow screens. `replay.css` owns all static palette/layout styling; only dynamic progress widths and severity colours stay inline.
- **replayEngine.ts** — Stateful replay engine: processes recorded game actions step-by-step and produces board state for each moment in the replay. `jumpToAction(roundIndex, actionIndex)` (`jumpToRound` + a `stepForward` loop) supports deep-linking from the review panel to a specific decision.
- **replayTypes.ts** — TypeScript types for replay data (paipu format, engine state).
- **reviewTypes.ts** — `ReviewReport`/`ReportDecision`/`SeatSummary`/`GapRef` types and `fetchReview`/`generateReview` API calls (`GET`/`POST /api/v1/matches/:matchId/review`). Field names are a cross-task contract with the backend (`internal/review/report.go`) — do not rename without updating that file. `fetchReview` returns `null` on 404 (no report generated yet); both throw `{status, message}` on other non-2xx responses (503 means no policy server is configured).
- **reviewUtils.ts** — Pure helpers consumed by `ReviewPanel.tsx` and covered by `reviewUtils.test.ts`: `decisionSeverity(d, thresholds?)` classifies a decision as `ok`/`disagreement`/`mistake` from the gap between the top and chosen action probability (a chosen action ranked in the top N with non-trivial probability is always exempt, checked before the gap tiers); `decisionGap`; `decisionKey(round, actionIndex)` — the anchor string that ties a `ReportDecision` to the replay engine's `(engine.currentRoundIndex, state.actionIndex)` position (multiple seats can share one key during a call window); `buildDecisionIndex(report)` groups decisions by that key; `selectPanelDecisions`/`selectBarRows` filter/shape decisions for one seat's panel; `actionLabel(actionId)` maps the RL action-catalog id (mirrors `internal/rl/action.go`) to bilingual `{en, zh}` labels; `SEVERITY_THRESHOLDS`/`SEVERITY_COLORS`/`SEVERITY_LABELS` are the default severity contract shared by the bar chart, mistake-summary counts, and progress-bar ticks.
- **ReviewPanel.tsx** — Self-contained review overlay: request-review states, decision bars, mistake summary, clickable gaps, value sparkline, caption, and threshold sliders. Static presentation belongs in `replay.css`; severity values and data-driven bar dimensions remain dynamic. Bilingual (`en`/`zh`) state stays local to the replay route.
- **ReviewPanel.test.ts** — `web/package.json` has no `@testing-library/react` and `vitest.config.ts` runs with `environment: 'node'` (no DOM) and only collects `*.test.ts`. Rather than add a dependency, this renders `ReviewPanel` with `react-dom/server`'s `renderToStaticMarkup` (already a transitive dependency of `react-dom`) against a fixture report and asserts on the resulting HTML string (severity badge text, a bar-row label, the request-review button, the unavailable message).

### `game/`

Live match and private-room waiting room. Routes: `/room/:roomId` (Table), `/match/:matchId` (Game).

- **Game.tsx** — Live match controller. Owns socket/action submission flow, interrupt state, auto-flower reveal handling, and live round-result action buttons. Adapts backend player state into the shared `TableBoard` / `TableRoundResultOverlay` view models from `../../table/TableScene.tsx`. Keeps fixed 1600x900 stage scaling via `useGameStageLayout()`. Uses tab-scoped private-room session helper for refresh reconnects.
- **Table.tsx** — Private-table waiting screen with persistent Share Table, disclosed rules, and one sticky host Start Match action.
- **SeatCard.tsx** — Single seat plaque. Empty seats expose one default Add AI action; AI type is an advanced disclosure.
- **actionOrdering.ts** — Pure live action priority: wins first, calls next, Pass last.
- **MatchEndOverlay.tsx** — Chongci final standings with Back to Club as the primary action and Watch Replay as secondary.
- **ExitMatchButton.tsx** — Button component for leaving the active match.
- **privateRoomSession.ts** — Persists only the current non-sensitive table ID for login/rejoin navigation; authentication is owned by `AuthContext`
- **rejoinMatch.ts** — Logic for rejoining an active match after a page refresh or reconnect.
- **rejoinMatch.test.ts** — Vitest unit tests for non-sensitive left-match markers.

### `dev/`

Dev-only preview pages that render real components with mock data (no live match). Not linked from the app UI; reached by URL.

- **TableSample.tsx** — Renders the real `TableBoard` with mock game data so the table layout can be iterated without a live match. Route: `/tools/table-sample`.
- **RoundResultDemo.tsx** — Preview of the round-end payout sheet (`TableRoundResultOverlay`) so the shared live/replay settlement UI can be reviewed without playing a round. Route: `/tools/round-result`. Renders a control panel (scenario · viewport preset · readiness toggle) plus a resizable `<iframe>`; the iframe loads the same route with `?embed=1` and renders only the overlay full-bleed, so its own viewport drives the responsive `max-width: 720px` / landscape media queries. Presets include a 375x667 compact iPhone regression target. Mock `RoundResultView` data comes from `roundResultScenarios.ts` (unit-tested in `roundResultScenarios.test.ts`).

## Architecture Notes

- `dev/TableSample.tsx` exposes deterministic idle, active-turn, interrupt, callable-discard, round-result, match-end, and exit-dialog fixtures for visual QA without a backend.

- All files in a feature folder use `'../../` to reference `src`-level directories (`proto`, `table`, `contexts`, `hooks`, `theme`, `utils`, `config`). Intra-feature imports (files in the same folder) use `'./'`.
- `Game.tsx` consumes `useGameState()` and `useSocket()` from contexts.
- Live round-result payout adapters use explicit `Ready` / `Waiting` labels. Replay adapters leave readiness absent, and the shared overlay must not synthesize a status when none was provided.
- `Game.tsx` and `Replay.tsx` do not own seat/discard layout markup directly; shared table layout belongs in `../../table/`.
- The live gameplay board is intentionally not a canvas; the fixed-stage DOM approach preserves Framer Motion, SVG tiles, and clickable DOM interactions while eliminating viewport-unit drift.
- `Calc.tsx` is intentionally self-contained and does not share state with gameplay pages; it is a rules-debugging tool, not part of the live match flow.
- Player perspective: `mySeatId` determines which player is rendered at the bottom position; others are rotated around the table.
- Action buttons appear contextually: interrupt actions during `PHASE_WAIT_DISCARDS` (phase 3), turn actions during `PHASE_PLAYER_TURN` (phase 2).
- See `../../table/AGENTS.md` for the shared tabletop presenter, `../../theme/AGENTS.md` for the ledger design system, and `docs/superpowers/specs/2026-05-15-shanten-calc-ledger-redesign.md` for the calc/shanten UI spec.

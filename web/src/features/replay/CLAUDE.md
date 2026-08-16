# web/src/features/replay/

> Paipu library, replay viewer, and the post-game review overlay. Routes: `/replay`, `/replay/:matchId`.

## Key Files

### Library and navigation
- **ReplayLibrary.tsx** — Opens raw match IDs or shared `/replay/:matchId` links and lists the signed-in account's cursor-paginated completed games with open/copy actions and full loading/offline/empty states.
- **replayReference.ts** — Strictly extracts a **local** replay match ID from raw IDs, relative routes, or HTTP(S) links. Pasted origins are never navigated or fetched.

### Playback
- **Replay.tsx** — Fetches paipu, advances the local `ReplayEngine`, and adapts replay state into the same `TableBoard` / `TableRoundResultOverlay` presenter live play uses. Transport controls, perspective selector, and "show all hands" toggle live in a lacquer side drawer that becomes a bottom sheet on narrow screens.
- **replayEngine.ts** — Stateful engine: processes recorded actions step-by-step and produces board state for each moment. `getActionDescription(lang?)` emits English or Simplified Chinese transport copy; `jumpToAction(roundIndex, actionIndex)` (`jumpToRound` + a `stepForward` loop) supports deep-linking from the review panel to a specific decision.
- **replayTypes.ts** — Types for paipu format and engine state.
- **replay.css** — Owns **all** static palette/layout styling for this route; only dynamic progress widths and severity colours stay inline.

### Post-game review
- **reviewTypes.ts** — `ReviewReport`/`ReportDecision`/`SeatSummary`/`GapRef` plus `fetchReview`/`generateReview` (`GET`/`POST /api/v1/matches/:matchId/review`). **Field names are a cross-task contract with `internal/review/report.go` — do not rename without updating that file.** `fetchReview` returns `null` on 404 (no report yet); both throw `{status, message}` on other non-2xx (503 = no policy server configured). **`POST` requires an authenticated session**: `generateReview(matchId, apiFetch)` takes the caller's `useAuth().apiFetch` (cookie + CSRF) as its second argument — plain `fetch` gets a 401, since the backend moved this route into the protected group to stop unauthenticated `?force=1` spam from exhausting policy-server capacity. `GET` stays a public, unauthenticated cache read and never builds a report.
- **reviewUtils.ts** — Pure helpers covered by `reviewUtils.test.ts`: `decisionSeverity(d, thresholds?)` classifies a decision `ok`/`disagreement`/`mistake` from the gap between top and chosen action probability (a chosen action ranked in the top N with non-trivial probability is always exempt, checked **before** the gap tiers); `decisionGap`; `decisionKey(round, actionIndex)` — the anchor tying a `ReportDecision` to the engine's `(currentRoundIndex, actionIndex)` position (multiple seats can share one key during a call window); `buildDecisionIndex`; `selectPanelDecisions`/`selectBarRows`; `actionLabel(actionId)` mapping the RL action-catalog id (mirrors `internal/rl/action.go`) to bilingual labels; `SEVERITY_THRESHOLDS`/`SEVERITY_COLORS`/`SEVERITY_LABELS`, the severity contract shared by the bar chart, mistake counts, and progress-bar ticks.
- **ReviewPanel.tsx** — Self-contained review overlay: request-review states, decision bars, mistake summary, clickable gaps, value sparkline, caption, threshold sliders. Bilingual state stays local to this route.
- **ReviewPanel.test.ts** — `web/package.json` has no `@testing-library/react` and `vitest.config.ts` runs `environment: 'node'` (no DOM), collecting only `*.test.ts`. Rather than add a dependency, this renders `ReviewPanel` via `react-dom/server`'s `renderToStaticMarkup` (already a transitive dep of `react-dom`) against a fixture report and asserts on the HTML string.

## Architecture Notes

- Replay reuses the live presenter rather than maintaining a second seat/discard DOM tree — layout fixes land once, in `../../table/`.
- The replay route opts out of forced landscape rotation (`.stage-rotator--replay`) so its control drawer stays reachable in portrait.
- Paipu lists only completed (`MATCH_END`) matches, which is why an endless match mode never appears in the library.
- The review backend needs `POLICY_SERVER_URL` configured, or `GET` returns 503.

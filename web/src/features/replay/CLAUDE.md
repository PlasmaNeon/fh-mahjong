# web/src/features/replay/

> Paipu library, replay viewer, and the post-game review overlay. Routes: `/replay`, `/replay/:matchId`.

## Key Files

### Library and navigation
- **ReplayLibrary.tsx** — Opens raw match IDs or shared `/replay/:matchId` links and lists the signed-in account's cursor-paginated completed games with open/copy actions and full loading/offline/empty states.
- **replayReference.ts** — Strictly resolves raw IDs, relative routes, or HTTP(S) bookmarks to **local** match/import routes. Library bookmarks retain only round/cursor/seat/study/advice/decision state; other query fields and pasted origins are never navigated or fetched. The legacy match-ID parser retains its existing contract.

### Playback
- **Replay.tsx** — Fetches paipu, advances the local `ReplayEngine`, and adapts replay state into the same `TableBoard` / `TableRoundResultOverlay` presenter live play uses. Transport controls, perspective selector, and "show all hands" toggle live in a lacquer side drawer that becomes a bottom sheet on narrow screens.
- **replayEngine.ts** — Stateful engine: processes recorded actions step-by-step and produces board state for each moment. `getActionDescription(lang?)` emits English or Simplified Chinese transport copy; `jumpToAction(roundIndex, actionIndex)` (`jumpToRound` + a `stepForward` loop) supports deep-linking from the review panel to a specific decision.
- **replayTypes.ts** — Types for paipu format and engine state.
- **replay.css** — Owns **all** static palette/layout styling for this route; only dynamic progress widths and severity colours stay inline.

### Post-game review
- **reviewClient.ts** — `ReviewReport`/`ReportDecision`/`SeatSummary`/`GapRef` plus `fetchReview`/`generateReview` (`GET`/`POST /api/v1/matches/:matchId/review`). **Field names are a contract with `internal/review/report.go` — do not rename without updating that file.** `fetchReview` returns `null` on 404 (no report yet); both throw `{status, message}` on other non-2xx (503 = no policy server configured). **`POST` requires an authenticated session**: `generateReview(matchId, apiFetch)` takes the caller's `useAuth().apiFetch` (cookie + CSRF) as its second argument — plain `fetch` gets a 401. The route is protected because each build drives `/evaluate` load on the policy server shared with live RL seats. `GET` stays a public, unauthenticated cache read and never builds a report.
- **reviewUtils.ts** — Pure helpers covered by `reviewUtils.test.ts`: `decisionSeverity(d, thresholds?)` classifies a decision `ok`/`disagreement`/`mistake` from the gap between top and chosen action probability (a chosen action ranked in the top N with non-trivial probability is always exempt, checked **before** the gap tiers); `decisionGap`; `decisionKey(round, actionIndex)` — the anchor tying a `ReportDecision` to the engine's `(currentRoundIndex, actionIndex)` position (multiple seats can share one key during a call window); `buildDecisionIndex`; `selectPanelDecisions`/`selectBarRows`; `actionLabel(actionId)` mapping the RL action-catalog id (mirrors `internal/rl/action.go`) to bilingual labels; `SEVERITY_THRESHOLDS`/`SEVERITY_COLORS`/`SEVERITY_LABELS`, the severity contract shared by the bar chart, mistake counts, and progress-bar ticks.
- **ReviewPanel.tsx** — Self-contained review overlay: request-review states, decision bars, mistake summary, clickable gaps, value sparkline, caption, threshold sliders. Bilingual state stays local to this route.
- **ReviewPanel.test.ts** — `web/package.json` has no `@testing-library/react` and `vitest.config.ts` runs `environment: 'node'` (no DOM), collecting only `*.test.ts`. Rather than add a dependency, this renders `ReviewPanel` via `react-dom/server`'s `renderToStaticMarkup` (already a transitive dep of `react-dom`) against a fixture report and asserts on the HTML string.

## Architecture Notes

- Replay reuses the live presenter rather than maintaining a second seat/discard DOM tree — layout fixes land once, in `../../table/`.
- The replay route opts out of forced landscape rotation (`.stage-rotator--replay`) so its control drawer stays reachable in portrait.
- Paipu lists only completed (`MATCH_END`) matches, which is why an endless match mode never appears in the library.
- Building a review needs `POLICY_SERVER_URL` on the backend, or `POST` returns 503. `GET` never builds; it returns 404 until a report is cached.

## Adapted AI study viewer

The current viewer uses `ReviewStudy.tsx`, `studyClient.ts`, `useStudy.ts`, and `studyUtils.ts`. The legacy `ReviewPanel`/client remain compatible for existing consumers/tests. New route `/replay/import/:importId` reads account-owned native uploads; `ReplayLibrary` previews JSON/player selection and uploads via cookie/CSRF before optional background analysis. Imported replay IDs never enter public live-match storage.

The slate table and 300px lacquer drawer remain the shared presenter. Drawer views are Decision/Rounds/Risk. All legal action probabilities and genuine payout evaluations remain available; per-tile confidence, exact actual-copy marker, best-action outline and optional risk annotations are presentation-only fields. `ReplayEngine.replayDiscards` preserves dim called-discard footprints and tsumogiri dots while `discards` keeps its canonical removal semantics. The center HUD remains compact; dice/wall/wangpai context uses its existing corner slot. Settlement keys carry stable pattern IDs.

Study mode hides actual/AI/future results, including future starting scores; revealing one decision does not reveal final standings. Inferred/unknown choices do not count toward agreement. Rating discloses its included denominator and uses fully evaluated, non-flat action ranges. Risk and tsumo logs disclose the cumulative proxy, not a calibrated game probability. Five reviewer languages use the shared i18n provider, with English fallback outside translated namespaces.

Jobs poll with abort/generation guards, expose partial/pending values, cancel, retry and reopen cached work. Bookmarks restore round/cursor/seat/study/stable decision; malformed numeric fields are bounded. Ratio threshold persists locally. Keyboard shortcuts retain event/round/play controls and add Alt+arrows for decisions, error jumps and toggles. Focused-table wheel stepping is opt-in and uses a non-passive listener. Static/pure tests cover spoilers, duplicate tile/ID 0 markers, ratio, rating, uncertainty absence, locale placeholders and bookmark bounds.

Portrait replay keeps the table in a compact landscape proportion above its scrollable controls. Risk contributor details use a native modal dialog with Escape and focus restoration.

Candidate columns sort by confidence or expected payout without changing the policy recommendation. Bookmarks retain advice visibility and the selected decision even when responses share a cursor. Discard logs include individual-opponent cumulative proxies and observed outcomes only after the event is visible in study mode.

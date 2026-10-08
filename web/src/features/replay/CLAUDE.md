# web/src/features/replay/

> Paipu library, replay viewer, and the AI review/study drawer. Routes: `/replay`,
> `/replay/:matchId`, `/replay/import/:importId`.

Feature definitions (recommendation, evaluation, agreement, rating, risk):
[`docs/replay-review.md`](../../../../docs/replay-review.md).

## Key files

### Library
- **ReplayLibrary.tsx** — open a match id or shared link, list the account's completed games
  (cursor-paginated), and upload a native paipu: JSON preview, player selection, upload with
  cookie + CSRF, optional analysis.
- **replayReference.ts** — resolves ids, relative routes, or HTTP(S) bookmarks to local
  match/import routes only. Bookmarks keep round, cursor, seat, study, advice, and decision state;
  other query fields and foreign origins are never followed.

### Playback
- **Replay.tsx** — fetches the paipu (live match or import), drives `ReplayEngine`, and adapts its
  state into the shared `TableBoard` / `TableRoundResultOverlay`. Controls live in a 300px side
  drawer that becomes a bottom sheet on narrow screens; portrait keeps the table in a compact
  landscape proportion above the controls. The route opts out of forced landscape rotation.
- **replayEngine.ts** — steps recorded actions into board state. `jumpToAction(round, action)`
  supports deep links; `replayDiscards` keeps dimmed called-discard footprints and tsumogiri
  dots while `discards` keeps canonical removal semantics. `getActionDescription(lang)` gives
  localized transport text.
- **replayTypes.ts** — paipu and engine-state types.
- **replay.css** — all static styling for the route; only progress widths and severity colors
  stay inline.

### Review and study
- **ReviewStudy.tsx**, **useStudy.ts**, **studyClient.ts**, **studyUtils.ts** — the current
  viewer: Decision / Rounds / Risk drawer views, per-tile confidence and risk annotations over the
  hand, candidate tables sortable by confidence or expected payout, agreement and rating, and the
  background job client (polls with abort/generation guards, shows partial results, cancel, retry,
  reopen cached work).
- **reviewClient.ts**, **ReviewPanel.tsx**, **reviewUtils.ts** — the original policy-only review,
  kept for existing consumers. `reviewClient.ts` field names are a contract with
  `internal/review/report.go`. `GET /matches/:id/review` is a public cache read (404 until built);
  `POST` needs `useAuth().apiFetch` (cookie + CSRF) and returns 503 without a policy server.

## Behavior

- **Study mode** hides advice, the actual choice, AI choices, and future results (including later
  starting scores) until revealed; revealing one decision does not reveal standings.
- Only recorded, non-forced choices count toward agreement and rating; the included denominator is
  shown. Risk and tsumo logs show a cumulative proxy, labelled as such.
- Exact tile id 0 and duplicate faces stay distinct in annotations.
- Keyboard: arrows step events and rounds, Space autoplays, Alt+arrows jump decisions and errors.
  Wheel stepping is opt-in on a focused table. The ratio threshold persists locally.
- Reviewer text supports five languages through the shared i18n provider.
- Imported replays never enter public match storage, history, or training data.
- `vitest` runs in a node environment without a DOM, so component tests render with
  `react-dom/server` (`renderToStaticMarkup`) and assert on the HTML.

# Paipu replay with integrated AI review

Date: 2026-10-04
Status: Implemented and locally verified; deployment is outside this task.
Planning baseline: `origin/main` at `0442d0a7`.
Implementation base: `origin/main` at `fa58e7cd`.
Worktree: `/Users/plasma/fh-mahjong-paipu-ai-review`.
Branch: `codex/paipu-ai-review`.

## Goal and scope

Upload a Fenghua paipu, run the project's served AI against its recorded
decision positions, and study the results in the existing replay viewer.
At each choice, the player can see their actual operation, the AI's preferred
operation, and the recommendation probability for every legal alternative.
Provide the full feature set of the inspected KillerDucky replay, adapted to
the existing Fenghua replay UI. Confidence bars alone do not meet this goal.
The feature-parity checklist below is a release requirement, including the
advanced evaluation, risk, summary, settings, and navigation features.

The first version assumes this project's Fenghua JSON paipu format. Mortal,
KillerDucky, and Mahjong Soul are interface references. Mortal's riichi model
is not compatible with Fenghua rules, wild flowers, scoring, or the project's
204-action catalog. Importing Mahjong Soul records and running Mortal on
them would require a separate rules/format/model integration and is deferred.

This scope was presented in the plan. Implementation proceeded after the user
requested full replay feature parity and said “go”.

## Research and verified starting point

### Reference workflow

- Opened [Mortal](https://mjai.ekyu.moe/zh-cn.html) in Codex's built-in browser.
- Selected a public replay from
  [Amae Koromo's highlight list](https://amae-koromo.sapk.ch/highlight):
  [public Mahjong Soul paipu](https://mahjongsoul.game.yo-star.com/?paipu=261004-7da53e99-77b6-47b7-af9b-8b083bb79a15_a32332903).
- Ran Mortal with its existing 4.1b/KillerDucky defaults and inspected the
  [generated review](https://mjai.ekyu.moe/killerducky/?data=/report/92e780aa897aea60.json).
  These hosted reports expire; the URL is a research example, not an app dependency.
- Verified hand-aligned bars, actual-choice outlines, separate Player/Mortal
  rows, a sorted Action/Q/P table, previous/next choice, previous/next error,
  and previous/next round controls. At one disagreement the first two
  recommendation percentages were 51.12% and 37.99%: differing from the
  first choice does not by itself establish a serious mistake.
- Read the [KillerDucky source](https://github.com/killerducky/killer_mortal_gui)
  and [mjai-reviewer FAQ](https://github.com/Equim-chan/mjai-reviewer/blob/master/faq.md).
  The FAQ explains that P reflects model preference, while Q has model-specific
  semantics. Our policy probabilities should not be presented as Mortal Q.
- Searched Mahjong Soul/MAKA references as additional context. Its authenticated
  in-client review UI was not inspected; no implementation depends on presumed
  MAKA behavior.

### Full reference feature checklist

Audited the live Options, About, round-score, and accumulated-risk dialogs,
plus the reference's `index.js` rendering and input handlers. About explains
the relative recommendation bars and lists the less visible keyboard-only
risk views. The checklist is bounded to this KillerDucky viewer and its
Mortal upload/review entry flow, rather than every feature of other reviewers.

| ID | Reference feature | Required equivalent in the existing Fenghua UI |
| --- | --- | --- |
| F01 | Submit a paipu and choose a reviewed player | Native JSON upload, local replay link/ID entry, player selection, analyze, reopen and retry. |
| F02 | Four-seat replay board, hands, calls and rivers | Reuse `TableBoard`; preserve drawn-tile separation, called-discard markers, active discard and distinguish drawn versus hand discards when known. |
| F03 | Round/dealer/seat indicators, wall remaining, dora and scores | Existing HUD with Fenghua prevailing/seat wind, dealer, wall/wangpai, wild indicator, dice and current scores where the record supports them. |
| F04 | Discard preference bars and player's chosen-tile outline | Tile-attached recommendation bars, exact percentages, actual-copy marker and AI-first-choice marker. Relative-to-best display is available and labeled. |
| F05 | Non-discard operation bars | Separate chii variants, pon, kan variants, pass, ron/tsumo and haitei choices, with tiles and probabilities. |
| F06 | Player versus Mortal operation rows | Prominent actual-versus-AI comparison with rank, match/disagreement and probability gap. |
| F07 | Complete Action/Q/P candidate table | All legal operations, policy probability and genuine per-action evaluation estimate. Sort by preference or evaluation; keep the policy recommendation explicit. |
| F08 | Previous/next event | Retain step transport, timeline and autoplay; cross-round stepping works. |
| F09 | Previous/next choice | Selected-seat decision navigation, including multiple responses at the same event. |
| F10 | Previous/next error and configurable threshold | Probability-ratio error filter `100 * P(actual) / P(best)`, plus existing severity filters. Persist settings and use the same predicate in jumps, markers and counts. |
| F11 | Previous/next round and start/end shortcuts | Round navigation and round-start/round-end jumps with clear disabled endpoints. |
| F12 | Clickable round score table and final totals | Round start scores, four-seat payout deltas, result, final scores/ranks, with rows that navigate. Add round agreement and rating summaries. |
| F13 | Round-end result dialog | Winner, ron/tsumo/draw, payer(s), winning tiles/melds, score patterns and payouts using stable `pattern_id` localization. |
| F14 | Hide/reveal opponent hands | Independent hand-reveal toggle, also reachable from a hand's accessible control. Never changes evaluation inputs. |
| F15 | Hide/reveal Mortal, spoiler-free “what would you do?” | Study mode hides actual choice, recommendations and future-result analysis until reveal; toggle from the advice area as well as settings. |
| F16 | Optional colored deal-in bars by opponent | Independent risk overlay with separate per-opponent and joint immediate-ron estimates under Fenghua rules. |
| F17 | Detailed deal-in tables and clickable wait breakdown | All tile faces, public remaining-copy counts, opponent threat, sampled legal winning-wait/pattern contributors, and drill-down into a tile. |
| F18 | Suji/known-safe information in the risk detail | Fenghua visibility and structural-risk evidence. Explain rule differences; a previously discarded tile is not automatically safe and riichi suji weights are not applicable. |
| F19 | Accumulated deal-in table with event jumps | Round exposure log by discarder/opponent, per-event risk, cumulative risk proxy, actual result and links to the pre-discard position. |
| F20 | Tsumo attempts: hit/miss, per-draw and cumulative chance | Draw-opportunity log with eligible winning tiles, public unseen counts, legal tsumo estimate, cumulative opportunity proxy and observed hit/miss. |
| F21 | Engine/model/version, time, temperature, matches/total, rating | Report details with checkpoint identity, reviewer/schema version, mode/length, measured loading/build time, actual evaluation settings, agreement and an explicitly model-relative 0–100 rating. |
| F22 | English, Simplified Chinese, Japanese, Korean, Russian | Complete replay/review namespace translations for all five; default to the app locale and integrate with its i18n provider/fallbacks. No second translation framework. |
| F23 | Keyboard help and wheel stepping | Accessible shortcuts for every reference operation and optional focused-table wheel stepping. Preserve usable page/drawer scrolling. |
| F24 | Bookmark current position and advice visibility in URL | Stable replay/round/decision/perspective/study-mode URL; restore on reload, back/forward and direct open. Private-import links retain owner authorization. |
| F25 | Responsive phone portrait/landscape | Adapt annotations and analysis within the existing fixed-stage table and responsive drawer; keep current geometry and controls usable. |

Every row must have a fixture or browser verification before the complete
feature ships. “Required equivalent” means the same study capability under
Fenghua rules, with data semantics disclosed, not identical pixel layout or
riichi-only mechanics. A missing evaluator/risk implementation is unfinished
work, not an accepted omission or a permanently empty column.

No offline-export control was found in this viewer's audited menus or input
handlers. Its bookmark feature is F24; downloadable standalone reports and
multi-model comparison are separate additions rather than parity requirements.

### Current application

Inspected the latest-main replay at `/replay/review-fixture` in the built-in
browser and read the implementation. The table occupies the main pane; a
300px scrolling drawer holds transport, round/perspective controls, scores,
then the review panel. On narrow screens the drawer follows below the table.

| Existing piece | Evidence and consequence |
| --- | --- |
| `ReplayLibrary.tsx` / `replayReference.ts` | Opens local match IDs and links; no file upload UI. External pasted origins are not fetched. |
| `Replay.tsx` | Uses the shared `TableBoard`; mounts `ReviewPanel` near the drawer's bottom. |
| `ReviewPanel.tsx` / `reviewUtils.ts` | Already shows action probability bars, severity counts, top gaps, optional value trend, and thresholds. Reuse the data and helpers. |
| `internal/review/report.go` | Already returns sorted legal action probabilities, chosen probability, and checkpoint identity through a batched evaluator. |
| `internal/rl/searchpool.go` / `ai/src/fh_mahjong_ai/search.py` | Existing determinized rollout machinery can inform action-value evaluation. It starts from an RL environment, not a paipu review snapshot; it prunes candidates and may fall back to a root value, so it is not a ready-made complete reviewer evaluator. |
| `internal/rl/observation.go` | `publicDangerScore` is a bounded handcrafted feature, not a deal-in probability. Multiplying it by 100 does not implement F16–F20. |
| `ai/src/fh_mahjong_ai/serving.py` | `evaluate_batch` computes deterministic masked softmax probabilities, without action-sampling temperature/top-k. |
| `internal/api/review.go` | Authenticated review builds; bounded admission, deduplication, checkpoint-aware caching, event-window handling, and divergence errors. Preserve these controls. |
| `internal/api/paipu.go` | Existing upload requires `ADMIN_SECRET`, accepts arbitrary valid JSON, and stores under a caller-supplied match ID. It is not a user upload API. |
| `replayEngine.ts` | `jumpToAction(i)` includes action i in the displayed state. Review observations are captured before the chosen operation. |
| `internal/review/replay.go` | Implicit passes anchor to the triggering discard. v2 traces are cross-checked, but an implicit report row still uses PASS even when a matched trace contains a losing bidder's real call. |

Knowledge-graph tools were unavailable in this session, including index and
coverage tools. These findings use direct source inspection and browser
observations, not graph verification or an exhaustive architecture audit.
The local preview had no database or project policy server; project AI
generation was not smoke-tested during planning.

## Proposed experience

### 1. Upload and analyze

Add an upload section to the existing replay library alongside its local
link/ID entry. Accept a `.json` Fenghua paipu, show its players, ruleset,
round count, and file name, then select the player to study.

The primary action is **Upload and analyze**. Preserve the selected player
when opening the replay. Offer **Open replay** when the model service is
unavailable so a service outage does not prevent playback.

Display honest states: validating file, uploading, generating review, ready,
or a specific failure with retry. The existing build API does not expose
percentage progress; do not invent a progress percentage or ETA. Avoid
starting duplicate builds through repeated clicks. Handle an expired login
with the project's existing return-to flow.

### 2. Keep the current table and add advice at the hand

The selected player stays at the bottom of the existing shared table.
Place a small bar and percentage above each legal discard tile, attached
to its actual rendered tile wrapper so sorting, the drawn-tile gap, and
perspective changes cannot misalign the advice.

- Use a teal bar for recommendation weight and a gold marker for AI first
  choice. Give the actual physical discard a distinct outline and label.
- Same-face tile copies share the policy's face-level recommendation; do
  not divide its probability between copies. The raw paipu tile ID identifies
  the actual copy, including ID 0. Ties can have several AI first choices.
- Put chii, pon, the three kan variants, pass, ron, tsumo, and haitei
  accept/refuse in a compact operation strip with tile illustrations and
  percentages. Do not collapse distinct chii or kan actions into one row.
- Clicking a candidate highlights its tiles and details; it does not alter
  the recorded match or simulate an unrecorded continuation.
- Provide an **AI advice** toggle for studying the position before revealing
  recommendations. Study mode must also hide the actual-choice outline,
  comparison rows, disagreement ticks and future outcome/risk summaries.
  Keep the existing opponent-hand toggle independent.
- Retain exact percentages even when using a relative-to-best bar scale for
  readability. Label the scale; do not imply a full-height bar means a 100%
  recommendation. No visual smoothing changes the numeric probabilities.

Use existing table typography and materials. Suggested semantic colors:
table slate `#4f6374`, drawer ink `#17242b`, readable text `#f5f7fa`, advice
teal `#2fa88f`, AI marker gold `#d2a85f`, disagreement amber `#e5a53b`.
Use borders/icons/text as well as color. These are local accents, not a
replacement design system. Preserve hand starts, HUD alignment, tile size,
and discard symmetry.

### 3. Make the comparison immediately visible

Move current-decision analysis above secondary drawer controls. Show:

| Item | Example copy using illustrative data |
| --- | --- |
| Actual operation | You: discard 3m — 18.4%, ranked 3 of 11 |
| AI first choice | AI: discard 9m — 72.1% |
| Comparison | Different choice; recommendation gap 53.7 percentage points |
| Candidates | Tile/operation, recommendation %, rank, actual/AI markers |

Call the percentage **AI recommendation / AI 推荐度**. Explain briefly that
it represents the model's preference among legal operations. It is not a
calibrated probability that the operation is correct, wins the hand, or
avoids a deal-in. Add an **Evaluation** column backed by the new per-action
evaluator described below. The current state value cannot fill this column.
The Fenghua estimate has its own stated objective and units; do not call it
Mortal Q or imply its numbers are comparable to Mortal's model outputs.
Keep the existing state-value trend only when its calibration contract permits.

Show the top candidates first with **Show all legal operations**. Always
include the actual operation even when it falls outside the initial list.
Model identity, generation settings, measured times and help belong in report
details, with a clear visible model label. Extend the existing i18n resources
for the five reviewer locales; do not limit parity to the app's current two.

### 4. Navigate decisions and see each round's agreement

Retain action-by-action playback. Add previous/next decision and
previous/next disagreement, scoped to the selected player and able to cross
round boundaries. Stop autoplay on a jump. Disable navigation at its ends.

Add a compact round overview with recorded decision count, AI first-choice
match rate, disagreement count, and largest recommendation gap. Selecting
a row opens that round; selecting a disagreement opens its decision.

Define match rate as recorded comparable choices that are tied for the
highest policy probability, divided by recorded comparable choices.
Use a small documented float tolerance for ties. Forced/automatic actions
and inferred choices are excluded. A zero denominator displays an em dash.
Keep mean chosen recommendation separate from match rate: they are different
metrics. Add the reference's ratio-threshold filter (default 100%, every
nonmatching choice), while retaining existing severity filters as an advanced
alternative. Exact/tolerance ties never become errors. A 0% threshold flags
none; invalid inputs do not overwrite the saved setting. Use neutral
disagreement wording in the primary experience.

Round rows also show each seat's starting score and payout delta, winner/draw,
and ending scores. The game footer gives final scores/ranks according to the
recorded match mode. A result opens the existing settlement presentation with
winning tiles, melds and scoring patterns. Replace riichi pot/honba fields
with relevant Fenghua match context; do not invent nonexistent mechanics.

Add an overall and per-round model-relative rating using the per-action
evaluation estimates. For each comparable decision with a non-flat range,
`r = (evaluation(actual) - min) / (max - min)`; rating is
`100 * mean(r)^2`. Exclude forced/inferred/unknown decisions and flat or
missing ranges, disclose included/excluded counts, and show an em dash for
no rated decisions. This follows the reference's normalized-rating idea;
it is model/method specific, not a player skill rank or a cross-model score.

Desktop: table with hand bars plus the existing drawer, with the comparison
and decision controls near its top. Mobile: table above the current bottom
panel; keep comparison/navigation reachable and allow the candidate list
to scroll. No second table renderer or forced landscape. Organize the existing
drawer into **Decision**, **Rounds**, and **Risk** views; keep transport and
current round accessible in every view. Put full risk/score tables in the
app's existing themed dialog or expanded panel. Show secondary evaluation
details on row expansion on small screens instead of squeezing illegible
columns into the 300px drawer.

### 5. Advanced risk and draw-opportunity study

Keep risk separate from AI preference: use an independent toggle and compact
per-opponent bars/labels above the selected hand. Selecting an opponent or
tile opens its tile-risk table and contributors, with public remaining-copy
counts and explanation of the estimate. Include an all-opponents estimate
from joint sampled worlds; summing opponent percentages is not a probability.

The round risk view contains the reference's exposure and tsumo-opportunity
logs, actual result, and navigation to the originating position. Show a
cumulative exposure proxy `1 - product(1 - p_event)`, labeled as a proxy
because events are dependent. First combine opponents for an event, then
accumulate events, so a single discard is not counted several times.
Use the same qualified label for cumulative draw opportunities.

Fenghua waits include wild substitutions, flower wilds and independence
routes, with ron's four-point minimum and tsumo's separate eligibility.
Explain visibility/structural evidence instead of presenting riichi suji or
genbutsu as guarantees. Risk estimation must work without riichi declarations.
Concealed opponents' actual waits can be offered after reveal as retrospective
facts, clearly separate from the public-information estimate.

### 6. Preferences, shortcuts, and bookmarks

Preferences include review language, hands, advice/study mode, risk visibility,
bar scale and error threshold; persist them with validated defaults. Help
lists every operation and explains probability, evaluation, rating and risk.
Expose ordinary buttons for keyboard-only advanced features.

Keep the app's existing Left/Right event, Up/Down round and Space autoplay
bindings. Add Alt+Up/Down for choices, PageUp/PageDown or comma/period for
errors, Home/End for round boundaries, brackets for rounds, and h/m/d/e/a/z/b/?
for hands/advice/risk/threshold/accumulated-risk/risk-details/bookmark/help.
Document the adapted keys rather than silently repurposing current controls.
Ignore shortcuts in text fields, trap dialog focus, and use Escape to dismiss.
Wheel stepping is opt-in and restricted to a focused table surface.

Bookmark via a visible **Copy position link** control as well as b. Encode
stable decision ID, round/cursor fallback, seat and study state, validate URL
parameters, and handle obsolete model/report decision IDs gracefully. A URL
must not publish private uploaded data or grant someone new access.

## Correctness work required before UI advice

### Explicit review positions

Separate a decision's report identity from its display position. Add report
schema v2 fields for a stable decision ID, position immediately before the
choice, and recorded-choice provenance. Keep `actionIndex` as the historical
action anchor for compatibility; do not globally reinterpret playback.

The display cursor is the last action already applied:

- A recorded discard/call/kan/win at action i is reviewed at i - 1.
- An implicit response to discard i is reviewed after discard i, while
  the triggering tile is still on the table.
- Multiple seats responding to the same discard have separate decision IDs
  even when their display position is the same.
- Haitei and replacement-draw records need exact cursor checks against the
  server's pre-choice state; do not assume every action fits a simple offset.

Add a focused `jumpToDecision` adapter while keeping `jumpToAction` intact.
Tests must verify the actual hand, drawn tile, active discard, and meld state,
not merely the cursor number. Clear advice when moving outside its position,
changing the replay, or reaching a round result.

### Recorded versus inferred operations

Have v2 trace matching return the matched decision row. Use its real
`chosenId` for the review comparison when valid, while still feeding an
implicit pass to the reconstruction engine when needed to reproduce the
winning action stream. In particular, a losing bidder's recorded pon must
not be reported as their recorded pass.

Use choice provenance such as `recorded`, `inferred`, or `unknown`. For v1
unrecorded responses and v2 timeouts, show reconstructed advice with a clear
inferred/unknown label and exclude them from agreement and disagreement
statistics. Failed trace encoding also remains unknown. Preserve fail-loud
legality/trace/setup checks; never silently issue a plausible partial report.

Automatic draws/flower replacements stay playback events. A sole legal
choice is labeled **Forced operation**; it must not inflate agreement by
being presented as a model evaluated 100% confident recommendation.

Version frontend/back-end JSON types together. This is a paipu/report JSON
change, not a new game-state protobuf message. If implementation introduces
a protobuf field, follow the repository's proto-first regeneration workflow.

### Genuine per-action evaluation (F07 and F21)

Add a reviewer-specific evaluator rather than reinterpret softmax logits or
copy the current state's value into every row. Use determinized counterfactual
rollouts as the initial method, informed by the existing search pool:

1. Capture a branchable engine snapshot at the exact decision, including public
   event history and an explicit root seat. Build a narrow bridge from review
   reconstruction to the RL/search environment; there is no existing arbitrary
   paipu-snapshot endpoint to assume available.
2. Preserve the acting seat's information, then redeal opponents' concealed
   tiles and unseen walls before evaluation. Paired worlds and future-round
   seeds derive from a review seed and determinization group, never the live
   paipu seed/future. Mask event history with the same serving contract.
3. Evaluate **all** legal action IDs on paired sampled worlds, including the
   recorded action even with near-zero policy preference. Existing search
   candidate pruning cannot serve the complete reviewer table.
4. Apply the candidate to the root seat, then continue with the fixed served
   checkpoint. Respect interrupt priority, root-seat turn boundaries, legal
   masks, flowers/wangpai/haitei and the recorded classic/Chongci match mode.
5. Estimate discounted root-seat return on the checkpoint's training reward
   scale. Report method/version, objective, units, gamma, seed, sampled worlds,
   rollout horizon, terminal/bootstrap counts and standard error. Only use a
   valid public-observation value head with matching training convention for
   leaf bootstraps. Without such a head, use terminal rollouts; a cap that
   prevents an estimate is an explicit failure/incomplete analysis.
6. Do not carry search's gameplay fallback (`root_value` for the greedy
   candidate, `-inf` for failed candidates) into review results. It cannot be
   displayed as a measured action evaluation. Invalid/error samples, missing
   actions or contract mismatches keep evaluation incomplete and provide a
   retryable reason. No placeholder zero or fabricated rating.

Start benchmarking with 32 paired worlds per decision and the existing search
decision cap; choose final budgets from representative complete paipu timings
and uncertainty, not from a UI loading-time guess. Keep policy P and its first
choice unchanged. Estimated rollout return can rank alternatives differently;
the UI must state which ordering it shows. This is an action-evaluation study
feature, not an unrequested replacement for the live bot policy.

The report adds an explicit recommended action, per-action evaluation and
uncertainty, generation-method metadata, completeness and rating summaries.
Verify repeated-run determinism, paired candidate worlds, immediate wins,
classic/Chongci returns, explicit root-seat interrupts, bootstrap conventions,
and immunity to hidden-state/future-seed changes. The existing state value
and hand trend remain distinct optional fields.

### Fenghua risk and opportunity evaluator (F16–F20)

Build a separate versioned sampler/estimator using the same public-information
boundary. Initial risk estimates are conditional on a disclosed sampling
model, not calibrated model predictions or certainties about hidden hands.
The existing `publicDangerScore` can inform explanatory features but is not
the numeric probability estimator.

- At each relevant position, construct unseen-tile counts from the observer's
  own hand and public hands/melds/flowers/discards/indicator exactly once.
  Include hand sizes, replacement draws and live/dead-wall constraints. Do
  not condition on future discards, actual concealed opponents or the paipu's
  wall seed. Changing the reveal toggle never changes this input.
- Sample joint hidden worlds consistent with that information. Evaluate
  hypothetical discards using the authoritative rules and score gate, returning
  each opponent's legal-ron frequency and a joint any-opponent frequency.
  Treat blocked/non-discardable wilds and flower faces according to the rules;
  report not applicable rather than assume all 42 faces are legal discards.
  Include eligible risky-kan response risk as a separately labeled operation.
- Return opponent threat/ready estimates and each tile's contributing winning
  structures, pattern IDs, visible unseen counts, sample counts and uncertainty.
  Include wild-enabled and independence wins; do not reduce every wait to a
  riichi two-tile shape or claim a past discard makes a tile safe.
- Compute pre-draw legal tsumo opportunities from the acting player's known
  hand, unseen counts and correct draw source. Use public-information estimates
  for unknown wall allocation; then attach the recorded hit/miss separately.
  Do not use the observed draw to construct its earlier estimated chance.
- Build round exposure/opportunity logs for the relevant seats, labeled by
  whose information the estimate uses. Give each entry a decision/event
  anchor, one combined risk for each event, opponent breakdown and cumulative
  proxy. Retrospective outcome/hands are reveal-only facts.

Benchmark a proposed 128 worlds per risk position, reuse worlds across tile
faces and cache by input/method/seed. Test exact small-state enumeration,
four-point ron versus tsumo, unseen-count conservation, wild/flower routes,
multiple opponents, no waits, terminal positions and draw-source constraints.
Use held-out paipu outcomes to measure calibration error before describing
the estimate as calibrated. Uniform/heuristic hidden-world sampling can be
biased by opponent choices; disclose that model in details and retain honest
sampling uncertainty rather than claim attribution for the champion's choice.

## Import and report architecture

Use a dedicated authenticated import flow instead of exposing the admin
uploader to ordinary accounts:

- `POST /api/v1/replay-imports`: bounded file body, schema/ruleset/version/
  catalog validation, server-issued replay ID, owner account, content hash.
- `GET /api/v1/replay-imports/:id`: owner-authorized replay read.
- `GET/POST /api/v1/replay-imports/:id/review`: owner-authorized report read/build.
- Frontend route `/replay/import/:id` uses the same viewer/controller through
  a source adapter. Existing `/replay/:matchId` continues to work.

Imported records remain immutable and private to the importing account.
Never trust uploaded `players[].userId` as ownership or allow an embedded
`matchId` to overwrite a recorded live match. Store imports separately from
the live paipu/history records; list them in a distinct Imported section.
Preserve the original source match ID as metadata.

Start with explicit proposed limits (10 MiB JSON, 256 rounds, 100,000 total
actions/trace rows), verify them against real local exports, and document
them. Reject oversized, malformed, unsupported, or unfinished records before
model work. Require complete round results, four valid seats, legal tile
ranges, valid seeds, and supported schema/catalog revisions. Apply matching
client checks for fast feedback, with authoritative server validation.
Engine divergence during full review returns a useful round/action error.

Reuse `ExtractDecisions`, `BuildReport`, public-seat observations, and the
existing evaluator. Refactor existing request/build helpers only as needed
to share rate limits, admission slots, bounded contexts, identity checks,
and error mappings. Imported inference must not bypass the existing limits
or use opponents' concealed tiles/future draws as model inputs.

Cache identity must include immutable input identity, served checkpoint SHA,
report schema/reconstruction version, evaluation/risk method and sampling
configuration, and evaluation contract (including event window). Existing
match/checkpoint cache hits must reject obsolete
schema-v1 rows for the new experience; otherwise the corrected anchors and
choice provenance never take effect. Extend storage/build deduplication
keys consistently and preserve checkpoint promotion/rollback behavior.

The full evaluation is heavier than the existing policy-only batch. Use a
bounded, resumable background review job with phase states: reconstructing,
policy, action evaluation, risk and complete. POST admits/deduplicates the
job; GET returns status or the completed report. Persist phase/chunk progress,
recover interrupted jobs, offer cancel/retry and stop work for cancelled jobs.
Maintain the current shared admission/rate/concurrency controls; do not bypass
them through imports or extra evaluators. Bound queued work, replay size,
simulation slots, time and retained intermediate data; serialize GPU batches
through the policy service's existing ownership boundary.

Show policy advice as soon as its phase completes, with action/risk phases
explicitly pending. A report is **complete** only when every required phase
and every legal action has a valid result. Base usable progress on completed
work units after enumeration, never a fictional ETA; unexpected cap/failure
cannot silently turn the feature into probability-only mode. Cache completed
chunks by the full evaluation identity so retries avoid repeating valid work.

## Implementation sequence

1. **Fix decision truth and positions.** Update `internal/review/replay.go`,
   `report.go`, trace/report tests, the JSON client types, cache versioning,
   and replay decision-position helpers. Prove pre-choice alignment and
   recorded losing-call handling before drawing advice.
2. **Build imports and review jobs.** Add import API/storage validation and
   ownership, source adapters, uploaded history and analyze states. Add durable
   bounded job orchestration around shared reconstruction/policy facilities,
   with cancellation, resumption, deduplication and phase-aware cache keys.
3. **Implement action evaluation and risk.** Add the branch-snapshot bridge,
   all-legal paired rollouts, uncertainty/metadata, rating, Fenghua risk/wait
   drill-down and exposure/tsumo logs. Run real-checkpoint timing and sampler
   correctness checks before deciding production generation budgets.
4. **Integrate advice.** Add optional presentation-only tile annotations to
   shared table types/hand rendering, supplied only by replay. Build the
   operation strip, Action/Probability/Evaluation table, study mode and risk
   overlays in the existing replay drawer and table geometry.
5. **Complete summaries and controls.** Implement round/result/final-score
   views, agreement/rating, ratio filter, risk dialogs, decision/error jumps,
   bookmarks, preferences, shortcut help and all five review languages.
6. **Verify every parity item.** Attach fixture/browser evidence to F01–F25,
   run required CI gates and real-policy complete-review smoke checks, and
   inspect desktop/phone screenshots in Codex's built-in browser. Intermediate
   milestones do not reduce the final feature requirements.

Likely implementation files: `web/src/features/replay/*`,
`web/src/table/types.ts`, `web/src/table/seat/ClosedHand.tsx` and the table
prop chain, `web/src/i18n/locales/*`, `internal/review/*`,
`internal/api/{server,review,paipu}.go` plus a focused import module,
and `internal/storage/` models/migration. New evaluation work also affects
`internal/rl/` snapshot/search integration and `ai/src/fh_mahjong_ai/` reviewer
evaluation/serving, plus review-job and risk modules with appropriate tests.
Update the relevant directory
`CLAUDE.md` files and preserve their `AGENTS.md` symlinks.

## Acceptance and verification

- A valid native v1/v2 JSON file can be uploaded, analyzed, reopened, and
  studied from the selected player's perspective. Cross-account import
  access and caller-controlled overwrites are rejected.
- An actual choice and every legal candidate have correct labels, percentages,
  rank, and tile identity. Percentages sum to approximately 100% over legal
  action IDs. Reject NaN, infinite, negative, or zero-total evaluator outputs.
- Recorded discards are shown before the tile leaves the hand; response
  decisions show the triggering discard. Multi-seat windows, losing calls,
  explicit pass, timeout, and legacy inferred pass are covered separately.
- Duplicate faces, tile ID 0, all flower wilds, chii variants, three kan
  variants, haitei accept/refuse, and round-end choices render faithfully.
- Every jump, perspective change, autoplay transition, and source change
  keeps advice/report/board synchronized. A late response from another replay
  never appears on the current replay.
- Round/game agreement uses the stated recorded-choice denominator. Exact
  ties, close alternatives, no decisions, and inferred choices are covered.
- Loading, missing report, 401/403, 413, 422, 429, 502/503, timeout, and retry
  states are specific and usable. No fake inference percentages/progress.
- Cache tests cover schema upgrades, model reload/promotion/rollback, and
  unchanged-input deduplication. Imported review load shares live-review limits.
- Every F01–F25 feature has a recorded check; F07, F16–F21 cannot pass with
  fake values, omitted candidates, hardcoded bars or permanently disabled UI.
- Per-action evaluation covers all legal alternatives, retains raw policy
  preference, discloses method/units/uncertainty, and passes public-information
  and deterministic paired-rollout tests. Rating covers flat/missing ranges
  and its separate included/excluded denominator.
- Risk details, tile contributors, joint opponent estimates, event jumps,
  cumulative proxy and tsumo logs are checked against deterministic or exact
  fixtures. Revealing true hands/future outcomes never changes earlier estimates.
- Keyboard/button equivalents, modal focus, focused wheel stepping, persisted
  ratio threshold and reload/back/forward position bookmarks are exercised.
  Study mode hides actual and future-result spoilers in all analysis views.
- Jobs recover after restart, resume valid chunks, cancel promptly, reject
  excess admission, bound simulation/GPU resources and expose incomplete
  evaluations honestly. Real complete-paipu latency and resource usage are
  measured before generation budgets are finalized.
- Browser checks cover 1440x900, 1280x720, 390x844 portrait, and 844x390
  landscape, all five review languages, all four perspectives, 30 discards, and four
  direct kans. Hand advice must not collide with melds/flowers/discards.
- Run `gofmt -l .`, `go vet ./...`, `go test ./...`, and
  `cd web && npx tsc && npx vitest run` after implementation. If Python
  inference code changes, run its relevant tests through `uv run --project ai`.

Completion means the upload-to-analysis-to-decision-navigation workflow and
every parity feature are verified with a real served project checkpoint,
deterministic fixtures and browser screenshots. The full adapted experience
is the deliverable; a probability-only milestone, mock report or passing unit
tests alone is not completion. The implementation and verification record below distinguishes this plan from observed evidence.

## Implementation record (2026-10-04)

The implementation uses `paired-round-return-v1`: full terminal round rollouts under the served checkpoint, paired across every legal candidate, rather than a root-return/bootstrap blend. This avoids displaying a privileged or uncalibrated critic value as action evaluation. Values are mean net round payout in Fenghua points with standard error and sample count. All legal alternatives are retained. Default budgets are 32 worlds and 128 risk worlds; a 30-minute job can resume complete chunks. Reconstruction is bounded to 4096 decisions.

The implementation covers F01-F25 in the existing table/drawer. A native v2 fixture generated through the project engine was uploaded through Codex's built-in browser, with real cookie/CSRF auth, and analyzed by the operational iter275 checkpoint (SHA 377d99bc7e5d29dad22a253145f09d124fc4e9b2007bb1abb4b9912d44059769). The two-world full smoke completed all 45 decisions/90 risk-evaluation chunks in 63.15 seconds; two normal 32-world browser jobs completed all 45 decisions and all 390 legal candidates, with 32 terminal samples per candidate, in 977.6 and 1045.2 seconds on local CPU. The latter is retained in the persistent local preview. This is a real policy smoke, not promotion evidence.

The risk estimator remains a uniform unseen-world legal-wait study tool. It is independent of AI preference, has no calibration claim, and does not call previously discarded Fenghua tiles safe. Other-face hypothetical estimates do not condition a future draw; own legal discard estimates use the known held tile. Contributors can overlap by scoring pattern. Cumulative quantities are explicitly dependent-event proxies.

Verification: full Go suite, go vet, clean gofmt output, frontend TypeScript, 268 frontend tests and production build passed. Targeted cancel/resume and ownership tests also pass under Go's race detector. Browser evidence and final acceptance checks are recorded below.


### Final verification record

All browser checks used Codex's built-in browser. The preview uses normal production routes and cookie/CSRF auth with a synthetic local account and persistent SQLite, not a deployed PostgreSQL environment. The operational policy and its promotion pointer were unchanged. Completed results reopened after a backend restart. The first temporary in-memory preview expired at its one-hour test timeout; its successor retains imports/jobs across restart.

A scorer-backed legal-tsumo fixture caught an initial double-count of the drawn tile. The correction uses the pre-draw hand plus the hypothetical tile, and the complete actual hand with no added tile for hit detection. Draw estimates are rebuilt cheaply on resume. The local stored report was revalidated through the normal resume builder after this correction; completed real candidate rollouts were retained. Its actual draw opportunities include nonzero copy-weighted estimates. A root-observation equality regression also confirms rollout branches preserve the same reviewed match context. The suggested redundant context change was removed before the final checks.

| Feature | Evidence |
|---|---|
| F01 | Browser file chooser, player preview, authenticated upload/analyze/reopen; owner/CSRF/dedup/import-isolation tests. |
| F02 | All four browser perspectives; drawn slot; called-river and tile-zero drawn-discard provenance regressions. |
| F03 | Browser Fenghua HUD: winds, wild indicator, dice, wall/wangpai and scores. |
| F04 | Browser physical-copy marker, preference percentages, best outline; duplicate/tile-zero annotation tests. |
| F05 | Full catalog operation labels and all legal bars; recorded losing-response reconstruction test. |
| F06 | Browser actual-versus-policy comparison, rank, gap and agreement. |
| F07 | Real 390-candidate result with n=32, mean and standard error; confidence/value column sorting. |
| F08 | Event transport, timeline, autoplay and keyboard browser checks. |
| F09 | Decision navigation; shared-position selection regression. |
| F10 | Ratio predicate tests, persisted threshold; same predicate in navigation and timeline. |
| F11 | Round start/end browser controls; existing round stepping engine behavior retained. |
| F12 | Browser round summary, payouts, agreement/rating and final ranks; study-mode future-score exclusion test. |
| F13 | Browser real ron settlement; all 41 stable scoring ids localized in five reviewer languages, with legacy-name fallback. |
| F14 | Independent hand toggle and H shortcut; earlier estimates do not change with reveal. |
| F15 | Browser hidden advice/reveal plus SSR spoiler tests; future error markers remain hidden in study mode. |
| F16 | Real joint/opponent sample frequencies and independent overlay; annotated dense fixtures. |
| F17 | Browser nonzero 5s risk detail: legal independence contributor, public hypothetical example; modal Escape/focus return. |
| F18 | Browser visibility explanation; authoritative Fenghua legal scorer, no riichi suji/furiten safety claim. |
| F19 | Clickable discard log, per-opponent and joint cumulative proxies; observed outcome withheld until visible in study mode. |
| F20 | Actual legal-tsumo and copy-weighted opportunity test; browser real nonzero draw log and event jump. |
| F21 | Real checkpoint SHA, method/schema/config/time, agreement and separate rating denominator. |
| F22 | Browser en/zh-CN/ja/ko/ru controls; complete resource/placeholder tests. |
| F23 | Browser keyboard controls, focused optional wheel, native risk modal focus and Escape. |
| F24 | Browser bookmark reload and library paste restore round/cursor/seat/decision/advice visibility; shared-response selection, malformed query and strictly local import/match route tests. |
| F25 | Browser 1440x900, 1280x720, 390x844 and 844x390; annotated thirty-discard/four-direct-kan synthetic geometry fixtures. |

The risk model samples uniform unseen legal waits. It is a study estimate, not a calibrated opponent model; zero sample hits do not prove safety. Candidate evaluation uncertainty is substantial at 32 worlds, and the objective is round payout rather than full-match placement. A complete one-round CPU analysis took roughly 16–17 minutes; larger replays can require explicit resume after the 30-minute execution budget. Peak RSS and multi-job capacity were not benchmarked, and production PostgreSQL deployment was not exercised. These limits are distinct from the passing local correctness checks.

Final screenshot artifacts: `paipu-review-desktop.png` and `paipu-review-portrait.png` under `/Users/plasma/.codex/visualizations/2026/10/04/01a105a3-d56d-72d3-bf8d-4de87814a3e2/`. The retained local preview is `http://127.0.0.1:3002/replay/import/a3575ef4-29e8-4b37-9d24-57216ba68676?round=0&cursor=22&seat=2&study=0&advice=1&decision=r0-d15-s2`. Its SQLite browser harness and policy are development-only processes, outside production deployment.

Follow-up integration verification found that reconstruction forced the recorded dealer on later classic hands, skipping the natural RNG draw and shifting the wall shuffle. Reconstruction now forces a later dealer only for Chongci mode, honoring explicit match metadata before legacy score-based inference. A completed, authoritative two-hand capped-classic v2 fixture with nonzero starting scores reproduces the original failure and verifies imported deal/trace/settlement reconstruction and captured study branches in both hands. Existing multi-round Chongci and checkpoint-resume regressions remain passing. This check does not constitute an additional real-policy multi-round analysis.

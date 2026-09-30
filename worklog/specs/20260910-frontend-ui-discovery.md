# Frontend UI discovery

Status: draft concepts and source audit; not an approved implementation specification.
Date: 2026-09-10. Scope: Fenghua Mahjong web frontend.

## Recommendation

User priorities: home, rooms and navigation; desktop and phone equally. Start with direction A, Direct play, as the prototype candidate. Place matchmaking and private-room creation directly on the entry screen. Add a clearly labeled invitation-link entry and consistent Play / Replays / Tools navigation. Make room occupancy, host authority, sharing and the reason a game cannot start immediately understandable. Keep table redesign secondary to this effort. This is a design hypothesis, not a validated winner.

Compare with B, Room first, if joining friends is the dominant entry task; compare with C, Activity hub, if play, replay and tools are frequently used together. Do not combine all three navigation systems. Palette selection comes after layout selection.

[Open the three concept boards](20260910-frontend-ui-directions.svg). These are schematic wireframes, not screenshots or a functioning prototype. Desktop home and waiting-room screens use comparable scenarios. Each direction also shows phone home and room layouts. Desktop and phone are reviewed as an equally weighted pair.

## Evidence and limits

The existing frontend answered HTTP 200 at http://localhost:3000. Browser discovery returned no available browsers, so no rendered application screens, screenshots, timing, touch interaction, or usability outcomes were observed. No authenticated games were joined. Source inspection is direct: graph tools were unavailable. Production code was not changed. An unrelated pre-existing untracked worklog file was left alone.

### Source observations and design implications

| Observation | Evidence | Interpretation and next check |
| --- | --- | --- |
| Home links to `/play`, tools, replay and profile; matchmaking is a separate screen. | `web/src/features/lobby/Home.tsx`, Home; `web/src/features/lobby/Lobby.tsx`, Lobby | Test bringing the two play choices to entry. This removes a navigation step, but we have not established that the step causes confusion. Preserve authentication return intent and cancellation semantics. |
| Small coarse-pointer portrait screens rotate the live board 90 degrees; replay is excluded. | `web/src/table/table-geometry.css`, portrait query around line 702 | Test whether transition between upright lobby and rotated game is understandable. Compare an explicit landscape invitation with current behavior; don't promise a readable portrait table before testing the full hand. |
| Play and next-step both use ▶; transport buttons lack explicit accessible names. | `web/src/features/replay/Replay.tsx:320` | Concrete ambiguity in source. Use distinct play/step glyphs and localized accessible labels; validate keyboard focus and announce current action. |
| Stage aspect is clamped from 16:9 to 2.39; compact stages use a shorter design height. | `web/src/table/stage/computeStageLayout.ts` | There is already a responsive geometry system. Measure remaining space and tile sizes before replacing it. The stage is not simply an immutable 1600×900 canvas. |
| Live and replay share board/result presentation; table demos include interrupt, multi-chii and called-hand scenarios. | `web/src/App.tsx`; `web/src/features/dev/TableSample.tsx`; `web/src/features/dev/RoundResultDemo.tsx` | Use these fixtures for fair comparisons. Preserve shared board rendering to prevent live/replay layout divergence. Demo behavior does not prove actual network flow correctness. |

### Baseline capture list

Capture both Chinese and English at 1440×900, 1024×768, 393×852 and 852×393. Add 375×667 and 667×375 for compact-phone stress checks; use coarse-pointer emulation for the rotation query. Record viewport, locale, fixture and build revision with every screenshot.

- `/`: anonymous and authenticated entry, language switch.
- `/play`: idle, connecting, queued, cancellation and failed request.
- `/room/new` and a local test room: invitation, empty seat, host start, guest waiting, rejoin. A real local test account is needed to validate authentication and networking.
- `/tools/table-sample`: active hand, interrupt, multi-chii, called-hand, settlement. Measure tile faces and control bounds; distinguish the fixture's sample English labels from production localization.
- `/tools/round-result`: tsumo, ron, draw and long breakdown; ready/waiting state at every built-in viewport. Ready and Exit must remain reachable.
- `/replay`: empty library, completed match and invalid reference; `/replay/:matchId`: playback, next step, round selection, perspective and review. Use a known local replay or a labeled fixture.
- Reconnection: never cover the local hand with a persistent banner; communicate whether interaction is available. Test actual reconnect behavior separately from mockups.

Annotate each screenshot with task, observed problem, consequence, severity and proposed experiment. Record “no issue observed” where appropriate. Do not convert this source audit into invented visual findings.

## Reference research

- [Mahjong Soul official getting-started guide](https://mahjongsoul.com/startguide/assets/jantama_startguide.pdf): source covers starting play, ranked/friend games and in-game operations. Use its task separation as a reference for novice instructions. Riichi rules are not Fenghua rules; do not transplant scoring, riichi controls or dead-wall assumptions. Text retrieved; visual screenshot comparison remains pending.
- [Lichess features](https://lichess.org/features) and [analysis entry](https://lichess.org/analysis): source establishes separate play, study and analysis destinations. Our inference is that Fenghua replay may benefit from a workspace distinct from play. The analysis page reported blocked assets through the text fetch; no visual quality judgment is supported.
- [Riichi City official site](https://lizhimahjong.com/): candidate reference only; retrieved page had no usable content. Do not treat it as a completed comparison.

The reference board remains incomplete until actual interface images can be inspected. No claims about competitor usability or player preference have been established.

## Design directions

### A — Direct play

Primary job: get into a game and make the next decision confidently.

- Entry: brand and language/account utilities above Find a game and Create a room. Show the selected ruleset beside those actions; replay and tools follow with lower emphasis. Rejoining an active match takes priority when that state is known.
- In play: quiet felt; stable local hand; turn and call feedback near relevant tiles; a consistent action area above the hand. Secondary table settings live in an explicit menu. Show connection status without obscuring play.
- Settlement: winner and win type, four seat deltas, scoring details, then reachable Ready and Exit. Match completion has a separate replay action; do not promise library access to unfinished matches.
- Phone: upright entry/results; prototype landscape play first. The portrait strategy is unresolved, not silently assumed solved by scaling.
- Candidate colors: shell `#F7F9FB`, ink `#273346`, action blue `#22559C`, felt `#255B53`, tile white `#FFFFFF`, error red `#B8323C`.
- Type: Noto Sans SC for Chinese; Source Sans 3 for Latin UI and numerals. Semibold labels and tabular score figures; left-aligned text, spatially centered board.
- Tradeoff: clear and direct, but less atmosphere. The Mahjong tile/board is the memorable visual element; avoid a generic dashboard or hero banner.

### B — Room first

Primary job: make joining friends and returning to a familiar table inviting.

- Entry: a small table motif beside Find a game and Invite friends. Room screens give four seats, host status and occupancy the main visual space. There is no new pre-game readiness system. Keep game controls as restrained as A.
- Settlement: retain scoring hierarchy while emphasizing who is ready for the next round.
- Phone: stack the room seats and primary actions; keep ornament out of the hand/action area. Same gameplay geometry comparison as A.
- Candidate colors: shell `#F2F4EE`, ink `#273346`, jade `#236B54`, felt `#214D43`, white `#FFFFFF`, error red `#B8323C`.
- Type: Noto Serif SC only for the compact brand/room title; Noto Sans SC for controls and dense information. Left alignment; use the four-seat arrangement only where it conveys room state.
- Tradeoff: stronger identity but more room-specific UI. Avoid reproducing the current decoration with new colors and calling it a redesign.

### C — Activity hub

Primary job: move between playing and understanding completed games.

- Entry: Play, Review and Tools as distinct destinations. Play still exposes matchmaking and room creation directly.
- In play: hide analysis chrome. In desktop review: board on the left, timeline/decision details on the right; transport remains visible below the board. On phone: board, persistent transport, then a contained details panel.
- Settlement: Ready remains primary mid-match; at match completion, Review this game opens the appropriate replay.
- Candidate colors: shell `#F6F8FC`, ink `#273346`, indigo `#4C59A5`, felt `#304B69`, white `#FFFFFF`, error red `#B8323C`.
- Type: Noto Sans SC and Source Sans 3; tabular action/score figures. Give the board more space than metadata; keep analysis text left aligned.
- Tradeoff: best candidate if review matters frequently; otherwise navigation and panel complexity may be unnecessary.

The SVG uses generic fallback type for portability. These font and color specifications are proposed inputs for the prototype, not proof of accessibility contrast or final typography.

## Revised navigation and room specification

The user prioritized navigation and rooms after the initial broad concepts. The linked board now reflects that narrower focus; palette and in-game notes above are secondary considerations.

### Home and navigation

- Home is the Play destination. Desktop has a compact brand + Play / Replays / Tools header, with account/language as utilities. Phone uses the same three destinations in a bottom navigation bar outside an active match. Avoid duplicate Home and Play destinations.
- Expose Find a game and Create a room immediately. Put the current ruleset beside these choices. Advanced settings open on demand.
- Join an invitation uses a pasted link to an existing room. This is a proposed convenience input, not an assertion that a new room-code API exists. Parse approved local room routes and reject malformed/foreign destinations without navigating to them. Direct invitation links continue to work.
- An existing active match produces a prominent Rejoin action only when verified by current state. Do not invent a recent-room list from stale browser storage.
- Preserve `/play` as a working entry/deep link even if Home shares its presentation; decide canonical routing during implementation.

### Waiting room

Desktop: occupancy heading and Copy invitation at the top; seat list or four-seat arrangement in the main area; concise rules summary beside it; start eligibility explanation and primary action below. Phone: same information in one column, four full-width seat rows, and a reachable action footer that does not cover content.

Source correction: `PrivateRoom.tsx` allows the host to start when all four seats are human/bot. It does not expose a pre-game ready protocol. Show **joined / empty / bot**, label the host and the current user, and explain that guests wait for the host. Reserve **Ready** for the existing between-round flow. The earlier suggestion of pre-game readiness was not grounded in this source.

Host with empty seats: “Invite 2 players or add bots”; start remains unavailable. Host with four occupied seats: Start game. Guest: Waiting for host to start. Bot changes and rule changes retain existing host-only controls. Show copy success and failure beside Copy invitation. Back navigation must not imply that room membership ended; actual leave/rejoin semantics must be verified before defining a Leave room action.

### Confirmed source targets

- `Home.tsx` presents four destination links; `ClubShell.tsx` supplies brand/home, language and profile, but not direct Replays/Tools navigation. Hypothesis: explicit shared destinations reduce backtracking. Validate with actual tasks.
- `CreateRoom.tsx` starts creation when authenticated and redirects to the room; this is already an action flow, not a room-settings form. Improve its loading/error continuity rather than adding a redundant creation confirmation.
- `PrivateRoom.tsx` already includes copy feedback, host-only settings, occupancy-based start, retry and rejoin states. Improve hierarchy and discoverability rather than describing those capabilities as missing.

### Primary task script

1. From home, find a game; cancel searching and remain oriented.
2. Create a private room, including an anonymous-user login return.
3. Copy the invitation and explain how a friend joins.
4. Open a valid invitation; recover from invalid/unavailable room state without creating a replacement room.
5. As host, identify empty seats, add a bot if wanted, and start when eligible. As guest, identify who can start and why the game is waiting.
6. From Play, find a replay, visit tools, and return; test browser Back as well as app navigation.
7. Return to an active match after leaving the screen or refreshing.

Run this script on both phone and desktop. A critical failure on either device blocks selection. Desired outcome: fewer wrong destinations/backtracks and clearer next actions than baseline, without losing any supported state or inventing a new backend contract.

## Prototype and selection protocol

1. Complete the baseline screenshot audit when a browser is available. Use the confirmed priorities: home, rooms and navigation; desktop and phone equally.
2. Prototype A as the working hypothesis, retaining B and C as alternatives. Use isolated fixture data, existing tile SVG assets, and no real matchmaking requests. Focus on home → authentication return → create/join room → host start/guest wait → game entry. Also demonstrate navigation to Replays and Tools, plus back navigation and rejoin. Detailed in-game and review changes are follow-up scope. Label the prototype clearly.
3. Make controls demonstrate quick-match searching/cancel, creation loading/retry, invitation validation, copy confirmation, host seat filling, guest waiting and match entry. Mock server state explicitly; do not imply local UI can authoritatively start a real game. Rejoining restores the existing match, not a new room.
4. Review the prototype screenshots at the same baseline sizes/locales. Do not rely only on an attractive large desktop screenshot. Inspect a 14-tile hand, three melds, flower rails, six-column discards and long scoring details.
5. Have the user and, if available, 3–5 players perform identical tasks in baseline and prototype. Counterbalance order where possible. Separate visual preference from task success; a small sample is directional evidence.

### Proposed acceptance checks

- Correctly identify the active seat, latest discard, wild tile and available response without prompting.
- Start matchmaking, create a room and return from cancelled login without losing intent or trapping navigation.
- Correctly choose a chii combination and cancel it without accidentally discarding.
- Distinguish play from next-step in replay on first use; keyboard users receive understandable control names and visible focus.
- Identify who won, why and the user's payout; reach Ready and Exit with long result content.
- No hand/discard/action overlap or clipping at agreed device sizes. Record actual dimensions. Aim for 44 CSS-pixel button targets; do not blindly impose that width on all 14 portrait hand tiles when it cannot fit. Choose orientation or an independently tested selection interaction.
- Primary text and interactive states pass a documented contrast check, reduced-motion behavior is reviewed, and meaning does not depend on color alone.
- Candidate reduces observed hesitation/errors on the user's priority task and introduces no critical task failures. Record the observations, not a fabricated percentage improvement.

Weight the comparison according to confirmed priorities: entry/navigation clarity 35%, room/invitation flow 30%, recovery/rejoin 15%, visual hierarchy 10%, cross-page consistency 10%. Score every category separately on desktop and phone, then average the two with equal weight. No scores assigned yet. A task-blocking issue disqualifies a candidate until repaired even if its weighted score is high.

## Implementation sequence after design validation

1. Theme tokens/primitives and the entry/room shell, preserving existing auth/session flow.
2. Room layout and host/guest state presentation, invitation entry and recovery paths. Preserve server authority, room membership and authentication return semantics.
3. Consistent shell navigation across replay and tools; touch table/result layouts only where needed to complete the entry and return journeys. Defer broader board/replay redesign to evidence from the audit.
4. Bilingual responsive verification, appropriate interaction/regression tests, and repository-required CI gates before calling implementation complete. Update affected directory CLAUDE.md files with real architectural changes.

Do not rewrite game state, bridge APIs, auth, or scoring to achieve a cosmetic layout change. If prototype evidence calls for a behavior change, state it explicitly in the implementation spec.

## Completion status

Done: targeted source audit, initial primary-source research, three schematic direction boards, provisional recommendation, baseline capture matrix and prototype/selection brief. SVG rendered through Quick Look and inspected; a status label overlap was corrected. The final sheet uses a square canvas to allow a full-width Quick Look preview. The SVG is the canonical artifact.

Pending: rendered current-app audit and annotated screenshots; full visual reference comparison; interactive prototype; player feedback and final selection. Browser connection is the current blocker to rendered-app inspection. This draft does not represent completion of the entire discovery sprint or approval to implement a selected design.

## 2026-09-15 continuation — clickable Direct play prototype

User accepted continuing with Direct play. Added a standalone local Vite entry at `http://localhost:3000/ui-prototype.html`. It does not change production routing, styles, auth, room state or matchmaking. Source lives in `web/src/features/dev/DirectPlayPrototype.tsx` and `directPlayPrototype.css`; `web/ui-prototype.html` is deliberately outside the default production build entry.

Implemented sample flows: home with direct matchmaking/room creation and invitation input; mock sign-in continuation/cancel; cancelable search; host room with bot filling and occupancy-gated start; guest room with host controls disabled; copyable guest-preview links; in-memory return to room/match; Play/Replays/Tools navigation; Chinese/English; 393px phone preview. Replays is an explicit empty fixture, tools open existing pages, and match entry ends the navigation demo. Refresh resets sample state. Actual creation/retry/reconnection/server persistence remain outside this prototype.

Browser status: dedicated browser provider returned no available browsers. Native Computer Use connected successfully to Vivaldi. Inspected the existing home and play screens, then rendered and exercised the prototype there. This supersedes the earlier blanket browser-inspection blocker; browser-provider automation remains unavailable.

Observed desktop baseline: home is a centered four-destination menu; Play opens a second screen with Find Match and Create Private Table. Prototype combines those actions at entry and keeps destination navigation visible. No real match or room was created.

Manual checks completed: desktop mock login → host room → fill three bots → enabled Start → match-entry endpoint; search → cancel → home; Chinese 393px container layout; malformed external invitation rejection; valid sample invitation → mock login → guest view with disabled start/rules and no seat mutation controls; copy invitation success feedback. Copy opens only a prototype invitation, not a real room. Following the copied link in a fresh tab was not completed. Physical phone/device emulation and the full viewport matrix remain unverified.

Visual iteration: reduced decoration and padding on phone so room creation is visible sooner; moved Copy invitation above the seat list; added scroll/focus reset on page changes. Narrow preview was inspected after layout changes. The 393px container preview exercises responsive CSS but does not reproduce a phone browser's keyboard or safe-area behavior.

Validation: TypeScript passed after final component changes. Repository gates passed: gofmt produced no paths, go vet and go test passed, and all 222 frontend tests across 35 files passed. Existing tests are regression coverage; they do not automate the new prototype flows. No production build/deployment or player usability study was performed.

Next design decision: review the clickable home/room experience on both screen sizes and collect user feedback before adapting it to production auth and room APIs. The earlier concept board and research remain supporting drafts, not validated usability results.

## 2026-09-18 — real calculator and shanten restyle

Both `/tools/calc` and `/tools/shanten` now use the shared `ToolsShell` and scoped Direct play light theme. Changes cover navigation, typography, surfaces, buttons, fields, tray selection, badges, result panels and narrow-screen layout. Removed decorative page headers and duplicate language controls; accessible page titles remain. Existing calculation state, API requests, tile primitives and deep-link handling are unchanged. During development, Play/Replays links return to the prototype; production uses the normal routes.

Verified calculator rendering and tool-tab navigation in Vivaldi, plus shanten typed-hand application (13 selected tiles and remaining-copy counts). The local analysis endpoint returned Request failed, so successful scoring/analysis results were not visually exercised. No physical-phone verification was completed. TypeScript, all 222 frontend tests, Go formatting/vet/tests and the production build passed. Restored the generated tracked `web/dist/index.html` after build validation to keep the diff source-only.

## 2026-09-26 — real table and settlement refresh

Added `web/src/table/direct-table.css` as the final presentation layer for shared live/replay tables, tile faces/backs, selection/call states, settlement panels, and game dialogs/final standings. Retained geometry, flight transforms, rule logic, and result action wiring. User rejected the initial light playing field; revised it to muted slate blue (#476274) with darker surrounding shell (#293b49), softened tile faces and payout panels.

Built-in browser checks: desktop table, active-turn controls, multi-chii eligible state, match-end dialog; long payout fixtures at 375x667 portrait and 667x375 rotated-shell dimensions, including readiness labels. Ready/Exit remain visible. These are real shared components with fixture data, not a live match. Physical touch/portrait rotation and network-driven animation remain unverified; viewport overrides did not reliably target the nonselected table tab, so no new full phone-table verification is claimed. Existing geometry/flight tests pass.

## 2026-09-27 — table clearance and rotation audit

Fixed three observed layout defects: long bottom discard pools intersected the local hand on short stages; the wild plaque intersected the left concealed rail; four-kan opponent rails clipped at the edge. Discards now have independent size/column tokens and share an upward-shifted center with the HUD. Opponent exposed tiles have a separate width budget, preserving concealed/local hand sizing. Compact exposed rails were reduced further after a new regression exposed 19 design pixels of overflow inside the bundle even though viewport clipping had disappeared.

Added synthetic crowded (30 discards per seat) and meld-heavy (four direct kans/eight flowers per seat) fixtures, clean toolbar mode and explicit portrait-shell rotation. Browser checks used only the Codex built-in browser. Measured cross-zone tile intersections and viewport clipping at 568x320, 667x375, 844x390, 800x600, 1024x768, 1280x720, 1920x1080, 2560x1080 and forced-rotated 320x568, 375x667, 390x844, 430x932. Both fixtures passed those checks; the final compact meld-size adjustment was rechecked at all four portrait sizes. Also checked a selected/lifted self tile and the called-hand fixture. Seat rotations remain 0/-90/180/+90; compact side pivots intentionally share the higher baseline to protect the local hand.

Validation: TypeScript, 231 tests across 36 files, Go formatting/vet/tests and diff whitespace checks passed. Nine new geometry tests cover long discard clearance and four-kan width budgets. Screenshots: /tmp/fh-ui-review/crowded-phone-final.png and /tmp/fh-ui-review/kans-phone-final.png. These checks use synthetic shared-component fixtures and viewport simulation; physical-device touch/safe areas and live network animation were not verified. Changes remain uncommitted in the isolated direct-play worktree.

### Six-column correction

User requires no more than six discards per row at every size. Replaced the compact eight-column layout with six columns and reduced compact discard height to 26 design pixels so five rows still clear the lifted self hand. The clearance tests now enforce six columns. Built-in browser checks at 667x375, 568x320 and forced-rotated 375x667 found no cross-zone tile overlaps or clipping. TypeScript and all 231 frontend tests passed.

### Center wild indicator

Moved the wild indicator from the corner into CenterHud, with a localized label, larger tile face and amber frame. Retained optional Chongci metadata in the corner. Compact score bands now place wind and score inline, with corrected side anchors to avoid intersecting the indicator or round/wall chips. Built-in browser DOM checks found no center-content intersections at 568x320, 667x375, 844x390, 1024x768, 1280x720 and forced-rotated 375x667. Six-column discard geometry is unchanged. TypeScript, all 231 frontend tests and Go gates passed. Screenshot: /tmp/fh-ui-review/center-wild-final.png.

## 2026-09-28 — moderate phone tile enlargement

User rejected the larger-tile/scrollable-history tradeoff. Final compact layout keeps every discard visible, six per row, and preserves single-row meld formation order. Discards increased from 20x26 to 24x32 design pixels; opponent exposed tiles from 19x26 to 24x32; local exposed tiles to 28x38. Reclaimed padding and group gaps rather than adding scrolling. Widened/raised side bundles and shifted the top bundle left; flower-only rails sit above the hand, with the local rail inset from the right opponent. Added an eight-flower/full-hand fixture.

## 2026-09-29 — shared proportional table preview

User chose one phone/desktop proportion set with elastic peripheral space and requested large self tiles inset from the window. Implemented preview-only `layout=unified` on TableSample: fixed 720 design height, shared compact-derived geometry, aspect-based stage width, self tiles 82x116, bottom inset 28, hand span 1200. At 667x375 the measured tiles are 42.7x60.4 CSS px, with left inset 21 and bottom inset 14.6; at 1280x720, tiles are 82x116 with 40/28 insets. At 2560x1080, tiles are 123x174 with 380/42 insets. New styles are scoped to the preview attribute; live and replay remain unchanged pending visual review.

Built-in browser checks: crowded 30-discard, four-kan and eight-flower fixtures at all three sizes, plus phone lifted tile and forced portrait rotation. No measured cross-zone tile intersections or viewport clipping. Screenshots: /tmp/fh-ui-review/unified-phone.png, unified-desktop.png, unified-wide.png. Physical phone safe-area behavior and live network animation remain unverified.

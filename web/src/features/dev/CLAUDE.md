# web/src/features/dev/

> Dev-only pages that render real components against mock data, reached by URL only. Iterate on
> table and settlement layout here, not by deploying a live match.

## Key files

- **TableSample.tsx** (`/tools/table-sample`) — the real `TableBoard` with deterministic fixtures.
  - Fixtures: idle, active turn (clickable hand), called hand, interrupt, multi-chii, callable
    discard, round result, match end, exit dialog, `wild-hand`, and the stress fixtures
    `crowded` (30 discards per seat), `meld-heavy` (four direct kans and eight flowers per seat),
    `flower-heavy`. Stress fixtures test layout extremes, not legal game states.
  - Query: `fixture=<name>`, `clean=1` (hide the toolbar), `rotate=1` (force the portrait-shell
    transform), `review=1` (synthetic advice/risk annotations — layout fixtures, never real AI
    output), `layout=unified` (preview-only shared phone/desktop geometry from
    `tableSampleUnified.css`; live and replay routes do not use it yet).
- **RoundResultDemo.tsx** (`/tools/round-result`) — the shared settlement sheet with a control
  panel (scenario, viewport preset, readiness) and a resizable iframe that loads the same route
  with `?embed=1`. The iframe is load-bearing: the overlay must size from its own container to
  reproduce phone layouts (375×667 and the default 667×375 rotated presets).
- **roundResultScenarios.ts** — mock `RoundResultView` data.
- **DirectPlayPrototype.tsx**, **directPlayPrototype.css** — the standalone `/ui-prototype.html`
  navigation prototype: no auth, sockets, or backend; in-memory state that resets on refresh;
  393px phone preview.

## Unified layout preview (`layout=unified`)

One 720-high stage and one proportion set; width grows with the window's aspect ratio. Self
tiles stay about 43×60 at 667×375. Side pivots sit at equal and opposite 28-unit offsets from the
HUD center, with a constant 60-unit local inset; concealed-hand anchors stay fixed as melds
form. Exposed tiles: opponents 28×38, self 34×46, flowers 32×42; side seats with four-wide kans
shrink to 26×34 (three melds) or 24×32 (four) to keep one meld row. `tableSampleUnified.test.ts`
covers scaling, hand size, edge clearance, and lifted-hand separation.

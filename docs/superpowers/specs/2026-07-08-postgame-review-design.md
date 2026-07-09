# Post-Game Review ("复盘") Design

**Date:** 2026-07-08
**Status:** Approved
**Inspiration:** mjai.ekyu.moe (Mortal reviewer) + killerducky/killer_mortal_gui (integrated review UI)

## Goal

Help human players on the Fenghua platform find out which of their decisions were
suboptimal, reviewed by the production RL champion
(`chongci_selfplay_deep4_phaseb1_iter275_39ch`, 39ch PolicyValueNet, residual_blocks=4,
eval +0.4722 paired placement vs the IQL anchor; `ai/checkpoints/best-checkpoints.json`).

A match review replays the stored paipu deterministically and, at **every decision
point of every seat**, records the champion's full masked policy distribution (plus
its value estimate) over the legal actions, alongside the action the player actually
took. Mistake flagging is a **display-layer** concern (tiered thresholds on the
probability gap), so a generated report stays valid as UI thresholds evolve.

## Decisions Settled During Brainstorm

| Question | Decision |
|---|---|
| Review metric | **Policy-probability only** in v1. EV via `EvaluateBranches` rollouts is an explicit non-goal (heuristic-completion noise; slow). |
| Orchestration | **Go drives, Python serves.** Go replays the paipu and encodes observations; a batch HTTP call to the policy server returns distributions. |
| Delivery | **On-demand backend API** (`POST /api/v1/matches/:id/review`) with cached reports; 503 when no policy server is configured. |
| UI surface | **Integrated replay-viewer overlay**, KillerDucky-style: analysis panel at every decision, not just flagged ones. |
| Flagging | **Tiered severity** on probability gap, neutral wording, tunable in UI. |
| Game modes | **No mode branching**: classic-mode rounds are encoded as *Chongci final hand with equal scores*, so the champion always sees its native context. |
| Seats | **All four seats** reviewed in one pass; UI defaults to the requesting player's seat with a seat switcher. |
| Hidden information | Reviewer uses the **39ch visible observation only** (seat-relative, no hidden-opponent leakage). Never the oracle/51ch encoding. |

## Architecture & Data Flow

```
storage.Match.PaipuJSON
        │
        ▼
internal/review (Go)
  ├─ paipu replay driver: engine.Game + SetWallSeed per round,
  │    feed recorded actions, capture each decision point
  │    (EncodeObservation 39ch + actionMask + chosen action id)
  ├─ report builder: batch obs → policy server → assemble ReviewReport
        │  HTTP: POST {POLICY_SERVER_URL}/evaluate  (batched)
        ▼
ai serve_policy.py  /evaluate endpoint (CheckpointPolicy forward pass,
                     masked softmax + value, no sampling, checkpoint-stamped)
        │
        ▼
ReviewReport JSON → match_reviews table (Postgres)
        │
        ▼
web replay viewer overlay (/replay/:matchId review mode)
```

## Component 1: Go review engine — `internal/review`

New package. Two responsibilities, separately testable.

### 1a. Paipu replay driver

Reconstructs the match decision-by-decision from `engine.Paipu`:

- Per round: seed a fresh/continuing `engine.Game` with the round's `WallSeed`
  (`Game.SetWallSeed`), verify the dealt hands match `Deals` (fail fast on
  divergence — a divergent replay must abort with a clear error, never produce a
  silently wrong review), then feed the recorded action stream through the engine.
- A **decision point** is any state where a seat has more than one legal action per
  the `internal/rl` action mask (204-action catalog). At each one, capture:
  - seat, round index, action index into the paipu stream (for viewer sync),
  - `rl.EncodeObservation` output (39ch planes + 58 scalars),
  - the legal-action mask,
  - the action actually taken, encoded through the same catalog
    (`encodeAction`/`DecodeActionID` round-trip).
- **Implicit "pass" decisions count.** When a seat could have called
  (pon/kan/ron/chii) during an interrupt window and did not — i.e. the paipu is
  silent for that seat — that is a reviewable decision whose chosen action is
  "pass". The engine's interrupt-window state plus the action mask makes these
  windows explicit during replay.
- **Mode normalization:** for classic-mode matches, the Chongci context scalars
  (indices 42–57) are encoded as if the round were the *final hand of a Chongci
  match with all four scores equal*. Chongci matches encode their real context.
  No other mode branching anywhere in the pipeline.
- Reuses `internal/rl` (action catalog, mask, observation encoder) and
  `internal/engine`; must not fork rules or state-transition logic. Whether the
  driver wraps `rl.Env` or drives `engine.Game` directly is an implementation
  decision for the plan — the constraint is exact-replay fidelity including
  interrupt windows.

### 1b. Report builder

- Collects all decision points, batches observations, POSTs to the policy server,
  and assembles a `ReviewReport`:
  - **Header:** match id, ruleset, players, checkpoint id/step (from the server
    response), report schema version, generation timestamp.
  - **Per decision:** seat; round; paipu action index; legal actions each with
    champion probability; chosen action; champion value estimate.
    Probabilities are the full masked softmax — the UI derives top-N and gaps.
  - **Per-seat summary:** decision count, mean probability assigned to chosen
    actions, and the 5 largest probability gaps (pointers to decisions).
- Policy server unavailable or checkpoint mismatch → typed error, no partial
  report persisted.

## Component 2: Policy server — `ai/src/fh_mahjong_ai/serving.py` + `scripts/serve_policy.py`

Add a batch **evaluate** endpoint:

- Request: array of `{obs, mask}` rows (same wire format the existing serving path
  uses for observations).
- Response: per row, the full masked softmax distribution over the 204 actions and
  the value-head output; plus checkpoint id/step and obs-channel count for
  stamping. Deterministic — this is `CheckpointPolicy`'s existing forward pass
  *without* the temperature/top-k sampling step.
- Server-side chunking with a max batch size (default 256 rows per forward pass)
  so a full match (typically a few hundred decisions) reviews in one HTTP round
  trip regardless of size.

## Component 3: Backend API + storage

- `POST /api/v1/matches/:id/review` — idempotent build-or-return-cached. Loads
  `Match.PaipuJSON`, runs `internal/review` against `POLICY_SERVER_URL`
  (env/config). Unset or unreachable → `503 {"error": "reviewer unavailable"}`.
  Auth: same visibility rule as fetching the match/replay itself.
- `GET /api/v1/matches/:id/review` — returns the cached report (latest by
  creation time), 404 if none.
- New table `match_reviews` (GORM model in `internal/storage`):
  `id, match_id (indexed), checkpoint_id, report TEXT (JSON), created_at` —
  TEXT rather than JSONB for consistency with `Match.PaipuJSON` and the
  in-memory sqlite test setup.
  A separate table — not a Match column — so a future champion can re-review a
  match without destroying the old report. `(match_id, checkpoint_id)` unique:
  re-POST with the same champion returns the cached row.

## Component 4: Frontend — replay viewer review mode

Extend `web/src/features/replay` (Replay.tsx / replayEngine.ts / replayTypes.ts):

- **Always-on analysis panel** when a review exists for the match: at every
  decision, a horizontal bar chart of the champion's action preferences (tile
  glyphs + percentages, top-N legal actions), with the player's actual choice
  highlighted and severity-colored. Decisions sync to playback via the paipu
  action index recorded per decision.
- **Tiered severity** computed in the frontend from the report's raw
  distributions. Gap = (champion top-action prob) − (prob assigned to chosen
  action). Defaults: `<0.30` none; `0.30–0.60` "disagreement" (yellow); `≥0.60`
  "likely mistake" (red); never flagged if the chosen action is within the
  champion's top-3 with ≥5% probability. Thresholds are UI-tunable constants.
- **Neutral wording:** "champion prefers X (72%)" — never "wrong". The champion
  is strong, not an oracle. A persistent small note states the champion optimizes
  placement (Chongci objective).
- **Mistake navigation:** per-seat summary strip (counts by severity, biggest
  gaps) with jump-to-decision; seat switcher defaulting to the requesting
  player's seat.
- **Value timeline:** the champion's value estimate per decision plotted across
  the match (mjai-reviewer-style fortune graph) — free from the same forward pass.
- Bilingual zh/en like `/calc`. A "request review" button on the replay page
  drives the POST endpoint and shows build progress / the 503 unavailable state.

## Error Handling

- **Replay divergence** (dealt hands ≠ `Deals`, illegal recorded action, mask
  says the chosen action was illegal): abort with a descriptive error naming
  round + action index. Never emit a partial or corrected report.
- **Old paipu versions** missing required fields: explicit "unreviewable" error.
- **Policy server**: connection/shape/checkpoint errors are surfaced as 502/503
  with detail; nothing cached.

## Testing

- **Go (`internal/review`)**: golden-paipu fixtures → deterministic decision-point
  extraction (counts, masks, chosen-action encodings, pass-window detection);
  hidden-information test in the spirit of `internal/rl/env_test.go`; classic→
  Chongci-final-hand scalar encoding test; report builder against a stub policy
  server (httptest); divergence-abort tests. `go test ./...` green.
- **Python**: evaluate-endpoint tests — mask correctness (zero prob on illegal
  actions), batch shapes, determinism, checkpoint stamping.
  `uv run --project ai pytest`.
- **Frontend**: vitest for gap/severity computation, top-3 exemption, report
  parsing, decision↔playback index sync.

## Non-Goals (v1)

- EV rollouts (`EvaluateBranches` counterfactual tier) — future enhancement,
  slots in as an optional per-decision enrichment of the same report schema.
- ONNX / pure-Go inference (no-Python review).
- Automatic review on match end (reviews are on-demand).
- Reviewing legacy paipu that predate required fields.
- Bot-play generation (that is the held sibling design: standalone
  checkpoint→paipu generator, see memory `project_paipu_observability_plan`).
  The two tools intentionally share paipu format, serving stack, and viewer.

## Workflow Notes (for the implementation plan)

- Implementation in a later session via subagent-driven development;
  `/adversarial-review-loop` until approve **before** opening the PR; then wait
  for GitHub Codex PR review approval; merge with `gh pr merge N --merge`.
- Update `AGENTS.md` in every touched directory (`internal/review` gets a new one).
- Proto is untouched by this design (report is plain JSON, not protobuf).

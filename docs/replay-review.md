# Replay and AI Review

The replay viewer (`/replay/:matchId`, `/replay/import/:importId`) plays back a paipu on the
shared table and, when a policy server is configured, shows the AI's view of every decision.
Backend: `internal/review`, `internal/api/review.go`, `replay_study.go`, `replay_imports.go`.
Frontend: `web/src/features/replay/`.

## Sources

| Source | Route | Access |
|---|---|---|
| Recorded match | `/replay/:matchId` | Public read; the account's completed matches list at `/replay` |
| Imported paipu | `/replay/import/:importId` | Private to the uploading account |

Imports accept native Fenghua paipu JSON (v1 or v2, ≤ 10 MiB). They are immutable, deduplicated
per account by content hash, validated before any model work, and stored apart from live
matches, match history, and training data. Uploaded player ids never grant ownership.

## Pipeline

```
paipu ─► ExtractDecisions ─► decisions + observations ─► /evaluate ─► policy report (v1)
                                    │
                                    └─► BuildStudy ─► per-action evaluation + risk ─► study report (v2)
```

1. **Reconstruction.** `ExtractDecisions` replays each round in a fresh `engine.Game` from the
   recorded wall seed, dealer, and deals, feeding exactly the recorded actions. Every point where
   a seat had more than one legal option becomes a decision with the observation the reviewed
   checkpoint would have seen (public information only, with Chongci context restored from the
   paipu). Any mismatch with the engine — a bad seed, an illegal action, a v2 trace row that
   disagrees with the reconstructed legal set — aborts the review. There is no partial report.
2. **Policy.** Observations go to the policy server's `/evaluate` in chunks of 256. Each decision
   gets the probability of every legal action. A checkpoint swap mid-review is an error.
3. **Action evaluation.** For every legal action, `BuildStudy` plays the action on 32 paired
   worlds (opponent hands and wall re-dealt from what the player could not see), continues with
   the reviewed checkpoint to the end of the round, and reports the mean net payout and its
   standard error in Fenghua points. Seed 20261004, 512 rollout decisions per world.
4. **Risk.** For candidate discards, 128 sampled worlds estimate each opponent's legal-ron
   frequency (with the 4-point minimum, wild and Independence waits) and a joint any-opponent
   frequency, plus pre-draw tsumo chances for the player. Sampling is uniform over unseen tiles,
   so these are model-conditional estimates, not calibrated probabilities.

Study builds run as background jobs: 30-minute budget, renewable lease, durable partial results,
cancel and resume. They share two build slots, a four-request queue, and a six-per-minute
per-account limit with the plain review, so review load cannot starve live `/act` traffic.

## What the viewer shows

- **AI recommendation** — the policy's probability for each legal action, shown as bars over the
  hand tiles and rows for calls. It is the model's preference among legal operations, not the
  probability that the move is correct.
- **Evaluation** — the per-action mean payout from step 3, with its standard error.
- **Decision provenance** — `recorded` (from the v2 trace or the action stream), `inferred`
  (reconstructed, e.g. a v1 pass), or `unknown`. A single-option decision is a forced operation.
  Only recorded, non-forced decisions count toward the statistics below.
- **Agreement** — share of counted decisions where the chosen action is the AI's top action.
- **Rating** — for decisions where every action has an evaluation and the range is not flat,
  `r = (eval(actual) − min) / (max − min)`; rating = `100 · mean(r)²`. Model-specific, not a
  player skill rank; the included count is shown.
- **Risk log** — per-discard exposure with a cumulative proxy `1 − Π(1 − p)`, labelled a proxy
  because events are dependent.
- **Study mode** hides advice, the actual choice, and future results until revealed.
- **Anchors.** A decision is shown at the position just before the choice; responses to one
  discard share a position but keep separate decision ids. Bookmarks encode round, cursor, seat,
  and decision.

## Configuration and caching

- `POLICY_SERVER_URL` must point at a policy server, or build requests return 503.
  `POLICY_SERVER_TOKEN` must equal the server's `FH_MJ_EVALUATE_TOKEN`.
- The event window comes from `REVIEW_EVENT_WINDOW`, or `RL_AGENT_EVENT_WINDOW` when both
  point at the same service. The encoder and the client must use the same window.
- Reports are cached per (match, checkpoint sha); a new champion adds a row, a rollback serves
  the old row. Study builds are keyed by input, checkpoint sha, schema, event window, method, and
  config. `?force=1` rebuilds.

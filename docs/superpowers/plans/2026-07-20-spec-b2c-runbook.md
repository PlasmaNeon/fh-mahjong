# B2c Deployment Runbook (post-merge, operational)

Transcribes spec §6 (`docs/superpowers/specs/2026-07-20-spec-b2c-serving-design.md`)
with exact commands. This is the ONLY path from "iter_075 is gate-qualified"
to "iter_075 is the operational serving champion" — every step below is a
gate; stop and report on any failure rather than proceeding to the next step.

User-set operational gate (2026-07-20, "light" option): shadow >= 50 games,
canary >= 20 private-room matches (criteria per step, below).

Candidate: `chongci_b2b_eventgru_privcritic_iter075`
(`ai/checkpoints/best-checkpoints.json`'s `gate_qualified_research_champion`
entry) — checkpoint `/root/fh-mahjong-runs/b2b/ckpt/iter_075.pt`, sha256
`00f469b010d35056c0ec0555c43f5c30f56c8f2177a865296e8cef672649008e`,
`event_window=128`, `residual_blocks=4`, `privileged_critic=True`,
`aux_heads=True`. Rollback fallback: iter275
(`current_chongci_reward_trained_best`, unchanged today).

## 1. Deploy the NEW policy server image at window 0 (old champion, unchanged serving)

Ship the new loader/serving image (metadata-aware `infer_model_config`,
`/act` compact event fields, enriched `/healthz`) to Zeabur's `policy`
service, still pointing at iter275 — this MUST be byte-identical to
current production behavior (parity layer 1 covers window-0 states too).

```
uv run --project ai fh-mj-serving-parity \
  --checkpoint /root/fh-mahjong-runs/deploy/selfplay-deep4-student-iter275-39ch.pt \
  --event-history-window 0 \
  --episodes 50 --start-seed 970000 \
  --bridge-kind go --match-mode chongci \
  --endpoint https://<policy-service>.zeabur.app/act
```

Expect: `result: PASS`, 0 fallbacks, 0 mismatches. Any failure here is a
regression in the NEW server image itself (not iter_075) — stop and fix
before touching the champion pointer.

(`--bridge-kind go --match-mode chongci` is REQUIRED here — as of adversarial
round 10, Finding 1, `--endpoint` is a hard gate that refuses to run against
anything else, since a mock/classic bridge never exercises production-shaped
Chongci event streams: round transitions/resets, interrupts, tail
truncation. `--allow-non-production` exists only for local experimentation,
never for this gate.)

## 2-4 preamble: candidate runs on a SEPARATE service instance, never the live primary

**Steps 2, 3, and 4 all evaluate iter_075 through a candidate policy-service
instance that is distinct from the production primary.** The production
`policy` service (`RL_AGENT_POLICY_URL`) stays on iter275 at window 0,
untouched, until step 6's atomic switch. This is the fix for an earlier draft
of this runbook, which had steps 2-4 reload the PRODUCTION service in place to
iter_075 while the backend's `RL_AGENT_EVENT_WINDOW` stayed at its default 0.
That reload would have made the live `RL Agent` seat's own primary policy
start returning event_window=128 responses to a window-0-configured backend —
the contract-aware health/`/act` checker (`internal/bot/remote/health.go`,
`http_policy.go`'s `ValidateServer`) would then reject every response and
every live RL seat would silently fall back to the heuristic bot mid-match.
Worse, step 4's shadow gate would then be comparing iter_075 against
heuristic fallback traffic, not against the actual iter275 incumbent it needs
to be compared against — an invalid gate that would still report "pass".

**Local option (primary — the backend can always reach localhost or a second
service on the same host):** run a second `fh-mj-serve-policy` process on a
different port serving iter_075, e.g.:

```
uv run --project ai fh-mj-serve-policy \
  --manifest ai/checkpoints/best-checkpoints.json \
  --checkpoint /root/fh-mahjong-runs/b2b/ckpt/iter_075.pt \
  --port 8766 \
  --enable-logit-export
```

`--enable-logit-export` is REQUIRED on this candidate/parity instance (adversarial
round 12, Finding 1): step 2's `fh-mj-serving-parity --endpoint` hard gate always
requests `return_logits: true` to verify tight logit parity, not just argmax
agreement, and `serve_policy.py` refuses that field with an HTTP 400 unless the
server was launched with this flag (or `FH_MJ_ENABLE_LOGIT_EXPORT=1`). The
production `policy` service's launch command (`ai/Dockerfile.deploy`'s `CMD`)
deliberately does **not** set `--enable-logit-export` — the full masked logit
vector is a material model-extraction surface and must never be exposed on the
publicly deployed primary endpoint. This is exactly why the parity gate in step
2 must run against the **candidate** service (already the case as of step
2-4's preamble above, not the production primary).

This is the **candidate service** referenced in steps 2-4 below
(`http://127.0.0.1:8766`, or `https://<candidate>.zeabur.app` if deployed as
a second Zeabur service — e.g. `policy-candidate` — or reached via a local
tunnel to a staging instance). The production `policy` service keeps serving
iter275 on its usual port/URL throughout; nothing about its traffic changes
until step 6.

If an already-running candidate service needs to be swapped to iter_075
in-place instead of restarted, use the exact `/reload` request (against the
CANDIDATE service's URL only, never the production one):

```
curl -X POST http://127.0.0.1:8766/reload \
  -H 'Content-Type: application/json' \
  -d '{"checkpoint": "/root/fh-mahjong-runs/b2b/ckpt/iter_075.pt", "expected_event_window": 128}'
```

(`expected_event_window=128` makes the reload refuse to swap if the
checkpoint's own metadata disagrees, per `serve_policy.py`'s `reload()`
contract check — belt-and-suspenders against loading the wrong file.)

**Before proceeding to step 4 (shadowing), verify the candidate itself is
actually serving iter_075**, not a stale or misconfigured checkpoint:

```
curl -s http://127.0.0.1:8766/healthz | python3 -m json.tool
```

Confirm both:
- `checkpoint_sha256 == 00f469b010d35056c0ec0555c43f5c30f56c8f2177a865296e8cef672649008e`
  (the `gate_qualified_research_champion` entry's `checkpoint_sha256` in
  `ai/checkpoints/best-checkpoints.json` — re-read the live value from that
  file rather than trusting this copy if the manifest has moved on)
- `event_window == 128`

## 2. `fh-mj-serving-parity` hard gate — iter_075 against the candidate service

```
uv run --project ai fh-mj-serving-parity \
  --checkpoint /root/fh-mahjong-runs/b2b/ckpt/iter_075.pt \
  --event-history-window 128 \
  --episodes 200 --start-seed 971000 \
  --bridge-kind go --match-mode chongci \
  --endpoint http://127.0.0.1:8766/act
```

(Substitute the candidate service's URL if it's a second Zeabur service or
tunnel instead of a local port. `--bridge-kind go --match-mode chongci` is
REQUIRED — see the note on step 1 above; the seeded episodes' natural chongci
round transitions are exactly what makes this a real hard gate rather than a
single-round mock smoke test.)

Expect: `result: PASS`, `decisions checked` in the thousands, 0 fallbacks,
0 mismatches. This is the HARD GATE (spec §3, item 2) — real HTTP POSTs to
the actual `/act` endpoint of the candidate serving image (the same
loader/serving code the production image runs, just a separate process/
service so production traffic is never touched), not a mock. Any single
mismatch, illegal action, or HTTP error is an immediate stop.

## 3. Serving smoke

```
uv run --project ai fh-mj-serving-smoke \
  --checkpoint /root/fh-mahjong-runs/b2b/ckpt/iter_075.pt \
  --bridge-kind go --episodes 20 --start-seed 972000
```

Expect: all episodes complete, legal actions throughout, 0 fallbacks
(`report['decisions'] > 0`, no exceptions). `run_bridge_serving_smoke` drives
`CheckpointPolicy` **in-process** (no HTTP round-trip, no service involved at
all) against real bridge legality — it exercises the in-process serving stack
(observation encoding, event-history windowing, action decoding) end-to-end,
distinct from step 2's `--endpoint` mode, which is the only step that
actually POSTs to a running `/act` HTTP endpoint (the candidate's).

## 4. Shadow >= 50 games

Enable shadow mode on the live `RL Agent` seat: set on the PRODUCTION backend
(the primary stays iter275/window-0; only the shadow target changes)

```
RL_AGENT_SHADOW_POLICY_URL=http://127.0.0.1:8766/act
RL_AGENT_SHADOW_EVENT_WINDOW=128
```

pointing at the candidate service verified above (not a reload of the
production `policy` service), and restart the backend. `bot.ShadowPolicy`
sends the primary's (iter275's) live traffic to iter_075 on the candidate
service asynchronously (bounded FIFO, drop-on-backpressure, never blocks
play) and logs `{decision_index, primary_action, shadow_action, agree?,
shadow_latency_ms, shadow_error?}` per decision. Because the primary is
untouched, this is a true iter_075-vs-iter275 shadow comparison, not a
comparison against fallback traffic.

Exit criteria (ALL required, over >= 50 completed games):
- zero shadow-side errors/fallbacks (`shadow_error` empty on every logged
  decision; dropped-request counter is informational, not a failure — the
  shadow must never block play, but a drop should still be rare at
  production event volume)
- p95 shadow act latency < 200 ms
- disagreement rate recorded in the progress note (RECORDED, not judged —
  two different policies are expected to disagree; this is not a gate on
  the rate itself)

Unset `RL_AGENT_SHADOW_POLICY_URL` afterward to stop shadow traffic once
the outcome is recorded, unless proceeding straight to canary.

## 5. Canary >= 20 private-room matches

Point a private room's empty-seat `RL Agent` button directly at iter_075
(temporary `RL_AGENT_POLICY_URL` override on a canary deployment, or a
manifest-scoped `--checkpoint-id` override — do NOT flip the production
pointer yet) and play/observe >= 20 completed private-room matches with
iter_075 actually controlling play (not shadow).

The canary deployment's backend MUST also set `RL_AGENT_EVENT_WINDOW=128`
alongside `RL_AGENT_POLICY_URL` — iter_075 is an event model (window 128);
leaving the backend at its default `RL_AGENT_EVENT_WINDOW=0` while the
policy service serves iter_075 makes the health/contract checker (see
`internal/bot/remote/health.go`'s `HealthChecker`, `http_policy.go`'s
`HTTPPolicy.ValidateServer`) report the endpoint as an event_window mismatch
— the RL agent is then reported unavailable, or every `/act` 400s into the
heuristic fallback, defeating the canary. Verify with the `/healthz` response
(`event_window: 128, contract_version: 1`) and `HTTPPolicy.Stats().Fallbacks`
before counting canary matches.

Exit criteria (ALL required):
- zero fallbacks (`HTTPPolicy.Stats().Fallbacks == 0` across the canary
  matches — check via the room/API path used for post-game review, or the
  server's stats log line at `--stats-log-every`)
- no crashes or incidents

## 6. Atomic switch: manifest pointer + Zeabur deploy

ONE commit that does both of the following (never split across commits —
an inconsistent intermediate state is a rollback risk):

1. In `ai/checkpoints/best-checkpoints.json`, set
   `current_chongci_reward_trained_best` to the `gate_qualified_research_champion`
   entry's contents (checkpoint_path, sha256, model_config, evaluation,
   promotion_gate — carry the confirmation-gate record forward), retaining
   the previous entry as `previous_best_checkpoint_path` /
   `previous_best_id` per the existing manifest convention (see how the
   iter275 entry itself records its predecessor). Update `gate_qualified_research_champion.serving_status`
   from `blocked_on_b2c` to `deployed` (or remove the entry if the schema
   treats "current" and "gate-qualified-pending" as mutually exclusive —
   confirm against `checkpoint_manifest.py`'s schema before editing).
2. Update the Zeabur `policy` service's committed champion checkpoint
   (`Dockerfile.deploy`) to iter_075 and deploy:

   ```
   git commit -am "feat(ai): promote iter_075 to operational serving champion (B2c)"
   git push   # Zeabur auto-redeploys ALL services on push — expected, not a bug
   ```
3. Set the production backend's `RL_AGENT_EVENT_WINDOW=128` (was `0`) as
   part of this same switch — iter_075 is an event model, and the backend
   env var must match what the `policy` service now serves or the
   contract-aware health/`/act` gate (`internal/bot/remote/health.go`,
   `http_policy.go`'s `ValidateServer`) reports the endpoint unavailable /
   every `/act` 400s into the heuristic fallback. Restart the backend after
   setting it.

   Post-game review's own client (`internal/api/review.go`'s
   `reviewEventWindow`, talking to `POLICY_SERVER_URL`) is governed
   separately by `REVIEW_EVENT_WINDOW`, NOT `RL_AGENT_EVENT_WINDOW` directly
   — the two env vars can describe different servers (adversarial round 7,
   Finding 2). If `POLICY_SERVER_URL` is the same service as the resolved RL
   agent endpoint (the common case — one `policy` service serves both
   private-room RL and review), leaving `REVIEW_EVENT_WINDOW` unset is fine:
   it falls back to `RL_AGENT_EVENT_WINDOW` automatically when the two URLs
   match (or when `POLICY_SERVER_URL` is unset). If review points at a
   DIFFERENT server/checkpoint, set `REVIEW_EVENT_WINDOW` explicitly instead
   of relying on the fallback.

From this point iter_075 is the promotion anchor for all future candidates
(future gates compare against iter_075, not iter275).

## Rollback path (iter275)

If any post-switch signal regresses (elevated fallback rate, incident,
regression in live win-rate monitoring):

1. Revert the manifest-pointer commit from step 6 (`git revert <sha>`) —
   this restores `current_chongci_reward_trained_best` to iter275 in one
   commit, mirroring the atomic-switch discipline.
2. Redeploy the Zeabur `policy` service from the reverted `Dockerfile.deploy`
   (iter275 checkpoint is still committed in history — do not delete it).
3. Set the production backend's `RL_AGENT_EVENT_WINDOW` back to `0` —
   iter275 is a window-0 (event-free) checkpoint; leaving the backend at 128
   after rolling the `policy` service back to iter275 makes the same
   contract gate report the endpoint unavailable. Restart the backend after
   unsetting/resetting it.
4. Re-run step 2's `fh-mj-serving-parity --endpoint` hard gate against
   iter275 post-rollback to confirm the rollback itself is byte-identical
   to pre-B2c production behavior before declaring the incident closed.

## Recording outcomes

Record every stage's outcome (pass/fail, dates, report paths, disagreement
rate, fallback counts) in the B2c progress note before proceeding to the
next stage.

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
  --endpoint https://<policy-service>.zeabur.app/act
```

Expect: `result: PASS`, 0 fallbacks, 0 mismatches. Any failure here is a
regression in the NEW server image itself (not iter_075) — stop and fix
before touching the champion pointer.

## 2. `fh-mj-serving-parity` hard gate — iter_075 against the prod image

Point the same policy service (or a staging copy) at iter_075 via
`/reload` (or redeploy with `--checkpoint` overridden), THEN:

```
uv run --project ai fh-mj-serving-parity \
  --checkpoint /root/fh-mahjong-runs/b2b/ckpt/iter_075.pt \
  --event-history-window 128 \
  --episodes 200 --start-seed 971000 \
  --endpoint https://<policy-service>.zeabur.app/act
```

Expect: `result: PASS`, `decisions checked` in the thousands, 0 fallbacks,
0 mismatches. This is the HARD GATE (spec §3, item 2) — real HTTP POSTs to
the actual `/act` endpoint of the running production image, not a mock.
Any single mismatch, illegal action, or HTTP error is an immediate stop.

## 3. Serving smoke

```
uv run --project ai fh-mj-serving-smoke \
  --checkpoint /root/fh-mahjong-runs/b2b/ckpt/iter_075.pt \
  --bridge-kind go --episodes 20 --start-seed 972000
```

Expect: all episodes complete, legal actions throughout, 0 fallbacks
(`report['decisions'] > 0`, no exceptions). `run_bridge_serving_smoke` drives
`CheckpointPolicy` **in-process** (no HTTP round-trip) against real bridge
legality — it exercises the in-process serving stack (observation encoding,
event-history windowing, action decoding) end-to-end, distinct from step 2's
`--endpoint` mode, which is the only step that actually POSTs to the running
`/act` HTTP endpoint.

## 4. Shadow >= 50 games

Enable shadow mode on the live `RL Agent` seat: set on the backend

```
RL_AGENT_SHADOW_POLICY_URL=https://<policy-service-or-staging>.zeabur.app/act
RL_AGENT_SHADOW_EVENT_WINDOW=128
```

and restart the backend. `bot.ShadowPolicy` sends the primary's live traffic
to iter_075 asynchronously (bounded FIFO, drop-on-backpressure, never blocks
play) and logs `{decision_index, primary_action, shadow_action, agree?,
shadow_latency_ms, shadow_error?}` per decision.

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

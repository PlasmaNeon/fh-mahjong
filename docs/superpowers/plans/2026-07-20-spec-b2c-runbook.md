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

**Logit-export authentication (adversarial round 13, Finding 1):**
`serve_policy.py`'s `/act` no longer has an `--enable-logit-export` on/off
switch — a process-wide boolean would let ANY network caller harvest full
logit vectors the instant it was set. Instead, a `--logit-export-token TOKEN`
(or `FH_MJ_LOGIT_EXPORT_TOKEN` env var) must be configured, and every request
that sets `return_logits: true` must carry the SAME token in a
`logit_export_token` field (checked with `hmac.compare_digest`) or it gets
HTTP 400 with no logits in the body. Every command below that launches a
candidate/private serving instance for `fh-mj-serving-parity --endpoint`
uses the generated token below and passes the matching
`--logit-export-token` to the parity command too. **The production `policy`
service never sets this flag.**

**Reload authentication (adversarial round 14, Finding 1a/1b):**
`serve_policy.py`'s POST `/reload` is a remote policy-replacement primitive,
so it is disabled ENTIRELY unless the server is launched with
`--admin-token TOKEN` (or `FH_MJ_ADMIN_TOKEN`); every `/reload` request must
then carry the SAME token in an `Authorization: Bearer <token>` HEADER
(`hmac.compare_digest`, checked before the request body is read)
or it is refused with the previous policy left serving. The server also
rejects the checkpoint path outright unless it is a regular file under a
2 GiB cap, before reading a single byte, and honors an optional
`expected_sha256` field (verified before the new checkpoint is
deserialized). **Production instances should normally run WITHOUT
`--admin-token`/`FH_MJ_ADMIN_TOKEN` set at all (reload disabled) — only
configure it deliberately, for the duration of a maintenance window, on
the specific instance being reloaded.**

**Evaluate authentication (adversarial round 19):** `serve_policy.py`'s POST
`/evaluate` — the endpoint the Go post-game review pipeline
(`internal/review`) batch-scores decisions through — is disabled ENTIRELY
unless the server is launched with `--evaluate-token TOKEN` (or
`FH_MJ_EVALUATE_TOKEN`); every `/evaluate` request must then carry the SAME
token in an `Authorization: Bearer <token>` HEADER (`hmac.compare_digest`,
checked before the request body is read, same ordering discipline as
`/reload`) or it gets HTTP 403 with an actionable message, `evaluate_batch`
never invoked. This closes a gap where an unauthenticated `/evaluate`
returned dense per-action probability vectors for caller-controlled
observations — a model-extraction surface (logit differences are
recoverable from `log(p_i/p_j)`) and a compute-DoS path — that made the
`/act` logit-export gate above moot on any public deployment. **Unlike
`--logit-export-token`/`--admin-token`, this token is REQUIRED in
production, not just on candidate/maintenance instances** — the review
feature needs it configured on whichever policy server production's
`POLICY_SERVER_URL` names. The matching Go-side env var is
`POLICY_SERVER_TOKEN`, read in `internal/api/review.go` where the review
HTTP client is constructed; it must be set to the SAME value as the policy
server's `--evaluate-token`/`FH_MJ_EVALUATE_TOKEN` wherever `POLICY_SERVER_URL`
is set (candidate steps, shadow/canary, and step 6 promotion, below) or
review requests will get a 502 (the policy server's 403 surfaces through
`internal/review`'s existing "policy server evaluation failed" error path).

**Generate all three secrets once, before starting (adversarial round 14,
Finding 2; round 19):** never hard-code a literal token in a command, a
script, or anything committed to the repo. Generate all three once per
deployment window and reference the env vars for every command below that
needs them:

```
export FH_MJ_LOGIT_EXPORT_TOKEN="$(openssl rand -hex 32)"
export FH_MJ_ADMIN_TOKEN="$(openssl rand -hex 32)"
export FH_MJ_EVALUATE_TOKEN="$(openssl rand -hex 32)"
```

Treat all three as secrets for the lifetime of the deployment window (do not
log them, do not commit them, rotate by re-running the commands above for
the next window — `FH_MJ_EVALUATE_TOKEN`/`POLICY_SERVER_TOKEN` are the
exception: since they stay live in production past step 6, rotating them
requires a coordinated restart of both the policy server and the backend
with the new value, not just a fresh deployment-window `export`). Where
practical, keep the candidate/parity serving instances non-public (bind to
`127.0.0.1`, a local tunnel, or an internal-only Zeabur service) — token
auth is not a substitute for reducing public exposure of these endpoints.

## 1. Verify the NEW policy server image at window 0 (old champion, unchanged serving)

Ship the new loader/serving image (metadata-aware `infer_model_config`,
`/act` compact event fields, enriched `/healthz`) to Zeabur's `policy`
service, still pointing at iter275 — this MUST be byte-identical to
current production behavior (parity layer 1 covers window-0 states too).

**This step's hard gate does NOT run against the live production URL**
(adversarial round 13, Finding 2): the production endpoint never configures
`--logit-export-token`, and `fh-mj-serving-parity --endpoint` always requests
`return_logits: true` as part of its tight logit-tolerance check — every
request against the live URL would get an immediate HTTP 400, so the gate
could never pass there even when the new image is perfectly correct. Split
"is prod actually running this image+checkpoint" from "does this image+
checkpoint reproduce the reference exactly":

1a. Deploy the new server image to Zeabur, still pointing at iter275 (window
0), by the usual push/redeploy path.

1b. Confirm the LIVE prod deployment's identity via `/healthz` — this needs
no logits, so it works against the real public URL:

```
curl -s https://<policy-service>.zeabur.app/healthz | python3 -m json.tool
```

Confirm `checkpoint_sha256` matches the iter275 entry in
`ai/checkpoints/best-checkpoints.json` and `event_window == 0`.

1c. Run the window-0 parity HARD GATE against a **PRIVATE/local instance of
the same production image+checkpoint** (iter275, window 0) — on the operator
machine or a non-public staging service, launched with a throwaway
`--logit-export-token`, never against the public prod URL:

```
uv run --project ai fh-mj-serve-policy \
  --manifest ai/checkpoints/best-checkpoints.json \
  --checkpoint /root/fh-mahjong-runs/deploy/selfplay-deep4-student-iter275-39ch.pt \
  --port 8767 \
  --logit-export-token "$FH_MJ_LOGIT_EXPORT_TOKEN"
```

```
uv run --project ai fh-mj-serving-parity \
  --checkpoint /root/fh-mahjong-runs/deploy/selfplay-deep4-student-iter275-39ch.pt \
  --event-history-window 0 \
  --episodes 50 --start-seed 970000 \
  --bridge-kind go --match-mode chongci \
  --endpoint http://127.0.0.1:8767/act \
  --logit-export-token "$FH_MJ_LOGIT_EXPORT_TOKEN"
```

Expect: `result: PASS`, 0 fallbacks, 0 mismatches. Any failure here is a
regression in the NEW server image itself (not iter_075) — stop and fix
before touching the champion pointer. Kill the private instance afterward
(port 8767); it is throwaway and never receives real traffic.

(`--bridge-kind go --match-mode chongci` is REQUIRED here — as of adversarial
round 10, Finding 1, `--endpoint` is a hard gate that refuses to run against
anything else, since a mock/classic bridge never exercises production-shaped
Chongci event streams: round transitions/resets, interrupts, tail
truncation. `--allow-non-production` exists only for local experimentation,
never for this gate.)

Together, 1b (healthz identity check against the live URL) and 1c (parity
hard gate against a private instance of the same bits) are the complete
step-1 gate. A separate no-logit "action-only" mode against the live prod
URL was considered and deliberately NOT added: it would require a new
`serving_parity.py` CLI mode with weaker guarantees (argmax-only, no logit
tolerance) purely so it could run against production, duplicating a gate
1c already covers more strictly — not worth the extra surface for a step
that already has a solid two-part answer.

## 2-5 preamble: candidate runs on a SEPARATE service instance, never the live primary

**Steps 2 through 5 all evaluate iter_075 through a candidate policy-service
instance that is distinct from the production primary.** The production
`policy` service (`RL_AGENT_POLICY_URL`) stays on iter275 at window 0,
untouched, until step 6's cutover. This is the fix for an earlier draft
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

**This candidate service is not throwaway** (adversarial round 13, Finding
3): as of step 6 below, it IS the promotion target — the same running
process/service is what production traffic gets pointed at, blue/green
style, rather than being torn down and replaced. Keep that in mind when
choosing where to run it (a stable host/service, not a scratch machine you
plan to reclaim).

**Local option (primary — the backend can always reach localhost or a second
service on the same host):** run a second `fh-mj-serve-policy` process on a
different port serving iter_075, e.g.:

```
uv run --project ai fh-mj-serve-policy \
  --manifest ai/checkpoints/best-checkpoints.json \
  --checkpoint /root/fh-mahjong-runs/b2b/ckpt/iter_075.pt \
  --port 8766 \
  --logit-export-token "$FH_MJ_LOGIT_EXPORT_TOKEN" \
  --admin-token "$FH_MJ_ADMIN_TOKEN" \
  --evaluate-token "$FH_MJ_EVALUATE_TOKEN"
```

`--evaluate-token` enables POST `/evaluate` on this candidate instance
(adversarial round 19) so that post-game review can be exercised against
iter_075 candidate traffic ahead of step 6's promotion — set the backend's
`POLICY_SERVER_TOKEN` to the same value on any backend whose
`POLICY_SERVER_URL` is pointed at this candidate.

`--admin-token` is what makes the in-place `/reload` swap below possible at
all (adversarial round 14, Finding 1a) — without it this instance's
`/reload` is disabled and the candidate would need a restart instead.

`--logit-export-token` is REQUIRED on this candidate instance for step 2
(adversarial round 12, Finding 1; adversarial round 13, Finding 1): step 2's
`fh-mj-serving-parity --endpoint` hard gate always requests
`return_logits: true` to verify tight logit parity, not just argmax
agreement, and `serve_policy.py` refuses that field with an HTTP 400 unless
the request carries a token matching the server's configured
`--logit-export-token` (or `FH_MJ_LOGIT_EXPORT_TOKEN`). The production
`policy` service's launch command (`ai/Dockerfile.deploy`'s `CMD`)
deliberately does **not** set a logit-export token — the full masked logit
vector is a material model-extraction surface and must never be exposed on
the publicly deployed primary endpoint. This is exactly why the parity gate
in step 2 must run against the **candidate** service (already the case as of
this preamble, not the production primary).

This is the **candidate service** referenced in steps 2-5 below
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
  -H "Authorization: Bearer $FH_MJ_ADMIN_TOKEN" \
  -d "{\"checkpoint\": \"/root/fh-mahjong-runs/b2b/ckpt/iter_075.pt\", \"expected_event_window\": 128, \"expected_sha256\": \"00f469b010d35056c0ec0555c43f5c30f56c8f2177a865296e8cef672649008e\"}"
```

(the `Authorization: Bearer` header must match this instance's
`--admin-token`/`FH_MJ_ADMIN_TOKEN` or the request is refused with the
previous policy left serving (adversarial round 14, Finding 1a; header-based
auth since adversarial round 15, Finding 1) — a server started without
`--admin-token` refuses this request outright, no matter what is sent.
`expected_sha256` is the
`gate_qualified_research_champion` entry's checkpoint hash — the server
verifies it against the checkpoint's actual bytes before deserializing
anything, and rejects a mismatch (adversarial round 14, Finding 1b).
`expected_event_window=128` makes the reload refuse to swap if the
checkpoint's own metadata disagrees, per `serve_policy.py`'s `reload()`
contract check — belt-and-suspenders against loading the wrong file. Same as
before, `/reload` does not change a running server's `--logit-export-token`;
that is fixed at launch. Equivalently, `fh-mj-reload-policy --checkpoint
/root/fh-mahjong-runs/b2b/ckpt/iter_075.pt --expected-sha256
00f469b010d35056c0ec0555c43f5c30f56c8f2177a865296e8cef672649008e
--expected-event-window 128 --admin-token "$FH_MJ_ADMIN_TOKEN" --port 8766`
does the same thing through the CLI wrapper (`--expected-event-window` is
what makes this — or any cross-window swap — a deliberate, checked
promotion rather than being refused by the server's default "must match
the currently-serving policy's window" contract check).)

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
  --endpoint http://127.0.0.1:8766/act \
  --logit-export-token "$FH_MJ_LOGIT_EXPORT_TOKEN"
```

(Substitute the candidate service's URL if it's a second Zeabur service or
tunnel instead of a local port, and the actual token it was launched with.
`--bridge-kind go --match-mode chongci` is REQUIRED — see the note on step 1
above; the seeded episodes' natural chongci round transitions are exactly
what makes this a real hard gate rather than a single-round mock smoke test.)

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
iter_075 actually controlling play (not shadow). This continues to target the
SAME candidate service from steps 2-4 (it is not torn down between steps).

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

## 6. Atomic switch: blue/green backend cutover (no policy redeploy)

**Promotion is a backend env-var flip, not a policy-service redeploy or a
manifest edit** (adversarial round 13, Finding 3). The earlier draft of this
step promoted by editing the manifest pointer and redeploying
`Dockerfile.deploy`'s committed checkpoint AND separately changing the
backend's `RL_AGENT_EVENT_WINDOW` — two independent moving parts that could
land at different times, leaving a window where the policy image and the
backend's expected window disagree. Instead:

- The **candidate** `iter_075`/window-128 service already running from steps
  2-5 becomes the promotion target in place — it is not redeployed or
  recreated.
- The **production** `iter275`/window-0 `policy` service is left running,
  completely untouched, as the "blue" rollback target — do not redeploy it,
  do not edit its `Dockerfile.deploy`, do not touch the manifest yet.

**Before flipping traffic, harden the candidate service for production
exposure:** restart it WITHOUT `--logit-export-token` AND WITHOUT
`--admin-token`/`FH_MJ_ADMIN_TOKEN` (same checkpoint, same port/URL — just
drop both flags, since it is about to receive real user traffic and must
not expose logit export or an authenticated remote-reload primitive to end
users the way the candidate/parity steps needed them for). **`--evaluate-token`/
`FH_MJ_EVALUATE_TOKEN` is the one exception — KEEP it set on the restart**
(adversarial round 19): unlike logit export and reload, POST `/evaluate` is
required in production for the post-game review pipeline, so it stays
token-gated rather than being dropped like the other two. Do not drop it
"for consistency" with the hardening below.

**Dropping the CLI flags is not enough** (adversarial round 15, Finding 3):
if the shell that launches the service still has `FH_MJ_LOGIT_EXPORT_TOKEN`
and/or `FH_MJ_ADMIN_TOKEN` exported (e.g. left over from step 1's `export`
lines), `serve_policy.py`'s argparse defaults fall back to those env vars
and BOTH features stay enabled even with the flags gone — an environment
that merely "doesn't pass the flag" is not the same as an environment where
the feature is off. The restart command must explicitly unset both, not
just omit the flags — but must NOT unset `FH_MJ_EVALUATE_TOKEN`, which stays
exported so `/evaluate` remains enabled:

```bash
env -u FH_MJ_LOGIT_EXPORT_TOKEN -u FH_MJ_ADMIN_TOKEN \
  uv run --project ai fh-mj-serve-policy \
  --manifest ai/checkpoints/best-checkpoints.json \
  --checkpoint /root/fh-mahjong-runs/b2b/ckpt/iter_075.pt \
  --port 8766 \
  --evaluate-token "$FH_MJ_EVALUATE_TOKEN"
```

(`env -u NAME` unsets `NAME` for the child process only, regardless of
whether the parent shell has it exported — this is more reliable than
`unset FH_MJ_LOGIT_EXPORT_TOKEN; unset FH_MJ_ADMIN_TOKEN` in the same shell
session, which is easy to forget or to run in the wrong shell/session.)

**REQUIRED before cutover** — verify the restart actually turned both
features off, not just that the process came back up. A bare HTTP status
code is NOT enough here: an unauthenticated request against an
ENABLED-but-still-secret server (i.e. the flags leaked back in via
`FH_MJ_LOGIT_EXPORT_TOKEN`/`FH_MJ_ADMIN_TOKEN` still being exported —
exactly the failure mode this check exists to catch) returns the SAME
status code (400 / 403) as a genuinely disabled server. All four checks
below must pass; do not proceed to the `RL_AGENT_POLICY_URL` flip below
until they do:

```bash
# 1. /healthz identity check: same checkpoint, same event_window, as before
#    the restart (confirms this is still iter_075/window-128, not an
#    accidental redeploy of something else).
curl -s http://127.0.0.1:8766/healthz | python3 -m json.tool
# expect: "checkpoint_sha256": "00f469b010d35056c0ec0555c43f5c30f56c8f2177a865296e8cef672649008e",
#         "event_window": 128, "contract_version": 1

# 2. PRIMARY check — the server's own startup log lines (main() in
#    serve_policy.py prints these once, at launch, from the SAME
#    args.logit_export_token/args.admin_token that gate every request —
#    unlike a curl status code, this can't be confused with an
#    enabled-but-unauthenticated response):
#      "Logit export (return_logits): disabled"
#      "Reload (/reload): disabled"
#      "Evaluate (/evaluate): enabled(token)"
#    grep the restarted process's stdout/log for all three exact lines. If
#    either of the first two instead reads "ENABLED (...)", the flags/env
#    leaked back in — stop and re-check the launching shell's environment
#    (env | grep FH_MJ_) before proceeding. If the THIRD line instead reads
#    "disabled", `--evaluate-token`/`FH_MJ_EVALUATE_TOKEN` was dropped by
#    mistake — post-game review will 502 in production; restart with it set
#    before proceeding.

# 3. Secondary check — return_logits request, checking the RESPONSE BODY
#    (not just the status code): a disabled server's 400 body always
#    contains "logit export disabled on this server"; an ENABLED server
#    given no/wrong token instead returns a DIFFERENT 400 body containing
#    "logit export token missing or does not match" — status code alone
#    cannot tell these apart, the message can.
curl -s -X POST http://127.0.0.1:8766/act \
  -H 'Content-Type: application/json' \
  -d '{"return_logits": true}'
# expect body to contain: "logit export disabled on this server"
# if it instead contains "token missing or does not match", logit export
# is still ENABLED (leaked token) even though this also returns HTTP 400 —
# do not treat the status code alone as a pass.

# 4. Secondary check — /reload, checking the RESPONSE BODY: a disabled
#    server's 403 body always contains "is disabled on this server"; an
#    ENABLED server given no/wrong Authorization header instead returns a
#    DIFFERENT 403 body containing "missing or invalid 'Authorization:
#    Bearer <token>' header" — again, the status code alone cannot
#    distinguish these.
curl -s -X POST http://127.0.0.1:8766/reload \
  -H 'Content-Type: application/json' \
  -d '{"checkpoint_id": "current"}'
# expect body to contain: "is disabled on this server"
# if it instead contains "missing or invalid ... header", reload is still
# ENABLED (leaked token) even though this also returns HTTP 403 — do not
# treat the status code alone as a pass.
```

If check 2's log lines read "ENABLED", or check 3/4's response bodies
contain the "enabled-but-unauthenticated" message instead of the
"disabled on this server" message, the candidate service is STILL
exposing logit export or remote reload to production traffic (the
`FH_MJ_LOGIT_EXPORT_TOKEN`/`FH_MJ_ADMIN_TOKEN` env vars leaked back into
the restart) — stop and re-check the launching shell's environment
(`env | grep FH_MJ_`) before proceeding.

**PROMOTION = ONE backend revision** changing, together:
- `RL_AGENT_POLICY_URL` → the candidate service's `/act` URL
- `RL_AGENT_EVENT_WINDOW` → `128`
- `POLICY_SERVER_URL` (post-game review's client,
  `internal/api/review.go`'s `reviewEventWindow`) → the SAME candidate
  service's URL, if review should follow the new champion (the common case —
  one `policy` service serves both private-room RL and review). Leaving
  `REVIEW_EVENT_WINDOW` unset is then fine: it falls back to
  `RL_AGENT_EVENT_WINDOW` automatically once `POLICY_SERVER_URL` matches the
  resolved RL agent endpoint (adversarial round 7, Finding 2). If review
  should stay on a DIFFERENT server/checkpoint, leave `POLICY_SERVER_URL`
  alone and set `REVIEW_EVENT_WINDOW` explicitly instead.
- `POLICY_SERVER_TOKEN` → the SAME value as the candidate service's
  `--evaluate-token`/`FH_MJ_EVALUATE_TOKEN` (adversarial round 19) — required
  whenever `POLICY_SERVER_URL` is set or changed, since the candidate's
  `/evaluate` (kept token-gated through the hardening step above) refuses
  any request without a matching bearer token. Read where the review HTTP
  client is constructed in `internal/api/review.go`.

Deploy this single revision and restart the backend.

**In-flight rooms**: rooms are in-process state (no external session store),
so a backend restart ends every live match regardless of whether the
switch is atomic — blue/green does not change this. Schedule the cutover
in a quiet window; this is inherent to the current architecture, not
something to try to work around here.

**AFTER** the cutover is confirmed healthy (health checks pass, a spot-check
match plays correctly against the new primary), do the following as a
**bookkeeping commit** — it records history, it is no longer the switching
mechanism:

1. In `ai/checkpoints/best-checkpoints.json`, set
   `current_chongci_reward_trained_best` to the `gate_qualified_research_champion`
   entry's contents (checkpoint_path, sha256, model_config, evaluation,
   promotion_gate — carry the confirmation-gate record forward), retaining
   the previous entry as `previous_best_checkpoint_path` /
   `previous_best_id` per the existing manifest convention (see how the
   iter275 entry itself records its predecessor). Update
   `gate_qualified_research_champion.serving_status` from `blocked_on_b2c` to
   `deployed` (or remove the entry if the schema treats "current" and
   "gate-qualified-pending" as mutually exclusive — confirm against
   `checkpoint_manifest.py`'s schema before editing).
2. Optionally update the Zeabur `policy` service's committed champion
   checkpoint (`Dockerfile.deploy`) to iter_075 at a later, unhurried deploy
   — this only matters for what a FRESH deploy of the `policy` service
   defaults to; the currently-running candidate service (now receiving real
   traffic per the backend env vars above) already IS iter_075, so this is
   not time-pressured the way the env-var flip was. When it does land:

   ```
   git commit -am "feat(ai): promote iter_075 to operational serving champion (B2c)"
   git push   # Zeabur auto-redeploys ALL services on push — expected, not a bug
   ```

Keep all existing gate criteria from steps 4-5 intact (shadow >= 50, canary
>= 20, zero fallbacks, p95 latency) — nothing about the switch mechanism
changes what had to pass before reaching this step.

From this point iter_075 is the promotion anchor for all future candidates
(future gates compare against iter_075, not iter275).

## Rollback path (iter275)

Because iter275's `policy` service was NEVER taken down (it stayed live as
the "blue" target throughout steps 2-6), rollback is also a pure backend
env-var flip, not a policy-service redeploy:

1. Deploy ONE backend revision reverting `RL_AGENT_POLICY_URL`,
   `RL_AGENT_EVENT_WINDOW`, `POLICY_SERVER_URL`, `POLICY_SERVER_TOKEN`, and
   (if it was set) `REVIEW_EVENT_WINDOW` back to their pre-switch values
   (pointing at the still-running iter275 "blue" service) and restart the
   backend. No policy image redeploy is needed — iter275 was never stopped.
   If iter275's "blue" `policy` service never had `--evaluate-token`
   configured (it predates this gate), leave `POLICY_SERVER_TOKEN` unset
   post-rollback too — review will 502 against it either way until that
   service is likewise given an `--evaluate-token`/`FH_MJ_EVALUATE_TOKEN`.
2. As with the promotion switch, this restart ends any in-flight rooms
   (inherent to in-process room state, not specific to rollback) — schedule
   accordingly if the rollback itself isn't already an emergency.
3. If the bookkeeping commit (manifest pointer / `Dockerfile.deploy`) from
   step 6 had already landed, revert it (`git revert <sha>`) for consistency
   with the manifest's recorded history — this is bookkeeping cleanup, not
   what makes the rollback effective; the effective rollback already
   happened in step 1 above.
4. Re-run step 1's window-0 parity gate to reconfirm iter275 behavior
   post-rollback: as in step 1, run it against a **private/local instance**
   of the iter275 image+checkpoint with a throwaway `--logit-export-token`
   (never directly against the live "blue" service, which — like the
   original production endpoint — has no token configured and would 400
   every request) before declaring the incident closed.

## Recording outcomes

Record every stage's outcome (pass/fail, dates, report paths, disagreement
rate, fallback counts) in the B2c progress note before proceeding to the
next stage.

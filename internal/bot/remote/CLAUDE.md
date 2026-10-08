# internal/bot/remote/

> Plays a seat through a Python policy server (`fh-mj-serve-policy`), with heuristic fallback.

A separate package because `rl` imports `bot`, while remote policies need `rl`'s encoders.

## Key files

- **http_policy.go** — `HTTPPolicy`:
  - Encodes the observation with `rl.EncodeObservationWithEvents` using its own configured event
    window, POSTs `/act`, and decodes the returned `action_id` with `rl.DecodeActionID` against
    the live legal set.
  - Any failure falls back to the heuristic policy with a reason: `config`, `encode`, `request`,
    `status`, `bad_json`, `remote_error`, `illegal_action`, `decode`, `unknown`.
  - `ChooseActionCtxProv` is the one place remote vs fallback is decided; the checkpoint sha comes
    from the same `/act` response as the action (never a separate `/healthz` read that could race a
    reload). A legacy server without the field yields an empty sha, not an error.
  - Per-instance counters (`Stats()`, `DecisionCounts()`, `ObservedPolicyIDs()`) feed paipu
    provenance, so `cmd/server` builds a fresh instance per RL seat.
  - `ValidateServer` checks `/healthz` (event window, contract version). `cmd/server` runs it in
    the background at startup; a mismatch logs loudly and still fails closed per decision.
- **health.go** — `HealthChecker`: cached `/healthz` probe that gates the RL seat option;
  `Identity()` returns the public-safe `"<basename>@step<N>"` label (never a path or URL).
- **warmup.go** — `WarmupManager`: drives `POST /warmup` so no match pays a cold forward pass.
  Warm once per endpoint per TTL (default 15 m; 0 = once per process); concurrent callers share
  one request and its result; failures are never cached; 10 s budget; optional bearer token; every
  attempt logs a `policy warmup:` line.
- **rl_endpoint.go** — `EffectiveRLEndpointURL[FromEnv]`: `RL_AGENT_POLICY_URL`, else
  `AI_BOT_POLICY_URL`, else the localhost default. Shared by `cmd/server` and the review API.
- **service_identity.go** — `SameServiceEndpoint(a, b)`.
- **checkpoint_identity.go** — `checkpointIdentity(path, step)`.

## Invariants

- Never trust the Python service for legality.
- Keep the fallback local and deterministic (the heuristic policy unless a caller injects
  another).
- During live checks, read `HTTPPolicy.Stats()` to confirm the model is serving rather than
  silently falling back.

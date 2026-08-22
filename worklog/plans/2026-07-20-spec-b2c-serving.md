# Spec B2c: Serving Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the gate-qualified B2b champion servable: room-owned DecisionContext → event-carrying `/act` → metadata-aware Python loading, gated by a two-layer eval-vs-serving parity harness, with shadow mode ready for the post-merge rollout.

**Architecture:** Additive `bot.ContextPolicy` capability (bot.Policy untouched); the room snapshots RAW events under its game lock and owns the decision counter; `HTTPPolicy` applies its own declared contract (window from backend env, validated against `/healthz`). Compact JSON event fields on `/act`+`/evaluate` with fail-closed validation. `infer_model_config` reconstructs B2b architectures from checkpoint metadata cross-checked against tensor shapes. `ShadowPolicy` deep-clones state before async mirroring. Parity: Go byte-equality across the case matrix + `fh-mj-serving-parity` (in-process CI mode, true-HTTP hard-gate mode).

**Tech Stack:** Go 1.25 (`internal/bot`, `internal/bot/remote`, `internal/api`, `internal/rl`, `internal/review`, `cmd/server`), Python 3.12 (`ai/`). NO proto changes (wire is JSON).

**Spec:** `worklog/specs/2026-07-20-spec-b2c-serving-design.md` (approved by user + Codex, corrections 1-4 folded in). Branch: `claude/spec-b2c-serving` (exists, off main @ 85273ab).

## Global Constraints

- `bot.Policy` interface UNCHANGED — no ripple into `internal/rl`'s heuristic callers.
- Window-0 serving stays byte-identical (the old champion is the regression bar at every layer).
- An event model must NEVER infer on silent zero history — fail closed at Go encode, wire validation, and Python load/act layers.
- Compact wire form: `len(event_history) == event_count <= event_window`; a short-but-consistent early-round history is VALID.
- After Go changes: `go vet ./... && go test ./...`. After Python: `uv run --project ai pytest`.
- Commits end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Event contract v1 constants: `EventContractV1 = 1`; window ≤ `MaxEventHistoryWindow` (512); tail truncation; zero tail-padding + explicit count; observer-relative seats; per-round reset.

---

### Task 1: `bot.DecisionContext` + `ContextPolicy` + room dispatch

**Files:**
- Create: `internal/bot/context.go`
- Modify: `internal/api/room_bot.go` (both `ChooseAction` call sites, lines ~41 and ~66)
- Modify: `internal/api/room.go` (add the per-game decision counter field near `automatedDecisions`)
- Test: `internal/api/room_bot_test.go` (append; if absent, create), `internal/bot/context_test.go` (create)

**Interfaces:**
- Produces (later tasks depend on these exact names):

```go
// internal/bot/context.go
package bot

type DecisionContext struct {
    State         *pb.GameState
    Seat          uint32
    DecisionIndex uint64               // room-owned per-game counter
    Events        []engine.PublicEvent // snapshot COPY, RAW (unwindowed)
}

type ContextPolicy interface {
    ChooseActionCtx(ctx *DecisionContext) *pb.PlayerAction
}
```

(`internal/bot` gains an `internal/engine` import — legal: engine imports neither bot nor rl.)

- [ ] **Step 1: Write the failing tests.** `internal/bot/context_test.go`: a stub `ContextPolicy` receives a context whose `Events` slice does not alias the source (mutate source after build, assert context copy unchanged). `internal/api` test: a room whose `BotPolicy` implements BOTH interfaces gets `ChooseActionCtx` called with (a) non-nil State, (b) monotonically increasing `DecisionIndex` across two decisions, (c) `Events` equal to the engine's log at call time; a legacy-only policy still gets `ChooseAction`. Use the existing room test scaffolding in `internal/api/room_remote_test.go` as the construction pattern (`NewRoom(..., WithBotPolicy(...))`).
- [ ] **Step 2: Run to verify failure** (`go test ./internal/bot/ ./internal/api/ -run 'Context' -v` → compile FAIL).
- [ ] **Step 3: Implement.** `context.go` as above plus a room-side helper in `internal/api/room_bot.go`:

```go
// buildDecisionContext snapshots the decision atomically. Called with the
// room lock held (the callers already are). The events slice is COPIED —
// policies may consume it after the lock is released.
func (r *Room) buildDecisionContext(seat uint32) *bot.DecisionContext {
	events := r.Engine.PublicEvents()
	snapshot := make([]engine.PublicEvent, len(events))
	copy(snapshot, events)
	r.policyDecisionIndex++
	return &bot.DecisionContext{
		State:         r.Engine.State,
		Seat:          seat,
		DecisionIndex: r.policyDecisionIndex,
		Events:        snapshot,
	}
}
```

with `policyDecisionIndex uint64` added to the Room struct. At BOTH call sites replace `r.policyForSeat(seat).ChooseAction(r.Engine.State, seat)` with:

```go
			policy := r.policyForSeat(seat)
			var action *pb.PlayerAction
			if ctxPolicy, ok := policy.(bot.ContextPolicy); ok {
				action = ctxPolicy.ChooseActionCtx(r.buildDecisionContext(seat))
			} else {
				action = policy.ChooseAction(r.Engine.State, seat)
			}
```

(match each site's local variable usage exactly; confirm lock context — both sites run under the room's mutex per the surrounding code).
- [ ] **Step 4: Run tests + `go vet ./... && go test ./...`** — PASS.
- [ ] **Step 5: Commit** (`feat(bot): DecisionContext + ContextPolicy capability, room-owned dispatch`).

---

### Task 2: Exported events encoder + contract constants + Go feature parity (gate layer 1)

**Files:**
- Modify: `internal/rl/observation.go` (beside `EncodeObservation` ~180)
- Modify: `internal/rl/eventcodec.go` (contract constant)
- Modify: `ai/src/fh_mahjong_ai/events.py` (mirror constant `EVENT_CONTRACT_V1 = 1`)
- Test: `internal/rl/serving_parity_test.go` (create)

**Interfaces:**
- Produces: `rl.EncodeObservationWithEvents(state *pb.GameState, seat uint32, decisionIndex uint64, events []engine.PublicEvent, window uint32) (*pb.SeatObservation, error)` (thin wrapper over `encodeObservation(state, seat, decisionIndex, false, events, window)`); `rl.EventContractV1 = 1`.

- [ ] **Step 1: Failing test.** `serving_parity_test.go`: drive seeded envs (reuse `newSeededHistoryEnv` + `randomLegalActionID` from `eventcodec_test.go`) and at sampled decisions assert `EncodeObservationWithEvents(state, seat, idx, game.PublicEvents(), 128)` is `proto.Equal` (and marshal-byte-equal) to the eval path's `encodeObservation(state, seat, idx, false, game.PublicEvents(), 128)` across the CASE MATRIX: fresh round start (no events), a log driven past 128 entries within one long round if reachable — otherwise build a synthetic >128 log on the game via repeated draws — (tail truncation), the first decision after a round transition (fresh log), a normal PLAYER_TURN, and a WAIT_DISCARDS interrupt decision (construct as in `TestSearchPool_RootActionPinnedToRootSeat`). Also: window 0 → output byte-equal to `EncodeObservation` (3-arg legacy).
- [ ] **Step 2: RED** (undefined symbol).
- [ ] **Step 3: Implement** the wrapper + `EventContractV1 = 1` const with a comment naming the contract terms (window ≤ MaxEventHistoryWindow, tail, zero-pad+count, observer-relative, per-round reset), and the `EVENT_CONTRACT_V1 = 1` mirror in events.py.
- [ ] **Step 4: GREEN + full suites.**
- [ ] **Step 5: Commit** (`feat(rl): EncodeObservationWithEvents + event contract v1 + serving feature-parity tests`).

---

### Task 3: `HTTPPolicy` becomes a `ContextPolicy` (compact wire, /healthz handshake)

**Files:**
- Modify: `internal/bot/remote/http_policy.go` (ChooseAction :119, chooseRemote :163, actRequest struct, constructor options)
- Test: `internal/bot/remote/http_policy_test.go` (append — an `httptest.Server` pattern already exists in this package's tests; follow it)

**Interfaces:**
- Consumes: Task 1's `bot.DecisionContext`/`ContextPolicy`; Task 2's `rl.EncodeObservationWithEvents`, `rl.EventContractV1`.
- Produces: `remote.WithEventWindow(window uint32) Option` (0 = event-free, default); `HTTPPolicy.ChooseActionCtx`; `HTTPPolicy.ValidateServer(ctx) error` (GET /healthz, require `event_window == p.eventWindow` and `contract_version == rl.EventContractV1` when `p.eventWindow > 0`; a legacy healthz without those fields fails validation for event policies and passes for window-0 policies). actRequest gains:

```go
	EventHistory    []uint32 `json:"event_history,omitempty"`
	EventCount      int      `json:"event_count"`
	EventWindow     uint32   `json:"event_window"`
	ContractVersion uint32   `json:"contract_version"`
```

(the three scalar fields are ALWAYS sent — a window-0 policy sends 0/0/1 so the server can distinguish "legacy Go caller" from "event caller with empty history").

- [ ] **Step 1: Failing tests.** (a) `ChooseActionCtx` with a stub server: payload contains compact tail-windowed events (`len(event_history) == event_count <= event_window`), window, contract version; encoding equals `rl.EncodeObservationWithEvents` output for the same context; decision index comes FROM THE CONTEXT (the internal `p.decisionIndex` counter is not used on the ctx path). (b) window > available events → count == len(events), no padding on the wire. (c) `ValidateServer` against a stub /healthz: matching window+version passes; mismatched window fails; legacy body fails for eventWindow>0 and passes for 0. (d) legacy `ChooseAction` still works and sends `event_window:0`.
- [ ] **Step 2: RED.**
- [ ] **Step 3: Implement.** `ChooseActionCtx` mirrors `chooseRemote`'s request/response/validation flow but encodes via `rl.EncodeObservationWithEvents(ctx.State, ctx.Seat, ctx.DecisionIndex, ctx.Events, p.eventWindow)` and populates the event fields from the OBSERVATION's `EventHistory` (already tail-windowed by the encoder — compact form is exactly that slice). Fallback semantics unchanged (heuristic fallback + counters). Keep `chooseRemote` for the legacy path; extract the shared HTTP/request logic into a private helper rather than duplicating (~the existing body from `requestPayload :=` down).
- [ ] **Step 4: GREEN + full Go suite.**
- [ ] **Step 5: Commit** (`feat(bot/remote): HTTPPolicy speaks the event contract (compact /act, healthz handshake)`).

---

### Task 4: Python loading — metadata-authoritative reconstruction + CheckpointPolicy events

**Files:**
- Modify: `ai/src/fh_mahjong_ai/model.py` (`infer_model_config` — replace the B2b refusal)
- Modify: `ai/src/fh_mahjong_ai/storage.py` (helper `model_config_metadata(model_config) -> dict` used at save)
- Modify: `ai/src/fh_mahjong_ai/oracle.py` (train_b2b save: metadata gains the COMPLETE ModelConfig via the helper, keeping the `b2b` block)
- Modify: `ai/src/fh_mahjong_ai/serving.py` (`from_checkpoint` :57, `choose` :84, `evaluate_batch` :130)
- Test: `ai/tests/test_b2c_loading.py` (create)

**Interfaces:**
- Produces: `infer_model_config(state_dict, metadata=None) -> ModelConfig` — signature gains optional `metadata`; reconstruction order: complete `metadata.model_config` if present → `metadata.b2b` four-flag block (iter_075 fallback; other fields inferred from shapes as today) → legacy shape inference (no B2b keys). Cross-check: the reconstructed config must reproduce the state_dict's tensor SHAPES exactly (build a throwaway `PolicyValueNet` and compare key/shape sets) — mismatch raises. B2b keys with NO usable metadata still raise the B2c-scoped error. `CheckpointPolicy.from_checkpoint` passes the checkpoint's metadata; `choose`/`evaluate_batch` thread events exactly like `TorchGreedyPolicy` (tail-window to `model_config.event_window`, int64 row + length; `Observation.event_history` already exists). `ServedAction` unchanged.

- [ ] **Step 1: Failing tests.** (a) iter_075-style checkpoint (B2b modules + four-flag `b2b` metadata) → `from_checkpoint` succeeds, model has `event_window == 128`... use a SMALL config in the test (window 8) — assert reconstructed config matches the saved one field-for-field where determinable. (b) complete-metadata checkpoint (new save path) round-trips every ModelConfig field including non-default `channels`. (c) B2b modules without metadata → raises (unchanged guard). (d) doctored metadata contradicting tensor shapes → raises "shape cross-check". (e) `choose` on an event model with a populated `Observation.event_history` produces the SAME action as `TorchGreedyPolicy` on the identical observation (parity-in-miniature); with `event_history` EMPTY and window > 0, `choose` must RAISE (a served event model never silently zero-histories — serve_policy's validation is the first line, this is defense-in-depth) — window-0 models unchanged.
- [ ] **Step 2: RED.**
- [ ] **Step 3: Implement** (order matters: storage helper → train_b2b save → infer_model_config → CheckpointPolicy threading + the empty-history raise for event models).
- [ ] **Step 4: GREEN + full pytest.** Also re-run `ai/tests/test_b2b_training.py` (save-path change) and `test_reload_policy.py`.
- [ ] **Step 5: Commit** (`feat(ai): metadata-authoritative checkpoint loading + event-aware CheckpointPolicy`).

---

### Task 5: serve_policy — enriched /act + /evaluate, /healthz, validated /reload

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/serve_policy.py` (`observation_from_json` :194, `_handle_act` :108, `_handle_evaluate` :126, `do_GET` healthz :81, `_handle_reload` :161 + `PolicyHolder.reload` :43)
- Test: `ai/tests/test_serve_policy_events.py` (create; drive the handlers via `http.server` on an ephemeral port or by calling handler internals with a fake request — follow `test_reload_policy.py`'s existing pattern)

**Interfaces:**
- Consumes: Task 4's loading + event-aware `choose`; `EVENT_CONTRACT_V1` from events.py.
- Produces: `observation_from_json(payload, model_event_window)` validating per the compact contract:
  - window-0 model: event fields ignored entirely (byte-identical behavior — regression bar);
  - event model: `event_history`/`event_count`/`event_window`/`contract_version` REQUIRED; `len(event_history) != event_count`, `event_count > event_window`, `event_window != model_event_window`, or `contract_version != EVENT_CONTRACT_V1` → `ValueError` (handler → HTTP 400 with the reason). `event_count == 0` with consistent fields is VALID (early round).
  - `/evaluate`: same per-observation validation.
  - `/healthz` adds: `checkpoint_sha256` (computed once at load), `model_config` summary (from metadata), `event_window`, `contract_version`.
  - `PolicyHolder.reload`: build + validate the NEW policy fully (load, metadata cross-check, window match against the CURRENT policy's window unless explicitly overridden by the reload request's `expected_event_window` field) BEFORE swapping the reference; on any failure the old policy remains active and the response is an error.

- [ ] **Step 1: Failing tests** covering: valid short history accepted; each of the four 400 conditions; window-0 model ignores garbage event fields; healthz carries sha256+window+version; reload of an incompatible checkpoint leaves the active policy serving (subsequent /act still answers with the OLD checkpoint path).
- [ ] **Step 2: RED.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: GREEN + full pytest.**
- [ ] **Step 5: Commit** (`feat(ai): event contract on /act & /evaluate, enriched /healthz, validated reload`).

---

### Task 6: Review replay + review client

**Files:**
- Modify: `internal/review/replay.go` (:335 region — the EncodeObservation call; plumb a `policyEventWindow uint32` through `BuildReport`/the replay driver, default 0)
- Modify: `internal/review/client.go` (the /evaluate batch payload gains per-observation compact event fields when window > 0)
- Modify: `internal/api/review.go` (:98 — pass the configured window; source = the same backend env as Task 7's wiring, default 0)
- Test: extend `internal/review`'s existing tests: window 0 → request payloads byte-identical to before (regression); window 8 → each batched observation carries consistent compact fields matching the replayed game's log at that decision.

- [ ] Steps: failing test → implement (`rl.EncodeObservationWithEvents(state, seat, idx, game.PublicEvents(), window)` in the replay loop — the replayed engine.Game regenerates the log naturally) → green + suites → commit (`feat(review): event-aware replay + enriched /evaluate batches`).

---

### Task 7: `bot.ShadowPolicy` + backend wiring

**Files:**
- Create: `internal/bot/shadow.go`, `internal/bot/shadow_test.go`
- Modify: `cmd/server/main.go` (~:99-119 policy resolver: wrap with shadow when `RL_AGENT_SHADOW_POLICY_URL` is set; the shadow HTTPPolicy gets `WithEventWindow` from `RL_AGENT_SHADOW_EVENT_WINDOW`, default 128)

**Interfaces:**
- Produces:

```go
func NewShadowPolicy(primary Policy, shadow ContextPolicy, queueSize int) *ShadowPolicy
// implements Policy AND ContextPolicy; Close() drains and stops the worker.
// Metrics() returns {Decisions, ShadowErrors, Dropped, Agreements, P95LatencyMs}.
```

Behavior: primary answers synchronously (ctx path if it implements ContextPolicy, else legacy). A DEEP CLONE — `proto.Clone(ctx.State).(*pb.GameState)` + copied events — is enqueued (non-blocking send; on full queue increment `Dropped` and skip). One worker goroutine calls `shadow.ChooseActionCtx`, records latency/agreement/error, logs one structured line per decision (`log.Printf` matching the package's existing style) and an aggregate line every 100 decisions. `Close()` closes the intake and waits for the worker.

- [ ] Steps: failing tests (primary's action always returned even when shadow blocks/errors; deep-clone isolation — mutate the live state after the call, worker sees the snapshot: use a slow stub shadow capturing its input; dropped counter under a full queue; Close() terminates cleanly; agreement counting) → implement → green + `go test ./internal/bot/ -race -count=2` → wire `cmd/server/main.go` (shadow wraps the RESOLVED primary policy; construction logged) → full suites → commit (`feat(bot): ShadowPolicy with deep-cloned async mirroring + backend wiring`).

---

### Task 8: `fh-mj-serving-parity` + runbook + docs sweep

**Files:**
- Create: `ai/src/fh_mahjong_ai/scripts/serving_parity.py`; register `fh-mj-serving-parity = "fh_mahjong_ai.scripts.serving_parity:main"` in `ai/pyproject.toml`
- Create: `ai/tests/test_serving_parity.py`
- Create: `worklog/plans/2026-07-20-spec-b2c-runbook.md`
- Modify: AGENTS.md for `internal/bot`, `internal/api`, `internal/rl`, `internal/review`, `ai/`

**CLI contract:** `fh-mj-serving-parity --checkpoint PATH [model flags] --event-history-window N --episodes E --start-seed S (--in-process | --endpoint URL) [--device cpu|cuda]`. For each seeded bridge decision state: build the /act-shaped payload EXACTLY as `HTTPPolicy` would (compact fields from the bridge observation's `event_history`); obtain the serving action via CheckpointPolicy in-process OR a real HTTP POST to `--endpoint`; obtain the reference action via `TorchGreedyPolicy` on the bridge observation; assert identical action IDs and (in-process only) max-abs logit diff ≤ 1e-4 same-device; any fallback/HTTP error/illegal action = immediate failure with the offending state dumped (seed + decision index). Exit 0 only on 100% parity; print a summary table. Tests: mock-bridge in-process parity end-to-end (window 8 model); an injected feature perturbation is CAUGHT (harness must fail when serving path is deliberately skewed — proves the harness can fail); endpoint mode against a locally spun `serve_policy` thread.

**Runbook** (transcribe the spec §6 sequence with exact commands: new image at window 0 → `fh-mj-serving-parity --endpoint` vs prod image with iter_075 → smoke → shadow ≥50 games (zero shadow errors/fallbacks, p95 < 200 ms, disagreement recorded) → canary ≥20 private-room matches (zero fallbacks) → atomic manifest-pointer + Zeabur switch (single commit flipping `current_chongci_reward_trained_best` to the iter_075 entry + deploy) → iter275 rollback path).

- [ ] Steps: failing tests → implement CLI → green + full pytest + `uv run --project ai fh-mj-serving-parity --help` → runbook + AGENTS.md sweep → full Go+Python verification + `git diff origin/main --stat` review → commit (`feat(ai): serving parity harness (hard gate) + B2c runbook`).

Then: final whole-branch review (fable) → adversarial-review-loop → PR → GitHub Codex approval → `gh pr merge N --merge` → execute the runbook (user-approved light gate).

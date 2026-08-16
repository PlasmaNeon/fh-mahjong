# internal/bot/

> Deterministic non-human seat policies.

## Overview

This package hosts server-side and CLI bot logic. Policies consume a `GameState`, seat index, and the legal actions already populated by the core engine, then return one concrete `PlayerAction`. The initial implementation is a deterministic heuristic bot built on top of the shared shanten analysis package.

## Key Files

- **heuristic.go** — Heuristic baseline policy:
  - prioritizes `TSUMO`, `RON`, and `ACCEPT_HAITEI`
  - ranks discards using shanten, useful tiles, route damage, and simple shape heuristics
  - respects haitei turn restrictions by discarding only the accepted haitei tile when no tsumo is available
  - simulates `CHII` / `PON` follow-up discards before deciding to call
  - applies conservative `KAN` rules that avoid wild tiles and unstable hand shapes
  - clones protobuf actions/tiles field-by-field to avoid copying generated message mutex state
- **heuristic_test.go** — Coverage for discard ranking, route preservation, call choices, and legality.
- **remote/** — Subpackage for Python-served AI policies. It calls a remote policy endpoint for an `action_id`, decodes that id through `rlenv`, and falls back to the heuristic policy on service or legality failures.
- **factory.go** — `NewPolicy(pb.Difficulty)` selects the policy implementation for a seat. Returns an error for unsupported / unspecified difficulty values. Used by `api.Matchmaker` when assembling per-seat policies for a `Room`.
- **factory_test.go** — Coverage for heuristic resolution and rejection of unspecified/unknown difficulty values.
- **context.go** — `DecisionContext{State, Seat, DecisionIndex, Events}` and the additive `ContextPolicy` interface (`ChooseActionCtx`). Room dispatch (`internal/api/room_bot.go`) prefers `ChooseActionCtx` when a policy implements it, falling back to legacy `ChooseAction` otherwise. `Events` is always a snapshot copy — callers may hold it past the room's lock.
  - **`DecisionProvenance` + `ProvenanceContextPolicy` (paipu v2)** — `DecisionProvenance{Source, FallbackReason, CheckpointName, CheckpointStep, CheckpointSha}` identifies where ONE decision's action came from (`"remote"|"fallback"|"heuristic"`); it travels only via return values, never as mutable policy state, so a hot reload between two decisions can never cross-attribute a checkpoint to the wrong action. `ProvenanceContextPolicy` is the additive capability (`ContextPolicy` + `ChooseActionCtxProv(ctx) (*pb.PlayerAction, DecisionProvenance)`); `internal/api/room_decisions.go`'s `chooseSeatAction` prefers it over plain `ContextPolicy` over legacy `Policy`, defaulting to a fixed `"heuristic"` provenance for policies that don't implement it. `remote.HTTPPolicy` is the only policy that reports `"remote"`/`"fallback"` — see `internal/bot/remote/CLAUDE.md`; it decodes the served checkpoint's `checkpoint_sha256` atomically from the same `/act` response that produced the action (never a separate `/healthz` call).
- **shadow.go** — `ShadowPolicy` (`NewShadowPolicy(primary, shadow ContextPolicy, queueSize)`): shadow-mode wrapper that lets a candidate `ContextPolicy` silently mirror a live primary's decisions for comparison without ever affecting play. Implements both `Policy` and `ContextPolicy`. The primary always answers synchronously; a deep clone (`proto.Clone` on state and the primary's action, plus a copied `Events` slice) is handed to a single background worker over a bounded channel — a full queue drops the decision (`Metrics().Dropped`) rather than blocking. `Metrics()` reports `{Decisions, ShadowErrors, Dropped, Agreements, P95LatencyMs}`; `Close()` drains the queue and stops the worker (idempotent via `sync.Once`). Legacy `ChooseAction` (no context) is answered by the primary with mirroring intentionally skipped — see the doc comment for why. Wired in `cmd/server/main.go` behind `RL_AGENT_SHADOW_POLICY_URL` (+ `RL_AGENT_SHADOW_EVENT_WINDOW`, default 128, capped at `rl.MaxEventHistoryWindow`), wrapping the resolved `RL_AGENT_POLICY_URL` primary for private-room RL seats.
  - **`ChooseActionCtxProv` (paipu v2)** — implements `ProvenanceContextPolicy` by forwarding the **primary's** provenance unchanged (the shadow candidate's own decision is never on the record — it exists purely for comparison, never for play). When the primary doesn't itself implement `ProvenanceContextPolicy`, this falls back to a fixed `DecisionProvenance{Source: "heuristic"}` alongside its plain `ChooseActionCtx` answer.
- **shadow_test.go** — Coverage: primary's action always returned (even when the shadow blocks or panics), deep-clone isolation against post-call mutation of state/events, dropped-under-full-queue, `Close()` termination/idempotency, and agreement counting.

## Architecture Notes

- The package is under `internal/` but separate from `internal/engine/` so the state machine remains ruleset-agnostic.
- Policies only rely on state already produced by the engine; they do not re-implement rules or mutate the game directly.
- The same policy should be reused by CLI demos, server-side empty seats, and future RL self-play data generation.
- Remote AI policies must keep the Go engine as final authority: every returned `action_id` is decoded against current legal actions before it can become a `PlayerAction`.
- Tile-type keys, the 0-33 index, and proto Tile/Action deep-clones come from the shared `tiles` package (`github.com/plasma/fh-mahjong/internal/tiles`) — do not re-inline `suit*100+value` or re-add local `cloneTile`/`cloneAction`.

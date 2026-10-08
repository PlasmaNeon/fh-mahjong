# internal/bot/

> Non-human seat policies: the deterministic heuristic bot, the policy interfaces, and the shadow
> wrapper. Remote (Python-served) policies live in `remote/`.

## Key files

- **policy.go** — the contracts:
  - `Policy.ChooseAction(state, seat)` — the base interface.
  - `ContextPolicy.ChooseActionCtx(*DecisionContext)` — adds a room-owned decision snapshot:
    state, seat, decision index, and a copy of the raw public event log. Each policy applies its
    own event window.
  - `ProvenanceContextPolicy.ChooseActionCtxProv` — also returns `DecisionProvenance` (source
    `remote`/`fallback`/`heuristic`, fallback reason, checkpoint name/step/sha) for the paipu v2
    trace. Provenance travels only in return values, so a hot reload between two decisions cannot
    mislabel either.
  - Callers prefer `ProvenanceContextPolicy` > `ContextPolicy` > `Policy`.
- **heuristic.go** — `HeuristicPolicy`: always takes tsumo/ron/haitei accept; ranks discards by
  shanten, useful tiles, route damage, and shape; simulates the follow-up discard before a
  chii/pon; avoids kans with wilds or unstable shapes; honors haitei restrictions. Deterministic.
  Plays empty seats, `cmd/play` opponents, and RL opponents.
- **factory.go** — `NewPolicy(pb.Difficulty)`; errors on unspecified or unknown difficulty.
- **shadow.go** — `ShadowPolicy(primary, shadow, queueSize)`: the primary answers synchronously;
  a deep copy of the decision goes to one background worker that asks the shadow and records
  agreement and latency. A full queue drops the comparison, never blocks. `Close()` drains and
  stops (idempotent). Provenance is always the primary's. Wired by `cmd/server` behind
  `RL_AGENT_SHADOW_POLICY_URL`; closed by the room at shutdown.

## Invariants

- Policies read engine-produced state and legal actions only; they never re-implement rules or
  mutate the game.
- Any action from a remote model is decoded against the current legal set before use (see
  `remote/`).
- Use the shared `tiles` package for face keys and clones; never re-inline `suit*100+value` or a
  local `cloneTile`/`cloneAction`.

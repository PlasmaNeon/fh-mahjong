# internal/engine/

> The ruleset-agnostic game state machine and the `RuleEngine` contract.

`Game` drives one match — wall, deal, turns, interrupt windows, round end, match end — and
delegates every rule decision to the injected `RuleEngine`. Overview in
[`docs/architecture.md`](../../docs/architecture.md).

## Key files

- **game.go** — `Game`:
  - `NewGame(matchID, ruleset, MatchOptions)` — classic or Chongci; the prevailing wind is East
    and never changes.
  - `ProcessPlayerAction(seat, action)` — the single entry point for players and bots.
    `handleActiveTurnAction` (discard, kan, flower, tsumo), `handleInterruptAction` (pon, chii,
    ron, kan during `WAIT_DISCARDS`).
  - `ResolveInterrupts()` — priority resolution once every eligible seat has responded or the
    room's timer fires. After a pon/chii it refreshes the claimer's valid actions.
  - `ExecuteSystemDraw()` / `ExecuteDeadWallDraw()` — wall draws. A normal draw clears all
    kong/flower bonus flags.
  - `SetWallSeed(seed)`, `SetNextDealer(seat)` — deterministic setup for RL, replay, and tests.
  - `InterruptQueued(seat)` — read-only view of queued interrupt responses (RL wrappers).
  - `finalizeRoundEnd()` / `startNextRound()` — payouts, Chongci dealer succession and bust
    check, next hand (scores carry over).
- **clone.go** — `CloneForBranch()`: an isolated copy for what-if rollouts; drops the recorder
  and timers so a branch cannot touch replay logs or schedule work.
- **redeal.go** — `RedealUnseen(actingSeat, seed)`: search determinization. Re-deals opponents'
  concealed hands and the undrawn wall from the acting seat's unseen pool, keeps all public state
  and wall geometry, clears the interrupt queue, and recomputes every non-acting seat's valid
  actions against its new hand (see invariants). `RedealUnseenForReview` canonicalizes the unseen
  pool by tile id first, so identical public states never depend on the true allocation.
  `VisibleWildIndicator()` returns the public indicator.
- **events.go** — the always-on per-round public event log (`PublicEvent`, `PublicEvents()`),
  captured at the same call sites as the paipu recorder but never nil-guarded. Cleared at deal,
  copied by `CloneForBranch`. `FaceIndex42` / `FaceIndex34` / `FaceIndex42FromID` are the single
  definition of the 42-face space (man 0–8, pin 9–17, sou 18–26, jihai 27–33, flower 34–41);
  `internal/rl` and `internal/review` wrap them. Tsumo, ron, and haitei refuse log no event.
- **paipu.go** — paipu DTOs and `PaipuRecorder`:
  - Records the canonical action stream per round, player labels (`Kind`, `Difficulty`,
    `PolicyID`; absent in old paipu), and round results.
  - **Paipu v2** (`PaipuVersion = 2`): `PaipuRound.Decisions` — one row per player decision
    (legal catalog ids, chosen id, source, fallback reason, checkpoint identity), separate from
    the pass-free `Actions` stream — and `PaipuMatchMeta` (status, placements, server commit,
    mode, contract versions), stamped by `internal/api` at persist time. `RecordDecision` falls
    back to the just-closed round when the recorded action itself ended the round.
  - `ProtoEnumsRevision = 1` guards the raw enum ints embedded in paipu JSON; bump it if
    `proto/game.proto` renumbers one.
  - The engine stays provenance-blind: catalog encoding and source labels come from the caller.
- **rule_engine.go** — `RuleEngine`: `GetInitialWall`, `EvaluateHand`, `CalculatePayouts`,
  `GetValidActions`, `GetValidInterrupts`, `ResolveInterruptPriority`.
- **mt19937.go** — Mersenne Twister wall shuffle for 108/136/144-tile walls, matching Tenhou's
  exactly (`testdata/`). `SeedFromUint64()` expands a compact seed via SplitMix64.

## Invariants

- **Never import `internal/rules`.** Rules arrive through `RuleEngine` only.
- `Game.State` (`*pb.GameState`) is mutated only here; the API layer serializes and broadcasts.
- **Wall consumption.** Dead-wall replacement draws descend from the back and can cross into the
  live wall; `ExecuteSystemDraw` must skip indices they consumed (`isTileConsumedByDeadWall`) or
  a tile is dealt twice. Gated by `internal/rl/env_fuzz_test.go`.
- **Flowers.** Non-wild flowers auto-reveal on every draw source (live wall, dead wall, accepted
  haitei) and after a chii/pon handoff; wild flowers stay in hand. `revealInitialFlowers` runs
  after the deal and after the dealer's 14th tile.
- If a replacement draw exhausts the wall or ends a Chongci match, keep the terminal phase; never
  return to `PLAYER_TURN` with no valid actions.
- `PlayerState.LastDiscardFromDrawn` (public tsumogiri flag) lives on the player, not on
  `ActiveDiscard`, because a no-interrupt discard clears `ActiveDiscard` before the broadcast.
- **Redeal honesty.** `RedealUnseen` recomputes interrupts for every non-acting seat regardless
  of its pre-redeal eligibility (gating on it would leak the true hands), excludes the active
  discarder (a player never interrupts its own discard), applies the haitei ron-only filter, and
  erases non-root draw faces from the clone's event log. Guarded by
  `TestRedealUnseen_GainingEligibilityAdmitted` and `TestRedealUnseen_DiscarderExcludedFromOpenWindow`.
- A naturally rolled dealer consumes one extra `GenU32()`; `SetNextDealer` skips it. Replays must
  pick the same path or the shuffle desyncs.

## Test gotchas

- `handleInterruptAction` auto-resolves only after every eligible seat responds. From a random
  deal another seat may also hold a claim, so a lone test claim can stay queued; drive it with
  `resolveLoneClaim()` in `game_test.go`.
- Pin the deal with `SetWallSeed(SeedFromUint64(n))` when asserting exact board state.

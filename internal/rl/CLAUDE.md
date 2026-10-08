# internal/rl/

> Deterministic RL environment around `engine.Game`: seeded resets, step-to-next-decision,
> seat-relative observations, the fixed 204-action catalog, batched env and search pools.

Observation and action layouts are documented in [`docs/ai-player.md`](../../docs/ai-player.md).

## Key files

- **action.go** — the 204-action catalog (`ActionCatalogVersion = 1`, pinned by
  `TestActionCatalogPinned`), legal masks, `EncodeAction` / `DecodeActionID` / `LegalActions`.
  Serving clients and `internal/review` resolve actions through the same legality map. Same-face
  copies collapse to one representative tile id. `FLOWER_REVEAL` is a system action, not in the
  catalog.
- **observation.go** — `39 × 42 × 1` planes + 58 scalars, never hidden opponent tiles.
  - `EncodeObservation` (event-free) and `EncodeObservationWithEvents(state, seat, decisionIndex,
    events, window)` (serving, review) wrap one internal encoder.
  - Scalar 1 is the prevailing wind relative to East, so East encodes as 0.
  - `publicSeenCounts` excludes `ActiveDiscard`: the claimable discard is already in the
    discarder's river.
  - Oracle mode appends 12 privileged planes (opponents' concealed hands) for training only.
- **eventcodec.go** — the packed public-event codec and `EventContractV1`. A draw's face is masked
  unless the observer drew it. `renderEventHistory` keeps the last `window` events, oldest first;
  window 0 returns nil and the observation stays byte-identical. Mirrored in
  `ai/src/fh_mahjong_ai/events.py`; change both or neither (shared golden vector).
- **lookahead.go** — `lookahead_version` 1: 13 per-face discard/call look-ahead channels after the
  39 public ones. Chii features sit on the sequence's middle face so every channel transforms
  under the face symmetries. Version 0 is byte-identical.
- **env.go** — `Env`: `Reset`, `Step`, `EvaluateBranches`, `GenerateHeuristicTrajectory`.
  - Non-learning seats are auto-played by the heuristic bot (`auto_play_heuristics`).
  - Chongci: per-step reward is the acting seat's score change since its last decision /1000
    (it telescopes to the match net). Each later hand gets a wall seed derived from the episode
    seed. `PHASE_MATCH_END` is terminal; round-end ready gates are auto-acked.
  - Classic: reward only at round end.
  - Terminal responses carry `RoundOutcome` (winner, win type, payouts, score `breakdown`).
  - `EvaluateBranches` clones the game, applies each candidate, and finishes with heuristics;
    it can stop at the next round end for hand-level labels.
- **envpool.go** — `EnvPool`: many envs stepped per FFI call (`ApplyCommands`; step/reset/skip
  per slot) on at most `GOMAXPROCS` goroutines. Returns flat little-endian buffers plus per-slot
  `SlotState`; event rows carry an explicit count because packed `0x0` is a valid event. Never
  self-resets — the caller owns seeds. `StepMarshaled` reuses buffers; its bytes are valid until
  the next call.
- **searchpool.go** — `SearchPool`: K determinized clones of one live decision
  (`CloneForBranch` + `RedealUnseen`), stepped with the `EnvPool` messages. `SearchPoolOptions`
  adds oracle planes, a true-state mode (no redeal; ground truth), and world ids for the search
  diagnostic.
- **route_probe.go** — read-only route shanten per legal discard, for the route study.
- **selfplay.go** — `ReadyAllPlayersForNextRound` (the round-end ready loop, with the hand-seed
  rule as a parameter), `IsFinalReadyBeforeNextRound`, `FinalScores`.

## Invariants

- Wrap `engine.Game`; never fork rules or transition logic.
- Face order everywhere: man 0–8, pin 9–17, sou 18–26, jihai 27–33, flower 34–41
  (`engine.FaceIndex42`).
- `advanceToDecision` resolves `WAIT_DISCARDS` only after every pending seat has queued a
  response, and must resolve an already-complete window even without auto-play.
- **Search honesty** (`searchpool.go`):
  - Clone seeds derive from `(pool seed, determinization group)` only — never from the live env's
    seed, which would deal the real future hand at a round boundary. Clones in the same group share
    a world (paired comparison).
  - The root seat is explicit when given (required under duplicate-seat evaluation, where a
    lower-numbered heuristic seat can also hold an interrupt); the first command is always played
    as the root seat's move.
  - After a round ends mid-rollout, the clone keeps going until the root seat's next genuine
    decision and returns that row (real mask) as the value bootstrap; it never emits a frozen
    foreign-turn view. A match end returns no observation. The decision cap is checked only at
    root decisions, with a hard stop at `2·cap + 16`.
  - Oracle-configured envs are refused, and so is `TrueState` with oracle planes.
- `observation_symmetry_test.go` proves the encoder equivariant and scoring invariant under suit
  permutations, rank reversal, and dragon permutations (except best-discard scalars 33–35, 37, 40,
  which break ties by face order). It licenses suit averaging in `ai/`.
- `env_fuzz_test.go` asserts no tile id ever appears twice in a hand (the dead-wall double-draw
  regression).
- Use the shared `tiles` package for face keys, indices, and clones.

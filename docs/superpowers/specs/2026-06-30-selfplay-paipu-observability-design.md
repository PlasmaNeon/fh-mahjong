# Self-Play Paipu Observability — Design (HELD)

**Status:** HELD / deferred — decided to build *later*, not now. Captured 2026-06-30.
**Owner context:** the self-play feature-dropout campaign (see `project_grp_ppo_campaign`,
PRs #117/#119/#120, promotion PR #122).

## One-line goal

A standalone tool that loads any policy checkpoint and emits **replay-viewable paipu**
(game records) so we can *watch how the agent actually plays* — without changing the
training loop or disturbing in-flight runs.

## Why this exists (the reasoning that led here)

We run **on-policy PPO** (online RL): each iteration collects fresh rollouts with the
current net, updates ~2 epochs, then **discards** the data. The moment we `ppo_update`,
that data is off-policy, so PPO cannot reuse it for training.

So the value of "saving paipu" splits by online-compatibility:

| Use | Compatible with our online PPO? | Verdict |
|---|---|---|
| **Observability / eval** (watch games) | Orthogonal — yes | **No-regret. This doc.** |
| **Opponent diversity (league)** | Yes, but needs saved model *snapshots*, not paipu | Already have it — the snapshot pool (branch `claude/ppo-selfplay-pool`) |
| **Data reuse for sample efficiency** | **No** — needs an off-policy/offline method (IMPALA/V-trace, SAC, or periodic IQL/CQL like the anchor) | Deferred; separate method decision |

The no-regret slice is **observability**: be able to *see* a checkpoint play, in the
existing `/replay/:matchId` viewer.

## Key decision: standalone generator, NOT loop instrumentation

- ❌ **Instrument the training loop** (emit paipu during rollout): only helps *future*
  runs, adds overhead to the throughput-bottlenecked hot path, and **can't help the
  in-flight runs** (sp-long/sp-big) without a restart that loses progress.
- ✅ **Standalone checkpoint → paipu generator**: load any saved checkpoint, play seeded
  matches, dump paipu in the existing format. Works on **existing checkpoints right now**
  (the winning 39ch student, iter_050, the anchor) with zero changes/risk to running jobs.

  Observability does **not** need the *historical* training games (PPO sampled them
  stochastically anyway) — it needs **on-demand** games from a given checkpoint.

## Approach (reuse what already exists)

- `cmd/rlpaipu/main.go` already generates a **seeded** match as paipu JSON — but driven
  by the **heuristic** bot (`generateHeuristicPaipu`). The plumbing seed → engine run →
  paipu is exactly what we reuse.
- `internal/engine/paipu.go` is the rich, replayable paipu format (every draw/discard/
  meld, flower reveals, per-round result with hand/melds/score breakdown/per-seat
  deltas), served at `/replay/:matchId`.
- **Change:** swap the action source from the heuristic → the **learned policy**, served
  via the existing remote-bot → `serve_policy.py` path (`internal/bot/remote`). The engine
  assembles a real paipu that drops straight into the replay viewer.
- Reuses: paipu format, engine, serving path, replay viewer. Minimal new code.

## Render modes (build both)

- **Self-play** (4× the same net) — matches the training regime; shows what the agent does.
- **Student vs 3 anchors** — the interpretable "is it visibly better?" view.

## Honest scope

The wiring is a **small but real** build, not a one-liner: a Go driver that builds the
**39ch observation**, queries `serve_policy` for each decision, and feeds `cmd/rlpaipu`'s
paipu assembly. The main integration point to verify is **encoder reuse** — the exact 39ch
plane encoding the policy server expects must match what the driver produces. Worth doing
cleanly rather than hacking.

## When we resume — next steps

1. **Code-grounding pass:** confirm how the 39ch obs is encoded for `serve_policy`; whether
   `internal/bot/remote` can drive a full engine match; and whether the bridge/env can
   return a paipu directly (`internal/rl/env.go` currently does **not** record one).
2. **Pick the path:** Go-remote-bot (reuse HTTP serving, no bridge change) vs a small bridge
   addition (env returns the paipu). Choose by which has less integration friction.
3. **Build:** `writing-plans` → subagent-driven (campaign norm), or just implement (small).
4. **Output target:** a CLI roughly `fh-mj-paipu --checkpoint X --mode selfplay|vs-anchor
   --seeds ... --out dir/` producing replay-viewable JSON.

## Explicitly deferred (NOT this work)

- Loop instrumentation / saving training-time paipu.
- Off-policy/offline RL **data reuse** (the sample-efficiency lever against the CPU-bound
  throughput wall) — a separate method decision (would move us off pure on-policy PPO).

## Deterministic-replay note (for if/when we *do* save training games later)

Self-play is fully seeded, but PPO samples actions stochastically, so seed alone won't
reproduce a game — you'd record the **action sequence** (a few KB/match; wall/draw
randomness is seeded, so given the actions the replay is exact). Store the **paipu** (not
raw tensors) as the canonical artifact and regenerate features on demand — that decouples
the corpus from the current encoding, so a future net with different inputs can still
consume old games.

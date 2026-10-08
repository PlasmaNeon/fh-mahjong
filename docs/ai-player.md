# AI Player Design

How the RL agent sees the table, chooses actions, is trained, and is served. Measurement and
promotion rules are in [`ai-evaluation.md`](ai-evaluation.md); what has been tried and learned is
in [`ai-findings.md`](ai-findings.md); module detail is in [`../ai/MODULES.md`](../ai/MODULES.md).

## Principles

- **Go is the simulator and the legality authority.** Python never re-implements rules. A policy
  returns an `action_id`; Go decodes it against the current legal set before anything changes.
- **The deployed policy sees only public information plus its own hand.** Opponents' hands
  appear only at training time, as critic input and auxiliary targets — never as a policy input.
- **Every decision is a training transition** — discard, pass, chii, pon, kan, win, haitei
  accept/refuse (Mortal-style operation-level learning), not one sample per hand.
- **No human game corpus exists for Fenghua.** The agent bootstraps from a heuristic bot and
  improves by self-play.

## Players

| Player | Where | Used for |
|---|---|---|
| Heuristic bot | `internal/bot/heuristic.go` | Empty seats, `cmd/play`, behavior-cloning data, the opponents in the promotion gate |
| RL policy | `ai/` checkpoint served by `fh-mj-serve-policy` | The private-room "RL Agent" seat and post-game review |

The heuristic ranks discards by shanten, useful tiles, and route damage, simulates the discard
after a chii/pon before calling, always takes a win, and avoids risky kans. It is deterministic.

## Decision interface

`internal/rl` turns `engine.Game` into an environment that stops at each decision of a learning
seat and returns a `SeatObservation`: tile planes, scalar features, an optional event history, and
a 204-wide legal-action mask.

### Action catalog (`internal/rl/action.go`, version 1)

| ids | action |
|---|---|
| 0 | pass |
| 1 | tsumo |
| 2 | ron |
| 3 / 4 | accept / refuse haitei |
| 5–46 | discard, one per tile face (42) |
| 47–80 | pon, per face (34) |
| 81–114 / 115–148 / 149–182 | kan: direct / closed / upgraded, per face |
| 183–203 | chii, per suit × start rank (3 × 7) |

Tile faces use one order everywhere: man 0–8, pin 9–17, sou 18–26, jihai 27–33, flowers 34–41
(`engine.FaceIndex42`). A face id stands for every physical copy; Go picks the tile. Flower
reveal is automatic and not in the catalog. Changing the catalog means bumping
`ActionCatalogVersion` (guarded by `TestActionCatalogPinned`).

### Tile planes (39 × 42 × 1)

Each channel is a 42-long vector over tile faces.

| channels | content |
|---|---|
| 0–3 | own concealed hand, count ≥ 1..4 |
| 4–7 | own open melds, count ≥ 1..4 |
| 8, 9 | own flowers; own discards (count/4) |
| 10–15 | right opponent: open melds ≥ 1..4, flowers, discards |
| 16–21 | across opponent: same |
| 22–27 | left opponent: same |
| 28 | the discard currently up for claim |
| 29 | wild faces |
| 30–35 | legal action families: discard, pon, kan-direct, kan-closed, kan-upgraded, chii |
| 36 | own concealed count/4 |
| 37 | publicly seen count/4 (excludes the claimable discard, which is already in the river) |
| 38 | all discards count/4 |

No spatial pooling: tile identity survives to the dense layers.

Two optional extensions sit after channel 39:
- **Privileged planes** (12, training only): the three opponents' concealed hands as count ≥ 1..4
  thresholds. They feed the critic and the belief target, never the policy.
- **Look-ahead planes** (13, `lookahead_version` 1, dormant): per legal discard and call, the
  shanten and useful-tile counts after it. Tried and did not help (see findings).

### Scalars (58)

| index | content |
|---|---|
| 0–23 | seat wind, prevailing wind, relative active seat, phase, wall and dead-wall counts, dice, haitei flag; per seat: hand size, score, meld and flower counts |
| 24 | face of the claimable discard |
| 25, 29–31 | shanten: overall, standard, seven pairs, Independence |
| 26–28 | opponents' discard counts |
| 32 | useful-tile count |
| 33–35, 37, 40 | best discard look-ahead: shanten after, useful tiles, delta, is-wild, its danger |
| 36 | wilds in hand |
| 38 | visible score potential |
| 39, 41 | danger of the claimable discard; danger range over legal discards |
| 42–57 | Chongci match context: mode, hand progress, rank, leader pressure, large-loss and bust margins, score gaps, current-hand threat |

### Event history

The observation carries the last *W* public events of the current round (W = 128 for every
current model), oldest first, each packed into one `uint32`:

```
bits 0-3 type (draw, discard, chii, pon, kan-open, kan-closed, kan-upgrade, flower)
bits 4-5 actor seat relative to the observer   bits 6-11 face (63 = unknown)
bits 12-13 called-from seat                     bit 14 tsumogiri   bit 15 haitei
```

Another seat's draw is masked to face 63 at encode time. Window 0 leaves the observation
byte-identical to an event-free one. The codec is `internal/rl/eventcodec.go`, mirrored in
`ai/src/fh_mahjong_ai/events.py`; change both or neither (a shared golden vector pins them).

## Model (`ai/src/fh_mahjong_ai/model.py`)

```
planes[:, :39] ─ conv stem (3×3, 96ch) ─ 4 residual blocks ─ flatten ─ linear 256 ─┐
scalars (58) ─ MLP 128 ───────────────────────────────────────────────────────────┤
events (≤128) ─ embedding 32 + side features ─ GRU 128 (last valid step) ──────────┤
                                                                       trunk MLP 256
                                    ┌──────────────┬─────────────────────┼──────────────┐
                              policy head     value head ◄── privileged   aux heads
                              (204 logits,    (scalar)       encoder over  belief 12×42,
                              masked)                        planes 39–50  deal-in, rank
```

- The policy path reads only the 39 public channels, so the actor is information-legal by
  construction. The privileged encoder feeds only the value head; aux heads read the public
  trunk. At serving time the privileged and aux modules are simply unused.
- A dueling Q head and legacy risk heads exist for the offline trainers; PPO does not use them.
- Architecture flags live in `ModelConfig` and every checkpoint's `metadata["model_config"]`.
  `infer_model_config` rebuilds the net from metadata and cross-checks tensor shapes; a
  checkpoint with an event encoder but no metadata is refused (the window is not recoverable from
  shapes).
- New modules are added default-off so existing checkpoints load strictly, and warm-starts
  zero-initialize the new input columns so the grown net equals its parent at step zero.

## Training

### Pipeline

1. **Heuristic data** — `fh-mj-generate-data` plays heuristic matches through the Go bridge.
2. **Behavior cloning** — `fh-mj-train-bc` fits the policy to heuristic actions. It only needs
   to be legal and plausible.
3. **Self-play PPO** — `fh-mj-train-b2b` plays all four seats with the current net and updates
   it with clipped PPO. Every champion since July 2026 descends, through a chain of PPO laps, from
   one offline anchor (BC + IQL on heuristic data); lineage in [`ai-findings.md`](ai-findings.md).
4. **Gate** — duplicate-seat evaluation and `fh-mj-compare` decide promotion
   ([`ai-evaluation.md`](ai-evaluation.md)).

### Recipe

| Setting | Value |
|---|---|
| Mode | Chongci (start 2000, bust at 0, 50-hand cap), step cap 4000 decisions |
| Reward | dense per-hand score delta / 1000 for the acting seat (sums to the match net) |
| Returns | GAE, γ = 0.99, λ = 0.95 |
| PPO | 320 matches/iteration, minibatch 256, 2 epochs, lr 2e-5, entropy 0, clip 0.2, grad norm 0.5 |
| Aux loss | 0.1 × (belief BCE + deal-in BCE + rank CE) |
| Self-play | all four seats are the learner; actions sampled from the masked policy |
| Augmentation | `--suit-augment`: each decision is collected in a random suit permutation |
| Collector | `--collector batched --pool-slots 256 --pool-pipeline-groups 2`, fp32 |

The evaluation metric (mean placement) is deliberately not the training reward. Do not tune the
reward toward it.

**Hindsight labels.** Deal-in: 1 for every decision of the seat that paid a ron in that hand.
Rank: the seat's final placement (0–3) or 4 for bust; truncated matches are masked out. Belief:
the privileged planes themselves.

### Collectors

- `process` — spawn workers, one forward per decision. The historical default.
- `batched` — one Go `EnvPool` steps every live match per FFI call and the net runs one batched
  forward per round (CUDA graphs on GPU). Pipeline groups overlap Go stepping with the forward.
  Greedy `per_row` output is byte-identical to the process collector; in production `batched`
  mode floats differ at rounding level, so a lap never switches collector mid-run.

Recipe fields that change which rows share a forward (`collector`, `pool_slots`,
`pool_pipeline_groups`, `trunk_dtype`, `suit_augment`) are rejected on resume.

### Resume and provenance

`train_state.pt` (model, optimizer, all RNG states, a config echo) is written atomically every
few iterations. `--resume-from-state` refuses any config drift and any run-id mismatch with
`history.json`. Training pins the bridge library's sha256.

### Throughput (RTX 4090, champion size)

About 1 minute per iteration with the batched collector and 2 pipeline groups: a 150-iteration
lap takes ~2.5 hours. Never run two memory-heavy jobs on the 24 GB card at once; past the limit
WSL pages GPU memory and both stall.

## Decision rule

- **Greedy.** The served policy plays the argmax of the masked logits. Sampling produced
  visible blunders against humans, and the greedy champion was not exploitable by a trained best
  response.
- **Suit averaging.** The rules treat man, pin, and sou identically and the encoder is proven
  suit-equivariant (`internal/rl/observation_symmetry_test.go`). Averaging the policy's
  log-probabilities over the six suit permutations of the observation, then taking the argmax,
  beat the plain policy by +0.037 placement with a lower tail. Every current strength claim is
  for the suit-averaged policy. It costs six forwards per decision (~9 ms CPU p50 vs ~3 ms).
  Enable it with `--symmetry-average suits` in evaluation and serving.

## Serving

```
Room ─► remote.HTTPPolicy ─► POST /act {seat, planes, scalars, action_mask,
            │                         event_history, event_count, event_window, contract_version}
            │                ◄─ {action_id, value, checkpoint_path, checkpoint_step, checkpoint_sha256}
            └─ rl.DecodeActionID against the live legal set ─► engine (or heuristic fallback)
```

- `fh-mj-serve-policy` endpoints: `/act`, `/evaluate` (batched probabilities for review; needs
  `FH_MJ_EVALUATE_TOKEN`), `/healthz` (checkpoint sha, model config, event window, contract
  version), `/reload` (hot-swap after full validation), `/warmup`.
- **Event contract v1**: Go sends the tail-windowed events the checkpoint declares. An event
  model rejects missing or inconsistent event fields with a 400 rather than inferring on a
  zeroed history; a window-0 model ignores them. Contract versions must match on both sides.
- **Serving parity is a hard gate.** `fh-mj-serve-policy` must choose exactly what the evaluator
  chose on the same states: `fh-mj-serving-parity` checks every decision of seeded matches,
  in-process or against a live endpoint (whose `/healthz` sha must match the checkpoint).
- Rollout to production goes shadow (candidate mirrors live decisions) → canary → switch.

## Current state (2026-10-08)

| Role | Checkpoint | Where |
|---|---|---|
| Production | deep4 `iter275` student, 39 channels, no events, greedy | `ai/checkpoints/deploy/`, Zeabur `policy` |
| Gate-qualified research champion | `anchor075` (`restart-iter075`, sha `ce9d867f…`) | `ai/checkpoints/anchors/` |
| Strongest registered policy | look-ahead-lap control `iter_150` (`f9662491…`), suit-averaged | training box |
| Running | 450-iteration continuation lap from `f9662491` (eval seeds 4,150,000+) | training box |

At a strong table the strongest policy is about +0.15 placement better than production.
Shipping it needs the B2c rollout (event-window serving, already built) plus suit-averaged
serving.

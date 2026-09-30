# RL Implementation Takeaways for fh-mahjong

The reading notes turned into concrete defaults for this repo. Current campaign state is in
[roadmap-and-development-plan.md § Where The Project Actually Is](./roadmap-and-development-plan.md#where-the-project-actually-is).

## Training pipeline

1. Generate heuristic trajectories with the Go simulator (`fh-mj-generate-data`).
2. Behavior-clone them (`fh-mj-train-bc`) — the warm start.
3. Train on-policy PPO self-play, symmetric all-four seats (`fh-mj-train-b2b`).
4. Promote only through fixed-seed duplicate-seat arenas with a pre-registered confirmation
   on a fresh window (`fh-mj-evaluate --duplicate-seats`, `fh-mj-compare`).

Every discard, pass, chii, pon, kan, win, and haitei decision is a training transition
(Mortal-style operation-level learning). Offline IQL/AWBC/CQL remain in the package as the
pre-PPO baselines; warm-start IQL fine-tunes of a strong anchor consistently regressed it.

## Model

- No-pooling residual CNN over `39 x 42 x 1` tile planes (96 channels, 4 blocks) plus a
  scalar encoder, so tile positions survive.
- An event GRU over the public decision history (B2b).
- Dueling Q head; channel attention stays an ablation.
- The flat 204-action masked head; split decision-family heads are deferred until the flat
  head is shown to be a bottleneck.

## Privileged information

Training-only. The B2b net has a privileged critic (51 channels: 39 public + 12 privileged)
feeding only the value head, plus auxiliary belief / deal-in / rank heads read from the public
trunk. The policy path consumes only the 39 public channels, so deployed inference never sees
hidden state.

## Reward

- Chongci training reward: dense per-hand score delta (score/1000). Evaluation metric: mean
  placement. Keep the two independent — never tune the training reward toward the eval vector.
- Classic Fenghua: terminal single-hand payout.
- An additive terminal placement bonus `(10,5,1,−10)` did not produce tail-safer play
  (placement-reshape, NULL). Large-loss shaping and CQL are ablations, never promotion criteria.

## Rules learned the hard way

- Do not initialize a Q head from policy logits; logits rank actions but are not calibrated
  payout predictions.
- A risk or auxiliary head is unusable until calibrated: AUC above random, monotonic risk
  bands, acceptable severity error. Every Chongci large-loss head tried ranked at chance
  (AUC 0.4998, 0.5096, 0.4990). Coefficient sweeps do not substitute for a different objective.
- Sparse first-divergence replay weighting did not improve the gate; do not repeat it without
  a changed objective.
- Paired-trace rows after the first divergence are not same-state counterfactuals — use them
  for calibration and data mining, never as promotion proof.

Details: [`worklog/rl-experiment/20260825-chongci-iql-era-experiment-ledger.md`](../../worklog/rl-experiment/20260825-chongci-iql-era-experiment-ledger.md).

## Observation scalars

58 scalars, compatible with the Go heuristic analysis:

| Indices | Content |
|---|---|
| 25 | overall shanten |
| 29-31 | route-specific shanten |
| 32, 34 | useful-tile counts (ukeire) |
| 36-37 | wild preservation |
| 38 | visible score potential |
| 39-41 | public danger heuristics |
| 42-57 | Chongci match context: mode, hand progress, rank strength, leader pressure, large-loss and bust safety, opponent pressure, score gaps, current-hand threat |

## Evaluation

- Fixed-seed duplicate evaluation with seats rotated on the same wall.
- Primary: mean placement with seed-clustered CIs. Guardrails: large-loss rate,
  positive-reward rate. Raw win rate is unusable — equal-strength agents drive it toward 25%.
- The promotion gate plays against 3 heuristic bots; a strong table
  (`--opponent-checkpoint`) is a separate measurement.

## Closed levers

ACH regret objective, snapshot-pool opponents, 8-block capacity, and determinized
pMCPA-style test-time search each failed to beat the champion; search got worse with more
budget. The champion was not exploitable by a trained best response.

## Not yet tried

Transformer or hierarchical sequence models (DTQN, GTrXL, Tjong).

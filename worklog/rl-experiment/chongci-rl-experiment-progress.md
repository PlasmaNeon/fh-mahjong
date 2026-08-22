# Chongci RL Experiment Progress Note

Last updated: 2026-06-16

This note is the running experiment notebook for the Fenghua Mahjong AI work,
especially the Chongci reward-learning line. Update this file after every new
data-generation run, training run, evaluation gate, promotion, rejection, or
material design change.

The style is intentionally closer to an interview or paper report than to a
short changelog. It records the research question, design rationale,
implementation path, experiment ledger, results, interpretation, and next
hypotheses so future work does not repeat old branches blindly.

## Abstract

The project started from a broad question: how do we turn a Fenghua Mahjong
rules engine into a useful AI agent, and how do we learn RL while building it?
The current answer is a pragmatic, Mortal-style training stack:

1. keep the Go engine as the authoritative simulator,
2. encode only visible information into `SeatObservation`,
3. collect operation-level transitions for every discard, pass, chii, pon, kan,
   win, and haitei decision,
4. warm-start policy quality with behavior cloning,
5. train conservative reward learners with discrete IQL on fixed datasets and
   mixed checkpoint self-play,
6. promote checkpoints only through duplicate-seat evaluation, not training
   loss, offline agreement, or raw win rate.

The main promoted Chongci checkpoint is:

```text
id: chongci_broader_mixed_iql_highrisk_pairwise_epoch001
path: /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
```

The latest experiments show a recurring pattern: reward-learning candidates can
improve EV while creating new tail losses unless the data includes enough
candidate-vs-anchor divergence coverage. The current broader mixed IQL anchor
is promoted because it improved mean reward, positive-reward rate, and
large-loss rate on two identical deterministic combined-gate repeats. The next
work should start from this checkpoint as the new Chongci anchor.

## Original Motivation And Learning Path

The discussion began with paper-read reports and roadmap work. The first durable
plan was to connect RL learning material directly to this repo instead of
keeping study notes separate from code.

The accepted learning and development direction became:

```text
simulator correctness
-> heuristic trajectories
-> behavior cloning
-> duplicate evaluation
-> conservative offline RL
-> mixed checkpoint self-play
-> live AI integration
```

Later, after reviewing Mortal and Suphx again, the direction was refined:

```text
Mortal-style operation-level Q/value learning first
Suphx-style oracle/global reward auxiliaries later
```

The user also preferred articles and maintained documentation over old videos.
The roadmap was updated accordingly in:

```text
docs/rl-papers/roadmap-and-development-plan.md
```

Key learning questions covered during the conversation:

- Bellman equation: why current value depends on immediate reward plus next
  value.
- Monte Carlo return `G_t`: total discounted future reward from timestep `t`.
- Episode: one complete rollout unit, which may mean one hand for classic mode
  or one multi-hand Chongci match for Chongci mode.
- Value: expected return from a state, not guaranteed reward.
- Temporal difference target:

```text
G_t ~= R_{t+1} + gamma * V(S_{t+1})
```

- `R_{t+1}`: the reward observed after taking the action at time `t`.
- `gamma`: the discount factor; it controls how much future reward matters.
- Q-learning: the update mainly uses current state/action/reward/next state;
  history only matters if it is encoded into the observation or model memory.
- Policy-action value equation:

```text
Q^pi(s, a) = r + gamma * Q^pi(s', pi(s'))
```

- ReLU: neural-network activation that keeps positive values and clips negative
  values to zero.
- AdamW: Adam optimizer with decoupled weight decay; useful default for neural
  network training.

These Q&A sessions directly shaped the code explanation: every training row is
an operation-level transition, and delayed match reward is backfilled to the
decision states that caused it.

## Design Commitments

### Simulator Boundary

Go remains the authority:

- `core/` owns the game state machine.
- `rules/` owns Fenghua scoring.
- `rlenv/` wraps the simulator for deterministic reset/step and observation
  encoding.
- Python never mutates game state directly.
- Python returns an `action_id`; Go still validates that action against legal
  actions before applying it.

This is important because an RL policy should not become a second unofficial
rules implementation.

### Observation Boundary

The deployed policy receives visible information only.

Current observation defaults:

```text
planes: 39 x 42 x 1
scalars: 50
action space: 204 discrete actions
```

Tile-face order follows the backend shanten order:

```text
man: 0-8
pin: 9-17
sou: 18-26
jihai: 27-33
flower: 34-41
```

Important scalar groups:

- overall shanten,
- route-specific shanten,
- ukeire / useful tile counts,
- discard look-ahead,
- wild preservation,
- visible score potential,
- public danger,
- Chongci mode and score-context features.

Hidden opponent hands and wall order are not exposed to inference. Oracle-style
auxiliary training remains a later direction, not a deployment input.

### Action Space

The fixed 204-action catalog is kept because it gives a stable bridge between
Go, Python, and serving:

- tile discards,
- chii variants,
- pon,
- kan variants,
- win actions,
- pass,
- haitei accept/refuse and related decision categories.

The flat head is not perfect, but it is stable. Hierarchical action heads are a
future optimization after the current reward loop is more reliable.

### Model Architecture

The default model is a no-pooling residual CNN over semantic tile planes plus a
scalar encoder:

- no adaptive pooling by default,
- residual convolution blocks preserve tile-face positions,
- dueling Q head separates state value from action advantage,
- channel attention is available as an ablation,
- transformer/history models are deferred.

This is not a direct Mortal clone. It is a practical bridge: Mortal-style
operation-level value learning with a repo-specific no-pooling tile-plane model.

### Reward Design

Classic Fenghua target:

```text
terminal single-hand payout for the acting seat
```

Chongci target:

```text
final match net score change / 1000
```

Discrete IQL default target:

```text
gamma ** steps_to_done * terminal_reward
```

This means reward learning starts from every operation, but the reward signal is
still delayed. A discard, chii, pon, kan, pass, or win decision receives a target
based on what eventually happened in that hand or match.

Large-loss shaping and CQL penalties are explicit ablations. They are not
promotion criteria by themselves.

### Evaluation Policy

For Chongci, raw win rate is not the main metric. Because four same-strength
agents often play together, win rate can hover near 25 percent and miss EV or
tail-risk improvements.

Primary metrics:

- mean reward / expected final net score,
- positive-reward rate,
- large-loss rate,
- duplicate-seat comparison on fixed seed windows.

Promotion rule:

```text
Promote only if mean reward improves on independent duplicate gates and
large-loss rate does not regress materially.
```

Training loss, offline action agreement, and quick screens are not enough.

### Seed-window policy (2026-07-14, binding)

The `870000+` window is RETIRED for promotion decisions: it selected
iter_200/240/275 AND scored every later gate, so any number measured on it
carries winner's-curse bias (~+0.035 expected on the champion's margin).

- **Screening** — `--start-seed 910000 --online-episodes 120` (480
  placements): cheap looks, checkpoint selection, curiosity. Unlimited use;
  never cite for promotion.
- **Confirmation** — `--start-seed 950000 --online-episodes 1500` (6000
  placements, ~6h on the 4090): final gates ONLY. Every promotion or
  lever-verdict claim must cite a confirmation run compared via
  `fh-mj-compare` (seed-clustered paired CI95). The windows cannot collide:
  screening consumes seeds far below 950000 at these episode counts.
- CIs: duplicate-seat rotations of one wall seed are correlated — use the
  clustered fields (`mean_placement_ci95_clustered`, `cluster_design_effect`)
  added 2026-07-14, not the naive iid `mean_placement_ci95`. Power reference
  (iid-optimistic; scale by the measured design effect): 1500 seeds ≈ ±0.03
  half-width; 80% power needs ~550 seeds for a true +0.05, ~1530 for +0.03.

## Implementation Milestones

### Roadmap And Study Docs

Durable documents:

- `docs/rl-papers/roadmap-and-development-plan.md`
- `docs/rl-papers/implementation-takeaways.md`
- this file

Important roadmap changes:

- replaced stale/dead links,
- removed video-first learning path,
- made article/docs-first study stages,
- moved from generic offline RL to Mortal-style operation-level Q/value
  learning,
- documented Suphx-style oracle training as later auxiliary work.

### Behavior Cloning

Behavior cloning was implemented as the first stable policy layer:

- generate heuristic trajectories through the Go bridge,
- train policy with cross-entropy over heuristic actions,
- evaluate exact/top-3/action-family agreement,
- use BC as a warm start and regularizer for reward learning.

BC is not treated as the final intelligence. It is a way to put the policy into
legal and plausible regions before reward-based learning.

### Data Visualization

Generated replay data was verified through the replay UI. This confirmed that
the data path from Go simulator to serialized transition records was usable for
inspection, not only training.

### Python Environment And MLflow

The project standard became:

```bash
uv run --project ai ...
```

Avoid pip, conda, and ad hoc virtualenv commands for this repo.

MLflow was added for training/evaluation runs. Important MLflow behaviors:

- training logs params and metrics,
- evaluation logs online duplicate metrics,
- artifacts are local to the AI package or remote run directory,
- checkpoint binaries stay outside git.

### Remote WSL Training

Training moved to remote WSL because the remote machine has an RTX 4090.
The Mac remains the coordination and git workspace; WSL owns large datasets,
checkpoints, MLflow runs, and reports under:

```text
/root/fh-mahjong-runs/
```

## Current Promoted Chongci Checkpoint

Current best:

```text
id: iql_lowlr_selfplay200_epoch003
method: discrete_iql_mixed_selfplay
checkpoint:
/root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
```

Training configuration:

```text
init checkpoint:
/root/fh-mahjong-runs/chongci-mixed-selfplay-iql-50-20260521-211207/checkpoints/iql_mixed_selfplay_50_4ep/epoch_004.pt

self-play episodes: 200
self-play start seed: 500000
self-play transitions: 203539
self-play checkpoint seats: 0, 2
epochs: 3
batch size: 4096
learning rate: 3e-5
gamma: 0.99
target mode: mc
expectile: 0.7
temperature: 1.0
max weight: 20.0
BC weight: 1.0
CQL weight: 0.0
max transitions per dataset: 200000
MLflow run id: 66bb53bf9b8d4d76882022369b823f3d
```

Promotion evidence:

Screen:

```text
duplicate_20_seed368000
seats: 80
candidate mean_reward: 0.2010250092
previous best mean_reward: 0.0398125127
candidate positive_reward_rate: 56.25%
previous best positive_reward_rate: 51.25%
candidate large_loss_rate: 12.50%
previous best large_loss_rate: 25.00%
```

Independent gates:

```text
duplicate_20_seed369000
seats: 80
candidate mean_reward: 0.0412124991
previous best mean_reward: -0.2162124813
candidate positive_reward_rate: 53.75%
previous best positive_reward_rate: 35.00%
candidate large_loss_rate: 23.75%
previous best large_loss_rate: 21.25%

duplicate_20_seed370000
seats: 80
candidate mean_reward: 0.0291249957
previous best mean_reward: 0.0258874949
candidate positive_reward_rate: 50.00%
previous best positive_reward_rate: 50.00%
candidate large_loss_rate: 18.75%
previous best large_loss_rate: 15.00%
```

Combined promotion view:

```text
combined_duplicate_60_seed368000_369000_370000
seats: 240
candidate mean_reward: 0.0904541681
previous best mean_reward: -0.0501708259
candidate positive_reward_rate: 53.33%
previous best positive_reward_rate: 45.42%
candidate large_loss_rate: 18.33%
previous best large_loss_rate: 20.42%
```

Interpretation:

- promotion was justified by aggregate EV and positive-rate improvement,
- one independent window had a large-loss regression,
- the aggregate including screening supported promotion,
- later experiments made us more cautious about single-window promotion.

## Experiment Ledger

### Baseline Direction: Heuristic To BC To Reward Learning

The first pipeline was:

1. generate deterministic heuristic trajectories,
2. train BC,
3. evaluate agreement and duplicate seats,
4. move to AWBC/IQL reward learning.

The key conclusion was that BC does not need to be perfect. It should make legal
and plausible decisions, then reward learning should try to improve EV.

### Classic Fenghua Reward Best

Classic Fenghua has a promoted AWBC reward-trained checkpoint:

```text
id: awbc_temp1_maxw2_value025_lr1e5_epoch006
path:
/root/fh-mahjong-runs/reward-next-ev-20260519-003157/checkpoints/awbc_temp1_maxw2_value025_lr1e5_500k_6ep/epoch_006.pt
```

This remains separate from Chongci. Chongci uses match-level net score and a
different evaluation mode.

### Chongci Mode Introduction

Chongci is a multi-hand score contest mode. It does not change Fenghua tile
rules or per-hand scoring, but it changes the episode:

```text
episode = multi-hand match until bust threshold or hand cap
reward = final net score change / 1000
```

This made the single-round policy still useful as a base, but not sufficient as
the final objective. The model can reuse tile-play knowledge, action masks, and
visible observations, but it needs match-context scalars and match-level reward.

### Mixed Self-Play IQL

Mixed self-play was added to move toward the Mortal way:

- keep operation-level transitions,
- let checkpoint seats generate data,
- keep older datasets instead of discarding them,
- train IQL over repeated `--data` inputs.

The current best Chongci checkpoint came from this line.

### Rejected Candidate: Self-Play 400 Fixed Engine

```text
id: chongci_selfplay400_fixed_mc_lowdrift_epoch002
method: discrete_iql_mixed_selfplay
checkpoint:
/root/fh-mahjong-runs/chongci-selfplay400-fixed-engine-20260522-163043/checkpoints/iql_selfplay400_fixed_mc_lowdrift_3ep/epoch_002.pt
```

Quick screen:

```text
duplicate_20_seed413000
seats: 80
candidate mean_reward: 0.0285124928
promoted mean_reward: 0.0148750069
candidate positive_reward_rate: 43.75%
promoted positive_reward_rate: 52.50%
candidate large_loss_rate: 17.50%
promoted large_loss_rate: 21.25%
```

Wider gate:

```text
combined_duplicate_60_seed414000_424000_434000
seats: 240
candidate mean_reward: -0.1544625033
promoted mean_reward: -0.0539875031
candidate positive_reward_rate: 42.08%
promoted positive_reward_rate: 47.50%
candidate large_loss_rate: 22.08%
promoted large_loss_rate: 16.25%
```

Decision:

```text
rejected
```

Interpretation:

- quick screen looked partially promising,
- wider gate reversed the signal,
- larger self-play alone did not guarantee improvement.

### Rejected Candidate: Safe TD BC8

```text
id: chongci_safe_td_bc8_epoch002
method: discrete_iql_mixed_selfplay
checkpoint:
/root/fh-mahjong-runs/chongci-safe-anchor-sweep-20260522-220530/checkpoints/safe_td_bc8/epoch_002.pt
```

Training intent:

- use one-step TD targets,
- reduce policy drift,
- strong BC anchoring,
- small CQL penalty.

Quick screen:

```text
duplicate_8_seed444000
seats: 32
candidate mean_reward: 0.1283750087
promoted mean_reward: 0.0115312636
candidate positive_reward_rate: 56.25%
promoted positive_reward_rate: 43.75%
candidate large_loss_rate: 12.50%
promoted large_loss_rate: 12.50%
```

Wider gate:

```text
combined_duplicate_60_seed454000_464000_474000
seats: 240
candidate mean_reward: -0.1355750089
promoted mean_reward: -0.0164624968
candidate positive_reward_rate: 42.50%
promoted positive_reward_rate: 45.42%
candidate large_loss_rate: 20.83%
promoted large_loss_rate: 12.08%
```

Diagnostics:

```text
candidate_vs_promoted_disagreement_rate: 0.002655
candidate_vs_dataset_agreement_rate: 0.997345
promoted_vs_dataset_agreement_rate: 1.0
```

Decision:

```text
rejected
```

Interpretation:

- candidate barely differed from the promoted policy offline,
- small online differences were enough to hurt gate results,
- one-step TD did not become the default.

### Rejected Candidate: CQL + Downside Shaping

```text
id: chongci_cql02_bc12_ll05_epoch002
method: discrete_iql_mixed_selfplay
checkpoint:
/root/fh-mahjong-runs/chongci-calibrated-cql-downside-run-20260523-062236/checkpoints/iql_cql02_bc12_ll05_2ep/epoch_002.pt
```

Training intent:

- stronger CQL,
- strong BC anchoring,
- direct policy path,
- downside shaping for large losses.

Failed-band wide gate:

```text
combined_duplicate_60_seed454000_464000_474000
seats: 240
candidate mean_reward: -0.0345291607
promoted mean_reward: -0.1980916709
candidate positive_reward_rate: 42.50%
promoted positive_reward_rate: 41.67%
candidate large_loss_rate: 15.83%
promoted large_loss_rate: 22.08%
```

Independent gate:

```text
combined_duplicate_60_seed484000_494000_504000
seats: 240
candidate mean_reward: -0.0853583515
promoted mean_reward: -0.0579000078
candidate positive_reward_rate: 42.08%
promoted positive_reward_rate: 44.58%
candidate large_loss_rate: 18.75%
promoted large_loss_rate: 17.92%
```

Decision:

```text
rejected
```

Interpretation:

- the method improved exactly the failed seed bands,
- the improvement did not generalize,
- Q-margin guarded policy overrides remained unsafe,
- direct policy training stayed the only viable serving path.

### Rejected Candidate: Broader Data CQL/Downside

Run:

```text
/root/fh-mahjong-runs/chongci-broader-downside-cql-run-20260525-221704
```

Training intent:

- reuse older Chongci datasets,
- include fixed 400 self-play data,
- try CQL/downside shaping with broader coverage.

Training summary:

```text
epochs: 2
batch size: 512
learning rate: 5e-6
target mode: mc
expectile: 0.5
temperature: 0.5
max weight: 5
policy weight: 0.25
BC weight: 12.0
CQL weight: 0.2
large loss threshold: -1.0
large loss penalty: 0.5
```

Failed-band screen:

```text
candidate seats: 120
candidate mean_reward: -0.1660416573
anchor mean_reward: -0.1216749996
candidate positive_reward_rate: 35.83%
anchor positive_reward_rate: 44.17%
candidate large_loss_rate: 18.33%
anchor large_loss_rate: 19.17%
```

Decision:

```text
stopped independent evaluation and rejected direction early
```

Interpretation:

- large-loss rate improved slightly,
- mean reward and positive rate regressed,
- not worth a wider gate.

### Rejected Candidate: Capped 400k Current-Policy Self-Play, Low-Drift IQL

Recorded in PR #48:

```text
PR: https://github.com/PlasmaNeon/fh-mahjong/pull/48
id: chongci_selfplay400k_current_lowdrift_epoch002
checkpoint:
/root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/checkpoints/iql_selfplay400k_current_lowdrift_2ep/epoch_002.pt
```

Data:

```text
source oversized run:
/root/fh-mahjong-runs/chongci-selfplay800-current-lowdrift-run-20260525-223354

capped dataset:
/root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz

selected transitions: 400000
selected shards: 8
policy source: all seats controlled by current Chongci promoted checkpoint
start seed: 860000
```

Training:

```text
epochs: 2
batch size: 4096
learning rate: 1e-5
target mode: mc
expectile: 0.7
temperature: 1.0
max weight: 10
policy weight: 1.0
BC weight: 1.0
CQL weight: 0.0
MLflow run id: bb71fd1dacec4a939f51ef41d9c231ba
```

Quick screen:

```text
combined_duplicate_40_seed514000_524000
seats: 160
anchor mean_reward: -0.1012624875
candidate epoch001 mean_reward: -0.2026062459
candidate epoch002 mean_reward: -0.0340625048

anchor positive_reward_rate: 41.25%
candidate epoch001 positive_reward_rate: 40.00%
candidate epoch002 positive_reward_rate: 48.12%

anchor large_loss_rate: 20.00%
candidate epoch001 large_loss_rate: 24.38%
candidate epoch002 large_loss_rate: 16.88%
```

Independent gate:

```text
combined_duplicate_60_seed534000_544000_554000
seats: 240
anchor mean_reward: -0.0512083434
candidate epoch002 mean_reward: -0.0707291663

anchor positive_reward_rate: 43.33%
candidate epoch002 positive_reward_rate: 44.17%

anchor large_loss_rate: 20.83%
candidate epoch002 large_loss_rate: 16.67%
```

Decision:

```text
rejected
```

Interpretation:

- epoch 2 passed the quick screen on all three tracked metrics,
- independent gate kept positive-rate and large-loss improvements,
- mean reward regressed on the independent gate,
- because expected value is primary, the checkpoint was not promoted.

### Conservative Capped 400k Ablation

Run:

```text
/root/fh-mahjong-runs/chongci-capped400k-conservative-ablation-20260526-001923
```

Training intent:

- reduce policy drift,
- preserve mean reward,
- keep some tail-loss benefit from capped current-policy self-play.

Configuration:

```text
epochs: 2
batch size: 4096
learning rate: 5e-6
target mode: mc
expectile: 0.7
temperature: 1.0
max weight: 5
q weight: 1.0
value weight: 1.0
policy weight: 0.5
BC weight: 2.0
CQL weight: 0.0
MLflow run id: 0f4744a3a4ab4448938e29eebfb2f643
```

Quick screen:

```text
combined_duplicate_40_seed514000_524000
seats: 160

anchor:
mean_reward: -0.1373062432
positive_reward_rate: 44.38%
large_loss_rate: 18.12%

candidate epoch001:
mean_reward: -0.0937437564
positive_reward_rate: 40.00%
large_loss_rate: 17.50%

candidate epoch002:
mean_reward: -0.1394562721
positive_reward_rate: 43.12%
large_loss_rate: 20.00%
```

Quick-screen interpretation:

- epoch 1 improved mean reward and slightly improved large-loss rate,
- epoch 1 regressed positive-reward rate,
- epoch 2 was not useful,
- epoch 1 deserved an independent gate.

Independent gate:

```text
/root/fh-mahjong-runs/chongci-conservative-epoch001-independent-gate-20260526-010515

combined_duplicate_60_seed534000_544000_554000
seats: 240

anchor:
mean_reward: -0.1068208367
positive_reward_rate: 42.08%
large_loss_rate: 16.67%

candidate epoch001:
mean_reward: -0.0642041788
positive_reward_rate: 44.58%
large_loss_rate: 18.75%
MLflow run id: f72806acfbf9469ba154fcc058192791
```

Decision:

```text
not promoted yet
```

Interpretation:

- candidate epoch 1 improved mean reward and positive-reward rate,
- candidate epoch 1 regressed large-loss rate,
- repeated fixed-seed anchor evaluations varied materially across runs,
- this candidate needs repeated independent gates or an evaluation-stability fix
  before promotion.

## Evaluation Stability Issue

The strongest new finding from the latest work is that "fixed seed" evaluation
is not as stable as expected. The same anchor checkpoint on the same nominal
seed windows produced materially different metrics in repeated gates.

Examples:

Earlier independent anchor for:

```text
534000 / 544000 / 554000
```

reported:

```text
mean_reward: -0.0512083434
positive_reward_rate: 43.33%
large_loss_rate: 20.83%
```

Later independent anchor on the same nominal windows reported:

```text
mean_reward: -0.1068208367
positive_reward_rate: 42.08%
large_loss_rate: 16.67%
```

This should not be hand-waved. Possible causes:

1. evaluation is not fully deterministic despite fixed wall seeds,
2. checkpoint policy inference has nondeterministic tie-breaking or GPU behavior,
3. Python/Go bridge order or reset behavior differs across runs,
4. Chongci multi-hand episodes amplify small action differences,
5. action selection may depend on unpinned runtime state,
6. duplicate evaluation may not be fixing every source of randomness.

Until this is understood, promotion should require stronger repeated evidence.

### Determinism Audit Update, 2026-05-26

Run directories:

```text
/root/fh-mahjong-runs/chongci-determinism-audit-patched-20260526-210542
/root/fh-mahjong-runs/chongci-determinism-audit-patched-20260526-211132
```

Audit setup:

```text
checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
seed windows: 534000:1, 544000:1, 554000:1
duplicate seats: true
episodes per repeat: 12
repeats: 3
match mode: chongci
chongci config: starting_score=2000, bust_threshold=0, max_hands=50
max steps: 20000
device: cuda
```

Fix 1:

`rlenv.Env.Reset(seed)` previously seeded only the first hand. Chongci episodes
can span many hands, and later `startNextRound()` calls consumed no RL seed, so
`core.dealTiles()` fell back to `time.Now().UnixNano()`. The fix stores the
episode seed in `Env` and derives a deterministic wall seed before the final
ready ack starts each later Chongci hand.

Verification:

```text
go test ./rlenv -run 'TestChongciResetDeterministicAcrossMultipleHands|TestGenerateHeuristicTrajectoryChongciReachesMatchEnd|TestDeterministicResetAndStep'
go test ./core ./rlenv
```

Intermediate result:

After fixing per-hand wall seeds, the audit still had one repeat drift:

```text
repeat 1: mean_reward=-0.1675833315 reward_digest=8aa75277b83d8252
repeat 2: mean_reward=-0.1332499832 reward_digest=2f2aeb62418f9e2a
repeat 3: mean_reward=-0.1675833315 reward_digest=8aa75277b83d8252
```

The only differing reward was one rotated seat/seed episode, which pointed to
gameplay resolution rather than broad random reset failure.

Fix 2:

`rules.FenghuaRuleset.ResolveInterruptPriority()` iterated over a Go map.
When two interrupt actions had the same priority, the winner could depend on
randomized map iteration order. The fix scans seats `0..3` and resolves
same-priority ties by ascending seat.

Verification:

```text
go test ./rules ./rlenv
```

Final audit result:

```text
run: /root/fh-mahjong-runs/chongci-determinism-audit-patched-20260526-211132
repeat 1: mean_reward=-0.1645833254 reward_sum=-1.9749999046 positive=41.67% large_loss=8.33% reward_digest=b7b031caf71aa6a1 online_digest=fc8afae414bf92b6
repeat 2: mean_reward=-0.1645833254 reward_sum=-1.9749999046 positive=41.67% large_loss=8.33% reward_digest=b7b031caf71aa6a1 online_digest=fc8afae414bf92b6
repeat 3: mean_reward=-0.1645833254 reward_sum=-1.9749999046 positive=41.67% large_loss=8.33% reward_digest=b7b031caf71aa6a1 online_digest=fc8afae414bf92b6
decision: deterministic on the focused repeated audit
```

Follow-up gate:

```text
run: /root/fh-mahjong-runs/chongci-conservative-epoch001-repeated-gate-20260526-211552
candidate: /root/fh-mahjong-runs/chongci-capped400k-conservative-ablation-latest/checkpoints/iql_selfplay400k_lr5e6_bc2_pw05_2ep/epoch_001.pt
anchor: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
seed windows per repeat: 534000:10, 544000:10, 554000:10
duplicate seats: true
episodes per checkpoint per repeat: 120
repeats: 2
status: complete
```

Results:

| Policy | Repeat | Mean Reward | Reward Sum | Positive Rate | Large-Loss Rate | Reward Digest |
|--------|--------|-------------|------------|---------------|-----------------|---------------|
| Anchor | 1 | -0.0557833426 | -6.6940011978 | 43.33% | 15.00% | `a736bf2ffdcde190` |
| Anchor | 2 | -0.0557833426 | -6.6940011978 | 43.33% | 15.00% | `a736bf2ffdcde190` |
| Candidate epoch 1 | 1 | -0.0519666746 | -6.2360010147 | 45.00% | 17.50% | `237adc471625d510` |
| Candidate epoch 1 | 2 | -0.0519666746 | -6.2360010147 | 45.00% | 17.50% | `237adc471625d510` |

Decision:

Do not promote yet. The result is now deterministic and candidate epoch 1 has
better mean reward and positive-rate on this gate, but it still increases
large-loss rate from `15.00%` to `17.50%`. Treat the checkpoint as a useful
EV-improving candidate, not a serving checkpoint.

Next interpretation:

- The previous instability was evaluation nondeterminism, not just sampling
  noise.
- Conservative epoch 1 is directionally useful for EV.
- Tail-risk remains the blocker.
- The next training run should preserve the conservative setup but add a
  smaller tail-risk penalty or stricter promotion guard, then evaluate on the
  same deterministic repeated gate.

### Tail-Risk Penalty 0.10 Follow-Up, 2026-05-26

Run:

```text
/root/fh-mahjong-runs/chongci-conservative-epoch001-tailpenalty010-gate-20260526-222615
```

Question:

Can a small utility penalty for very negative returns preserve the EV gain from
conservative epoch 1 while reducing the large-loss regression?

Training:

```text
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
output checkpoint: /root/fh-mahjong-runs/chongci-conservative-epoch001-tailpenalty010-gate-20260526-222615/checkpoints/iql_selfplay400k_lr5e6_bc2_pw05_tail010_1ep/epoch_001.pt
data: same four-dataset capped400k mix as the conservative epoch-1 run
epochs: 1
lr: 5e-6
target_mode: mc
expectile: 0.7
max_weight: 5
policy_weight: 0.5
bc_weight: 2.0
cql_weight: 0.0
max_transitions: 400000 per dataset
large_loss_threshold: -1.0
large_loss_penalty: 0.1
mlflow training run: 466ebd83d72f41919d70c264737923eb
```

Evaluation:

Same deterministic repeated gate:

```text
seed windows: 534000:10, 544000:10, 554000:10
duplicate seats: true
episodes per repeat: 120
repeats: 2
```

Results:

| Policy | Repeat | Mean Reward | Reward Sum | Positive Rate | Large-Loss Rate | Reward Digest |
|--------|--------|-------------|------------|---------------|-----------------|---------------|
| Anchor | 1 | -0.0557833426 | -6.6940011978 | 43.33% | 15.00% | `a736bf2ffdcde190` |
| Anchor | 2 | -0.0557833426 | -6.6940011978 | 43.33% | 15.00% | `a736bf2ffdcde190` |
| Tail010 candidate | 1 | -0.0519666746 | -6.2360010147 | 45.00% | 17.50% | `237adc471625d510` |
| Tail010 candidate | 2 | -0.0519666746 | -6.2360010147 | 45.00% | 17.50% | `237adc471625d510` |

Evaluation MLflow runs:

```text
82290dbbf0b647198108299f270e6d7d
64c2695371d94fa28cbef97a286606cb
```

Decision:

Do not promote. `large_loss_penalty=0.1` was too weak to change the policy
outcome versus the no-penalty conservative epoch-1 candidate: the reward digest
and headline metrics are identical. The candidate still improves EV and
positive rate but worsens large-loss rate.

Next interpretation:

- The deterministic gate is working.
- A very small downside utility penalty does not materially change this
  checkpoint after one epoch.
- Next try should either use a stronger but still moderate penalty, such as
  `0.25`, or add a guarded policy-selection rule that rejects candidate
  overrides in high-risk states.

### Tail-Risk Penalty 0.25 Follow-Up, 2026-05-27

Run:

```text
/root/fh-mahjong-runs/chongci-conservative-epoch001-tailpenalty025-gate-20260527-215926
```

Question:

Does a stronger but still moderate downside penalty change the conservative
epoch-1 policy enough to keep the EV/positive-rate gain while restoring the
large-loss guardrail?

Training:

```text
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
output checkpoint: /root/fh-mahjong-runs/chongci-conservative-epoch001-tailpenalty025-gate-20260527-215926/checkpoints/iql_selfplay400k_lr5e6_bc2_pw05_tail025_1ep/epoch_001.pt
data: same four-dataset capped400k mix as the conservative epoch-1 run
epochs: 1
lr: 5e-6
target_mode: mc
expectile: 0.7
max_weight: 5
policy_weight: 0.5
bc_weight: 2.0
cql_weight: 0.0
max_transitions: 400000 per dataset
large_loss_threshold: -1.0
large_loss_penalty: 0.25
mlflow training run: d84eb52b6f184df0a24646de6831b76e
```

Evaluation:

Same deterministic repeated gate:

```text
seed windows: 534000:10, 544000:10, 554000:10
duplicate seats: true
episodes per repeat: 120
repeats: 2
```

Results:

| Policy | Repeat | Mean Reward | Reward Sum | Positive Rate | Large-Loss Rate | Reward Digest |
|--------|--------|-------------|------------|---------------|-----------------|---------------|
| Anchor | 1 | -0.0557833426 | -6.6940011978 | 43.33% | 15.00% | `a736bf2ffdcde190` |
| Anchor | 2 | -0.0557833426 | -6.6940011978 | 43.33% | 15.00% | `a736bf2ffdcde190` |
| Tail025 candidate | 1 | -0.0519666746 | -6.2360010147 | 45.00% | 17.50% | `237adc471625d510` |
| Tail025 candidate | 2 | -0.0519666746 | -6.2360010147 | 45.00% | 17.50% | `237adc471625d510` |

Evaluation MLflow runs:

```text
93d437b33943451d89f7bbed15eca591
af396285381d4d69b17e33183df7a0fe
```

Decision:

Do not promote. `large_loss_penalty=0.25` also produced the same reward digest
and headline gate metrics as the no-penalty and `0.10` candidates. The penalty
changed training loss slightly but did not change the deployed argmax policy on
this deterministic gate.

Next interpretation:

- Utility-target shaping at `0.10` and `0.25` is too weak, too indirect, or
  drowned out by BC regularization for this one-epoch setup.
- Repeating larger utility penalties blindly is lower value unless we first
  confirm that the learned logits/Q values change on high-risk states.
- The next useful branch is diagnostic/guarded: inspect large-loss seeds and
  candidate-vs-anchor first action divergences, then either add a risk-aware
  guard at action-selection time or train with explicit high-risk-state
  weighting.

### Policy-Head Guard Diagnostic, 2026-05-28

Run:

```text
/root/fh-mahjong-runs/chongci-policy-guard-diagnostics-20260527-232537
```

Question:

Can the conservative epoch-1 candidate be deployed behind a promoted anchor
policy, using the candidate only when a Q-margin says the candidate's policy
action is better than the anchor policy action?

Before the valid diagnostic, an implementation issue was found in
`GuardedQPolicy`: it selected the candidate action directly from the Q head.
That does not match normal checkpoint evaluation, where the deployed action
comes from the policy/logit head. The invalid Q-head-only sweep produced a
catastrophic selected-window result (`mean=-2.0541`, `large_loss=100%`) and was
stopped. The policy adapter was corrected so:

```text
anchor action    = argmax(anchor policy logits)
candidate action = argmax(candidate policy logits)
guard score      = candidate_q(candidate action) - candidate_q(anchor action)
chosen action    = candidate action only if guard score >= q_margin
```

Validation:

```text
uv run --project ai python -m pytest ai/tests/test_policies.py ai/tests/test_evaluate.py
remote: /root/.local/bin/uv run --project ai python -m pytest ai/tests/test_policies.py ai/tests/test_evaluate.py
```

Both local and remote focused tests passed: `14 passed`.

Selected-window setup:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes per policy: 44
large_loss_threshold: -1.0
anchor: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
candidate: /root/fh-mahjong-runs/chongci-capped400k-conservative-ablation-latest/checkpoints/iql_selfplay400k_lr5e6_bc2_pw05_2ep/epoch_001.pt
```

Baseline results on the same selected windows:

| Policy | Mean Reward | Reward Sum | Positive Rate | Large-Loss Rate |
|--------|-------------|------------|---------------|-----------------|
| Anchor | -0.1427727342 | -6.2820005417 | 40.91% | 20.45% |
| Candidate | -0.1820000112 | -8.0080003738 | 43.18% | 27.27% |

Corrected policy-head guard sweep:

| Q Margin | Mean Reward | Reward Sum | Positive Rate | Large-Loss Rate | Choice Rates |
|----------|-------------|------------|---------------|-----------------|--------------|
| 0.000 | -0.1694772840 | -7.4570007324 | 40.91% | 25.00% | same 99.749%, candidate 0.132%, anchor 0.119% |
| 0.005 | -0.1694772840 | -7.4570007324 | 40.91% | 25.00% | same 99.749%, candidate 0.132%, anchor 0.119% |
| 0.020 | -0.1693409383 | -7.4510011673 | 40.91% | 25.00% | same 99.749%, candidate 0.123%, anchor 0.128% |

Decision:

Do not run a full promotion gate for this guard. On the selected risk windows,
the corrected guard improves over the raw candidate but remains worse than the
anchor on both mean reward and large-loss rate. It also changes too few
decisions to be a strong serving strategy. This suggests the current
candidate's policy head is already very close to the anchor on most decisions,
and the harmful difference is concentrated in a small number of policy-action
divergences rather than broad Q confidence.

Next interpretation:

- A pure deployment-time Q-margin guard is not enough for this candidate.
- Tail penalties at `0.10` and `0.25` did not alter the deterministic gate.
- The next reward-learning branch should change the training distribution or
  target weighting directly: oversample/regress high-risk divergence states,
  add explicit large-loss transition weighting, or train a new candidate with
  stronger rank/bust-risk features instead of relying on a post-hoc guard.

### High-Risk Transition Weight 3.0 Quick Screen, 2026-05-29

Run:

```text
/root/fh-mahjong-runs/chongci-highrisk-weight3-20260529-134310
```

Question:

Can direct loss weighting for large-loss transitions change the conservative
epoch-1 policy where target utility penalties and post-hoc guards did not?

Implementation:

`train_iql.py` now accepts:

```text
--large-loss-weight <float>
```

When paired with `--large-loss-threshold`, the trainer upweights all IQL loss
terms for transitions whose terminal return is at or below the threshold. This
is different from `--large-loss-penalty`: the penalty changes the target
utility, while the weight changes how strongly those samples train the Q,
value, policy, BC, and CQL losses. Weighted losses are normalized by the sum of
sample weights so the batch learning-rate scale is not multiplied blindly.

Validation:

```text
local:  uv run --project ai python -m pytest ai/tests/test_iql.py ai/tests/test_policies.py ai/tests/test_evaluate.py
remote: /root/.local/bin/uv run --project ai python -m pytest ai/tests/test_iql.py ai/tests/test_policies.py ai/tests/test_evaluate.py
```

Both focused test runs passed: `25 passed`.

Training:

```text
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
output checkpoint: /root/fh-mahjong-runs/chongci-highrisk-weight3-20260529-134310/checkpoints/iql_selfplay400k_lr5e6_bc2_pw05_llw3_1ep/epoch_001.pt
data: same four-dataset capped400k mix as conservative epoch 1
epochs: 1
batch size: 4096
lr: 5e-6
target_mode: mc
expectile: 0.7
max_weight: 5
policy_weight: 0.5
bc_weight: 2.0
cql_weight: 0.0
large_loss_threshold: -1.0
large_loss_weight: 3.0
mlflow training run: dc78069ff34d4d4a8adabb99202669f2
```

The logged sample weights showed the weighting path was active:

```text
step 100 sample_weight=1.327
step 200 sample_weight=1.331
```

Selected high-risk quick screen:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes: 44
mlflow eval run: fbdd407efe7540789c5e0fd8748a9a4d
```

| Policy | Mean Reward | Reward Sum | Positive Rate | Large-Loss Rate |
|--------|-------------|------------|---------------|-----------------|
| Anchor | -0.1427727342 | -6.2820005417 | 40.91% | 20.45% |
| Raw conservative candidate | -0.1820000112 | -8.0080003738 | 43.18% | 27.27% |
| High-risk weight 3.0 | -0.1629772782 | -7.1710004807 | 45.45% | 27.27% |

Decision:

Do not run the full deterministic repeated gate for this candidate. The
training-side weighting did move the policy: mean reward and positive rate
improved versus the raw candidate on the selected windows. However, the
large-loss rate did not improve and remains materially worse than the anchor.

Next interpretation:

- Direct high-risk weighting works mechanically and changes the policy.
- Weight `3.0` is not enough to fix the tail-risk regression.
- The next run should either use stronger weighting (`4.0` to `6.0`) with even
  lower policy drift, or filter/oversample the exact first-divergence states
  instead of weighting every large-loss transition equally.

### High-Risk Weight 5.0 With Lower Policy Drift, 2026-05-30

Run:

```text
/root/fh-mahjong-runs/chongci-highrisk-weight5-bc3-pw025-20260530-005605
```

Question:

Does stronger high-risk weighting reduce large-loss rate if policy drift is
constrained harder with lower policy improvement weight and higher BC
regularization?

Training:

```text
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
output checkpoint: /root/fh-mahjong-runs/chongci-highrisk-weight5-bc3-pw025-20260530-005605/checkpoints/iql_selfplay400k_lr5e6_bc3_pw025_llw5_1ep/epoch_001.pt
data: same four-dataset capped400k mix as conservative epoch 1
epochs: 1
batch size: 4096
lr: 5e-6
target_mode: mc
expectile: 0.7
max_weight: 5
policy_weight: 0.25
bc_weight: 3.0
cql_weight: 0.0
large_loss_threshold: -1.0
large_loss_weight: 5.0
mlflow training run: 01519955e154456da9beac53f54c2d11
```

The logged sample weights showed the stronger weighting path was active:

```text
step 100 sample_weight=1.654
step 200 sample_weight=1.662
```

Selected high-risk quick screen:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes: 44
mlflow eval run: 408277b6ecd846d39df902c8812b0e37
```

| Policy | Mean Reward | Reward Sum | Positive Rate | Large-Loss Rate |
|--------|-------------|------------|---------------|-----------------|
| Anchor | -0.1427727342 | -6.2820005417 | 40.91% | 20.45% |
| Raw conservative candidate | -0.1820000112 | -8.0080003738 | 43.18% | 27.27% |
| High-risk weight 3.0 | -0.1629772782 | -7.1710004807 | 45.45% | 27.27% |
| High-risk weight 5.0, BC 3.0, policy 0.25 | -0.1738409400 | -7.6490011215 | 43.18% | 25.00% |

Decision:

Do not run the full deterministic repeated gate. This candidate reduces
large-loss rate versus the raw and weight-3 candidates, but it still trails the
anchor on tail risk and trails weight 3.0 on mean reward and positive rate.

Next interpretation:

- Broad high-risk weighting has a real effect, but the tradeoff is not clean:
  stronger weighting reduces tail rate slightly while damaging EV.
- The next useful path is not simply a larger global weight. It should target
  the exact action-divergence states, especially `pass->pon` / `discard`
  divergence cases identified by paired traces.
- Add first-divergence reports directly to evaluation output or create a
  high-risk dataset/filter so the trainer can emphasize those states without
  reweighting every large-loss trajectory.

### First-Divergence Risk Filtering Implementation, 2026-05-30

Implementation branch:

```text
codex/chongci-divergence-risk-reports
```

Question:

Can the training and evaluation stack expose exact high-risk cases directly,
so future experiments do not rely on manual JSON inspection or broad
large-loss weighting?

Implemented:

- Evaluation reports now include `episode_summaries` and `large_loss_episodes`
  at both single-seat and duplicate-seat levels.
- Paired trace reports now include:
  - candidate/right large-loss first-divergence cases,
  - new candidate/right large-loss cases where the anchor avoided the large
    loss,
  - worst reward-delta first-divergence cases,
  - action labels, action ids, decision index, seed, seat, rewards, and scalar
    snapshots for those cases.
- New sharded datasets preserve `decision_indices` and `sample_weights`.
- IQL training can consume paired trace reports:

```text
--risk-trace-report <paired_trace.json>
--risk-trace-weight <float>
--risk-trace-dataset-start-seed <seed per --data path>
--risk-trace-worst-delta-count <n>
```

The risk filter maps paired-trace seeds to dataset `episode_index` by subtracting
the provided dataset start seed. For new shards it matches:

```text
episode_index + seat + decision_index
```

For older shards that do not have `decision_indices`, it falls back to:

```text
episode_index + seat + action_id
```

This is intentionally explicit: current historical datasets do not always carry
enough metadata for true decision-index matching, so future targeted runs should
generate new shards with `decision_indices` preserved.

Validation:

```text
uv run --project ai python -m pytest \
  ai/tests/test_buffer.py \
  ai/tests/test_iql.py \
  ai/tests/test_evaluate.py \
  ai/tests/test_paired_trace.py \
  ai/tests/test_risk_filter.py \
  ai/tests/test_storage.py
```

Result:

```text
43 passed
```

Next interpretation:

- We now have the plumbing required for exact divergence-state training.
- The next experiment should regenerate or collect a small dataset over the
  same seed range as the risky paired-trace cases, then train with
  `--risk-trace-report` and verify that the matched transition count is
  non-zero before evaluating.

### Risk-Trace Matching Smoke, 2026-05-30

Run:

```text
/root/fh-mahjong-runs/chongci-risktrace-smoke-20260530-012825
```

Question:

Does the new `--risk-trace-report` path actually map paired-trace first
divergences back to training rows when the generated shards preserve
`decision_indices`?

Dataset generation:

Generated three all-checkpoint Chongci self-play shard sets with the promoted
current checkpoint controlling all four seats:

```text
current checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
trace report: /root/fh-mahjong-runs/chongci-risk-diagnostics-20260527-231007/reports/anchor_vs_candidate_selected_trace.json
```

| Start Seed | Episodes | Transitions | Output |
|------------|----------|-------------|--------|
| 534000 | 6 | 11,670 | `/root/fh-mahjong-runs/chongci-risktrace-smoke-20260530-012825/data/risk-seed-534000-n6-npz` |
| 544001 | 4 | 8,486 | `/root/fh-mahjong-runs/chongci-risktrace-smoke-20260530-012825/data/risk-seed-544001-n4-npz` |
| 554001 | 1 | 1,440 | `/root/fh-mahjong-runs/chongci-risktrace-smoke-20260530-012825/data/risk-seed-554001-n1-npz` |

Training smoke:

```text
--risk-trace-report /root/fh-mahjong-runs/chongci-risk-diagnostics-20260527-231007/reports/anchor_vs_candidate_selected_trace.json
--risk-trace-weight 6.0
--risk-trace-dataset-start-seed 534000
--risk-trace-dataset-start-seed 544001
--risk-trace-dataset-start-seed 554001
--risk-trace-worst-delta-count 8
```

Matching result:

```text
dataset=0 cases=20 matched_cases=4 weighted_transitions=3 matched_by={'seed_seat_decision': 4}
dataset=1 cases=20 matched_cases=1 weighted_transitions=1 matched_by={'seed_seat_decision': 1}
dataset=2 cases=20 matched_cases=0 weighted_transitions=0 matched_by={}
```

Decision:

The targeted risk-trace path works. It can map paired trace first-divergence
cases into generated training rows by exact `episode_index + seat +
decision_index`, and the smoke produced non-zero matched cases. This validates
the plumbing; it is not yet a promoted checkpoint experiment because the
dataset is intentionally tiny and used only to verify matching.

Next interpretation:

- The next real experiment should generate a larger risk-aligned dataset around
  the selected risky seed windows, train with `--risk-trace-report`, and
  quick-screen the result against the anchor/raw candidate selected-window
  baselines before any full repeated gate.
- Because only a few transitions matched, the next dataset should include all
  risky windows from the paired trace report and possibly use repeated
  checkpoint-pool self-play to create more rows around those exact decision
  states.

### Experiment: Risk-Trace Candidate V1

Run:

```text
/root/fh-mahjong-runs/chongci-risktrace-candidate-v1-20260530-013357
/root/fh-mahjong-runs/chongci-risktrace-candidate-v1-latest
```

Question:

Can exact first-divergence risk weighting improve the previously rejected
conservative reward learner on the selected high-risk windows without hurting
the promoted anchor's tail-risk behavior?

Data:

The training run reused the four main historical datasets:

```text
/root/fh-mahjong-runs/chongci-iql-50scalar-200-20260521-082220/data/heuristic-chongci-50scalar-200-npz
/root/fh-mahjong-runs/chongci-mixed-selfplay-iql-50-20260521-211207/data/selfplay-iql-seat0-vs-heuristic-npz
/root/fh-mahjong-runs/chongci-mixed-selfplay-iql-200-seats02-20260521-234609/data/selfplay-iql-seats0-2-vs-heuristic-npz
/root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-latest/data/selfplay-current-capped400k-npz
```

It also added the all-current risk-aligned smoke shards and new all-raw-candidate
risk-aligned shards for the selected seed windows:

| Policy Source | Seed Window | Episodes | Transitions |
|---------------|-------------|----------|-------------|
| promoted anchor | 534000 | 6 | 11,670 |
| promoted anchor | 544001 | 4 | 8,486 |
| promoted anchor | 554001 | 1 | 1,440 |
| raw conservative candidate | 534000 | 6 | 12,416 |
| raw conservative candidate | 544001 | 4 | 8,327 |
| raw conservative candidate | 554001 | 1 | 1,440 |

Training:

```text
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
output checkpoint: /root/fh-mahjong-runs/chongci-risktrace-candidate-v1-20260530-013357/checkpoints/iql_risktrace_v1/epoch_001.pt
epochs: 1
lr: 5e-6
max_transitions: 400000
target_mode: mc
expectile: 0.7
policy_weight: 0.25
bc_weight: 3.0
large_loss_weight: 1.0
risk_trace_weight: 6.0
risk_trace_worst_delta_count: 8
MLflow train run: c427a6312b7e425ba4b175c367654b1a
```

Risk trace matching was non-zero but sparse:

```text
current-policy shards matched: 5 cases, 4 weighted transitions
raw-candidate shards matched: 4 cases, 4 weighted transitions
```

Evaluation:

```text
report: /root/fh-mahjong-runs/chongci-risktrace-candidate-v1-20260530-013357/reports/candidate_risktrace_v1_selected_risk_windows.json
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes: 44
MLflow eval run: 98439cb470dd41b0902510bf6a21b617
```

Result:

| Checkpoint | Mean Reward | Reward Sum | Positive Rate | Large-Loss Rate |
|------------|-------------|------------|---------------|-----------------|
| promoted anchor | -0.1428 | -6.2820 | 40.91% | 20.45% |
| raw conservative candidate | -0.1820 | -8.0080 | 43.18% | 27.27% |
| high-risk weight 3 | -0.1630 | -7.1710 | 45.45% | 27.27% |
| high-risk weight 5 | -0.1738 | -7.6490 | 43.18% | 25.00% |
| risk-trace candidate v1 | -0.1466 | -6.4520 | 43.18% | 20.45% |

Large-loss cases for the risk-trace candidate:

```text
534001 seat 0 reward -1.930
534003 seat 0 reward -2.095
544003 seat 0 reward -1.463
534000 seat 1 reward -1.154
544001 seat 2 reward -1.009
544003 seat 2 reward -1.282
554001 seat 2 reward -1.364
534001 seat 3 reward -1.249
544004 seat 3 reward -1.116
```

Decision:

Rejected at quick-screen. Do not run the full repeated promotion gate for this
checkpoint.

Interpretation:

The risk-trace weighting direction is materially better than the raw
conservative candidate and the broader high-risk weighting variants on the
selected risk windows. However, it still does not beat the promoted anchor on
mean reward, and it only matches the anchor's large-loss rate instead of
improving it. The sparse match count also means the training signal is too thin
to justify promotion work. The next branch should either create denser exact
divergence-state coverage or add features that let the model generalize the
risk state rather than merely upweighting a handful of matched rows.

### Experiment: Risk-Trace Dense V2

Run:

```text
/root/fh-mahjong-runs/chongci-risktrace-dense-v2-20260530-014516
/root/fh-mahjong-runs/chongci-risktrace-dense-v2-latest
```

Question:

V1 had too few exact risk-case matches. Does a broader paired trace over the
full deterministic gate seed windows produce enough risk cases to improve the
candidate beyond the promoted anchor?

Trace:

```text
anchor: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
candidate source: /root/fh-mahjong-runs/chongci-capped400k-conservative-ablation-latest/checkpoints/iql_selfplay400k_lr5e6_bc2_pw05_2ep/epoch_001.pt
report: /root/fh-mahjong-runs/chongci-risktrace-dense-v2-20260530-014516/reports/anchor_vs_raw_candidate_gate_windows_trace.json
seed windows: 534000:10, 544000:10, 554000:10
seats: 0, 1, 2, 3
pairs: 120
divergence rate: 65.83%
raw candidate better rate: 20.00%
raw candidate mean delta vs anchor: +0.0038
```

The broader trace produced 61 unique risk cases:

```text
worst_delta: 40
candidate_large_loss: 21
new_candidate_large_loss: 3
unique seeds covered: 27
```

Data:

Dense v2 generated six risk-aligned shards, three from all-anchor self-play and
three from all-raw-candidate self-play:

| Policy Source | Seed Window | Episodes | Transitions |
|---------------|-------------|----------|-------------|
| promoted anchor | 534000 | 10 | 19,593 |
| promoted anchor | 544000 | 10 | 21,292 |
| promoted anchor | 554000 | 10 | 20,379 |
| raw conservative candidate | 534000 | 10 | 20,362 |
| raw conservative candidate | 544000 | 10 | 21,523 |
| raw conservative candidate | 554000 | 10 | 20,520 |

Training:

```text
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
output checkpoint: /root/fh-mahjong-runs/chongci-risktrace-dense-v2-20260530-014516/checkpoints/iql_risktrace_dense_v2/epoch_001.pt
epochs: 1
lr: 5e-6
max_transitions: 400000
target_mode: mc
expectile: 0.7
policy_weight: 0.25
bc_weight: 3.0
large_loss_weight: 1.0
risk_trace_weight: 6.0
risk_trace_worst_delta_count: 40
MLflow train run: 9c6d5b64116c4824bf7b3343e6a11643
```

Risk trace matching was materially denser than v1:

```text
anchor shards matched: 14 cases, 12 weighted transitions
raw-candidate shards matched: 14 cases, 13 weighted transitions
total matched: 28 cases, 25 weighted transitions
```

Evaluation:

```text
report: /root/fh-mahjong-runs/chongci-risktrace-dense-v2-20260530-014516/reports/candidate_risktrace_dense_v2_gate_windows.json
seed windows: 534000:10, 544000:10, 554000:10
duplicate seats: true
episodes: 120
MLflow eval run: 9de488f3b67047609350d9e7cadcf338
```

Result:

| Checkpoint | Mean Reward | Reward Sum | Positive Rate | Large-Loss Rate |
|------------|-------------|------------|---------------|-----------------|
| promoted anchor on paired trace | -0.0558 | -6.6940 | 43.33% | 15.00% |
| raw conservative candidate on paired trace | -0.0520 | -6.2360 | 45.00% | 17.50% |
| risk-trace dense v2 | -0.0578 | -6.9390 | 43.33% | 16.67% |

Decision:

Rejected at quick-screen. Do not run the full repeated promotion gate for this
checkpoint.

Interpretation:

Dense v2 fixed the data-density problem from v1, but the learned checkpoint
still did not beat the promoted anchor. The raw conservative candidate continues
to show the familiar tradeoff on these windows: slightly better EV and positive
rate, worse large-loss rate. Risk-trace dense v2 softened the tail-risk
regression versus the raw candidate, but gave up enough EV that it landed just
behind the anchor on both main promotion dimensions.

This suggests the next useful work is not more replay weighting with the same
features. The learner needs either stronger risk features, a better target for
match-level placement/tail risk, or a paired-action objective that can directly
prefer the anchor action over the candidate action at known harmful
divergences.

### Experiment: Pairwise Divergence Preference V1/V2

Implementation:

The IQL trainer now supports a direct paired-trace preference signal:

```text
--pairwise-weight <float>
--pairwise-margin <float>
--pairwise-replay-multiplier <int>
```

Risk cases loaded from paired traces now preserve both actions at the first
divergence:

```text
preferred action: anchor / left action
avoided action: candidate / right action
```

Matched training rows receive:

```text
pairwise_preferred_action_ids
pairwise_avoided_action_ids
pairwise_weights
```

The trainer applies a margin loss on policy logits:

```text
max(0, margin - (logit(preferred) - logit(avoided)))
```

The first implementation exposed an important bug: empty pairwise batches used
`logits.sum() * 0` as a zero loss. Because masked logits can contain `-inf`,
this produced `nan`. The fix returns a true scalar zero tensor when no valid
pairwise rows are present.

#### V1: Sparse Pairwise Replay

Run:

```text
/root/fh-mahjong-runs/chongci-pairwise-divergence-v1b-20260530-024913
```

Training:

```text
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
trace: /root/fh-mahjong-runs/chongci-risktrace-dense-v2-latest/reports/anchor_vs_raw_candidate_gate_windows_trace.json
risk_trace_weight: 3.0
pairwise_weight: 0.5
pairwise_margin: 0.25
pairwise_replay_multiplier: 0
MLflow train run: 5f0735f577cd4914bdc327e3892921ec
```

Signal check:

```text
matched pairwise cases: 28
matched pairwise transitions: 25
logged pairwise_count: 0 on sampled batches
```

Evaluation:

```text
report: /root/fh-mahjong-runs/chongci-pairwise-divergence-v1b-20260530-024913/reports/candidate_pairwise_v1b_gate_windows.json
episodes: 120
mean_reward: -0.0564
reward_sum: -6.7720
positive_reward_rate: 43.33%
large_loss_rate: 17.50%
MLflow eval run: de12e6f2896b4a0cb5293dec482452e0
```

Decision:

Rejected at quick-screen. The pairwise rows were too sparse under uniform
sampling to affect training reliably.

#### V2: Oversampled Pairwise Replay

Run:

```text
/root/fh-mahjong-runs/chongci-pairwise-divergence-v2-20260530-030337
```

Training:

```text
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
trace: /root/fh-mahjong-runs/chongci-risktrace-dense-v2-latest/reports/anchor_vs_raw_candidate_gate_windows_trace.json
risk_trace_weight: 3.0
pairwise_weight: 0.5
pairwise_margin: 0.25
pairwise_replay_multiplier: 256
MLflow train run: cca4cf60e69b4b9d91e553c57fccf286
```

Signal check:

```text
pairwise replay expanded rows: 6,400
logged pairwise_count: 3 to 8 on sampled batches
logged pairwise_loss: 0.0000
```

The zero pairwise loss is meaningful: the promoted-anchor-initialized policy
already ranked the anchor action above the raw-candidate action by the requested
margin on those sampled divergence rows. Therefore this auxiliary did not add a
strong corrective gradient.

Evaluation:

```text
report: /root/fh-mahjong-runs/chongci-pairwise-divergence-v2-20260530-030337/reports/candidate_pairwise_v2_gate_windows.json
episodes: 120
mean_reward: -0.0891
reward_sum: -10.6920
positive_reward_rate: 42.50%
large_loss_rate: 15.83%
MLflow eval run: db85d09131164abea61691718620dca4
```

Comparison on the same 120-seat gate-window screen:

| Checkpoint | Mean Reward | Reward Sum | Positive Rate | Large-Loss Rate |
|------------|-------------|------------|---------------|-----------------|
| promoted anchor | -0.0558 | -6.6940 | 43.33% | 15.00% |
| risk-trace dense v2 | -0.0578 | -6.9390 | 43.33% | 16.67% |
| pairwise v1b | -0.0564 | -6.7720 | 43.33% | 17.50% |
| pairwise v2 | -0.0891 | -10.6920 | 42.50% | 15.83% |

Decision:

Rejected at quick-screen. Do not run the full repeated promotion gate.

Interpretation:

The pairwise machinery is useful infrastructure, but this specific preference
target is mostly redundant when training starts from the promoted anchor. The
policy already prefers the anchor actions at those first-divergence states, so
the bad outcomes are likely coming from value/Q learning, later trajectory
distribution shift, or missing risk context rather than the policy head failing
to rank the anchor action above the candidate action at the recorded first
divergence.

Next direction:

Pairwise policy-margin loss should remain available, but the next experiment
should not spend another run on the same preference target. More useful options:

1. Add risk-context features that explain why the raw candidate's higher-EV
   choices create tail losses.
2. Add a Q/value-side pairwise target, comparing the anchor and candidate
   actions in the critic rather than only policy logits.
3. Add a match-level tail-value auxiliary for bust risk and score-pressure.

### Experiment: Pairwise Q Preference V1

Implementation:

The pairwise divergence machinery now supports an independent critic-side
margin loss:

```text
--pairwise-q-weight <float>
--pairwise-q-margin <float>
```

This reuses the same paired-trace labels as the policy-margin loss:

```text
preferred action: anchor / left action
avoided action: candidate / right action
```

But it applies the margin to Q values instead of policy logits:

```text
max(0, margin - (Q(preferred) - Q(avoided)))
```

Run:

```text
/root/fh-mahjong-runs/chongci-pairwise-q-v1-20260530-145835
```

Training:

```text
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
trace: /root/fh-mahjong-runs/chongci-risktrace-dense-v2-latest/reports/anchor_vs_raw_candidate_gate_windows_trace.json
risk_trace_weight: 3.0
pairwise_weight: 0.0
pairwise_q_weight: 0.5
pairwise_q_margin: 0.25
pairwise_replay_multiplier: 256
MLflow train run: 63ac6b6db06442f587b170b77ddb48eb
```

Signal check:

```text
pairwise replay expanded rows: 6,400
logged pairwise_count: 3 to 8 on sampled batches
logged pairwise_q_loss: nonzero early, then 0.0000 after the critic fit the margin
```

Evaluation:

```text
report: /root/fh-mahjong-runs/chongci-pairwise-q-v1-20260530-145835/reports/candidate_pairwise_q_v1_gate_windows.json
episodes: 120
mean_reward: -0.0801
reward_sum: -9.6080
positive_reward_rate: 42.50%
large_loss_rate: 17.50%
MLflow eval run: 2c9bccbd6e254418941a9c246317389b
```

Comparison on the same 120-seat gate-window screen:

| Checkpoint | Mean Reward | Reward Sum | Positive Rate | Large-Loss Rate |
|------------|-------------|------------|---------------|-----------------|
| promoted anchor | -0.0558 | -6.6940 | 43.33% | 15.00% |
| pairwise v2 policy-margin | -0.0891 | -10.6920 | 42.50% | 15.83% |
| pairwise Q v1 | -0.0801 | -9.6080 | 42.50% | 17.50% |

Decision:

Rejected at quick-screen. Do not run the full repeated promotion gate.

Interpretation:

The Q-side preference loss is mechanically active and trainable, unlike the
policy-margin loss that was already satisfied. However, fitting this critic
margin did not improve deployed policy behavior. It likely perturbed the
critic/policy update enough to hurt EV while still failing to solve tail risk.

This closes the current paired-trace preference branch. The next useful branch
should be feature-side or target-side:

1. Add explicit score-pressure / bust-risk context to the observation.
2. Add a match-level tail-value auxiliary that predicts probability or severity
   of crossing the large-loss threshold.
3. Revisit pairwise losses only after those richer risk signals exist.

## Risk-Context Feature Branch

Date: 2026-05-30

Branch:

```text
codex/chongci-risk-context-features
```

Question:

Can visible match-score context make the learner distinguish high-EV decisions
from decisions that increase large-loss exposure, instead of relying only on
post-hoc transition weighting?

Implementation:

At this May 30 branch stage, the observation scalar count stayed at `50` to
avoid a model-shape migration. This was later superseded by the May 31
58-scalar visible-context branch.
The Chongci tail scalars keep the existing visible-only inputs and replace the
weakest score-context slots with risk-aligned fields:

| Scalar | Meaning |
|--------|---------|
| 42 | Chongci mode flag |
| 43 | hand progress |
| 44 | remaining hand fraction |
| 45 | rank strength |
| 46 | leader pressure |
| 47 | own large-loss safety margin |
| 48 | own bust safety margin |
| 49 | opponent large-loss pressure |

The large-loss score threshold is derived from the current reward scale:
`starting_score - 1000`, clamped not to fall below the bust threshold. This
matches the default Chongci large-loss metric of final normalized reward
`<= -1.0` while using only visible score/config fields.

Expected caveat:

This changes scalar semantics for indices `46`, `47`, and `49`. Existing
checkpoints can still load, but comparisons after this branch should use
freshly generated observations/datasets or be treated as a feature-ablation
run, not a direct continuation of the previous scalar contract.

Next experiment:

1. Rebuild the Go bridge on the remote 4090 machine.
2. Generate a small Chongci mixed self-play smoke shard with the new scalar
   semantics.
3. Train one conservative IQL epoch from the promoted Chongci anchor.
4. Run the selected-window quick screen before any repeated promotion gate.

Smoke result:

```text
remote worktree: /root/fh-mahjong-risk-context
run: /root/fh-mahjong-runs/chongci-riskcontext-smoke-20260530-152708
dataset: /root/fh-mahjong-runs/chongci-riskcontext-smoke-20260530-152708/data/selfplay-current-riskcontext-n8-npz
transitions: 15,983 from 8 all-anchor Chongci self-play episodes
checkpoint: /root/fh-mahjong-runs/chongci-riskcontext-smoke-20260530-152708/checkpoints/iql_riskcontext_smoke/epoch_001.pt
training MLflow run: d56a4cd94a40440189c096e314764f51
```

Validation:

```text
local: go test ./rules ./rlenv
local: uv run --project ai pytest ai/tests/test_paired_trace.py
remote: go test ./rules ./rlenv
remote: uv run --project ai --extra dev pytest ai/tests/test_paired_trace.py
remote bridge: go build -buildmode=c-shared -o build/libfh_mahjong_bridge.so ./cmd/rlbridge
```

Tiny duplicate-seat screen:

```text
seed windows: 534000:2, 544001:2, 554001:1
online episodes: 20 duplicate seats
max steps per episode: 8192
anchor report: /root/fh-mahjong-runs/chongci-riskcontext-smoke-20260530-152708/reports/anchor_riskcontext_smoke_screen.json
candidate report: /root/fh-mahjong-runs/chongci-riskcontext-smoke-20260530-152708/reports/candidate_riskcontext_smoke_screen.json
anchor MLflow run: 06494788b2934bb39ea885b886a6ca5b
candidate MLflow run: d29ff2c676f6482f80107562a7e6f372
```

| Policy | Avg Reward | Positive Rate | Large-Loss Rate |
|--------|------------|---------------|-----------------|
| promoted anchor under new scalars | -0.1600 | 35.00% | 25.00% |
| risk-context smoke epoch 1 | -0.1600 | 35.00% | 25.00% |

Decision:

Smoke passed but is not promotable. The candidate only matched the anchor on a
tiny selected-window screen, and it trained from just 15,983 transitions.

Interpretation:

The feature-side path is mechanically valid: the Go encoder, Python
diagnostics, bridge build, self-play generation, IQL training, MLflow logging,
and duplicate evaluation all work with the new visible risk scalars. The next
useful run should regenerate a larger all-current or mixed-current dataset
under the new scalar semantics before training a real conservative IQL
candidate. Do not mix old scalar-semantics datasets into that main feature
ablation unless the run is explicitly marked as a compatibility experiment.

### Current64 Risk-Context Follow-Up

Run:

```text
/root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534
```

Question:

Does a larger fresh-scalar all-anchor self-play dataset make the risk-context
feature branch improve selected-window reward behavior after one conservative
IQL epoch?

Data:

```text
dataset: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/data/selfplay-current-riskcontext-n64-npz
episodes: 64 all-anchor Chongci self-play episodes
start seed: 606000
transitions: 131,842
shards: 50,000 / 50,000 / 31,842
```

Training:

```text
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
output checkpoint: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/checkpoints/iql_riskcontext_current64/epoch_001.pt
epochs: 1
batch size: 2048
lr: 5e-6
target_mode: mc
expectile: 0.7
policy_weight: 0.25
bc_weight: 3.0
cql_weight: 0.0
training MLflow run: ab1c41e7b2d54bcfbd7b9b83d52a675a
final loss: 0.1579
```

Evaluation:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes: 44
max steps per episode: 8192
anchor report: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/reports/anchor_selected_windows.json
candidate report: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/reports/candidate_selected_windows.json
anchor MLflow run: 56b021fa11d3415b84df5aa01bcdd6b9
candidate MLflow run: beb8ec53ae66460c9454d546764a56f6
```

| Policy | Avg Reward | Positive Rate | Large-Loss Rate |
|--------|------------|---------------|-----------------|
| promoted anchor under new scalars | -0.1400 | 40.91% | 20.45% |
| risk-context current64 epoch 1 | -0.1700 | 40.91% | 20.45% |

Decision:

Rejected at selected-window screen. Do not run a repeated promotion gate for
this checkpoint.

Interpretation:

The larger fresh-scalar run remained mechanically healthy, but the candidate
lost expected value while leaving positive-rate and large-loss guardrails
unchanged. This says the visible score-pressure scalars alone are not enough at
this data scale and hyperparameter setting. The next useful branch should add a
target-side signal, especially a match-level large-loss probability/severity
auxiliary, rather than scaling this exact current64 recipe.

## Large-Loss Auxiliary Target Branch

Date: 2026-05-30

Branch:

```text
codex/chongci-risk-context-features
```

Question:

Can a target-side auxiliary objective make the shared representation understand
large-loss states before the policy update tries to act on them?

Implementation:

The model keeps normal serving behavior unchanged: inference still selects from
masked policy logits. The shared trunk now also has default-off auxiliary heads:

| Head | Target |
|------|--------|
| large-loss probability | `terminal_return <= large_loss_threshold` |
| large-loss severity | `max(large_loss_threshold - terminal_return, 0)` |

Training flags:

```text
--large-loss-aux-weight
--large-loss-severity-weight
```

Both default to `0.0`, so existing IQL behavior is unchanged unless an
experiment explicitly enables them. Old checkpoints can still load; the new
auxiliary head starts from random weights when absent from the checkpoint.

Next experiment:

Use the fresh-scalar current64 dataset as a smoke test first:

```text
data: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/data/selfplay-current-riskcontext-n64-npz
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
large_loss_threshold: -1.0
large_loss_aux_weight: 0.25
large_loss_severity_weight: 0.10
```

Only run a selected-window screen first. If it loses EV or leaves large-loss
unchanged, reject and tune the auxiliary weights or data mix before any
promotion gate.

### Current64 Auxiliary Smoke

Run:

```text
/root/fh-mahjong-runs/chongci-riskcontext-aux-current64-20260530-232602
```

Question:

Does adding large-loss probability/severity auxiliary targets to the fresh
current64 scalar dataset improve selected-window tail behavior?

Data:

```text
data: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/data/selfplay-current-riskcontext-n64-npz
transitions: 131,842
```

Training:

```text
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
output checkpoint: /root/fh-mahjong-runs/chongci-riskcontext-aux-current64-20260530-232602/checkpoints/iql_riskcontext_aux_current64/epoch_001.pt
large_loss_threshold: -1.0
large_loss_aux_weight: 0.25
large_loss_severity_weight: 0.10
epochs: 1
batch size: 2048
lr: 5e-6
target_mode: mc
expectile: 0.7
policy_weight: 0.25
bc_weight: 3.0
cql_weight: 0.0
training MLflow run: 3d8faf2b071c4ebbace96796d6501bdb
final loss: 0.3298
```

Training diagnostics:

```text
step 20: ll_aux=0.6923 ll_sev=0.2345
step 40: ll_aux=0.6488 ll_sev=0.2214
step 60: ll_aux=0.5999 ll_sev=0.1939
```

Evaluation:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes: 44
max steps per episode: 8192
candidate report: /root/fh-mahjong-runs/chongci-riskcontext-aux-current64-20260530-232602/reports/candidate_selected_windows.json
candidate MLflow run: f50021375b9f40bcaaa409da612f38c3
```

| Policy | Avg Reward | Positive Rate | Large-Loss Rate |
|--------|------------|---------------|-----------------|
| promoted anchor under new scalars | -0.1400 | 40.91% | 20.45% |
| scalar-only current64 epoch 1 | -0.1700 | 40.91% | 20.45% |
| auxiliary current64 epoch 1 | -0.1900 | 40.91% | 25.00% |

Decision:

Rejected at selected-window screen. Do not run a repeated promotion gate for
this checkpoint.

Interpretation:

The auxiliary heads learned measurable losses, but this weight setting worsened
both expected value and large-loss rate. The likely issue is not plumbing; it is
that the auxiliary target shaped the shared trunk too strongly or too late
without giving the policy a better supported action distribution. Next target
ablation should reduce auxiliary weights sharply, freeze or detach the policy
path from the auxiliary gradient, or train the auxiliary only as a diagnostic
head before allowing it to influence the shared trunk.

### Current64 Small Auxiliary Smoke

Run:

```text
/root/fh-mahjong-runs/chongci-riskcontext-auxsmall-current64-20260530-233411
```

Question:

Does a much smaller large-loss auxiliary weight avoid the regression from the
first auxiliary setting?

Training:

```text
data: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/data/selfplay-current-riskcontext-n64-npz
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
output checkpoint: /root/fh-mahjong-runs/chongci-riskcontext-auxsmall-current64-20260530-233411/checkpoints/iql_riskcontext_auxsmall_current64/epoch_001.pt
large_loss_threshold: -1.0
large_loss_aux_weight: 0.05
large_loss_severity_weight: 0.02
training MLflow run: 65064772fa7946b8afe09d3e0747f4b8
final loss: 0.2039
```

Evaluation:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes: 44
candidate report: /root/fh-mahjong-runs/chongci-riskcontext-auxsmall-current64-20260530-233411/reports/candidate_selected_windows.json
candidate MLflow run: 6845d7aa619d42e7b89dec461199bf09
```

| Policy | Avg Reward | Positive Rate | Large-Loss Rate |
|--------|------------|---------------|-----------------|
| promoted anchor under new scalars | -0.1400 | 40.91% | 20.45% |
| scalar-only current64 epoch 1 | -0.1700 | 40.91% | 20.45% |
| auxiliary 0.25 / 0.10 | -0.1900 | 40.91% | 25.00% |
| auxiliary 0.05 / 0.02 | -0.1600 | 40.91% | 20.45% |

Decision:

Rejected at selected-window screen. Do not run a repeated promotion gate for
this checkpoint.

Interpretation:

Reducing the auxiliary weights removed the large-loss regression and improved
EV relative to the scalar-only candidate, but it still did not beat the anchor.
The useful next ablation is not a larger version of the same shared-gradient
auxiliary. Instead, test a detached auxiliary head so the risk labels can be
logged and calibrated without changing the shared trunk/policy update.

## Detached Large-Loss Auxiliary Branch

Date: 2026-05-31

Implementation:

Added a `--large-loss-aux-detach` IQL flag. When enabled, the large-loss
probability/severity heads are trained from detached trunk features. This keeps
the auxiliary diagnostics and checkpoint tensors, but blocks auxiliary gradients
from changing the shared tile/scalar trunk used by policy, Q, and value heads.

Question:

Does the large-loss auxiliary become harmless as a diagnostic/calibration head
when it cannot perturb the policy/Q representation?

Next experiment:

Use the same current64 dataset and selected-window screen:

```text
data: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/data/selfplay-current-riskcontext-n64-npz
large_loss_threshold: -1.0
large_loss_aux_weight: 0.25
large_loss_severity_weight: 0.10
large_loss_aux_detach: true
```

### Current64 Detached Auxiliary Smoke

Run:

```text
/root/fh-mahjong-runs/chongci-riskcontext-auxdetach-current64-20260531-012539
```

Question:

Does detaching the auxiliary gradient prevent the policy/Q regression observed
in shared-gradient large-loss auxiliary runs?

Training:

```text
data: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/data/selfplay-current-riskcontext-n64-npz
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
output checkpoint: /root/fh-mahjong-runs/chongci-riskcontext-auxdetach-current64-20260531-012539/checkpoints/iql_riskcontext_auxdetach_current64/epoch_001.pt
large_loss_threshold: -1.0
large_loss_aux_weight: 0.25
large_loss_severity_weight: 0.10
large_loss_aux_detach: true
training MLflow run: 27cec93b47af409296dbd1265798ad58
final loss: 0.3793
```

Evaluation:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes: 44
candidate report: /root/fh-mahjong-runs/chongci-riskcontext-auxdetach-current64-20260531-012539/reports/candidate_selected_windows.json
candidate MLflow run: 7a12feca2a8142ebb3e01e857af31119
```

| Policy | Avg Reward | Positive Rate | Large-Loss Rate |
|--------|------------|---------------|-----------------|
| promoted anchor under new scalars | -0.1400 | 40.91% | 20.45% |
| scalar-only current64 epoch 1 | -0.1700 | 40.91% | 20.45% |
| auxiliary 0.25 / 0.10 | -0.1900 | 40.91% | 25.00% |
| auxiliary 0.05 / 0.02 | -0.1600 | 40.91% | 20.45% |
| detached auxiliary 0.25 / 0.10 | -0.1700 | 40.91% | 20.45% |

Decision:

Rejected at selected-window screen. Do not run a repeated promotion gate for
this checkpoint.

Interpretation:

Detaching the auxiliary path removed the large-loss regression, confirming that
the bad 0.25 / 0.10 run was caused by shared-trunk perturbation rather than a
serving/evaluation bug. However, detached auxiliary training also reverted to
the scalar-only candidate behavior and did not improve the policy. This closes
the current64 same-data auxiliary sweep. The next useful experiment needs a new
ingredient: richer/generated risk states, a direct risk-aware action objective,
or a larger fresh-scalar dataset with mixed risk cases, not another auxiliary
weight tweak on the same current64 data.

## Fresh Risk-Seed Data Branch

Date: 2026-05-31

Question:

Can fresh-scalar data generated directly on known first-divergence / large-loss
seeds improve the selected-window tail-risk screen?

Risk seeds:

The seed list came from:

```text
/root/fh-mahjong-runs/chongci-risktrace-dense-v2-latest/reports/anchor_vs_raw_candidate_gate_windows_trace.json
```

Seeds:

```text
534000 534001 534002 534003 534005 534008 534009
544001 544003 544004 544007 544008 544009
554001 554005 554006 554007
```

Data generation:

```text
run: /root/fh-mahjong-runs/chongci-riskcontext-riskseeds-20260531-015743
anchor policy: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
raw candidate policy: /root/fh-mahjong-runs/chongci-capped400k-conservative-ablation-latest/checkpoints/iql_selfplay400k_lr5e6_bc2_pw05_2ep/epoch_001.pt
generated datasets: 34 one-episode shards
generated transitions: 69,148
```

### Risk-Seed Mix With Exact Risk Weighting

Run:

```text
/root/fh-mahjong-runs/chongci-riskcontext-riskseeds-20260531-015743
```

Training:

```text
base data: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/data/selfplay-current-riskcontext-n64-npz
risk data: 17 anchor shards + 17 raw-candidate shards
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
output checkpoint: /root/fh-mahjong-runs/chongci-riskcontext-riskseeds-20260531-015743/checkpoints/iql_riskseed_mix/epoch_001.pt
risk_trace_weight: 3.0
risk_trace_worst_delta_count: 40
training MLflow run: 14bc5f6ec6eb40129db3a63b1750a19c
final loss: 0.1387
```

Risk matching:

The fresh shards produced non-zero exact matches from the paired trace report.
The base current64 dataset had no exact matches; selected risk-seed shards had
`seed_seat_decision` matches and weighted transitions.

Evaluation:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes: 44
candidate report: /root/fh-mahjong-runs/chongci-riskcontext-riskseeds-20260531-015743/reports/candidate_selected_windows.json
candidate MLflow run: 7e20df1b86e24012b030d8a4012dd9e1
```

| Policy | Avg Reward | Positive Rate | Large-Loss Rate |
|--------|------------|---------------|-----------------|
| promoted anchor under new scalars | -0.1400 | 40.91% | 20.45% |
| scalar-only current64 epoch 1 | -0.1700 | 40.91% | 20.45% |
| risk-seed mix + risk weight | -0.1400 | 40.91% | 22.73% |

Decision:

Rejected at selected-window screen. EV matched the anchor, but large-loss rate
regressed.

### Risk-Seed Mix Without Risk Weighting

Run:

```text
/root/fh-mahjong-runs/chongci-riskcontext-riskseeds-nowt-20260531-021528
```

Training:

```text
base data: current64 fresh-scalar data
risk data: 17 anchor shards + 17 raw-candidate shards
output checkpoint: /root/fh-mahjong-runs/chongci-riskcontext-riskseeds-nowt-20260531-021528/checkpoints/iql_riskseed_mix_nowt/epoch_001.pt
risk_trace_weight: disabled
training MLflow run: 5af744bcb839462fae38a2c8dbd1aba2
final loss: 0.1354
```

Evaluation:

```text
candidate report: /root/fh-mahjong-runs/chongci-riskcontext-riskseeds-nowt-20260531-021528/reports/candidate_selected_windows.json
candidate MLflow run: c4f9de1774c3409ca33ca519b11d775e
```

| Policy | Avg Reward | Positive Rate | Large-Loss Rate |
|--------|------------|---------------|-----------------|
| promoted anchor under new scalars | -0.1400 | 40.91% | 20.45% |
| risk-seed mix, no risk weight | -0.1800 | 40.91% | 22.73% |

Decision:

Rejected. Adding raw-candidate risk-seed data without exact risk weighting
hurt EV and tail risk.

### Anchor-Only Risk-Seed Data

Run:

```text
/root/fh-mahjong-runs/chongci-riskcontext-riskseeds-anchoronly-20260531-022041
```

Training:

```text
base data: current64 fresh-scalar data
risk data: 17 anchor-only shards
output checkpoint: /root/fh-mahjong-runs/chongci-riskcontext-riskseeds-anchoronly-20260531-022041/checkpoints/iql_riskseed_anchoronly/epoch_001.pt
risk_trace_weight: 3.0
risk_trace_worst_delta_count: 40
training MLflow run: 30468004787842779a199fed5fe8fe6c
final loss: 0.1394
```

Evaluation:

```text
candidate report: /root/fh-mahjong-runs/chongci-riskcontext-riskseeds-anchoronly-20260531-022041/reports/candidate_selected_windows.json
candidate MLflow run: fd24298097a24b119fabb9e526529fde
```

| Policy | Avg Reward | Positive Rate | Large-Loss Rate |
|--------|------------|---------------|-----------------|
| promoted anchor under new scalars | -0.1400 | 40.91% | 20.45% |
| anchor-only risk seeds | -0.1600 | 43.18% | 22.73% |

Decision:

Rejected. Positive rate improved by one seat, but EV and large-loss rate both
missed the anchor.

Interpretation:

Fresh risk-seed data is useful mechanically because it produced exact
risk-trace matches, but the current recipe still moves the policy into worse
tail outcomes. Raw-candidate shards appear especially unsafe; anchor-only data
is safer but still not enough. The next useful direction should avoid simply
mixing whole risk-seed episodes. Instead, create an action-level objective that
uses first-divergence rows directly, or filter training to only the exact
matched risk decisions plus their short local context.

### Anchor-Only Filtered First-Divergence Replay

Run:

```text
/root/fh-mahjong-runs/chongci-riskcontext-riskseeds-filtered-20260531-035442
```

Question:

Can we avoid the whole-risk-episode regression by keeping the normal current64
anchor replay source intact, then adding only exact first-divergence rows from
the anchor risk-seed shards plus a very small same-seat local context window?

Implementation:

- `apply_risk_case_weights` now marks exact matches in `risk_case_matches`.
- `fh-mj-train-iql --risk-trace-filter-datasets` keeps the first `--data`
  source as the base replay dataset and filters later sources.
- `--risk-trace-context-radius N` keeps same-episode, same-seat rows whose
  `decision_index` is within `N` decisions of an exact match.
- Unit coverage checks exact context selection and the multi-dataset loader
  behavior.

Local validation:

```text
uv run --project ai pytest ai/tests/test_risk_filter.py ai/tests/test_iql.py ai/tests/test_model.py
result: 32 passed

uv run --project ai pytest ai/tests/test_model.py ai/tests/test_iql.py ai/tests/test_storage.py ai/tests/test_serving.py ai/tests/test_policies.py ai/tests/test_evaluate.py ai/tests/test_risk_filter.py ai/tests/test_paired_trace.py
result: 62 passed

uv run --project ai python -m py_compile ai/src/fh_mahjong_ai/scripts/train_iql.py ai/src/fh_mahjong_ai/risk_filter.py ai/src/fh_mahjong_ai/trainer.py ai/src/fh_mahjong_ai/model.py
result: passed

go test ./rules ./rlenv
result: passed
```

Remote validation:

```text
cd /root/fh-mahjong-risk-context
/root/.local/bin/uv run --project ai --extra dev pytest ai/tests/test_risk_filter.py ai/tests/test_iql.py ai/tests/test_model.py
result: 32 passed
```

Training:

```text
base data: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/data/selfplay-current-riskcontext-n64-npz
risk data: 17 anchor-only one-seed shards
output checkpoint: /root/fh-mahjong-runs/chongci-riskcontext-riskseeds-filtered-20260531-035442/checkpoints/iql_riskseed_anchor_filtered/epoch_001.pt
risk_trace_weight: 3.0
risk_trace_worst_delta_count: 40
risk_trace_filter_datasets: true
risk_trace_context_radius: 2
training MLflow run: 44791c3621184dcbb18ec87baae27ecc
final loss: 0.1313
```

Risk matching:

```text
base current64 dataset: 0 exact matches
anchor risk-seed filtered rows kept: 11 total
non-empty filtered shards: 8 of 17
matching mode: seed_seat_decision
```

The non-empty risk shards were:

```text
534000: 3 rows
534001: 1 row
534002: 2 rows
544003: 1 row
544004: 1 row
544008: 1 row
544009: 1 row
```

An initial evaluation was accidentally run with the short score config
`starting_score=2`, `bust_threshold=-2`, `max_hands=8`; that report is not
comparable to the historical selected-window gate and should not be used for a
promotion decision.

Comparable evaluation:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes: 44
max steps per episode: 8192
Chongci config: default starting_score=2000, bust_threshold=0, max_hands=50
candidate report: /root/fh-mahjong-runs/chongci-riskcontext-riskseeds-filtered-20260531-035442/reports/candidate_selected_windows_default_config.json
candidate MLflow run: f5ad40fcfcd646b0b62bd7f92e9e51a0
```

| Policy | Avg Reward | Positive Rate | Large-Loss Rate |
|--------|------------|---------------|-----------------|
| promoted anchor under new scalars | -0.1400 | 40.91% | 20.45% |
| scalar-only current64 epoch 1 | -0.1700 | 40.91% | 20.45% |
| anchor-only filtered first-divergence replay | -0.1700 | 40.91% | 20.45% |

Decision:

Rejected at selected-window screen. Exact filtered replay avoided the previous
anchor-only risk-seed large-loss regression, but it did not improve over the
scalar-only current64 checkpoint and still missed the promoted anchor by EV.

Interpretation:

This confirms the loader-level filtered replay plumbing works, but the signal is
too sparse: only 11 extra risk-context rows survived filtering. The next branch
needs either more exact matched risk rows from generated data, or a stronger
action-level objective on those rows. Simply adding the sparse rows with sample
weighting is not enough.

### All-Anchor Filtered First-Divergence Replay

Run:

```text
/root/fh-mahjong-runs/chongci-riskcontext-allanchor-filtered-20260531-150447
```

Question:

Does covering every seed from the dense paired trace improve filtered replay
enough to beat the promoted anchor? The previous filtered run used only 17
targeted anchor seed shards and kept 11 risk-context rows. This run generated
the 13 missing anchor shards and trained against all 30 trace seeds.

Additional data generation:

```text
generated missing anchor seeds:
534004 534006 534007
544000 544002 544005 544006
554000 554002 554003 554004 554008 554009
new generated shards: 13
```

Training:

```text
base data: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/data/selfplay-current-riskcontext-n64-npz
risk data: 30 all-anchor one-seed shards
output checkpoint: /root/fh-mahjong-runs/chongci-riskcontext-allanchor-filtered-20260531-150447/checkpoints/iql_allanchor_filtered/epoch_001.pt
risk_trace_weight: 3.0
risk_trace_worst_delta_count: 40
risk_trace_filter_datasets: true
risk_trace_context_radius: 2
training MLflow run: c15f54ac3a7c46deb2cb02aefde03de5
final loss: 0.1312
```

Risk matching:

```text
base current64 dataset: 0 exact matches
all-anchor filtered rows kept: 16 total
matching mode: seed_seat_decision
```

Evaluation:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes: 44
max steps per episode: 8192
Chongci config: default starting_score=2000, bust_threshold=0, max_hands=50
candidate report: /root/fh-mahjong-runs/chongci-riskcontext-allanchor-filtered-20260531-150447/reports/candidate_selected_windows.json
candidate MLflow run: fb34b342b1894457b752334a59af47f2
```

| Policy | Avg Reward | Positive Rate | Large-Loss Rate |
|--------|------------|---------------|-----------------|
| promoted anchor under new scalars | -0.1400 | 40.91% | 20.45% |
| anchor-only filtered replay, 17 seeds | -0.1700 | 40.91% | 20.45% |
| all-anchor filtered replay, 30 seeds | -0.1800 | 40.91% | 20.45% |

Decision:

Rejected at selected-window screen. Increasing seed coverage from 17 to 30 only
raised filtered rows from 11 to 16 and slightly worsened EV.

Interpretation:

This closes the simple "more trace seeds" version of filtered replay. The
limiting factor is not only unique seed coverage; it is that exact decision
matches remain too rare and the objective remains too weak when sampled through
the normal replay distribution. The next experiment should not spend more time
on the same filtered replay recipe. Use a stronger objective on exact rows,
change target-side risk learning, or collect repeated data specifically around
the exact matched decision states.

### All-Anchor Filtered Replay With Sparse-Row Oversampling

Run:

```text
/root/fh-mahjong-runs/chongci-riskcontext-allanchor-filtered-replayx-20260531-151817
```

Question:

Was the all-anchor filtered run failing because the exact matched rows were too
rarely sampled? This run reused the same 30 all-anchor risk-seed inputs, kept the
same filtered replay setup, and added `--pairwise-replay-multiplier 256` so the
sparse exact rows were repeated into an auxiliary replay source. No pairwise loss
was enabled; the multiplier was used as a sampling intervention for the matched
rows and their sample weights.

Training:

```text
base data: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/data/selfplay-current-riskcontext-n64-npz
risk data: 30 all-anchor one-seed shards
output checkpoint: /root/fh-mahjong-runs/chongci-riskcontext-allanchor-filtered-replayx-20260531-151817/checkpoints/iql_allanchor_filtered_replayx/epoch_001.pt
risk_trace_weight: 3.0
risk_trace_worst_delta_count: 40
risk_trace_filter_datasets: true
risk_trace_context_radius: 2
pairwise_replay_multiplier: 256
training MLflow run: b1c58e84cafd43a9817b5962c1d9c6ad
final loss: 0.1492
```

Sampling check:

The stronger-sampling setup worked mechanically. Training batches now exposed
the sparse rows:

```text
step 20: pairwise_count=8,  sample_weight=1.039
step 40: pairwise_count=19, sample_weight=1.050
step 60: pairwise_count=15, sample_weight=1.048
```

Evaluation:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes: 44
candidate report: /root/fh-mahjong-runs/chongci-riskcontext-allanchor-filtered-replayx-20260531-151817/reports/candidate_selected_windows.json
candidate MLflow run: 36aa6cb011a5479a8cdaa5eac8470059
```

| Policy | Avg Reward | Positive Rate | Large-Loss Rate |
|--------|------------|---------------|-----------------|
| promoted anchor under new scalars | -0.1400 | 40.91% | 20.45% |
| all-anchor filtered replay | -0.1800 | 40.91% | 20.45% |
| all-anchor filtered replay + sparse-row oversampling | -0.1800 | 40.91% | 20.45% |

Decision:

Rejected at selected-window screen.

Interpretation:

This distinguishes two failure modes. The previous run under-sampled exact rows;
this run fixed row exposure but still did not improve the policy. The filtered
replay target is not strong enough in this form. Stop this replay-only line and
move to target-side learning or a better state/action objective.

### Target-Side Large-Loss Auxiliary On All-Anchor Data

Run:

```text
/root/fh-mahjong-runs/chongci-targetrisk-aux-allanchor-20260531-162926
```

Question:

Can a target-side large-loss probability/severity auxiliary improve the policy
where replay-only first-divergence weighting failed? This run used the base
current64 dataset plus all 30 anchor risk-seed shards without risk filtering.
The auxiliary heads shared trunk gradients, so this was representation shaping,
not a detached diagnostic.

Training:

```text
base data: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/data/selfplay-current-riskcontext-n64-npz
risk data: 30 all-anchor one-seed shards, unfiltered
output checkpoint: /root/fh-mahjong-runs/chongci-targetrisk-aux-allanchor-20260531-162926/checkpoints/iql_aux_allanchor/epoch_001.pt
large_loss_threshold: -1.0
large_loss_aux_weight: 0.05
large_loss_severity_weight: 0.02
large_loss_aux_detach: false
training MLflow run: 1222eb29180b4a5484808eceb07c462a
final loss: 0.1624
```

Training check:

The auxiliary losses were active:

```text
step 20: ll_aux=0.5458, ll_sev=0.1169
step 40: ll_aux=0.5084, ll_sev=0.1057
step 80: ll_aux=0.5076, ll_sev=0.0804
```

Evaluation:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes: 44
candidate report: /root/fh-mahjong-runs/chongci-targetrisk-aux-allanchor-20260531-162926/reports/candidate_selected_windows.json
candidate MLflow run: db51c58f0f0343f5a2d19598e9ded404
```

| Policy | Avg Reward | Positive Rate | Large-Loss Rate |
|--------|------------|---------------|-----------------|
| promoted anchor under new scalars | -0.1400 | 40.91% | 20.45% |
| all-anchor filtered replay + oversampling | -0.1800 | 40.91% | 20.45% |
| all-anchor large-loss auxiliary | -0.1700 | 40.91% | 22.73% |

Decision:

Rejected at selected-window screen.

Interpretation:

The auxiliary target moved the policy differently from replay-only weighting,
but not in the right direction: EV improved versus the replay-only all-anchor
runs, while large-loss rate regressed. This suggests the current auxiliary
form is not enough as a promotion candidate. A lower-weight auxiliary or a
critic-side risk score may be worth testing, but the direct shared-gradient
all-anchor auxiliary is rejected.

### Lower-Weight Target-Side Large-Loss Auxiliary

Run:

```text
/root/fh-mahjong-runs/chongci-targetrisk-auxlow-allanchor-20260531-163427
```

Question:

Was the target-side auxiliary tail regression caused by excessive auxiliary
weight? This repeats the all-anchor auxiliary setup with lower coefficients.

Training:

```text
base data: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/data/selfplay-current-riskcontext-n64-npz
risk data: 30 all-anchor one-seed shards, unfiltered
output checkpoint: /root/fh-mahjong-runs/chongci-targetrisk-auxlow-allanchor-20260531-163427/checkpoints/iql_auxlow_allanchor/epoch_001.pt
large_loss_threshold: -1.0
large_loss_aux_weight: 0.02
large_loss_severity_weight: 0.005
large_loss_aux_detach: false
training MLflow run: b1bfc92969f440199300ae7ab48372ca
final loss: 0.1493
```

Evaluation:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes: 44
candidate report: /root/fh-mahjong-runs/chongci-targetrisk-auxlow-allanchor-20260531-163427/reports/candidate_selected_windows.json
candidate MLflow run: 58cf08c0a0624fae9736260a9eb50b80
```

| Policy | Avg Reward | Positive Rate | Large-Loss Rate |
|--------|------------|---------------|-----------------|
| promoted anchor under new scalars | -0.1400 | 40.91% | 20.45% |
| all-anchor large-loss auxiliary | -0.1700 | 40.91% | 22.73% |
| lower-weight all-anchor large-loss auxiliary | -0.1700 | 40.91% | 22.73% |

Decision:

Rejected at selected-window screen.

Interpretation:

Lowering the auxiliary coefficients did not change the selected-window behavior.
The shared-gradient large-loss auxiliary is not a useful next promotion path in
its current form.

### Large-Loss Auxiliary Calibration

Run:

```text
/root/fh-mahjong-runs/chongci-risk-calibration-terminal-20260531-164248
```

Question:

Can the trained large-loss auxiliary head be used as a risk guard even though
the policy checkpoint did not promote?

Implementation:

`fh-mj-reward-calibration --large-loss-threshold` now reports large-loss
probability/severity calibration. Q/value calibration still uses discounted
targets, but large-loss calibration uses the undiscounted terminal return,
matching how the auxiliary head was trained.

Validation:

```text
uv run --project ai pytest ai/tests/test_reward_calibration.py ai/tests/test_model.py
result: 13 passed

uv run --project ai python -m py_compile ai/src/fh_mahjong_ai/reward_calibration.py ai/src/fh_mahjong_ai/scripts/reward_calibration.py
result: passed

remote: /root/.local/bin/uv run --project ai --extra dev pytest ai/tests/test_reward_calibration.py
result: 3 passed
```

Reports:

```text
data: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/data/selfplay-current-riskcontext-n64-npz
threshold: -1.0 terminal return
aux report: /root/fh-mahjong-runs/chongci-risk-calibration-terminal-20260531-164248/reports/aux_allanchor_current64.json
auxlow report: /root/fh-mahjong-runs/chongci-risk-calibration-terminal-20260531-164248/reports/auxlow_allanchor_current64.json
```

| Checkpoint | Large-Loss Rate | Brier | AUC | Avg P(LL) | Positive Mean P(LL) | Negative Mean P(LL) | Severity MAE |
|------------|-----------------|-------|-----|-----------|---------------------|---------------------|--------------|
| all-anchor auxiliary | 15.69% | 0.1511 | 0.5021 | 0.2265 | 0.2274 | 0.2263 | 0.3294 |
| lower-weight all-anchor auxiliary | 15.69% | 0.2541 | 0.4936 | 0.4827 | 0.4803 | 0.4831 | 0.4534 |

Risk bands:

For the all-anchor auxiliary checkpoint, the large-loss rate was effectively
flat across predicted probability bands:

```text
0.00-0.25: 15.63%
0.25-0.50: 15.77%
0.50-0.75: 15.60%
0.75-1.00: 0.00% over only 2 samples
```

Decision:

Do not use the current large-loss auxiliary head as a serving-time risk guard.

Interpretation:

The auxiliary head is not ranking large-loss states. It learned a probability
scale, but that probability does not separate large-loss and non-large-loss
transitions. This explains why the target-side auxiliary runs did not improve
the policy. The next useful direction should change the target definition or
the input/history available to the risk head, not simply adjust auxiliary
coefficients.

## Action-Conditioned Risk Critic V1 Calibration

Date: 2026-05-31

Run:

```text
/root/fh-mahjong-runs/chongci-actionrisk-critic-allanchor-20260531-211136
```

Question:

Does changing the large-loss auxiliary from a state-only head to a 204-action
risk critic produce a calibrated offline risk signal before adding new visible
match-history inputs?

Implementation:

- `PolicyValueNet.action_risk_predictions()` predicts one large-loss logit and
  one severity value per catalog action.
- IQL gathers the risk prediction at the observed dataset `action_id`.
- Calibration can force the action-conditioned path with
  `fh-mj-reward-calibration --large-loss-risk-mode action`.
- The deployed policy path is unchanged.

Training:

```text
checkpoint: /root/fh-mahjong-runs/chongci-actionrisk-critic-allanchor-20260531-211136/checkpoints/iql_actionrisk_allanchor/epoch_001.pt
base data: /root/fh-mahjong-runs/chongci-riskcontext-current64-20260530-153534/data/selfplay-current-riskcontext-n64-npz
risk data: 30 all-anchor one-seed shards
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
epochs: 1
batch_size: 2048
learning_rate: 0.000005
policy_weight: 0.25
bc_weight: 3.0
large_loss_threshold: -1.0
large_loss_aux_weight: 0.05
large_loss_severity_weight: 0.02
mlflow training run: 67359bf189a145abbe90720c6783b613
```

Training logs confirmed the action-risk losses were active:

```text
step 20: ll_aux=1.8510 ll_sev=0.5253
step 40: ll_aux=1.7142 ll_sev=0.5086
step 60: ll_aux=1.8007 ll_sev=0.4799
step 80: ll_aux=1.7854 ll_sev=0.4338
final loss: 0.2320
```

Calibration:

```text
report: /root/fh-mahjong-runs/chongci-actionrisk-critic-allanchor-20260531-211136/reports/actionrisk_current64_calibration.json
mlflow calibration run: 08a09e16ee8d4dea86ed1c84aa2fb4d1
transitions: 131842
Q MAE: 0.1290
Q RMSE: 0.2032
Q bias: -0.0035
Q corr: 0.0055
value MAE: 0.0743
large-loss rate: 15.69%
large-loss Brier: 0.3329
large-loss AUC: 0.4998
large-loss severity MAE: 0.7600
```

Decision:

Reject at calibration gate. Do not run selected-window online evaluation or a
serving-time guard from this checkpoint.

Interpretation:

The action-conditioned plumbing is mechanically correct and the auxiliary loss
is active, but the learned risk scores are still near-random without richer
visible context. This confirms the next change should be input/target quality:
add visible Chongci match-history and score-pressure features before retraining
the action-risk critic. More coefficient sweeps on the current input shape are
low-value.

## Visible 58-Scalar Action-Risk Critic Calibration

Date: 2026-05-31

Branch:

```text
codex/chongci-visible-risk-scalars
```

Run:

```text
/root/fh-mahjong-runs/chongci-visible58-actionrisk-20260531-215255
```

Question:

Does adding visible Chongci match-history and score-pressure scalars improve
the action-conditioned large-loss risk critic enough to pass offline
calibration?

Implementation:

The observation scalar count increased from `50` to `58`. The new scalars are
visible-only and are derived from public scores, hand number, public discards,
open melds, flowers, and the Chongci config:

| Scalar | Meaning |
|--------|---------|
| 50 | self score ratio versus starting score |
| 51 | signed net score progress versus starting score |
| 52 | signed score gap versus right opponent |
| 53 | signed score gap versus across opponent |
| 54 | signed score gap versus left opponent |
| 55 | next-rank pressure, score needed to catch the nearest higher player |
| 56 | lower-rank cushion, margin over the nearest lower player |
| 57 | max opponent public current-hand threat |

Old checkpoints still load because the scalar encoder weight migration pads
missing scalar columns with zero initialization. Older 42/50-scalar datasets can
still be sampled with the model path because scalar inputs are padded at
inference/training time, but this experiment generated fresh 58-scalar shards.

Validation:

```text
local: go test ./rlenv ./rules
local: uv run --project ai pytest ai/tests/test_model.py ai/tests/test_iql.py ai/tests/test_storage.py ai/tests/test_serving.py ai/tests/test_policies.py ai/tests/test_paired_trace.py ai/tests/test_reward_calibration.py
remote: go test ./rlenv ./rules
remote: uv run --project ai --extra dev pytest ai/tests/test_model.py ai/tests/test_iql.py ai/tests/test_storage.py ai/tests/test_serving.py ai/tests/test_paired_trace.py ai/tests/test_reward_calibration.py
remote: go build -buildmode=c-shared -o build/libfh_mahjong_bridge.so ./cmd/rlbridge
```

Remote data:

```text
train data: /root/fh-mahjong-runs/chongci-visible58-actionrisk-20260531-215255/data/anchor-visible58-train64-npz
train episodes: 64
train transitions: 131612
train seeds: 640000-640063
calibration data: /root/fh-mahjong-runs/chongci-visible58-actionrisk-20260531-215255/data/anchor-visible58-calib16-npz
calibration episodes: 16
calibration transitions: 31448
calibration seeds: 650000-650015
scalar shape: 58
policy source: promoted Chongci anchor on all four seats
```

Training:

```text
checkpoint: /root/fh-mahjong-runs/chongci-visible58-actionrisk-20260531-215255/checkpoints/iql_visible58_actionrisk/epoch_001.pt
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
epochs: 1
batch_size: 2048
learning_rate: 0.000005
policy_weight: 0.25
bc_weight: 3.0
large_loss_threshold: -1.0
large_loss_aux_weight: 0.05
large_loss_severity_weight: 0.02
mlflow training run: a1d4cea1992d4ebaa8ce2be5ebca4bfa
```

Training logs confirmed the action-risk loss remained active:

```text
step 20: ll_aux=1.7417 ll_sev=0.8766
step 40: ll_aux=1.7591 ll_sev=0.8336
step 60: ll_aux=1.8483 ll_sev=0.8490
final loss: 0.2638
```

Independent calibration:

```text
report: /root/fh-mahjong-runs/chongci-visible58-actionrisk-20260531-215255/reports/visible58_actionrisk_calib16.json
mlflow calibration run: a5c60c88e2374282a3b71bc190f6ad20
transitions: 31448
Q MAE: 0.1345
Q RMSE: 0.2170
Q bias: -0.0021
Q corr: 0.0043
value MAE: 0.0787
large-loss rate: 14.54%
large-loss Brier: 0.3114
large-loss AUC: 0.5096
large-loss positive mean probability: 0.4693
large-loss negative mean probability: 0.4596
large-loss severity MAE: 1.1919
```

Risk bands:

```text
0.00-0.25: 13.79% large-loss rate over 9723 samples
0.25-0.50: 14.78% large-loss rate over 7485 samples
0.50-0.75: 15.12% large-loss rate over 7268 samples
0.75-1.00: 14.73% large-loss rate over 6972 samples
```

Decision:

Reject at calibration gate. Do not run selected-window online evaluation or a
serving-time guard from this checkpoint.

Interpretation:

The new visible score-pressure scalars slightly improved probability Brier
versus the no-history action-risk run (`0.3114` vs `0.3329`), and the middle
risk bands are weakly ordered. However, AUC is still effectively random and the
positive/negative mean probability gap is only about `0.0097`, far below the
`0.05` calibration target. The next experiment needs a stronger risk-learning
setup, not guarded serving: larger and more diverse large-loss coverage,
balanced risk-only training, or a critic-side target that predicts score-delta
tail value more directly.

## Balanced Action-Risk Critic Calibration

Date: 2026-05-31

Branch:

```text
codex/chongci-balanced-risk-critic
```

Run:

```text
/root/fh-mahjong-runs/chongci-balanced-actionrisk-20260531-221155
```

Question:

Does a direct balanced positive/negative action-risk objective learn a better
large-loss ranking than the IQL side-loss objective?

Implementation:

Added `fh-mj-train-action-risk`, a calibration-only trainer for the
action-conditioned risk heads. It samples balanced batches from saved transition
shards:

```text
positive rows: terminal match return <= -1.0 for the acting seat
negative rows: terminal match return > -1.0 for the acting seat
loss: BCE(risk_logit(s, dataset_action), label)
      + severity_weight * SmoothL1(risk_severity(s, dataset_action), severity)
```

This path does not promote a serving policy. It exists to learn and calibrate
`P(large loss | visible state, action)` before any guard is allowed.

Training:

```text
data: /root/fh-mahjong-runs/chongci-visible58-actionrisk-20260531-215255/data/anchor-visible58-train64-npz
checkpoint: /root/fh-mahjong-runs/chongci-balanced-actionrisk-20260531-221155/checkpoints/action_risk_balanced/epoch_003.pt
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
epochs: 3
batch_size: 2048
learning_rate: 0.00002
positive_fraction: 0.5
severity_weight: 0.05
threshold: -1.0
mlflow training run: d5fe0317e0ae4d6d850c2d3dcc02aad4
```

Training logs showed the balanced objective was active and the severity error
improved:

```text
epoch 1 step 1:  loss=1.1460 prob=1.1110 sev=0.7010 p_pos=0.546 p_neg=0.547
epoch 2 step 64: loss=0.8054 prob=0.7914 sev=0.2800 p_pos=0.528 p_neg=0.517
epoch 3 step 64: loss=0.7820 prob=0.7706 sev=0.2267 p_pos=0.512 p_neg=0.506
```

Independent calibration:

```text
report: /root/fh-mahjong-runs/chongci-balanced-actionrisk-20260531-221155/reports/balanced_visible58_actionrisk_calib16.json
calibration data: /root/fh-mahjong-runs/chongci-visible58-actionrisk-20260531-215255/data/anchor-visible58-calib16-npz
transitions: 31448
large-loss rate: 14.54%
large-loss Brier: 0.2876
large-loss AUC: 0.4990
large-loss positive mean probability: 0.5051
large-loss negative mean probability: 0.5059
large-loss severity MAE: 0.5698
```

Risk bands:

```text
0.00-0.25: 14.28% large-loss rate over 2816 samples
0.25-0.50: 14.52% large-loss rate over 12359 samples
0.50-0.75: 14.91% large-loss rate over 13337 samples
0.75-1.00: 13.25% large-loss rate over 2936 samples
```

Decision:

Reject at calibration gate. Do not run selected-window online evaluation or a
serving-time guard from this checkpoint.

Interpretation:

Balanced training improved probability scale and severity error versus the IQL
auxiliary run, but it did not improve ranking. The positive and negative mean
probabilities are effectively identical, and AUC is still random. This means
the current observed-action terminal large-loss label is too weak/noisy for
ranking dangerous decisions by itself. The next useful direction is not another
balanced BCE sweep; it should add better supervision, such as paired
counterfactual/divergence labels, per-action score-delta targets, or explicit
large-loss-enriched data generated around the known failing seed windows.

## Current Conclusions

1. The current promoted Chongci checkpoint remains the best serving candidate.
2. More self-play data alone is not sufficient.
3. Strong downside shaping can reduce large losses but can also hurt EV.
4. Conservative anchoring can preserve or improve EV, but may trade off
   large-loss rate.
5. The last confirmed blocker was evaluation reliability; the focused audit is
   deterministic after fixing per-hand wall seeds and same-priority interrupt
   tie-breaking.
6. The model architecture is adequate for the current pipeline; deeper models
   should wait until gates are stable.
7. Mean reward remains the primary metric; positive-rate and large-loss rate are
   guardrails.
8. Conservative epoch 1 passed deterministic repeated evaluation for EV, but
   failed the tail-risk guardrail, so it should not be promoted yet.
9. A small tail-risk penalty (`large_loss_penalty=0.1`) did not change the
   candidate behavior on the repeated gate.
10. A moderate tail-risk penalty (`large_loss_penalty=0.25`) also did not change
    the candidate behavior on the repeated gate.
11. A corrected policy-head Q-margin guard improves over the raw candidate on
    selected risk windows but still trails the anchor, so it is not worth a full
    promotion gate yet.
12. High-risk transition weighting is implemented and active, but weight `3.0`
    improved selected-window EV/positive rate without reducing large-loss rate.
13. Stronger high-risk weighting (`5.0`) with lower policy drift reduced the
    selected-window large-loss rate from `27.27%` to `25.00%`, but still trailed
    the anchor and regressed EV versus weight `3.0`.
14. The stack now records large-loss seed lists and first-divergence risk cases
    directly, and IQL can consume paired trace reports for targeted sample
    weighting when datasets preserve or can map the relevant seed metadata.
15. A remote smoke run confirmed that `--risk-trace-report` produces non-zero
    exact `seed + seat + decision_index` matches on new shards, so targeted
    divergence-state training is now testable.
16. Risk-trace candidate v1 improved strongly over the raw conservative
    candidate but still failed to beat the promoted anchor on selected risk
    windows, so it is rejected before the full repeated gate.
17. Dense risk-trace coverage increased exact matched cases from single digits
    to 28 cases, but still did not beat the promoted anchor; the bottleneck is
    now feature/target quality more than risk-case sampling density.
18. Pairwise policy-margin training is implemented and validated, but the first
    pairwise runs showed that the promoted-anchor-initialized policy already
    ranks anchor actions over candidate actions on the sampled divergence rows;
    this did not improve promotion metrics.
19. Pairwise Q-margin training is also implemented and validated, but the first
    Q-side run worsened EV and large-loss rate, so paired-trace preference
    losses should pause until stronger risk-context features or target signals
    are added.
20. Filtered first-divergence replay is implemented and validated. The first
    anchor-only filtered run kept only 11 extra risk-context rows, matched the
    scalar-only current64 candidate, and still missed the promoted anchor; the
    bottleneck is now exact-match volume or a stronger objective on those rows.
21. Expanding filtered replay to all 30 dense-trace seeds kept only 16 rows and
    worsened EV to `-0.18`; do not repeat this filtered replay recipe without a
    stronger sampling or objective change.
22. Sparse-row oversampling made exact rows visible in training batches but did
    not improve selected-window reward, so the filtered replay objective itself
    is exhausted for now.
23. Shared-gradient large-loss auxiliary training on all-anchor data was active
    but regressed selected-window large-loss rate, so the first target-side
    version is also rejected.
24. Lowering the large-loss auxiliary coefficients reproduced the same rejected
    selected-window result.
25. Large-loss auxiliary calibration shows near-random AUC and flat risk bands,
    so the current auxiliary head should not be used as a guard.
26. The next risk-learning direction is documented in
    `worklog/rl-experiment/chongci-risk-target-design.md`: add visible match-history
    inputs and train an action-conditioned critic-side risk head before trying
    any serving-time guard.
27. Action-conditioned risk heads are now implemented in the Python model and
    IQL auxiliary loss path. The next required evidence is calibration, not
    online serving.
28. The first action-conditioned calibration-only run was active but failed the
    calibration gate (`large-loss AUC 0.4998`, Brier `0.3329`), so it should
    not be evaluated online. The next required change is visible match-history
    and score-pressure input, not another auxiliary coefficient sweep.
29. The 58-scalar visible match-history/action-risk run also failed calibration
    (`large-loss AUC 0.5096`, Brier `0.3114`). The added public context helped
    Brier slightly but did not make risk rankings reliable enough for guarded
    serving.
30. Balanced action-risk training improved scale/severity (`Brier 0.2876`,
    `severity MAE 0.5698`) but still failed ranking (`large-loss AUC 0.4990`).
    Do not repeat balanced BCE alone; the next risk target needs stronger
    supervision or large-loss-enriched/counterfactual data.

## Recommended Next Experiments

### Step 1: Build Action-Conditioned Risk Critic Inputs

Use the design in [Chongci Risk Target And Input Design](./chongci-risk-target-design.md).

The next implementation should not repeat first-divergence replay weighting or
large-loss auxiliary coefficient sweeps. The next useful target is:

```text
risk_logit(s, a)    = P(terminal_match_return <= threshold | visible state, action)
risk_severity(s, a) = E[max(threshold - terminal_match_return, 0) | visible state, action]
```

Train it only on observed dataset actions first, and require offline calibration
before any guarded online evaluation.

Immediate work:

- keep the 58-scalar visible Chongci context,
- add stronger risk supervision: paired counterfactual labels, per-action
  score-delta targets, or large-loss-enriched data from known failing windows,
- only test a top-policy-candidate risk guard if offline calibration passes.

### Step 2: Add Risk Diagnostics To Evaluation Reports

Add report fields that help explain candidate failures without manual JSON
inspection:

- large-loss seed list,
- worst reward deltas,
- first divergence action labels,
- first divergence scalar snapshot,
- policy-choice source rates for guarded policies,
- exact checkpoint path and model config.

### Step 3: Explore Tail-Loss Without EV Regression

Possible ablations:

```text
lr: 5e-6 or lower
bc_weight: 2.0 to 4.0
policy_weight: 0.25 to 0.5
large_loss_penalty: small, only after determinism audit
cql_weight: 0.0 to 0.02
```

Do not run a broad grid until evaluation noise is controlled.

### Step 4: Consider Stronger Match-Level Features

Only after evaluation stability:

- richer score-potential features,
- placement/rank value auxiliary,
- opponent pressure and bust-risk auxiliary,
- history features for repeated hand context.

### Experiment: Paired Action-Risk Delta Supervision

Run:

`/root/fh-mahjong-runs/chongci-paired-actionrisk-delta-20260601-224151`

Question:

Can a separate action-conditioned risk critic learn more useful Chongci tail-risk
signals from paired first-divergence reports than from plain terminal large-loss
BCE alone?

Data:

Use visible 58-scalar Chongci transition shards plus paired trace reports whose
seed windows match the dataset `episode_index` mapping through
`--paired-dataset-start-seed`. The paired trace contributes anchor-preferred and
candidate-avoided action ids at the exact first divergence row.

Training:

`train_action_risk.py` now supports `--paired-trace-report`, reward-delta
targets, `--paired-margin-weight`, and `--paired-severity-weight`. The observed
action still trains large-loss probability/severity; paired rows additionally
force the worse candidate action to rank riskier than the anchor action and fit
the score-gap severity target.

First run:

```text
init checkpoint: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
general data: /root/fh-mahjong-runs/chongci-visible58-actionrisk-20260531-215255/data/anchor-visible58-train64-npz
paired data:
  /root/fh-mahjong-runs/chongci-risktrace-dense-v2-20260530-014516/data/anchor-risk-seed-534000-n10-npz
  /root/fh-mahjong-runs/chongci-risktrace-dense-v2-20260530-014516/data/anchor-risk-seed-544000-n10-npz
  /root/fh-mahjong-runs/chongci-risktrace-dense-v2-20260530-014516/data/anchor-risk-seed-554000-n10-npz
trace report: /root/fh-mahjong-runs/chongci-risktrace-dense-v2-20260530-014516/reports/anchor_vs_raw_candidate_gate_windows_trace.json
epochs: 1
steps_per_epoch: 100
batch_size: 2048
lr: 5e-5
paired_margin_weight: 0.5
paired_severity_weight: 0.25
paired_batch_fraction: 0.25
MLflow training run: ff981d1bf5fd428abdf24a39cc376177
MLflow calibration run: 5c6e3538a3394f2181ad436d7c5fd479
```

Evaluation:

First run offline action-risk calibration. Required diagnostics: nonzero
`matched_cases`, nonzero `paired_transitions`, probability Brier/AUC, severity
error, and paired margin/severity losses in the training report. Do not use this
critic for guarded serving or duplicate evaluation until calibration improves
over the plain action-risk critic.

Result:

```text
matched cases:
  start_seed 534000: 7 matched, 5 paired transitions, max reward-delta 0.5500
  start_seed 544000: 6 matched, 4 paired transitions, max reward-delta 0.1280
  start_seed 554000: 1 matched, 1 paired transition, max reward-delta 0.0920
total paired transitions: 10

training final:
  loss: 0.6008
  probability_loss: 0.5774
  severity_loss: 0.1169
  paired_margin_loss: 0.0000
  paired_severity_loss: 0.000025
  paired_delta_mae: 0.00649

independent calib16:
  large_loss_rate: 0.1454
  AUC: 0.4983
  Brier: 0.2809
  positive_mean: 0.4949
  negative_mean: 0.4957
  severity_MAE: 0.4369

previous plain visible58 action-risk calibration:
  AUC: 0.5096
  Brier: 0.3114
  positive_mean: 0.4693
  negative_mean: 0.4596
  severity_MAE: 1.1919
```

Decision:

Rejected for guarded serving/evaluation. The paired target improved severity
scale but did not improve risk ranking; AUC fell below the plain visible58
action-risk run and positive examples scored slightly lower than negatives.

Interpretation:

This is the next stronger supervision ingredient after plain large-loss BCE,
dense risk-trace replay weighting, and policy/Q pairwise margin losses failed to
reduce tail risk reliably. It targets the risk critic directly rather than
changing the deployed policy head during training. The result suggests the
available first-divergence paired labels are too sparse for a reliable
action-risk ranker by themselves. The next attempt needs either substantially
more matched counterfactual rows or a different target, such as explicit
history-aware state risk and match-score trajectory features, before any serving
guard should be retried.

### Experiment: Larger Counterfactual Rows Plus Score-Pressure Risk Target

Run:

`/root/fh-mahjong-runs/chongci-large-counterfactual-scorepressure-20260601-225427`

Question:

Can a larger paired-trace/data window plus a visible match-pressure risk target
produce a better action-risk critic than terminal large-loss BCE or sparse
paired reward-delta labels?

Data:

The remote job is generating fresh anchor transition shards for three new
50-seed windows:

```text
564000:50
574000:50
584000:50
```

It also runs a paired trace over the same windows and all four seats, for
`150 seeds x 4 seats = 600` paired episodes. This should produce substantially
more exact `seed/seat/decision_index` matches than the previous 30-seed /
120-pair trace.

Training:

`train_action_risk.py` now has:

```text
--target-mode terminal
--target-mode score_pressure
--score-pressure-threshold
--score-pressure-weight
```

`score_pressure` keeps terminal large-loss positives, but also marks visible
Chongci pressure states as risky when final reward is non-positive and the
visible match-pressure score is high. The pressure score uses only deployed
visible scalars:

```text
hand_progress
leader_pressure
large_loss_margin
self_bust_margin
opponent_large_loss_pressure
public_threat
```

This is a risk-critic diagnostic target, not a policy-promotion objective.

Evaluation:

The remote script will:

1. rebuild `build/libfh_mahjong_bridge.so`,
2. generate the three matched anchor shards,
3. run the 600-pair trace,
4. write `reports/match_check.json`,
5. train one score-pressure action-risk critic,
6. calibrate it on the independent visible58 `calib16` shard.

Decision:

Rejected for guarded serving/evaluation.

Interpretation:

This branch deliberately changes the risk target instead of repeating another
pairwise-margin or replay-weighting sweep. Promotion is not allowed from this
run alone; the first pass only decides whether the risk critic has usable
independent calibration.

Result:

```text
data:
  564000:50 anchor shard: 100,781 transitions
  574000:50 anchor shard: 102,028 transitions
  584000:50 anchor shard: 102,456 transitions

paired trace:
  pairs: 600
  divergence_rate: 71.83%
  candidate_better_rate: 21.33%
  mean_delta: +0.0050

match check:
  risk_cases: 292
  exact matched cases: 60
  paired training transitions: 28
  max pairwise reward delta: 0.7180

training final:
  loss: 0.6208
  probability_loss: 0.5953
  severity_loss: 0.1279
  paired_margin_loss: 0.0000
  paired_delta_mae: 0.00403

independent calib16:
  AUC: 0.5040
  Brier: 0.2753
  positive_mean: 0.4950
  negative_mean: 0.4926
  severity_MAE: 0.4212
```

The larger matched dataset improved over the previous paired-delta critic
(`AUC 0.4983`, `Brier 0.2809`, `severity_MAE 0.4369`), but still did not beat
the older plain visible58 action-risk ranker (`AUC 0.5096`). Do not use this
critic for a serving guard. A small score-pressure threshold/weight sweep is
allowed because it reuses the already-generated 600-pair data; do not generate
more paired data until the target itself proves useful.

### Experiment: Score-Pressure Target Sweep

Run:

`/root/fh-mahjong-runs/chongci-scorepressure-sweep-20260602-010025`

Question:

Can threshold/weight tuning of the score-pressure action-risk target beat the
plain visible58 action-risk critic on independent large-loss ranking?

Data:

Reused the larger counterfactual run:

```text
/root/fh-mahjong-runs/chongci-large-counterfactual-scorepressure-20260601-225427
```

No new paired data was generated.

Result:

```text
variant              AUC     Brier   pos_mean  neg_mean  severity_MAE
scorep_t050_w050     0.5027  0.2767  0.4971    0.4956    0.4023
scorep_t060_w100     0.5081  0.2728  0.4924    0.4879    0.4441
scorep_t070_w050     0.4977  0.2706  0.4839    0.4863    0.4628
```

Decision:

Rejected for guarded serving/evaluation.

Interpretation:

The best sweep result, `scorep_t060_w100`, improved over the untuned
score-pressure run (`AUC 0.5040`) but still did not beat the older plain
visible58 action-risk critic (`AUC 0.5096`). This closes simple scalar
score-pressure target tuning for now. The next risk target should not be another
threshold/weight sweep; it needs either action-family-specific calibration,
later-trajectory labels, or a separate dataset split designed for tail-risk
ranking rather than reusing the same anchor-only calibration shard.

### Experiment: Action-Family Large-Loss Calibration Breakdown

Run:

Used the best score-pressure sweep checkpoint:

```text
/root/fh-mahjong-runs/chongci-scorepressure-sweep-20260602-010025/checkpoints/scorep_t060_w100/epoch_001.pt
```

Question:

Is poor action-risk calibration global, or concentrated in specific decision
families?

Implementation:

`reward_calibration.py` now includes
`large_loss_calibration.by_action_family`, with per-family count, positive
count, large-loss rate, probability AUC/Brier, and severity error.

Result:

```text
family   count   pos   rate    AUC     Brier   severity_MAE
chii     1,249   201   0.1609  0.5124  0.2650  0.6344
discard 24,775  3,622 0.1462  0.5052  0.2772  0.4371
kan      108     18    0.1667  0.5636  0.2785  0.8630
pass     3,620   538   0.1486  0.5159  0.2551  0.4076
pon      936     118   0.1261  0.5174  0.2578  0.5324
win      759     76    0.1001  0.5316  0.2448  0.3667
```

Decision:

Keep the reporting change. Do not promote or guard from this checkpoint.

Interpretation:

The calibration weakness is mainly a discard-scale problem because discard rows
dominate the dataset and still have only `AUC 0.5052`. Smaller action families
look somewhat better, but their sample counts are too small to justify a serving
guard. The next target should focus on discard-specific later-trajectory labels
or a more balanced calibration split, not global scalar pressure tuning.

### Experiment: Discard Later-Trajectory Pressure Target

Run:

`/root/fh-mahjong-runs/chongci-discard-later-pressure-20260602-101602`

Question:

Can the action-risk critic learn a more useful discard risk signal by labeling
discard actions whose same-seat future trajectory enters visible Chongci
pressure, instead of expanding risk labels globally?

Implementation:

`train_action_risk.py` now supports:

```text
--target-mode discard_later_pressure
--discard-later-window
--discard-later-pressure-threshold
--discard-later-weight
```

The target keeps terminal large-loss positives for all action families. It adds
extra positives only when:

```text
action family = discard
final same-seat reward <= 0
future same-seat Chongci score pressure >= threshold
```

Future pressure is computed inside the same `episode_index + seat` trajectory,
ordered by `decision_indices` when present and falling back to row order for
older shards.

Decision:

Rejected for guarded serving/evaluation.

Interpretation:

This is the first post-score-pressure target that directly follows the
action-family calibration result. It improved severity calibration, but it did
not improve probability ranking, especially for the discard family.

Training:

```text
target_mode: discard_later_pressure
discard_later_window: 4
discard_later_pressure_threshold: 0.6
discard_later_weight: 0.5
steps_per_epoch: 150
transitions: 436,877
positive_transitions: 135,229
positive_rate: 0.3095
paired_transitions: 28
```

Independent calib16 result:

```text
variant                  AUC     Brier   pos_mean  neg_mean  severity_MAE
discard_later_w4_t060    0.5041  0.2793  0.4922    0.4892    0.3466
```

Action-family calibration:

```text
family   count   pos   rate    AUC     Brier   severity_MAE
chii     1,249   201   0.1609  0.4858  0.2166  0.4909
discard 24,775  3,622 0.1462  0.5003  0.3041  0.3358
kan      108     18    0.1667  0.5414  0.2859  0.7439
pass     3,620   538   0.1486  0.5225  0.1746  0.3244
pon      936     118   0.1261  0.4954  0.2258  0.4939
win      759     76    0.1001  0.5668  0.1352  0.3298
```

The result is better on severity error than the score-pressure sweep, but worse
on the ranking metric that matters for a guard. Discard probability is almost
flat (`positive_mean 0.5280`, `negative_mean 0.5278`), so this target should not
be promoted. The next useful branch should avoid more hand-built pressure
labels and instead create a supervised target from actual later trajectory
events: for example "this discard is the first discard before a future deal-in,
bust, or large-loss transition" using explicit outcome/trace events rather than
scalar pressure proxies.

### Experiment: Discard Future-Outcome Target

Run:

`/root/fh-mahjong-runs/chongci-discard-future-outcome-20260602-215612`

Question:

Can the action-risk critic rank risky discards better when labels come from
actual future terminal events instead of visible pressure proxies?

Implementation:

`train_action_risk.py` now supports:

```text
--target-mode discard_future_outcome
--discard-outcome-window
--discard-outcome-weight
```

The target keeps terminal large-loss positives for all action families. It adds
extra positives only to recent same-seat discard actions before actual bad
terminal outcomes:

```text
terminal_discarder_seat == seat and final reward <= 0
or final reward <= large-loss threshold
```

Within each `episode_index + seat` trajectory, rows are ordered by
`decision_indices` when present. `--discard-outcome-window` selects the most
recent discard actions before the terminal event, so the label is more localized
than marking every action in a bad episode.

Decision:

Rejected for guarded serving/evaluation.

Interpretation:

This is the replacement for the rejected `discard_later_pressure` proxy target.
It used actual terminal outcome fields instead of pressure proxies, but it made
large-loss probability ranking worse.

Training:

```text
target_mode: discard_future_outcome
discard_outcome_window: 4
discard_outcome_weight: 1.0
steps_per_epoch: 150
transitions: 436,877
positive_transitions: 73,169
positive_rate: 0.1675
paired_transitions: 28
```

Independent calib16 result:

```text
variant              AUC     Brier   pos_mean  neg_mean  severity_MAE
discard_outcome_w4   0.4983  0.2687  0.4811    0.4826    0.4097
```

Action-family calibration:

```text
family   count   pos   rate    AUC     Brier   severity_MAE
chii     1,249   201   0.1609  0.4920  0.2783  0.4772
discard 24,775  3,622 0.1462  0.4953  0.2729  0.3850
kan      108     18    0.1667  0.6043  0.2482  0.7569
pass     3,620   538   0.1486  0.4924  0.2541  0.5348
pon      936     118   0.1261  0.5541  0.2410  0.5831
win      759     76    0.1001  0.5361  0.2231  0.2458
```

Discard ranking stayed below random (`AUC 0.4953`), and overall positives
scored slightly lower than negatives. This target should not be promoted. The
likely issue is that terminal-event labels still do not identify the causal
discard; they only select recent discards in bad episodes. The next target needs
stronger counterfactual information, such as paired same-state action labels,
or a separate supervised dataset that captures explicit deal-in-danger labels
from visible opponent waits rather than final outcome alone.

### Experiment: Paired Counterfactual Supervision Coverage

Run:

Coverage report:

`/root/fh-mahjong-runs/chongci-large-counterfactual-scorepressure-20260601-225427/reports/counterfactual_supervision_summary.json`

Training run:

`/root/fh-mahjong-runs/chongci-counterfactual-actionrisk-20260602-220355`

Question:

Do the existing paired traces contain enough explicit same-state preferred /
avoided action supervision, especially for discard and deal-in cases, to justify
another training run?

Implementation:

`paired_trace.py` now adds `summary.counterfactual_supervision`. It converts
each first-divergence pair with different final rewards into:

```text
preferred action = action from higher-reward policy
avoided action = action from lower-reward policy
tags = worse_reward, avoided_deal_in, new_deal_in, avoided_large_loss, new_large_loss
```

The summary reports preferred/avoided action-family counts, high-risk avoided
families, reward-gap statistics, and sample high-risk cases.

Decision:

Rejected for guarded serving/evaluation.

Interpretation:

Coverage was better than the previous large-loss/worst-delta loader but still
sparse at the matched training-row level.

Counterfactual coverage from the existing 600-pair trace:

```text
labeled_pairs: 255
high_risk_labeled_pairs: 47
avoided discard labels: 229
high-risk avoided discard labels: 42
tag_counts:
  worse_reward: 255
  avoided_large_loss: 47
  new_large_loss: 19
```

Matched training rows with `--paired-trace-counterfactual-labels` and
`--paired-trace-min-reward-gap 0.05`:

```text
cases: 187
matched pairwise transitions: 49
mean pairwise reward delta: 0.3415
max pairwise reward delta: 1.4090
```

Training:

```text
target_mode: terminal
paired_trace_counterfactual_labels: true
paired_trace_min_reward_gap: 0.05
paired_margin_weight: 1.0
paired_severity_weight: 0.5
paired_batch_fraction: 0.5
steps_per_epoch: 150
transitions: 436,877
positive_transitions: 72,858
paired_transitions: 50
```

Independent calib16 result:

```text
variant                 AUC     Brier   pos_mean  neg_mean  severity_MAE
counterfactual_gap005   0.5066  0.2758  0.4795    0.4755    0.3516
```

Action-family calibration:

```text
family   count   pos   rate    AUC     Brier   severity_MAE
chii     1,249   201   0.1609  0.4995  0.2916  0.4486
discard 24,775  3,622 0.1462  0.5067  0.2824  0.3583
pass     3,620   538   0.1486  0.4910  0.2363  0.2381
pon      936     118   0.1261  0.5547  0.2707  0.4792
```

This is directionally better for discard ranking than the rejected proxy-target
runs, but it still does not beat the older plain visible58 action-risk critic
(`AUC 0.5096`). Do not promote it. The lesson is that direct same-state labels
help, but 49 matched pairwise transitions are not enough. The next useful move is
to generate paired-trace-aligned shards specifically around divergence windows
or export full observation tensors from paired traces so all 255 labels can train
directly without relying on shard rematching.

### Experiment: Direct Tensor Counterfactual Action-Risk Data

Run:

`/root/fh-mahjong-runs/chongci-direct-counterfactual-actionrisk-20260602-220925`

Question:

Can direct tensor-bearing paired-trace labels train the action-risk critic better
than seed/decision rematching, by using all counterfactual first-divergence
labels that pass the reward-gap threshold?

Implementation:

`paired_trace.py` can now include full `planes`, `scalars`, and `action_mask`
arrays at first-divergence observations when run with:

```text
--include-observation-arrays
```

`build_counterfactual_risk_data.py` converts those tensor-bearing labels into a
small sharded NPZ dataset. Each row stores the avoided action as the observed
`action_id`, the preferred action in `pairwise_preferred_action_ids`, the avoided
action in `pairwise_avoided_action_ids`, and the reward gap in
`pairwise_reward_delta_targets`.

Training plan:

```text
trace windows: 564000:50, 574000:50, 584000:50
seats: 0,1,2,3
min_reward_gap: 0.05
target_mode: terminal
paired_margin_weight: 1.0
paired_severity_weight: 0.5
paired_batch_fraction: 0.5
```

Result:

The run completed successfully.

```text
trace pairs:                   600
divergence rate:               71.83%
candidate-better rate:         21.33%
mean candidate-anchor delta:    0.0050
counterfactual rows:           187
positive terminal rows:         35
skipped reward-gap labels:      68
```

Independent calib16 result:

```text
variant                       AUC     Brier   pos_mean  neg_mean  severity_MAE
direct_counterfactual_gap005  0.5061  0.2482  0.4329    0.4280    0.4472
```

Action-family calibration:

```text
family   count   pos   rate    AUC     Brier   severity_MAE
chii     1,249   201   0.1609  0.5225  0.2662  0.4309
discard 24,775  3,622 0.1462  0.5048  0.2478  0.4594
pass     3,620   538   0.1486  0.5245  0.2418  0.3660
pon      936     118   0.1261  0.4723  0.2708  0.5094
kan      108      18   0.1667  0.3840  0.3918  0.8248
win      759      76   0.1001  0.5217  0.2148  0.3332
```

Decision:

Reject for promotion. Direct tensor labels removed the rematching bottleneck,
but the independent large-loss ranking still did not beat the older plain
visible58 action-risk critic (`AUC 0.5096`). The discard-specific AUC also
fell to `0.5048`, which is weaker than the rematched counterfactual run's
discard AUC (`0.5067`).

Interpretation:

The failure is now less likely to be caused only by sparse rematching. Direct
first-divergence labels are useful diagnostics, but as a standalone risk target
they remain too local, too few, or too noisy for the current action-risk head.
The next useful direction is not another scalar threshold sweep. Use the
counterfactual tensor path as tooling, then either:

1. add incremental/resumable paired-trace output so larger label sets are
   practical, or
2. move risk learning into a richer critic-side objective that combines later
   trajectory labels, action family, score-pressure context, and terminal
   downside rather than supervising only the first divergent action.

Follow-up tooling:

The paired-trace CLI now supports resumable long runs:

```text
--incremental-report-interval <pairs>
--resume
```

`--incremental-report-interval` periodically writes a valid report to
`--report-output`; `--resume` reloads existing seed/seat pairs from that report
and skips them. This does not change model behavior or calibration metrics. It
only prevents long tensor-bearing paired traces from losing all progress if a
late seed is slow or interrupted.

### Experiment: Larger Direct Tensor Counterfactual Action-Risk Data

Run:

`/root/fh-mahjong-runs/chongci-direct-counterfactual-actionrisk-large-20260602-235548`

Question:

Does a larger direct tensor-bearing counterfactual label set improve independent
large-loss ranking enough to beat the plain visible58 action-risk critic
(`AUC 0.5096`)?

Design:

```text
trace windows: 564000:100, 574000:100, 584000:100
seats: 0,1,2,3
total trace pairs: 1200
min_reward_gap: 0.05
target_mode: terminal
paired_margin_weight: 1.0
paired_severity_weight: 0.5
paired_batch_fraction: 0.5
steps_per_epoch: 200
```

Operational change:

This is the first run using resumable paired-trace output:

```text
--incremental-report-interval 20
--resume
```

Result:

The run completed successfully. The first partial checkpoint was written at
`20/1200` trace pairs, proving the incremental report path works on the remote
WSL machine.

```text
trace pairs:                   1200
divergence rate:               69.00%
candidate-better rate:         20.58%
mean candidate-anchor delta:    0.0109
counterfactual rows:           343
positive terminal rows:         69
skipped reward-gap labels:     144
```

Independent calib16 result:

```text
variant                            AUC     Brier   pos_mean  neg_mean  severity_MAE
direct_counterfactual_large_gap005 0.5022  0.2448  0.4264    0.4248    0.3682
```

Action-family calibration:

```text
family   count   pos   rate    AUC     Brier   severity_MAE
chii     1,249   201   0.1609  0.4853  0.2503  0.4805
discard 24,775  3,622 0.1462  0.5018  0.2438  0.3740
pass     3,620   538   0.1486  0.5143  0.2378  0.3050
pon      936     118   0.1261  0.4747  0.2904  0.4442
kan      108      18   0.1667  0.5414  0.3072  0.7814
win      759      76   0.1001  0.5778  0.2368  0.1445
```

Decision:

Reject for promotion. Scaling direct first-divergence tensor labels from `187`
rows to `343` rows made severity error better but made risk ranking worse:
overall AUC fell from `0.5061` to `0.5022`, and discard AUC fell from `0.5048`
to `0.5018`. It remains below the plain visible58 action-risk critic
(`AUC 0.5096`).

Interpretation:

This closes the direct first-divergence-only risk-target branch for now. The
larger direct label set did not solve the calibration problem, so the issue is
not just missing observation tensors or sparse rematching. First-divergence
labels are still useful for diagnostics and future counterfactual tooling, but
they should not be the main action-risk objective. The next branch should use a
richer critic-side target: later-trajectory labels, action-family context,
visible score pressure, and terminal downside together.

### Implementation: Future Outcome Context Risk Target

Change:

`train_action_risk.py` now has a richer critic-side target:

```text
--target-mode future_outcome_context
```

This target keeps hard terminal large-loss labels, then adds context labels for
recent same-seat actions before actual bad terminal outcomes. A bad outcome is:

```text
large final loss
or deal-in with non-positive final reward
```

The label is not discard-only. It assigns family-specific credit to recent
visible actions:

```text
discard > kan > pon ~= chii ~= pass > haitei
win actions are not treated as risky
```

The credit is also scaled by visible Chongci score-pressure scalars, so an action
near bust/large-loss pressure receives more risk supervision than the same
family in a safe score state.

New controls:

```text
--future-context-window
--future-context-score-pressure-weight
--future-context-min-credit
--future-context-weight
```

Validation:

```text
uv run --project ai pytest \
  ai/tests/test_train_action_risk.py \
  ai/tests/test_reward_calibration.py \
  ai/tests/test_paired_trace.py \
  ai/tests/test_build_counterfactual_risk_data.py \
  ai/tests/test_risk_filter.py
```

Local result:

```text
25 passed
```

Next experiment:

Train a balanced action-risk critic with `future_outcome_context` on the same
visible58/score-pressure/direct-counterfactual data mix, then calibrate on the
same independent visible58 `calib16` gate. The promotion threshold is unchanged:
it must beat the plain visible58 action-risk critic (`AUC 0.5096`), especially
on discard-family AUC.

### Experiment: Future Outcome Context Action-Risk Critic

Run:

`/root/fh-mahjong-runs/chongci-future-context-actionrisk-20260603-032526`

Question:

Does replacing direct first-divergence-only labels with later-trajectory,
score-aware, action-family-aware risk labels improve independent large-loss
ranking?

Training:

```text
data:
  /root/fh-mahjong-runs/chongci-visible58-actionrisk-20260531-215255/data/anchor-visible58-train64-npz
  /root/fh-mahjong-runs/chongci-large-counterfactual-scorepressure-20260601-225427/data/anchor-scorepressure-seed-564000-n50-npz
  /root/fh-mahjong-runs/chongci-large-counterfactual-scorepressure-20260601-225427/data/anchor-scorepressure-seed-574000-n50-npz
  /root/fh-mahjong-runs/chongci-large-counterfactual-scorepressure-20260601-225427/data/anchor-scorepressure-seed-584000-n50-npz
target_mode: future_outcome_context
future_context_window: 8
future_context_score_pressure_weight: 0.5
future_context_min_credit: 0.5
future_context_weight: 1.0
steps_per_epoch: 200
batch_size: 2048
lr: 5e-5
```

Training target coverage:

```text
transitions:          436,877
positive transitions:  73,314
positive rate:          16.75%
```

Independent calib16 result:

```text
variant                         AUC     Brier   pos_mean  neg_mean  severity_MAE
future_context_w8_p05_min05     0.5082  0.2628  0.5006    0.4969    0.3859
```

Action-family calibration:

```text
family   count   pos   rate    AUC     Brier   severity_MAE
chii     1,249   201   0.1609  0.5312  0.2553  0.4579
discard 24,775  3,622 0.1462  0.5056  0.2649  0.3876
pass     3,620   538   0.1486  0.5078  0.2591  0.3412
pon      936     118   0.1261  0.5072  0.2729  0.5342
kan      108      18   0.1667  0.5506  0.2711  0.6018
win      759      76   0.1001  0.5199  0.2101  0.2102
```

Decision:

Reject for promotion, but keep the target implementation. This is the strongest
recent richer-target result and it nearly reaches the plain visible58 baseline
(`AUC 0.5096`), but it still does not beat it. Discard AUC is also only
`0.5056`, so it is not enough for a serving guard.

Interpretation:

Later-trajectory labels plus score/action-family context are directionally
better than direct first-divergence labels (`0.5082` vs `0.5022` on the larger
direct run), but the ranking signal is still weak. The next variant should not
return to direct first-divergence supervision. It should either:

1. use action-family-specific calibration heads/weights so discard, pass, meld,
   and win decisions do not compete for one poorly separated risk scale, or
2. train the risk critic on a larger, more diverse trajectory set so the
   future-context labels have enough positive examples per family.

### Implementation: Action-Family-Balanced Risk Loss

Change:

`train_action_risk.py` now applies explicit per-row loss weights to both the
risk-probability BCE and severity losses. The weight source is:

```text
stored sample_weights
times optional action-family balance weights
```

New controls:

```text
--family-balance-strength
--family-weight-clip
```

Default behavior is unchanged because `--family-balance-strength` defaults to
`0.0`. When enabled, the trainer interpolates toward equal loss mass for action
families such as discard, pass, pon, kan, chii, haitei, and win. This is intended
to reduce discard-heavy domination without changing the evaluation gate.

Validation:

```text
uv run --project ai pytest \
  ai/tests/test_train_action_risk.py \
  ai/tests/test_reward_calibration.py \
  ai/tests/test_paired_trace.py \
  ai/tests/test_build_counterfactual_risk_data.py \
  ai/tests/test_risk_filter.py
```

Local result:

```text
26 passed
```

Next experiment:

Train the future-context critic with action-family-balanced loss and a larger,
more diverse data mix. This tests both proposed next steps together:

```text
target_mode: future_outcome_context
family_balance_strength: 1.0
larger data: visible58 train64 + scorepressure windows + direct tensor labels + current/all-seat self-play shards
```

### Experiment: Family-Balanced Future Context Risk Critic With Larger Data

Run:

`/root/fh-mahjong-runs/chongci-familybalanced-future-context-actionrisk-20260603-134259`

Question:

Do action-family-balanced loss weights plus a larger/diverse data mix improve the
future-context risk critic enough to beat the plain visible58 action-risk
baseline?

Training:

```text
data:
  visible58 train64
  scorepressure seed windows 564000/574000/584000
  direct tensor counterfactual large gap005 shard
  capped400k low-drift self-play shard
target_mode: future_outcome_context
family_balance_strength: 1.0
family_weight_clip: 4.0
future_context_window: 8
future_context_score_pressure_weight: 0.5
future_context_min_credit: 0.5
steps_per_epoch: 250
batch_size: 2048
paired_margin_weight: 0.5
paired_severity_weight: 0.25
```

Training target coverage:

```text
transitions:          837,220
positive transitions: 145,122
positive rate:          17.31%
paired transitions:        343
loss_weight_mean:        1.00
loss_weight_max:         4.93
```

Independent calib16 result:

```text
variant                                      AUC     Brier   pos_mean  neg_mean  severity_MAE
familybalanced_future_context_fb1_large      0.5053  0.4124  0.6504    0.6473    0.4132
```

Action-family calibration:

```text
family   count   pos   rate    AUC     Brier   severity_MAE
chii     1,249   201   0.1609  0.4645  0.2591  0.4010
discard 24,775  3,622 0.1462  0.5060  0.4585  0.4357
pass     3,620   538   0.1486  0.4877  0.2352  0.3027
pon      936     118   0.1261  0.5263  0.2503  0.4486
kan      108      18   0.1667  0.5216  0.2965  0.6495
win      759      76   0.1001  0.4680  0.2186  0.1475
```

Decision:

Reject for promotion. The larger data mix plus full family-balanced weighting
did not beat the plain visible58 baseline (`AUC 0.5096`) and also underperformed
the unweighted future-context run (`AUC 0.5082`). Discard AUC was roughly flat
(`0.5060` vs `0.5056`), but overall calibration got much worse because predicted
risk probabilities shifted too high (`mean ~= 0.65`) and Brier rose to `0.4124`.

Interpretation:

Full-strength family balancing overcorrected. It may help minority families
such as pon/kan, but it damaged chii/pass/win and global calibration. Do not
use `family_balance_strength=1.0` as the default. If this branch continues, try
a mild family balance such as `0.25` or `0.5`, or move to explicit per-family
post-hoc calibration instead of forcing one shared model scale during training.

### Experiment: Mild Family-Balanced Future Context Risk Critics

Run:

`/root/fh-mahjong-runs/chongci-mild-familybalance-future-context-actionrisk-20260603-160652`

Question:

Does mild action-family balancing keep the benefits of the richer future-context
target without the overcorrection seen at `family_balance_strength=1.0`?

Training:

Same larger data mix as the rejected full-balance run:

```text
visible58 train64
scorepressure seed windows 564000/574000/584000
direct tensor counterfactual large gap005 shard
capped400k low-drift self-play shard
```

Shared settings:

```text
target_mode: future_outcome_context
future_context_window: 8
future_context_score_pressure_weight: 0.5
future_context_min_credit: 0.5
paired_margin_weight: 0.5
paired_severity_weight: 0.25
steps_per_epoch: 250
batch_size: 2048
```

Variants:

```text
fb025: family_balance_strength 0.25
fb05:  family_balance_strength 0.50
```

Independent calib16 result:

```text
variant                  AUC     Brier   pos_mean  neg_mean  severity_MAE
future_context_fb025     0.5118  0.2683  0.4940    0.4876    0.3660
future_context_fb05      0.5023  0.2995  0.5293    0.5278    0.3562
```

Action-family calibration:

```text
family   fb025 AUC  fb05 AUC
chii     0.5492     0.5241
discard  0.5089     0.4998
pass     0.5218     0.4934
pon      0.4531     0.4983
kan      0.4889     0.5000
win      0.5206     0.5150
```

Decision:

Accept `future_context_fb025_large` as the best risk-critic calibration result
so far, but do not promote it as a playing policy. It beats the plain visible58
action-risk critic on overall AUC (`0.5118` vs `0.5096`) and improves discard
AUC over the unweighted future-context run (`0.5089` vs `0.5056`). `fb05` is
rejected because it regresses both overall and discard AUC.

Interpretation:

Mild family balancing is useful; stronger balancing overcorrects. The risk
critic now has a better independent large-loss ranking signal, especially for
discard/pass/chii, but pon/kan are still unstable because their calib counts are
small. The next step should be a guarded evaluation or offline policy filter
using `future_context_fb025_large`, with a conservative threshold sweep. Do not
serve it blindly: risk AUC improved, but policy EV and tail-risk must still be
measured in duplicate-seat evaluation.

### Experiment: Risk-Guarded Evaluation With Future-Context fb025 Critic

Run:

```text
/root/fh-mahjong-runs/chongci-riskguard-fb025-sweep-20260603-222928
```

Question:

Can the best calibrated action-risk critic from `future_context_fb025_large`
act as a conservative serving-time guard around the promoted Chongci policy?

Saved test checkpoint:

```text
/root/fh-mahjong-checkpoints/chongci-riskcritic-future-context-fb025-latest.pt
```

This checkpoint was copied from:

```text
/root/fh-mahjong-runs/chongci-mild-familybalance-future-context-actionrisk-20260603-160652/checkpoints/future_context_fb025/epoch_001.pt
```

Evaluation:

```text
anchor policy:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
risk critic:
  /root/fh-mahjong-checkpoints/chongci-riskcritic-future-context-fb025-latest.pt
seed window:
  650000:16
seats:
  0 1 2 3
episodes:
  64 per threshold
guard settings:
  candidate_risk_threshold=0.45
  min_risk_reduction=0.08
  max_policy_logit_gap=2.0
  severity_weight=0.1
```

Result:

```text
anchor_risk_threshold  mean_reward  positive_rate  large_loss_rate  guard_choice_rate
0.55                   -0.2243      39.06%         18.75%           1.25%
0.60                   -0.2039      40.62%         14.06%           0.86%
0.65                   -0.2288      37.50%         12.50%           0.58%
0.70                   -0.2119      40.62%         14.06%           0.32%
```

Report:

```text
/root/fh-mahjong-runs/chongci-riskguard-fb025-sweep-20260603-222928/reports/riskguard_fb025_seed650000_n16.json
/root/fh-mahjong-runs/chongci-riskguard-fb025-sweep-20260603-222928/reports/summary.json
```

Same-window anchor side-by-side:

```text
/root/fh-mahjong-runs/chongci-anchor-sidebyside-20000-20260603-230156
```

The first generic-anchor attempt used the default `max_steps_per_episode=256`
and was invalid because every match truncated. The valid rerun matched the
risk-guarded evaluator's `max_steps_per_episode=20000`.

```text
seed_window  policy       mean_reward  positive_rate  large_loss_rate
650000:16    anchor       -0.2100      40.62%         15.62%
650000:16    guard 0.60   -0.2039      40.62%         14.06%
delta                     +0.0061      +0.00%         -1.56%
```

Independent gate:

```text
/root/fh-mahjong-runs/chongci-riskguard-fb025-independent-20260603-230720
```

```text
seed_window  policy       mean_reward  positive_rate  large_loss_rate  guard_choice_rate
660000:16    anchor       -0.1300      40.62%         17.19%           n/a
660000:16    guard 0.60   -0.1446      37.50%         18.75%           0.81%
delta                     -0.0146      -3.12%         +1.56%           n/a
```

Decision:

Keep the saved risk critic as a testable artifact, but reject this guarded
serving configuration for now. On the calibration/smoke window, threshold
`0.60` slightly beat the pure anchor, but the independent `660000:16` gate
reversed the result: mean reward, positive rate, and large-loss rate all
regressed.

Interpretation:

The action-risk critic can affect play without causing illegal actions, but the
current guard is not reliably selecting beneficial substitutions. The low guard
choice rate (`~0.8%`) means each substitution has to be very high precision; on
the independent window, those substitutions were not good enough. Do not spend
more time on threshold sweeps for this critic. The next useful branch should
improve the risk target/model itself or move the risk signal into offline
training, then re-run the same side-by-side protocol.

### Experiment: Risk-Guard Intervention Audit And Policy-Nearest Ranking

Runs:

```text
/root/fh-mahjong-runs/chongci-riskguard-fb025-intervention-audit-fixed-20260603-233302
/root/fh-mahjong-runs/chongci-riskguard-policynearest-20260603-234107
```

Question:

Did the `future_context_fb025_large` guard fail because the risk model was
unusable, or because the serving rule chose the lowest-risk substitute without
preserving enough policy quality?

Implementation:

- Added generic intervention summaries to guarded evaluation reports.
- Added `chosen_action_id` to `RiskGuardedPolicy` choice metadata.
- Added `selection_mode="policy_nearest"` to `RiskGuardedPolicy` and
  `evaluate_risk_guarded.py`.
- `lowest_risk` keeps the old behavior: among allowed lower-risk actions, pick
  the lowest risk score.
- `policy_nearest` keeps all risk filters but ranks allowed substitutes by
  closeness to the anchor policy logit, using risk only as a small tie-breaker.

Independent `660000:16` result:

```text
policy                    mean_reward  positive_rate  large_loss_rate  guard_choice_rate
anchor                    -0.1300      40.62%         17.19%           n/a
lowest_risk guard 0.60    -0.1446      37.50%         18.75%           0.81%
policy_nearest guard 0.60 -0.1351      37.50%         18.75%           0.82%
```

Intervention audit for the failed independent window:

```text
total interventions: 263 lowest_risk / 265 policy_nearest
anchor action families changed:
  discard: 243-245
  chii:    13
  pon:     6
  pass:    1
chosen action families:
  discard: 241-243
  pass:    13
  chii:    6
  kan:     2
  pon:     1
```

Episode bucket signal:

```text
interventions per episode  count  mean_reward  positive_rate
1                          7      -0.90 to -0.95  0.00%
2-4                        30     -0.05 to -0.06  43.33%
5+                         27     -0.03           40.74%
```

Decision:

Reject both serving guard variants for now. `policy_nearest` recovered part of
the mean-reward loss versus `lowest_risk`, but it still lost to pure anchor and
did not improve positive rate or large-loss rate.

Interpretation:

The direct serving guard is too blunt even when substitutions are policy-near.
Most interventions are discard-to-discard, so the critic is mostly changing
tile choice, not correcting rare high-level mistakes. The worst bucket is
episodes with exactly one intervention, which suggests the guard is not
high-precision enough at the exact moments it chooses to act. The next branch
should stop serving-time substitution for this critic and instead use the risk
signal as training-side supervision or train a better discard-specific
counterfactual critic before any new guard evaluation.

### Experiment: External Risk Critic As IQL Policy Regularizer

Runs:

```text
/root/fh-mahjong-runs/chongci-iql-external-risk-discard-20260604-235637
/root/fh-mahjong-runs/chongci-iql-external-risk-discard-t070-20260604-000909
/root/fh-mahjong-runs/chongci-iql-external-risk-discard-tailbc-20260604-001937
/root/fh-mahjong-runs/chongci-iql-external-risk-discard-tailbc3-20260604-002537
```

Question:

Can the saved `future_context_fb025_large` risk critic help policy learning if
used during offline IQL training instead of making live serving-time
substitutions?

Implementation:

- Added an optional frozen external action-risk model to `DiscreteIQLTrainer`.
- Added `--external-risk-checkpoint` to `train_iql.py`.
- Added `--external-risk-policy-weight`, `--external-risk-policy-threshold`,
  `--external-risk-policy-family`, and
  `--external-risk-policy-severity-weight`.
- Added `--large-loss-bc-weight` as a policy-only preservation term on
  transitions whose terminal return is at or below `--large-loss-threshold`.
- The regularizer computes the current policy distribution over legal actions,
  asks the frozen risk critic for action-conditioned risk probabilities, and
  penalizes policy mass assigned to legal actions whose risk exceeds the
  configured threshold.
- The first experiment was scoped to `discard` actions only because the serving
  audit showed most failed interventions were discard-to-discard changes.

Training setup:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
risk checkpoint:
  /root/fh-mahjong-checkpoints/chongci-riskcritic-future-context-fb025-latest.pt
datasets:
  heuristic-chongci-50scalar-200
  mixed-selfplay-iql-50
  mixed-selfplay-iql-200-seats02
  capped400k-current-lowdrift
max_transitions:
  150000 per dataset
epochs:
  1
batch_size:
  4096
lr:
  1e-5
external_risk_policy_weight:
  0.05
external_risk_policy_family:
  discard
```

Training diagnostics:

```text
threshold 0.60: ext_risk ~= 0.022-0.025
threshold 0.70: ext_risk ~= 0.007-0.009
```

Quick gate on `660000:16`:

```text
policy                               mean_reward  positive_rate  large_loss_rate
anchor                               -0.1328      40.62%         17.19%
external risk discard t0.60          -0.0526      43.75%         20.31%
external risk discard t0.70          -0.0526      43.75%         20.31%
external risk discard + tailBC w1    -0.0598      42.19%         20.31%
external risk discard + tailBC w3    -0.0845      42.19%         20.31%
```

Decision:

Reject all external-risk discard regularizer variants as promotion candidates.
They improve mean reward and positive rate on the quick gate, but every variant
regresses large-loss rate by `+3.125%`, which violates the Chongci promotion
guardrail. Increasing `large_loss_bc_weight` from `1.0` to `3.0` reduced the EV
gain but still did not recover tail risk.

Interpretation:

Using the risk critic during training is more promising than serving-time
substitution for mean reward, but this specific risk signal still does not
control tail losses. Raising the risk threshold reduced the regularizer's loss
magnitude but did not change the quick-gate result, suggesting the checkpoint
movement is dominated by the IQL update plus coarse risk pressure rather than
high-confidence tail correction. Adding a tail-only BC preservation term did
not fix the large-loss regression; it mostly traded away some mean reward. Do
not promote or expand this exact regularizer yet. The next useful branch is
either:

```text
1. train a better discard-specific counterfactual risk critic before using it
   in policy training, or
2. use paired/counterfactual large-loss labels to tell the policy which
   alternatives preserve EV without creating new large-loss cases.
```

### Experiment: Direct Counterfactual Pairwise IQL Auxiliary

Run:

```text
/root/fh-mahjong-runs/chongci-iql-counterfactual-pairwise-20260604-192734
```

Question:

Can tensor-bearing paired-trace counterfactual labels improve the reward-trained
IQL policy when used as a direct preferred/avoided action margin, without
behavior-cloning the avoided action?

Implementation:

- Added `--risk-trace-counterfactual-labels` and
  `--risk-trace-min-counterfactual-reward-gap` to `train_iql.py` so exact-match
  risk-trace replay can consume the same counterfactual first-divergence labels
  as action-risk training.
- Checked the existing large tensor trace against the older IQL replay shards.
  It produced hundreds of labels but `0` exact replay matches across the known
  heuristic/mixed/self-play datasets, so exact-match trace weighting would not
  train anything.
- Added `--pairwise-data` to `train_iql.py` for direct tensor-bearing
  counterfactual NPZ shards. These rows are loaded as auxiliary replay with
  normal IQL `sample_weights = 0`, dummy MC-compatible next-state fields, and
  non-zero `pairwise_weights`, so they affect only policy/Q preferred-over-
  avoided margin losses.

Data:

```text
source paired trace:
  /root/fh-mahjong-runs/chongci-direct-counterfactual-actionrisk-large-20260602-235548/reports/anchor_vs_candidate_tensor_trace.json
direct pairwise shard:
  /root/fh-mahjong-runs/chongci-iql-counterfactual-pairwise-20260604-192734/data/counterfactual-pairwise-gap010
rows:
  269
positive terminal rows at <= -1.0:
  52
mean reward gap:
  0.3873
max reward gap:
  1.5210
```

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
base datasets:
  heuristic-chongci-50scalar-200
  mixed-selfplay-iql-50
  mixed-selfplay-iql-200-seats02
  capped400k-current-lowdrift
max_transitions:
  150000 per base dataset
pairwise auxiliary:
  same 269-row shard repeated 12 times
epochs:
  1
batch_size:
  4096
lr:
  1e-5
pairwise_q_weight / margin:
  0.25 / 0.10
pairwise_weight / margin:
  0.02 / 0.05
```

Training diagnostics:

```text
pairwise_count:
  active, roughly 15-30 rows per logged batch
pairwise_q_loss:
  non-zero and decreasing, about 0.1695 -> 0.0878 in logged steps
epoch avg loss:
  0.1781
checkpoint:
  /root/fh-mahjong-runs/chongci-iql-counterfactual-pairwise-20260604-192734/checkpoints/counterfactual_pairwise_q025_policy002/epoch_001.pt
```

Evaluation:

```text
smoke window:
  660000:4, duplicate seats, 16 evaluated seats
anchor:
  mean_reward=-0.3686, positive_rate=43.75%, large_loss_rate=31.25%
candidate:
  mean_reward=-0.3611, positive_rate=43.75%, large_loss_rate=31.25%
full independent gate:
  660000:16, duplicate seats, 64 evaluated seats
anchor:
  mean_reward=-0.1328, positive_rate=40.62%, large_loss_rate=17.19%
candidate:
  mean_reward=-0.0805, positive_rate=43.75%, large_loss_rate=20.31%
candidate full report:
  /root/fh-mahjong-runs/chongci-iql-counterfactual-pairwise-20260604-192734/reports/candidate_counterfactual_pairwise_gate_660000_16.json
```

Decision:

Rejected. The candidate improves mean reward and positive-rate on the
independent gate, but it regresses large-loss rate from `17.19%` to `20.31%`.
That violates the Chongci promotion guardrail, so
`ai/checkpoints/best-checkpoints.json` records it as a rejected candidate and
the promoted checkpoint remains `iql_lowlr_selfplay200_epoch003`.

Interpretation:

The new plumbing is useful because it turns tensor-bearing paired traces into
active pairwise IQL supervision even when exact seed/decision matching against
older replay shards is impossible. However, this exact candidate repeats the
same pattern as the frozen external-risk regularizer branch: better EV and
positive-rate, worse tail risk. Do not scale this exact 269-row auxiliary ratio
without a new tail-control ingredient. The useful next branch is to make the
counterfactual auxiliary tail-aware, for example by training only high-risk
counterfactual rows, using reward-gap/severity weights, or adding a tail
constraint that blocks EV improvements which increase large-loss frequency.

### Experiment: High-Risk-Only Counterfactual Pairwise IQL Auxiliary

Run:

```text
/root/fh-mahjong-runs/chongci-iql-counterfactual-highrisk-pairwise-20260604-194925
```

Question:

Does restricting direct counterfactual pairwise supervision to only high-risk
first-divergence rows avoid the large-loss regression from the broader
269-row counterfactual auxiliary run?

Data:

```text
source paired trace:
  /root/fh-mahjong-runs/chongci-direct-counterfactual-actionrisk-large-20260602-235548/reports/anchor_vs_candidate_tensor_trace.json
direct high-risk pairwise shard:
  /root/fh-mahjong-runs/chongci-iql-counterfactual-highrisk-pairwise-20260604-194925/data/counterfactual-highrisk-gap010
rows:
  52
positive terminal rows at <= -1.0:
  52
skipped non-high-risk labels:
  217
mean reward gap:
  0.4446
max reward gap:
  1.5210
```

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
base datasets:
  heuristic-chongci-50scalar-200
  mixed-selfplay-iql-50
  mixed-selfplay-iql-200-seats02
  capped400k-current-lowdrift
max_transitions:
  150000 per base dataset
pairwise auxiliary:
  same 52-row shard repeated 64 times
epochs:
  1
batch_size:
  4096
lr:
  1e-5
pairwise_q_weight / margin:
  0.25 / 0.10
pairwise_weight / margin:
  0.01 / 0.05
checkpoint:
  /root/fh-mahjong-runs/chongci-iql-counterfactual-highrisk-pairwise-20260604-194925/checkpoints/highrisk_pairwise_q025_policy001/epoch_001.pt
```

Training diagnostics:

```text
pairwise_count:
  active, roughly 15-32 rows per logged batch
pairwise_q_loss:
  non-zero and decreasing, about 0.1134 -> 0.0058 in logged steps
epoch avg loss:
  0.1619
```

Evaluation:

```text
smoke window:
  660000:4, duplicate seats, 16 evaluated seats
anchor:
  mean_reward=-0.3686, positive_rate=43.75%, large_loss_rate=31.25%
candidate:
  mean_reward=-0.3599, positive_rate=43.75%, large_loss_rate=31.25%

full independent gate:
  660000:16, duplicate seats, 64 evaluated seats
anchor:
  mean_reward=-0.1328, positive_rate=40.62%, large_loss_rate=17.19%
candidate:
  mean_reward=-0.0883, positive_rate=43.75%, large_loss_rate=20.31%
candidate full report:
  /root/fh-mahjong-runs/chongci-iql-counterfactual-highrisk-pairwise-20260604-194925/reports/candidate_highrisk_pairwise_gate_660000_16.json
```

Decision:

Rejected. High-risk filtering preserved the same EV/positive-rate improvement,
but it still regressed large-loss rate from `17.19%` to `20.31%`.
`ai/checkpoints/best-checkpoints.json` records this as a rejected candidate.

Interpretation:

Narrowing pairwise labels to high-risk rows is not enough. The policy still
moves into a better-average but worse-tail region. The next branch should stop
treating pairwise margin as the whole tail-control mechanism. Use a true
tail-aware objective, such as reward-gap/severity-weighted pairwise Q targets,
explicit large-loss probability constraints during IQL, or a promotion-time
conservative ensemble where the candidate can only override anchor actions when
tail-risk stays below the anchor on matched states.

### Experiment: Reward-Delta Severity Pairwise IQL Auxiliary

Run:

```text
/root/fh-mahjong-runs/chongci-iql-counterfactual-severity-pairwise-20260604-201002
```

Question:

Can `pairwise_reward_delta_targets` make direct counterfactual pairwise IQL
tail-aware enough to reduce the large-loss regression from equal-margin
pairwise variants?

Implementation:

- Added `pairwise_reward_delta_targets` to `TrainBatch` and replay buffer
  sampling.
- Added `--pairwise-reward-delta-weight`,
  `--pairwise-reward-delta-margin-scale`, and
  `--pairwise-reward-delta-clip` to `train_iql.py`.
- Pairwise rows can now scale relative row weights and required policy/Q
  margins by clipped counterfactual reward gap. Defaults remain zero, preserving
  previous behavior unless the new flags are enabled.

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
pairwise data:
  269-row counterfactual-pairwise-gap010 shard repeated 12 times
pairwise_q_weight / margin:
  0.25 / 0.05
pairwise_weight / margin:
  0.01 / 0.02
pairwise_reward_delta_weight:
  1.0
pairwise_reward_delta_margin_scale:
  0.35
pairwise_reward_delta_clip:
  2.0
checkpoint:
  /root/fh-mahjong-runs/chongci-iql-counterfactual-severity-pairwise-20260604-201002/checkpoints/severity_pairwise_q025_policy001_margin035/epoch_001.pt
```

Training diagnostics:

```text
pairwise_count:
  active, roughly 15-30 rows per logged batch
pairwise_loss:
  materially active, about 0.1078 -> 0.0089 in logged steps
pairwise_q_loss:
  materially active, about 0.2826 -> 0.1687 in logged steps
epoch avg loss:
  0.2027
```

Evaluation:

```text
smoke window:
  660000:4, duplicate seats, 16 evaluated seats
candidate:
  mean_reward=-0.3207, positive_rate=43.75%, large_loss_rate=31.25%

full independent gate:
  660000:16, duplicate seats, 64 evaluated seats
anchor:
  mean_reward=-0.1328, positive_rate=40.62%, large_loss_rate=17.19%
candidate:
  mean_reward=-0.0745, positive_rate=43.75%, large_loss_rate=18.75%
candidate full report:
  /root/fh-mahjong-runs/chongci-iql-counterfactual-severity-pairwise-20260604-201002/reports/candidate_severity_pairwise_gate_660000_16.json
```

Decision:

Rejected, but keep as the best pairwise-tail direction so far. It still
regresses large-loss rate against the promoted anchor, but it improves the
pairwise branch from `20.31%` large-loss to `18.75%`.

Interpretation:

Reward-gap severity is the first pairwise change that actually moved tail risk
in the right direction while preserving the EV gain. One stronger severity
variant is justified. If that still cannot match the anchor's `17.19%`
large-loss rate, stop pairwise-margin sweeps and move to explicit constrained
selection or a separate large-loss probability constraint.

### Experiment: Strong Reward-Delta Severity Pairwise IQL Auxiliary

Run:

```text
/root/fh-mahjong-runs/chongci-iql-counterfactual-severity-strong-20260604-202008
```

Question:

Can a stronger reward-gap margin close the remaining one-seat tail gap from the
moderate severity run?

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
pairwise data:
  269-row counterfactual-pairwise-gap010 shard repeated 12 times
pairwise_q_weight / margin:
  0.35 / 0.05
pairwise_weight / margin:
  0.01 / 0.02
pairwise_reward_delta_weight:
  1.0
pairwise_reward_delta_margin_scale:
  0.70
pairwise_reward_delta_clip:
  2.0
checkpoint:
  /root/fh-mahjong-runs/chongci-iql-counterfactual-severity-strong-20260604-202008/checkpoints/severity_pairwise_q035_policy001_margin070/epoch_001.pt
```

Training diagnostics:

```text
pairwise_count:
  active, roughly 15-30 rows per logged batch
pairwise_loss:
  much stronger, about 0.2504 -> 0.0147 in logged steps
pairwise_q_loss:
  much stronger, about 0.4604 -> 0.2947 in logged steps
epoch avg loss:
  0.2767
```

Evaluation:

```text
smoke window:
  660000:4, duplicate seats, 16 evaluated seats
candidate:
  mean_reward=-0.2749, positive_rate=43.75%, large_loss_rate=31.25%

full independent gate:
  660000:16, duplicate seats, 64 evaluated seats
anchor:
  mean_reward=-0.1328, positive_rate=40.62%, large_loss_rate=17.19%
candidate:
  mean_reward=-0.0718, positive_rate=40.62%, large_loss_rate=20.31%
candidate full report:
  /root/fh-mahjong-runs/chongci-iql-counterfactual-severity-strong-20260604-202008/reports/candidate_severity_strong_gate_660000_16.json
```

Decision:

Rejected. Stronger severity margins improved mean reward but regressed
large-loss rate back to `20.31%` and lost the positive-rate gain. This is worse
than the moderate severity run for the Chongci promotion guard.

Interpretation:

Stop pairwise-margin sweeps. The moderate severity run showed that reward-gap
targets can move tail risk in the right direction, but pairwise margin alone is
not a reliable tail-control mechanism. The next branch should be an explicit
constraint: either a large-loss probability constraint in IQL or a conservative
anchor/candidate selector that allows candidate actions only when an independent
tail-risk model says risk is no worse than anchor.

### Experiment: Explicit Tail-Constrained Candidate Selector

Run:

```text
/root/fh-mahjong-runs/chongci-tail-constrained-candidate-20260604-203409
```

Question:

Can we keep the EV upside from the moderate severity-pairwise candidate while
blocking candidate overrides unless an independent action-risk model predicts
large-loss probability is no worse than the promoted anchor action?

Implementation:

- Added `TailConstrainedCandidatePolicy`.
- The policy computes:
  - anchor action from promoted anchor policy logits,
  - candidate action from reward-trained candidate policy logits,
  - candidate Q advantage over the anchor action from the candidate Q head,
  - anchor and candidate large-loss probability from the action-risk model.
- It allows the candidate action only when:

```text
candidate_q - anchor_action_q >= min_q_margin
candidate_large_loss_probability - anchor_large_loss_probability <= max_risk_increase
candidate_tail_score - anchor_tail_score <= max_risk_increase
```

- With default `severity_weight=0`, the tail-score condition is the same as the
  large-loss probability condition. This keeps the first implementation aligned
  with the intended rule: candidate can improve EV only when large-loss
  probability is no worse than anchor.
- Added `evaluate_tail_constrained.py` to run duplicate-seat gate sweeps.

Policy inputs:

```text
anchor checkpoint:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
candidate checkpoint:
  /root/fh-mahjong-runs/chongci-iql-counterfactual-severity-pairwise-20260604-201002/checkpoints/severity_pairwise_q025_policy001_margin035/epoch_001.pt
risk checkpoint:
  /root/fh-mahjong-checkpoints/chongci-riskcritic-future-context-fb025-latest.pt
constraint:
  min_q_margin=0.0
  max_risk_increase=0.0
  severity_weight=0.0
```

Smoke evaluation:

```text
window:
  660000:4, duplicate seats, 16 evaluated seats
anchor:
  mean_reward=-0.3686, positive_rate=43.75%, large_loss_rate=31.25%
tail constrained candidate:
  mean_reward=-0.3596, positive_rate=43.75%, large_loss_rate=31.25%
candidate override rate:
  0.094%
anchor block rate:
  0.201%
same-action rate:
  99.705%
report:
  /root/fh-mahjong-runs/chongci-tail-constrained-candidate-20260604-203409/reports/tail_constrained_moderate_smoke_660000_4.json
```

Independent gate:

```text
window:
  660000:16, duplicate seats, 64 evaluated seats
anchor:
  mean_reward=-0.1328, positive_rate=40.62%, large_loss_rate=17.19%
tail constrained candidate:
  mean_reward=-0.1324, positive_rate=40.62%, large_loss_rate=17.19%
candidate override rate:
  0.068%
anchor block rate:
  0.241%
same-action rate:
  99.691%
report:
  /root/fh-mahjong-runs/chongci-tail-constrained-candidate-20260604-203409/reports/tail_constrained_moderate_gate_660000_16.json
```

Decision:

Not promoted yet, but this is the first candidate-serving path that preserves
the anchor large-loss rate on the independent `660000:16` gate while allowing a
small amount of EV-positive candidate behavior. The gain is tiny because the
constraint is strict and the candidate/anchor agree on almost all actions.

Follow-up:

A larger combined-window validation finished:

```text
seed windows:
  534000:10
  544000:10
  554000:10
evaluated seats:
  120
anchor:
  mean_reward=-0.0557, positive_rate=42.50%, large_loss_rate=15.00%
tail constrained candidate:
  mean_reward=-0.0570, positive_rate=41.67%, large_loss_rate=15.00%
candidate override rate:
  0.062%
anchor block rate:
  0.225%
report:
  /root/fh-mahjong-runs/chongci-tail-constrained-candidate-20260604-203409/reports/tail_constrained_moderate_combined_gate_534_544_554.json
anchor report:
  /root/fh-mahjong-runs/chongci-tail-constrained-candidate-20260604-203409/reports/anchor_combined_gate_534_544_554_n10.json
```

Final decision:

Rejected as a promotion candidate. The explicit constraint preserves large-loss
rate on the combined gate, but it loses mean reward and positive-rate versus
the promoted anchor. It also allows candidate overrides on only about `0.06%`
of decisions, so it is currently too conservative to be useful.

Interpretation:

The explicit constraint behaves correctly. It blocks almost every candidate
divergence, which means it is not a strong policy improvement yet, but it
solves the specific failure mode from pairwise IQL: EV-up candidates no longer
automatically increase tail risk. The next useful work is improving risk-model
sensitivity or adding an action-family-specific tolerance so the constraint can
safely allow more than about `0.06%` candidate overrides without regressing
large-loss rate.

### Experiment: Stronger Future-Context Risk Critic fb050

Run:

```text
/root/fh-mahjong-runs/chongci-stronger-familybalance-riskcritic-20260604-212437
```

Question:

Can a stronger action-risk critic create better large-loss separation than the
current `future_context_fb025` critic, so the tail-constrained candidate
selector can safely allow more candidate actions?

Data:

```text
/root/fh-mahjong-runs/chongci-visible58-actionrisk-20260531-215255/data/anchor-visible58-train64-npz
/root/fh-mahjong-runs/chongci-large-counterfactual-scorepressure-20260601-225427/data/anchor-scorepressure-seed-564000-n50-npz
/root/fh-mahjong-runs/chongci-large-counterfactual-scorepressure-20260601-225427/data/anchor-scorepressure-seed-574000-n50-npz
/root/fh-mahjong-runs/chongci-large-counterfactual-scorepressure-20260601-225427/data/anchor-scorepressure-seed-584000-n50-npz
/root/fh-mahjong-runs/chongci-direct-counterfactual-actionrisk-large-20260602-235548/data/counterfactual-gap005-npz
/root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz
```

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
checkpoint:
  /root/fh-mahjong-runs/chongci-stronger-familybalance-riskcritic-20260604-212437/checkpoints/future_context_fb050/epoch_001.pt
target_mode:
  future_outcome_context
future_context_window:
  12
future_context_score_pressure_weight:
  0.75
future_context_min_credit:
  0.35
family_balance_strength:
  0.50
family_weight_clip:
  6.0
positive_fraction:
  0.60
severity_weight:
  0.40
paired trace:
  /root/fh-mahjong-runs/chongci-direct-counterfactual-actionrisk-large-20260602-235548/reports/anchor_vs_candidate_tensor_trace.json
paired_margin_weight:
  1.0
paired_severity_weight:
  0.50
paired_margin:
  0.15
steps_per_epoch:
  500
batch_size:
  2048
learning_rate:
  5e-5
MLflow tracking URI:
  file:///root/fh-mahjong-mlruns
```

Training log ended with in-batch separation:

```text
step 500:
  loss=0.6054
  probability_loss=0.5702
  severity_loss=0.0787
  batch_positive_rate=46.1%
  positive_probability=0.666
  negative_probability=0.451
  paired_count=717
```

Calibration:

```text
data:
  /root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz
max_transitions:
  150000
report:
  /root/fh-mahjong-runs/chongci-stronger-familybalance-riskcritic-20260604-212437/reports/riskcritic_fb050_capped400k_calibration_150k.json
```

Result:

```text
overall:
  AUC=0.509609
  Brier=0.367835
  positive_mean_probability=0.621192
  negative_mean_probability=0.614801
discard:
  AUC=0.508306
  positive_mean_probability=0.641232
  negative_mean_probability=0.635552
pon:
  AUC=0.529279
kan:
  AUC=0.561398
pass:
  AUC=0.508965
win:
  AUC=0.545981
```

Baseline comparison on the same capped400k calibration protocol:

```text
previous future_context_fb025:
  overall AUC=0.509855
  Brier=0.270555
  positive_mean_probability=0.495633
  negative_mean_probability=0.490131
  discard AUC=0.508570
stronger fb050/window12:
  overall AUC=0.509609
  Brier=0.367835
  positive_mean_probability=0.621192
  negative_mean_probability=0.614801
  discard AUC=0.508306
```

Decision:

Rejected before tail-constrained serving/evaluation. The stronger run increased
probability scale and the positive/negative mean gap slightly, but independent
ranking did not improve: overall AUC and discard AUC are both lower than the
existing `fb025` critic, and Brier is much worse. This is overconfidence, not a
better risk model.

Interpretation:

Action-family-specific tolerance is available in the selector, but it should
not be used with this critic. The next risk-model step should change the label
or input signal, not simply increase family balance or future-context window
again. Good candidates are explicit later-trajectory supervision for
first-divergence states, separate discard/interruption risk heads, or critic-side
features that expose visible danger context more directly.

### Experiment: Family-Specific Future-Outcome Risk Critic

Run:

```text
/root/fh-mahjong-runs/chongci-family-context-riskcritic-20260604-233834
```

Question:

Can a different target signal improve risk-model sensitivity enough to make the
tail-constrained candidate selector useful? This run stops broad future-context
labeling and separates discard hindsight from interruption-decision hindsight.

Code change:

```text
target_mode:
  family_future_outcome_context
```

The new target keeps the existing checkpoint architecture and action-risk heads,
but changes the labels:

```text
discard actions:
  direct same-seat recent-discard hindsight before actual large loss or deal-in
chii/pon/kan/pass/haitei:
  separate lower-credit recent-action hindsight before actual large loss or deal-in
win actions:
  no auxiliary risk credit
```

This is intentionally different from `future_outcome_context`, where all recent
families shared one broad credit rule.

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
checkpoint:
  /root/fh-mahjong-runs/chongci-family-context-riskcritic-20260604-233834/checkpoints/family_context/epoch_001.pt
target_mode:
  family_future_outcome_context
future_context_window:
  8
future_context_score_pressure_weight:
  0.5
future_context_min_credit:
  0.35
family_balance_strength:
  0.25
positive_fraction:
  0.55
severity_weight:
  0.30
paired trace:
  /root/fh-mahjong-runs/chongci-direct-counterfactual-actionrisk-large-20260602-235548/reports/anchor_vs_candidate_tensor_trace.json
paired_margin_weight:
  0.5
paired_severity_weight:
  0.25
steps_per_epoch:
  500
batch_size:
  2048
learning_rate:
  5e-5
```

Training log ended with:

```text
step 500:
  loss=0.6433
  probability_loss=0.6139
  severity_loss=0.0789
  batch_positive_rate=46.4%
  positive_probability=0.579
  negative_probability=0.427
  paired_count=512
```

Calibration:

```text
data:
  /root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz
max_transitions:
  150000
report:
  /root/fh-mahjong-runs/chongci-family-context-riskcritic-20260604-233834/reports/riskcritic_family_context_capped400k_calibration_150k.json
```

Result:

```text
overall:
  AUC=0.515713
  Brier=0.299186
  positive_mean_probability=0.546971
  negative_mean_probability=0.538058
discard:
  AUC=0.514733
  positive_mean_probability=0.554814
  negative_mean_probability=0.546411
chii:
  AUC=0.522235
kan:
  AUC=0.565868
pass:
  AUC=0.514085
pon:
  AUC=0.508150
win:
  AUC=0.547209
```

Baseline comparison on the same capped400k calibration protocol:

```text
previous future_context_fb025:
  overall AUC=0.509855
  discard AUC=0.508570
failed fb050/window12:
  overall AUC=0.509609
  discard AUC=0.508306
family_future_outcome_context:
  overall AUC=0.515713
  discard AUC=0.514733
```

This passes the calibration-first gate. It is the best offline action-risk
ranking signal so far.

Tail-constrained smoke:

```text
anchor checkpoint:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
candidate checkpoint:
  /root/fh-mahjong-runs/chongci-iql-counterfactual-severity-pairwise-20260604-201002/checkpoints/severity_pairwise_q025_policy001_margin035/epoch_001.pt
risk checkpoint:
  /root/fh-mahjong-runs/chongci-family-context-riskcritic-20260604-233834/checkpoints/family_context/epoch_001.pt
seed window:
  660000:4
evaluated seats:
  16
```

Known anchor smoke on the same window:

```text
mean_reward=-0.368562
positive_reward_rate=43.75%
large_loss_rate=31.25%
```

Smoke results:

```text
discard tolerance 0.02:
  mean_reward=-0.371812
  positive_reward_rate=43.75%
  large_loss_rate=31.25%
  candidate_override_rate=0.0269%
  report=/root/fh-mahjong-runs/chongci-family-context-riskcritic-20260604-233834/reports/tail_constrained_family_context_smoke_660000_4_discard002.json

strict q_margin 0.0:
  mean_reward=-0.371812
  positive_reward_rate=43.75%
  large_loss_rate=31.25%
  candidate_override_rate=0.0269%
  report=/root/fh-mahjong-runs/chongci-family-context-riskcritic-20260604-233834/reports/tail_constrained_family_context_smoke_660000_4_strict_qsweep.json

strict q_margin 0.01:
  mean_reward=-0.371812
  positive_reward_rate=43.75%
  large_loss_rate=31.25%
  candidate_override_rate=0.0134%
  report=/root/fh-mahjong-runs/chongci-family-context-riskcritic-20260604-233834/reports/tail_constrained_family_context_smoke_660000_4_strict_qsweep.json
```

Decision:

Rejected for serving with the current candidate pair. The new target is a real
calibration improvement, but the constrained selector still loses EV to the
anchor on the small smoke while preserving the same positive and large-loss
rates. Do not run the larger gate for this anchor/candidate/risk combination.

Interpretation:

Keep `family_future_outcome_context`; it improved offline risk ranking and is
now the best diagnostic risk target. The remaining bottleneck is not risk
calibration alone. The current candidate policy has too few useful candidate
overrides under the no-worse-tail rule. The next experiment should either train
a new candidate that directly uses this family-context risk critic during IQL,
or build a candidate from states/actions where this critic shows confident
positive separation, instead of only filtering the old severity-pairwise
candidate at serving time.

### Experiment: IQL With Family-Context Risk Regularizer

Run:

```text
/root/fh-mahjong-runs/chongci-iql-family-riskreg-discard-20260604-234857
```

Question:

Can the calibrated `family_future_outcome_context` risk critic improve the
policy during reward learning, instead of only filtering an already-trained
candidate at serving time?

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
external risk checkpoint:
  /root/fh-mahjong-runs/chongci-family-context-riskcritic-20260604-233834/checkpoints/family_context/epoch_001.pt
checkpoint:
  /root/fh-mahjong-runs/chongci-iql-family-riskreg-discard-20260604-234857/checkpoints/riskreg_discard_t054_w050/epoch_001.pt
external_risk_policy_family:
  discard
external_risk_policy_threshold:
  0.54
external_risk_policy_weight:
  0.50
epochs:
  1
batch_size:
  4096
learning_rate:
  3e-5
max_transitions_per_dataset:
  150000
MLflow run id:
  c9e79c68c115495188eda0b3acae65c9
```

Data:

```text
/root/fh-mahjong-runs/chongci-iql-50scalar-200-20260521-082220/data/heuristic-chongci-50scalar-200-npz
/root/fh-mahjong-runs/chongci-mixed-selfplay-iql-50-20260521-211207/data/selfplay-iql-seat0-vs-heuristic-npz
/root/fh-mahjong-runs/chongci-mixed-selfplay-iql-200-seats02-20260521-234609/data/selfplay-iql-seats0-2-vs-heuristic-npz
/root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz
```

Training diagnostics:

```text
external risk policy loss stayed active:
  ~0.053 to 0.056
final avg loss:
  0.1751
final checkpoint:
  epoch_001.pt
```

Important correction:

The first smoke run omitted `--max-steps-per-episode`; those reports truncated
all episodes and returned zero rewards. They are invalid for model comparison.
All valid results below used:

```text
--max-steps-per-episode 20000
```

Direct serving smoke:

```text
seed window:
  660000:4
evaluated seats:
  16
candidate:
  mean_reward=-0.137688
  positive_reward_rate=56.25%
  large_loss_rate=31.25%
anchor:
  mean_reward=-0.368562
  positive_reward_rate=43.75%
  large_loss_rate=31.25%
candidate report:
  /root/fh-mahjong-runs/chongci-iql-family-riskreg-discard-20260604-234857/reports/candidate_smoke_660000_4_full.json
anchor report:
  /root/fh-mahjong-runs/chongci-iql-family-riskreg-discard-20260604-234857/reports/anchor_smoke_660000_4_full.json
```

Direct independent gate:

```text
seed window:
  660000:16
evaluated seats:
  64
candidate:
  mean_reward=-0.018328
  positive_reward_rate=48.44%
  large_loss_rate=18.75%
anchor:
  mean_reward=-0.132812
  positive_reward_rate=40.62%
  large_loss_rate=17.19%
delta candidate - anchor:
  mean_reward=+0.114484
  positive_reward_rate=+7.81pp
  large_loss_rate=+1.56pp
candidate report:
  /root/fh-mahjong-runs/chongci-iql-family-riskreg-discard-20260604-234857/reports/candidate_gate_660000_16_full.json
anchor report:
  /root/fh-mahjong-runs/chongci-iql-family-riskreg-discard-20260604-234857/reports/anchor_gate_660000_16_full.json
```

Direct-serving decision:

Rejected. The candidate has a real EV/positive-rate gain, but it violates the
current tail constraint because large-loss rate is worse than anchor.

Tail-constrained serving check:

```text
anchor checkpoint:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
candidate checkpoint:
  /root/fh-mahjong-runs/chongci-iql-family-riskreg-discard-20260604-234857/checkpoints/riskreg_discard_t054_w050/epoch_001.pt
risk checkpoint:
  /root/fh-mahjong-runs/chongci-family-context-riskcritic-20260604-233834/checkpoints/family_context/epoch_001.pt
seed window:
  660000:16
```

Result:

```text
q_margin=0.0:
  mean_reward=-0.142797
  positive_reward_rate=40.62%
  large_loss_rate=17.19%
  candidate_override_rate=0.1081%

q_margin=0.01:
  mean_reward=-0.142797
  positive_reward_rate=40.62%
  large_loss_rate=17.19%
  candidate_override_rate=0.1050%

anchor:
  mean_reward=-0.132812
  positive_reward_rate=40.62%
  large_loss_rate=17.19%
report:
  /root/fh-mahjong-runs/chongci-iql-family-riskreg-discard-20260604-234857/reports/tail_constrained_riskreg_candidate_gate_660000_16.json
```

Tail-constrained decision:

Rejected. The explicit selector restores the anchor large-loss rate, but it
also loses EV versus the anchor. This candidate should not go to the combined
repeated gate.

Interpretation:

This is useful evidence. The risk-regularized IQL branch can produce a stronger
EV candidate, unlike serving-time filtering of the older severity-pairwise
candidate. The unresolved issue is still tail risk: direct serving is EV-up but
tail-worse, while constrained serving is tail-safe but EV-down. The next branch
should tighten training-time tail control rather than rely on serving-time
filtering after training. Two concrete options:

```text
1. Increase training-side tail control mildly:
   keep external risk family=discard, threshold=0.54,
   add large_loss_bc_weight or reduce external-risk threshold to 0.535.

2. Train a two-candidate sweep:
   riskreg_discard_t054_w075 and riskreg_discard_t0535_w050,
   then keep only variants whose 660000:16 direct gate has large_loss_rate <= anchor.
```

### Experiment: Stronger Discard Risk-Regularizer Sweep

Run:

```text
/root/fh-mahjong-runs/chongci-iql-family-riskreg-sweep-20260605-002102
```

Question:

Can mild extra training-side tail control keep the EV gain from the
family-context risk-regularized IQL branch while removing the large-loss
regression seen in `riskreg_discard_t054_w050`?

Shared setup:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
external risk checkpoint:
  /root/fh-mahjong-runs/chongci-family-context-riskcritic-20260604-233834/checkpoints/family_context/epoch_001.pt
external risk family:
  discard
epochs:
  1
batch_size:
  4096
learning_rate:
  3e-5
max_transitions_per_dataset:
  150000
```

Candidates:

```text
riskreg_discard_t054_w075:
  external_risk_policy_threshold=0.54
  external_risk_policy_weight=0.75
  checkpoint=/root/fh-mahjong-runs/chongci-iql-family-riskreg-sweep-20260605-002102/checkpoints/riskreg_discard_t054_w075/epoch_001.pt
  MLflow run id=86b5203328124c77995e7e7a481ac8cb

riskreg_discard_t0535_w050:
  external_risk_policy_threshold=0.535
  external_risk_policy_weight=0.50
  checkpoint=/root/fh-mahjong-runs/chongci-iql-family-riskreg-sweep-20260605-002102/checkpoints/riskreg_discard_t0535_w050/epoch_001.pt
  MLflow run id=1b3388f8203147bdaa5fd574b13c9ffb
```

Direct `660000:16` gate:

```text
anchor:
  mean_reward=-0.132812
  positive_reward_rate=40.62%
  large_loss_rate=17.19%

riskreg_discard_t054_w075:
  mean_reward=-0.003938
  positive_reward_rate=48.44%
  large_loss_rate=17.19%
  delta_mean_reward=+0.128875
  delta_positive_reward_rate=+7.81pp
  delta_large_loss_rate=+0.00pp
  report=/root/fh-mahjong-runs/chongci-iql-family-riskreg-sweep-20260605-002102/reports/riskreg_discard_t054_w075_gate_660000_16_full.json

riskreg_discard_t0535_w050:
  mean_reward=-0.018328
  positive_reward_rate=48.44%
  large_loss_rate=18.75%
  delta_mean_reward=+0.114484
  delta_positive_reward_rate=+7.81pp
  delta_large_loss_rate=+1.56pp
  report=/root/fh-mahjong-runs/chongci-iql-family-riskreg-sweep-20260605-002102/reports/riskreg_discard_t0535_w050_gate_660000_16_full.json
```

Decision after `660000:16`:

```text
riskreg_discard_t0535_w050:
  rejected for tail regression
riskreg_discard_t054_w075:
  advanced to combined gate
```

Important correction:

The first combined-gate run:

```text
/root/fh-mahjong-runs/chongci-iql-family-riskreg-t054w075-combined-gate-20260605-003157
```

is invalid because `--online-episodes` was omitted. Both reports had
`online=null` and must not be used.

Corrected combined gate:

```text
/root/fh-mahjong-runs/chongci-iql-family-riskreg-t054w075-combined-gate-20260605-003448
seed windows:
  534000:10
  544000:10
  554000:10
evaluated seats:
  120
online episodes flag:
  --online-episodes 30
```

Result:

```text
anchor:
  mean_reward=-0.055675
  positive_reward_rate=42.50%
  large_loss_rate=15.00%
  report=/root/fh-mahjong-runs/chongci-iql-family-riskreg-t054w075-combined-gate-20260605-003448/reports/anchor_combined_gate_534_544_554_n10.json

riskreg_discard_t054_w075:
  mean_reward=-0.067108
  positive_reward_rate=43.33%
  large_loss_rate=17.50%
  report=/root/fh-mahjong-runs/chongci-iql-family-riskreg-t054w075-combined-gate-20260605-003448/reports/candidate_combined_gate_534_544_554_n10.json

delta candidate - anchor:
  mean_reward=-0.011433
  positive_reward_rate=+0.83pp
  large_loss_rate=+2.50pp
summary=/root/fh-mahjong-runs/chongci-iql-family-riskreg-t054w075-combined-gate-20260605-003448/reports/combined_gate_summary.json
```

Decision:

Rejected. `riskreg_discard_t054_w075` was promising on `660000:16`, but the
larger combined gate showed both EV regression and tail-risk regression. Do not
promote it.

Interpretation:

The family-context risk critic can create EV-up candidates, and the `0.54/0.75`
variant briefly satisfied the independent `660000:16` tail guard, but the effect
does not generalize across the larger gate. Further scalar threshold/weight
sweeps are unlikely to be high-value unless the evaluation target changes.
Prefer the next branch to add a direct training constraint on large-loss
transitions, for example combining the discard risk regularizer with
`large_loss_bc_weight`, or move to a larger data refresh before repeating this
family.

### Experiment: Discard Risk Regularizer Plus Large-Loss BC

Run:

```text
/root/fh-mahjong-runs/chongci-iql-riskreg-llbc-combined-20260605-011915
```

Question:

Can direct large-loss transition preservation fix the tail regression from the
otherwise promising `riskreg_discard_t054_w075` candidate?

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
external risk checkpoint:
  /root/fh-mahjong-runs/chongci-family-context-riskcritic-20260604-233834/checkpoints/family_context/epoch_001.pt
checkpoint:
  /root/fh-mahjong-runs/chongci-iql-riskreg-llbc-combined-20260605-011915/checkpoints/riskreg_discard_t054_w075_llbc050/epoch_001.pt
external_risk_policy_family:
  discard
external_risk_policy_threshold:
  0.54
external_risk_policy_weight:
  0.75
large_loss_threshold:
  -1.0
large_loss_bc_weight:
  0.50
epochs:
  1
batch_size:
  4096
learning_rate:
  3e-5
max_transitions_per_dataset:
  150000
MLflow run id:
  074977cb205441ec930f3d2946f43bb3
```

Training diagnostics:

```text
large-loss BC term was active:
  ll_bc about 0.0406 to 0.0654
  large-loss rows per logged batch about 645 to 691
external risk term stayed active:
  ext_risk about 0.0534 to 0.0558
final avg loss:
  0.2159
```

Evaluation:

The branch skipped the smaller `660000:16` screen and went directly to the
combined decision gate, per the updated protocol.

```text
seed windows:
  534000:10
  544000:10
  554000:10
evaluated seats:
  120
candidate report:
  /root/fh-mahjong-runs/chongci-iql-riskreg-llbc-combined-20260605-011915/reports/riskreg_discard_t054_w075_llbc050_combined_gate_534_544_554_n10.json
anchor report:
  /root/fh-mahjong-runs/chongci-iql-family-riskreg-t054w075-combined-gate-20260605-003448/reports/anchor_combined_gate_534_544_554_n10.json
```

Result:

```text
anchor:
  mean_reward=-0.055675
  positive_reward_rate=42.50%
  large_loss_rate=15.00%

riskreg_discard_t054_w075_llbc050:
  mean_reward=-0.081767
  positive_reward_rate=43.33%
  large_loss_rate=20.00%

delta candidate - anchor:
  mean_reward=-0.026092
  positive_reward_rate=+0.83pp
  large_loss_rate=+5.00pp
```

Decision:

Rejected. `large_loss_bc_weight=0.50` did not fix the tail issue. It worsened
both EV and large-loss rate on the combined gate, even though the large-loss BC
term was active during training.

Interpretation:

This closes the simple "add large-loss BC on top of discard risk regularizer"
branch for now. The current dataset/model combination is not giving a stable
tail-safe improvement through scalar loss additions. Next higher-value move is
data refresh or more targeted data construction: generate new mixed self-play
from the best anchor and the EV-up-but-tail-worse candidates, then train on
states where the combined gate actually diverges, rather than adding another
global scalar loss.

### Experiment: Targeted Combined-Gate Divergence Data

Run:

```text
/root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622
```

Question:

Can fresh self-play from the promoted anchor plus the EV-up/tail-worse
candidates fix the failure mode without adding another broad scalar penalty?
This branch intentionally stopped stacking `external_risk_policy_weight`,
`large_loss_bc_weight`, and other global loss terms. It instead trained only
from actual combined-gate divergence states plus local decision context.

Policy sources:

```text
anchor:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
riskreg_discard_t054_w075:
  /root/fh-mahjong-runs/chongci-iql-family-riskreg-sweep-20260605-002102/checkpoints/riskreg_discard_t054_w075/epoch_001.pt
riskreg_discard_t054_w050:
  /root/fh-mahjong-runs/chongci-iql-family-riskreg-discard-20260604-234857/checkpoints/riskreg_discard_t054_w050/epoch_001.pt
riskreg_discard_t0535_w050:
  /root/fh-mahjong-runs/chongci-iql-family-riskreg-sweep-20260605-002102/checkpoints/riskreg_discard_t0535_w050/epoch_001.pt
```

Paired traces:

```text
seed windows:
  534000:10
  544000:10
  554000:10
seats:
  0, 1, 2, 3
max_steps_per_episode:
  20000

anchor vs riskreg_discard_t054_w075:
  report=/root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/reports/anchor_vs_t054w075_combined_trace.json
  divergence_rate=92.50%
  candidate_better_rate=31.67%
  mean_delta=-0.011433
  candidate_large_loss_cases=21
  new_candidate_large_loss_cases=3

anchor vs riskreg_discard_t054_w050:
  report=/root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/reports/anchor_vs_t054w050_combined_trace.json
  divergence_rate=91.67%
  candidate_better_rate=30.83%
  mean_delta=-0.013375
  candidate_large_loss_cases=20
  new_candidate_large_loss_cases=2

anchor vs riskreg_discard_t0535_w050:
  report=/root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/reports/anchor_vs_t0535w050_combined_trace.json
  divergence_rate=91.67%
  candidate_better_rate=30.83%
  mean_delta=-0.013375
  candidate_large_loss_cases=20
  new_candidate_large_loss_cases=2
```

Fresh mixed data:

```text
seat 0:
  anchor checkpoint
seat 1:
  riskreg_discard_t054_w075
seat 2:
  riskreg_discard_t054_w050
seat 3:
  riskreg_discard_t0535_w050

/root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/data/mixed-anchor-candidates-534000-n10-npz
  transitions=20095
/root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/data/mixed-anchor-candidates-544000-n10-npz
  transitions=21123
/root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/data/mixed-anchor-candidates-554000-n10-npz
  transitions=20124
```

Code fix discovered during this run:

`load_risk_cases_from_paired_trace_reports` assumed reward keys like
`candidate_reward`. Named reports from this experiment used keys like
`candidate_t054_w075_reward`. The loader now reads `left_label` and
`right_label` from each report before loading rewards and counterfactual labels.

Training variant 1:

```text
checkpoint:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/checkpoints/targeted_divergence_q025_context2/epoch_001.pt
base data:
  /root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz
filtered data:
  the three fresh mixed self-play shards above
risk trace reports:
  the three anchor-vs-candidate combined traces above
risk_trace_filter_datasets:
  true
risk_trace_context_radius:
  2
pairwise_q_weight:
  0.25
pairwise_q_margin:
  0.10
pairwise_replay_multiplier:
  0
MLflow run id:
  8937d164eb1d4b5995f35be9cf810ff6
```

Training diagnostics:

```text
matched cases:
  7 + 6 + 6 across the three fresh shards
filtered context rows:
  9 + 8 + 10
logged pairwise_count:
  0
```

Evaluation:

```text
report:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/reports/targeted_divergence_q025_context2_combined_gate_534_544_554_n10.json
mean_reward:
  -0.072475
positive_reward_rate:
  42.50%
large_loss_rate:
  17.50%
```

Training variant 2:

```text
checkpoint:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/checkpoints/targeted_divergence_q025_context2_replay512/epoch_001.pt
same base data, filtered data, and trace reports as variant 1
pairwise_q_weight:
  0.25
pairwise_q_margin:
  0.10
pairwise_replay_multiplier:
  512
MLflow run id:
  73fe54f4b7f34b5a9da8bb2a71f0458b
```

Training diagnostics:

```text
matched cases:
  7 + 6 + 6 across the three fresh shards
pairwise replay rows:
  3584 + 2560 + 3072
logged pairwise_count:
  about 62 to 71 per logged batch
pairwise_q_loss:
  non-zero early, then 0.0 after the Q margin was satisfied
```

Evaluation:

```text
seed windows:
  534000:10
  544000:10
  554000:10
evaluated seats:
  120
report:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/reports/targeted_divergence_q025_context2_replay512_combined_gate_534_544_554_n10.json
MLflow eval run id:
  2c35a77530154319aad94b80243de12b
```

Result:

```text
anchor:
  mean_reward=-0.055675
  positive_reward_rate=42.50%
  large_loss_rate=15.00%

targeted_divergence_q025_context2:
  mean_reward=-0.072475
  positive_reward_rate=42.50%
  large_loss_rate=17.50%

targeted_divergence_q025_context2_replay512:
  mean_reward=-0.045225
  positive_reward_rate=44.17%
  large_loss_rate=16.67%
```

Decision:

Rejected for promotion. The replay-expanded targeted variant is the best result
from this branch because it improves EV and positive-rate versus the anchor,
but it still violates the explicit tail constraint: candidate large-loss rate
is `16.67%` versus anchor `15.00%`.

Interpretation:

The branch confirmed that using actual combined-gate divergence states is more
useful than another global loss stack: replay512 recovered EV and positive-rate
without an external risk regularizer or large-loss BC. However, the matched
state set is too small and still does not control large-loss probability. The
next useful move is not another scalar coefficient sweep. Either generate a
larger aligned mixed dataset for the same anchor/candidate family so exact
divergence coverage is not only 19 cases, or turn the paired traces into a
direct counterfactual NPZ auxiliary dataset with enough rows to enforce
tail-safe action preferences.

### Experiment: Direct Counterfactual Combined-Gate Pairwise IQL

Run:

```text
/root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622
```

Question:

Can direct tensor-bearing counterfactual rows from the combined-gate paired
traces train the reward policy better than sparse exact replay matching? This
keeps the same principle as the prior branch: use the actual failure states
from the combined gate, not another global scalar loss stack.

Code/tooling:

`build_counterfactual_risk_data.py` now reads each paired trace report's
stored `left_label` and `right_label`, so named candidates such as
`candidate_t054_w075` resolve reward/outcome keys correctly. Regression test:
`ai/tests/test_build_counterfactual_risk_data.py`.

Direct auxiliary data:

```text
source traces:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/reports/anchor_vs_t054w075_combined_trace.json
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/reports/anchor_vs_t054w050_combined_trace.json
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/reports/anchor_vs_t0535w050_combined_trace.json
min_reward_gap:
  0.10
large_loss_threshold:
  -1.0

/root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/data/direct-counterfactual-gap010/t054w075
  rows=48
  mean_reward_gap=0.380438
  max_reward_gap=1.312000
  positive_terminal_rows=4

/root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/data/direct-counterfactual-gap010/t054w050
  rows=47
  mean_reward_gap=0.387298
  max_reward_gap=1.312000
  positive_terminal_rows=4

/root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/data/direct-counterfactual-gap010/t0535w050
  rows=47
  mean_reward_gap=0.387298
  max_reward_gap=1.312000
  positive_terminal_rows=4
```

Training:

```text
checkpoint:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/checkpoints/direct_cf_gap010_q025_policy001_severity/epoch_001.pt
init checkpoint:
  /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
base data:
  /root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz
pairwise auxiliary repeats:
  64 per direct shard
pairwise_q_weight / margin:
  0.25 / 0.10
pairwise_weight / margin:
  0.01 / 0.05
pairwise_reward_delta_weight:
  0.50
pairwise_reward_delta_margin_scale:
  0.20
pairwise_reward_delta_clip:
  2.0
epochs:
  1
batch_size:
  4096
learning_rate:
  3e-5
MLflow run id:
  371bd8057c5f488b92d01e7838392a98
```

Training diagnostics:

```text
logged pairwise_count:
  about 226 to 241 per logged batch
pairwise_q_loss:
  0.1089 at step 10
  0.0339 at step 20
  0.0095 at step 30
pairwise policy loss:
  near 0.0 after the policy margin was satisfied
```

Evaluation:

```text
seed windows:
  534000:10
  544000:10
  554000:10
duplicate seats:
  true
evaluated seats:
  120
candidate report:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/reports/direct_cf_gap010_q025_policy001_severity_combined_gate_534_544_554_n10.json
candidate repeat report:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/reports/repeated_gate_direct_cf_gap010_q025_policy001_severity/candidate_repeat2.json
anchor refresh report:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/reports/repeated_gate_direct_cf_gap010_q025_policy001_severity/anchor_refresh.json
previous anchor report:
  /root/fh-mahjong-runs/chongci-iql-family-riskreg-t054w075-combined-gate-20260605-003448/reports/anchor_combined_gate_534_544_554_n10.json
MLflow eval run id:
  c428c0d6a3b0475aacbf9ebc21427135
```

Result:

```text
previous Chongci anchor:
  mean_reward=-0.055675
  positive_reward_rate=42.50%
  large_loss_rate=15.00%
  reward_sum=-6.681002

direct_cf_gap010_q025_policy001_severity:
  mean_reward=-0.002317
  positive_reward_rate=45.00%
  large_loss_rate=14.17%
  reward_sum=-0.278000

delta candidate - previous anchor:
  mean_reward=+0.053358
  positive_reward_rate=+2.50pp
  large_loss_rate=-0.83pp
```

Determinism check:

```text
candidate repeat 1:
  mean_reward=-0.002317
  positive_reward_rate=45.00%
  large_loss_rate=14.17%
  reward_sum=-0.278000

candidate repeat 2:
  mean_reward=-0.002317
  positive_reward_rate=45.00%
  large_loss_rate=14.17%
  reward_sum=-0.278000

anchor prior:
  mean_reward=-0.055675
  positive_reward_rate=42.50%
  large_loss_rate=15.00%
  reward_sum=-6.681002

anchor refresh:
  mean_reward=-0.055675
  positive_reward_rate=42.50%
  large_loss_rate=15.00%
  reward_sum=-6.681002
```

Decision:

Promoted as the current Chongci reward-trained best. It improves EV and
positive rate while reducing large-loss rate on the deterministic combined
gate, and both candidate and anchor repeats matched exactly.

Interpretation:

This is the first branch in the recent tail-control work that passed the
explicit tail constraint. The useful ingredient was not more scalar loss
stacking; it was direct counterfactual supervision from tensor-bearing
combined-gate first-divergence states, with reward-gap severity shaping. Next
steps should build on this promoted checkpoint with a larger direct
counterfactual dataset or a fresh self-play iteration using this checkpoint as
one of the table policies.

### Experiment: Promoted Anchor Self-Play And Larger Direct-CF Follow-Up

Run:

```text
self-play:
  /root/fh-mahjong-runs/chongci-promoted-anchor-selfplay-20260605-185613-bridgefix
larger direct counterfactual data:
  /root/fh-mahjong-runs/chongci-larger-direct-cf-20260605-185614-bridgefix
larger direct counterfactual IQL repeat32:
  /root/fh-mahjong-runs/chongci-larger-direct-cf-iql-20260605-213733
larger direct counterfactual IQL repeat8:
  /root/fh-mahjong-runs/chongci-larger-direct-cf-iql-lowdose-20260605-214843
```

Question:

After promoting `direct_cf_gap010_q025_policy001_severity`, can we improve the
new anchor by either:

1. starting a fresh mixed self-play iteration using the promoted checkpoint as
   one table policy, or
2. building a larger direct counterfactual dataset from fresh candidate-vs-anchor
   divergence windows?

Data:

```text
self-play data:
  /root/fh-mahjong-runs/chongci-promoted-anchor-selfplay-20260605-185613-bridgefix/data/promoted-anchor-mixed-720000-n200-npz
  transitions=409337

self-play table policies:
  seat 0: promoted direct-CF checkpoint
  seat 1: previous iql_lowlr_selfplay200_epoch003 anchor
  seat 2: promoted direct-CF checkpoint
  seat 3: riskreg_discard_t054_w075

larger direct-CF paired trace windows:
  664000:20
  674000:20
  684000:20
seats:
  0, 1, 2, 3
trace pairs per comparison:
  240
```

Larger direct-CF trace summaries:

```text
promoted_anchor vs previous_anchor:
  divergence_rate=88.75%
  previous_anchor_better_rate=32.50%
  mean_delta=-0.0219

promoted_anchor vs riskreg_t054_w075:
  divergence_rate=96.25%
  riskreg_t054_w075_better_rate=35.00%
  mean_delta=-0.0192

promoted_anchor vs riskreg_t054_w050:
  divergence_rate=96.25%
  riskreg_t054_w050_better_rate=35.42%
  mean_delta=-0.0175

promoted_anchor vs riskreg_t0535_w050:
  divergence_rate=96.25%
  riskreg_t0535_w050_better_rate=35.00%
  mean_delta=-0.0192
```

Larger direct-CF rows:

```text
gap010:
  previous_anchor rows=96, positive_terminal_rows=23, mean_reward_gap=0.4724
  t054w075 rows=107, positive_terminal_rows=26, mean_reward_gap=0.4839
  t054w050 rows=108, positive_terminal_rows=27, mean_reward_gap=0.4823
  t0535w050 rows=108, positive_terminal_rows=27, mean_reward_gap=0.4823
  total rows=419

gap005:
  previous_anchor rows=124, positive_terminal_rows=27, mean_reward_gap=0.3814
  t054w075 rows=134, positive_terminal_rows=31, mean_reward_gap=0.4013
  t054w050 rows=136, positive_terminal_rows=32, mean_reward_gap=0.3981
  t0535w050 rows=136, positive_terminal_rows=32, mean_reward_gap=0.3981
  total rows=530
```

Training:

```text
self-play iter1:
  init_checkpoint=/root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/checkpoints/direct_cf_gap010_q025_policy001_severity/epoch_001.pt
  epochs=2
  lr=2e-5
  max_transitions=200000
  direct-CF auxiliary=old gap010 shards repeated 32x
  MLflow run id=337ced55f30c4fe3a892410220769730

larger direct-CF repeat32:
  init_checkpoint=/root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/checkpoints/direct_cf_gap010_q025_policy001_severity/epoch_001.pt
  direct-CF auxiliary=new gap010 shards repeated 32x
  pairwise_q_weight=0.25
  pairwise_q_margin=0.10
  pairwise_weight=0.01
  pairwise_margin=0.05
  pairwise_reward_delta_weight=0.50
  pairwise_reward_delta_margin_scale=0.20
  max_transitions=150000
  MLflow run id=be146174b8af4118b015a6b2affa281a

larger direct-CF repeat8:
  same as repeat32, but new gap010 shards repeated 8x
  MLflow run id=b9093a024d83463387516716e64193c6
```

Evaluation:

```text
seed windows:
  534000:10
  544000:10
  554000:10
duplicate seats:
  true
evaluated seats:
  120
```

Result:

| checkpoint | mean reward | reward sum | positive rate | large-loss rate |
| --- | ---: | ---: | ---: | ---: |
| promoted anchor | -0.0023 | -0.2780 | 45.00% | 14.17% |
| promoted-anchor self-play iter1 epoch2 | -0.0461 | -5.5380 | 46.67% | 15.00% |
| larger direct-CF gap010 repeat32 | -0.0581 | -6.9720 | 43.33% | 16.67% |
| larger direct-CF gap010 repeat8 | -0.0367 | -4.4100 | 44.17% | 15.83% |

Decision:

Rejected. None of the follow-up checkpoints beat the promoted direct-CF anchor.
The repeat8 run was less damaging than repeat32, but it still violated the
explicit tail guard and lost EV versus the promoted checkpoint.

Interpretation:

The promoted checkpoint remains the current Chongci reward-trained best. Simply
adding more direct-CF rows from the same EV-up/tail-worse candidate family does
not improve the promoted policy when training starts from that promoted policy.
The direct-CF mechanism is still valid because it produced the promoted anchor,
but this larger follow-up data appears to pull the policy back toward rejected
candidate behavior. Do not keep sweeping replay repeats for this exact larger
gap010 setup. The next useful branch needs a different target construction,
such as filtering direct-CF rows to cases where the promoted anchor is the
preferred action, separating action families, or building a new divergence set
against genuinely new candidates rather than the already-rejected riskreg family.

### Experiment: Anchor-Preferred High-Risk Direct-CF Filter

Run:

```text
filtered direct-CF data:
  /root/fh-mahjong-runs/chongci-anchor-preferred-direct-cf-20260605-231142
IQL candidate:
  /root/fh-mahjong-runs/chongci-anchor-preferred-highrisk-iql-20260605-231252
```

Question:

Can the larger direct-CF follow-up become useful if we stop training on
candidate-preferred rows from rejected policies and keep only rows where the
current promoted anchor was the better policy? A high-risk-only subset was used
for the training run so the auxiliary target focused on avoided large-loss /
deal-in cases rather than broad policy preservation.

Code/tooling:

`build_counterfactual_risk_data.py` now supports:

```text
--preferred-policy <label>
```

This keeps only rows where the paired-trace counterfactual label selected that
policy as the preferred side. Regression coverage:
`ai/tests/test_build_counterfactual_risk_data.py`.

Filtered data:

```text
anchor-preferred gap010 rows:
  previous_anchor: 50
  t054w075: 54
  t054w050: 54
  t0535w050: 54
  total: 212

anchor-preferred high-risk gap010 rows:
  previous_anchor: 11
  t054w075: 13
  t054w050: 13
  t0535w050: 13
  total: 50

anchor-preferred gap005 rows:
  previous_anchor: 61
  t054w075: 65
  t054w050: 65
  t0535w050: 65
  total: 256

anchor-preferred high-risk gap005 rows:
  previous_anchor: 11
  t054w075: 15
  t054w050: 15
  t0535w050: 15
  total: 56
```

Training:

```text
checkpoint:
  /root/fh-mahjong-runs/chongci-anchor-preferred-highrisk-iql-20260605-231252/checkpoints/anchor_preferred_highrisk_gap010_q025_policy001_severity_repeat64/epoch_001.pt
init checkpoint:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/checkpoints/direct_cf_gap010_q025_policy001_severity/epoch_001.pt
pairwise data:
  anchor-preferred high-risk gap010 shards repeated 64x
pairwise_q_weight / margin:
  0.25 / 0.10
pairwise_weight / margin:
  0.01 / 0.05
pairwise_reward_delta_weight:
  0.50
pairwise_reward_delta_margin_scale:
  0.20
MLflow run id:
  48253a5edff2409d880406f24ecae982
```

Training diagnostics:

```text
logged pairwise_count:
  75 to 88
pairwise_q_loss:
  0.1122 at step 10
  0.0517 at step 20
  0.0216 at step 30
```

Evaluation:

```text
seed windows:
  534000:10
  544000:10
  554000:10
duplicate seats:
  true
evaluated seats:
  120
report:
  /root/fh-mahjong-runs/chongci-anchor-preferred-highrisk-iql-20260605-231252/reports/anchor_preferred_highrisk_gap010_repeat64_combined_gate_534_544_554_n10.json
MLflow eval run id:
  640996c532674f008e4bef20f58bdee3
```

Result:

| checkpoint | mean reward | reward sum | positive rate | large-loss rate |
| --- | ---: | ---: | ---: | ---: |
| promoted anchor | -0.0023 | -0.2780 | 45.00% | 14.17% |
| anchor-preferred high-risk gap010 repeat64 | -0.0624 | -7.4860 | 43.33% | 17.50% |

Decision:

Rejected. Filtering to promoted-anchor-preferred high-risk rows did not fix the
larger direct-CF family. It worsened EV and tail risk more than the all-row
repeat8 candidate.

Interpretation:

This closes the "same rejected candidate family + pairwise IQL target"
direction for now. Even when rows only reinforce the promoted anchor on
high-risk divergences, the resulting Q/policy update moves the deployed greedy
policy in a worse direction. The issue is likely not just candidate-preferred
rows; the offline pairwise objective is too blunt for these sparse
first-divergence contexts once the promoted checkpoint is already strong.

Next useful branch:

1. Analyze the rejected candidate's first-divergence families and large-loss
   seeds to find whether one action family, especially discard, is responsible.
2. Build an action-family-specific target only if that analysis identifies a
   narrow failure mode.
3. Otherwise generate a genuinely new candidate family or move to critic-side
   diagnostics instead of more pairwise IQL target variants.

### Diagnostic: Larger Direct-CF Tail-Failure Shape

Run:

```text
remote diagnostic JSON:
  /tmp/chongci_tail_diagnostic_20260606.json
paired-trace source:
  /root/fh-mahjong-runs/chongci-larger-direct-cf-20260605-185614-bridgefix/reports
evaluation reports:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/reports/direct_cf_gap010_q025_policy001_severity_combined_gate_534_544_554_n10.json
  /root/fh-mahjong-runs/chongci-promoted-anchor-selfplay-20260605-185613-bridgefix/reports/promoted_anchor_selfplay_iter1_epoch002_combined_gate_534_544_554_n10.json
  /root/fh-mahjong-runs/chongci-larger-direct-cf-iql-20260605-213733/reports/larger_direct_cf_gap010_q025_policy001_severity_combined_gate_534_544_554_n10.json
  /root/fh-mahjong-runs/chongci-larger-direct-cf-iql-lowdose-20260605-214843/reports/larger_direct_cf_gap010_repeat8_q025_policy001_severity_combined_gate_534_544_554_n10.json
  /root/fh-mahjong-runs/chongci-anchor-preferred-highrisk-iql-20260605-231252/reports/anchor_preferred_highrisk_gap010_repeat64_combined_gate_534_544_554_n10.json
```

Question:

Before training another branch, do the rejected follow-up candidates show a
narrow action-family failure that justifies an action-family-specific risk
target?

Method:

The diagnostic reused existing `paired_trace.py` first-divergence summaries and
combined-gate evaluation reports. It compared:

- counterfactual preferred/avoided action families in the larger direct-CF
  paired traces,
- high-risk first-divergence labels,
- large-loss seed/seat sets for the promoted anchor and rejected follow-ups,
- action-family rates inside large-loss episodes.

First-divergence label summary:

| avoided action family | all labels | high-risk labels |
| --- | ---: | ---: |
| discard | 641 | 141 |
| chii | 35 | 16 |
| pass | 19 | 7 |
| pon | 1 | 0 |

Top preferred-to-avoided family pairs:

| preferred -> avoided | count |
| --- | ---: |
| discard -> discard | 641 |
| pass -> chii | 23 |
| chii -> chii | 12 |
| chii -> pass | 11 |
| pon -> pass | 8 |
| pass -> pon | 1 |

Tag counts:

| tag | count |
| --- | ---: |
| worse_reward | 696 |
| avoided_large_loss | 164 |
| new_large_loss | 61 |

Combined-gate tail comparison:

| checkpoint | mean reward | large-loss rate | added large losses vs anchor | recovered large losses vs anchor |
| --- | ---: | ---: | ---: | ---: |
| promoted anchor | -0.0023 | 14.17% | 0 | 0 |
| self-play iter1 epoch002 | -0.0461 | 15.00% | 3 | 2 |
| larger direct-CF repeat32 | -0.0581 | 16.67% | 5 | 2 |
| larger direct-CF repeat8 | -0.0367 | 15.83% | 4 | 2 |
| anchor-preferred high-risk repeat64 | -0.0624 | 17.50% | 5 | 1 |

Repeated added large-loss seed/seats:

```text
self-play iter1 epoch002:
  534000:1, 534002:0, 534005:2
larger direct-CF repeat32:
  534000:1, 534002:0, 534005:2, 544009:1, 554004:3
larger direct-CF repeat8:
  534000:1, 534002:0, 544009:1, 554004:3
anchor-preferred high-risk repeat64:
  534000:0, 534000:1, 534002:0, 534002:1, 544009:1
```

Large-loss action-family rates were nearly identical to the anchor. The largest
differences were on the order of a few tenths of a percentage point, not a clear
family-level behavioral shift:

```text
promoted anchor large-loss family rates:
  discard 78.98%, pass 11.64%, chii 4.18%, pon 2.93%, win 1.91%, kan 0.35%

larger direct-CF repeat8 large-loss family deltas vs anchor:
  discard +0.21 pp, pass -0.33 pp, chii +0.10 pp, pon +0.03 pp, kan +0.03 pp

anchor-preferred high-risk repeat64 large-loss family deltas vs anchor:
  discard +0.14 pp, pass -0.05 pp, chii -0.10 pp, pon -0.06 pp, kan +0.03 pp
```

Decision:

Do not start an action-family-specific risk calibration branch from these
aggregate reports. The first-divergence labels are mostly discard-vs-discard,
but the rejected checkpoints do not show a meaningful aggregate action-family
rate shift in the large-loss episodes. A broad "penalize discard risk harder"
target would likely repeat the same scalar-loss problem under a narrower name.

Interpretation:

The failure is seed-local and context-specific, not family-global. The repeated
new large losses cluster around a small set of seed/seats, especially
`534000:1`, `534002:0`, and `544009:1`. The next useful data product is an
exact first-divergence inspection for those added large-loss cases: state
scalars, legal mask, chosen action ids, action logits/Q deltas, and downstream
reward. Only after that should we decide whether the issue is discard danger,
call/pass timing, score-pressure miscalibration, or a value overestimate.

Next useful branch:

1. Build a small deterministic failure-slice report for the repeated added
   large-loss seed/seats.
2. Include first-divergence action ids, action families, selected tile ids,
   visible score-pressure scalars, shanten/ukeire scalars, top masked Q actions,
   and final reward deltas.
3. Train only if the failure-slice report shows a stable pattern. Otherwise
   generate a genuinely new candidate family rather than continuing the larger
   direct-CF pairwise line.

### Diagnostic: Repeated Added-Loss Failure Slice

Run:

```text
remote run:
  /root/fh-mahjong-runs/chongci-failure-slice-20260606
reports:
  /root/fh-mahjong-runs/chongci-failure-slice-20260606/reports/promoted_anchor_vs_larger_direct_cf_repeat8_failure_slice.json
  /root/fh-mahjong-runs/chongci-failure-slice-20260606/reports/promoted_anchor_vs_anchor_preferred_highrisk_repeat64_failure_slice.json
compact summaries:
  /tmp/chongci_failure_slice_summary_20260606.json
  /tmp/chongci_failure_slice_q_summary_20260606.json
```

Question:

On the repeated added large-loss seed/seats, what exactly changes at the first
divergence? Is the problem broad family selection, Q/value ranking, or small
policy-logit flips between discard choices?

Seed/seat slice:

```text
seeds:
  534000, 534002, 534005, 544009, 554004
seats:
  0, 1, 2, 3
episodes per comparison:
  20
```

Result:

| comparison | divergence rate | candidate better rate | mean reward delta |
| --- | ---: | ---: | ---: |
| promoted anchor vs larger direct-CF repeat8 | 95.00% | 15.00% | -0.1418 |
| promoted anchor vs anchor-preferred high-risk repeat64 | 95.00% | 20.00% | -0.1885 |

First-divergence families:

| comparison | family pairs |
| --- | --- |
| repeat8 | `discard->discard: 16`, `chii->pass: 2`, `pon->pass: 1` |
| anchor-preferred high-risk | `discard->discard: 16`, `chii->pass: 2`, `pon->pass: 1` |

Counterfactual labels:

| comparison | labeled pairs | high-risk pairs | avoided family summary |
| --- | ---: | ---: | --- |
| repeat8 | 15 | 5 | `discard: 12`, `pass: 2`, `pon: 1` |
| anchor-preferred high-risk | 14 | 6 | `discard: 11`, `pass: 2`, `pon: 1` |

Worst first-divergence examples:

| comparison | seed:seat | anchor reward | candidate reward | delta | anchor action | candidate action |
| --- | --- | ---: | ---: | ---: | --- | --- |
| repeat8 | 534005:3 | 0.863 | -0.375 | -1.238 | discard 3p | discard 3z |
| repeat8 | 534000:0 | -0.359 | -0.907 | -0.548 | discard 3m | discard 9s |
| repeat8 | 554004:0 | 0.195 | -0.263 | -0.458 | discard 1z | discard 4s |
| anchor-preferred high-risk | 534002:1 | 0.987 | -1.278 | -2.265 | discard 3s | discard 2s |
| anchor-preferred high-risk | 554004:0 | 0.195 | -0.585 | -0.780 | discard 4m | discard 3s |
| anchor-preferred high-risk | 534000:0 | -0.359 | -1.095 | -0.736 | discard 4p | discard 2s |

Policy/Q readout:

The deployed action is selected by masked policy logits, not by the Q head. In
the worst failure states, the follow-up checkpoints mostly flip the top two
policy-logit discards:

```text
repeat8, 534000:0:
  anchor policy top:    discard 3m, discard 9s, discard 1s
  candidate policy top: discard 9s, discard 3m, discard 1s

repeat8, 554004:0:
  anchor policy top:    discard 1z, discard 4s, discard 9s
  candidate policy top: discard 4s, discard 1z, discard 9s

anchor-preferred high-risk, 534002:1:
  anchor policy top:    discard 3s, discard 2s, discard 1m
  candidate policy top: discard 2s, discard 3s, discard 1m

anchor-preferred high-risk, 544009:1:
  anchor policy top:    discard 6s, discard 7m, discard 7s
  candidate policy top: discard 7m, discard 6s, discard 7s
```

The Q head does not consistently explain these served-action flips. For
example, on `534000:0` in the repeat8 slice, the candidate action had higher
anchor-model Q than the anchor action, but the realized outcome was worse after
the policy flip. On `554004:3`, the anchor action had much higher Q and remained
the better outcome. This means a simple "use Q margin" rule is not reliable
enough by itself; the issue is local policy ranking under delayed reward noise.

Decision:

Do not train another global pairwise or family-level objective from this data.
The failure is now narrow enough to target directly: near-tie discard policy
flips in high-impact Chongci states. The next training candidate should preserve
the promoted anchor's top discard when:

- both policies choose discard,
- the candidate only wins the policy-logit ranking by a small margin,
- the promoted anchor has better realized reward on the paired trace,
- the case is a new large loss or large reward regression.

Interpretation:

This is different from the earlier broad risk regularizer. The target should
not say "discard is risky" or "all candidate divergence is bad." It should say:
when the current promoted anchor and a follow-up checkpoint disagree between
two legal discards and the follow-up creates a large regression, add a local
policy-margin preservation example for the anchor discard. This is closer to
behavioral guardrail distillation than reward shaping.

Next useful branch:

1. Build a small near-tie discard regression dataset from the failure-slice
   reports and any larger paired traces with observation arrays.
2. Train a low-dose policy-margin preservation candidate from the promoted
   anchor, without changing the Q objective.
3. Gate on the same combined seed windows. Promote only if mean reward and
   large-loss rate are no worse than the promoted direct-CF anchor.

### Experiment: Failure-Slice Discard Policy-Margin Candidate

Run:

```text
failure-slice paired traces:
  /root/fh-mahjong-runs/chongci-failure-slice-20260606
training run:
  /root/fh-mahjong-runs/chongci-failure-slice-policy-margin-20260606-000641
checkpoint:
  /root/fh-mahjong-runs/chongci-failure-slice-policy-margin-20260606-000641/checkpoints/failure_slice_discard_policy_margin_w010_m005/epoch_001.pt
```

Question:

Can a very narrow policy-margin preservation branch fix the repeated
discard-vs-discard large-loss regressions without touching the Q-margin
objective?

Data:

The data builder gained action-family filters:

```text
--preferred-action-family
--avoided-action-family
```

The candidate used only rows satisfying:

```text
preferred_policy = promoted_anchor
preferred_action_family = discard
avoided_action_family = discard
high_risk_only = true
min_reward_gap = 0.1
```

Filtered rows:

| source report | base rows |
| --- | ---: |
| promoted anchor vs larger direct-CF repeat8 failure slice | 3 |
| promoted anchor vs anchor-preferred high-risk repeat64 failure slice | 5 |
| merged base rows | 8 |
| repeated auxiliary rows | 512 |

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/checkpoints/direct_cf_gap010_q025_policy001_severity/epoch_001.pt
base data:
  /root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz
epochs:
  1
learning rate:
  2e-5
pairwise_weight / margin:
  0.01 / 0.05
pairwise_q_weight:
  0.0
pairwise_reward_delta_weight / margin_scale / clip:
  0.2 / 0.05 / 1.0
MLflow training run:
  31704ddbe7f54eb19fc16ed84640f608
```

Training diagnostics:

```text
pairwise_count:
  12 to 19 per logged batch
pairwise_loss:
  0.0000 throughout
pairwise_q_loss:
  logged diagnostically but not weighted
```

Interpretation of training diagnostics:

The policy-margin loss being zero means the promoted-anchor initialized policy
already satisfied this specific margin on sampled auxiliary rows. The run still
changed the model through the base IQL update, but the intended narrow
guardrail did not actively train.

Evaluation:

An initial evaluation without `--online-episodes` produced `online: null`. A
second evaluation with `--online-episodes 30` but without
`--max-steps-per-episode 20000` truncated all matches and produced all-zero
rewards. Both are invalid. The accepted evaluation is the corrected run:

```text
seed windows:
  534000:10, 544000:10, 554000:10
duplicate seats:
  true
max steps per episode:
  20000
evaluated seats:
  120
report:
  /root/fh-mahjong-runs/chongci-failure-slice-policy-margin-20260606-000641/reports/failure_slice_discard_policy_margin_w010_m005_combined_gate_534_544_554_n10.json
MLflow eval run:
  bcc795fc45054200914c2c9ecc3721c1
```

Result:

| checkpoint | mean reward | reward sum | positive rate | large-loss rate |
| --- | ---: | ---: | ---: | ---: |
| promoted anchor | -0.0023 | -0.2780 | 45.00% | 14.17% |
| failure-slice discard policy-margin | -0.0282 | -3.3850 | 45.00% | 15.83% |

Large-loss delta:

```text
added large-loss seed/seats:
  534002:0, 544009:2
recovered large-loss seed/seats:
  none
```

Decision:

Rejected. The candidate preserved positive-reward rate but worsened EV and
large-loss rate versus the promoted direct-CF anchor.

Interpretation:

This closes the first tiny near-tie policy-margin attempt. The result is useful
because it shows that simply replaying the known failure-slice rows as a
low-dose policy-margin auxiliary is not enough; the pairwise policy loss was
already satisfied at initialization. The next branch should not increase this
same loss weight blindly. It needs either:

1. a stricter active condition that actually produces non-zero policy loss, such
   as larger margins or logit-rank preservation against the candidate action, or
2. a new candidate-generation path that creates fresh paired traces where the
   promoted anchor is not already margin-satisfied.

### Diagnostic And Experiment: Scored First-Divergence Trace And Margin025

Run:

```text
scored trace:
  /root/fh-mahjong-runs/chongci-scored-failure-slice-20260606/reports/promoted_anchor_vs_failure_slice_policy_margin_added_loss_scored_trace.json
training run:
  /root/fh-mahjong-runs/chongci-failure-slice-policy-margin-20260606-active025
checkpoint:
  /root/fh-mahjong-runs/chongci-failure-slice-policy-margin-20260606-active025/checkpoints/failure_slice_discard_policy_margin_w010_m025/epoch_001.pt
```

Question:

Can compact policy/Q score diagnostics explain why the margin005 branch still
created added large losses? If the anchor's first-divergence policy margins are
small, does a stricter policy-margin setting help?

Code/tooling:

`paired_trace.py` now supports:

```text
--include-action-scores
--action-score-top-k
```

This records compact top masked policy logits and top masked Q values for each
recorded step. It is intentionally separate from `--include-observation-arrays`
so first-divergence analysis does not always require huge tensor-bearing
reports.

Scored trace:

```text
comparison:
  promoted anchor vs failure_slice_discard_policy_margin_w010_m005
seed/seat slice:
  534002 and 544009, seats 0-3
pairs:
  8
divergence rate:
  87.50%
candidate better rate:
  25.00%
mean delta:
  -0.1209
family pairs:
  discard->discard: 5
  chii->chii: 1
  chii->pass: 1
```

Key scored examples:

```text
544009:2:
  reward delta: -0.728
  anchor action: discard 1p
  candidate action: discard 7p
  anchor policy top:    discard 1p 3.947, discard 7p 3.809
  candidate policy top: discard 7p 3.840, discard 1p 3.822

534002:0:
  reward delta: -0.098
  anchor action: discard 1p
  candidate action: discard 9p
  anchor policy top:    discard 1p -0.858, discard 9p -0.879
  candidate policy top: discard 9p -0.766, discard 1p -1.063

534002:1:
  reward delta: -0.216
  anchor action: chii 6m7m8m
  candidate action: chii 7m8m9m
  anchor policy top:    chii 6m7m8m -0.498, chii 7m8m9m -0.629
  candidate policy top: chii 7m8m9m -0.571, chii 6m7m8m -0.580
```

Direct margin check on the original repeated auxiliary shard showed several
anchor-preferred rows had small anchor logit margins:

```text
534000:1 discard 1z over discard 3s: 0.028
554004:3 discard 1m over discard 1p: 0.183
534002:0 discard 6p over discard 3m: 0.114
534000:1 discard 9m over discard 9s: 0.194
534002:1 discard 3s over discard 2s: 0.164
```

Training:

Same setup as margin005, except:

```text
pairwise_margin:
  0.25
pairwise_weight:
  0.01
pairwise_q_weight:
  0.0
MLflow training run:
  2f8100be6e6845cf9ac157a9d73bf553
```

Training diagnostics:

Logged `pairwise_loss` was still `0.0000` by the first logged step, but the
direct pre-training margin check showed the stricter margin was active for some
rows at initialization. The most likely explanation is that those rows were
satisfied before the first logged interval.

Evaluation:

```text
seed windows:
  534000:10, 544000:10, 554000:10
duplicate seats:
  true
max steps per episode:
  20000
evaluated seats:
  120
report:
  /root/fh-mahjong-runs/chongci-failure-slice-policy-margin-20260606-active025/reports/failure_slice_discard_policy_margin_w010_m025_combined_gate_534_544_554_n10.json
MLflow eval run:
  bccbc227177b4cf3bd2b85d06f2d8a10
```

Result:

| checkpoint | mean reward | reward sum | positive rate | large-loss rate |
| --- | ---: | ---: | ---: | ---: |
| promoted anchor | -0.0023 | -0.2780 | 45.00% | 14.17% |
| margin005 | -0.0282 | -3.3850 | 45.00% | 15.83% |
| margin025 | -0.0275 | -3.3030 | 45.83% | 15.00% |

Large-loss delta:

```text
margin025 added vs promoted anchor:
  534002:0
margin025 recovered vs promoted anchor:
  none
margin025 recovered vs margin005:
  544009:2
```

Decision:

Rejected. Margin025 is directionally better than margin005 on positive-rate and
large-loss rate, but it still loses EV and tail risk versus the promoted
direct-CF anchor.

Interpretation:

The stricter policy margin partially helped: it removed one of margin005's added
large losses. But the branch still does not meet the promotion guard, and the
remaining failure `534002:0` shows that preserving a few known discard rankings
is too local to protect the full gate. Do not keep sweeping only
`pairwise_margin` on this eight-row shard.

Next useful branch:

1. Keep `--include-action-scores` as the default diagnostic tool for any future
   paired-trace failure slice.
2. Generate a larger scored failure dataset from fresh candidate families, not
   just the same eight-row failure slice.
3. If adding a new objective, make it teacher-policy distillation on selected
   high-risk states rather than another pairwise-margin sweep.

### Diagnostic And Experiment: Full Scored Trace And Preferred-Action Teacher Replay

Run:

```text
full scored tensor trace:
  /root/fh-mahjong-runs/chongci-larger-scored-failure-data-20260606/reports/promoted_anchor_vs_margin025_combined_gate_scored_tensor_trace.json
teacher data:
  /root/fh-mahjong-runs/chongci-larger-scored-failure-data-20260606/data/promoted_anchor_teacher_discard_gap010
repeated teacher data:
  /root/fh-mahjong-runs/chongci-larger-scored-failure-data-20260606/data/promoted_anchor_teacher_discard_gap010_repeat512
training run:
  /root/fh-mahjong-runs/chongci-teacher-discard-distill-20260606-020712
checkpoint:
  /root/fh-mahjong-runs/chongci-teacher-discard-distill-20260606-020712/checkpoints/teacher_discard_gap010_repeat512_bc005/epoch_001.pt
```

Question:

Can a larger scored tensor trace provide enough promoted-anchor-preferred
discard examples to train teacher-policy distillation instead of pairwise-margin
ranking?

Scored trace:

```text
comparison:
  promoted anchor vs margin025
seed windows:
  534000:10, 544000:10, 554000:10
seats:
  0, 1, 2, 3
pairs:
  120
divergence rate:
  67.50%
candidate better rate:
  20.00%
mean reward delta:
  -0.0252
```

Counterfactual labels:

```text
labeled pairs:
  51
high-risk labeled pairs:
  9
preferred->avoided families:
  discard->discard: 44
  chii->chii: 2
  chii->pass: 2
  pass->chii: 1
  pass->pon: 2
tags:
  worse_reward: 51
  avoided_large_loss: 9
  new_large_loss: 1
```

The only new large-loss case versus the promoted anchor in this trace was:

```text
534002:0
  reward delta: -0.098
  first divergence index: 22
  anchor action: discard 1p
  candidate action: discard 9p
```

Reusable teacher rows:

```text
preferred_policy = promoted_anchor
preferred_action_family = discard
avoided_action_family = discard
min_reward_gap = 0.1
training_target_policy = preferred
rows:
  11
repeated rows:
  5632
```

Code/tooling:

`build_counterfactual_risk_data.py` now supports:

```text
--training-target-policy avoided
--training-target-policy preferred
```

Default `avoided` preserves the old risk/negative-example behavior. `preferred`
sets `action_ids` and `terminal_rewards` from the better policy, so the shard
can be used as normal `--data` for teacher-policy replay. The builder also now
emits normal transition arrays (`next_planes`, `next_scalars`,
`next_action_mask`, `rewards`, `terminated`, `truncated`, `steps_to_done`) so
these shards can be used by `train_iql --data`, not only `--pairwise-data`.

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/checkpoints/direct_cf_gap010_q025_policy001_severity/epoch_001.pt
base data:
  /root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz
teacher data:
  promoted_anchor_teacher_discard_gap010_repeat512
epochs:
  1
learning rate:
  2e-5
bc_weight:
  0.05
pairwise_weight:
  0.0
pairwise_q_weight:
  0.0
MLflow training run:
  f6de4d4faa0b444b822b45d9eb9e1efb
```

Evaluation:

```text
seed windows:
  534000:10, 544000:10, 554000:10
duplicate seats:
  true
max steps per episode:
  20000
evaluated seats:
  120
report:
  /root/fh-mahjong-runs/chongci-teacher-discard-distill-20260606-020712/reports/teacher_discard_gap010_repeat512_bc005_combined_gate_534_544_554_n10.json
MLflow eval run:
  1bfa7ad826404341885ee58aff3abf94
```

Result:

| checkpoint | mean reward | reward sum | positive rate | large-loss rate |
| --- | ---: | ---: | ---: | ---: |
| promoted anchor | -0.0023 | -0.2780 | 45.00% | 14.17% |
| margin025 | -0.0275 | -3.3030 | 45.83% | 15.00% |
| teacher discard gap010 repeat512 | -0.0485 | -5.8140 | 45.83% | 18.33% |

Large-loss delta versus promoted anchor:

```text
added:
  534000:1
  534002:0
  544004:2
  554001:1
  554009:0
  554009:2
recovered:
  534005:0
```

Decision:

Rejected. Direct preferred-action teacher replay improved positive-rate versus
the anchor, but it badly regressed EV and tail risk.

Interpretation:

This result is worse than margin025. The issue is likely that the teacher rows
are too narrow and too heavily repeated: they preserve some promoted-anchor
discard choices but distort nearby policy behavior enough to create new tail
losses. Do not repeat the same teacher shard with only a larger repeat count or
larger BC weight.

Next useful branch:

1. Stop training on this `margin025`-derived teacher shard.
2. Generate fresh candidate families or broaden data collection before another
   teacher-distillation attempt.
3. If using teacher replay again, use a larger and more balanced scored dataset
   with both promoted-anchor wins and candidate wins, then constrain training so
   it does not only reinforce one side of a narrow failure slice.

### Experiment: Fresh Candidate Family And Balanced Teacher Replay

Run:

```text
/root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051
```

Question:

What is the current target after rejecting scalar loss stacking and the narrow
teacher-discard replay branch?

Current target:

Find an EV-improving policy update that does not increase large-loss
probability versus the promoted anchor. Operationally, generate fresh
candidate families from the promoted anchor, keep EV-up/tail-worse policies as
counterfactual data sources, then train a tail-constrained update from the
actual divergence states. Do not promote a checkpoint only because mean reward
improves.

Promoted anchor:

```text
/root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/checkpoints/direct_cf_gap010_q025_policy001_severity/epoch_001.pt
```

Fresh candidate probes:

| candidate | checkpoint | training run | expectile | temperature | BC weight | quick gate mean | quick positive | quick large-loss |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| base_iql_e075_temp5_bc002 | `/root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/checkpoints/base_iql_e075_temp5_bc002/epoch_001.pt` | `b289ed09bba84c71ba8fbf4f2be59ec2` | 0.75 | 5.0 | 0.02 | -0.0444 | 41.67% | 18.75% |
| base_iql_e065_temp2_bc010 | `/root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/checkpoints/base_iql_e065_temp2_bc010/epoch_001.pt` | `07c2a4e944c24f699fbbf9b79377fbbc` | 0.65 | 2.0 | 0.10 | -0.0195 | 41.67% | 16.67% |

Quick-screen reports:

```text
/root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/reports/base_iql_e075_temp5_bc002_quick_gate_534_544_554_n4.json
/root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/reports/base_iql_e065_temp2_bc010_quick_gate_534_544_554_n4.json
```

Decision after quick screen:

Neither fresh probe is promotable from the quick screen. The
`base_iql_e065_temp2_bc010` candidate is the better data source because it is
less tail-regressive and closer to the anchor while still producing different
decisions.

Full scored trace for `base_iql_e065_temp2_bc010`:

```text
report:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/reports/promoted_anchor_vs_fresh_e065_temp2_bc010_combined_gate_scored_tensor_trace.json
evaluated pairs:
  120
divergence rate:
  70.83%
candidate better:
  25.00%
same reward:
  59.17%
reward delta mean:
  +0.0063
reward delta sum:
  +0.7570
```

Full scored-trace result:

| policy | mean reward | reward sum | positive rate | large-loss count | large-loss rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| promoted anchor | -0.0023 | -0.2780 | 45.00% | 17 / 120 | 14.17% |
| base_iql_e065_temp2_bc010 | 0.0040 | 0.4790 | 46.67% | 19 / 120 | 15.83% |

New large-loss cases introduced by the fresh candidate:

```text
534000:1  delta=-0.314  anchor=discard 7s       candidate=discard 1z
534005:2  delta=-1.250  anchor=chii 5p6p7p      candidate=pass
```

Counterfactual rows from the scored trace:

```text
labeled pairs:
  49
high-risk pairs:
  10
family pairs:
  chii->chii: 1
  chii->pass: 6
  discard->discard: 72
  kan->discard: 1
  pon->chii: 2
  pon->pass: 3
preferred-to-avoided pairs:
  discard->discard: 37
  pass->chii: 3
  pass->pon: 3
  chii->pass: 3
  chii->pon: 1
  chii->chii: 1
  pon->chii: 1
tags:
  worse_reward: 49
  avoided_large_loss: 10
  new_large_loss: 2
```

Balanced teacher data:

```text
source trace:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/reports/promoted_anchor_vs_fresh_e065_temp2_bc010_combined_gate_scored_tensor_trace.json
base dataset:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/data/balanced_teacher_gap010
expanded dataset:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/data/balanced_teacher_gap010_repeat128
target policy:
  preferred action from either anchor or candidate
minimum reward gap:
  0.1
base rows:
  20
anchor-preferred rows:
  7
candidate-preferred rows:
  13
expanded rows:
  2560
mean reward gap:
  0.2699
max reward gap:
  1.25
```

Balanced teacher training:

```text
checkpoint:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/checkpoints/balanced_teacher_gap010_repeat128_bc002/epoch_001.pt
MLflow training run:
  7114b4eecc014ff7a7cfe15ec2c84b47
base data:
  /root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz
teacher data:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/data/balanced_teacher_gap010_repeat128
max transitions:
  200000
epochs:
  1
learning rate:
  2e-5
expectile:
  0.7
temperature:
  3.0
BC weight:
  0.02
pairwise weight:
  0.0
pairwise Q weight:
  0.0
```

Balanced teacher evaluation:

```text
seed windows:
  534000:10, 544000:10, 554000:10
duplicate seats:
  true
evaluated seats:
  120
report:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/reports/balanced_teacher_gap010_repeat128_bc002_combined_gate_534_544_554_n10.json
MLflow eval run:
  2cf45c5bfa22411b9bf4f9ca49f7a8ff
```

Result:

| policy | mean reward | reward sum | positive rate | large-loss count | large-loss rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| promoted anchor | -0.0023 | -0.2780 | 45.00% | 17 / 120 | 14.17% |
| fresh base_iql_e065_temp2_bc010 | 0.0040 | 0.4790 | 46.67% | 19 / 120 | 15.83% |
| balanced teacher gap010 repeat128 bc002 | 0.0204 | 2.4460 | 47.50% | 20 / 120 | 16.67% |

Balanced teacher large-loss delta versus promoted anchor:

```text
added:
  534000:1
  534002:0
  534005:1
  544009:2
recovered:
  534005:0
```

Decision:

Rejected for promotion. The balanced teacher candidate improves EV and
positive-reward rate, but worsens large-loss probability from 14.17% to 16.67%.
This violates the current promotion rule.

Interpretation:

The fresh candidate and the balanced teacher candidate are both useful because
they expose EV-up/tail-worse decisions from the current promoted anchor. They
are not useful as promoted checkpoints yet. This confirms the target should be
tail-constrained EV improvement: preserve the EV gains from the balanced
teacher branch while explicitly blocking or retraining the added large-loss
decisions.

Next useful branch:

1. Build a tail-constrained data product from the added large-loss seed/seats
   (`534000:1`, `534002:0`, `534005:1`, `534005:2`, `544009:2`) plus recovered
   cases such as `534005:0`.
2. Train against those exact divergence states with a rule that EV-up actions
   are only accepted when they do not increase large-loss probability versus
   the promoted anchor.
3. Use the same deterministic combined gate as the promotion guard. The current
   promoted anchor remains unchanged until a candidate improves EV/positive rate
   without worsening large-loss rate.

### Experiment: Targeted High-Risk Constraint On Balanced Teacher

Run:

```text
/root/fh-mahjong-runs/chongci-tail-constrained-balanced-20260607-023735
```

Question:

Can we keep some of the balanced-teacher EV gain while directly constraining the
two fresh-candidate large-loss divergences where the promoted anchor was the
preferred side?

Data:

```text
base data:
  /root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz
balanced teacher data:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/data/balanced_teacher_gap010_repeat128
anchor high-risk base data:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/data/anchor_highrisk_gap010
anchor high-risk repeated data:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/data/anchor_highrisk_gap010_repeat512
source trace:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/reports/promoted_anchor_vs_fresh_e065_temp2_bc010_combined_gate_scored_tensor_trace.json
```

High-risk shard:

```text
preferred policy:
  promoted_anchor
training target:
  preferred action
high-risk only:
  true
minimum reward gap:
  0.1
base rows:
  2
repeated rows:
  1024
mean reward gap:
  0.7820
max reward gap:
  1.25
```

Training:

```text
checkpoint:
  /root/fh-mahjong-runs/chongci-tail-constrained-balanced-20260607-023735/checkpoints/tail_balanced_highrisk_gap010/epoch_001.pt
MLflow training run:
  60a23635002348aa903f6a3154f5864a
init checkpoint:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/checkpoints/direct_cf_gap010_q025_policy001_severity/epoch_001.pt
epochs:
  1
max transitions per dataset:
  200000
learning rate:
  2e-5
expectile:
  0.7
temperature:
  3.0
BC weight:
  0.02
pairwise weight:
  0.01
pairwise margin:
  0.05
pairwise Q weight:
  0.25
pairwise Q margin:
  0.1
pairwise reward-delta weight:
  0.5
pairwise reward-delta margin scale:
  0.2
```

Training health:

Pairwise Q supervision was active. The logged pairwise counts were non-zero
throughout the epoch and `pairwise_q_loss` dropped from `0.1368` near step 10
to `0.0006` near step 40. This confirms the high-risk rows were seen by the
optimizer.

Evaluation:

```text
seed windows:
  534000:10, 544000:10, 554000:10
duplicate seats:
  true
evaluated seats:
  120
report:
  /root/fh-mahjong-runs/chongci-tail-constrained-balanced-20260607-023735/reports/tail_balanced_highrisk_gap010_combined_gate_534_544_554_n10.json
MLflow eval run:
  f407ce9366d04903a5d39dce8fd0a0d6
```

Result:

| policy | mean reward | reward sum | positive rate | large-loss count | large-loss rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| promoted anchor | -0.0023 | -0.2780 | 45.00% | 17 / 120 | 14.17% |
| balanced teacher gap010 repeat128 bc002 | 0.0204 | 2.4460 | 47.50% | 20 / 120 | 16.67% |
| tail balanced highrisk gap010 | -0.0200 | -1.8180 | 45.83% | 19 / 120 | 15.83% |

Decision:

Rejected. The explicit high-risk anchor rows reduced the balanced-teacher tail
regression from `20 / 120` to `19 / 120`, but the candidate still worsened the
promoted anchor tail count of `17 / 120` and also lost mean reward versus the
anchor.

Interpretation:

This confirms that two repeated high-risk rows are not enough to make the
balanced-teacher update tail-safe. The branch is useful because it shows the
direction is mechanically active, but it should not be repeated with only a
larger repeat factor. The next useful data source needs more actual
candidate-vs-anchor divergence windows, especially the balanced-teacher
candidate's own added large-loss states.

Next useful branch:

1. Generate a scored tensor paired trace between the promoted anchor and
   `tail_balanced_highrisk_gap010`.
2. Build a larger high-risk anchor-preferred shard from that trace and the
   balanced-teacher trace, not just the original two fresh-candidate failures.
3. Prefer a larger direct counterfactual dataset over more repeat-count tuning.

### Experiment: Expanded Tail-Candidate High-Risk Constraint

Run:

```text
/root/fh-mahjong-runs/chongci-tail-constrained-balanced2-20260607-031444
```

Question:

Does adding a second high-risk direct-CF shard from
`promoted_anchor` versus `tail_balanced_highrisk_gap010` close the remaining
large-loss gap to the promoted anchor?

Paired trace:

```text
report:
  /root/fh-mahjong-runs/chongci-tail-constrained-balanced-20260607-023735/reports/promoted_anchor_vs_tail_balanced_highrisk_gap010_scored_tensor_trace.json
left:
  promoted_anchor
right:
  tail_balanced_highrisk_gap010
pairs:
  120
complete:
  true
divergence rate:
  95.83%
tail_balanced_highrisk_gap010 better:
  37.50%
same reward:
  27.50%
labeled counterfactual pairs:
  87
avoided-large-loss labels:
  17
new-large-loss labels:
  4
```

New high-risk shard:

```text
source:
  /root/fh-mahjong-runs/chongci-tail-constrained-balanced-20260607-023735/data/anchor_highrisk_tail_candidate_gap010
repeated:
  /root/fh-mahjong-runs/chongci-tail-constrained-balanced-20260607-023735/data/anchor_highrisk_tail_candidate_gap010_repeat512
preferred policy:
  promoted_anchor
training target:
  preferred action
high-risk only:
  true
minimum reward gap:
  0.1
base rows:
  4
repeated rows:
  2048
mean reward gap:
  0.5037
max reward gap:
  1.4660
```

Training:

```text
checkpoint:
  /root/fh-mahjong-runs/chongci-tail-constrained-balanced2-20260607-031444/checkpoints/tail_balanced_highrisk2_gap010/epoch_001.pt
MLflow training run:
  f59aff0a1fff4f639ba253695ac4e289
init checkpoint:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/checkpoints/direct_cf_gap010_q025_policy001_severity/epoch_001.pt
base data:
  /root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz
balanced teacher data:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/data/balanced_teacher_gap010_repeat128
old high-risk data:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/data/anchor_highrisk_gap010_repeat512
new high-risk data:
  /root/fh-mahjong-runs/chongci-tail-constrained-balanced-20260607-023735/data/anchor_highrisk_tail_candidate_gap010_repeat512
epochs:
  1
max transitions per dataset:
  200000
learning rate:
  2e-5
expectile:
  0.7
temperature:
  3.0
BC weight:
  0.02
pairwise weight:
  0.01
pairwise margin:
  0.05
pairwise Q weight:
  0.25
pairwise Q margin:
  0.1
pairwise reward-delta weight:
  0.5
pairwise reward-delta margin scale:
  0.2
```

Training health:

Pairwise Q supervision was active again. Logged pairwise counts were non-zero
(`110` to `136` sampled rows per logged batch), and `pairwise_q_loss` dropped
from `0.1360` at step 10 to `0.0005` at step 50.

Evaluation:

```text
seed windows:
  534000:10, 544000:10, 554000:10
duplicate seats:
  true
evaluated seats:
  120
report:
  /root/fh-mahjong-runs/chongci-tail-constrained-balanced2-20260607-031444/reports/tail_balanced_highrisk2_gap010_combined_gate_534_544_554_n10.json
MLflow eval run:
  4f25b7a26a2d46a190ae5a236db27b67
```

Result:

| policy | mean reward | reward sum | positive rate | large-loss count | large-loss rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| promoted anchor | -0.0023 | -0.2780 | 45.00% | 17 / 120 | 14.17% |
| tail balanced highrisk gap010 | -0.0200 | -1.8180 | 45.83% | 19 / 120 | 15.83% |
| tail balanced highrisk2 gap010 | -0.0300 | -3.7330 | 46.67% | 18 / 120 | 15.00% |

Decision:

Rejected. The expanded high-risk shard improves tail risk versus the prior
targeted candidate, but it still worsens the promoted anchor's large-loss count
from `17 / 120` to `18 / 120`, and mean reward is also worse than the anchor.

Interpretation:

The direct-CF high-risk constraints are mechanically active and move tail risk
in the expected direction, but this data family is still too small and too
reactive. Repeating a handful of high-risk rows can partially repair a rejected
candidate, but it does not yet produce a promotable update. The next branch
should gather broader fresh candidate-vs-anchor divergence data rather than
adding another repeat-count or nearby pairwise-weight tweak to this same shard.

Next useful branch:

1. Stop extending this specific high-risk replay stack unless new divergence
   data is added.
2. Generate a broader fresh candidate family or mixed self-play batch from the
   promoted anchor plus the EV-up/tail-worse rejected candidates.
3. Build a larger direct-CF dataset from many actual divergence windows, then
   train with the same deterministic promotion guard.

### Experiment: Broader Mixed Self-Play IQL Promotion

Run:

```text
self-play:
  /root/fh-mahjong-runs/chongci-broader-mixed-selfplay-20260607-032601
training:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720
```

Question:

Can broader fresh mixed self-play from the promoted anchor plus the EV-up /
tail-worse rejected candidate family produce a tail-safe EV improvement, instead
of repeatedly tuning the same tiny high-risk shard?

Data generation:

```text
output:
  /root/fh-mahjong-runs/chongci-broader-mixed-selfplay-20260607-032601/data/anchor-fresh-balanced-tail2-760000-n200-npz
episodes:
  200
start seed:
  760000
transitions:
  409882
shards:
  9
seat 0:
  promoted_anchor
seat 1:
  fresh_base_iql_e065_temp2_bc010
seat 2:
  balanced_teacher_gap010_repeat128_bc002
seat 3:
  tail_balanced_highrisk2_gap010
```

Training:

```text
checkpoint:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
MLflow training run:
  9b0f942e7c84483b9ed9329c467363d3
init checkpoint:
  /root/fh-mahjong-runs/chongci-targeted-divergence-data-20260605-015622/checkpoints/direct_cf_gap010_q025_policy001_severity/epoch_001.pt
base data:
  /root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz
fresh mixed data:
  /root/fh-mahjong-runs/chongci-broader-mixed-selfplay-20260607-032601/data/anchor-fresh-balanced-tail2-760000-n200-npz
pairwise-only high-risk data:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/data/anchor_highrisk_gap010_repeat512
  /root/fh-mahjong-runs/chongci-tail-constrained-balanced-20260607-023735/data/anchor_highrisk_tail_candidate_gap010_repeat512
epochs:
  1
max transitions per dataset:
  200000
learning rate:
  2e-5
expectile:
  0.7
temperature:
  3.0
BC weight:
  0.03
pairwise weight:
  0.01
pairwise margin:
  0.05
pairwise Q weight:
  0.25
pairwise Q margin:
  0.1
pairwise reward-delta weight:
  0.5
pairwise reward-delta margin scale:
  0.2
```

Training health:

The high-risk rows were used as pairwise-only auxiliary replay. Training logs
showed non-zero pairwise batches and active Q-side constraints early:
`pairwise_q_loss=0.1376` at step 10, then `0.0000` after the margin fit. This
means the run used the high-risk rows without letting their terminal returns
dominate the normal IQL replay.

Evaluation:

```text
seed windows:
  534000:10, 544000:10, 554000:10
duplicate seats:
  true
evaluated seats:
  120
repeat 1 report:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/reports/broader_mixed_iql_highrisk_pairwise_combined_gate_534_544_554_n10.json
repeat 1 MLflow eval run:
  49dd6116145f447090f70f24afc50db8
repeat 2 report:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/reports/repeated_gate_broader_mixed_iql_highrisk_pairwise_candidate_repeat2.json
repeat 2 MLflow eval run:
  d89cc6eaf9d94a5db31a322072828224
```

Result:

| policy | repeat | mean reward | reward sum | positive rate | large-loss count | large-loss rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| previous promoted anchor | known deterministic | -0.0023 | -0.2780 | 45.00% | 17 / 120 | 14.17% |
| broader mixed IQL high-risk pairwise | 1 | 0.0100 | 1.4410 | 47.50% | 16 / 120 | 13.33% |
| broader mixed IQL high-risk pairwise | 2 | 0.0100 | 1.4410 | 47.50% | 16 / 120 | 13.33% |

Decision:

Promoted as the new `current_chongci_reward_trained_best`.

Interpretation:

This is the first branch in this sequence that moved all promotion metrics in
the right direction. The key change was not another scalar penalty or more
repeat-count pressure on the same tiny direct-CF shard. The useful ingredient
was broader fresh mixed self-play involving the previous promoted anchor and
the EV-up/tail-worse rejected policies, while keeping high-risk direct-CF rows
as pairwise-only constraints.

Next useful branch:

1. Treat
   `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
   as the new anchor for future Chongci reward-learning experiments.
2. Run the next self-play iteration from this promoted checkpoint, not the
   older direct-CF anchor.
3. Preserve the same promotion rule: improve EV/positive rate and do not worsen
   large-loss rate on deterministic duplicate-seat gates.

### Experiment: Post-Promotion All-Anchor Self-Play Iteration

Run:

```text
self-play:
  /root/fh-mahjong-runs/chongci-promoted-broader-selfplay-20260610-223633
normal-dose training:
  /root/fh-mahjong-runs/chongci-broader-anchor-selfplay-iql-20260610-225703
low-dose training:
  /root/fh-mahjong-runs/chongci-broader-anchor-selfplay-iql-lowdose-20260610-230656
ultra-low-dose training:
  /root/fh-mahjong-runs/chongci-broader-anchor-selfplay-iql-ultralow-20260610-231629
```

Question:

After promoting `broader_mixed_iql_highrisk_pairwise`, can a direct all-anchor
self-play iteration improve it further?

Data generation:

```text
output:
  /root/fh-mahjong-runs/chongci-promoted-broader-selfplay-20260610-223633/data/broader-anchor-selfplay-780000-n200-npz
episodes:
  200
start seed:
  780000
transitions:
  405621
shards:
  9
seat 0:
  broader_mixed_iql_highrisk_pairwise
seat 1:
  broader_mixed_iql_highrisk_pairwise
seat 2:
  broader_mixed_iql_highrisk_pairwise
seat 3:
  broader_mixed_iql_highrisk_pairwise
```

Training data:

```text
base data:
  /root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz
fresh all-anchor self-play:
  /root/fh-mahjong-runs/chongci-promoted-broader-selfplay-20260610-223633/data/broader-anchor-selfplay-780000-n200-npz
pairwise-only high-risk data:
  /root/fh-mahjong-runs/chongci-fresh-candidate-family-20260607-015051/data/anchor_highrisk_gap010_repeat512
  /root/fh-mahjong-runs/chongci-tail-constrained-balanced-20260607-023735/data/anchor_highrisk_tail_candidate_gap010_repeat512
```

Training variants:

| variant | checkpoint | learning rate | BC weight | MLflow train run |
| --- | --- | ---: | ---: | --- |
| normal | `/root/fh-mahjong-runs/chongci-broader-anchor-selfplay-iql-20260610-225703/checkpoints/broader_anchor_selfplay_iter1/epoch_001.pt` | 2e-5 | 0.03 | `e876f5354b4d48ca99b01af218b20b3b` |
| low-dose | `/root/fh-mahjong-runs/chongci-broader-anchor-selfplay-iql-lowdose-20260610-230656/checkpoints/broader_anchor_selfplay_iter1_lowdose/epoch_001.pt` | 1e-5 | 0.04 | `b79ba370265140b6bae923d8152c929a` |
| ultra-low-dose | `/root/fh-mahjong-runs/chongci-broader-anchor-selfplay-iql-ultralow-20260610-231629/checkpoints/broader_anchor_selfplay_iter1_ultralow/epoch_001.pt` | 5e-6 | 0.05 | `64d804c28a8b4775b9c2ae5cb29f45d2` |

Training health:

The pairwise rows were sampled in all three variants, but `pairwise_q_loss`
was already `0.0000` from the first logged batch. This means the promoted model
already satisfied those older high-risk Q margins; the new signal in this
experiment mainly came from the all-anchor self-play returns.

Evaluation:

```text
seed windows:
  534000:10, 544000:10, 554000:10
duplicate seats:
  true
evaluated seats:
  120
```

Result:

| policy | mean reward | reward sum | positive rate | large-loss count | large-loss rate | MLflow eval run |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| current promoted anchor | 0.0100 | 1.4410 | 47.50% | 16 / 120 | 13.33% | `49dd6116145f447090f70f24afc50db8` |
| normal all-anchor self-play | -0.0100 | -1.1960 | 47.50% | 14 / 120 | 11.67% | `7ede60742c544ad2a1c03382ad432ca9` |
| low-dose all-anchor self-play | 0.0100 | 0.8120 | 48.33% | 15 / 120 | 12.50% | `e8f0857948f54f73a6cadae31ef08f3d` |
| ultra-low-dose all-anchor self-play | -0.0100 | -1.0480 | 45.83% | 16 / 120 | 13.33% | `43f59235b51c4276b5c87b02c79ee231` |

Decision:

Rejected all three variants. The current promoted anchor remains:

```text
/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
```

Interpretation:

The all-anchor self-play data is useful, but not directly promotable with these
simple one-epoch IQL updates. The normal and low-dose variants improved tail
risk, and low-dose also improved positive rate, but both lost reward sum versus
the promoted anchor. Ultra-low-dose removed most of the useful tail improvement
while still losing EV.

The important signal is that this data family can reduce large-loss count, but
it currently trades away EV. Do not promote a variant only because tail risk is
better. The next branch should use these rejected variants as divergence data:
trace the promoted anchor against the low-dose candidate, then extract
counterfactual states where low-dose avoided large losses without sacrificing
too much EV.

Next useful branch:

1. Run a scored tensor paired trace between the promoted anchor and
   `broader_anchor_selfplay_iter1_lowdose`.
2. Build direct-CF rows from states where low-dose is better or avoids large
   losses, while filtering out broad EV-losing decisions.
3. Train a small candidate from those targeted rows instead of another global
   all-anchor self-play sweep.

### Experiment: Low-Dose Divergence Direct-CF Pairwise

Run:

```text
paired trace:
  /root/fh-mahjong-runs/chongci-lowdose-divergence-trace-20260610-232802
training:
  /root/fh-mahjong-runs/chongci-lowdose-targeted-pairwise-iql-20260610-235147
```

Question:

The low-dose all-anchor self-play candidate improved positive rate and
large-loss count but lost reward sum. Can we copy only the low-dose decisions
that beat the promoted anchor, without inheriting the whole EV regression?

Paired trace:

```text
report:
  /root/fh-mahjong-runs/chongci-lowdose-divergence-trace-20260610-232802/reports/promoted_anchor_vs_lowdose_selfplay_iter1_scored_tensor_trace.json
left:
  promoted_anchor
right:
  lowdose_selfplay_iter1
pairs:
  120
complete:
  true
divergence rate:
  64.17%
lowdose better:
  19.17%
same reward:
  65.83%
labeled counterfactual pairs:
  41
avoided-large-loss labels:
  6
new-large-loss labels:
  1
```

Direct-CF data:

```text
lowdose preferred gap010:
  /root/fh-mahjong-runs/chongci-lowdose-divergence-trace-20260610-232802/data/lowdose_preferred_gap010_repeat256
base rows:
  10
repeated rows:
  2560
mean reward gap:
  0.3010
max reward gap:
  0.4500

lowdose preferred highrisk gap010:
  /root/fh-mahjong-runs/chongci-lowdose-divergence-trace-20260610-232802/data/lowdose_preferred_highrisk_gap010_repeat512
base rows:
  3
repeated rows:
  1536
mean reward gap:
  0.3667
max reward gap:
  0.4500

anchor preferred highrisk gap010:
  no rows at min_reward_gap=0.1
```

Training:

```text
checkpoint:
  /root/fh-mahjong-runs/chongci-lowdose-targeted-pairwise-iql-20260610-235147/checkpoints/lowdose_targeted_pairwise/epoch_001.pt
MLflow training run:
  a5f6a52a5f2545f28291db0a49db7d60
init checkpoint:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
base data:
  /root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz
pairwise-only data:
  lowdose_preferred_gap010_repeat256
  lowdose_preferred_highrisk_gap010_repeat512
  older anchor_highrisk_gap010_repeat512
  older anchor_highrisk_tail_candidate_gap010_repeat512
learning rate:
  1e-5
BC weight:
  0.03
pairwise Q weight:
  0.25
pairwise Q margin:
  0.1
```

Training health:

The new pairwise rows were active. Logged `pairwise_q_loss` started at `0.0454`
and decreased to `0.0024`, with non-zero pairwise counts in every logged batch.

Evaluation:

```text
seed windows:
  534000:10, 544000:10, 554000:10
duplicate seats:
  true
evaluated seats:
  120
report:
  /root/fh-mahjong-runs/chongci-lowdose-targeted-pairwise-iql-20260610-235147/reports/lowdose_targeted_pairwise_combined_gate_534_544_554_n10.json
MLflow eval run:
  84131a67989b46c59d79ce957a1ea125
```

Result:

| policy | mean reward | reward sum | positive rate | large-loss count | large-loss rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| current promoted anchor | 0.0100 | 1.4410 | 47.50% | 16 / 120 | 13.33% |
| low-dose self-play candidate | 0.0100 | 0.8120 | 48.33% | 15 / 120 | 12.50% |
| low-dose targeted pairwise | -0.0200 | -1.8000 | 47.50% | 19 / 120 | 15.83% |
| fresh low-dose targeted pairwise w015 | -0.0200 | -2.0880 | 46.67% | 16 / 120 | 13.33% |
| fresh low-dose targeted pairwise effective w015 | -0.0300 | -3.0260 | 47.50% | 17 / 120 | 14.17% |
| promoted diverse IQL lr5e-6 bc05 | -0.0300 | -3.1400 | 45.00% | 19 / 120 | 15.83% |
| promoted diverse filtered IQL lr5e-6 bc05 | -0.0100 | -1.6750 | 45.83% | 18 / 120 | 15.00% |

Decision:

Rejected. The targeted pairwise data was mechanically active but made the
policy worse on both EV and large-loss rate.

Interpretation:

The low-dose candidate's useful behavior is not captured well enough by first
divergence pairwise margins alone. The low-dose policy had only 10 meaningful
preferred rows at `gap >= 0.1`, and replaying those margins overfit local
preferences without preserving the broader EV/tail balance.

Next useful branch:

1. Stop this low-dose pairwise branch.
2. If continuing from the all-anchor self-play data, use outcome filtering or a
   larger paired-trace data product, not the 10-row first-divergence shard.
3. The current promoted anchor remains unchanged.

### Experiment: Fresh Low-Dose Direct-CF Pairwise w015

Run:
`/root/fh-mahjong-runs/chongci-lowdose-targeted-pairwise-fresh-20260611-003312`

Question:
Can a broader old+fresh low-dose-vs-anchor direct counterfactual dataset transfer
the low-dose candidate's lower tail risk without losing the promoted anchor's EV?

Data:

- Base IQL data:
  `/root/fh-mahjong-runs/chongci-broader-mixed-selfplay-20260607-032601/data/anchor-fresh-balanced-tail2-760000-n200-npz`
- Fresh paired trace:
  `/root/fh-mahjong-runs/chongci-lowdose-divergence-trace-fresh-20260611-000449/reports/promoted_anchor_vs_lowdose_selfplay_iter1_fresh_scored_tensor_trace.json`
- Fresh trace summary:
  120 pairs, 68.33% first-action divergence, 15.00% low-dose-better rate,
  62.50% same-reward rate, 45 labeled counterfactual pairs.
- Fresh counterfactual tags:
  9 avoided-large-loss, 2 new-large-loss, 45 worse-reward.
- Preferred action families:
  42 discard, 2 pass, 1 chii.
- Pairwise auxiliary data:
  old low-dose preferred `gap >= 0.1`, old low-dose preferred high-risk
  `gap >= 0.1`, fresh low-dose preferred `gap >= 0.05`, and fresh low-dose
  preferred high-risk `gap >= 0.1`.

Training:

- Init checkpoint:
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Epochs: 1
- Batch size: 512
- LR: `1e-5`
- MC target with `gamma=1.0`
- `bc_weight=0.03`
- `pairwise_q_weight=0.15`, `pairwise_q_margin=0.08`
- `pairwise_weight=0.005`, `pairwise_margin=0.04`
- `pairwise_reward_delta_weight=0.25`
- MLflow train run:
  `6ff05a24ccff446495fc26083490fbce`

Evaluation:

- Gate: `534000:10`, `544000:10`, `554000:10`, duplicate seats, 120 seats.
- Report:
  `/root/fh-mahjong-runs/chongci-lowdose-targeted-pairwise-fresh-20260611-003312/reports/lowdose_targeted_pairwise_fresh_w015_combined_gate_534_544_554_n10.json`
- MLflow eval run:
  `cb2b5a8f58f0431b9e48f4a920d12e0e`

Result:

| policy | mean reward | reward sum | positive rate | large-loss count | large-loss rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| current promoted anchor | 0.0100 | 1.4410 | 47.50% | 16 / 120 | 13.33% |
| fresh low-dose targeted pairwise w015 | -0.0200 | -2.0880 | 46.67% | 16 / 120 | 13.33% |

Decision:

Rejected. The candidate tied the promoted anchor on large-loss rate but lost EV
and positive-reward rate.

Interpretation:

This did not reproduce the low-dose candidate's useful tail improvement. The
fresh trace added coverage, but most preferred rows were still discard-only
first-divergence examples. The trainer also reported raw pairwise row counts
during training, so repeated direct-CF shards did not behave as a clear larger
effective dataset in the training log. Do not continue this branch with nearby
pairwise weight changes alone.

Next useful branch:

1. Inspect/fix pairwise auxiliary loading if repeated shards are supposed to
   change effective sampling frequency.
2. Prefer a larger aligned data product from more low-dose-vs-anchor windows
   before another direct-CF candidate.
3. Keep the promoted anchor unchanged.

### Experiment: Fresh Low-Dose Direct-CF Pairwise Effective w015

Run:
`/root/fh-mahjong-runs/chongci-lowdose-targeted-pairwise-fresh-effective-20260611-004747`

Question:
After fixing the repeated-shard manifests so `read_transition_arrays` loads the
intended number of pairwise rows, does the same low-dose direct-CF branch work?

Data:

- Same base data and same old+fresh low-dose preferred pairwise shards as the
  prior w015 run.
- Manifest fix:
  the ad hoc repeated shards originally wrote `num_transitions` but not the
  canonical `transitions` field, so the loader only read the original raw row
  counts. The remote repeated manifests were fixed to include `transitions`.
- Effective pairwise rows loaded:
  1,280 old `gap >= 0.1`, 768 old high-risk `gap >= 0.1`, 1,536 fresh
  `gap >= 0.05`, and 512 fresh high-risk `gap >= 0.1`.

Training:

- Same hyperparameters as w015:
  `pairwise_q_weight=0.15`, `pairwise_q_margin=0.08`,
  `pairwise_weight=0.005`, `pairwise_margin=0.04`,
  `pairwise_reward_delta_weight=0.25`.
- MLflow train run:
  `71a01a1ebb59476a9ed4d5857f068aac`

Evaluation:

- Gate: `534000:10`, `544000:10`, `554000:10`, duplicate seats, 120 seats.
- Report:
  `/root/fh-mahjong-runs/chongci-lowdose-targeted-pairwise-fresh-effective-20260611-004747/reports/lowdose_targeted_pairwise_fresh_effective_w015_combined_gate_534_544_554_n10.json`
- MLflow eval run:
  `d0ef0078574d4345b75d06ba0417bfa8`

Result:

| policy | mean reward | reward sum | positive rate | large-loss count | large-loss rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| current promoted anchor | 0.0100 | 1.4410 | 47.50% | 16 / 120 | 13.33% |
| fresh low-dose targeted pairwise effective w015 | -0.0300 | -3.0260 | 47.50% | 17 / 120 | 14.17% |

Decision:

Rejected. Once the intended repeated pairwise rows actually loaded, the
candidate tied positive-reward rate but regressed EV and large-loss rate.

Interpretation:

This closes the low-dose first-divergence pairwise branch. The previous w015
run was under-dosed due to a generated-manifest issue; the corrected effective
run shows that adding the intended pairwise pressure makes tail risk worse, not
better. Do not continue with nearby low-dose pairwise weight changes.

Next useful branch:

1. Stop low-dose first-divergence direct-CF pairwise tuning.
2. Use larger aligned self-play/counterfactual data from promoted anchor plus
   diverse policies, or move to a different risk target that is not only first
   divergence.
3. Keep the promoted anchor unchanged.

### Experiment: Promoted Diverse IQL lr5e-6 bc05

Run:
`/root/fh-mahjong-runs/chongci-promoted-diverse-iql-20260611-021603`

Question:
Does a larger mixed self-play dataset improve the current promoted anchor when
trained conservatively without the failed low-dose pairwise objective?

Data:

- Fresh mixed self-play run:
  `/root/fh-mahjong-runs/chongci-promoted-diverse-selfplay-20260611-013359`
- Fresh mixed data:
  `/root/fh-mahjong-runs/chongci-promoted-diverse-selfplay-20260611-013359/data/promoted-anchor2-lowdose-prev-800000-n400-npz`
- Episodes: 400
- Transitions: 817,238
- Start seed: 800000
- Seat policies:
  seat 0 current promoted anchor, seat 1 current promoted anchor,
  seat 2 low-dose self-play candidate, seat 3 previous direct-CF anchor.
- Training data:
  capped current replay, prior broader mixed replay, and the fresh diverse
  replay.
- Pairwise data:
  only the older anchor high-risk pairwise auxiliaries from the current
  promotion family; no low-dose pairwise rows.

Training:

- Init checkpoint:
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Epochs: 1
- Batch size: 4096
- LR: `5e-6`
- MC target with `gamma=0.99`
- `bc_weight=0.05`
- `pairwise_q_weight=0.25`, `pairwise_q_margin=0.1`
- `pairwise_weight=0.01`, `pairwise_margin=0.05`
- `pairwise_reward_delta_weight=0.5`
- MLflow train run:
  `1a4a374839e148cb89e590ca24d93175`

Evaluation:

- Gate: `534000:10`, `544000:10`, `554000:10`, duplicate seats, 120 seats.
- Report:
  `/root/fh-mahjong-runs/chongci-promoted-diverse-iql-20260611-021603/reports/promoted_diverse_iql_lr5e6_bc05_combined_gate_534_544_554_n10.json`
- MLflow eval run:
  `1c6dc10a86794c16a078b1b82c8d11b8`

Result:

| policy | mean reward | reward sum | positive rate | large-loss count | large-loss rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| current promoted anchor | 0.0100 | 1.4410 | 47.50% | 16 / 120 | 13.33% |
| promoted diverse IQL lr5e-6 bc05 | -0.0300 | -3.1400 | 45.00% | 19 / 120 | 15.83% |

Decision:

Rejected. Training on all seats from the larger diverse dataset regressed EV,
positive-reward rate, and large-loss rate.

Interpretation:

The generated data is still useful, but not as a direct all-policy imitation/RL
source. Seat 2 and seat 3 actions come from weaker or older policies, so using
all seats as normal policy targets likely teaches behavior the current anchor
should not copy.

Next useful branch:

1. Reuse this dataset by filtering to the promoted-anchor seats only
   (`seat in {0, 1}`), so the model learns anchor decisions against diverse
   opponents.
2. Keep the promoted anchor unchanged.

### Experiment: Promoted Diverse Filtered IQL lr5e-6 bc05

Run:
`/root/fh-mahjong-runs/chongci-promoted-diverse-filtered-iql-20260611-022743`

Question:
Can the larger diverse-opponent dataset help if training uses only the current
promoted-anchor seats instead of all policies at the table?

Data:

- Source data:
  `/root/fh-mahjong-runs/chongci-promoted-diverse-selfplay-20260611-013359/data/promoted-anchor2-lowdose-prev-800000-n400-npz`
- Filtered data:
  `/root/fh-mahjong-runs/chongci-promoted-diverse-selfplay-20260611-013359/data/promoted-anchor-seats01-vs-diverse-800000-n400-npz`
- Filter:
  keep `seat in {0, 1}` because both seats used the current promoted anchor.
- Filtered transitions:
  408,608 total; 204,348 from seat 0 and 204,260 from seat 1.
- Training data:
  capped current replay, prior broader mixed replay, and filtered anchor-seat
  diverse-opponent replay.
- Pairwise data:
  only the older anchor high-risk pairwise auxiliaries from the current
  promotion family; no low-dose pairwise rows.

Training:

- Init checkpoint:
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Epochs: 1
- Batch size: 4096
- LR: `5e-6`
- MC target with `gamma=0.99`
- `bc_weight=0.05`
- `pairwise_q_weight=0.25`, `pairwise_q_margin=0.1`
- `pairwise_weight=0.01`, `pairwise_margin=0.05`
- `pairwise_reward_delta_weight=0.5`
- MLflow train run:
  `56774b3818a24936ac65f8a4388d3358`

Evaluation:

- Gate: `534000:10`, `544000:10`, `554000:10`, duplicate seats, 120 seats.
- Report:
  `/root/fh-mahjong-runs/chongci-promoted-diverse-filtered-iql-20260611-022743/reports/promoted_diverse_filtered_iql_lr5e6_bc05_combined_gate_534_544_554_n10.json`
- MLflow eval run:
  `753849732c0e4e72bfa3bde1aac5c3b9`

Result:

| policy | mean reward | reward sum | positive rate | large-loss count | large-loss rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| current promoted anchor | 0.0100 | 1.4410 | 47.50% | 16 / 120 | 13.33% |
| promoted diverse filtered IQL lr5e-6 bc05 | -0.0100 | -1.6750 | 45.83% | 18 / 120 | 15.00% |

Decision:

Rejected. Filtering to promoted-anchor seats improved over all-seat diverse
training, but still regressed EV, positive-reward rate, and large-loss rate.

Interpretation:

The larger diverse-opponent data did not help under the current conservative
IQL recipe. The failure is weaker than all-seat training, which confirms that
copying non-anchor policies was harmful, but the filtered recipe still pushes
the checkpoint away from the promoted anchor's gate behavior.

Next useful branch:

1. Stop replay-only variants of this diverse-opponent dataset for now.
2. Move to a different risk target or explicit promotion-gate counterfactuals
   beyond first-divergence pairwise.
3. Keep the promoted anchor unchanged.

### Diagnostic: Promoted Anchor vs Filtered Diverse IQL

Run:
`/root/fh-mahjong-runs/chongci-filtered-diverse-diagnostic-trace-20260611-024027`

Question:
Why did the filtered diverse-opponent replay candidate fail the combined gate,
and what should the next target focus on?

Trace:

- Left policy:
  current promoted anchor,
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Right policy:
  filtered diverse IQL candidate,
  `/root/fh-mahjong-runs/chongci-promoted-diverse-filtered-iql-20260611-022743/checkpoints/promoted_diverse_filtered_iql_lr5e6_bc05/epoch_001.pt`
- Gate windows:
  `534000:10`, `544000:10`, `554000:10`, all four seats.
- Report:
  `/root/fh-mahjong-runs/chongci-filtered-diverse-diagnostic-trace-20260611-024027/reports/promoted_anchor_vs_filtered_diverse_iql_combined_gate_trace.json`

Result:

- Pairs: 120
- First-action divergence rate: 55.83%
- Filtered candidate better rate: 15.00%
- Same-reward rate: 70.00%
- Mean reward delta, candidate minus anchor: -0.0260
- Labeled counterfactual pairs: 36
- High-risk labeled pairs: 10
- Tags:
  10 avoided-large-loss, 2 new-large-loss, 36 worse-reward.
- Preferred action families:
  34 discard, 1 pass, 1 chii.
- Avoided action families:
  34 discard, 2 chii.
- High-risk avoided action families:
  10 discard.

Interpretation:

The failure is mostly not action-family selection. The high-risk cases are
discard-vs-discard disagreements, so the next target should focus on tile-level
discard risk/selection under Chongci score pressure, not broad family weights or
another replay-only IQL pass.

Next useful branch:

1. Build a tile-level discard-risk target from promoted-anchor-vs-candidate
   high-risk discard disagreements.
2. Train it as critic-side/risk-side supervision first, then decide whether it
   should influence the policy.
3. Keep the promoted anchor unchanged until the deterministic combined gate
   improves EV without worsening large-loss rate.

### Experiment: Discard Direct-CF Risk Critic

Run:
`/root/fh-mahjong-runs/chongci-discard-riskcritic-20260611-063150`

Question:
Can a critic-side action-risk head learn tile-level discard risk from the
promoted-anchor-vs-filtered-candidate high-risk discard disagreements?

Data:

- Diagnostic trace:
  `/root/fh-mahjong-runs/chongci-filtered-diverse-diagnostic-trace-20260611-024027/reports/promoted_anchor_vs_filtered_diverse_iql_combined_gate_trace.json`
- Direct-CF high-risk avoided-discard shard:
  `/root/fh-mahjong-runs/chongci-filtered-diverse-diagnostic-trace-20260611-024027/data/highrisk_avoided_discard`
  - 10 rows
  - 10 positive terminal rows
  - mean reward gap 0.4665
- Direct-CF all avoided-discard shard:
  `/root/fh-mahjong-runs/chongci-filtered-diverse-diagnostic-trace-20260611-024027/data/all_avoided_discard`
  - 34 rows
  - 10 positive terminal rows
  - mean reward gap 0.2408
- Broad risk training data:
  capped current replay, prior broader mixed replay, filtered anchor-seat
  diverse-opponent replay, plus the 34-row all-avoided-discard direct-CF shard.

Training:

- Init checkpoint:
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Output checkpoint:
  `/root/fh-mahjong-runs/chongci-discard-riskcritic-20260611-063150/checkpoints/discard_cf_risk_frozen/epoch_002.pt`
- Target mode:
  `family_future_outcome_context`
- Encoder:
  frozen
- Epochs:
  2
- Steps per epoch:
  160
- Batch size:
  2048
- LR:
  `5e-5`
- Paired risk objective:
  `paired_margin_weight=1.0`, `paired_severity_weight=0.5`,
  `paired_batch_fraction=0.25`
- Training report:
  `/root/fh-mahjong-runs/chongci-discard-riskcritic-20260611-063150/reports/discard_cf_risk_frozen_train.json`
- Loaded rows:
  600,034 total, 104,260 positive, 495,774 negative, 34 paired rows.

Training Result:

- Final batch positive predicted risk:
  0.6163
- Final batch negative predicted risk:
  0.5220
- Final paired margin loss:
  0.0000 with 512 paired samples in the batch.

Direct-CF Calibration:

Report:
`/root/fh-mahjong-runs/chongci-discard-riskcritic-20260611-063150/reports/discard_cf_risk_frozen_calibration.json`

| dataset | rows | avoided prob mean | preferred prob mean | prob gap mean | prob gap positive rate | severity gap positive rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all avoided discard | 34 | 0.5458 | 0.3661 | 0.1797 | 100.00% | 79.41% |
| high-risk avoided discard | 10 | 0.8305 | 0.4228 | 0.4077 | 100.00% | 90.00% |

Interpretation:

The critic learned the direct-CF distinction on the small diagnostic shard: the
avoided discard has higher predicted risk than the preferred action in every
direct-CF row. However, this is calibration on only 34 direct-CF rows and is not
enough evidence for serving.

Guarded Evaluation:

Report:
`/root/fh-mahjong-runs/chongci-discard-riskcritic-20260611-063150/reports/discard_cf_risk_guard_policy_nearest_t075_060_gap15_combined_gate.json`

Configuration:

- Anchor policy:
  current promoted anchor
- Risk checkpoint:
  discard direct-CF risk critic
- `anchor_risk_threshold=0.75`
- `candidate_risk_threshold=0.60`
- `min_risk_reduction=0.15`
- `max_policy_logit_gap=1.5`
- Selection mode:
  `policy_nearest`

Result:

| policy | mean reward | reward sum | positive rate | large-loss count | large-loss rate | guard choice rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| current promoted anchor | 0.0100 | 1.4410 | 47.50% | 16 / 120 | 13.33% | 0.00% |
| discard risk guard | -0.0600 | -6.6560 | 45.83% | 23 / 120 | 19.17% | 0.76% |

Decision:

Rejected for guarded serving. The critic is useful as an offline diagnostic,
but the first guarded evaluation strongly regressed EV and large-loss rate even
with a low intervention rate.

Next useful branch:

1. Do not use this risk critic for serving or policy regularization yet.
2. Broaden risk calibration beyond the 34 direct-CF rows before another guard.
3. Prefer building a larger tile-level discard dataset from more paired traces,
   especially later-trajectory discard disagreements, before applying the risk
   head to policy.

### Experiment: Multi-Divergence Tile-Level Discard Calibration

Run:
`/root/fh-mahjong-runs/chongci-multidivergence-trace-20260611-213146`

Question:
Can we broaden tile-level discard calibration beyond the 34 strict
first-divergence direct-CF rows by recording multiple aligned action
disagreements per paired seed/seat trace?

Implementation:

- Added paired-trace `--max-divergences`.
- The default remains `1`, preserving strict first-divergence behavior.
- Values above `1` persist later aligned disagreements as calibration evidence.
- Later rows are not strict same-state counterfactuals after the first different
  action, so they must not be used as promotion-gate proof by themselves.
- Added `build_counterfactual_risk_data.py --divergence-source first|later|all`.
  The default remains `first`.

Validation:

- Local:
  `uv run --project ai pytest ai/tests/test_paired_trace.py ai/tests/test_build_counterfactual_risk_data.py ai/tests/test_train_action_risk.py`
- Remote:
  `/root/.local/bin/uv run --project ai pytest ai/tests/test_paired_trace.py ai/tests/test_build_counterfactual_risk_data.py ai/tests/test_train_action_risk.py`
- Result:
  both passed.

Trace:

- Left:
  current promoted anchor,
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Right:
  rejected filtered diverse IQL,
  `/root/fh-mahjong-runs/chongci-promoted-diverse-filtered-iql-20260611-022743/checkpoints/promoted_diverse_filtered_iql_lr5e6_bc05/epoch_001.pt`
- Seed windows:
  `590000:10`, `600000:10`, `610000:10`
- Seats:
  0, 1, 2, 3
- Pairs:
  120
- Max divergences per pair:
  12
- Report:
  `/root/fh-mahjong-runs/chongci-multidivergence-trace-20260611-213146/reports/promoted_anchor_vs_filtered_diverse_iql_multidiv_trace.json`

Trace Result:

| metric | value |
| --- | ---: |
| pairs | 120 |
| divergence rate | 62.50% |
| right better rate | 19.17% |
| same reward rate | 64.17% |
| mean reward delta | +0.0210 |
| all stored divergences | 635 |
| later divergences | 560 |
| later discard-vs-discard disagreements | 360 |

Direct Shards:

| shard | rows | positive terminal rows | mean reward gap |
| --- | ---: | ---: | ---: |
| `later_avoided_discard` | 361 | 119 | 0.2283 |
| `later_discard_vs_discard` | 287 | 93 | 0.2247 |

Shard paths:

- `/root/fh-mahjong-runs/chongci-multidivergence-trace-20260611-213146/data/later_avoided_discard`
- `/root/fh-mahjong-runs/chongci-multidivergence-trace-20260611-213146/data/later_discard_vs_discard`

Decision:

Accepted as a diagnostic data-generation improvement. The new data source is
large enough to replace the previous 34-row direct-CF shard for calibration
experiments, but later aligned rows are still not promotion evidence.

### Experiment: Later Discard-Vs-Discard Risk Critic

Run:
`/root/fh-mahjong-runs/chongci-later-discard-riskcritic-20260611-215649`

Question:
Can the larger later discard-vs-discard shard train a stronger tile-level
action-risk critic without changing the promoted policy?

Training:

- Init checkpoint:
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Output checkpoint:
  `/root/fh-mahjong-runs/chongci-later-discard-riskcritic-20260611-215649/checkpoints/later_discard_cf_risk_frozen/epoch_002.pt`
- Data:
  broader mixed replay, promoted diverse replay, and
  `later_discard_vs_discard`
- Target mode:
  `family_future_outcome_context`
- Encoder:
  frozen
- Epochs:
  2
- Steps per epoch:
  160
- Batch size:
  2048
- LR:
  `5e-5`
- Pairwise objective:
  `paired_margin_weight=1.0`, `paired_severity_weight=0.5`,
  `paired_batch_fraction=0.25`
- Training report:
  `/root/fh-mahjong-runs/chongci-later-discard-riskcritic-20260611-215649/reports/later_discard_cf_risk_frozen_train.json`
- Loaded rows:
  600,287 total, 96,484 positive, 503,803 negative, 287 paired rows.

Training Result:

| metric | value |
| --- | ---: |
| final loss | 0.8540 |
| final positive probability | 0.5627 |
| final negative probability | 0.5467 |
| final paired margin loss | 0.0001 |
| final paired count | 274 |
| final paired delta MAE | 0.1472 |

Pairwise Calibration:

Report:
`/root/fh-mahjong-runs/chongci-later-discard-riskcritic-20260611-215649/reports/later_discard_vs_discard_pairwise_calibration.json`

| metric | value |
| --- | ---: |
| rows | 287 |
| positive terminal rate | 32.40% |
| avoided probability mean | 0.5848 |
| preferred probability mean | 0.1961 |
| probability gap mean | 0.3887 |
| probability gap positive rate | 100.00% |
| severity gap positive rate | 83.62% |

Terminal Calibration:

Report:
`/root/fh-mahjong-runs/chongci-later-discard-riskcritic-20260611-215649/reports/later_discard_vs_discard_terminal_calibration.json`

| metric | value |
| --- | ---: |
| rows | 287 |
| large-loss rate | 32.40% |
| large-loss AUC | 0.5901 |
| large-loss Brier | 0.3056 |
| large-loss severity MAE | 0.3388 |

Decision:

Rejected for serving / guard use. The critic strongly ranks avoided discards
above preferred discards on the new direct shard, but terminal large-loss AUC is
only 0.5901 and the examples are later aligned disagreements rather than strict
same-state counterfactuals.

Interpretation:

The new tooling solved the data-volume problem for tile-level discard
calibration. It did not yet solve independent risk calibration. The right next
move is to use these rows for analysis and to mine stricter same-state or
near-state discard counterfactuals, not to run another guard threshold sweep.

### Experiment: Near-State Discard Counterfactual Extraction

Run:
`/root/fh-mahjong-runs/chongci-multidivergence-trace-20260611-213146`

Question:
How many of the 287 later discard-vs-discard rows remain useful after requiring
near-state evidence: both candidate discard tiles legal in both observations,
small visible-scalar distance, and similar legal-action masks?

Implementation:

- Added `fh_mahjong_ai.near_state_counterfactuals`.
- Added CLI:
  `python -m fh_mahjong_ai.scripts.extract_near_state_discards`
- The extractor filters tensor-bearing paired traces by:
  - discard-vs-discard preferred/avoided actions,
  - non-zero reward gap,
  - both chosen discard actions legal in both recorded observations,
  - bounded `decision_index` gap,
  - bounded visible-scalar L1/Linf distance,
  - minimum action-mask Jaccard overlap.
- This is still diagnostic. Later aligned disagreements are not promotion proof.

Validation:

- Local:
  `uv run --project ai pytest ai/tests/test_near_state_counterfactuals.py ai/tests/test_paired_trace.py ai/tests/test_build_counterfactual_risk_data.py ai/tests/test_train_action_risk.py`
- Result:
  28 passed.
- Remote:
  `/root/.local/bin/uv run --project ai pytest ai/tests/test_near_state_counterfactuals.py ai/tests/test_paired_trace.py ai/tests/test_build_counterfactual_risk_data.py`
- Result:
  19 passed.

Reports:

| filter | report | cases | high-risk cases | mean reward gap |
| --- | --- | ---: | ---: | ---: |
| strict | `/root/fh-mahjong-runs/chongci-multidivergence-trace-20260611-213146/reports/near_state_later_discard_vs_discard_strict.json` | 8 | 3 | 0.1315 |
| relaxed gap 2 | `/root/fh-mahjong-runs/chongci-multidivergence-trace-20260611-213146/reports/near_state_later_discard_vs_discard_relaxed_gap2.json` | 16 | 4 | 0.1194 |
| relaxed gap 4 | `/root/fh-mahjong-runs/chongci-multidivergence-trace-20260611-213146/reports/near_state_later_discard_vs_discard_relaxed_gap4.json` | 24 | 8 | 0.1179 |

Strict filter:

- `max_decision_index_gap=0`
- `max_scalar_l1=0.10`
- `max_scalar_linf=0.25`
- `min_action_mask_jaccard=0.95`

Relaxed gap 4 filter:

- `max_decision_index_gap=4`
- `max_scalar_l1=0.20`
- `max_scalar_linf=0.45`
- `min_action_mask_jaccard=0.85`

Main Rejection Reason:

In the strict extraction, 224 rows were rejected because the alternate discard
was not legal in both observations. This means most later aligned
discard-vs-discard rows are not true tile-swap comparisons, even when the action
family matches.

Decision:

Do not train from the near-state filtered rows. The strict set has only 8 cases,
and the relaxed set has only 24. That is useful as a diagnostic sanity check but
too small for the next risk critic.

Interpretation:

The next data step should not be more filtering of later aligned disagreements.
We need stricter same-state counterfactuals:

1. first-divergence discard-vs-discard traces over more independent windows, or
2. environment snapshot/branching support so the same visible state can be
   stepped with alternate legal discard actions.

The second option is the more correct long-term path, but it requires Go bridge
state snapshot/restore or an explicit branch-evaluation API.

### Experiment: Strict First-Divergence Discard Counterfactuals

Runs:

- `/root/fh-mahjong-runs/chongci-firstdiv-discard-trace-20260611-230907`
- `/root/fh-mahjong-runs/chongci-firstdiv-discard-trace-diverseall-20260611-234813`

Question:
Can strict first-divergence discard-vs-discard traces provide cleaner
same-state tile-level counterfactuals than later aligned disagreements?

Trace A:

- Left:
  current promoted anchor,
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Right:
  rejected filtered diverse IQL,
  `/root/fh-mahjong-runs/chongci-promoted-diverse-filtered-iql-20260611-022743/checkpoints/promoted_diverse_filtered_iql_lr5e6_bc05/epoch_001.pt`
- Seed windows:
  `620000:20`, `640000:20`, `680000:20`
- Pairs:
  240
- Report:
  `/root/fh-mahjong-runs/chongci-firstdiv-discard-trace-20260611-230907/reports/promoted_anchor_vs_filtered_diverse_iql_firstdiv_trace.json`

Trace A result:

| metric | value |
| --- | ---: |
| divergence rate | 62.08% |
| candidate better rate | 17.08% |
| same reward rate | 65.00% |
| mean reward delta | -0.0048 |
| labeled first-divergence pairs | 84 |
| high-risk labeled pairs | 19 |
| first discard-vs-discard rows | 78 |
| positive terminal rows | 17 |
| mean reward gap | 0.2449 |

Trace B:

- Left:
  current promoted anchor,
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Right:
  rejected all-seat diverse IQL,
  `/root/fh-mahjong-runs/chongci-promoted-diverse-iql-20260611-021603/checkpoints/promoted_diverse_iql_lr5e6_bc05/epoch_001.pt`
- Seed windows:
  `700000:20`, `720000:20`, `740000:20`
- Pairs:
  240
- Report:
  `/root/fh-mahjong-runs/chongci-firstdiv-discard-trace-diverseall-20260611-234813/reports/promoted_anchor_vs_diverse_all_iql_firstdiv_trace.json`

Trace B result:

| metric | value |
| --- | ---: |
| divergence rate | 67.50% |
| candidate better rate | 15.83% |
| same reward rate | 62.08% |
| mean reward delta | -0.0005 |
| labeled first-divergence pairs | 91 |
| high-risk labeled pairs | 17 |
| first discard-vs-discard rows | 82 |
| positive terminal rows | 16 |
| mean reward gap | 0.1862 |

Interpretation From Data Generation:

Strict first-divergence rows are much cleaner than later aligned disagreements.
Across two 240-pair traces, we got 160 strict discard-vs-discard rows with 33
large-loss rows. This is still small, but it is high-quality enough for one
diagnostic critic run.

### Experiment: Strict First-Divergence Risk Critic

Run:
`/root/fh-mahjong-runs/chongci-strict-firstdiv-riskcritic-20260612-002627`

Question:
Can a risk critic trained on strict first-divergence discard-vs-discard rows
generalize to an independent strict first-divergence holdout?

Training:

- Init checkpoint:
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Output checkpoint:
  `/root/fh-mahjong-runs/chongci-strict-firstdiv-riskcritic-20260612-002627/checkpoints/strict_firstdiv_discard_risk_frozen/epoch_002.pt`
- Data:
  broader mixed replay, promoted diverse replay, Trace A `first_discard_vs_discard`,
  Trace B `first_discard_vs_discard`
- Target mode:
  `family_future_outcome_context`
- Encoder:
  frozen
- Epochs:
  2
- Steps per epoch:
  160
- Batch size:
  2048
- LR:
  `5e-5`
- Pairwise objective:
  `paired_margin_weight=1.0`, `paired_severity_weight=0.5`,
  `paired_batch_fraction=0.25`
- Training report:
  `/root/fh-mahjong-runs/chongci-strict-firstdiv-riskcritic-20260612-002627/reports/strict_firstdiv_discard_risk_frozen_train.json`
- Loaded rows:
  600,160 total, 96,424 positive, 503,736 negative, 160 paired rows.

Training Result:

| metric | value |
| --- | ---: |
| final loss | 0.8723 |
| final positive probability | 0.5435 |
| final negative probability | 0.5193 |
| final paired margin loss | 0.0146 |
| final paired count | 512 |
| final paired delta MAE | 0.1444 |

Pairwise Calibration:

Report:
`/root/fh-mahjong-runs/chongci-strict-firstdiv-riskcritic-20260612-002627/reports/strict_firstdiv_pairwise_calibration.json`

| dataset | rows | prob gap mean | prob gap positive rate | severity gap positive rate |
| --- | ---: | ---: | ---: | ---: |
| train filtered first-div | 78 | 0.2011 | 98.72% | 78.21% |
| train diverse-all first-div | 82 | 0.1492 | 100.00% | 67.07% |
| holdout filtered first-div 590/600/610 | 39 | 0.0587 | 58.97% | 51.28% |

Terminal Holdout Calibration:

Report:
`/root/fh-mahjong-runs/chongci-strict-firstdiv-riskcritic-20260612-002627/reports/strict_firstdiv_holdout_terminal_calibration.json`

| metric | value |
| --- | ---: |
| holdout rows | 39 |
| large-loss rate | 33.33% |
| large-loss AUC | 0.3166 |
| large-loss Brier | 0.3938 |
| large-loss severity MAE | 0.4500 |

Decision:

Rejected for guarded serving and policy regularization. The critic fits the two
strict training shards but fails the independent strict first-divergence holdout.
Do not tune thresholds around this critic.

Interpretation:

Strict first-divergence data is the right direction, but 160 rows is not enough
coverage for a robust action-risk critic. The next useful choices are:

1. collect more strict first-divergence discard-vs-discard rows across more
   candidate checkpoints and independent windows, or
2. implement exact state snapshot/branch evaluation in the Go bridge so we can
   evaluate alternate legal discards from the same state directly.

The second path is more likely to become a durable reward-learning primitive,
because it would create explicit counterfactual labels instead of hoping paired
checkpoint divergences cover enough tile choices.

### Implementation: Exact Go Branch Evaluation

Date:
2026-06-12

Question:
Can we create exact same-state counterfactual labels for candidate actions
instead of relying only on paired checkpoint divergences?

Change:
Added `core.Game.CloneForBranch()` and `rlenv.Env.EvaluateBranches()`.
The branch evaluator clones the authoritative Go state machine, applies one
candidate action from the current learning-seat decision, then lets the shared
deterministic heuristic policy finish the branch. The live environment remains
unchanged. The c-shared bridge now exports `FHEnvEvaluateBranches`, and Python
exposes it as `CtypesGoBridge.evaluate_branches()`.

Validation:

| check | result |
| --- | --- |
| `go test ./core ./rlenv ./cmd/rlbridge` | pass |
| `uv run --project ai pytest ai/tests/test_bridge.py` | pass |
| `go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge` | pass |
| Python real-bridge branch smoke, seed 71, actions 8 and 9 | pass |

Smoke result:
From the same current Go observation, action 8 rolled out to rewards
`[-0.008, -0.008, -0.008, 0.024]` after 52 branch decisions, while action 9
rolled out to `[-0.052, -0.052, 0.208, -0.104]` after 36 branch decisions.
Both branches terminated normally and returned no branch error.

Decision:
Merged direction locally as the next reward-learning primitive, but not yet a
promoted agent. This is tooling for exact counterfactual dataset generation.

Interpretation:
This removes the main data bottleneck seen in strict first-divergence paired
trace work: we no longer need two checkpoints to naturally disagree on the
same state before comparing alternate legal discards. The next experiment
should generate branch-evaluated discard counterfactual shards from mixed
self-play states and train the action-risk/reward auxiliary on those direct
labels.

Follow-up implementation:
Added `fh-mj-generate-branch-counterfactuals`, which collects states from
checkpoint/random self-play seats, evaluates legal discard branches through
`EvaluateBranches`, and writes direct pairwise NPZ shards compatible with
`fh-mj-train-iql --pairwise-data`.

Generator smoke:

```bash
uv run --project ai fh-mj-generate-branch-counterfactuals \
  --episodes 1 \
  --start-seed 71 \
  --output-dir /tmp/fh-branch-cf-smoke \
  --seat-policy 0=random \
  --match-mode classic \
  --max-steps-per-episode 512 \
  --max-rows 1 \
  --max-branch-actions 2 \
  --seed 7
```

Result:
The smoke produced one direct discard-vs-discard pairwise row with mean reward
gap `0.296`, using the real Go c-shared bridge. This validates the data path;
the next useful remote run is a larger Chongci checkpoint-state generation job.

### Experiment: Branch Counterfactual Pairwise IQL V1

Run:
`/root/fh-mahjong-runs/chongci-branch-cf-iql-20260612-010350`

Question:
Can exact same-state Go branch labels for alternate legal discards improve the
promoted Chongci anchor when used as pairwise-only IQL supervision?

Data:

- Branch-CF run:
  `/root/fh-mahjong-runs/chongci-branch-cf-anchor-20260612-005749`
- Branch-CF shard:
  `/root/fh-mahjong-runs/chongci-branch-cf-anchor-20260612-005749/data/anchor-branch-cf-821000-r512`
- Controlled seat: seat 0 using the promoted Chongci anchor checkpoint
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Opponents: Go heuristic seats.
- Rows: 512 discard-vs-discard same-state pairwise labels.
- Branch calls: 911.
- Branch results: 4198.
- Branch mode: stop at next round end, branch cap 1024 decisions.
- Max branch actions per decision: 4.
- Minimum reward gap: `0.01`.
- Mean reward gap: `0.141244`.
- Max reward gap: `1.842`.
- Generation time: `135.45s`.

Training:

- Output checkpoint:
  `/root/fh-mahjong-runs/chongci-branch-cf-iql-20260612-010350/checkpoints/branch_cf_pairwise_iql/epoch_001.pt`
- Init checkpoint:
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Normal replay:
  `/root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz`
  and
  `/root/fh-mahjong-runs/chongci-broader-mixed-selfplay-20260607-032601/data/anchor-fresh-balanced-tail2-760000-n200-npz`
- Epochs: 1.
- Batch size: 4096.
- Learning rate: `1e-5`.
- Target mode: MC, `gamma=0.99`.
- IQL: `expectile=0.7`, `temperature=3.0`, `max_weight=20`.
- BC weight: `0.03`.
- Pairwise policy: weight `0.005`, margin `0.04`.
- Pairwise Q: weight `0.15`, margin `0.08`.
- Reward-delta scaling: weight `0.25`, margin scale `0.1`, clip `2.0`.
- Max transitions per normal dataset: 200000.
- MLflow run id: `ecbad1c2611f4f0d944d208f0379aa38`.

Evaluation:

- Gate: duplicate-seat combined gate over `534000:10`, `544000:10`,
  `554000:10`.
- Seats: 120.
- Candidate report:
  `/root/fh-mahjong-runs/chongci-branch-cf-iql-20260612-010350/reports/branch_cf_pairwise_iql_combined_gate_534_544_554_n10.json`
- Anchor repeat report:
  `/root/fh-mahjong-runs/chongci-branch-cf-iql-20260612-010350/reports/current_anchor_combined_gate_534_544_554_n10.json`
- Candidate MLflow eval run: `3629dce6a5d04ba08ffe9f1e42f53ab7`.
- Anchor MLflow eval run: `ec5fd10e544a464cbf0575503f2f4af5`.

Result:

| metric | branch-CF candidate | current anchor | delta |
| --- | ---: | ---: | ---: |
| seats | 120 | 120 | 0 |
| reward sum | -3.3690 | 1.4410 | -4.8100 |
| mean reward | -0.03 | 0.01 | -0.04 |
| positive-reward rate | 45.83% | 47.50% | -1.67pp |
| large-loss count | 19 | 16 | +3 |
| large-loss rate | 15.83% | 13.33% | +2.50pp |

Decision:
Rejected. The exact branch labels and training pipeline worked, but this first
512-row pairwise IQL update regressed EV, positive-reward rate, and tail risk.
The promoted Chongci checkpoint remains unchanged.

Interpretation:
The new branch evaluator is useful, but directly pushing 512 round-end
discard-pair labels into policy/Q margins is too blunt at this dose. Do not
promote this checkpoint. Next useful options are: collect more branch rows,
lower pairwise pressure, or use the exact branch labels first for
critic/calibration analysis before shaping the deployed policy.

Calibration follow-up:
Added `fh-mj-branch-cf-calibration` to score the exact branch-CF shard without
running a new gate. The diagnostic compares whether a checkpoint ranks the
preferred branch action above the avoided branch action under policy logits,
Q-values, and optional action-risk outputs.

Reports:

- Anchor:
  `/root/fh-mahjong-runs/chongci-branch-cf-iql-20260612-010350/reports/anchor_branch_cf_calibration_r512.json`
- Candidate:
  `/root/fh-mahjong-runs/chongci-branch-cf-iql-20260612-010350/reports/candidate_branch_cf_calibration_r512.json`

MLflow runs:

- Anchor calibration: `4bbb00ee8b3441f1bde16e4e4e5fcf85`
- Candidate calibration: `8bf0f0c46fc64218b5622cbabd69b2d3`

Calibration result:

| metric | anchor | branch-CF candidate | delta |
| --- | ---: | ---: | ---: |
| rows | 512 | 512 | 0 |
| policy preferred rate | 63.09% | 63.87% | +0.78pp |
| policy reward-gap-weighted preferred rate | 59.18% | 59.69% | +0.51pp |
| Q preferred rate | 50.59% | 56.05% | +5.47pp |
| Q reward-gap-weighted preferred rate | 50.74% | 56.00% | +5.25pp |
| risk lower-is-better preferred rate | 51.17% | 51.37% | +0.20pp |
| policy argmax preferred-action rate | 31.84% | 31.84% | 0.00pp |
| Q argmax preferred-action rate | 8.01% | 9.57% | +1.56pp |

High-gap slice:

| reward-gap bucket | rows | anchor policy preferred | candidate policy preferred | anchor Q preferred | candidate Q preferred |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0.50+` | 12 | 41.67% | 41.67% | 41.67% | 41.67% |

Interpretation:
The rejected candidate did learn the branch labels somewhat, especially in the
Q head, so the training signal was not inactive. However, that improvement did
not transfer to duplicate-seat evaluation, and the current 512-row shard has
only 12 large-gap rows. The next run should increase exact branch-CF coverage
and high-gap diversity before applying stronger policy/Q shaping. This also
rules out simply rerunning nearby coefficients on the same small shard.

### Experiment: Larger Branch Counterfactual Low-Pressure IQL

Run:
`/root/fh-mahjong-runs/chongci-branch-cf-large-iql-20260613-000745-retry`

Question:
Does a larger exact branch-CF shard with better high-gap coverage and lower
pairwise pressure transfer better than the rejected 512-row branch-CF update?

Data:

- Branch-CF data run:
  `/root/fh-mahjong-runs/chongci-branch-cf-anchor-large-20260612-235507`
- Branch-CF shard:
  `/root/fh-mahjong-runs/chongci-branch-cf-anchor-large-20260612-235507/data/anchor-branch-cf-831000-r2048-gap002-b6`
- Rows: 2048 discard-vs-discard same-state labels.
- Episodes requested: 1200.
- Start seed: 831000.
- Controlled seat: promoted Chongci anchor, seat 0.
- Opponents: Go heuristic seats.
- Branch calls: 3349.
- Branch results: 21378.
- Branch mode: stop at next round end, branch cap 1024 decisions.
- Max branch actions per decision: 6.
- Minimum reward gap: `0.02`.
- Mean reward gap: `0.188823`.
- Max reward gap: `1.824`.
- High-gap rows (`reward_gap >= 0.50`): 120.
- Generation time: `682.29s`.

Pre-training calibration:

| checkpoint | policy preferred | Q preferred | risk lower-is-better |
| --- | ---: | ---: | ---: |
| promoted anchor | 56.98% | 51.22% | 51.90% |
| rejected 512-row candidate | 57.32% | 51.66% | 51.76% |

The rejected 512-row candidate barely generalized to this larger branch-CF
shard, which confirms that the previous small-shard calibration gain was not
enough evidence for promotion.

Training:

- Output checkpoint:
  `/root/fh-mahjong-runs/chongci-branch-cf-large-iql-20260613-000745-retry/checkpoints/branch_cf_large_lowpressure_iql/epoch_001.pt`
- Init checkpoint:
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Normal replay:
  `/root/fh-mahjong-runs/chongci-capped400k-lowdrift-mlflow-run-20260525-230058/data/selfplay-current-capped400k-npz`
  and
  `/root/fh-mahjong-runs/chongci-broader-mixed-selfplay-20260607-032601/data/anchor-fresh-balanced-tail2-760000-n200-npz`
- Epochs: 1.
- Batch size: 4096.
- Learning rate: `1e-5`.
- Target mode: MC, `gamma=0.99`.
- IQL: `expectile=0.7`, `temperature=3.0`, `max_weight=20`.
- BC weight: `0.05`.
- Pairwise policy: weight `0.001`, margin `0.03`.
- Pairwise Q: weight `0.05`, margin `0.05`.
- Reward-delta scaling: weight `0.10`, margin scale `0.08`, clip `2.0`.
- Max transitions: 200000.
- MLflow run id: `165a48077a0b40aaa2a8babcb649349f`.

Training log:

- Pairwise rows loaded: 2048.
- Pairwise batches were active, with logged `pairwise_count` values 15, 22,
  and 27 at steps 25, 50, and 75.
- Final epoch average loss: `0.0728`.

Post-training calibration:

| metric | anchor | candidate | delta |
| --- | ---: | ---: | ---: |
| policy preferred rate | 56.98% | 57.28% | +0.29pp |
| policy reward-gap-weighted preferred rate | 57.63% | 58.10% | +0.47pp |
| Q preferred rate | 51.22% | 54.15% | +2.93pp |
| Q reward-gap-weighted preferred rate | 50.46% | 53.53% | +3.06pp |
| high-gap Q preferred rate | 55.83% | 58.33% | +2.50pp |

Calibration report:
`/root/fh-mahjong-runs/chongci-branch-cf-large-iql-20260613-000745-retry/reports/large_lowpressure_branch_cf_calibration_r2048.json`

Evaluation:

- Gate: duplicate-seat combined gate over `534000:10`, `544000:10`,
  `554000:10`.
- Seats: 120.
- Correct candidate report:
  `/root/fh-mahjong-runs/chongci-branch-cf-large-iql-20260613-000745-retry/reports/large_lowpressure_combined_gate_534_544_554_n10_max8192.json`
- MLflow eval run: `8daa8f94807f4d188e4f7d02aa90622b`.
- Invalid first eval:
  `/root/fh-mahjong-runs/chongci-branch-cf-large-iql-20260613-000745-retry/reports/large_lowpressure_combined_gate_534_544_554_n10.json`
  used the default step cap and all 120 matches truncated, so it is ignored.

Result:

| metric | large branch-CF candidate | current anchor | delta |
| --- | ---: | ---: | ---: |
| seats | 120 | 120 | 0 |
| reward sum | -2.9230 | 1.4410 | -4.3640 |
| mean reward | -0.02 | 0.01 | -0.03 |
| positive-reward rate | 45.00% | 47.50% | -2.50pp |
| large-loss count | 18 | 16 | +2 |
| large-loss rate | 15.00% | 13.33% | +1.67pp |

Decision:
Rejected. The larger shard and lower pairwise pressure improved exact branch
Q ranking, but duplicate-seat EV, positive rate, and large-loss rate all
regressed versus the promoted anchor.

Interpretation:
Short-horizon branch-CF labels are useful diagnostics, and the Q head can be
nudged toward them. But direct policy/Q margin shaping from these labels is not
yet transferring to better full-match play. Stop this direct branch-CF shaping
line for now. Keep the larger shard for critic-side calibration or analysis,
but do not promote or serve this checkpoint.

### Experiment: Branch-CF Frozen Action-Risk Critic

Run:
`/root/fh-mahjong-runs/chongci-branch-cf-riskcritic-20260613-004101`

Question:
Can exact same-state branch-CF rows train a critic-side action-risk head that
recognizes risky discard alternatives, without changing the deployed policy?

Data:

- Training shard:
  `/root/fh-mahjong-runs/chongci-branch-cf-anchor-large-20260612-235507/data/anchor-branch-cf-831000-r2048-gap002-b6`
- Rows: 2048.
- Bad-branch threshold: avoided branch reward `<= -0.2`.
- Positive avoided branches: 328.
- Negative avoided branches: 1720.
- Pairwise supervision: all 2048 rows.

Training:

- Output checkpoint:
  `/root/fh-mahjong-runs/chongci-branch-cf-riskcritic-20260613-004101/checkpoints/branch_cf_risk_frozen_t020/epoch_003.pt`
- Init checkpoint:
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Encoder: frozen.
- Epochs: 3.
- Steps per epoch: 120.
- Batch size: 1024.
- Learning rate: `5e-5`.
- Target mode: terminal.
- Threshold: `-0.2`.
- Paired margin weight: `1.0`.
- Paired severity weight: `0.25`.
- Paired margin: `0.10`.
- Paired delta scale: `0.5`.
- Paired delta clip: `3.0`.
- Paired batch fraction: `0.5`.
- Report:
  `/root/fh-mahjong-runs/chongci-branch-cf-riskcritic-20260613-004101/reports/branch_cf_risk_frozen_t020_train.json`

Training behavior:
The paired margin loss was active on every logged step with `paired_count=1024`.
It fell from `1.4725` at epoch 1 step 1 to `0.3807` at epoch 3 step 120.
The probability head also separated terminal branch labels: at the final logged
step, positive branch probability was `0.484` and negative branch probability
was `0.307`.

In-sample branch-CF calibration:

- Report:
  `/root/fh-mahjong-runs/chongci-branch-cf-riskcritic-20260613-004101/reports/branch_cf_risk_frozen_t020_calibration_r2048.json`
- MLflow run: `2d1e3e924f344b199d749cbaf42ab173`.
- Risk lower-is-better preferred rate: `76.46%`.

Holdout data:

- Holdout run:
  `/root/fh-mahjong-runs/chongci-branch-cf-holdout-20260613-004200`
- Holdout shard:
  `/root/fh-mahjong-runs/chongci-branch-cf-holdout-20260613-004200/data/anchor-branch-cf-841000-r512-gap002-b6`
- Rows: 512.
- Branch calls: 811.
- Branch results: 5168.
- Max branch actions per decision: 6.
- Minimum reward gap: `0.02`.
- Mean reward gap: `0.176687`.
- Max reward gap: `2.124`.
- Generation time: `193.73s`.

Holdout calibration:

| checkpoint / head | risk preferred | weighted risk preferred | high-gap risk preferred |
| --- | ---: | ---: | ---: |
| promoted anchor risk head | 52.15% | 51.65% | 42.86% |
| branch-CF frozen risk critic | 61.91% | 59.63% | 57.14% |

For reference, the reward/Q heads still did not solve this holdout:

| checkpoint | Q preferred | weighted Q preferred | high-gap Q preferred |
| --- | ---: | ---: | ---: |
| promoted anchor | 49.22% | 47.27% | 28.57% |
| large low-pressure branch-CF IQL candidate | 49.61% | 48.95% | 33.33% |

Larger independent holdout:

- Holdout run:
  `/root/fh-mahjong-runs/chongci-branch-cf-holdout-large-20260613-004827`
- Holdout shard:
  `/root/fh-mahjong-runs/chongci-branch-cf-holdout-large-20260613-004827/data/anchor-branch-cf-851000-r2048-gap002-b6`
- Rows: 2048.
- Branch calls: 3376.
- Branch results: 21410.
- Mean reward gap: `0.215305`.
- Max reward gap: `3.849`.
- High-gap rows (`reward_gap >= 0.50`): 152.
- Generation time: `1174.80s`.

Larger holdout calibration:

| checkpoint / head | risk preferred | weighted risk preferred | high-gap risk preferred |
| --- | ---: | ---: | ---: |
| promoted anchor risk head | 53.22% | 51.31% | 53.95% |
| branch-CF frozen risk critic | 63.18% | 61.99% | 65.13% |

Larger holdout reports:

- Anchor:
  `/root/fh-mahjong-runs/chongci-branch-cf-holdout-large-20260613-004827/reports/anchor_calibration_holdout_large_r2048.json`
- Branch-CF risk critic:
  `/root/fh-mahjong-runs/chongci-branch-cf-holdout-large-20260613-004827/reports/branch_cf_risk_frozen_t020_calibration_holdout_large_r2048.json`

Decision:
Diagnostic only. The branch-CF risk critic generalizes better than the anchor
risk head on both a 512-row and a 2048-row independent holdout. However, no
guarded-serving or policy-regularized duplicate-seat gate has passed. Do not
serve this critic yet.

Interpretation:
This is the first branch-CF result that transfers in the intended critic-side
direction: a frozen risk head can learn that the preferred branch should look
less risky than the avoided branch better than the default anchor risk head.
The result is still not a policy improvement by itself. Next useful work is a
deliberately conservative risk-guard experiment around the promoted anchor, with
promotion allowed only if duplicate-seat EV is not harmed and large-loss rate is
no worse than the unguarded anchor.

Guard screen:
The first conservative guard used the promoted anchor policy by default and
allowed the risk critic to substitute a nearby lower-risk legal action only when
all filters passed.

Configuration:

- Report:
  `/root/fh-mahjong-runs/chongci-branch-cf-riskcritic-20260613-004101/reports/risk_guarded_policy_nearest_gate_534_544_554_n10.json`
- Gate: duplicate-seat combined gate over `534000:10`, `544000:10`,
  `554000:10`.
- Seats: 120.
- Selection mode: `policy_nearest`.
- Candidate risk threshold: `0.45`.
- Minimum risk reduction: `0.15`.
- Maximum policy logit gap: `1.5`.
- Anchor risk thresholds swept: `0.55`, `0.65`, `0.75`.

Guard result:

| anchor risk threshold | reward sum | mean reward | positive rate | large-loss rate | guard choice rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| unguarded anchor | 1.4410 | 0.01 | 47.50% | 13.33% | 0.00% |
| `0.55` | -4.5270 | -0.0377 | 46.67% | 18.33% | 0.82% |
| `0.65` | -4.5810 | -0.0382 | 44.17% | 16.67% | 0.53% |
| `0.75` | -2.0110 | -0.0168 | 45.00% | 15.00% | 0.27% |

Guard decision:
Rejected. Even sparse guard interventions worsened EV and tail risk versus the
unguarded anchor. The critic remains useful for offline branch-risk analysis,
but it is not serving- or policy-regularization-ready.

Exact branch-CF guard preflight:
Added `fh-mj-branch-cf-guard-diagnostics` to compare a guard configuration
against exact branch-CF labels before running another duplicate-seat gate. The
diagnostic checks whether guard interventions turn an exact avoided branch into
the exact preferred branch, and whether the exact preferred branch even passes
the guard filters.

Report:
`/root/fh-mahjong-runs/chongci-branch-cf-riskcritic-20260613-004101/reports/risk_guarded_policy_nearest_branch_cf_preflight_holdout_large_r2048.json`

Preflight data:
`/root/fh-mahjong-runs/chongci-branch-cf-holdout-large-20260613-004827/data/anchor-branch-cf-851000-r2048-gap002-b6`

Preflight result:

| anchor risk threshold | guard changes | rescues avoided->preferred | harms preferred->avoided | known reward delta | changes to unlabeled |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0.55` | 17 | 0 | 0 | 0.0000 | 17 |
| `0.65` | 11 | 0 | 0 | 0.0000 | 11 |
| `0.75` | 7 | 0 | 0 | 0.0000 | 7 |

Filter diagnosis:

- Anchor chose the exact avoided branch on 241 of 2048 rows.
- Exact preferred branch passed the `max_policy_logit_gap <= 1.5` filter on
  only 4 of those 241 anchor-avoided rows.
- Exact preferred branch passed all current guard filters on 0 rows at every
  tested threshold.
- Median anchor-to-preferred policy logit gap on anchor-avoided rows was
  `20.6959`, so the current guard design is fundamentally policy-near and
  cannot reach many exact preferred branch alternatives.

Preflight decision:
This explains the failed duplicate-seat guard: it was not performing exact
branch rescues. It was making rare substitutions into actions outside the
preferred/avoided branch label pair, so the offline branch-CF evidence did not
support the live guard. Do not run nearby guard-threshold sweeps. Any future
guard must first show positive rescue count and positive known reward-gap delta
on exact branch-CF preflight before duplicate-seat evaluation.

Oracle preferred-branch preflight:
Extended `fh-mj-branch-cf-guard-diagnostics` with an upper-bound diagnostic that
asks whether the exact preferred branch would pass risk filters if the
policy-logit gap cap were relaxed. This is not a serving policy. It separates
two failure modes: a critic that cannot identify safer preferred branches versus
a proposal policy that cannot reach those branches.

Report:
`/root/fh-mahjong-runs/chongci-branch-cf-riskcritic-20260613-004101/reports/risk_guarded_policy_nearest_branch_cf_preflight_holdout_large_r2048_oracle.json`

Oracle preflight result on the 2048-row large holdout:

| anchor risk threshold | base risk-filter pass | cap `1.5` rescue delta | cap `3.0` rescue delta | cap `6.0` rescue delta | cap `12.0` rescue delta | cap `24.0` rescue delta | no cap rescue delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0.55` | 30 | 0 / 0.0000 | 1 / 0.3280 | 6 / 1.5620 | 11 / 2.2050 | 28 / 4.7600 | 30 / 4.8980 |
| `0.65` | 24 | 0 / 0.0000 | 1 / 0.3280 | 5 / 1.3460 | 10 / 1.9890 | 22 / 3.6410 | 24 / 3.7790 |
| `0.75` | 11 | 0 / 0.0000 | 0 / 0.0000 | 3 / 0.6840 | 4 / 1.0000 | 10 / 2.0120 | 11 / 2.1140 |

Interpretation:
The frozen risk critic is not useless: when handed the exact preferred branch,
it allows some positive reward-gap rescues under relaxed policy-distance caps.
The current `max_policy_logit_gap <= 1.5` guard allows none. The blocker is
therefore mainly action proposal / policy prior mismatch, not just risk-score
calibration. A future branch should train the policy to make exact preferred
branch actions reachable, or use branch-CF data as policy-side distillation,
before another duplicate-seat guard gate.

Policy-side branch-CF distillation pilot:
After the oracle preflight showed a policy-prior mismatch, ran a one-epoch
policy-side branch-CF distillation pilot. This reused the promoted Chongci
checkpoint as initialization, trained on the current mixed self-play replay, and
added the 2048-row exact branch-CF shard as direct pairwise auxiliary data.
`--pairwise-replay-multiplier` was extended to apply to direct `--pairwise-data`
rows so the branch-CF rows are not drowned by the much larger mixed replay.

Run:
`/root/fh-mahjong-runs/chongci-branch-cf-policy-distill-20260614-0638`

Training:

- Main data:
  `/root/fh-mahjong-runs/chongci-broader-mixed-selfplay-20260607-032601/data/anchor-fresh-balanced-tail2-760000-n200-npz`
- Pairwise data:
  `/root/fh-mahjong-runs/chongci-branch-cf-anchor-large-20260612-235507/data/anchor-branch-cf-831000-r2048-gap002-b6`
- Init checkpoint:
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- Candidate checkpoint:
  `/root/fh-mahjong-runs/chongci-branch-cf-policy-distill-20260614-0638/checkpoints/branch_cf_policy_distill_w4_m6_repeat128/epoch_001.pt`
- Pairwise replay rows after multiplier: `262144`.
- Pairwise policy weight: `4.0`.
- Pairwise margin: `6.0`.
- Pairwise reward-delta weight: `2.0`.
- Pairwise reward-delta margin scale: `2.0`.
- Q-side pairwise weight: `0.0`.
- Epochs: `1`.

Branch-CF calibration:

| dataset | policy preferred margin rate | policy preferred argmax | policy avoided argmax | Q preferred margin rate |
| --- | ---: | ---: | ---: | ---: |
| train branch-CF r2048 | 99.95% | 33.45% | 0.00% | 53.17% |
| holdout branch-CF r2048 | 61.28% | 23.68% | 10.64% | 50.54% |

Calibration reports:

- Train:
  `/root/fh-mahjong-runs/chongci-branch-cf-policy-distill-20260614-0638/reports/policy_distill_train_branch_cf_calibration_r2048.json`
- Holdout:
  `/root/fh-mahjong-runs/chongci-branch-cf-policy-distill-20260614-0638/reports/policy_distill_holdout_branch_cf_calibration_r2048.json`
- Candidate-as-anchor preflight:
  `/root/fh-mahjong-runs/chongci-branch-cf-policy-distill-20260614-0638/reports/policy_distill_as_anchor_branch_cf_preflight_holdout_r2048.json`

Smoke evaluation:

| screen | seats | mean reward | positive rate | large-loss rate |
| --- | ---: | ---: | ---: | ---: |
| `534000:2` duplicate seats | 8 | -0.26 | 37.50% | 62.50% |

Smoke report:
`/root/fh-mahjong-runs/chongci-branch-cf-policy-distill-20260614-0638/reports/policy_distill_smoke_534000_n2.json`

Decision:
Rejected before full duplicate-seat gate. The pilot proves the policy logits can
be moved toward exact branch-CF labels, but the resulting live policy is not
gameplay-safe. The full `534000/544000/554000` gate was started and stopped
after roughly eight minutes with no report because the smaller smoke already
showed severe tail-risk regression.

Interpretation:
Naively forcing branch-CF preferred actions into the policy head overfits the
exact branch labels and damages broad policy behavior. The next branch should
not increase this loss further. Use branch-CF labels more conservatively:
filtered high-confidence rows, family-specific distillation, KL anchoring to
the promoted policy, or an action-proposal head evaluated offline before any
live gate.

KL-anchored branch-CF distillation pilots:
Added two safety controls to `fh-mj-train-iql` before retrying policy-side
branch-CF distillation:

- `--pairwise-data-min-reward-gap` filters direct `--pairwise-data` rows by
  `pairwise_reward_delta_targets`.
- `--policy-kl-anchor-checkpoint` plus `--policy-kl-weight` regularizes the
  trained masked policy distribution toward a frozen promoted-anchor policy.

First KL pilot:

- Run:
  `/root/fh-mahjong-runs/chongci-branch-cf-kl-distill-20260614-0710`
- Candidate checkpoint:
  `/root/fh-mahjong-runs/chongci-branch-cf-kl-distill-20260614-0710/checkpoints/branch_cf_kl_anchor_gap050_w030_m20_repeat64/epoch_001.pt`
- Reward-gap filter: `>= 0.5`.
- Effective direct pairwise replay rows: `7680`.
- Pairwise policy weight: `0.3`.
- Pairwise margin: `2.0`.
- Pairwise reward-delta weight: `1.0`.
- Pairwise reward-delta margin scale: `0.5`.
- KL anchor: promoted Chongci checkpoint.
- KL weight: `1.0`.

First KL calibration:

| dataset | policy preferred margin rate | policy preferred argmax | policy avoided argmax | Q preferred margin rate |
| --- | ---: | ---: | ---: | ---: |
| train branch-CF r2048 | 59.42% | 23.54% | 12.06% | 52.00% |
| holdout branch-CF r2048 | 58.40% | 23.83% | 11.67% | 51.86% |

First KL smoke:

| policy | screen | seats | mean reward | positive rate | large-loss rate |
| --- | --- | ---: | ---: | ---: | ---: |
| promoted anchor | `534000:2` | 8 | 0.0040 | 50.00% | 50.00% |
| gap050 KL candidate | `534000:2` | 8 | -0.1749 | 50.00% | 50.00% |

Second strict KL pilot:

- Run:
  `/root/fh-mahjong-runs/chongci-branch-cf-kl-distill-strict-20260614-0725`
- Candidate checkpoint:
  `/root/fh-mahjong-runs/chongci-branch-cf-kl-distill-strict-20260614-0725/checkpoints/branch_cf_kl_anchor_gap100_w005_m05_repeat64/epoch_001.pt`
- Reward-gap filter: `>= 1.0`.
- Effective direct pairwise replay rows: `2240`.
- Pairwise policy weight: `0.05`.
- Pairwise margin: `0.5`.
- Pairwise reward-delta weight: `0.0`.
- Pairwise reward-delta margin scale: `0.0`.
- KL anchor: promoted Chongci checkpoint.
- KL weight: `5.0`.

Strict KL calibration:

| dataset | policy preferred margin rate | policy preferred argmax | policy avoided argmax | Q preferred margin rate |
| --- | ---: | ---: | ---: | ---: |
| train branch-CF r2048 | 57.91% | 23.05% | 12.55% | 51.76% |
| holdout branch-CF r2048 | 57.08% | 23.73% | 11.82% | 51.32% |

Strict KL smoke:

| policy | screen | seats | mean reward | positive rate | large-loss rate |
| --- | --- | ---: | ---: | ---: | ---: |
| strict KL candidate | `534000:2` | 8 | -0.0599 | 50.00% | 50.00% |
| strict KL candidate | `534000:4` | 16 | -0.0325 | 50.00% | 50.00% |
| promoted anchor | `534000:4` | 16 | 0.0279 | 50.00% | 50.00% |

Decision:
Rejected before full duplicate-seat gate. KL anchoring and high-confidence row
filtering avoided the catastrophic large-loss smoke from the naive policy
distillation run, but both KL candidates still lost EV versus the promoted
anchor while providing no positive-rate or tail-risk improvement.

Interpretation:
Stop policy-side branch-CF distillation weight/filter tuning in this family.
The branch-CF labels remain useful for diagnostics and critic/proposal analysis,
but forcing them into the deployed policy head does not currently improve live
Chongci play. The next viable direction is not another nearby pairwise-weight
sweep; it should be a separate action-proposal/reranking analysis, more aligned
full-match counterfactual labels, or fresh self-play data that naturally visits
the branch-CF-preferred actions before policy training.

Branch-CF proposal/reranking diagnostics:
Added proposal/rerank diagnostics to `fh-mj-branch-cf-calibration`. The report
now measures whether exact branch-CF preferred actions are reachable in the
anchor policy's legal top-k candidates and whether Q or risk reranking can turn
an avoided top-1 action into the exact preferred branch action.

Run:
`/root/fh-mahjong-runs/chongci-branch-cf-proposal-diagnostics-20260614-0745`

Data:
`/root/fh-mahjong-runs/chongci-branch-cf-holdout-large-20260613-004827/data/anchor-branch-cf-851000-r2048-gap002-b6`

Reports:

- Promoted anchor:
  `/root/fh-mahjong-runs/chongci-branch-cf-proposal-diagnostics-20260614-0745/reports/anchor_holdout_proposal_rerank_r2048.json`
- Branch-CF frozen risk critic:
  `/root/fh-mahjong-runs/chongci-branch-cf-proposal-diagnostics-20260614-0745/reports/riskcritic_holdout_proposal_rerank_r2048.json`
- Strict KL rejected candidate:
  `/root/fh-mahjong-runs/chongci-branch-cf-proposal-diagnostics-20260614-0745/reports/strict_kl_holdout_proposal_rerank_r2048.json`

Offline proposal/rerank result on the 2048-row holdout:

| scorer / reranker | preferred rank median | preferred better than avoided | top-k | preferred in policy top-k | rescues | harms | known reward-gap delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| anchor policy rank | 4.0 | 57.23% | 3 | 43.5% | n/a | n/a | n/a |
| anchor Q rerank | n/a | n/a | 3 | 43.5% | 22 | 36 | 0.179 |
| anchor risk rerank | 5.0 | 53.22% | 3 | 43.5% | 25 | 25 | 0.133 |
| branch-CF risk rerank | 5.0 | 63.18% | 3 | 43.5% | 28 | 23 | 3.954 |
| branch-CF risk rerank | 5.0 | 63.18% | 5 | 60.4% | 29 | 29 | 1.776 |
| branch-CF risk rerank | 5.0 | 63.18% | 10 | 92.2% | 34 | 22 | 1.035 |

Interpretation from offline diagnostics:
The branch-CF risk critic does have a useful exact-label signal when used only
inside the anchor policy's top-k proposals. The best offline screen was top-3
risk reranking: small positive rescue/harm balance and positive known
reward-gap delta.

Live top-k risk-rerank smoke:
Added `--selection-mode policy_topk_risk --policy-top-k N` to
`fh-mj-evaluate-risk-guarded`, then tested the branch-CF risk critic as a live
top-3 reranker around the promoted anchor.

| policy | screen | seats | mean reward | positive rate | large-loss rate | risk-guard choice rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| top-3 risk rerank, unconstrained | `534000:2` | 8 | -1.9032 | 0.00% | 100.00% | 60.52% |
| top-3 risk rerank, strict thresholds | `534000:2` | 8 | -0.6619 | 37.50% | 62.50% | 5.52% |

Live reports:

- Unconstrained:
  `/root/fh-mahjong-runs/chongci-branch-cf-proposal-diagnostics-20260614-0745/reports/top3_risk_rerank_smoke_534000_n2.json`
- Strict:
  `/root/fh-mahjong-runs/chongci-branch-cf-proposal-diagnostics-20260614-0745/reports/top3_risk_rerank_strict_smoke_534000_n2.json`

Decision:
Rejected for serving/evaluation. The exact branch-CF top-k rerank signal does
not transfer to live Chongci action selection. The unconstrained top-3 reranker
intervened far too often and collapsed every smoke seat into a large loss; the
strict version intervened sparsely but still materially regressed EV and tail
risk. Do not continue with nearby top-k risk-rerank threshold sweeps.

Interpretation:
The issue is not just whether a preferred branch action is present in policy
top-k. The short-horizon branch-CF label does not reliably define a safe
full-match intervention rule. The next branch should move away from serving-time
reranking and toward more aligned labels: full-match branch evaluation,
counterfactual labels conditioned on match phase/score pressure, or fresh
self-play data where the improved action sequence is generated organically.

Full-match branch-CF feasibility probe:
Added progress instrumentation to `fh-mj-generate-branch-counterfactuals`:
`--progress-every N` writes JSON branch-start/branch-done lines, branch elapsed
time, and result terminated/truncated/error counts; `--max-elapsed-seconds S`
stops after the current branch call once the wall-clock budget is exhausted.

Run:
`/root/fh-mahjong-runs/chongci-fullmatch-branch-cf-probe-20260614-0755`

Checkpoint:
`/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`

Probe results:

| probe | branch cap | min gap | rows | branch calls | branch results | elapsed | finding |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| tiny full-match truncation probe | 256 | 0.00 | 0 | 193 | 547 | 120.0s | every branch result truncated |
| truncation diagnostic probe | 256 | 0.00 | 0 | 40 | 114 | 35.5s | result_truncated equals branch action count |
| high-cap zero-gap smoke | 4096 | 0.00 | 1 | 1 | 2 | 22.4s | full-match branches can terminate, but first row had zero reward gap |
| high-cap meaningful probe | 4096 | 0.02 | 4 | 11 | 32 | 100.8s | generated usable non-zero-gap full-match labels |

Meaningful shard:
`/root/fh-mahjong-runs/chongci-fullmatch-branch-cf-probe-20260614-0755/data/fullmatch-branch-cf-861050-e1-r4-b2-d4096-gap002`

Meaningful shard manifest:

- rows: 4
- mean reward gap: 0.4305
- max reward gap: 0.6140
- skipped no-label branch calls: 7
- skipped not-enough-discard states: 1
- branch mode: full match (`branch_stop_at_round_end=false`)
- max branch actions: 2
- branch max decisions: 4096

Anchor calibration report:
`/root/fh-mahjong-runs/chongci-fullmatch-branch-cf-probe-20260614-0755/reports/anchor_fullmatch_probe_r4.json`

Tiny calibration result:

| rows | policy preferred rate | policy argmax preferred | Q preferred rate | Q argmax preferred | risk lower-is-better rate |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 75.00% | 50.00% | 25.00% | 0.00% | 50.00% |

Interpretation:
Full-match branch labels are feasible but expensive: roughly 4 useful rows in
101 seconds in this tiny probe. The low-cap probes were invalid because they
only produced truncated branch results. The high-cap labels look more aligned
with the promoted policy head than with the current Q head, which argues against
using the current Q/risk heads as a reranker and favors a larger diagnostic
full-match branch-CF shard before any training change.

Decision:
Do not train on the four-row shard. Next, generate a larger full-match
diagnostic shard with `--branch-max-decisions 4096`, `--max-branch-actions 2`,
`--min-reward-gap 0.02`, and progress logging. Use that shard only for
calibration and failure-slice analysis first. If density and calibration remain
reasonable, then try a very small policy-side auxiliary run with strict duplicate
gate promotion; otherwise pivot to fresh self-play data instead of more branch
label engineering.

Larger full-match diagnostic shard:
Generated the first larger diagnostic shard from the same promoted anchor with
the high-cap full-match settings.

Run:
`/root/fh-mahjong-runs/chongci-fullmatch-branch-cf-diagnostic-20260614-0753`

Data:
`/root/fh-mahjong-runs/chongci-fullmatch-branch-cf-diagnostic-20260614-0753/data/fullmatch-branch-cf-861100-e4-r32-b2-d4096-gap002`

Report:
`/root/fh-mahjong-runs/chongci-fullmatch-branch-cf-diagnostic-20260614-0753/reports/anchor_fullmatch_diagnostic_r32.json`

Generation summary:

| rows | episodes | branch calls | branch results | skipped no-label | skipped not-enough-discards | elapsed | mean gap | max gap |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 32 | 4 | 59 | 165 | 27 | 15 | 308.7s | 0.2153 | 0.5560 |

Anchor calibration:

| rows | policy preferred | policy argmax preferred | Q preferred | Q argmax preferred | risk lower-is-better |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 32 | 65.62% | 53.12% | 53.12% | 9.38% | 62.50% |

Policy proposal coverage:

| metric | value |
| --- | ---: |
| preferred policy rank median | 1.0 |
| avoided policy rank median | 5.0 |
| preferred better than avoided by policy | 65.62% |
| preferred in policy top-3 | 62.50% |
| avoided in policy top-3 | 28.12% |
| reward-gap-weighted preferred in policy top-3 | 71.03% |

Interpretation:
The first 32-row full-match shard supports the idea that the promoted policy is
already partially aligned with full-match branch labels, especially in top-1 and
top-3 proposal rank. The Q head is weaker as an action selector despite a small
majority preferred-rate, because Q argmax hits the preferred action on only
9.38% of rows. This is not enough data for a training claim, but it is enough to
justify scaling the full-match diagnostic shard before another policy update.

Next decision:
Scale the same full-match label source to a larger diagnostic shard before
training. The immediate target is a 128-row shard using the same settings. Use
it for calibration/failure slices first; only train if policy top-k coverage and
reward-gap density remain stable.

Full-match 128-row diagnostic and low-dose auxiliary reject:

128-row diagnostic run:
`/root/fh-mahjong-runs/chongci-fullmatch-branch-cf-diagnostic-128-20260614-0800`

Data:
`/root/fh-mahjong-runs/chongci-fullmatch-branch-cf-diagnostic-128-20260614-0800/data/fullmatch-branch-cf-861500-e12-r128-b2-d4096-gap002`

Reports:

- Anchor calibration:
  `/root/fh-mahjong-runs/chongci-fullmatch-branch-cf-diagnostic-128-20260614-0800/reports/anchor_fullmatch_diagnostic_r128.json`
- Failure slices:
  `/root/fh-mahjong-runs/chongci-fullmatch-branch-cf-diagnostic-128-20260614-0800/reports/anchor_fullmatch_diagnostic_r128_failures.json`

Generation summary:

| rows | episodes | branch calls | branch results | skipped no-label | skipped not-enough-discards | elapsed | mean gap | max gap |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | 12 | 226 | 630 | 98 | 41 | 1062.3s | 0.3329 | 1.4730 |

Reward-gap density:

| gap filter | rows |
| ---: | ---: |
| >= 0.20 | 76 |
| >= 0.50 | 33 |
| >= 0.75 | 19 |
| >= 1.00 | 9 |

Anchor calibration:

| rows | policy preferred | policy argmax preferred | policy argmax avoided | Q preferred | Q argmax preferred | risk lower-is-better |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | 38.28% | 25.78% | 45.31% | 52.34% | 11.72% | 51.56% |

Policy proposal coverage:

| top-k | preferred in policy top-k | avoided in policy top-k | reward-gap-weighted preferred |
| ---: | ---: | ---: | ---: |
| 3 | 40.62% | 58.59% | 39.30% |
| 5 | 57.81% | 70.31% | 51.36% |
| 10 | 86.72% | 96.88% | 90.75% |
| 20 | 100.00% | 100.00% | 100.00% |

Failure slices:

| segment | rows | rate | mean reward gap | median reward gap |
| --- | ---: | ---: | ---: | ---: |
| policy misrank | 79 | 61.72% | 0.3513 | 0.2310 |
| high-gap policy misrank | 21 | 16.41% | 0.8309 | 0.7850 |
| Q misrank | 61 | 47.66% | 0.3162 | 0.2200 |
| high-gap Q misrank | 13 | 10.16% | 0.9053 | 0.9730 |

Interpretation:
The 128-row shard reversed the optimistic 32-row signal. The promoted policy is
often confidently choosing the full-match avoided discard, including high-gap
rows. This makes full-match branch labels a real diagnostic target, but not a
safe direct policy overwrite target without strong anchoring.

Low-dose full-match KL auxiliary:

Run:
`/root/fh-mahjong-runs/chongci-fullmatch-branch-cf-kl-lowdose-20260614-0820`

Training:

- Base data:
  `/root/fh-mahjong-runs/chongci-broader-mixed-selfplay-20260607-032601/data/anchor-fresh-balanced-tail2-760000-n200-npz`
- Pairwise data:
  `/root/fh-mahjong-runs/chongci-fullmatch-branch-cf-diagnostic-128-20260614-0800/data/fullmatch-branch-cf-861500-e12-r128-b2-d4096-gap002`
- Pairwise row filter: reward gap >= 0.5, 33 source rows.
- Pairwise replay multiplier: 64, 2112 effective rows.
- Init/KL anchor:
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
- LR: `1e-5`
- BC weight: `0.05`
- Pairwise policy weight: `0.05`
- Pairwise policy margin: `0.5`
- Pairwise Q weight: `0.05`
- Pairwise Q margin: `0.1`
- KL weight: `5.0`
- MLflow run: `20df942b1a7d4919aa33e1cc5d049927`

Candidate:
`/root/fh-mahjong-runs/chongci-fullmatch-branch-cf-kl-lowdose-20260614-0820/checkpoints/fullmatch_gap050_kl_lowdose/epoch_001.pt`

Calibration on the same 128-row full-match shard:

| policy | policy preferred | policy argmax preferred | policy argmax avoided | Q preferred | Q argmax preferred |
| --- | ---: | ---: | ---: | ---: | ---: |
| promoted anchor | 38.28% | 25.78% | 45.31% | 52.34% | 11.72% |
| low-dose candidate | 41.41% | 25.78% | 42.97% | 62.50% | 12.50% |

Smoke evaluation:

| policy | screen | seats | mean reward | reward sum | positive rate | large-loss rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| promoted anchor | `534000:2` | 8 | 0.00 | 0.0320 | 50.00% | 50.00% |
| low-dose candidate | `534000:2` | 8 | -0.16 | -1.3180 | 50.00% | 50.00% |

Decision:
Rejected before a full duplicate gate. The low-dose full-match auxiliary
improves offline Q preference and barely improves policy preference, but it
still loses live smoke EV with no positive-rate or large-loss improvement.

Interpretation:
Stop direct policy-side branch-label distillation again, even with full-match
labels, unless a new mechanism changes how labels enter training. The next
aligned path is fresh self-play data that lets alternative decisions unfold
organically, not another pairwise-weight/threshold sweep.

Sampled-anchor self-play pivot:
Added checkpoint-temperature sampling for mixed self-play generation while
keeping default serving/evaluation greedy. This allows controlled exploration
from the promoted policy without deploying stochastic actions.

Run started:
`/root/fh-mahjong-runs/chongci-sampled-anchor-selfplay-20260614-0835`

Data target:
`/root/fh-mahjong-runs/chongci-sampled-anchor-selfplay-20260614-0835/data/anchor-sampled-temp025-862000-n100-npz`

Generation settings:

- seats 0-3: promoted anchor checkpoint
- checkpoint temperature: `0.25`
- episodes: `100`
- start seed: `862000`
- match mode: Chongci
- chunk size: `10`

Purpose:
Use this as the next candidate data source for reward learning if it completes
with plausible returns and legal-action validation. The first screen after
generation should compare its outcome distribution against greedy-anchor
self-play before training from it.

Sampled-anchor self-play result:

Completed:
`/root/fh-mahjong-runs/chongci-sampled-anchor-selfplay-20260614-0835/data/anchor-sampled-temp025-862000-n100-npz`

Generation summary:

| episodes | transitions | elapsed | temperature | seats |
| ---: | ---: | ---: | ---: | --- |
| 100 | 204538 | 665.6s | 0.25 | all promoted anchor |

Outcome comparison:

| dataset | episode-seats | positive rate | large-loss rate <= -0.5 | min return | max return |
| --- | ---: | ---: | ---: | ---: | ---: |
| sampled anchor temp 0.25 | 400 | 47.25% | 29.75% | -2.152 | 3.527 |
| greedy anchor first 400 seats | 400 | 48.00% | 30.00% | n/a | n/a |
| broader mixed first 400 seats | 400 | 46.00% | 34.50% | n/a | n/a |

Low-dose sampled-IQL run:
`/root/fh-mahjong-runs/chongci-sampled-anchor-iql-20260614-0850`

Medium-dose sampled-IQL run:
`/root/fh-mahjong-runs/chongci-sampled-anchor-iql-medium-20260614-0900`

Training source for both:

- Base:
  `/root/fh-mahjong-runs/chongci-broader-mixed-selfplay-20260607-032601/data/anchor-fresh-balanced-tail2-760000-n200-npz`
- Fresh sampled:
  `/root/fh-mahjong-runs/chongci-sampled-anchor-selfplay-20260614-0835/data/anchor-sampled-temp025-862000-n100-npz`
- Init:
  `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`

| run | LR | BC | KL | sampled-data argmax divergence vs anchor | full-match-CF argmax divergence | smoke reward sum | decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| low-dose | 1e-5 | 0.05 | 2.0 | 0.21% | 0.00% | 0.0320 | no-op |
| medium-dose | 2e-5 | 0.03 | 1.0 | 0.38% | 0.00% | 0.0320 | no-op |

Both matched the promoted anchor exactly on the `534000:2` smoke report:
8 seats, reward sum `0.0320`, positive rate `50.00%`, large-loss rate `50.00%`.

Interpretation:
Temperature `0.25` was too close to greedy. It generated valid data, but the
dataset still agrees with the greedy anchor on roughly 99% of sampled decisions,
so conservative IQL barely changed the deployed policy. Do not widen-gate these
checkpoints; they are no-op diagnostics.

Next probe:
Started a smaller higher-exploration sampled self-play run:
`/root/fh-mahjong-runs/chongci-sampled-anchor-selfplay-temp075-20260614-0910`

Target:
`/root/fh-mahjong-runs/chongci-sampled-anchor-selfplay-temp075-20260614-0910/data/anchor-sampled-temp075-863000-n50-npz`

Settings:

- episodes: `50`
- start seed: `863000`
- checkpoint temperature: `0.75`
- all seats: promoted anchor checkpoint

Screen before training:
Compare return distribution and greedy-anchor action agreement. Only train from
this data if it provides materially more action diversity without clearly
destroying the outcome distribution.

Temp 0.75 sampled-anchor probe:

Completed:
`/root/fh-mahjong-runs/chongci-sampled-anchor-selfplay-temp075-20260614-0910/data/anchor-sampled-temp075-863000-n50-npz`

Generation summary:

| episodes | transitions | elapsed | temperature | seats |
| ---: | ---: | ---: | ---: | --- |
| 50 | 103178 | 343.1s | 0.75 | all promoted anchor |

Distribution and diversity:

| dataset | episode-seats | positive rate | large-loss rate <= -0.5 | greedy agreement first 20k | median return |
| --- | ---: | ---: | ---: | ---: | ---: |
| temp 0.25 | 400 | 47.25% | 29.75% | 99.13% | -0.0400 |
| temp 0.75 | 200 | 43.50% | 32.00% | 97.90% | -0.1115 |

Temp 0.75 IQL:

- Run:
  `/root/fh-mahjong-runs/chongci-sampled-anchor-temp075-iql-20260614-0920`
- Candidate:
  `/root/fh-mahjong-runs/chongci-sampled-anchor-temp075-iql-20260614-0920/checkpoints/sampled_anchor_temp075_iql_medium/epoch_001.pt`
- MLflow run: `ccba8208a6694c4d84f00679d02bba30`
- Argmax divergence: 0.33% on temp 0.75 sampled data, 0.78% on full-match CF.
- Smoke `534000:2`: reward sum `-0.2260` vs promoted anchor `0.0320`, same positive and large-loss rates.

Temp 0.75 AWBC:

- Run:
  `/root/fh-mahjong-runs/chongci-sampled-anchor-temp075-awbc-20260614-0930`
- Candidate:
  `/root/fh-mahjong-runs/chongci-sampled-anchor-temp075-awbc-20260614-0930/checkpoints/sampled_anchor_temp075_awbc/epoch_001.pt`
- MLflow run: `3bde7df655b34e739916f2cd54a6be77`
- Argmax divergence: 0.24% on temp 0.75 sampled data, 0.00% on full-match CF.
- Smoke `534000:2`: reward sum `-0.2810` vs promoted anchor `0.0320`, same positive and large-loss rates.

Decision:
Reject both temp 0.75 candidates before wider gates. Temp 0.75 increased action
diversity only modestly and worsened the sampled self-play outcome distribution.
IQL and AWBC still mostly preserved the promoted policy, and the few changed
actions hurt smoke EV.

Interpretation:
Simple global temperature sampling is not enough. Temp 0.25 is too greedy; temp
0.75 is still mostly greedy but already degrades outcomes. The next data path
should use a more targeted exploration mechanism, for example per-seat
sampled-vs-greedy mixing, top-k-only sampling, or sampling only at high-value
uncertain decisions. Do not spend wider gates on these no-op sampled-data
checkpoints.

### Experiment: Anchor Top-K Sampled Self-Play Probe

Run:
`/root/fh-mahjong-runs/chongci-sampled-anchor-topk3-temp100-20260614-0945`

Question:
Can checkpoint self-play exploration be made more useful by sampling only among
the promoted anchor's top legal actions, instead of globally sampling over all
legal actions with a higher temperature?

Implementation:

- Added checkpoint-policy sampling controls:
  - `CheckpointPolicy.from_checkpoint(..., sample_temperature=T, sample_top_k=K, seed=S)`
  - `fh-mj-generate-selfplay --checkpoint-temperature T --checkpoint-top-k K`
- Defaults remain greedy serving/evaluation: `sample_temperature=0.0`,
  `sample_top_k=0`.
- Self-play manifests now record both `checkpoint_temperature` and
  `checkpoint_top_k`.

Data:

`/root/fh-mahjong-runs/chongci-sampled-anchor-topk3-temp100-20260614-0945/data/anchor-sampled-topk3-temp100-864000-n50-npz`

Generation summary:

| episodes | transitions | elapsed | temperature | top-k | seats |
| ---: | ---: | ---: | ---: | ---: | --- |
| 50 | 100831 | 350.0s | 1.0 | 3 | all promoted anchor |

Distribution and diversity:

| dataset | episode-seats | positive rate | large-loss rate <= -0.5 | greedy agreement first 20k | median return |
| --- | ---: | ---: | ---: | ---: | ---: |
| temp 0.25 | 400 | 47.25% | 29.75% | 99.13% | -0.0400 |
| temp 0.75 | 200 | 43.50% | 32.00% | 97.90% | -0.1115 |
| top-k 3 temp 1.0 | 200 | 48.00% | 32.00% | 97.25% | -0.0765 |

The top-k dataset produced slightly more action diversity than temp 0.75 while
keeping a better sampled outcome distribution. It is still mostly greedy, but it
is the best of the simple sampled-anchor probes so far.

Training:

- Run:
  `/root/fh-mahjong-runs/chongci-sampled-anchor-topk3-iql-20260614-0955`
- Candidate:
  `/root/fh-mahjong-runs/chongci-sampled-anchor-topk3-iql-20260614-0955/checkpoints/sampled_anchor_topk3_iql_medium/epoch_001.pt`
- MLflow run: `5a48986343744644a0bb1268c96cd1e7`
- Recipe matched the temp 0.75 medium IQL comparison:
  - base data:
    `/root/fh-mahjong-runs/chongci-broader-mixed-selfplay-20260607-032601/data/anchor-fresh-balanced-tail2-760000-n200-npz`
  - top-k data:
    `/root/fh-mahjong-runs/chongci-sampled-anchor-topk3-temp100-20260614-0945/data/anchor-sampled-topk3-temp100-864000-n50-npz`
  - init/KL anchor:
    `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`
  - epoch `1`, batch `4096`, learning rate `2e-5`, BC weight `0.03`,
    policy KL weight `1.0`, max transitions `200000` per dataset.

Offline drift:

| comparison set | checked rows | argmax divergence vs anchor |
| --- | ---: | ---: |
| top-k sampled data | 20000 | 0.27% |
| full-match branch-CF 128 | 128 | 0.78% |

Evaluation:

Use `--max-steps-per-episode 0` for Chongci duplicate smoke gates. Without this,
the Python evaluator default can truncate all seats before match end and produce
zero-reward `match_truncated` reports for both anchor and candidate.

Corrected smoke window: `534000:2`, duplicate seats, Chongci max hands `50`.

| checkpoint | reward sum | mean reward | positive rate | large-loss rate | outcomes |
| --- | ---: | ---: | ---: | ---: | --- |
| promoted anchor | 0.0320 | 0.0040 | 50.00% | 50.00% | 8 match_end |
| top-k IQL candidate | -0.3140 | -0.0392 | 50.00% | 50.00% | 8 match_end |

Decision:
Reject the top-k IQL candidate before wider gates. Keep the top-k sampling
tooling and dataset as useful exploration infrastructure, but do not promote
this checkpoint.

Interpretation:
Top-k sampling is a better data-generation primitive than broad temperature
sampling, but a simple one-epoch IQL update still does not improve the anchor.
The policy barely moves offline, and the small live differences hurt expected
value on the smoke gate. The next experiment should either generate more top-k
data with a direct sampled-vs-greedy paired comparison, or train with a clearer
objective on the sampled divergences instead of another broad IQL pass.

### Experiment: Exact Sampled-Vs-Greedy Branch Counterfactuals

Run:

`/root/fh-mahjong-runs/chongci-sampled-greedy-branch-cf-topk3-large-20260614-1545`

Question:

Can we avoid broad sampled-data policy drift by labeling only the exact same-state
decisions where top-k sampling chooses a different action than the greedy anchor?

Implementation:

- Added `fh-mj-generate-sampled-branch-counterfactuals`.
- The generator loads a checkpoint, computes both greedy and sampled top-k
  actions from the same visible observation, and calls Go `evaluate_branches()`
  only when those two actions differ.
- It writes the same pairwise NPZ schema consumed by `fh-mj-train-iql
  --pairwise-data`, with extra diagnostics:
  `branch_greedy_action_ids`, `branch_sampled_action_ids`, and
  `branch_sampled_ranks`.
- Existing broad branch-CF generation remains discard-only by default. This new
  path can label all legal action families because sampled-vs-greedy differences
  include discard, chii, pon, kan, pass, and haitei/win decisions.

Smoke shard:

`/root/fh-mahjong-runs/chongci-sampled-greedy-branch-cf-topk3-20260614-1540/data/topk3-sampled-vs-greedy-865000-r128`

| rows | elapsed | branch errors | mean gap | max gap | sampled preferred | greedy preferred |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | 34.5s | 0 | 0.0540 | 1.2300 | 92 | 36 |

Anchor calibration on the 128-row smoke shard:

| scorer | preferred rate | reward-gap weighted preferred rate |
| --- | ---: | ---: |
| policy logits | 28.91% | 66.23% |
| Q values | 50.78% | 65.33% |

Large shard:

`/root/fh-mahjong-runs/chongci-sampled-greedy-branch-cf-topk3-large-20260614-1545/data/topk3-sampled-vs-greedy-865100-r2048`

| rows | elapsed | branch errors | mean gap | max gap | sampled preferred | greedy preferred |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2048 | 394.3s | 0 | 0.0457 | 1.3240 | 1618 | 430 |

Reward-gap distribution:

| filter | rows | sampled preferred rate | mean gap |
| --- | ---: | ---: | ---: |
| all rows | 2048 | 79.00% | 0.0457 |
| gap >= 0.01 | 587 | 49.40% | 0.1580 |
| gap >= 0.05 | 387 | 50.65% | 0.2227 |
| gap >= 0.10 | 266 | 48.50% | 0.2917 |
| gap >= 0.50 | 30 | 36.67% | 0.7921 |

Important detail:
Most rows have zero or near-zero branch reward gap. Because the branch result
order is greedy then sampled, zero-gap rows can make the sampled action appear
preferred without meaningful evidence. Training must filter these out with
`--pairwise-data-min-reward-gap`; do not train on all rows.

Anchor calibration on the 2048-row shard:

| scorer | all preferred | weighted preferred | gap 0.05-0.20 | gap 0.20-0.50 | gap 0.50+ |
| --- | ---: | ---: | ---: | ---: | ---: |
| policy logits | 21.04% | 51.38% | 48.86% | 47.83% | 63.33% |
| Q values | 51.22% | 46.53% | 51.60% | 44.93% | 43.33% |

Training candidate A:

- Run:
  `/root/fh-mahjong-runs/chongci-sampled-greedy-branch-cf-iql-20260614-1555`
- Candidate:
  `/root/fh-mahjong-runs/chongci-sampled-greedy-branch-cf-iql-20260614-1555/checkpoints/topk3_sampled_greedy_pairwise_iql_gap005/epoch_001.pt`
- MLflow run: `566cb373550c4639a134d8816fcbb984`
- Data:
  - base mixed replay:
    `/root/fh-mahjong-runs/chongci-broader-mixed-selfplay-20260607-032601/data/anchor-fresh-balanced-tail2-760000-n200-npz`
  - top-k sampled replay:
    `/root/fh-mahjong-runs/chongci-sampled-anchor-topk3-temp100-20260614-0945/data/anchor-sampled-topk3-temp100-864000-n50-npz`
  - pairwise data:
    `topk3-sampled-vs-greedy-865100-r2048`
- Pairwise filter: `--pairwise-data-min-reward-gap 0.05`
- Effective auxiliary rows: `24768`
- Pairwise batches were active: logged `pairwise_count` around 300 rows/batch.

Candidate A calibration:

| scorer | all preferred | weighted preferred | gap 0.05-0.20 | gap 0.20-0.50 | gap 0.50+ |
| --- | ---: | ---: | ---: | ---: | ---: |
| policy logits | 25.93% | 67.44% | 65.30% | 71.74% | 66.67% |
| Q values | 54.74% | 67.83% | 67.58% | 68.84% | 70.00% |

Candidate A smoke, corrected `534000:2` duplicate-seat gate with
`--max-steps-per-episode 0`:

| checkpoint | reward sum | mean reward | positive rate | large-loss rate | outcomes |
| --- | ---: | ---: | ---: | ---: | --- |
| promoted anchor | 0.0320 | 0.0040 | 50.00% | 50.00% | 8 match_end |
| candidate A | -1.4470 | -0.1809 | 50.00% | 50.00% | 8 match_end |

Decision:
Reject candidate A before wider gates. It fit the branch labels but damaged
live expected value.

Training candidate B:

- Run:
  `/root/fh-mahjong-runs/chongci-sampled-greedy-branch-cf-iql-conservative-20260614-1605`
- Candidate:
  `/root/fh-mahjong-runs/chongci-sampled-greedy-branch-cf-iql-conservative-20260614-1605/checkpoints/topk3_sampled_greedy_pairwise_iql_gap010_conservative/epoch_001.pt`
- MLflow run: `2bac1bb5c6984982a8c253ff24e8f66f`
- Changes from candidate A:
  - no broad top-k sampled replay
  - `--pairwise-data-min-reward-gap 0.10`
  - learning rate `5e-6`
  - pairwise policy weight `0.005`
  - pairwise policy margin `0.02`
  - policy KL weight `5.0`
- Effective auxiliary rows: `17024`
- Pairwise batches were active.

Candidate B calibration:

| scorer | all preferred | weighted preferred | gap 0.05-0.20 | gap 0.20-0.50 | gap 0.50+ |
| --- | ---: | ---: | ---: | ---: | ---: |
| policy logits | 22.31% | 53.32% | 51.60% | 50.00% | 63.33% |
| Q values | 52.05% | 54.53% | 54.34% | 56.52% | 50.00% |

Candidate B smoke, corrected `534000:2` duplicate-seat gate:

| checkpoint | reward sum | mean reward | positive rate | large-loss rate | outcomes |
| --- | ---: | ---: | ---: | ---: | --- |
| promoted anchor | 0.0320 | 0.0040 | 50.00% | 50.00% | 8 match_end |
| candidate B | -0.3150 | -0.0394 | 50.00% | 50.00% | 8 match_end |

Decision:
Reject candidate B before wider gates. It is safer than candidate A but still
loses the smoke gate.

Interpretation:
The exact sampled-vs-greedy branch-CF generator is successful and should be kept.
It creates dense same-state labels quickly, and those labels produce active
pairwise training. However, direct policy distillation from short-horizon
branch labels is still not sufficient for live Chongci improvement. The failure
mode is now clear: calibration on branch labels improves, but the duplicate-seat
EV gate gets worse.

Stop rule:
Do not run another nearby pairwise-IQL coefficient sweep on this same 2048-row
short-horizon shard. The next useful step needs a new ingredient:

- branch to match end for a smaller high-confidence sampled-vs-greedy shard,
- learn a Q/reranker diagnostic from branch labels without changing the served
  policy head, then validate it with a guarded candidate screen,
- or use these exact branch labels to choose which top-k sampled states deserve
  longer branch evaluation instead of training directly on all short-horizon
  labels.

### Experiment: Chongci Global EV Predictor V1

Run:
`/root/fh-mahjong-runs/chongci-global-ev-v1-20260614-172311`

Question:
Can a separate visible-state global expected-value predictor learn final
Chongci match value well enough to become the missing Mortal/Suphx-style global
reward signal, instead of continuing short-horizon branch-CF policy sweeps?

Data:

- `/root/fh-mahjong-runs/chongci-broader-mixed-selfplay-20260607-032601/data/anchor-fresh-balanced-tail2-760000-n200-npz`
- `/root/fh-mahjong-runs/chongci-sampled-anchor-topk3-temp100-20260614-0945/data/anchor-sampled-topk3-temp100-864000-n50-npz`
- Capped at `--max-transitions 100000` per source, producing `200000`
  total transitions.
- Target is final terminal reward for the acting seat:
  `terminal_rewards[row, seat]`.

Training:

CLI:

```bash
fh-mj-train-global-ev \
  --data /root/fh-mahjong-runs/chongci-broader-mixed-selfplay-20260607-032601/data/anchor-fresh-balanced-tail2-760000-n200-npz \
  --data /root/fh-mahjong-runs/chongci-sampled-anchor-topk3-temp100-20260614-0945/data/anchor-sampled-topk3-temp100-864000-n50-npz \
  --checkpoint-dir /root/fh-mahjong-runs/chongci-global-ev-v1-20260614-172311/checkpoints/global_ev_v1 \
  --report-output /root/fh-mahjong-runs/chongci-global-ev-v1-20260614-172311/reports/global_ev_v1.json \
  --epochs 3 \
  --batch-size 2048 \
  --lr 1e-4 \
  --weight-decay 1e-4 \
  --max-transitions 100000 \
  --device cuda \
  --model-channel-attention \
  --mlflow \
  --mlflow-tracking-uri sqlite:////root/fh-mahjong-branch-cf/ai/mlflow.db \
  --mlflow-experiment chongci-rl \
  --mlflow-run-name global_ev_v1
```

MLflow run:
`5290d322e81b49818febaace6365a303`

Evaluation:
Episode-mod validation split, `validation_mod=10`, no duplicate-seat serving
evaluation because this checkpoint is a value model, not a policy.

Result:

| metric | global EV model | train-mean baseline |
| --- | ---: | ---: |
| validation transitions | 19,661 | 19,661 |
| MAE | 0.4893 | 0.7676 |
| RMSE | 0.6775 | 1.0096 |
| correlation | 0.7566 | 0.0000 |
| bias | -0.1231 | -0.0018 |

Checkpoint:
`/root/fh-mahjong-runs/chongci-global-ev-v1-20260614-172311/checkpoints/global_ev_v1/epoch_003.pt`

Decision:
Successful calibration probe. Do not promote this as a policy, but keep the
global EV path and scale it to the full mixed/top-k dataset.

Interpretation:
This is the first recent branch after the sampled branch-CF rejections that
shows a strong transferable learning signal without changing action selection.
It matches the Mortal/Suphx lesson: learn a global outcome predictor from
visible state first, then use it to normalize rewards, select valuable branch
states, or rank candidate continuations. The negative bias means it should not
yet be used as an absolute serving-time score; first use it for calibration,
diagnostics, and relative comparisons on held-out data.

### Experiment: Chongci Global EV Full Scale And First TD Policy Probes

Runs:

- Full global EV:
  `/root/fh-mahjong-runs/chongci-global-ev-full-20260614-172415`
- Policy-architecture global EV:
  `/root/fh-mahjong-runs/chongci-global-ev-policyarch-20260614-172734`
- Unconstrained `global_ev_td` IQL probe:
  `/root/fh-mahjong-runs/chongci-global-ev-td-iql-probe-20260614-172802`
- KL-constrained `global_ev_td` IQL probe:
  `/root/fh-mahjong-runs/chongci-global-ev-td-iql-kl-probe-20260614-173036`

Question:
After the standalone global EV predictor proves learnable, can it be used
directly as a Bellman target for IQL policy improvement?

Implementation:
Added explicit IQL support for:

```text
--target-mode global_ev_td --global-ev-checkpoint PATH
```

The target is:

```text
Q_target = immediate_reward + gamma * frozen_global_ev(next_observation)
```

This is intentionally separate from `mc` and learned-`td` targets so runs are
auditable and cannot accidentally change reward semantics.

Full global EV training:

- Data: all `510713` transitions from the broader mixed self-play and top-k
  sampled datasets.
- Model: no-pooling residual CNN with channel attention.
- Epochs: `5`
- MLflow run: `05f31e499f044b8995ebc2456972664b`
- Checkpoint:
  `/root/fh-mahjong-runs/chongci-global-ev-full-20260614-172415/checkpoints/global_ev_full/epoch_005.pt`

Full global EV result:

| metric | global EV model | train-mean baseline |
| --- | ---: | ---: |
| validation transitions | 50,909 | 50,909 |
| MAE | 0.5449 | 0.8052 |
| RMSE | 0.7102 | 1.0367 |
| correlation | 0.7367 | 0.0000 |
| bias | -0.0483 | -0.0036 |

Policy-architecture global EV:

- Data: `200000` capped transitions, same sources as V1.
- Model: default policy-compatible no-attention architecture.
- Epochs: `3`
- MLflow run: `278c835f141b4f9cbf2ba97ec2bdf733`
- Checkpoint:
  `/root/fh-mahjong-runs/chongci-global-ev-policyarch-20260614-172734/checkpoints/global_ev_policyarch/epoch_003.pt`

Policy-architecture EV result:

| metric | global EV model | train-mean baseline |
| --- | ---: | ---: |
| validation transitions | 19,661 | 19,661 |
| MAE | 0.5024 | 0.7676 |
| RMSE | 0.6787 | 1.0096 |
| correlation | 0.7474 | 0.0000 |
| bias | -0.0511 | -0.0018 |

Policy probes:

Both probes warm-started from the promoted Chongci anchor:
`/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`

Both used capped mixed/top-k data with `--max-transitions 100000`, one epoch,
and the policy-compatible global EV checkpoint above.

Smoke evaluation:

- Window: `534000:2`
- Duplicate seats: yes
- Seats: `8`
- Mode: `chongci`
- `--max-steps-per-episode 0`

| checkpoint | reward sum | mean reward | positive rate | large-loss rate | large-loss count |
| --- | ---: | ---: | ---: | ---: | ---: |
| promoted anchor | 0.0320 | 0.0040 | 50.00% | 25.00% | 2 |
| global EV TD IQL | -1.2830 | -0.1604 | 50.00% | 50.00% | 4 |
| global EV TD IQL + anchor KL | -0.6650 | -0.0831 | 50.00% | 37.50% | 3 |

Decision:
Accept the global EV predictor infrastructure. Reject both direct
`global_ev_td` policy probes before any wider gate.

Interpretation:
The visible-state global EV model is learning a real outcome signal. The policy
update failure means the current direct Bellman-target recipe still changes
the action distribution in harmful states, even with anchor KL. This is not a
reason to discard global EV; it means the next use should be more conservative:

- use global EV for diagnostics and branch/state selection first,
- compare global EV deltas on candidate-vs-anchor first divergences,
- use it as an auxiliary value calibration target before using it as the main
  Q target,
- avoid more nearby `global_ev_td` policy coefficient sweeps until divergence
  analysis shows which action families or score-pressure states caused the
  smoke loss.

### Experiment: Global EV First-Divergence Diagnostics And Action EV Probe

Runs:

- KL candidate paired trace:
  `/root/fh-mahjong-runs/chongci-global-ev-td-iql-kl-probe-20260614-173036/reports/anchor_vs_candidate_tensor_trace_534000_n2.json`
- State global EV diagnostic:
  `/root/fh-mahjong-runs/chongci-global-ev-td-iql-kl-probe-20260614-173036/reports/global_ev_first_divergence_diagnostics_534000_n2.json`
- Action-conditioned global EV:
  `/root/fh-mahjong-runs/chongci-action-global-ev-policyarch-20260614-174339`
- Action-conditioned global EV diagnostic:
  `/root/fh-mahjong-runs/chongci-global-ev-td-iql-kl-probe-20260614-173036/reports/action_global_ev_first_divergence_diagnostics_534000_n2.json`

Question:
Can the learned global EV signal explain why the KL-constrained
`global_ev_td` policy probe lost the smoke gate?

Implementation:

- Added `fh-mj-global-ev-diagnostics`.
- It reads tensor-bearing paired-trace reports produced with
  `--include-observation-arrays`.
- State mode scores `EV(state)` for anchor and candidate first-divergence
  observations.
- Action-conditioned mode scores `EV(state, action_id)` for the two first
  divergence actions.
- Added `--action-conditioned` to `fh-mj-train-global-ev`, implemented
  `ActionGlobalEVNet`, and added tests for model shape, training, and
  divergence diagnostics.

Paired trace:

- Left: promoted anchor
- Right: KL-constrained `global_ev_td` probe
- Window: `534000:2`
- Seats: `0 1 2 3`
- Pairs: `8`
- Divergence rate: `100%`
- Candidate better rate: `0%`
- Mean reward delta: `-0.0871`

State global EV diagnostic:

| metric | value |
| --- | ---: |
| scoreable divergences | 8 |
| MAE | 0.0871 |
| correlation | 0.0000 |
| sign accuracy | 0.00% |
| harmful recall | 0.00% |

Interpretation:
This result is expected and important. At first divergence, the anchor and
candidate are in the same visible state. A state-only `EV(state)` model gives
the same prediction to both actions, so it cannot rank a discard choice. It is
still useful for state valuation and calibration, but not for same-state action
selection.

Action-conditioned EV training:

CLI used:

```bash
fh-mj-train-global-ev \
  --action-conditioned \
  --data /root/fh-mahjong-runs/chongci-broader-mixed-selfplay-20260607-032601/data/anchor-fresh-balanced-tail2-760000-n200-npz \
  --data /root/fh-mahjong-runs/chongci-sampled-anchor-topk3-temp100-20260614-0945/data/anchor-sampled-topk3-temp100-864000-n50-npz \
  --checkpoint-dir /root/fh-mahjong-runs/chongci-action-global-ev-policyarch-20260614-174339/checkpoints/action_global_ev_policyarch \
  --report-output /root/fh-mahjong-runs/chongci-action-global-ev-policyarch-20260614-174339/reports/action_global_ev_policyarch.json \
  --epochs 3 \
  --batch-size 4096 \
  --lr 1e-4 \
  --weight-decay 1e-4 \
  --max-transitions 100000 \
  --device cuda
```

MLflow run:
`3fa59115f82b41548a7ec972aa21f17f`

Action-conditioned EV result:

| metric | action EV model | train-mean baseline |
| --- | ---: | ---: |
| validation transitions | 19,661 | 19,661 |
| MAE | 0.5045 | 0.7676 |
| RMSE | 0.6843 | 1.0096 |
| correlation | 0.7429 | 0.0000 |
| bias | -0.0632 | -0.0018 |

Action-conditioned first-divergence diagnostic:

| metric | value |
| --- | ---: |
| scoreable divergences | 8 |
| MAE | 0.0965 |
| correlation | 0.3092 |
| sign accuracy | 66.67% |
| harmful divergences | 3 |
| harmful predicted harmful rate | 66.67% |
| family pair | discard -> discard |

Action-conditioned EV guard preflight:

Candidate action is allowed when:

```text
EV(state, candidate_action) - EV(state, anchor_action) >= margin
```

| margin | allowed | harmful block rate | actual allowed delta sum |
| ---: | ---: | ---: | ---: |
| 0.0000 | 4 / 8 | 66.67% | -0.2380 |
| -0.0200 | 5 / 8 | 66.67% | -0.2380 |
| -0.0500 | 8 / 8 | 0.00% | -0.6970 |

Worst false positive:

- Seed `534000`, seat `1`, decision `433`
- Anchor action: `discard 1z`
- Candidate action: `discard 3s`
- Actual delta: `-0.2380`
- Predicted delta: `+0.0383`
- Context: rank score `0.3333`, overall shanten `0.4444`,
  ukeire `1.0`, large-loss margin `0.4610`, opponent large-loss pressure
  `0.6270`

Decision:
Keep action-conditioned EV as a diagnostic and candidate guard signal. Do not
promote any policy from this branch yet.

Guard decision:
Do not run live guarded duplicate-seat evaluation yet. The strict action-EV
guard blocks two of three harmful first divergences, but it still allows one
harmful candidate discard with actual delta `-0.2380`. The loose margin
`-0.05` allows all first divergences and would not protect the anchor.

Next useful branch:
Use action-conditioned EV for a conservative preflight/rerank diagnostic before
training another policy:

- Compare anchor action vs candidate action on paired first divergences.
- Gate only when `EV(state, candidate_action)` is not worse than
  `EV(state, anchor_action)` by a small margin.
- Validate on paired traces first, then only run duplicate-seat evaluation if
  harmful first-divergence recall is high and false-positive rate is low.

Stop rule:
Do not retry state-only `global_ev_td` coefficient sweeps. State EV cannot rank
same-state actions. Use action-conditioned EV or exact branch outcomes for
action selection diagnostics.

### Experiment: Exact Branch-CF Action-EV Calibration

Runs:

- Branch-only action EV:
  `/root/fh-mahjong-runs/chongci-branch-action-ev-20260614-201134`
- Trajectory-initialized branch fine-tune:
  `/root/fh-mahjong-runs/chongci-branch-action-ev-finetune-20260614-201348`

Question:
Can exact branch-CF preferred/avoided rewards improve action-conditioned EV
enough to become a reliable guard or reranker?

Implementation:

- Added `fh-mj-train-global-ev --branch-cf-action-targets`.
- Each exact branch-CF row is expanded into two action-conditioned samples:
  preferred action with `branch_preferred_rewards`, avoided action with
  `branch_avoided_rewards`.
- Added `fh-mj-action-ev-branch-cf-calibration` to measure whether an
  action-EV checkpoint ranks exact preferred branch actions above avoided
  branch actions on train and holdout shards.

Branch-CF datasets:

- Train:
  `/root/fh-mahjong-runs/chongci-branch-cf-anchor-large-20260612-235507/data/anchor-branch-cf-831000-r2048-gap002-b6`
- Holdout:
  `/root/fh-mahjong-runs/chongci-branch-cf-holdout-large-20260613-004827/data/anchor-branch-cf-851000-r2048-gap002-b6`

Branch-only action EV:

- Training rows: `4096` action-target rows from `2048` branch-CF pairs
- MLflow run: `f89766d263ef42a2a8591569a818be84`
- Checkpoint:
  `/root/fh-mahjong-runs/chongci-branch-action-ev-20260614-201134/checkpoints/branch_action_ev/epoch_012.pt`

Branch-CF calibration:

| checkpoint | train preferred rate | train gap-weighted preferred | holdout preferred rate | holdout gap-weighted preferred |
| --- | ---: | ---: | ---: | ---: |
| trajectory action EV | 48.29% | 47.28% | 46.44% | 48.68% |
| branch-only action EV | 67.24% | 67.91% | 68.65% | 66.66% |

Smoke first-divergence diagnostic on the KL rejected candidate:

| checkpoint | sign accuracy | harmful recall | margin 0 allowed | margin 0 actual allowed delta |
| --- | ---: | ---: | ---: | ---: |
| trajectory action EV | 66.67% | 66.67% | 4 / 8 | -0.2380 |
| branch-only action EV | 33.33% | 33.33% | 3 / 8 | -0.4590 |

Interpretation:
Exact branch-CF targets do improve ranking on exact branch-CF holdout, but the
branch-only model transfers worse to the paired smoke first-divergence trace.
This suggests the current branch-CF distribution is useful as a diagnostic
label source, but too narrow as a standalone action-EV training distribution.

Trajectory-initialized branch fine-tune:

- Init checkpoint:
  `/root/fh-mahjong-runs/chongci-action-global-ev-policyarch-20260614-174339/checkpoints/action_global_ev_policyarch/epoch_003.pt`
- Fine-tune checkpoint:
  `/root/fh-mahjong-runs/chongci-branch-action-ev-finetune-20260614-201348/checkpoints/branch_action_ev_finetune/epoch_004.pt`
- MLflow run: `57169bbf29ba474685d2a8bd9d546ec9`

Calibration:

| checkpoint | train preferred rate | train gap-weighted preferred | holdout preferred rate | holdout gap-weighted preferred |
| --- | ---: | ---: | ---: | ---: |
| trajectory-initialized branch fine-tune | 52.83% | 51.50% | 49.37% | 49.39% |

Smoke first-divergence diagnostic:

| checkpoint | sign accuracy | harmful recall | margin 0 allowed | margin 0 actual allowed delta |
| --- | ---: | ---: | ---: | ---: |
| trajectory-initialized branch fine-tune | 66.67% | 66.67% | 4 / 8 | -0.2380 |

Decision:
Reject branch-only and trajectory-initialized branch fine-tune as guard models.
Keep the calibration tooling. The best current guard preflight signal remains
the trajectory action-EV checkpoint, but it still needs a larger paired-trace
preflight before any live guarded duplicate-seat evaluation.

Next useful branch:
Run a larger tensor-bearing paired trace for the rejected KL candidate and
score the trajectory action-EV guard margins. If margin `0.0` still lets
through harmful first divergences, do not build live guard serving yet.

### Experiment: Larger Action-EV Guard Preflight

Run:
`/root/fh-mahjong-runs/chongci-action-ev-larger-preflight-20260614-201508`

Question:
Do the current action-conditioned EV checkpoints block harmful first
divergences on a larger tensor-bearing paired trace before any live guarded
duplicate-seat evaluation?

Data:

- Anchor checkpoint: promoted Chongci reward-trained anchor.
- Candidate checkpoint: rejected KL-constrained `global_ev_td` IQL probe.
- Seed window: `534000:10`
- Seats: `0 1 2 3`
- Paired trace settings: tensor-bearing first-divergence trace,
  `--max-divergences 1`, `--max-steps-per-episode 0`
- Paired trace report:
  `/root/fh-mahjong-runs/chongci-action-ev-larger-preflight-20260614-201508/reports/anchor_vs_candidate_tensor_trace_534000_n10.json`

Paired trace summary:

| metric | value |
| --- | ---: |
| pairs | 40 |
| scoreable first divergences | 37 |
| divergence rate | 92.50% |
| candidate better rate | 12.50% |
| mean candidate-minus-anchor delta | -0.1348 |

Guard preflight metrics:

| checkpoint | first-divergence corr | sign accuracy | harmful recall | margin 0 allowed | margin 0 actual allowed delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| trajectory action EV | -0.0098 | 42.11% | 35.71% | 20 / 37 | -4.4580 |
| branch-only action EV | 0.1526 | 52.63% | 50.00% | 20 / 37 | -2.6580 |
| branch fine-tune action EV | -0.0752 | 52.63% | 50.00% | 19 / 37 | -4.3400 |

Decision:
Rejected for serving/guard use. No action-EV checkpoint is safe enough for live
guarded duplicate-seat evaluation. The branch-only model is the least bad at
margin `0.0`, but it still lets through substantial harmful reward delta.

Interpretation:
State-only EV cannot compare same-state actions. Action-conditioned EV can, but
the current regression-only branch-CF objective is not aligned enough with the
paired-trace failures that matter for serving. The next branch should train the
action-EV scorer with an explicit branch-CF pairwise ranking loss and then
repeat this same larger paired-trace preflight before any live guard or rerank.

Implementation follow-up:
Added `fh-mj-train-global-ev` branch-CF pairwise ranking controls:

```text
--branch-cf-pairwise-weight
--branch-cf-pairwise-margin
--branch-cf-pairwise-reward-gap-weight
--branch-cf-pairwise-reward-gap-margin-scale
--branch-cf-pairwise-reward-gap-clip
```

These controls train `EV(state, preferred_action)` above
`EV(state, avoided_action)` directly on exact branch-CF rows while preserving
the branch reward regression target. This is diagnostic/guard infrastructure,
not a promoted play policy.

### Experiment: Branch-CF Pairwise Action-EV

Run:
`/root/fh-mahjong-runs/chongci-branch-action-ev-pairwise-20260615-032903`

Question:
Does adding an explicit branch-CF pairwise ranking loss make action-EV useful
enough for first-divergence guard/rerank preflight?

Training:

```text
fh-mj-train-global-ev
--data /root/fh-mahjong-runs/chongci-branch-cf-anchor-large-20260612-235507/data/anchor-branch-cf-831000-r2048-gap002-b6
--action-conditioned
--branch-cf-action-targets
--branch-cf-pairwise-weight 1.0
--branch-cf-pairwise-margin 0.05
--branch-cf-pairwise-reward-gap-weight 1.0
--branch-cf-pairwise-reward-gap-margin-scale 0.10
--epochs 12
--batch-size 1024
--lr 0.0001
--device cuda
```

MLflow run:
`57ebc1615c984ca9a9a0e7ce5ebfc111`

Checkpoint:
`/root/fh-mahjong-runs/chongci-branch-action-ev-pairwise-20260615-032903/checkpoints/branch_action_ev_pairwise/epoch_012.pt`

Regression result:

| metric | value |
| --- | ---: |
| validation MAE | 0.1242 |
| validation RMSE | 0.1944 |
| validation correlation | 0.1764 |
| baseline validation MAE | 0.1153 |
| branch-pair validation preferred rate | 77.33% |
| branch-pair validation gap-weighted preferred rate | 69.93% |

Exact branch-CF calibration:

| split | preferred rate | gap-weighted preferred rate | mean margin |
| --- | ---: | ---: | ---: |
| train | 74.95% | 72.86% | 0.0497 |
| holdout | 73.73% | 71.40% | 0.0479 |

Compared with the regression-only branch action-EV checkpoint, the pairwise
loss improves exact branch-CF holdout ranking from `68.65%` preferred to
`73.73%` preferred.

Paired-trace preflight:

- Paired trace:
  `/root/fh-mahjong-runs/chongci-action-ev-larger-preflight-20260614-201508/reports/anchor_vs_candidate_tensor_trace_534000_n10.json`
- Diagnostic report:
  `/root/fh-mahjong-runs/chongci-branch-action-ev-pairwise-20260615-032903/reports/pairwise_action_ev_first_divergence_diagnostics_strict_534000_n10.json`

| metric | value |
| --- | ---: |
| scoreable first divergences | 37 |
| MAE | 0.1884 |
| correlation | 0.1734 |
| sign accuracy | 68.42% |
| harmful recall | 71.43% |

Guard margin screen:

| margin | allowed | harmful block rate | actual allowed delta sum |
| ---: | ---: | ---: | ---: |
| -0.0200 | 23 / 37 | 42.86% | -3.5190 |
| -0.0500 | 26 / 37 | 35.71% | -3.4170 |
| 0.0000 | 14 / 37 | 71.43% | -2.8020 |
| 0.0200 | 11 / 37 | 78.57% | -0.5900 |
| 0.0500 | 11 / 37 | 78.57% | -0.5900 |
| 0.1000 | 6 / 37 | 85.71% | -0.2160 |
| 0.1500 | 0 / 37 | 100.00% | 0.0000 |

Decision:
Rejected for serving/guard use. The pairwise ranking objective improves exact
branch-CF ranking and larger paired-trace sign accuracy, but the useful guard
margins still allow negative reward delta. The only non-negative setting blocks
every divergence, which is equivalent to refusing the candidate rather than
learning a useful guard.

Interpretation:
The model is now fitting branch-CF ordering better, so the infrastructure is
working. The remaining failure is data/label alignment: exact branch rows from
generic anchor self-play do not yet cover the high-impact paired-trace failure
states well enough. Do not continue nearby margin/weight sweeps on this branch.

Next useful branch:
Generate exact branch-CF labels from the actual high-impact paired-trace failure
states, starting with the worst false positives in this report. The priority is
to make the action-EV scorer see those state/action contexts directly, not to
tune another global pairwise coefficient.

### Experiment: Targeted Action-EV Branch-CF From Guard Failures

Runs:

- False-positive branch-CF from `534000:10`:
  `/root/fh-mahjong-runs/chongci-targeted-action-ev-falsepositive-20260615-052116`
- Worst-delta branch-CF from `534000:10`:
  `/root/fh-mahjong-runs/chongci-targeted-worstdelta-branchcf-20260615-052259`
- Targeted mixed model, `534000` targets only:
  `/root/fh-mahjong-runs/chongci-targeted-action-ev-mixed-20260615-052217`
- Additional targeted branch-CF from independent `544000:10`:
  `/root/fh-mahjong-runs/chongci-targeted-544-branchcf-20260615-053312`
- Targeted mixed model, `534000+544000` targets:
  `/root/fh-mahjong-runs/chongci-targeted-action-ev-mixed3-20260615-053423`

Question:
Can exact branch-CF labels mined from high-impact paired-trace guard failures
make action-EV reliable enough for guard/rerank use?

Implementation:

Added `fh-mj-generate-targeted-branch-counterfactuals`.

The CLI reads paired-trace or action-EV diagnostic reports, extracts target
`seed/seat/decision_index` cases, replays the anchor checkpoint with exactly
that learning seat controlled, calls Go `EvaluateBranches` at the live matched
state, and writes the existing pairwise NPZ branch-CF schema.

This matters because saved observation tensors are not enough for exact branch
evaluation; the Go bridge needs the full hidden game state.

Targeted data:

| source | rows | mean reward gap | max reward gap | notes |
| --- | ---: | ---: | ---: | --- |
| `534000` action-EV false positives | 4 | 0.4520 | 1.2380 | all target decisions replayed |
| `534000` worst reward deltas | 8 | 0.3823 | 1.2380 | includes one pon/pass branch pair |
| `544000` action-EV false positives | 6 | 0.0753 | 0.2200 | lower gap than `534000` |
| `544000` worst reward deltas | 8 | 0.1029 | 0.2600 | lower gap than `534000` |

Training:

Mixed targeted models used the broad exact branch-CF shard plus repeated
targeted rows, with the same branch-CF pairwise action-EV objective:

```text
--action-conditioned
--branch-cf-action-targets
--branch-cf-pairwise-weight 1.0
--branch-cf-pairwise-margin 0.05
--branch-cf-pairwise-reward-gap-weight 1.0
--branch-cf-pairwise-reward-gap-margin-scale 0.10
```

Results on training/mining windows:

| checkpoint | eval window | sign accuracy | harmful recall | best useful margin | best useful allowed delta |
| --- | --- | ---: | ---: | ---: | ---: |
| pairwise action-EV | `534000:10` | 68.42% | 71.43% | 0.1000 | -0.2160 |
| targeted mixed, `534000` only | `534000:10` | 57.89% | 71.43% | 0.1000 | -0.1660 |
| targeted mixed3, `534000+544000` | `544000:10` | 36.36% | 33.33% | 0.0500 | +0.1730 |

The `544000` positive result is not sufficient because `544000` was also used
for targeted data mining before mixed3 was trained.

Held-out evaluation:

- Held-out trace:
  `/root/fh-mahjong-runs/chongci-targeted-action-ev-mixed3-20260615-053423/reports/anchor_vs_candidate_tensor_trace_554000_n10.json`
- Pairs: `40`
- Divergence rate: `72.50%`
- Candidate better rate: `15.00%`
- Mean candidate-minus-anchor delta: `-0.1002`

Held-out guard preflight:

| checkpoint | sign accuracy | harmful recall | margin 0 allowed delta | margin 0.05 allowed delta | margin 0.10 allowed delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| pairwise action-EV | 52.63% | 46.15% | -2.9420 | -2.0310 | -0.7770 |
| targeted mixed3 | 52.63% | 61.54% | -1.4230 | -0.8840 | -0.8880 |

Decision:
Rejected for guard/serving use. Targeted branch-CF mining improves the held-out
allowed-delta loss compared with the broad pairwise model, but every non-empty
guard margin still allows negative reward delta on held-out `554000:10`.

Interpretation:
The targeted exact-state generator is useful and should stay. The current
action-EV scorer is still not robust enough to guard a live candidate. The
failure is no longer missing exact-state plumbing; it is weak generalization
from tiny targeted branch labels.

Stop rule:
Do not run live guarded duplicate-seat evaluation from these action-EV
checkpoints. Do not continue by changing only pairwise weights or guard margins.

Next useful branch:
Scale the targeted exact-state dataset across more independent windows before
training another scorer, or use the targeted data as an offline diagnostic for
candidate proposal quality rather than a serving guard. A minimum viable next
dataset should mine false positives and worst deltas from at least three
training windows, then hold out a fourth window before any guard consideration.

### Experiment: Scaled Targeted Action-EV And Proposal Diagnostics

Runs:

- Targeted data scale run:
  `/root/fh-mahjong-runs/chongci-targeted-action-ev-scale-20260615-054630`
- Scaled targeted action-EV training:
  `/root/fh-mahjong-runs/chongci-targeted-action-ev-scaled-train-20260615-061310`
- Proposal-quality diagnostic:
  `/root/fh-mahjong-runs/chongci-targeted-proposal-diagnostics2-20260615-061827`

Question:
Does adding more independent targeted exact-state branch labels make action-EV
robust enough for guard use, and if not, are candidates even proposing exact
preferred branches?

Scaled targeted data:

| window | false-positive rows | false-positive mean gap | worst-delta rows | worst-delta mean gap |
| --- | ---: | ---: | ---: | ---: |
| `564000:10` | 5 | 0.1012 | 8 | 0.1512 |
| `574000:10` | 4 | 0.1022 | 8 | 0.0665 |
| `584000:10` | 8 | 0.2267 | 8 | 0.1182 |

Trace summaries for these mining windows:

| window | pairs | divergence rate | candidate better rate | mean candidate-minus-anchor delta |
| --- | ---: | ---: | ---: | ---: |
| `564000:10` | 40 | 80.00% | 17.50% | -0.0261 |
| `574000:10` | 40 | 82.50% | 20.00% | -0.0108 |
| `584000:10` | 40 | 82.50% | 25.00% | -0.0569 |

Training:

The scaled scorer used the broad branch-CF shard plus the older `534000` and
`544000` targeted rows and the new `564000`, `574000`, `584000` rows, repeated
32 times.

MLflow run:
`e3f153e570b44cc6875f930d5ea5cefc`

Checkpoint:
`/root/fh-mahjong-runs/chongci-targeted-action-ev-scaled-train-20260615-061310/checkpoints/targeted_action_ev_scaled/epoch_012.pt`

Training report:

| metric | value |
| --- | ---: |
| action-target transitions | 8384 |
| validation MAE | 0.1292 |
| baseline validation MAE | 0.1209 |
| validation correlation | 0.3110 |
| branch-CF holdout preferred rate | 67.29% |
| branch-CF holdout gap-weighted preferred rate | 63.74% |

Held-out `554000:10` guard preflight:

| checkpoint | sign accuracy | harmful recall | margin 0 allowed delta | margin 0.05 allowed delta | margin 0.10 allowed delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| targeted mixed3 | 52.63% | 61.54% | -1.4230 | -0.8840 | -0.8880 |
| scaled targeted action-EV | 63.16% | 46.15% | -2.9070 | -1.8230 | -1.0380 |

Decision:
Rejected for guard/serving use. Scaling targeted data improved validation
correlation but worsened the held-out guard screen versus mixed3. This confirms
that more of the same small targeted labels is not enough.

Proposal-quality diagnostic:

After adding action IDs to compact global-EV diagnostic rows and preserving
left/right paired-trace actions in targeted branch-CF arrays, the held-out
`554000` proposal-quality report showed:

| policy side | valid rows | exact preferred matches | preferred match rate | exact avoided matches | neither rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| anchor/left | 15 | 2 | 13.33% | 0 | 86.67% |
| candidate/right | 15 | 3 | 20.00% | 0 | 80.00% |

Report:
`/root/fh-mahjong-runs/chongci-targeted-proposal-diagnostics2-20260615-061827/reports/proposal_quality_554.json`

Interpretation:
The candidate is not commonly choosing the exact preferred branch in these
failure states. The guard model is therefore trying to rescue a weak proposal
set rather than selecting between consistently good candidates. This makes live
guarding a poor next step.

Stop rule:
Do not continue action-EV guard training by only adding more small targeted
windows, pairwise weights, or guard margin sweeps.

Next useful branch:
Improve candidate proposal quality directly. Use exact branch-CF rows to train
or evaluate the policy/Q action head so the candidate can put exact preferred
branches into its top-k proposals before rerunning action-EV guard work.

### Experiment: Branch-CF proposal policy head training

Run:
`/root/fh-mahjong-runs/chongci-branch-proposal-policy-20260615-062504`

Follow-up stronger run:
`/root/fh-mahjong-runs/chongci-branch-proposal-policy-strong-20260615-063005`

Question:
Can exact branch-counterfactual labels improve the candidate's action proposal
quality enough that future critic or guard work has good branches to choose
from?

Data:
The first run used the broad `2048`-row branch-CF shard
`anchor-branch-cf-831000-r2048-gap002-b6` plus targeted exact-state rows from
false-positive and worst-delta action-EV windows. The stronger run reused the
same data mixture.

Training:
Both runs initialized from the promoted Chongci anchor:
`/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`.

The first run trained frozen encoder heads for `8` epochs with `q_weight=0.25`,
`anchor_kl_weight=0.05`, and `reward_gap_weight=0.5`; MLflow run
`bd345015e00f4db0a85e3d0cb73e5e74`.

The stronger run trained frozen encoder heads for `20` epochs and `10`
steps/epoch with `q_weight=0.5`, `anchor_kl_weight=0.02`, and
`reward_gap_weight=1.0`; MLflow run
`b2ed0192632b44b5b0215e60b04c38a9`.

Evaluation:
Independent branch-CF holdout:
`/root/fh-mahjong-runs/chongci-branch-cf-holdout-large-20260613-004827/data/anchor-branch-cf-851000-r2048-gap002-b6`.

Selected-window duplicate-seat smoke:
`534000:6`, `544001:4`, `554001:1`, all seats, Chongci mode,
`--max-steps-per-episode 0`.

Result:

| checkpoint | branch holdout policy better | branch holdout Q better | policy argmax preferred | selected smoke mean | selected smoke positive | selected smoke large loss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| anchor | 57.23% | 51.37% | 23.78% | -0.01 | 50.00% | 18.18% |
| first proposal epoch 8 | 57.37% | 53.03% | 23.88% | not run | not run | not run |
| strong proposal epoch 17 | 62.45% | 63.53% | 22.56% | -1.00 | 11.36% | 45.45% |
| strong proposal epoch 20 | 62.11% | 62.55% | 22.22% | not run | not run | not run |

Reports:

```text
/root/fh-mahjong-runs/chongci-branch-proposal-policy-20260615-062504/reports/branch_proposal_holdout_calibration.json
/root/fh-mahjong-runs/chongci-branch-proposal-policy-20260615-062504/reports/anchor_holdout_calibration.json
/root/fh-mahjong-runs/chongci-branch-proposal-policy-strong-20260615-063005/reports/branch_proposal_strong_epoch017_holdout_calibration.json
/root/fh-mahjong-runs/chongci-branch-proposal-policy-strong-20260615-063005/reports/branch_proposal_strong_epoch020_holdout_calibration.json
/root/fh-mahjong-runs/chongci-branch-proposal-policy-strong-20260615-063005/reports/anchor_selected_window_smoke.json
/root/fh-mahjong-runs/chongci-branch-proposal-policy-strong-20260615-063005/reports/strong_epoch017_selected_window_smoke.json
```

Decision:
Reject both branch-proposal policy checkpoints for gameplay. The stronger
checkpoint clearly improves exact branch-label ranking, but it destroys live
selected-window Chongci performance.

Interpretation:
Short-horizon exact branch-CF labels remain useful diagnostics, but directly
pushing the deployed policy head toward them is not aligned enough with
full-match Chongci EV and tail risk. This repeats the earlier pattern seen in
branch-CF distillation: offline preferred-label gains are not sufficient.

Stop rule:
Do not continue this line with nearby proposal-head hyperparameter sweeps. The
next useful direction should either collect more aligned full-match labels,
use branch labels only for offline diagnostics/state selection, or train a
separate non-serving proposal model whose suggestions must pass an exact
preflight before gameplay.

### Experiment: Full-match aligned divergence from failed proposal policy

Run:
`/root/fh-mahjong-runs/chongci-fullmatch-aligned-proposal-divergence-20260615-063931`

Question:
Can real full-match divergence labels from the failed proposal policy produce a
more aligned training signal than short-horizon exact branch-CF labels?

Data:
Paired trace compared the promoted anchor against the rejected strong proposal
checkpoint:

```text
anchor:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
proposal_bad:
  /root/fh-mahjong-runs/chongci-branch-proposal-policy-strong-20260615-063005/checkpoints/branch_proposal_policy_strong/epoch_017.pt
windows:
  534000:6
  544001:4
  554001:1
seats:
  0, 1, 2, 3
max_divergences:
  1
```

Trace result:

```text
pairs: 44
divergence_rate: 100.00%
proposal_bad_better_rate: 13.64%
mean proposal_bad-minus-anchor delta: -0.9893
```

Report:
`/root/fh-mahjong-runs/chongci-fullmatch-aligned-proposal-divergence-20260615-063931/reports/anchor_vs_proposal_bad_selected_trace.json`

Counterfactual shard:

```text
path:
  /root/fh-mahjong-runs/chongci-fullmatch-aligned-proposal-divergence-20260615-063931/data/anchor_preferred_first_gap005
rows:
  36
min_reward_gap:
  0.05
mean_reward_gap:
  1.3046
preferred_policy:
  anchor
divergence_source:
  first
```

Training:
One conservative IQL epoch initialized from the promoted anchor, using the
current broader mixed self-play data as normal replay and the 36-row
full-match-aligned shard as pairwise-only auxiliary data.

```text
checkpoint:
  /root/fh-mahjong-runs/chongci-fullmatch-aligned-proposal-divergence-20260615-063931/checkpoints/fullmatch_aligned_pairwise_lowdose/epoch_001.pt
MLflow:
  095fdc10468b4c7e823b0afda035df4a
pairwise rows after replay expansion:
  2304
pairwise policy loss:
  0.0000
pairwise Q loss:
  active, last logged 0.0862
```

Evaluation:
Same selected-window duplicate-seat smoke, Chongci mode,
`--max-steps-per-episode 0`.

| checkpoint | mean reward | positive rate | large-loss rate |
| --- | ---: | ---: | ---: |
| anchor | -0.01 | 50.00% | 18.18% |
| full-match aligned pairwise low-dose | -0.04 | 45.45% | 20.45% |

Report:
`/root/fh-mahjong-runs/chongci-fullmatch-aligned-proposal-divergence-20260615-063931/reports/fullmatch_aligned_pairwise_lowdose_selected_window_smoke.json`

Decision:
Rejected. This is much less destructive than the proposal-policy checkpoint,
but it still loses EV, positive rate, and large-loss rate against the anchor on
the same selected-window smoke.

Interpretation:
The aligned full-match trace is a better data source than short-horizon branch
labels, but 36 strict first-divergence rows from one failed policy are still too
small for a useful direct training update. The next useful step is not another
nearby low-dose replay multiplier or pairwise coefficient. Generate a larger
independent full-match divergence set first, then inspect whether anchor-
preferred rows cover enough action contexts before training again.

### Experiment: Mortal-Style Mixed Full-Match Self-Play IQL Low-Dose

Run:
`/root/fh-mahjong-runs/chongci-mortalstyle-mixed-selfplay-20260616-044500`

Question:
After re-reading Mortal and Suphx, test the better-aligned direction:
large operation-level full-match replay first, then one conservative reward-
learning update from the promoted Chongci anchor. This intentionally avoids
another small branch-CF, action-EV guard, or scalar risk-penalty sweep.

Implementation changes:
- Added per-seat checkpoint sampling overrides to `fh-mj-generate-selfplay`.
  This allows two greedy anchor seats plus one controlled exploration seat in
  the same table.
- Added `--checkpoint-sample-action-family` / per-seat `sample_family`, so the
  exploration checkpoint samples only decisions where all legal actions are in
  the requested family. For this run, exploration was discard-only.
- Added `fh-mj-dataset-diagnostics` to summarize replay coverage before
  training: policy-source mix, action-family distribution, final acting-seat
  return, large-loss coverage, terminal outcome fields when present, and
  Chongci score-pressure buckets.

Data:
Generated 400 full Chongci matches, seeds `900000` through `900399`, all four
seats in the simulator.

Table mix:
- seat 0: greedy promoted anchor
- seat 1: greedy promoted anchor
- seat 2: heuristic/shanten opponent, auto-played by Go
- seat 3: promoted anchor with top-k sampling only on discard-only decisions

Anchor:
`/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`

Dataset:
`/root/fh-mahjong-runs/chongci-mortalstyle-mixed-selfplay-20260616-044500/data/anchor2-heuristic-discard-sampled-900000-n400-npz`

Manifest:
`/root/fh-mahjong-runs/chongci-mortalstyle-mixed-selfplay-20260616-044500/reports/anchor2-heuristic-discard-sampled-900000-n400.manifest.json`

Generation result:
- matches: 400
- transitions: 611,706
- elapsed: 2,459.61 seconds
- shards: 13

Coverage diagnostics:
`/root/fh-mahjong-runs/chongci-mortalstyle-mixed-selfplay-20260616-044500/reports/anchor2-heuristic-discard-sampled-900000-n400.dataset_diagnostics.json`

Key coverage:
- policy source rows: source 0 = 203,559, source 1 = 204,053, source 3 =
  204,094. Source 2 is the heuristic opponent and is not emitted as learning
  rows because Go auto-plays heuristic seats.
- action-family distribution:
  - discard: 481,867 (78.77%)
  - pass: 70,098 (11.46%)
  - chii: 24,803 (4.05%)
  - pon: 18,403 (3.01%)
  - win: 14,652 (2.40%)
  - kan: 1,862 (0.30%)
  - haitei: 21
- acting-seat final return:
  - mean: -0.00223
  - sum: -1,364.70
  - std: 1.0433
  - min/max: -2.275 / 4.221
  - positive rate: 48.38%
  - large-loss rate at `-1.0`: 17.32%
- score-pressure scalars were available.

Diagnostic limitation:
The full-match Chongci replay stores final match returns correctly, but the
round-style terminal winner/discarder fields were not populated in this dataset
(`winner_seat=-1`, `discarder_seat=-1`). Deal-in/win counts therefore remain
evaluation-time metrics for this run, not dataset-coverage metrics.

Training:
One conservative IQL epoch from the promoted anchor:

```text
target_mode=mc
epochs=1
batch_size=4096
lr=0.00001
expectile=0.7
temperature=3.0
max_weight=20.0
bc_weight=0.04
policy_kl_anchor_checkpoint=<promoted anchor>
policy_kl_weight=0.02
large_loss_threshold=-1.0
max_transitions=200000
device=cuda
```

Checkpoint:
`/root/fh-mahjong-runs/chongci-mortalstyle-mixed-selfplay-20260616-044500/checkpoints/mortalstyle_mixed_iql_lowdose/epoch_001.pt`

MLflow training run:
`27739837660d457f9825d3ae8bdc91b6`

Final logged training loss:
`0.0719`

Evaluation:
Selected-window duplicate-seat smoke only:
- seeds: `534000:6`, `544001:4`, `554001:1`
- mode: Chongci
- seats: duplicate all seats
- max steps per episode: `0`

Reports:
- anchor:
  `/root/fh-mahjong-runs/chongci-mortalstyle-mixed-selfplay-20260616-044500/reports/anchor_selected_window_smoke.json`
- candidate:
  `/root/fh-mahjong-runs/chongci-mortalstyle-mixed-selfplay-20260616-044500/reports/candidate_selected_window_smoke.json`

| checkpoint | episodes | mean reward | reward sum | positive rate | large-loss rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| anchor | 44 | -0.0150 | -0.6600 | 50.00% | 18.18% |
| mortal-style mixed IQL low-dose | 44 | -0.0690 | -3.0380 | 45.45% | 18.18% |

Decision:
Rejected. The candidate ties large-loss rate but loses expected reward and
positive rate on the selected-window duplicate-seat smoke. Do not run the
repeated combined gate for this checkpoint.

Interpretation:
The new data loop is the right direction and is much better aligned with Mortal
than the previous tiny branch-CF shards, but one low-dose MC-IQL pass over the
first 200k rows still nudged the policy in a worse direction. The likely next
engineering gap is not another scalar penalty. The next useful step is to make
the dataset/training loop more measurable:

1. Record whether sampled discard actions actually diverged from greedy anchor
   actions during generation.
2. Add an offline replay evaluation of anchor vs trained candidate over the
   generated dataset before live smoke.
3. If the sampled seat rarely differs from greedy, increase discard exploration
   coverage or explicitly store greedy-vs-sampled divergence rows.
4. If divergence is healthy, train with stronger anchor preservation or split
   train/validation by match seed before another live smoke.

Follow-up replay policy diagnostic:

To reuse the generated replay and rejected checkpoint instead of discarding the
experiment, added `fh-mj-replay-policy-diagnostics` and ran it on the first
200,000 replay rows used by the IQL update.

Report:
`/root/fh-mahjong-runs/chongci-mortalstyle-mixed-selfplay-20260616-044500/reports/mortalstyle_mixed_iql_lowdose_replay_policy_diagnostics_200k.json`

Key result:
- anchor vs replay agreement: 99.305%
- candidate vs replay agreement: 99.2305%
- candidate vs anchor divergence: 374 / 200,000 = 0.187%
- divergence by source:
  - source 0: 89 / 66,433 = 0.134%
  - source 1: 108 / 66,710 = 0.162%
  - source 3: 177 / 66,857 = 0.265%
- divergence action-family pairs:
  - discard -> discard: 349
  - chii -> pass: 10
  - pass -> chii: 5
  - pass -> pon: 3
  - other pairs: 7
- all-row return mean: -0.0160
- anchor/candidate-agree return mean: -0.0158
- anchor/candidate-diverge return mean: -0.1143
- large-loss rows: 16.19%
- large-loss rows with candidate/anchor divergence: 78

Interpretation update:
The rejected checkpoint did not broadly drift away from the anchor. It changed
only a tiny slice of decisions, and that slice has materially worse replay
return. This makes the run useful as a targeted failure-mining source:

1. Extract the 374 candidate-vs-anchor divergence rows.
2. Prioritize the 349 discard-vs-discard rows and the 78 large-loss divergence
   rows.
3. Reconstruct or branch-evaluate those exact states if possible.
4. Use them as explicit anchor-preservation / do-not-change labels before
   another broad IQL pass.
5. Do not generate a larger 1000-match dataset until this divergence slice is
   understood; otherwise we risk scaling the same weak signal.

### Experiment: Anchor-Preservation Divergence Shard And Retry

Run:
`/root/fh-mahjong-runs/chongci-mortalstyle-mixed-selfplay-20260616-044500`

Question:
Can we reuse the rejected Mortal-style mixed IQL candidate by mining its harmful
anchor-vs-candidate replay divergences, then training a conservative retry that
keeps the broad reward-learning update while explicitly preserving the anchor on
the known bad discard changes?

New tooling:
Extended `fh-mj-replay-policy-diagnostics` so it can write a pairwise auxiliary
shard from candidate-vs-anchor replay divergences. The labels are deliberately
marked as `anchor_preservation_divergence`, not exact branch-CF labels: anchor
action is preferred, rejected-candidate action is avoided, and a small synthetic
pairwise gap is used only to prevent known bad drift.

Extracted shards:
- all divergences:
  `/root/fh-mahjong-runs/chongci-mortalstyle-mixed-selfplay-20260616-044500/data/anchor_preservation_divergences_200k`
- discard-vs-discard divergences:
  `/root/fh-mahjong-runs/chongci-mortalstyle-mixed-selfplay-20260616-044500/data/anchor_preservation_discard_divergences_200k`

All-divergence shard:
- rows: 374
- return mean: -0.1143
- action-family pairs:
  - discard -> discard: 349
  - chii -> pass: 10
  - pass -> chii: 5
  - pass -> pon: 3
  - other: 7

Discard-vs-discard shard:
- rows: 349
- return mean: -0.0895
- source rows:
  - source 0: 82
  - source 1: 100
  - source 3: 167

Calibration on the discard-vs-discard shard:
- anchor policy preferred-action rate: 100.00%
- rejected candidate policy preferred-action rate: 0.57%
- rejected candidate policy avoided-action rate: 99.43%

This validates that the shard directly captures the policy-head difference that
made the rejected checkpoint worse, rather than broad unrelated replay noise.

Training:
One conservative IQL retry from the promoted anchor:

```text
data=<400-match mixed full-match replay>
pairwise_data=anchor_preservation_discard_divergences_200k
pairwise_replay_multiplier=32
pairwise_weight=0.02
pairwise_margin=0.05
pairwise_q_weight=0.0
target_mode=mc
epochs=1
batch_size=4096
lr=0.00001
bc_weight=0.04
policy_kl_weight=0.02
max_transitions=200000
```

Checkpoint:
`/root/fh-mahjong-runs/chongci-mortalstyle-mixed-selfplay-20260616-044500/checkpoints/mortalstyle_mixed_iql_anchor_preserve_discard/epoch_001.pt`

MLflow training run:
`f7a2718b643949caa8eb9002c7b64eec`

Replay diagnostic after training:
`/root/fh-mahjong-runs/chongci-mortalstyle-mixed-selfplay-20260616-044500/reports/mortalstyle_mixed_iql_anchor_preserve_discard_replay_policy_diagnostics_200k.json`

Compared with the first rejected candidate:
- candidate-vs-anchor divergence fell from 374 to 129 rows.
- discard-vs-discard divergence fell from 349 to 114 rows.
- large-loss divergence fell from 78 to 24 rows.
- divergence-row mean return improved from -0.1143 to -0.0701.

Selected-window duplicate-seat smoke:
`/root/fh-mahjong-runs/chongci-mortalstyle-mixed-selfplay-20260616-044500/reports/mortalstyle_mixed_iql_anchor_preserve_discard_selected_window_smoke.json`

| checkpoint | episodes | mean reward | reward sum | positive rate | large-loss rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| anchor | 44 | -0.0150 | -0.6600 | 50.00% | 18.18% |
| first mixed IQL reject | 44 | -0.0690 | -3.0380 | 45.45% | 18.18% |
| anchor-preservation retry | 44 | -0.0240 | -1.0580 | 47.73% | 18.18% |

Decision:
Rejected, but useful. The divergence-mining approach recovered most of the
damage from the first rejected candidate, but it still loses EV and positive
rate versus the promoted anchor on the selected-window smoke. Do not run the
repeated combined gate.

Interpretation:
This confirms prior rejected experiments are reusable:
- The rejected candidate exposed a small harmful policy-drift slice.
- Mining that slice and training against it reduced harmful replay divergence.
- The approach improved the rejected checkpoint materially, but not enough for
promotion.

Next direction:
Use divergence extraction as a preflight loop before any more live smoke:

1. For every new broad IQL/AWBC candidate, compare it against the anchor on the
   replay dataset first.
2. If candidate-vs-anchor divergence is tiny and negative-return concentrated,
   mine those rows and correct before live evaluation.
3. If divergence is broad or improves replay return, then run selected-window
   smoke.
4. The next actual improvement attempt should collect stronger positive
   exploration signal, not only anchor-preservation negatives. Candidate
   preservation can stop harm, but it does not by itself create better play.

### Experiment: Stronger Discard-Sampling Coverage Probe

Run:
`/root/fh-mahjong-runs/chongci-sampled-discard-coverage-20260616-081945`

Target recap:
The target remains a stronger Chongci policy than the promoted anchor, measured
by deterministic duplicate-seat mean reward with no worse large-loss rate.
Reward learning should improve operation-level action choice under final
Chongci match return. The previous anchor-preservation retry was useful but not
sufficient: it reduced harmful drift from a rejected candidate, but it did not
create better play. The corrected next target is therefore positive exploration
signal, not another preservation-only sweep.

Question:
Does stronger discard-only top-k sampling produce measurable sampled-vs-greedy
divergence with usable final-return coverage?

Data:
Generated 100 full Chongci matches:

```text
seeds: 910000..910099
table:
  seat 0: greedy promoted anchor
  seat 1: greedy promoted anchor
  seat 2: heuristic opponent
  seat 3: promoted anchor, temperature=1.25, top_k=5, sample_family=discard
```

Dataset:
`/root/fh-mahjong-runs/chongci-sampled-discard-coverage-20260616-081945/data/anchor2-heuristic-discard-sampled-910000-n100-npz`

Diagnostics:
`/root/fh-mahjong-runs/chongci-sampled-discard-coverage-20260616-081945/reports/anchor2-heuristic-discard-sampled-910000-n100.dataset_diagnostics.json`

Generation result:
- matches: 100
- transitions: 153,663
- elapsed: 628.42 seconds

Overall coverage:
- acting-return mean: -0.0160
- positive rate: 46.10%
- large-loss rate: 15.94%
- action mix:
  - discard: 78.65%
  - pass: 11.54%
  - chii: 4.07%
  - pon: 3.06%
  - win: 2.40%
  - kan: 0.28%

Sampling coverage:
- sampling-applied rows: 40,161
- true sampled-vs-greedy divergences: 1,710
- sampled-vs-greedy rate among sampled decisions: 4.26%
- all sampled divergences were `discard -> discard`
- sampled divergence return mean: +0.0102
- sampled divergence positive rate: 43.74%
- sampled divergence large-loss rate: 15.03%

Interpretation:
This is a useful correction. The previous 400-match run did not record whether
sampling truly changed the greedy action, so it could not distinguish weak
exploration from anchor-clone replay. The new instrumentation shows that
stronger discard-only sampling does produce a nontrivial set of actual
discard-vs-discard divergences, and those divergences are not obviously worse:
their mean return is slightly positive and their large-loss rate is lower than
the full dataset.

Decision:
Scale this exact sampling setting to a larger independent dataset before
training. Do not train from this 100-match probe alone; use it as a coverage
gate. The next run should generate 400 matches with the same settings and then
train only after dataset diagnostics confirm similar or better sampled
divergence coverage.

### Experiment: Scaled Discard-Sampling Coverage Gate

Run:
`/root/fh-mahjong-runs/chongci-sampled-discard-scaled-20260616-083304`

Question:
Does the stronger discard-only sampling signal from the 100-match probe remain
usable at 400 matches, and is broad IQL training justified?

Data:
Generated 400 full Chongci matches:

```text
seeds: 920000..920399
table:
  seat 0: greedy promoted anchor
  seat 1: greedy promoted anchor
  seat 2: heuristic opponent
  seat 3: promoted anchor, temperature=1.25, top_k=5, sample_family=discard
transitions: 613,997
elapsed: 2,412.91 seconds
```

Dataset:
`/root/fh-mahjong-runs/chongci-sampled-discard-scaled-20260616-083304/data/anchor2-heuristic-discard-sampled-920000-n400-npz`

Diagnostics:
`/root/fh-mahjong-runs/chongci-sampled-discard-scaled-20260616-083304/reports/anchor2-heuristic-discard-sampled-920000-n400.dataset_diagnostics.json`

Overall coverage:
- acting-return mean: -0.0352
- positive rate: 44.99%
- large-loss rate: 15.66%
- action mix:
  - discard: 78.75%
  - pass: 11.45%
  - chii: 4.06%
  - pon: 3.03%
  - win: 2.40%
  - kan: 0.31%

Sampling coverage:
- sampling-applied rows: 160,519
- true sampled-vs-greedy divergences: 6,873
- sampled-vs-greedy rate among sampled decisions: 4.28%
- all sampled divergences were `discard -> discard`
- sampled divergence return mean: -0.2071
- sampled divergence positive rate: 37.31%
- sampled divergence large-loss rate: 19.34%

Decision:
Do not train broad IQL/AWBC from this dataset as-is. The dataset has enough
true sampled-vs-greedy decisions, but the sampled divergence slice is
materially worse than the full dataset: lower mean return, lower positive rate,
and higher large-loss rate.

Interpretation:
The stronger sampling setting solved the previous coverage problem but exposed
a better target problem: naive discard exploration often chooses worse actions.
The useful next step is to reuse the exact branch-counterfactual infrastructure
on sampled-vs-greedy discard divergences, preferably with full-match branch
rollouts, and only train from validated positive branch labels. This keeps the
work aligned with final Chongci reward instead of learning from broad sampled
replay that is already tail-worse.

### Experiment: Full-Match Sampled-Vs-Greedy Discard Branch-CF Probe

Run:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-branchcf-20260616-091439`

Question:
Can we turn the stronger sampling coverage into aligned reward-learning labels
by evaluating exact sampled-vs-greedy discard divergences through match end?

Data:

```text
parent scaled dataset:
  /root/fh-mahjong-runs/chongci-sampled-discard-scaled-20260616-083304
checkpoint:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
seeds: 930000..930019
temperature: 1.25
top_k: 5
action_family: discard
min_reward_gap: 0.02
max_rows: 256
branch_through_match_end: true
branch_max_decisions: 8192
```

Decision:
Completed. The run hit the 256-row cap:

```text
rows: 256
branch_calls: 821
branch_results: 1,642
skipped_same_action: 23,118
skipped_action_family: 64
skipped_no_label: 565
mean_reward_gap: 0.2479
max_reward_gap: 1.3300
sampled_preferred_count: 124
greedy_preferred_count: 132
preferred_family_counts: discard=256
avoided_family_counts: discard=256
elapsed_seconds: 2,438.08
```

Interpretation:
This is the correct data shape. It shows the stronger discard sampler is not
generically good, but it does find real positive alternatives: sampled is
preferred in 124/256 full-match exact branch labels, while greedy is preferred
in 132/256. This is much better than broad sampled replay because every row is
an exact same-state comparison with final Chongci match reward.

### Experiment: Full-Match Pairwise IQL From Sampled Discard Labels

Run:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-20260616-095618`

Question:
Can one conservative MC-IQL pass use the broad sampled dataset for final-return
coverage while the full-match sampled-vs-greedy branch-CF shard supplies exact
same-state discard preferences?

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
primary data:
  /root/fh-mahjong-runs/chongci-sampled-discard-scaled-20260616-083304/data/anchor2-heuristic-discard-sampled-920000-n400-npz
pairwise data:
  /root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-branchcf-20260616-091439/data/sampled-discard-fullmatch-930000-e20-r256-gap002
epochs: 1
lr: 1e-5
max_transitions: 200,000
policy_kl_weight: 0.05
pairwise_replay_multiplier: 64
pairwise_weight: 0.005
pairwise_q_weight: 0.10
pairwise_margin: 0.02
pairwise_q_margin: 0.02
MLflow run id: f33d4a688ca045e19f72423d7f3dbcee
```

Candidate:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-20260616-095618/checkpoints/sampled_discard_fullmatch_pairwise_iql/epoch_001.pt`

Selected-window smoke:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
episodes: 44
max_steps_per_episode: 0
```

| checkpoint | avg reward | reward sum | positive rate | large-loss rate | win rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| anchor | -0.0100 | -0.6600 | 50.00% | 18.18% | 50.00% |
| full-match pairwise IQL | -0.0200 | -1.0520 | 50.00% | 18.18% | 50.00% |

Decision:
Rejected. Do not run the larger repeated gate. The candidate ties the selected
smoke large-loss rate but loses EV/reward sum versus the anchor.

Interpretation:
The target correction was right: broad sampled replay alone was tail-worse, and
exact full-match branch labels are the right aligned primitive. The first
256-row auxiliary shard is still too small or underweighted to improve live
duplicate-seat EV from the current anchor. Do not sweep nearby pairwise
coefficients. The next useful step is to scale full-match sampled-vs-greedy
branch-CF labels across more independent seeds, then train a candidate only
after the scaled shard has enough preferred sampled alternatives and balanced
greedy-preservation rows.

### Experiment: Scaled Full-Match Sampled-Vs-Greedy Branch-CF Labels

Run:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-branchcf-scale-20260616-100502`

Question:
Can the balanced 256-row full-match sampled-vs-greedy discard branch-CF probe
be scaled to a stronger aligned auxiliary dataset before another reward
learning candidate?

Data:

```text
parent broad sampled dataset:
  /root/fh-mahjong-runs/chongci-sampled-discard-scaled-20260616-083304
parent 256-row branch-CF probe:
  /root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-branchcf-20260616-091439
checkpoint:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
seeds: 940000..940079
temperature: 1.25
top_k: 5
action_family: discard
min_reward_gap: 0.02
max_rows: 1,024
branch_through_match_end: true
branch_max_decisions: 8192
max_elapsed_seconds: 21,600
```

Result:

```text
rows: 1,024
branch_calls: 3,065
branch_results: 6,130
skipped_same_action: 86,590
skipped_action_family: 241
skipped_no_label: 2,041
mean_reward_gap: 0.2752
max_reward_gap: 1.7430
sampled_preferred_count: 492
greedy_preferred_count: 532
preferred_family_counts: discard=1,024
avoided_family_counts: discard=1,024
elapsed_seconds: 9,386.38
```

Decision:
Passed data-quality screening. The preferred split remains balanced enough to
avoid learning "sampled is always better", and the mean reward gap is large
enough to justify one scaled-label candidate.

### Experiment: Scaled Full-Match Pairwise IQL Candidate

Run:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009`

Question:
Does replacing the 256-row full-match sampled-vs-greedy branch-CF shard with a
balanced 1,024-row shard fix the selected-smoke-only improvement and transfer
to the repeated combined gate?

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
primary data:
  /root/fh-mahjong-runs/chongci-sampled-discard-scaled-20260616-083304/data/anchor2-heuristic-discard-sampled-920000-n400-npz
pairwise data:
  /root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-branchcf-scale-20260616-100502/data/sampled-discard-fullmatch-940000-e80-r1024-gap002
epochs: 1
lr: 1e-5
max_transitions: 200,000
policy_kl_weight: 0.05
pairwise_replay_multiplier: 32
pairwise_weight: 0.005
pairwise_q_weight: 0.10
pairwise_margin: 0.02
pairwise_q_margin: 0.02
MLflow run id: de4c5f12601f4a5591ab672f538df820
```

Candidate:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009/checkpoints/sampled_discard_fullmatch_pairwise_iql_scale/epoch_001.pt`

Selected-window smoke:

| checkpoint | avg reward | reward sum | positive rate | large-loss rate | win rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| anchor | -0.0100 | -0.6600 | 50.00% | 18.18% | 50.00% |
| scaled pairwise IQL | 0.0500 | 2.0380 | 50.00% | 15.91% | 50.00% |

Repeated combined gate, repeat 1:

| checkpoint | avg reward | reward sum | positive rate | large-loss rate | win rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| anchor | 0.0100 | 1.4410 | 47.50% | 13.33% | 47.50% |
| scaled pairwise IQL | -0.0000 | -0.2770 | 47.50% | 14.17% | 47.50% |

Decision:
Rejected. The selected-window smoke improvement did not transfer to the first
combined-gate repeat. The candidate loses EV and worsens large-loss rate versus
the anchor. Repeat 2 was stopped because repeat 1 already failed the promotion
rule.

Interpretation:
The scaled full-match branch labels are useful, but training from broad sampled
replay plus balanced sampled-vs-greedy pairwise labels still creates broad
policy drift. The candidate diverged often and did not generalize to the full
combined gate. Do not tune nearby pairwise weights from this point. Diagnose
the failed combined-gate divergences and build targeted labels from actual
high-impact failure states.

### Experiment: Combined-Gate Failure Trace And Worst-State Targeted Branch-CF

Run:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009`

Question:
Which exact decisions caused the scaled pairwise IQL candidate to fail the
combined gate, and can those states be converted into aligned branch-CF labels?

Paired trace:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009/reports/anchor_vs_scaled_pairwise_iql_combined_gate_trace.json`

Compact summary:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009/reports/anchor_vs_scaled_pairwise_iql_combined_gate_trace_compact_summary.json`

Trace result:

```text
pairs: 120
diverged_pairs: 113
divergence_rate: 94.17%
stored_divergences: 326
candidate_better_count: 41
anchor_better_count: 32
tie_count: 47
candidate_better_rate: 34.17%
mean_delta_candidate_minus_anchor: -0.0143
anchor_large_loss_count: 16
candidate_large_loss_count: 17
new_large_loss_count: 2
avoided_large_loss_count: 1
first-divergence right action families:
  discard: 108
  chii: 2
  pon: 2
  kan: 1
```

Worst-target report:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009/reports/anchor_vs_scaled_pairwise_iql_worst20_cases.json`

Targeted branch-CF:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009/data/worst20_targeted_fullmatch_branchcf_gap002`

Targeted branch-CF result:

```text
target_cases: 20
rows: 19
branch_calls: 20
branch_results: 152
skipped_missing_decision: 0
skipped_not_enough_actions: 0
skipped_no_label: 1
mean_reward_gap: 0.5974
max_reward_gap: 1.7300
preferred_family_counts:
  discard: 17
  pass: 2
avoided_family_counts:
  discard: 17
  chii: 1
  pon: 1
elapsed_seconds: 427.08
```

Decision:
Diagnostic only for now. The 19-row targeted shard is high quality and directly
comes from the failed combined-gate states, but it is too small to train a new
candidate by itself.

All-anchor-better targeted report:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009/reports/anchor_vs_scaled_pairwise_iql_anchor_better_cases.json`

All-anchor-better targeted branch-CF:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009/data/anchor_better_targeted_fullmatch_branchcf_gap002`

All-anchor-better targeted branch-CF result:

```text
target_cases: 32
rows: 29
branch_calls: 32
branch_results: 255
skipped_missing_decision: 0
skipped_not_enough_actions: 0
skipped_no_label: 3
mean_reward_gap: 0.4769
max_reward_gap: 1.7300
preferred_family_counts:
  discard: 27
  pass: 2
avoided_family_counts:
  discard: 27
  chii: 1
  pon: 1
elapsed_seconds: 655.13
```

Decision:
Keep this shard as high-signal failure-state data, but do not train from it
alone. It is larger than the worst-20 shard and covers all anchor-better cases
from the failed combined-gate trace, yet 29 rows is still not enough evidence
for a new reward-learning candidate by itself.

Interpretation:
The next useful data step is to scale this targeted failure-state branch-CF
process: include all anchor-better cases from the paired trace, new large-loss
cases, and more failed candidate windows. A future candidate should train on
the broad 1,024 sampled-vs-greedy full-match labels plus a materially larger
targeted failure-state shard, not just the broad sampled replay.

### Experiment: Independent Failure Trace And Targeted Branch-CF Expansion

Run:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009`

Question:
Does the scaled pairwise IQL candidate fail in the same way on independent
windows, and can those failures expand the high-signal targeted branch-CF data
without relying only on the original combined-gate trace?

Paired trace:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009/reports/anchor_vs_scaled_pairwise_iql_independent_564_574_584_trace.json`

Compact summary:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009/reports/anchor_vs_scaled_pairwise_iql_independent_564_574_584_compact_summary.json`

Trace result:

```text
seed windows: 564000:10, 574000:10, 584000:10
pairs: 120
diverged_pairs: 111
divergence_rate: 92.50%
candidate_better_rate: 30.83%
mean_delta_candidate_minus_anchor: -0.0123
anchor_reward_sum: -4.1130
candidate_reward_sum: -5.5860
anchor_positive_rate: 43.33%
candidate_positive_rate: 42.50%
anchor_better_cases_gap002: 34
candidate_better_cases_gap002: 30
tie_cases_gap002: 56
new_large_loss_cases_threshold_neg1: 5
```

Independent anchor-better target report:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009/reports/anchor_vs_scaled_pairwise_iql_independent_564_574_584_anchor_better_cases.json`

Independent targeted branch-CF:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009/data/independent_anchor_better_targeted_fullmatch_branchcf_gap002`

Independent targeted branch-CF result:

```text
target_cases: 34
rows: 30
branch_calls: 34
branch_results: 270
skipped_missing_decision: 0
skipped_not_enough_actions: 0
skipped_no_label: 4
mean_reward_gap: 0.3362
max_reward_gap: 2.0530
preferred_family_counts:
  chii: 2
  discard: 27
  pass: 1
avoided_family_counts:
  chii: 2
  discard: 27
  pass: 1
elapsed_seconds: 650.94
```

Decision:
Keep the independent targeted shard. It confirms the rejected candidate fails
outside the original gate windows and gives another 30 aligned full-match
branch labels. Together with the 29-row all-anchor-better shard from the
original gate, the current targeted failure-state pool has 59 non-overlapping
high-signal rows. This is still small, so any training use must be conservative
and mixed with the broad 1,024 sampled-vs-greedy full-match branch labels and
the main transition dataset.

Interpretation:
The repeated pattern is now clear: the failed candidate has broad action drift,
mostly on discard decisions, and the anchor often wins by avoiding a small
number of high-impact discard/pass/chii choices. The next candidate, if trained,
should use these targeted rows as a small failure-preservation replay, not as a
new primary objective. If that still fails, the correct next move is more
independent failure mining, not coefficient sweeps.

### Experiment: Combined Targeted Failure Replay IQL

Run:
`/root/fh-mahjong-runs/chongci-combined-targeted-failure-iql-20260617-055103`

Question:
Can the broad 1,024 sampled-vs-greedy full-match branch labels be improved by
adding the 59 targeted failure-state rows as a small replay source, while using
stronger KL anchoring to avoid the broad policy drift seen in the previous
scaled pairwise IQL candidate?

Combined pairwise data:
`/root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009/data/combined_broad_targeted_pairwise_gap002_targetedx8`

Composition:

```text
broad sampled-vs-greedy rows: 1024 x 1
original-gate targeted anchor-better rows: 29 x 8
independent targeted anchor-better rows: 30 x 8
merged pairwise rows before trainer replay: 1496
pairwise rows after trainer replay multiplier 24: 35904
mean pairwise reward gap: 0.3163
max pairwise reward gap: 2.0530
```

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
primary data:
  /root/fh-mahjong-runs/chongci-sampled-discard-scaled-20260616-083304/data/anchor2-heuristic-discard-sampled-920000-n400-npz
pairwise data:
  /root/fh-mahjong-runs/chongci-sampled-discard-fullmatch-pairwise-iql-scale-20260617-035009/data/combined_broad_targeted_pairwise_gap002_targetedx8
epochs: 1
batch_size: 512
lr: 7e-6
target_mode: mc
max_transitions: 200,000
policy_kl_weight: 0.08
pairwise_replay_multiplier: 24
pairwise_weight: 0.003
pairwise_q_weight: 0.08
pairwise_margin: 0.02
pairwise_q_margin: 0.02
MLflow run id: b9ea3ebb096b49d990889e8ba06bccd4
final loss: 0.1601
```

Candidate:
`/root/fh-mahjong-runs/chongci-combined-targeted-failure-iql-20260617-055103/checkpoints/combined_targeted_failure_iql/epoch_001.pt`

Selected-window smoke:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
max_steps_per_episode: 0
large_loss_threshold: -1.0
```

Reports:

```text
anchor:
  /root/fh-mahjong-runs/chongci-combined-targeted-failure-iql-20260617-055103/reports/smoke_selected_anchor.json
  MLflow run id: 4090d85d1271446a8e0fd72508729537
candidate:
  /root/fh-mahjong-runs/chongci-combined-targeted-failure-iql-20260617-055103/reports/smoke_selected_candidate.json
  MLflow run id: c199024ab6dc45d09b8fdf3f669fe972
```

| checkpoint | episodes | avg reward | reward sum | positive rate | large-loss count | large-loss rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| anchor | 44 | -0.0100 | -0.6600 | 50.00% | 8 | 18.18% |
| combined targeted failure IQL | 44 | -0.0700 | -3.1770 | 45.45% | 9 | 20.45% |

Decision:
Rejected. The candidate fails the selected-window smoke before the repeated
combined gate: it loses EV, positive rate, and large-loss rate versus the
promoted anchor.

Interpretation:
Adding 59 targeted failure-state rows with conservative KL was not enough to
repair the broad drift introduced by the sampled-vs-greedy pairwise objective.
The useful artifacts are the independent paired trace, the targeted branch-CF
shards, and the merged dataset builder output. Do not continue by only tuning
nearby pairwise weights. The next better direction is to increase aligned
full-match self-play data quality: either mine more independent failed windows
until targeted coverage is materially larger, or generate a fresh mixed
self-play dataset from the promoted anchor plus controlled discard exploration
and train a lower-drift candidate from that broader data.

### Experiment: Fresh Discard-Exploration Self-Play IQL

Data run:
`/root/fh-mahjong-runs/chongci-fresh-discard-explore-selfplay-20260618-031501`

Training run:
`/root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312`

Question:
Can a fresh Mortal-style operation-level dataset from the promoted anchor plus
controlled discard-only exploration improve the anchor without relying on the
failed sampled-vs-greedy pairwise objective?

Data generation:

```text
episodes: 400
start_seed: 980000
end_seed: 980399
transitions: 607,761
chunk_size: 25
elapsed_seconds: 2,822.46
dataset:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-selfplay-20260618-031501/data/anchor-anchor-heuristic-discard-sampled-980000-n400-npz
manifest:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-selfplay-20260618-031501/reports/anchor-anchor-heuristic-discard-sampled-980000-n400.manifest.json
seat 0: promoted anchor, greedy
seat 1: promoted anchor, greedy
seat 2: heuristic, auto-play baseline
seat 3: promoted anchor, top-3 sampling only on discard decisions
sample temperature: 0.85
```

Dataset diagnostics:

```text
diagnostics:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-selfplay-20260618-031501/reports/dataset_diagnostics.json
sampling diagnostics:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-selfplay-20260618-031501/reports/sampling_and_return_diagnostics.json
controlled rows by policy source:
  seat 0 anchor: 202,354
  seat 1 anchor: 202,877
  seat 3 sampled anchor: 202,530
action-family rates:
  discard: 78.70%
  pass: 11.53%
  chii: 3.97%
  pon: 3.05%
  win: 2.43%
  kan: 0.31%
sampled seat:
  sampling_applied_count: 158,885
  sampled_from_greedy_count: 4,474
  sampled_from_greedy_family: discard->discard
acting-seat mean terminal reward: -0.0142
positive rate: 46.07%
large-loss rate: 15.65%
sampled-from-greedy mean terminal reward: -0.0652
sampled-from-greedy positive rate: 42.33%
sampled-from-greedy large-loss rate: 15.89%
```

Interpretation before training:
The data is mechanically healthy: seat coverage is balanced, the sampled seat
actually diverges from greedy on discard decisions, and sampled divergences have
worse average return than the full dataset. That is useful IQL data because it
contains operation-level evidence about which sampled discard deviations were
bad.

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
primary data:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-selfplay-20260618-031501/data/anchor-anchor-heuristic-discard-sampled-980000-n400-npz
epochs: 1
batch_size: 512
lr: 5e-6
target_mode: mc
max_transitions: 300,000
bc_weight: 0.05
policy_kl_weight: 0.10
pairwise data: none
MLflow run id: 7d38061fd4cd475897d81ef1d626ef4c
final loss: 0.0900
```

Candidate:
`/root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/checkpoints/fresh_discard_explore_iql_lowdrift/epoch_001.pt`

Selected-window smoke:

```text
seed windows: 534000:6, 544001:4, 554001:1
duplicate seats: true
max_steps_per_episode: 0
large_loss_threshold: -1.0
```

Reports:

```text
anchor:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/reports/smoke_selected_anchor.json
  MLflow run id: a7323a86d5d244ce9a35ff6fe61dce6c
candidate:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/reports/smoke_selected_candidate.json
  MLflow run id: 4ff8b302b5dd4dadb6834de10bfe0e2e
```

| checkpoint | episodes | avg reward | reward sum | positive rate | large-loss count | large-loss rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| anchor | 44 | -0.0100 | -0.6600 | 50.00% | 8 | 18.18% |
| fresh discard-explore IQL | 44 | -0.0700 | -3.1770 | 45.45% | 9 | 20.45% |

Paired trace:
`/root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/reports/anchor_vs_fresh_discard_explore_iql_smoke_trace.json`

Compact trace summary:
`/root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/reports/anchor_vs_fresh_discard_explore_iql_smoke_trace_compact_summary.json`

Trace result:

```text
pairs: 44
diverged_pairs: 35
divergence_rate: 79.55%
candidate_better_rate: 29.55%
mean_delta_candidate_minus_anchor: -0.0559
anchor_better_cases_gap002: 10
candidate_better_cases_gap002: 9
tie_cases_gap002: 25
new_large_loss_cases_threshold_neg1: 1
avoided_large_loss_cases_threshold_neg1: 0
first-divergence candidate action families:
  discard: 34
  chii: 1
worst first-divergence:
  seed: 544004
  seat: 0
  anchor action: discard 7s
  candidate action: discard 3p
  anchor reward: 1.0560
  candidate reward: -0.4210
  reward delta: -1.4770
```

Targeted anchor-better report:
`/root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/reports/anchor_vs_fresh_discard_explore_iql_anchor_better_cases.json`

Targeted branch-CF:
`/root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/data/fresh_iql_anchor_better_targeted_fullmatch_branchcf_gap002`

Targeted branch-CF result:

```text
target_cases: 10
rows: 8
branch_calls: 10
branch_results: 86
skipped_missing_decision: 0
skipped_not_enough_actions: 0
skipped_no_label: 2
mean_reward_gap: 0.4084
max_reward_gap: 1.3200
preferred_family_counts:
  discard: 8
avoided_family_counts:
  discard: 8
elapsed_seconds: 184.84
```

Q-ranking diagnostics:

```text
paired-trace Q diagnostics, anchor:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/reports/paired_trace_q_rank_anchor.json
paired-trace Q diagnostics, rejected candidate:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/reports/paired_trace_q_rank_candidate.json
targeted branch-CF calibration, anchor:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/reports/targeted_branchcf_q_rank_anchor.json
targeted branch-CF calibration, rejected candidate:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/reports/targeted_branchcf_q_rank_candidate.json
```

| diagnostic set | checkpoint | rows | policy preferred rate | Q preferred rate | Q weighted preferred rate | key result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| paired first-divergence labels | anchor | 19 | 52.63% | 57.89% | 53.21% | weak Q separation; 42.11% Q misrank |
| paired first-divergence labels | fresh discard-explore IQL | 19 | 47.37% | 57.89% | 52.93% | policy worse than anchor on the same labels |
| targeted branch-CF rows | anchor | 8 | 37.50% | 50.00% | 65.26% | exact-state Q is not reliable enough |
| targeted branch-CF rows | fresh discard-explore IQL | 8 | 50.00% | 50.00% | 65.26% | exact-state Q remains at 50% preferred rate |

Decision:
Rejected. The fresh data was good enough to train from, but this low-drift IQL
candidate failed the selected-window smoke and therefore should not run the
larger repeated combined gate.

Interpretation:
The failure is again broad discard drift: the candidate diverges on 79.55% of
smoke pairs and almost all first divergences are discard choices. The sampled
exploration dataset is still useful, but one epoch of IQL from it moved the
policy into a bad region. The targeted branch-CF follow-up confirms the losing
states are real high-gap discard decisions, but only produced 8 rows. That is
diagnostic data, not enough for another training candidate by itself.

The Q-ranking diagnostics add one stronger constraint: the current Q head should
not be trusted to drive policy improvement yet. On paired first-divergence labels
it only ranks the preferred action above the avoided action 57.89% of the time,
and on the exact targeted branch-CF rows it is 50.00% for both the anchor and
the rejected candidate. That means the next learning step should first improve
Q/value ranking under a frozen or tightly anchored policy path, then re-run
these diagnostics before any new gameplay gate.

Next direction:
Do not run another nearby IQL or pairwise-weight sweep. The better next
implementation is a constrained value-learning pass: freeze or strongly anchor
the policy-selection path, learn Q/value from the fresh exploration data, and
validate whether the learned Q ranks anchor actions above candidate actions on
the smoke trace and the 8 targeted branch-CF rows before allowing policy
improvement.

### Experiment: Critic-Only Q-Ranking Diagnostic

Run:
`/root/fh-mahjong-runs/chongci-critic-only-qrank-20260617-231030`

Question:
Can we improve the Q/value ranking signal from the fresh discard-exploration
dataset and exact targeted branch-CF rows without changing the served policy?

Implementation change:
Added `--critic-only` to `fh_mahjong_ai.scripts.train_iql`. This freezes every
parameter except `q_head.*` and `value_head.*`, and rejects `--resume` because
optimizer parameter groups differ. The local and remote regression test
`test_train_iql_critic_only_freezes_policy_path` verifies non-critic tensors
stay unchanged while the Q head moves.

First attempt:
`/root/fh-mahjong-runs/chongci-critic-only-qrank-20260617-230522`

This failed before training because MLflow server was not listening on
`127.0.0.1:5000`. The remote MLflow server was then started with a SQLite backend
under `/root/fh-mahjong-runs/mlflow`.

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
primary data:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-selfplay-20260618-031501/data/anchor-anchor-heuristic-discard-sampled-980000-n400-npz
pairwise Q-only data:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/data/fresh_iql_anchor_better_targeted_fullmatch_branchcf_gap002
epochs: 1
batch_size: 512
lr: 2e-5
target_mode: mc
max_transitions: 300,000
policy_weight: 0.0
bc_weight: 0.0
q_weight: 1.0
value_weight: 1.0
pairwise_replay_multiplier: 128
pairwise_q_weight: 0.20
pairwise_q_margin: 0.02
pairwise_reward_delta_weight: 0.5
pairwise_reward_delta_margin_scale: 0.1
critic_only: true
MLflow run id: 1638dd93059b4ff18b021504fbb9c386
final loss: 0.0300
```

Checkpoint:
`/root/fh-mahjong-runs/chongci-critic-only-qrank-20260617-231030/checkpoints/fresh_discard_explore_critic_only_qrank/epoch_001.pt`

Checkpoint audit:

```text
non_critic_changed: 0
critic_unchanged: 0
```

This confirms the policy-selection path did not move. This checkpoint must not
be treated as a playable policy promotion.

Diagnostics:

```text
paired trace report:
  /root/fh-mahjong-runs/chongci-critic-only-qrank-20260617-231030/reports/paired_trace_q_rank_critic_only.json
targeted branch-CF report:
  /root/fh-mahjong-runs/chongci-critic-only-qrank-20260617-231030/reports/targeted_branchcf_q_rank_critic_only.json
```

| diagnostic set | rows | policy preferred rate | Q preferred rate | Q weighted preferred rate | Q misrank rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| paired first-divergence labels | 19 | 52.63% | 63.16% | 79.65% | 36.84% |
| targeted branch-CF rows | 8 | 37.50% | 100.00% | 100.00% | 0.00% |

Decision:
Accepted as a diagnostic success only. The critic-only pass proves the Q/value
head can learn the known bad discard divergences without policy drift. It does
not prove a stronger playing policy yet, because action selection is still the
unchanged promoted anchor policy.

Next direction:
Use this critic checkpoint to create a constrained policy-improvement step:
derive policy targets only where the critic has exact-state support, keep KL to
the promoted anchor, and require the same Q-ranking preflight before any
duplicate-seat smoke. Do not run a gameplay gate directly on this checkpoint;
its policy is intentionally unchanged.

### Experiment: Policy-Head-Only Exact Branch-CF Candidates

Question:
Can the diagnostic critic be converted into a small playable policy improvement
by updating only `policy_head.*` from the 8 exact targeted branch-CF rows, while
keeping encoder, Q, and value fixed?

Implementation change:
Added `--policy-head-only` to `fh_mahjong_ai.scripts.train_iql`. This freezes
the encoder, value head, Q head, and risk heads, leaving only the served policy
logits trainable. The regression test
`test_train_iql_policy_head_only_freezes_encoder_and_critics` verifies that only
`policy_head.*` tensors change.

Candidate A:
`/root/fh-mahjong-runs/chongci-policy-head-exactcf-20260618-000001`

Checkpoint:
`/root/fh-mahjong-runs/chongci-policy-head-exactcf-20260618-000001/checkpoints/policy_head_exactcf_kl_anchor/epoch_001.pt`

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-critic-only-qrank-20260617-231030/checkpoints/fresh_discard_explore_critic_only_qrank/epoch_001.pt
policy_head_only: true
lr: 5e-5
pairwise rows: 8 exact targeted branch-CF rows repeated 256x
pairwise_weight: 0.05
policy_kl_weight: 0.20
normal replay rows: 1,024, with q/value/policy/bc weights set to 0.0
MLflow run id: dbae90f9e1c8474283cd7e4dd588f3ae
final loss: 0.3845
checkpoint audit:
  non_policy_changed: 0
  policy_unchanged: 0
```

Candidate A preflight:

| diagnostic set | rows | policy preferred rate | Q preferred rate | Q misrank rate |
| --- | ---: | ---: | ---: | ---: |
| paired first-divergence labels | 19 | 42.11% | 63.16% | 36.84% |
| targeted branch-CF rows | 8 | 50.00% | 100.00% | 0.00% |

Decision:
Rejected before duplicate-seat smoke. Candidate A improved the exact targeted
branch-CF policy rate from 37.50% to 50.00%, but broad paired-trace policy
preference regressed from the anchor/critic-only 52.63% to 42.11%. That violates
the preflight rule: do not spend a live gate on a candidate whose small exact
update already harms the known failed-smoke first-divergence labels.

Candidate B:
`/root/fh-mahjong-runs/chongci-policy-head-exactcf-strongkl-20260618-000002`

Checkpoint:
`/root/fh-mahjong-runs/chongci-policy-head-exactcf-strongkl-20260618-000002/checkpoints/policy_head_exactcf_strongkl/epoch_001.pt`

Training:

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-critic-only-qrank-20260617-231030/checkpoints/fresh_discard_explore_critic_only_qrank/epoch_001.pt
policy_head_only: true
lr: 1e-5
pairwise rows: 8 exact targeted branch-CF rows repeated 128x
pairwise_weight: 0.02
policy_kl_weight: 1.00
normal replay rows: 1,024, with q/value/policy/bc weights set to 0.0
MLflow run id: 331f245a1d724759a0070d14f1863634
final loss: 0.1848
checkpoint audit:
  non_policy_changed: 0
  policy_unchanged: 0
```

Candidate B preflight:

| diagnostic set | rows | policy preferred rate | Q preferred rate | Q misrank rate |
| --- | ---: | ---: | ---: | ---: |
| paired first-divergence labels | 19 | 52.63% | 63.16% | 36.84% |
| targeted branch-CF rows | 8 | 37.50% | 100.00% | 0.00% |

Decision:
Rejected before duplicate-seat smoke. Candidate B preserved the broad
paired-trace policy rate, but it did not improve the exact targeted branch-CF
policy rate. It is effectively a no-op for the intended correction.

Interpretation:
The constrained policy-head path is directionally correct but data-limited. The
critic can fit the 8 exact branch-CF labels, but the policy head cannot use that
tiny shard safely: either it moves enough to improve exact rows and regresses
broad paired labels, or it preserves broad labels and makes no exact correction.

Next direction:
Stop tuning these two weights. Generate a larger exact-state branch-CF policy
dataset from more failed windows before another policy update. The minimum
useful next dataset should contain enough same-state discard-vs-discard rows to
split into train/holdout and require both:

```text
1. train exact branch-CF policy preferred rate improves
2. held-out exact branch-CF policy preferred rate improves
3. paired failed-smoke policy preferred rate does not regress
```

Only after that should a duplicate-seat smoke run be allowed.

### Experiment: Expanded Exact-State Branch-CF Data Generation

Run:
`/root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003`

Question:
Can we mine enough additional same-state failure windows from the rejected fresh
discard-exploration IQL candidate to support a real train/holdout exact branch-CF
policy dataset?

Step started:
An expanded tensor-bearing paired trace is running between:

```text
left / anchor:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
right / rejected candidate:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/checkpoints/fresh_discard_explore_iql_lowdrift/epoch_001.pt
seed windows:
  534000:20
  544000:20
  554000:20
seats: 0, 1, 2, 3
total paired seed/seat cases: 240
match_mode: chongci
max_steps_per_episode: 0
large_loss_threshold: -1.0
include_observation_arrays: true
include_action_scores: true
max_divergences: 1
report:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/reports/anchor_vs_fresh_iql_expanded_trace.json
log:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/logs/paired_trace.log
pid:
  184432
```

Current status:
The process is running on remote WSL. The child Python process is actively using
CPU; no final report has been written yet.

Partial-40 branch-CF probe:

```text
snapshot:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/reports/anchor_vs_fresh_iql_expanded_trace_partial40_snapshot.json
case_source: worst_reward_delta_cases
output:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/worst_delta_partial40_targeted_branchcf_gap002
target_cases: 15
rows: 7
branch_calls: 15
branch_results: 148
skipped_no_label: 8
mean_reward_gap: 0.1631
max_reward_gap: 0.5080
preferred_family_counts:
  discard: 7
avoided_family_counts:
  discard: 7
```

Interpretation:
The partial trace is producing the right kind of data, but 7 exact rows is still
too small for another policy-head update. Keep this shard as reusable auxiliary
evidence, but wait for more paired-trace coverage before training.

Partial-60 worst-delta branch-CF:

```text
snapshot:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/reports/anchor_vs_fresh_iql_expanded_trace_partial60_snapshot.json
case_source: worst_reward_delta_cases
output:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/worst_delta_partial60_targeted_branchcf_gap002
target_cases: 21
rows: 11
branch_calls: 21
branch_results: 200
skipped_no_label: 10
mean_reward_gap: 0.2289
max_reward_gap: 0.5080
preferred_family_counts:
  discard: 11
avoided_family_counts:
  discard: 11
```

Partial-80 candidate-large-loss branch-CF:

```text
snapshot:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/reports/anchor_vs_fresh_iql_expanded_trace_partial80_snapshot.json
case_source: candidate_large_loss_cases
output:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/candidate_large_loss_partial80_targeted_branchcf_gap002
target_cases: 12
rows: 7
branch_calls: 12
branch_results: 118
skipped_no_label: 5
mean_reward_gap: 0.2014
max_reward_gap: 0.3380
controlled_seats:
  0, 1
preferred_family_counts:
  discard: 7
avoided_family_counts:
  discard: 7
```

Interpretation:
Both probes validate the data source, but they remain below the threshold for
another policy-head candidate. The correct next move is still to let the paired
trace continue, then generate a larger deduplicated exact-state shard from the
full or a later partial report.

Partial-120 all-first-divergence branch-CF:

```text
snapshot:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/reports/anchor_vs_fresh_iql_expanded_trace_partial120_snapshot.json
case_source: pairs
output:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_partial120_targeted_branchcf_gap002
target_cases: 94
rows: 65
branch_calls: 94
branch_results: 918
skipped_no_label: 29
mean_reward_gap: 0.1897
max_reward_gap: 1.1800
controlled_seats:
  0, 1
preferred_family_counts:
  discard: 65
avoided_family_counts:
  discard: 65
split:
  train rows: 52
  holdout rows: 13
  split seed: 20260618
train:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_partial120_targeted_branchcf_gap002_split/train
holdout:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_partial120_targeted_branchcf_gap002_split/holdout
```

Baseline calibration on the split using the critic-only checkpoint:

```text
checkpoint:
  /root/fh-mahjong-runs/chongci-critic-only-qrank-20260617-231030/checkpoints/fresh_discard_explore_critic_only_qrank/epoch_001.pt
train report:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/reports/all_first_divergence_partial120_train_calibration_critic_only.json
holdout report:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/reports/all_first_divergence_partial120_holdout_calibration_critic_only.json
train policy preferred rate: 50.00%
train Q preferred rate: 51.92%
holdout policy preferred rate: 61.54%
holdout Q preferred rate: 61.54%
```

Policy-head candidate C:
`/root/fh-mahjong-runs/chongci-policy-head-allcf-partial120-20260618-001200`

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-critic-only-qrank-20260617-231030/checkpoints/fresh_discard_explore_critic_only_qrank/epoch_001.pt
train pairwise data:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_partial120_targeted_branchcf_gap002_split/train
policy_head_only: true
lr: 2e-5
pairwise_replay_multiplier: 64
pairwise_weight: 0.03
policy_kl_weight: 0.50
MLflow run id: 1fd98a849b2c4dce98fe7d8093f3d5f4
checkpoint:
  /root/fh-mahjong-runs/chongci-policy-head-allcf-partial120-20260618-001200/checkpoints/policy_head_allcf_partial120_kl/epoch_001.pt
checkpoint audit:
  non_policy_changed: 0
  policy_unchanged: 0
```

Candidate C preflight:

| diagnostic set | baseline policy preferred | candidate policy preferred | Q preferred |
| --- | ---: | ---: | ---: |
| exact branch-CF train | 50.00% | 51.92% | 51.92% |
| exact branch-CF holdout | 61.54% | 61.54% | 61.54% |
| original failed-smoke paired labels | 52.63% | 57.89% | 63.16% |

Decision:
Rejected before duplicate-seat smoke. It improved train and original paired
labels but did not improve exact branch-CF holdout.

Policy-head candidate D:
`/root/fh-mahjong-runs/chongci-policy-head-allcf-partial120-strong-20260618-001500`

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-critic-only-qrank-20260617-231030/checkpoints/fresh_discard_explore_critic_only_qrank/epoch_001.pt
policy_head_only: true
lr: 3e-5
pairwise_replay_multiplier: 96
pairwise_weight: 0.05
policy_kl_weight: 0.30
MLflow run id: 0165c4704869466688d9530332a01dc5
checkpoint:
  /root/fh-mahjong-runs/chongci-policy-head-allcf-partial120-strong-20260618-001500/checkpoints/policy_head_allcf_partial120_strong/epoch_001.pt
checkpoint audit:
  non_policy_changed: 0
  policy_unchanged: 0
```

Candidate D preflight:

| diagnostic set | baseline policy preferred | candidate policy preferred | Q preferred |
| --- | ---: | ---: | ---: |
| exact branch-CF train | 50.00% | 51.92% | 51.92% |
| exact branch-CF holdout | 61.54% | 61.54% | 61.54% |
| original failed-smoke paired labels | 52.63% | 52.63% | 63.16% |

Decision:
Rejected before duplicate-seat smoke. Stronger policy-head movement did not
improve holdout and lost the original paired-label gain from candidate C.

Interpretation:
The 65-row partial-120 exact branch-CF shard is useful, but the current
policy-head-only recipe is not yet converting it into a generalizing policy
improvement. The Q head is also weak on the broader all-first-divergence exact
labels: only 51.92% train and 61.54% holdout preferred rate. This means the
next better step is not another policy coefficient tweak; first improve or
refresh the critic on the broader all-first-divergence exact data, then retry
policy only if Q-ranking improves on both train and holdout.

Critic-only candidate E:
`/root/fh-mahjong-runs/chongci-critic-allcf-partial120-20260618-001800`

```text
init checkpoint:
  /root/fh-mahjong-runs/chongci-critic-only-qrank-20260617-231030/checkpoints/fresh_discard_explore_critic_only_qrank/epoch_001.pt
critic_only: true
train pairwise data:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_partial120_targeted_branchcf_gap002_split/train
lr: 3e-5
pairwise_replay_multiplier: 128
pairwise_q_weight: 0.40
MLflow run id: 97f90919293d40cdaaa80032c57bd3ed
checkpoint:
  /root/fh-mahjong-runs/chongci-critic-allcf-partial120-20260618-001800/checkpoints/critic_allcf_partial120/epoch_001.pt
checkpoint audit:
  non_critic_changed: 0
  critic_unchanged: 0
```

Candidate E preflight:

| diagnostic set | baseline Q preferred | candidate Q preferred |
| --- | ---: | ---: |
| exact branch-CF train | 51.92% | 100.00% |
| exact branch-CF holdout | 61.54% | 53.85% |
| original failed-smoke paired labels | 63.16% | 63.16% |

Decision:
Rejected as a critic update. It overfits the 52-row train split and worsens
holdout. Do not use it for policy training or serving.

Partial-180 status:

```text
pairs: 180 / 240
divergence_rate: 78.89%
reward_delta_mean: -0.0482
worst_reward_delta_cases: 46
candidate_large_loss_cases: 31
high_risk_cases: 20
snapshot:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/reports/anchor_vs_fresh_iql_expanded_trace_partial180_snapshot.json
new branch-CF job:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_partial180_targeted_branchcf_gap002
pid:
  187076
```

Full paired trace result:

```text
report:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/reports/anchor_vs_fresh_iql_expanded_trace.json
pairs: 240
complete: true
divergence_rate: 79.17%
candidate_better_rate: 24.17%
mean_delta_candidate_minus_anchor: -0.0394
worst_reward_delta_cases: 59
candidate_large_loss_cases: 40
high_risk_cases: 20
```

Full all-first-divergence branch-CF:

```text
case_source: pairs
output:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_full240_targeted_branchcf_gap002
target_cases: 190
rows: 135
branch_calls: 190
branch_results: 1882
skipped_no_label: 55
mean_reward_gap: 0.2153
max_reward_gap: 1.3200
controlled_seats:
  0, 1, 2, 3
preferred_family_counts:
  discard: 135
avoided_family_counts:
  discard: 135
split:
  train rows: 108
  holdout rows: 27
  split seed: 20260618
train:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_full240_targeted_branchcf_gap002_split/train
holdout:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_full240_targeted_branchcf_gap002_split/holdout
```

Baseline full-split calibration:

```text
checkpoint:
  /root/fh-mahjong-runs/chongci-critic-only-qrank-20260617-231030/checkpoints/fresh_discard_explore_critic_only_qrank/epoch_001.pt
train policy preferred: 53.70%
train Q preferred: 56.48%
holdout policy preferred: 62.96%
holdout Q preferred: 59.26%
```

Critic-only candidate F:
`/root/fh-mahjong-runs/chongci-critic-allcf-full240-20260618-003000`

```text
critic_only: true
train pairwise data:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_full240_targeted_branchcf_gap002_split/train
lr: 5e-6
pairwise_replay_multiplier: 32
pairwise_q_weight: 0.05
MLflow run id: 9bdc6d939ae843bda3e65e520e1bbe80
checkpoint:
  /root/fh-mahjong-runs/chongci-critic-allcf-full240-20260618-003000/checkpoints/critic_allcf_full240_lowdose/epoch_001.pt
checkpoint audit:
  non_critic_changed: 0
  critic_unchanged: 0
```

Candidate F preflight:

| diagnostic set | baseline Q preferred | candidate Q preferred |
| --- | ---: | ---: |
| exact branch-CF train | 56.48% | 77.78% |
| exact branch-CF holdout | 59.26% | 59.26% |
| original failed-smoke paired labels | 63.16% | 63.16% |

Decision:
Rejected as a critic update. It improves train Q but only ties holdout Q.

Policy-head candidate G:
`/root/fh-mahjong-runs/chongci-policy-head-allcf-full240-20260618-003300`

```text
policy_head_only: true
train pairwise data:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_full240_targeted_branchcf_gap002_split/train
lr: 1e-5
pairwise_replay_multiplier: 64
pairwise_weight: 0.03
policy_kl_weight: 0.50
MLflow run id: 68c914c75245484b8040c013565fbe79
checkpoint:
  /root/fh-mahjong-runs/chongci-policy-head-allcf-full240-20260618-003300/checkpoints/policy_head_allcf_full240_kl/epoch_001.pt
checkpoint audit:
  non_policy_changed: 0
  policy_unchanged: 0
```

Candidate G preflight:

| diagnostic set | baseline policy preferred | candidate policy preferred |
| --- | ---: | ---: |
| exact branch-CF train | 53.70% | 54.63% |
| exact branch-CF holdout | 62.96% | 62.96% |
| original failed-smoke paired labels | 52.63% | 57.89% |

Decision:
Rejected before duplicate-seat smoke. It improves train and the original
failed-smoke paired labels, but the exact branch-CF holdout only ties baseline.

Current conclusion:
The expanded data loop worked: it produced a real 135-row exact same-state
discard branch-CF dataset. The current head-only recipes still do not generalize
past holdout. This suggests the next useful change is not another coefficient
sweep; it is either a better split/coverage strategy from more independent seeds
or a different supervised objective that uses the full legal-branch reward
distribution rather than only preferred-vs-avoided pair labels.

### Experiment: action-conditioned EV on full240 exact branch-CF

Run:
`/root/fh-mahjong-runs/chongci-action-ev-full240-20260618-234627`

Question:
Can a separate `EV(state, action)` predictor learn the exact same-state
discard reward gaps better than the previous policy-head and Q-head pairwise
updates?

Data:

```text
train:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_full240_targeted_branchcf_gap002_split/train
holdout:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_full240_targeted_branchcf_gap002_split/holdout
source paired trace:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/reports/anchor_vs_fresh_iql_expanded_trace.json
```

Training:

```text
script:
  fh_mahjong_ai.scripts.train_global_ev
mode:
  --action-conditioned
  --branch-cf-action-targets
epochs: 4
steps_per_epoch: 40
batch_size: 64
lr: 3e-4
pairwise_weight: 0.25
reward_gap_weight: 1.0
reward_gap_margin_scale: 0.1
MLflow run id: 02731be9102d4bad835502abfd079964
checkpoint:
  /root/fh-mahjong-runs/chongci-action-ev-full240-20260618-234627/checkpoints/action_ev_full240_gaprank/epoch_004.pt
```

Exact branch-CF calibration:

| split | rows | preferred rate | reward-gap weighted preferred rate |
| --- | ---: | ---: | ---: |
| train | 108 | 94.44% | 95.13% |
| holdout | 27 | 66.67% | 81.84% |

Training report:

```text
expanded train transitions: 216
internal validation MAE: 0.1869
internal validation correlation: -0.0945
constant baseline MAE: 0.1213
```

First-divergence paired-trace preflight:

```text
report:
  /root/fh-mahjong-runs/chongci-action-ev-full240-20260618-234627/reports/paired_trace_action_ev_preflight.json
scoreable divergences: 190
sign accuracy: 47.86%
harmful count: 59
harmful predicted harmful rate: 38.98%
guard margin 0.0000:
  allowed: 101
  harmful block rate: 38.98%
  actual allowed delta sum: -6.3810
guard margin -0.0200:
  allowed: 111
  harmful block rate: 33.90%
  actual allowed delta sum: -6.1830
guard margin -0.0500:
  allowed: 119
  harmful block rate: 32.20%
  actual allowed delta sum: -6.0940
```

Decision:
Rejected for guarded serving and promotion. The exact branch-CF holdout result
is better than the previous head-only tie, especially on reward-gap weighted
ranking, but paired-trace preflight still allows a negative total reward delta.

Interpretation:
The action-conditioned EV direction is more aligned than scalar risk stacking,
but the current 135-row full240 exact branch-CF shard is not enough to make a
reliable first-divergence guard. Keep the tooling and the data. Do not run live
guarded duplicate-seat evaluation from this checkpoint. The next useful step is
to expand independent same-state branch coverage or train from a fuller legal
branch reward distribution rather than only one preferred/avoided pair per
state.

Next when complete:
Build a larger independent exact-state action-EV dataset from new seed windows,
prioritizing candidate-loss first divergences and high-gap discard alternatives.
Keep train/holdout split by seed window, not just row count, then rerun the same
paired-trace preflight before any guarded serving attempt.

### Experiment: independent exact-state branch-CF data generation

Run:
`/root/fh-mahjong-runs/chongci-independent-exactcf-data-20260618-234957`

Question:
Can new independent seed windows produce a larger same-state discard branch-CF
dataset that generalizes better than the full240 shard?

Data-generation plan:

```text
anchor:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
candidate:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/checkpoints/fresh_discard_explore_iql_lowdrift/epoch_001.pt
seed windows:
  564000:20
  574000:20
  584000:20
seats:
  0, 1, 2, 3
paired trace pairs:
  240 planned
paired trace report:
  /root/fh-mahjong-runs/chongci-independent-exactcf-data-20260618-234957/reports/anchor_vs_fresh_iql_independent_trace.json
targeted branch-CF output:
  /root/fh-mahjong-runs/chongci-independent-exactcf-data-20260618-234957/data/all_first_divergence_independent_targeted_branchcf_gap002
```

Branch-CF labeling settings:

```text
case_source: pairs
action_family: discard
min_reward_gap: 0.02
max_branch_actions: 0
match_mode: chongci
max_steps_per_episode: 0
```

Current status:
Started on remote WSL. The checkpoints loaded successfully and paired-trace
progress reached `1/240` pairs with no configuration error.

Partial status update:

```text
elapsed: about 6 minutes
paired-trace progress: 24/240
partial report written at: 20/240
partial divergence rate: 50.00%
partial candidate better rate: 10.00%
partial mean candidate-anchor reward delta: -0.0122
process state: active Python child, about 105% CPU
```

Final result:

```text
paired trace pairs: 240
divergence rate: 72.92%
candidate better rate: 21.67%
same reward rate: 55.83%
mean candidate-anchor reward delta: -0.004925
scoreable branch target cases: 175
targeted exact branch-CF rows: 106
branch calls: 175
branch results: 1720
skipped no label: 69
mean branch reward gap: 0.2143
max branch reward gap: 1.3320
preferred family: discard only
avoided family: discard only
```

Diagnostics:

```text
report:
  /root/fh-mahjong-runs/chongci-independent-exactcf-data-20260618-234957/reports/targeted_branch_cf_diagnostics.json
data:
  /root/fh-mahjong-runs/chongci-independent-exactcf-data-20260618-234957/data/all_first_divergence_independent_targeted_branchcf_gap002
split:
  /root/fh-mahjong-runs/chongci-independent-exactcf-data-20260618-234957/data/all_first_divergence_independent_targeted_branchcf_gap002_split
train split:
  75 rows, episode_index < 584000
holdout split:
  31 rows, episode_index >= 584000
left policy preferred match rate: 5.66%
right policy preferred match rate: 7.55%
```

Interpretation:
This is a useful independent branch-label dataset. The low left/right preferred
match rates mean neither original policy usually chose the exact best branch,
so the value is in the counterfactual labels rather than imitation of either
checkpoint.

### Experiment: combined old+independent action-EV

Run:
`/root/fh-mahjong-runs/chongci-action-ev-combined-exactcf-20260619-004613`

Question:
Does adding the independent exact-state branch-CF rows improve action-EV
generalization across both the old full240 holdout and the new held-out
`584xxx` seed window?

Training:

```text
old train:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_full240_targeted_branchcf_gap002_split/train
new train:
  /root/fh-mahjong-runs/chongci-independent-exactcf-data-20260618-234957/data/all_first_divergence_independent_targeted_branchcf_gap002_split/train
epochs: 4
steps_per_epoch: 60
batch_size: 64
lr: 2e-4
pairwise_weight: 0.25
reward_gap_weight: 1.0
reward_gap_margin_scale: 0.1
MLflow run id: dfd6564836684550a8158c24b3089d2d
checkpoint:
  /root/fh-mahjong-runs/chongci-action-ev-combined-exactcf-20260619-004613/checkpoints/action_ev_combined_gaprank/epoch_004.pt
```

Exact branch-CF calibration:

| split | rows | preferred rate | reward-gap weighted preferred rate |
| --- | ---: | ---: | ---: |
| old train | 108 | 96.30% | 97.11% |
| old holdout | 27 | 48.15% | 52.78% |
| new train | 75 | 97.33% | 94.00% |
| new holdout | 31 | 54.84% | 57.92% |

Paired-trace preflight:

| report | scoreable divergences | sign accuracy | harmful recall | guard margin 0 allowed delta |
| --- | ---: | ---: | ---: | ---: |
| old trace | 190 | 49.57% | 50.85% | -2.6380 |
| new trace | 175 | 50.94% | 57.41% | 1.4470 |

Decision:
Rejected for guarded serving and promotion. The new-trace guard preflight is
positive, but the old-trace guard preflight is still negative and branch-CF
holdout rates are weak. This checkpoint is diagnostic only.

Interpretation:
Adding independent rows helped on the new paired trace but did not generalize
back to the old trace or produce strong held-out branch ranking. The next move
should not be another coefficient sweep. Use the combined branch-CF datasets to
train a less overfit objective or generate a larger multi-window shard before
any policy/serving attempt.

### Experiment: tail-candidate independent exact-state branch-CF data generation

Run:
`/root/fh-mahjong-runs/chongci-tail-independent-exactcf-data-20260619-004908`

Question:
Can a different rejected/diverse candidate policy expose different same-state
discard branch labels than the fresh discard-explore candidate, improving
multi-window coverage without tuning the action-EV objective again?

Data-generation plan:

```text
anchor:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
candidate:
  /root/fh-mahjong-runs/chongci-tail-constrained-balanced2-20260607-031444/checkpoints/tail_balanced_highrisk2_gap010/epoch_001.pt
seed windows:
  594000:20
  604000:20
  614000:20
seats:
  0, 1, 2, 3
paired trace pairs:
  240 planned
paired trace report:
  /root/fh-mahjong-runs/chongci-tail-independent-exactcf-data-20260619-004908/reports/anchor_vs_tail_balanced_independent_trace.json
targeted branch-CF output:
  /root/fh-mahjong-runs/chongci-tail-independent-exactcf-data-20260619-004908/data/all_first_divergence_tail_targeted_branchcf_gap002
```

Branch-CF labeling settings:

```text
case_source: pairs
action_family: discard
min_reward_gap: 0.02
max_branch_actions: 0
match_mode: chongci
max_steps_per_episode: 0
```

Current status:
Started on remote WSL. Both checkpoints loaded successfully and paired-trace
progress reached `1/240` pairs with no configuration error.

Partial status update:

```text
elapsed: about 4 minutes
partial report written at: 20/240
partial divergence rate: 90.00%
partial candidate better rate: 30.00%
partial same reward rate: 25.00%
partial mean candidate-anchor reward delta: 0.00725
candidate large-loss cases: 0
```

Second partial status update:

```text
elapsed: about 30 minutes
paired-trace log progress: 152/240
partial report written at: 140/240
partial divergence rate: 89.29%
partial candidate better rate: 25.71%
partial same reward rate: 36.43%
partial mean candidate-anchor reward delta: -0.03636
candidate large-loss cases: 0
```

Final result:

```text
paired trace pairs: 240
divergence rate: 87.08%
candidate better rate: 27.92%
same reward rate: 36.67%
mean candidate-anchor reward delta: -0.02836
scoreable branch target cases: 209
targeted exact branch-CF rows: 139
branch calls: 209
branch results: 2073
skipped no label: 70
mean branch reward gap: 0.2410
max branch reward gap: 2.0970
preferred family: discard only
avoided family: discard only
```

Diagnostics:

```text
report:
  /root/fh-mahjong-runs/chongci-tail-independent-exactcf-data-20260619-004908/reports/targeted_branch_cf_diagnostics.json
data:
  /root/fh-mahjong-runs/chongci-tail-independent-exactcf-data-20260619-004908/data/all_first_divergence_tail_targeted_branchcf_gap002
split:
  /root/fh-mahjong-runs/chongci-tail-independent-exactcf-data-20260619-004908/data/all_first_divergence_tail_targeted_branchcf_gap002_split
train split:
  89 rows, episode_index < 614000
holdout split:
  50 rows, episode_index >= 614000
left policy preferred match rate: 9.35%
right policy preferred match rate: 11.51%
```

Interpretation:
This is a strong complementary shard. It has higher divergence than the fresh
candidate trace, a larger reward-gap maximum, and a low original-policy
preferred-match rate. It should be kept as data, but by itself it still does
not justify a serving/guard model.

### Experiment: multi-window action-EV from old+fresh+tail exact branch-CF

Run:
`/root/fh-mahjong-runs/chongci-action-ev-multiwindow-exactcf-20260619-014619`

Question:
Does combining the old full240 shard, the fresh independent shard, and the tail
independent shard make the action-conditioned EV predictor robust enough across
multiple held-out seed windows and paired-trace preflights?

Training:

```text
old train:
  /root/fh-mahjong-runs/chongci-expanded-exactcf-data-20260618-000003/data/all_first_divergence_full240_targeted_branchcf_gap002_split/train
fresh train:
  /root/fh-mahjong-runs/chongci-independent-exactcf-data-20260618-234957/data/all_first_divergence_independent_targeted_branchcf_gap002_split/train
tail train:
  /root/fh-mahjong-runs/chongci-tail-independent-exactcf-data-20260619-004908/data/all_first_divergence_tail_targeted_branchcf_gap002_split/train
epochs: 4
steps_per_epoch: 80
batch_size: 64
lr: 1.5e-4
pairwise_weight: 0.25
reward_gap_weight: 1.0
reward_gap_margin_scale: 0.1
MLflow run id: fbeb83d6669441658269904f75c7d000
checkpoint:
  /root/fh-mahjong-runs/chongci-action-ev-multiwindow-exactcf-20260619-014619/checkpoints/action_ev_multiwindow_gaprank/epoch_004.pt
```

Exact branch-CF calibration:

| split | rows | preferred rate | reward-gap weighted preferred rate |
| --- | ---: | ---: | ---: |
| old train | 108 | 94.44% | 96.92% |
| old holdout | 27 | 59.26% | 62.37% |
| fresh train | 75 | 92.00% | 89.69% |
| fresh holdout | 31 | 58.06% | 65.24% |
| tail train | 89 | 94.38% | 95.50% |
| tail holdout | 50 | 78.00% | 88.45% |

Paired-trace preflight:

| report | scoreable divergences | sign accuracy | harmful recall | guard margin 0 allowed delta |
| --- | ---: | ---: | ---: | ---: |
| old trace | 190 | 40.17% | 37.29% | -8.0270 |
| fresh trace | 175 | 61.32% | 61.11% | 3.4810 |
| tail trace | 209 | 44.74% | 41.18% | -7.1680 |

Decision:
Rejected for guarded serving and promotion. Held-out branch-CF ranking improved
on the tail shard and modestly on old/fresh holdouts, but full paired-trace
preflight still fails on old and tail traces.

Interpretation:
The same-state branch labels are useful and reusable, but action-EV pairwise
training still does not predict full first-divergence reward deltas reliably.
This is not fixed by another nearby coefficient or epoch sweep. The next
direction should change the objective or data representation: train on
trace-level outcomes for all first-divergence rows, add richer context/history
features to the action-EV scorer, or move these labels into a conservative
policy update only after a stronger preflight objective is available.

### Tooling: paired-trace action-EV dataset builder

Local code added:

```text
ai/src/fh_mahjong_ai/paired_trace_action_ev.py
ai/src/fh_mahjong_ai/scripts/build_paired_trace_action_ev_data.py
ai/tests/test_paired_trace_action_ev.py
```

Purpose:
Convert tensor-bearing paired-trace first-divergence outcome deltas into the
same branch-action EV NPZ schema consumed by `train_global_ev
--branch-cf-action-targets`. Unlike exact branch-CF best/worst labels, this
uses actual anchor-vs-candidate final match reward differences from paired
traces.

Validation:

```text
local:
  uv run --project ai pytest ai/tests/test_paired_trace_action_ev.py ai/tests/test_global_ev.py ai/tests/test_global_ev_diagnostics.py
  16 passed
remote:
  /root/.local/bin/uv run --project ai pytest ai/tests/test_paired_trace_action_ev.py ai/tests/test_global_ev.py ai/tests/test_global_ev_diagnostics.py
  16 passed
```

### Experiment: paired-trace delta action-EV

Data run:
`/root/fh-mahjong-runs/chongci-paired-trace-action-ev-data-20260619-020620`

Question:
Can direct first-divergence paired-trace reward deltas train an action-EV model
that passes paired-trace preflight better than same-state branch-CF best/worst
training?

Built paired-trace action-EV rows:

| source trace | rows after gap >= 0.02 | train rows | holdout rows |
| --- | ---: | ---: | ---: |
| old | 95 | 68 | 27 |
| fresh | 84 | 59 | 25 |
| tail | 127 | 88 | 39 |

Training run:
`/root/fh-mahjong-runs/chongci-action-ev-pairedtrace-delta-20260619-020647`

Training:

```text
old train:
  /root/fh-mahjong-runs/chongci-paired-trace-action-ev-data-20260619-020620/data/old_paired_trace_action_ev_gap002_split/train
fresh train:
  /root/fh-mahjong-runs/chongci-paired-trace-action-ev-data-20260619-020620/data/fresh_paired_trace_action_ev_gap002_split/train
tail train:
  /root/fh-mahjong-runs/chongci-paired-trace-action-ev-data-20260619-020620/data/tail_paired_trace_action_ev_gap002_split/train
epochs: 4
steps_per_epoch: 80
batch_size: 64
lr: 1.5e-4
pairwise_weight: 0.25
reward_gap_weight: 1.0
reward_gap_margin_scale: 0.1
MLflow run id: 8d3da5b491eb4a5886a9cc78d2190b69
checkpoint:
  /root/fh-mahjong-runs/chongci-action-ev-pairedtrace-delta-20260619-020647/checkpoints/action_ev_pairedtrace_delta/epoch_004.pt
```

Internal validation:

```text
validation MAE: 0.9311
validation RMSE: 1.1446
validation correlation: 0.5033
constant baseline MAE: 0.9584
```

Full-trace preflight:

| report | scoreable divergences | sign accuracy | harmful recall | guard margin 0 allowed delta |
| --- | ---: | ---: | ---: | ---: |
| old trace | 190 | 49.57% | 52.54% | 1.1160 |
| fresh trace | 175 | 60.38% | 64.81% | 2.6290 |
| tail trace | 209 | 55.26% | 60.00% | 2.3530 |

Holdout-only preflight:

| report | scoreable divergences | sign accuracy | harmful recall | guard margin 0 allowed delta |
| --- | ---: | ---: | ---: | ---: |
| old holdout | 64 | 29.03% | 23.08% | -1.5920 |
| fresh holdout | 61 | 54.55% | 50.00% | -1.1260 |
| tail holdout | 69 | 48.98% | 58.06% | -1.9470 |

Decision:
Rejected for guarded serving and promotion. The full-trace preflight looked
positive, but holdout-only preflight is negative on all three source traces.

Interpretation:
The direct paired-trace objective is closer to the desired full reward signal
than branch-CF best/worst labels, but the current dataset/model still overfits
seed-window-specific signals. Keep the builder and data. Next useful move is
not threshold tuning; it is either more independent trace windows with
holdout-first evaluation, or a model/objective that uses richer trajectory
context rather than only the first-divergence visible observation.

### Implementation: trajectory-context paired-trace action-EV

Question:
Can paired-trace action-EV use visible trajectory history before the first
divergence, rather than only the first-divergence observation, so the scorer has
enough context to generalize across seed windows?

Code changes:

```text
ai/src/fh_mahjong_ai/paired_trace.py
ai/src/fh_mahjong_ai/paired_trace_action_ev.py
ai/src/fh_mahjong_ai/global_ev_diagnostics.py
ai/src/fh_mahjong_ai/scripts/build_paired_trace_action_ev_data.py
ai/src/fh_mahjong_ai/scripts/action_ev_branch_cf_calibration.py
ai/src/fh_mahjong_ai/scripts/global_ev_diagnostics.py
ai/tests/test_paired_trace.py
ai/tests/test_paired_trace_action_ev.py
ai/tests/test_global_ev_diagnostics.py
```

Added `pre_divergence_context` to paired-trace reports. It records only visible,
reward-free context:

- divergence step and decision index,
- prefix action-family rates,
- previous action-family one-hot,
- visible scalar deltas from the first decision to the divergence.

The context vector is appended by
`fh-mj-build-paired-trace-action-ev-data --include-trajectory-context`. This
widens paired-trace action-EV scalar inputs from 58 to 81.

Validation:

```text
local:
  uv run --project ai pytest \
    ai/tests/test_paired_trace.py \
    ai/tests/test_paired_trace_action_ev.py \
    ai/tests/test_global_ev.py \
    ai/tests/test_global_ev_diagnostics.py \
    ai/tests/test_iql.py::test_train_iql_critic_only_freezes_policy_path \
    ai/tests/test_iql.py::test_train_iql_policy_head_only_freezes_encoder_and_critics \
    ai/tests/test_paired_trace_q_diagnostics.py \
    ai/tests/test_branch_cf_calibration.py
  41 passed

remote:
  /root/.local/bin/uv run --project ai pytest \
    ai/tests/test_paired_trace.py \
    ai/tests/test_paired_trace_action_ev.py \
    ai/tests/test_global_ev.py \
    ai/tests/test_global_ev_diagnostics.py \
    ai/tests/test_iql.py::test_train_iql_critic_only_freezes_policy_path \
    ai/tests/test_iql.py::test_train_iql_policy_head_only_freezes_encoder_and_critics \
    ai/tests/test_paired_trace_q_diagnostics.py \
    ai/tests/test_branch_cf_calibration.py
  41 passed
```

### Experiment: context paired-trace tail smoke

Data run:
`/root/fh-mahjong-runs/chongci-context-pairedtrace-tail-20260619-022149`

Policies:

```text
anchor:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
candidate:
  /root/fh-mahjong-runs/chongci-tail-constrained-balanced2-20260607-031444/checkpoints/tail_balanced_highrisk2_gap010/epoch_001.pt
```

Trace command:

```text
fh-mj-paired-trace
  --seed-window 624000:20
  --seed-window 634000:20
  --seed-window 644000:20
  --seats 0 1 2 3
  --match-mode chongci
  --max-steps-per-episode 0
  --include-observation-arrays
  --max-divergences 1
```

Status:
The full trace is still running. At the 80-pair partial report, it had reached
seat 1 and covered seeds `624000..644019`.

Partial report at 80 pairs:

| metric | value |
| --- | ---: |
| pairs | 80 |
| candidate reward delta sum | 2.8420 |
| candidate reward delta mean | 0.0355 |
| negative delta rate | 30.00% |
| positive delta rate | 38.75% |

Context check:

```text
first 20 pairs: context available in 19/20 pairs
partial shard scalar shape: (33, 81)
context_available_sum: 33.0
```

Partial60 training shard:

```text
source report:
  /root/fh-mahjong-runs/chongci-context-pairedtrace-tail-20260619-022149/reports/anchor_vs_tail_context_trace.json
data:
  /root/fh-mahjong-runs/chongci-context-pairedtrace-tail-20260619-022149/data/tail_context_paired_trace_action_ev_gap002_partial60
split:
  train: episode_index < 644000
  holdout: episode_index >= 644000
rows:
  total 33
  train 21
  holdout 12
scalar width:
  81
```

Important implementation issue found:
The first split script copied the original manifest without changing top-level
`transitions`, `shard_size`, or shard row counts. `read_transition_arrays`
therefore allocated 33 rows for a 21-row train shard and left uninitialized
garbage rows, which produced huge invalid action ids and CUDA embedding-index
asserts. The split manifest was rebuilt with matching top-level and shard row
counts. After the fix, expanded action ids loaded as `0..203`.

Training run:
`/root/fh-mahjong-runs/chongci-action-ev-context-tail-partial60-fixed-20260619-023632`

Training:

```text
train data:
  /root/fh-mahjong-runs/chongci-context-pairedtrace-tail-20260619-022149/data/tail_context_paired_trace_action_ev_gap002_partial60_split/train
epochs: 4
steps_per_epoch: 40
batch_size: 32
lr: 1.5e-4
pairwise_weight: 0.25
reward_gap_weight: 1.0
reward_gap_margin_scale: 0.1
MLflow run id: f24e434cd5ae475799dc5ca16ad35b0f
checkpoint:
  /root/fh-mahjong-runs/chongci-action-ev-context-tail-partial60-fixed-20260619-023632/checkpoints/action_ev_context_tail_partial60/epoch_004.pt
```

Internal validation:

```text
validation MAE: 0.6030
validation RMSE: 0.7373
validation correlation: 0.3643
constant baseline MAE: 0.8229
pair preference accuracy: 75.00%
```

Preflight:

| report | scoreable divergences | sign accuracy | harmful recall | guard margin 0 allowed delta |
| --- | ---: | ---: | ---: | ---: |
| partial report, 80 pairs | 69 | 65.45% | 58.33% | 4.9330 |
| holdout `seed >= 644000`, 20 pairs | 15 | 53.85% | 50.00% | 0.1790 |

Decision:
Diagnostic only. Do not promote or serve. The result is too small and includes
only a one-seat holdout window, but it is useful because the holdout-only
preflight is no longer immediately negative and the context-bearing data path
works end to end.

Next:
Wait for the full 240-pair trace to finish. Rebuild the context shard and split
by independent seed windows before training a real context action-EV model.
Then compare holdout-only preflight to the previous no-context paired-trace
delta model. If holdout still fails, the next change should be more data
diversity or a stronger sequential model, not threshold tuning.

### Experiment: context paired-trace tail full240

Data run:
`/root/fh-mahjong-runs/chongci-context-pairedtrace-tail-20260619-022149`

Final trace summary:

| metric | value |
| --- | ---: |
| pairs | 240 |
| seats | 0, 1, 2, 3 |
| seed windows | `624000:20`, `634000:20`, `644000:20` |
| divergence rate | 88.33% |
| candidate better rate | 33.33% |
| reward delta mean | 0.0323 |
| reward delta sum | 7.7550 |
| negative delta rate | 29.58% |
| positive delta rate | 33.33% |

Full context shard:

```text
data:
  /root/fh-mahjong-runs/chongci-context-pairedtrace-tail-20260619-022149/data/tail_context_paired_trace_action_ev_gap002_full240
split:
  train: episode_index < 644000
  holdout: episode_index >= 644000
rows:
  total 128
  train 82
  holdout 46
scalar width:
  81
expanded action ids:
  train 0..203
  holdout 0..202
```

Training run:
`/root/fh-mahjong-runs/chongci-action-ev-context-tail-full240-20260620-004119`

Training:

```text
train data:
  /root/fh-mahjong-runs/chongci-context-pairedtrace-tail-20260619-022149/data/tail_context_paired_trace_action_ev_gap002_full240_split/train
epochs: 4
steps_per_epoch: 80
batch_size: 64
lr: 1.5e-4
pairwise_weight: 0.25
reward_gap_weight: 1.0
reward_gap_margin_scale: 0.1
MLflow run id: 56eba63c914e483780b9a24bb464d19c
```

Training behavior:

| epoch | train MAE | validation MAE | validation corr | pair pref |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.4490 | 0.5793 | 0.6757 | 50.00% |
| 2 | 0.2005 | 0.6241 | 0.5418 | 57.14% |
| 3 | 0.1357 | 0.7790 | 0.4288 | 57.14% |
| 4 | 0.0962 | 0.8444 | 0.3787 | 57.14% |

The validation curve overfits after epoch 1, but paired-trace preflight is the
actual diagnostic.

Same-report preflight:

| checkpoint | report | scoreable divergences | sign accuracy | harmful recall | guard margin 0 allowed delta |
| --- | --- | ---: | ---: | ---: | ---: |
| epoch 1 | train windows | 141 | 70.71% | 69.57% | 8.2810 |
| epoch 1 | holdout `seed >= 644000` | 71 | 34.62% | 48.00% | -0.0510 |
| epoch 1 | full trace | 212 | 58.28% | 61.97% | 8.2300 |
| epoch 4 | train windows | 141 | 86.87% | 95.65% | 12.6310 |
| epoch 4 | holdout `seed >= 644000` | 71 | 48.08% | 68.00% | 1.6510 |
| epoch 4 | full trace | 212 | 73.51% | 85.92% | 14.2820 |

Legacy zero-context cross-report preflight with epoch 4:

These older reports do not contain `pre_divergence_context`, so diagnostics pad
the 23 context scalars with zeros. This is useful as a robustness check but not
a fair context-vs-context comparison.

| report | subset | scoreable divergences | sign accuracy | harmful recall | guard margin 0 allowed delta |
| --- | --- | ---: | ---: | ---: | ---: |
| old | holdout | 64 | 38.71% | 46.15% | -2.6700 |
| old | full | 190 | 53.85% | 61.02% | -3.7980 |
| fresh | holdout | 61 | 45.45% | 37.50% | -3.1730 |
| fresh | full | 175 | 49.06% | 46.30% | -2.5910 |
| tail | holdout | 69 | 51.02% | 51.61% | -3.4150 |
| tail | full | 209 | 55.92% | 63.53% | -3.8540 |

Decision:
Rejected for guarded serving and promotion. The context-bearing same-report
holdout is promising relative to the previous no-context all-holdout failure,
but cross-report zero-context preflight is still negative. The correct next
step is to generate additional context-bearing paired traces from different
candidates/windows and train on that combined context data, not to tune margins
on this single trace.

### Experiment: context paired-trace fresh data generation

Data run:
`/root/fh-mahjong-runs/chongci-context-pairedtrace-fresh-20260620-004411`

Question:
Can a second context-bearing paired trace from a different candidate reduce the
single-trace overfitting seen in the tail-only context action-EV model?

Policies:

```text
anchor:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
candidate:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/checkpoints/fresh_discard_explore_iql_lowdrift/epoch_001.pt
```

Trace command:

```text
fh-mj-paired-trace
  --seed-window 654000:20
  --seed-window 664000:20
  --seed-window 674000:20
  --seats 0 1 2 3
  --match-mode chongci
  --max-steps-per-episode 0
  --include-observation-arrays
  --max-divergences 1
```

Status:
Running on remote WSL. At the first 20-pair partial report:

| metric | value |
| --- | ---: |
| pairs | 20 |
| reward delta sum | -1.6090 |
| reward delta mean | -0.0805 |
| negative delta rate | 30.00% |
| positive delta rate | 20.00% |
| zero delta rate | 50.00% |

Next:
Wait for 240/240 pairs, then build a context shard and train a combined
tail+fresh context action-EV model with holdout-only preflight on both context
reports.

### Experiment: combined tail+fresh context action-EV

Fresh context trace final summary:

Run:
`/root/fh-mahjong-runs/chongci-context-pairedtrace-fresh-20260620-004411`

| metric | value |
| --- | ---: |
| pairs | 240 |
| seats | 0, 1, 2, 3 |
| seed windows | `654000:20`, `664000:20`, `674000:20` |
| divergence rate | 75.00% |
| candidate better rate | 22.50% |
| reward delta mean | -0.0178 |
| reward delta sum | -4.2730 |
| negative delta rate | 24.58% |
| positive delta rate | 22.50% |

Fresh context shard:

```text
data:
  /root/fh-mahjong-runs/chongci-context-pairedtrace-fresh-20260620-004411/data/fresh_context_paired_trace_action_ev_gap002_full240
split:
  train: episode_index < 674000
  holdout: episode_index >= 674000
rows:
  total 98
  train 63
  holdout 35
scalar width:
  81
expanded action ids:
  train 0..203
  holdout 0..197
```

Training run:
`/root/fh-mahjong-runs/chongci-action-ev-context-tail-fresh-20260620-012543`

Training:

```text
train data:
  /root/fh-mahjong-runs/chongci-context-pairedtrace-tail-20260619-022149/data/tail_context_paired_trace_action_ev_gap002_full240_split/train
  /root/fh-mahjong-runs/chongci-context-pairedtrace-fresh-20260620-004411/data/fresh_context_paired_trace_action_ev_gap002_full240_split/train
epochs: 4
steps_per_epoch: 100
batch_size: 64
lr: 1.5e-4
pairwise_weight: 0.25
reward_gap_weight: 1.0
reward_gap_margin_scale: 0.1
MLflow run id: 79e996b21faf49ebaafe480fddc190d5
```

Internal validation:

| epoch | train MAE | validation MAE | validation corr | pair pref |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.4835 | 0.6158 | 0.4867 | 47.62% |
| 2 | 0.2534 | 0.7716 | 0.4313 | 47.62% |
| 3 | 0.1744 | 0.8177 | 0.3531 | 52.38% |
| 4 | 0.1377 | 0.8180 | 0.3166 | 57.14% |

Preflight:

| checkpoint | report | scoreable divergences | sign accuracy | harmful recall | guard margin 0 allowed delta |
| --- | --- | ---: | ---: | ---: | ---: |
| epoch 1 | tail train | 141 | 60.61% | 54.35% | 4.0900 |
| epoch 1 | tail holdout | 71 | 46.15% | 64.00% | 0.0790 |
| epoch 1 | tail full | 212 | 55.63% | 57.75% | 4.1690 |
| epoch 1 | fresh train | 118 | 63.51% | 60.00% | 1.1830 |
| epoch 1 | fresh holdout | 62 | 48.72% | 63.16% | -1.4760 |
| epoch 1 | fresh full | 180 | 58.41% | 61.02% | -0.2930 |
| epoch 4 | tail train | 141 | 80.81% | 86.96% | 10.8210 |
| epoch 4 | tail holdout | 71 | 38.46% | 56.00% | 0.8550 |
| epoch 4 | tail full | 212 | 66.23% | 76.06% | 11.6760 |
| epoch 4 | fresh train | 118 | 75.68% | 75.00% | 4.9870 |
| epoch 4 | fresh holdout | 62 | 41.03% | 42.11% | -3.0000 |
| epoch 4 | fresh full | 180 | 63.72% | 64.41% | 1.9870 |

Decision:
Rejected for guarded serving and promotion. Combining tail+fresh context data
improved train/full reports but still failed the fresh holdout. This is another
seed-window generalization failure, not a margin problem.

Interpretation:
The visible trajectory context is useful infrastructure, but the current
action-EV objective still overfits source windows/candidates. Continue with
data diversity and stronger holdout protocols. Do not tune guard thresholds or
nearby loss coefficients on this branch.

### Experiment: context paired-trace fresh2 data generation

Data run:
`/root/fh-mahjong-runs/chongci-context-pairedtrace-fresh2-20260620-012813`

Question:
The combined tail+fresh context model failed the fresh holdout, so can more
fresh-candidate context data from independent seed windows improve source
coverage without changing loss coefficients?

Policies:

```text
anchor:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
candidate:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/checkpoints/fresh_discard_explore_iql_lowdrift/epoch_001.pt
```

Trace command:

```text
fh-mj-paired-trace
  --seed-window 684000:20
  --seed-window 694000:20
  --seed-window 704000:20
  --seats 0 1 2 3
  --match-mode chongci
  --max-steps-per-episode 0
  --include-observation-arrays
  --max-divergences 1
```

Status:
Running on remote WSL. Startup was valid: both checkpoints loaded and the first
pair completed.

Final trace summary:

| metric | value |
| --- | ---: |
| pairs | 240 |
| seats | 0, 1, 2, 3 |
| seed windows | `684000:20`, `694000:20`, `704000:20` |
| divergence rate | 81.25% |
| candidate better rate | 28.33% |
| reward delta mean | 0.0149 |
| reward delta sum | 3.5780 |
| negative delta rate | 20.42% |
| positive delta rate | 28.33% |

Fresh2 context shard:

```text
data:
  /root/fh-mahjong-runs/chongci-context-pairedtrace-fresh2-20260620-012813/data/fresh2_context_paired_trace_action_ev_gap002_full240
split:
  train: episode_index < 704000
  holdout: episode_index >= 704000
rows:
  total 94
  train 58
  holdout 36
scalar width:
  81
expanded action ids:
  train 0..188
  holdout 0..192
```

### Experiment: combined tail+fresh+fresh2 context action-EV

Training run:
`/root/fh-mahjong-runs/chongci-action-ev-context-tail-fresh-fresh2-20260620-021122`

Question:
Does adding another independent fresh-candidate context trace fix the fresh
holdout failure without changing thresholds or loss coefficients?

Training:

```text
train data:
  /root/fh-mahjong-runs/chongci-context-pairedtrace-tail-20260619-022149/data/tail_context_paired_trace_action_ev_gap002_full240_split/train
  /root/fh-mahjong-runs/chongci-context-pairedtrace-fresh-20260620-004411/data/fresh_context_paired_trace_action_ev_gap002_full240_split/train
  /root/fh-mahjong-runs/chongci-context-pairedtrace-fresh2-20260620-012813/data/fresh2_context_paired_trace_action_ev_gap002_full240_split/train
epochs: 4
steps_per_epoch: 120
batch_size: 64
lr: 1.5e-4
pairwise_weight: 0.25
reward_gap_weight: 1.0
reward_gap_margin_scale: 0.1
MLflow run id: a8d94f6d85c84af4aa3e6c654fda9b0c
```

Internal validation:

| epoch | train MAE | validation MAE | validation corr | pair pref |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.5444 | 0.6057 | 0.6132 | 55.56% |
| 2 | 0.3410 | 0.5915 | 0.6434 | 40.74% |
| 3 | 0.2400 | 0.6672 | 0.5486 | 40.74% |
| 4 | 0.1784 | 0.6684 | 0.5276 | 62.96% |

Preflight:

| checkpoint | report | scoreable divergences | sign accuracy | harmful recall | guard margin 0 allowed delta |
| --- | --- | ---: | ---: | ---: | ---: |
| epoch 1 | tail holdout | 71 | 44.23% | 52.00% | -0.5140 |
| epoch 1 | fresh holdout | 62 | 51.28% | 57.89% | -1.0600 |
| epoch 1 | fresh2 holdout | 67 | 52.50% | 63.16% | 1.4550 |
| epoch 2 | tail holdout | 71 | 42.31% | 32.00% | -0.4720 |
| epoch 2 | fresh holdout | 62 | 51.28% | 63.16% | -0.4150 |
| epoch 2 | fresh2 holdout | 67 | 57.50% | 63.16% | 0.7380 |
| epoch 4 | tail holdout | 71 | 30.77% | 36.00% | -0.9280 |
| epoch 4 | fresh holdout | 62 | 41.03% | 42.11% | -0.8970 |
| epoch 4 | fresh2 holdout | 67 | 62.50% | 63.16% | 2.3530 |

Decision:
Rejected for guarded serving and promotion. Adding a second fresh context trace
helped the fresh2 holdout but did not fix tail/fresh holdout generalization.
Every candidate epoch has at least two negative holdout preflights.

Interpretation:
This is now enough evidence to stop this action-EV recipe. The failure is not
just missing one more fresh trace or a bad epoch choice. The next move should
change the objective/model shape, for example a direct pairwise reward-delta
model over both divergent actions plus context, or a proper sequential/history
encoder. Do not continue simple scalar, threshold, epoch, or coefficient sweeps
on this branch.

### Experiment: Direct Pairwise Reward-Delta Predictor

Run:
`/root/fh-mahjong-runs/chongci-pairwise-delta-tail-fresh-fresh2-20260620-021914`

Question:
Does predicting `candidate_reward - anchor_reward` directly from the shared
first-divergence observation, visible trajectory context, and both divergent
action ids generalize better than assigning absolute action EV to each action?

Data:

```text
train reports:
  tail context train
  fresh context train
  fresh2 context train
holdout reports:
  tail context holdout
  fresh context holdout
  fresh2 context holdout
rows: 387
scalar width: 81
target: final Chongci reward delta
```

Training:

```text
model: scalar/context MLP + left/right/action-delta embeddings
epochs: 4
steps_per_epoch: 120
batch_size: 64
lr: 1.5e-4
weight_decay: 1e-4
device: cuda
```

Preflight, margin 0:

| checkpoint | tail holdout | fresh holdout | fresh2 holdout | decision |
| --- | ---: | ---: | ---: | --- |
| epoch 1 | 2.964 | -0.333 | 0.423 | reject |
| epoch 2 | 0.847 | -0.763 | 0.202 | reject |
| epoch 3 | 0.789 | -0.643 | -0.205 | reject |
| epoch 4 | 1.092 | -0.552 | -0.047 | reject |

Decision:
Rejected for serving, guarded evaluation, and promotion. The direct
reward-delta objective improved the full-report picture, but every epoch still
failed at least one independent holdout.

Interpretation:
This is a better diagnostic shape than action-EV for paired traces, but the
first-divergence scalar/action MLP still overfits source windows. Do not promote
from full-report gains. The next useful direction is real visible history input
or more source-diverse full-match paired traces, not threshold tuning.

### Experiment: Direct Pairwise Reward-Delta With Nonzero Gap Filter

Run:
`/root/fh-mahjong-runs/chongci-pairwise-delta-gap002-tail-fresh-fresh2-20260620-022139`

Question:
Is the holdout failure mainly caused by noisy zero/near-zero reward-delta rows?

Data:
Same train/eval reports as the direct pairwise reward-delta experiment, but
training excluded rows with `abs(candidate_reward - anchor_reward) < 0.02`.

Training:

```text
rows: 203
model: same scalar/action pairwise-delta MLP
epochs: 4
steps_per_epoch: 120
batch_size: 64
lr: 1.5e-4
device: cuda
```

Preflight, margin 0:

| checkpoint | tail holdout | fresh holdout | fresh2 holdout | decision |
| --- | ---: | ---: | ---: | --- |
| epoch 1 | 4.706 | -2.535 | 0.738 | reject |
| epoch 2 | 0.497 | -2.335 | 0.082 | reject |
| epoch 3 | 0.087 | -2.348 | -0.397 | reject |
| epoch 4 | 0.308 | -2.348 | -0.732 | reject |

Decision:
Rejected. Filtering small-gap rows made the fresh holdout materially worse.

Interpretation:
The blocker is not just label noise from near-zero deltas. Stop this scalar/action
pairwise MLP family unless the data/model shape changes.

### Experiment: Visible Sequence Pairwise-Delta Smoke

Run:
`/root/fh-mahjong-runs/chongci-sequence-smoke-20260620-023204`

Question:
Can paired-trace reports store compact visible pre-divergence operation history,
and can a sequence-aware reward-delta model consume it?

Data:

```text
tail candidate:
  train seeds 624000:2
  holdout seeds 644000:2
fresh candidate:
  train seeds 654000:2
  holdout seeds 674000:2
fresh2 candidate:
  train seeds 684000:2
  holdout seeds 704000:2
seats: 0, 1, 2, 3
full pairs: 48
train divergence rows: 21
```

Implementation:
- Added `pre_divergence_sequence` to paired-trace reports.
- Added `PairwiseSequenceDeltaNet`, a small GRU over visible prefix rows plus
  the existing scalar/action pairwise-delta inputs.
- Added `fh-mj-train-pairwise-delta --sequence-model`.

Training:

```text
epochs: 4
steps_per_epoch: 80
batch_size: 32
lr: 1.5e-4
device: cuda
```

Result:

| report | scoreable divergences | sign accuracy | guard margin 0 allowed delta |
| --- | ---: | ---: | ---: |
| tail holdout | 8 | 25.00% | 0.184 |
| fresh holdout | 8 | 20.00% | -1.170 |
| fresh2 holdout | 6 | 50.00% | 0.024 |

Decision:
Infrastructure validated, model rejected. This was intentionally a small smoke,
not a promotion candidate.

Interpretation:
The next aligned step is a full source-diverse sequence paired-trace refresh,
then source-heldout sequence training. Do not read the tiny smoke as evidence
that sequence history works or fails for strength; it only proves the data and
training path are mechanically usable.

### Experiment: Full Source-Diverse Sequence Pairwise-Delta

Run:
`/root/fh-mahjong-runs/chongci-sequence-full-20260620-025953`

Question:
Does a source-diverse full paired-trace refresh with compact visible
pre-divergence sequences let the sequence pairwise-delta model pass independent
source-heldout preflight?

Data:

```text
anchor:
  /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt
tail candidate:
  /root/fh-mahjong-runs/chongci-tail-constrained-balanced2-20260607-031444/checkpoints/tail_balanced_highrisk2_gap010/epoch_001.pt
fresh/fresh2 candidate:
  /root/fh-mahjong-runs/chongci-fresh-discard-explore-iql-20260618-040312/checkpoints/fresh_discard_explore_iql_lowdrift/epoch_001.pt
tail seeds:
  624000:20, 634000:20, 644000:20
fresh seeds:
  654000:20, 664000:20, 674000:20
fresh2 seeds:
  684000:20, 694000:20, 704000:20
seats:
  0, 1, 2, 3
max_steps_per_episode:
  20000
```

Training plan:

```text
split:
  tail holdout: seed >= 644000
  fresh holdout: seed >= 674000
  fresh2 holdout: seed >= 704000
model:
  PairwiseSequenceDeltaNet
epochs:
  4
steps_per_epoch:
  160
batch_size:
  64
lr:
  1.0e-4
```

Evaluation:
The pipeline will write per-epoch holdout preflight reports under
`reports/preflight_epoch*_*.json` and aggregate them in
`reports/epoch_preflight_summary.json`.

Trace result:

| report | pairs | divergence rate | candidate better rate | mean delta |
| --- | ---: | ---: | ---: | ---: |
| tail full | 240 | 88.33% | 33.33% | 0.0323 |
| fresh full | 240 | 75.00% | 25.42% | -0.0178 |
| fresh2 full | 240 | 81.25% | 28.33% | 0.0149 |

Training result:

| epoch | train MAE | validation MAE | validation corr |
| --- | ---: | ---: | ---: |
| 1 | 0.1573 | 0.1930 | 0.2761 |
| 2 | 0.1407 | 0.2138 | 0.2670 |
| 3 | 0.1106 | 0.2526 | 0.1978 |
| 4 | 0.0823 | 0.2836 | 0.1753 |

Source-heldout preflight, margin 0:

| checkpoint | tail holdout | fresh holdout | fresh2 holdout | decision |
| --- | ---: | ---: | ---: | --- |
| epoch 1 | 4.193 | -2.509 | 0.256 | reject |
| epoch 2 | 2.533 | -1.093 | 1.184 | reject |
| epoch 3 | 3.364 | -0.131 | 0.770 | reject |
| epoch 4 | 2.846 | 0.016 | 0.768 | borderline |

Epoch 4 was the first checkpoint with all source-heldout margin-0 deltas
non-negative, but the fresh holdout was only `0.016` and failed at margin
`0.05` (`-0.378`). This is not strong enough for live guarded evaluation.

### Experiment: Independent Sequence Pairwise-Delta Preflight

Run:
`/root/fh-mahjong-runs/chongci-sequence-independent-preflight-20260620-035316`

Question:
Does the borderline epoch-4 sequence scorer from
`chongci-sequence-full-20260620-025953` hold up on new independent seed windows
without retraining?

Data:

```text
scored checkpoint:
  /root/fh-mahjong-runs/chongci-sequence-full-20260620-025953/checkpoints/pairwise_sequence_delta_full/epoch_004.pt
tail independent:
  714000:10, all seats
fresh independent:
  724000:10, all seats
fresh2 independent:
  734000:10, all seats
```

Trace result:

| report | pairs | divergence rate | mean delta |
| --- | ---: | ---: | ---: |
| tail independent | 40 | 95.00% | 0.0562 |
| fresh independent | 40 | 67.50% | 0.0617 |
| fresh2 independent | 40 | 75.00% | -0.0035 |

Preflight, epoch 4, margin 0:

| report | scoreable divergences | sign accuracy | allowed delta | allowed count |
| --- | ---: | ---: | ---: | ---: |
| tail independent | 38 | 38.46% | -0.225 | 18 |
| fresh independent | 27 | 47.62% | 1.561 | 17 |
| fresh2 independent | 30 | 50.00% | 1.411 | 17 |

Decision:
Rejected for guard, serving, and promotion. The full source-heldout result was
not stable on new independent seeds.

Interpretation:
Visible sequence context is useful infrastructure, and it improved over the
earlier scalar/action pairwise-delta failures, but the current scorer still
overfits source windows. Do not run duplicate-seat guarded evaluation from this
scorer. The next aligned direction is not another threshold sweep; either expand
independent source diversity before training or change the scorer objective to
optimize worst-source/heldout robustness directly.

### Experiment: Source-Balanced Worst-Source Sequence Pairwise-Delta

Run:
`/root/fh-mahjong-runs/chongci-sequence-worstsource-20260620-202912`

Question:
Can broader source diversity plus a worst-source training objective make the
sequence reward-delta scorer robust enough to pass original holdouts and a new
independent preflight?

Implementation:
- Added source ids to pairwise-delta arrays.
- Added `fh-mj-train-pairwise-delta --source-balanced-batches`.
- Added `--worst-source-loss-weight`, which adds the maximum per-source batch
  MSE to the normal MSE objective.

Training data:

```text
original source train reports:
  tail train
  fresh train
  fresh2 train
additional source-diversity reports:
  tail independent 714000:10
  fresh independent 724000:10
  fresh2 independent 734000:10
rows:
  482
```

Training:

```text
model: PairwiseSequenceDeltaNet
source_balanced_batches: true
worst_source_loss_weight: 1.0
epochs: 4
steps_per_epoch: 180
batch_size: 96
lr: 1.0e-4
```

Training metrics:

| epoch | train MAE | validation MAE | validation corr |
| --- | ---: | ---: | ---: |
| 1 | 0.2085 | 0.2611 | 0.1122 |
| 2 | 0.1803 | 0.2639 | 0.0646 |
| 3 | 0.1576 | 0.2660 | 0.1262 |
| 4 | 0.1403 | 0.2899 | 0.0380 |

New independent2 preflight data:

```text
tail independent2: 744000:10, all seats
fresh independent2: 754000:10, all seats
fresh2 independent2: 764000:10, all seats
```

Independent2 trace result:

| report | pairs | divergence rate | mean delta |
| --- | ---: | ---: | ---: |
| tail independent2 | 40 | 87.50% | 0.0794 |
| fresh independent2 | 40 | 75.00% | 0.0194 |
| fresh2 independent2 | 40 | 77.50% | 0.0267 |

Preflight, margin 0:

| checkpoint | tail holdout | fresh holdout | fresh2 holdout | tail independent2 | fresh independent2 | fresh2 independent2 | decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| epoch 1 | 1.986 | -1.273 | -0.390 | 1.914 | 0.114 | 1.115 | reject |
| epoch 2 | 2.799 | -2.698 | -0.253 | 0.706 | 0.150 | 1.280 | reject |
| epoch 3 | 3.691 | -2.686 | -0.101 | 0.611 | 0.149 | 0.961 | reject |
| epoch 4 | 2.928 | -2.331 | -0.522 | 0.718 | -0.367 | 1.032 | reject |

Decision:
Rejected. The robust objective fixed the prior tail-independent failure but
regressed the original fresh/fresh2 source holdouts and did not stay positive on
fresh independent2.

Interpretation:
Do not sweep `worst_source_loss_weight` as the next move. The failure moved
between sources instead of disappearing, which means the scorer still lacks a
stable generalization signal. The useful artifacts remain: source ids,
source-balanced batches, worst-source objective support, and the independent2
reports. The next aligned direction is to build a larger multi-source training
set first, then use a source-heldout protocol where one whole seed window/source
is held out during model selection.

### Experiment: Larger Multi-Source Sequence Dataset

Run:
`/root/fh-mahjong-runs/chongci-sequence-multisource-20260621-000804`

Question:
Does a larger multi-source sequence dataset reduce source-window overfitting
enough for the sequence reward-delta scorer to pass whole-source heldout
preflight?

Training sources:

```text
existing sources:
  /root/fh-mahjong-runs/chongci-sequence-full-20260620-025953 train splits
  /root/fh-mahjong-runs/chongci-sequence-independent-preflight-20260620-035316 independent reports
  /root/fh-mahjong-runs/chongci-sequence-worstsource-20260620-202912 independent2 reports
new train sources:
  tail 774000:10
  tail 784000:10
  fresh 794000:10
  fresh 804000:10
  fresh2 814000:10
  fresh2 824000:10
new whole-source holdouts:
  tail 834000:10
  fresh 844000:10
  fresh2 854000:10
```

Training plan:

```text
model: PairwiseSequenceDeltaNet
source_balanced_batches: true
worst_source_loss_weight: 1.0
epochs: 4
steps_per_epoch: 220
batch_size: 120
lr: 1.0e-4
selection: reject unless all base and new whole-source holdouts are non-negative
```

Current status:
Started on remote WSL. Nine paired-trace jobs are running in parallel to build
six new train sources plus three new whole-source holdouts.

Decision:
Still running.

Interpretation:
This is not another threshold or coefficient sweep. It tests the current
hypothesis that the scorer needs broader source diversity and whole-source
heldout model selection before any live duplicate-seat gate.

### Experiment: Placement Reward-Shaping Pipeline Validation (bounded)

Run:
`/root/fh-mahjong-runs/placement-compare-20260621-012708`

Question:
Does the new `--reward-shaping placement` path (rank-based placement returns
instead of raw net-score returns) run end to end on the real Go bridge, and does
a small from-scratch comparison show any raw-vs-placement difference?

Data:
200 Chongci self-play episodes (seat 1 random, others heuristic), seed 800000,
single window of mixed self-play shards (`shards/`).

Training:
Two IQL runs on identical data, from scratch, 3 epochs, batch 256, lr 1e-4, cuda:
- raw MC return target (`iql-raw/epoch_003.pt`)
- `--reward-shaping placement` MC return target (`iql-placement/epoch_003.pt`)
During training the placement run showed the expected smaller value-target
magnitude (q≈0.033, value≈0.006 vs raw q≈0.142, value≈0.071) because placement
returns are bounded in [-1, 1].

Evaluation:
40-seed Chongci duplicate-seat eval (160 matches each), `--max-steps-per-episode
4000`. NOTE: a first eval pass with the default step cap truncated every match
(`match_truncated: 1.0`, all-zero reward); a high step cap is required for
Chongci matches to resolve.

Result:

| metric | raw | placement |
| --- | ---: | ---: |
| mean_reward | -2.0698 | -2.0726 |
| mean_reward_ci95 | 0.0166 | 0.0260 |
| large_loss_rate | 1.0000 | 0.9938 |
| positive_reward_rate | 0.0 | 0.0 |
| round outcomes | match_end 1.0 | match_end 1.0 |

Decision:
inconclusive (mechanics validated, no quality signal).

Interpretation:
The full new pipeline works on the 4090 with the real bridge: placement
data/return shaping, raw and placement IQL training, and fully-resolved
duplicate-seat eval with the new `mean_reward_ci95` field. But both 3-epoch
from-scratch models are degenerate (lose every match, ~100% large loss), so the
means are statistically indistinguishable and tell us nothing about placement
quality. A meaningful comparison needs the full protocol: warm-start from the
promoted Chongci checkpoint, an order of magnitude more data, more epochs, and
the placement `--target-mode global_ev_td` variant (train GlobalEV with
`--reward-shaping placement`, then bootstrap IQL Q targets from it). Also: always
pass a high `--max-steps-per-episode` for Chongci online/duplicate eval.

### Experiment: Full-Scale Warm-Started Placement / GlobalEV-TD Campaign

Run:
`/root/fh-mahjong-runs/placement-campaign-20260621-022616`

Question:
With proper warm-start from the promoted anchor and scaled anchor-in-the-loop
mixed self-play, does placement reward shaping (MC) or placement-aware
`--target-mode global_ev_td` beat the promoted Chongci anchor on a duplicate-seat
CI gate?

Data:
3 fresh windows of mixed self-play (300 Chongci episodes each, seeds 810000 /
820000 / 830000; promoted anchor in two seats + one random seat + heuristic,
seats rotated, GPU inference) plus the existing
`chongci-broader-mixed-selfplay-20260607-032601/.../anchor-fresh-balanced-tail2-760000-n200-npz`
dataset. Reused via repeated `--data`.

Training (all warm-started from the promoted anchor
`chongci-broader-mixed-iql-20260607-034720/.../epoch_001.pt`, 6 epochs, batch
256, lr 1e-4, cuda):
- raw MC return target
- `--reward-shaping placement` MC return target
- `--target-mode global_ev_td` bootstrapped from a placement-trained GlobalEV
  (`fh-mj-train-global-ev --reward-shaping placement`, 4 epochs)

Evaluation:
80-seed Chongci duplicate-seat eval, `--max-steps-per-episode 4000`, all matches
resolved (`match_end 1.0`). Anchor evaluated on the identical gate.

Result:

| variant | mean_reward | ci95 | large_loss_rate | positive_reward_rate |
| --- | ---: | ---: | ---: | ---: |
| anchor (promoted) | -0.0903 | 0.1291 | 0.2156 | 0.4406 |
| raw warm-start | -0.1749 | 0.1296 | 0.2469 | 0.4281 |
| placement | -0.2018 | 0.1293 | 0.2531 | 0.4250 |
| global_ev_td (placement) | -0.2053 | 0.1371 | 0.2750 | 0.4094 |

Decision:
rejected (no promotion). No candidate beats the anchor.

Interpretation:
The anchor is best on every metric. All three warm-start fine-tunes drifted
slightly worse, and placement / global_ev_td did not help. Individual gaps fall
within the wide 80-seed CI (~0.13), but the monotonic ordering of large-loss rate
(0.2156 -> 0.2469 -> 0.2531 -> 0.2750) and positive rate (0.4406 -> 0.4281 ->
0.4250 -> 0.4094) indicates a small but consistent regression from this
fine-tune recipe rather than pure noise. Likely causes: (1) 6-epoch fine-tuning
of an already well-tuned promoted checkpoint on a smaller/fresher data mix drifts
it (distribution shift / mild forgetting); (2) placement shaping changes the
target scale and, under a short fine-tune, did not produce a better policy.
What to try before concluding placement shaping is unhelpful: train candidates on
the anchor's full original data mix (not just ~1100 episodes) so fine-tuning does
not regress; use a lower LR / fewer epochs to limit drift; and widen the eval to
several hundred seeds to tighten the CI below the observed gaps. The placement
and global_ev_td code paths are correct and validated; this is a negative result
about the warm-start fine-tune recipe at this data scale, not a code failure.

### Experiment: Corrected Gentle-Recipe Placement Re-Run

Run:
`/root/fh-mahjong-runs/placement-campaign2-20260621-170935`

Question:
Campaign #1 used an aggressive fine-tune (lr 1e-4, 6 epochs, batch 256) that
might have caused the regression. The promoted anchor was actually built with a
gentle recipe (lr 2e-5, 1 epoch, batch 4096) on its own 409882-transition mix.
Does matching that gentle recipe, on the anchor's original data, let placement or
global_ev_td beat the anchor on a tighter (160-seed) CI gate?

Data:
Anchor's original training mix
(`chongci-broader-mixed-selfplay-20260607-032601/.../anchor-fresh-balanced-tail2-760000-n200-npz`,
409882 transitions) plus the reused campaign-#1 self-play windows (sp-a/b/c).
`--max-transitions 200000` per dataset.

Training (warm-start from the promoted anchor, lr 2e-5, 2 epochs, batch 4096,
bc-weight 0.03, cuda): raw MC, `--reward-shaping placement` MC, and
`--target-mode global_ev_td` from a placement-trained GlobalEV (3 epochs).

Evaluation:
160-seed Chongci duplicate-seat gate, `--max-steps-per-episode 4000`, all matches
resolved. Anchor re-evaluated on the identical gate.

Result:

| variant | mean_reward | ci95 | large_loss_rate | positive_reward_rate |
| --- | ---: | ---: | ---: | ---: |
| anchor (promoted) | -0.0902 | 0.0881 | 0.2094 | 0.4328 |
| raw warm-start | -0.5190 | 0.0825 | 0.3625 | 0.3047 |
| placement | -0.5113 | 0.0829 | 0.3609 | 0.3063 |
| global_ev_td (placement) | -0.5870 | 0.0807 | 0.3797 | 0.2797 |

Decision:
rejected (no promotion).

Interpretation:
All fine-tune variants regress hard versus the anchor with non-overlapping CIs
(160 seeds tightens ci95 to ~0.08, below the gaps), so this is significant, not
noise. Placement is statistically identical to raw (no benefit); global_ev_td is
worst. Counterintuitively the gentle recipe regressed WORSE than campaign #1's
aggressive recipe (raw -0.519 vs -0.175), which means campaign #2 introduced its
own confounds rather than isolating the recipe: `--max-transitions 200000` reads
the first 200k episode-ordered rows of each dataset (a biased subset), and batch
4096 with only ~390 steps gives poor IQL value estimates. So neither campaign is
a perfectly clean controlled test.

Robust cross-campaign conclusion: IQL warm-start fine-tuning of the promoted
anchor consistently fails to improve and significantly regresses it across two
very different hyperparameter regimes, and placement reward shaping never helps
(placement ~= raw in both campaigns). The anchor is a strong local optimum that
short IQL fine-tunes move away from.

Recommendation: shelve anchor warm-start fine-tuning and placement-as-objective
as the improvement lever. The placement / GlobalEV / eval-CI code is correct and
merged (PR #83) and stays available, but is not the path to a better Chongci
agent. Pivot research effort to: (a) the proven from-scratch mixed self-play loop
with a growing frozen checkpoint pool and duplicate-seat promotion (the only path
that ever produced a Chongci promotion), and (b) training-only oracle auxiliaries
(opponent tile / wall prediction feeding the value/Q heads, deployed visible-only)
to attack the POMDP directly. If anyone revisits fine-tuning, first remove the
confounds: no `--max-transitions` truncation, moderate batch size, and reproduce
the anchor's full auxiliary-term recipe; but the prior is now poor.

### Experiment: Live Self-Play Improvement Loop (fh-mj-selfplay-loop)

Run:
`/root/fh-mahjong-runs/selfplay-loop-20260621-233930`

Question:
Can the proven mixed self-play loop — generate with the current best, train a
fresh IQL candidate on accumulated data (never fine-tuning the rolling best), and
promote only on a CI-confirmed gain — advance past the promoted Chongci anchor,
the thing reward shaping and warm-start fine-tuning could not do?

Setup:
First live run of `fh-mj-selfplay-loop` (merged in PR #85). Warm-start from the
promoted anchor (`--fixed-init` and `--initial-best` =
`chongci-broader-mixed-iql-20260607-034720/.../epoch_001.pt`), `--base-data` = the
anchor's original 409882-transition mix. 6 iterations max, 300 episodes/iter
(current best in 2 seats + heuristic + random), fresh IQL each iter (4 epochs,
batch 256, lr 1e-4, no truncation), two-stage CI gate (60-seed screen -> 160-seed
confirm), patience 3, Chongci, GPU.

Result:
Early-stopped at patience after 3 consecutive non-promotions; no candidate
promoted. `current_best` stayed the anchor throughout.

| iter | decision | candidate screen mean | candidate confirm mean (ci95) |
| --- | --- | ---: | ---: |
| anchor | (baseline) | -0.0666 (screen) | -0.0902 (0.0881) |
| 1 | rejected_confirm | -0.0738 | -0.148 (0.0938) |
| 2 | rejected_screen | -0.2026 | not run |
| 3 | rejected_screen | -0.1987 | not run |

Decision:
rejected (no promotion). Loop exited cleanly (rc=0).

Interpretation:
The loop infrastructure is fully validated on real hardware: self-play
generation, fresh-IQL-on-accumulated-data training, the two-stage CI gate
(iter 1 correctly rejected on CI overlap; iters 2-3 cheaply rejected on the
screen without spending a confirm), best-eval caching, the resumable ledger, and
the patience early-stop all worked. The deployed best never regressed
(monotonic), which is the core safety property.

But like reward shaping and warm-start fine-tuning before it, a short self-play
loop did not beat the anchor. The cause is data scale, not the method: each
iteration added only 300 episodes against the anchor's 409882-transition base, so
3 iterations (~900 episodes) is far too little signal to move a well-tuned
checkpoint, and iter 1's candidate was already close (screen -0.074 vs anchor
-0.067) before regressing on confirm. To actually clear the anchor the loop needs
many more iterations and/or much larger episodes-per-iter, which is impractical at
the current single-env generation speed (~20-40 min per 300-episode window with
checkpoint seats). The aligned next step is the deferred parallel-generation
follow-up so the loop can run far more self-play per iteration, then re-run with
more iterations; the oracle-auxiliary direction remains the higher-upside
alternative. The loop itself (PR #85) is sound and ready to scale.

### Experiment: Streamed Big-Batch Loop (memory fixed; more data falsified)

Run:
`/root/fh-mahjong-runs/stream-loop-20260623-231641`

Question:
Now that training memory is no longer the wall (streaming replay, PR #88 + the
row-copy leak fix PR #89), does 1500 episodes/iter let the self-play loop beat the
promoted anchor? This is the clean re-test the earlier OOM/crash prevented.

Setup:
`fh-mj-selfplay-loop --stream-training --stream-shuffle-buffer 50000
--stream-workers 2`, 2 iterations, 1500 episodes/iter, warm-start fixed-init =
promoted anchor, base-data = anchor's original mix, gate 60-seed screen / 160-seed
confirm, patience 2, Chongci, cuda.

Result:
Finished cleanly (rc=0). No candidate promoted.

| iter | decision | candidate screen mean |
| --- | --- | ---: |
| anchor (baseline) | — | ~-0.067 screen / -0.0902 confirm |
| 1 | rejected_screen | -0.4629 |
| 2 | rejected_screen | -0.5401 |

Two findings:

1. Streaming training works. Both iterations trained the full accumulated dataset
   (~409 K base + ~1.85 M new transitions per iter) to completion with RAM steady
   at ~10 GB and zero crashes — versus the prior non-streaming run (OOM rc=137)
   and the first streamed run (DataLoader-worker leak, fixed in PR #89 by copying
   rows so buffered samples don't retain whole-shard views). Streaming + the
   memory fix are validated end to end on real 1500-episode data.

2. More data does NOT beat the anchor — it makes the policy worse, and worse with
   more accumulated data (iter 1 screen -0.4629, iter 2 -0.5401, both rejected at
   the cheap screen versus the anchor's ~-0.067). The "the loop only failed
   because each iteration had too few episodes" hypothesis is decisively
   falsified.

Decision:
rejected (no promotion); hypothesis falsified.

Interpretation and consequence for parallel generation:
This is the clean answer the streaming detour was built to get, and it is
negative. Likely mechanism: the loop's self-play data composition (anchor in 2
seats + one random seat + heuristic) is lower quality than the anchor's actual
training mix (specific teacher policies, no random seat), so fresh IQL on a
growing pile of it drifts the policy away from the well-tuned anchor — more data =
more drift = worse. Combined with the earlier negatives (reward shaping,
warm-start fine-tuning, 300-ep loop), the picture is consistent: offline IQL
retraining at this data composition/recipe cannot beat the anchor.

Critically, this falsifies the premise of the shelved parallel-generation spec
(`worklog/specs/2026-06-22-parallel-selfplay-generation-design.md`):
generating MORE self-play data faster is pointless when more data degrades the
policy. Do NOT build parallel generation. The binding issue is data QUALITY /
training recipe, not data VOLUME or generation speed.

Recommended next directions (none is "more of the same"):
- Stop and accept the anchor as the current ceiling; the loop/streaming/eval
  tooling is built and the negative space is well mapped.
- If pursuing strength, change the DATA RECIPE, not the volume: reproduce the
  anchor's real training composition (teacher policies instead of a random seat),
  or curate/filter self-play data quality, before any further scaling.
- Or pivot to the oracle-auxiliary research direction, which does not depend on
  growing the offline dataset.

### Experiment: First Online PPO vs Frozen Anchor (slice 1)

Run:
`/root/fh-mahjong-runs/ppo-anchor-20260625-194705`

Question:
The project's first ONLINE/on-policy trainer (`fh-mj-train-ppo`, PR #91 + reward
fix PR #92). Warm-started from the promoted anchor (policy+value), the learning
seat plays Chongci vs 3 frozen-anchor seats and learns via masked clipped PPO from
the per-seat match reward. Can online RL beat the anchor where offline could not?

Setup:
40 iterations, 16 matches/iter, gamma 0.999, gae_lambda 0.95, lr 2e-5,
entropy_coef 0.01, ppo_epochs 4, minibatch 256, sample_temperature 1.0, Chongci,
cuda. Reward = env `step.rewards[seat]` (sparse: 0 until match end, then final net
score change / 1000 — the env exposes no per-hand deltas). Eval = 120-seed Chongci
duplicate CI gate; anchor evaluated on the identical seeds.

Pre-flight (important): the original `collect_rollouts` read reward from
`StepResult.info` round-outcome payouts, which the Go bridge leaves empty, so the
reward was always 0 (PPO would learn nothing). Fixed in PR #92 to read
`step.rewards[seat]`; verified non-zero on the bridge before the run.

Result:
PPO did NOT beat the anchor; it regressed.

| variant | mean_reward | ci95 | large_loss_rate | positive_reward_rate |
| --- | ---: | ---: | ---: | ---: |
| anchor | -0.0615 | 0.1040 | 0.2083 | 0.4500 |
| ppo_final (iter 40) | -0.4238 | 0.0987 | 0.3417 | 0.3229 |

CIs do not overlap; worse on every metric.

Learning curve (rollout mean_reward, learning seat vs 3 frozen anchors; anchor-vs-
anchor ~ 0): iter1 +0.50, iter2 -0.25, iter3 +0.18, iter20 -0.48, iter40 -0.14 —
swings +-0.5 with no upward trend, drifting negative. Entropy stayed ~0.07-0.17
nats (near-deterministic, minimal exploration); approx_kl ~ +-0.008 (updates
barely moved the policy).

Decision:
rejected (no promotion). The PPO infrastructure works end to end (rollouts,
GAE, clipped update, eval gate; no crash), but this configuration degraded the
policy.

Interpretation (fixable failure mode, not "online RL can't work"):
Catastrophic signal-to-noise. Three compounding causes:
1. Tiny batch — 16 matches/iter = only 16 noisy terminal-reward signals; the
   per-iteration reward variance (+-0.5) swamps the gradient.
2. Sparse terminal reward over a ~440-step learning-seat horizon — the env emits
   no per-hand deltas, so almost all credit must flow through the value critic;
   the direct reward signal is one number per match.
3. Minimal exploration — the warm-started policy is highly peaked (entropy ~0.1),
   and entropy_coef 0.01 did not keep it exploring, so PPO mostly drifted under
   noise rather than discovering better lines.
Net: 40 noisy updates slowly degraded the anchor.

Recommendations before scaling online RL (do NOT just rerun as-is):
- Much larger rollouts per update (hundreds of matches) to cut reward variance —
  this is the highest-leverage fix and it needs faster generation, so the
  shelved parallel-generation spec is now justified specifically for online RL.
- Add dense per-hand reward (requires Go env support to emit per-hand score
  deltas, or reconstruct from visible score scalars) to fix credit assignment.
- Raise entropy_coef / sample_temperature for real exploration; tune lr; more
  iterations once signal-to-noise is fixed.
- Consider the GlobalEV/GRP reward as the critic/return target (Suphx-style).
The PPO code paths (PR #91/#92) are correct and reusable; this is a
tuning/throughput/reward-density problem, not a code failure.

### Experiment: Oracle Guiding → Self-Play Feature-Dropout (deployable beat)

Run:
`/root/fh-mahjong-runs/sp-gate` (50-iter small net, first beat),
`/root/fh-mahjong-runs/sp-long` (80-iter small net),
`/root/fh-mahjong-runs/sp-big` + `/root/fh-mahjong-runs/sp-big-ext` (deeper 4-block net).
Anchor: `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`.

Question:
Can a DEPLOYABLE imperfect-information agent beat the anchor, by combining the two
untried pieces of the Suphx/Mortal recipe: (1) a perfect-information scaffold
(51ch oracle observation = the 3 opponents' concealed hands) annealed away via
feature-dropout (δ 0→1), and (2) all-4 symmetric self-play (every seat is the
co-evolving net) instead of a fixed heuristic/anchor opponent?

Data:
Self-generated all-4 self-play (no offline dataset). 51ch oracle net warm-started
from the 39ch anchor via `build_oracle_model`. Deeper variant = `residual_blocks=4`
warm-started from the 2-block anchor (blocks 0-1 + heads + input conv copied, new
blocks' output convs zeroed → logit_corr 1.000 with the anchor).

Training:
all-4 self-play + feature-dropout (δ=0 first 20% iters, linear ramp 0→1 over the
next 60%, δ=1 final 20%); 256 matches/iter, lr 2e-5, entropy_coef 0, ppo_epochs 2,
max_grad_norm 0.5, gamma 0.99, chongci, max-steps 4000, cuda, 5 workers. sp-gate 50
iters; sp-long 80 iters; sp-big 60 iters (deeper); sp-big-ext resumes sp-big
iter_060 for 60 more δ=1 iters (→ iter_120). MLflow: N/A — these were run via
standalone scripts (`sp_big.py`, `sp_big_ext.py`), not the MLflow-integrated CLI;
metrics are in each run's `train.log` + `ckpt/history.json`.

Evaluation:
Deployable 39ch student extracted from the 51ch net (slice input conv), evaluated
NON-oracle (directly comparable to the anchor). Paired duplicate-seat, 120 episodes
× 4 seats = 480, start-seed 870000, chongci 50 hands, max-steps 4000. Anchor
evaluated on the identical seeds (`/root/fh-mahjong-runs/oracle-gate-baseline/eval-anchor.json`).
Reports under each run's `deploy/`/`eval-*` json.

Result:

| checkpoint | paired diff vs anchor | ci95 | large_loss |
| --- | ---: | ---: | ---: |
| anchor | 0.0 (mean_pl -0.0528) | — | 0.208 |
| sp-gate iter_050 (small, first beat) | +0.1639 | 0.0676 | 0.165 |
| sp-long iter_075 (small, longer) | +0.2125 | 0.0750 | 0.138 |
| sp-big iter_060 (deep4, 60 iters) | +0.1875 | 0.0719 | 0.150 |
| **sp-big-ext iter_120 (deep4, 120 iters)** | **+0.2958** | **0.0773** | **0.104** |

Decision:
promoted — `sp-big-ext` iter_120 (deep 4-block) → `current_chongci_reward_trained_best`
(PR #136), extracted standalone 39ch at
`/root/fh-mahjong-runs/deploy/selfplay-deep4-student-iter120-39ch.pt`. The prior
`iter_050` student moves to `fallbacks`; `iter_075` (+0.2125) is the runner-up/
fallback candidate at `/root/fh-mahjong-runs/deploy/selfplay-student-iter075-39ch.pt`.

Interpretation:
First deployable agent to robustly beat the anchor — the winning combination is the
Suphx feature-dropout scaffold + all-4 self-play (neither alone had cleared parity).
Depth initially looked worse (deep4 at 60 iters = +0.1875 < small-net +0.2125) but
that was UNDERTRAINING, not a capacity ceiling: given a fair 120-iter budget the
deeper net's δ=1 tail climbed 080/100/120 = +0.2042/+0.2903/+0.2958 and plateaued
well above the small net, halving large-loss (0.104 vs 0.208). Lesson: bigger nets
need proportionally more experience; compare at matched (sufficient) budgets, and
promote demonstrated (converged) performance, not potential. Serving had to learn
the checkpoint's architecture from the state dict (`infer_model_config`, PR #136),
since the promoted net is 4-block vs the 2-block default.

### Experiment: Phase B run #1 — bigger-batch extension of the deep4 champion

Run:
`/root/fh-mahjong-runs/phaseB1` (resumed from `/root/fh-mahjong-runs/sp-big-ext/ckpt/iter_120.pt`)

Question:
The deep4 champion's iteration-scaling had plateaued (+0.290 -> +0.296 over iters
100->120). Is gradient noise the binding constraint — i.e. does a bigger batch
per PPO update (more matches per iteration) break the plateau?

Data:
Self-generated all-4 self-play, delta=1 throughout (net already weaned).

Training:
Single variable vs the champion run: matches_per_iter 256 -> 320 (the intended
512 was OOM-killed — the process collector materializes ~3x the batch; fixed
post-hoc in PR #146). 155 iters (gi 121-275), nw=10, lr 2e-5, entropy 0,
ppo_epochs 2, chongci, cuda. No MLflow (standalone script /root/sp_phaseb1.py);
metrics in train.log + ckpt/history.json.

Evaluation:
Extracted 39ch students, paired duplicate-seat 120x4=480 episodes, start-seed
870000, vs the IQL anchor baseline (-0.0528). Promotion bar: CI lower bound
above the prior champion's +0.2958.

Result:

| checkpoint | paired diff | CI95 | CI lo | large_loss |
| --- | ---: | ---: | ---: | ---: |
| champion iter_120 (prior) | +0.2958 | 0.0773 | — | 0.104 |
| iter_200 | +0.3903 | 0.0825 | +0.3078 | 0.094 |
| iter_240 | +0.3861 | 0.0781 | +0.3080 | 0.073 |
| iter_275 | +0.4722 | 0.0815 | +0.3907 | 0.079 |

Standalone plain-39ch validation of iter_275: +0.4722 +/-0.0815 (exact match to
the --from-oracle eval; artifact self-contained at
`/root/fh-mahjong-runs/deploy/selfplay-deep4-student-iter275-39ch.pt`).

Decision:
promoted — iter_275 student -> `current_chongci_reward_trained_best`
(prior champion iter_120 retained in fallbacks; BC stays the generic fallback).

Interpretation:
Bigger-batch hypothesis confirmed even at 1.25x batch: the plateau was gradient
noise, not capacity or iteration count. The curve is still RISING at run end
(240 -> 275 jumped +0.086), so Phase B run #2 continues from iter_275 at
matches_per_iter 448 (enabled by the PR #146 collector memory fix). Operational
lessons: 512x16 needs ~38GB (3x-batch materialization) — fixed by worker-side
release + consume-mode concat; watcher aggregators must not be edited via sed
patterns that miss escaped quotes (evals ran, aggregation mislabeled).

### Experiment: ACH regret objective A/B (2026-07-07/08) — FAILED, keep PPO

Motivation: with scaling saturated (Phase B #2 parity at 448), the champion not
exploitable, and the oracle-ceiling eval showing hidden-info value ~0 (perfect-info
51ch iter_275 = +0.4361 vs the 39ch student's +0.4722 — parity, so belief modeling
ruled out), the remaining lever was the objective itself: clipped-NeuRD / ACH
(LuckyJ's family), merged as a drop-in for ppo_update in PR #147
(--objective ach --ach-beta; RolloutBatch unchanged; PPO default byte-identical).

A/B (both resume iter_275, identical seeds, 40 iters, batch 224 after OOM tuning,
delta held 1): PPO control +0.4306 vs anchor / large_loss 0.079 (validates champion
and eval); ACH beta=2 -0.6250 / large_loss 0.675; paired ACH-PPO = -1.0556 +/-0.077.
ACH never sharpened (entropy pinned ~1.73 vs PPO 0.14); mean_abs_logit 1.2-1.5
stayed BELOW beta=2 with saturation 4-15%, so beta was not the binding constraint
(beta sweep pointless). A from-scratch retry (IQL anchor, lr 1e-4) was projected
~30h on the 31GB box (the anchor plays max-length games; 224 OOM'd, 128 crawled)
and was killed per user decision.

Theory note: ACH/regret-min guarantees Nash convergence only in 2-player zero-sum
(the paper's 1-on-1 mahjong benchmark); in 4-player games regret dynamics reach
only coarse-correlated equilibria and need not sharpen — the observed failure is
consistent with the setting, not just the config. LuckyJ's 4-player method is
undisclosed. Verdict: ACH closed; PPO remains the objective.

Incidental find (blocking bug, fixed): the A/B crashed at iter 277 with
"duplicate action id 182 for ACTION_KAN" — root cause was NOT wilds but a wall
double-draw: dead-wall (kong/flower) replacement draws descend past wangpaiBoundary
into the live wall, and ExecuteSystemDraw never skipped those consumed indices, so
the same physical tile could be dispensed twice (phantom duplicate tile id in a
hand; corrupts counts/scoring). Fixed in PR #149 (front draw skips
isTileConsumedByDeadWall indices; fuzzer regression gate in
internal/rl/kan_dup_repro_test.go reproduced at seeds 15/47/68 pre-fix). The
related wild-in-kan rule enforcement (PR #148) was closed: a wild kan is
unreachable in normal play (a standard indicator leaves only 3 wild-face copies in
play; a kan needs 4). Rules clarified by the owner: wilds are jokers ONLY in the
concealed hand; in open melds / discards / calls they are strictly face-value.

### Experiment: pool-diversity run (2026-07-08/09) — PARITY, champion stands

The last untested training lever: the entire champion line was pure mirror
self-play (pool_max_size=1). Run: 39ch student extracted from iter_275, trained
via train_ppo (single learning seat, pure 39ch env) against a snapshot pool
(pool_max_size 6, snapshot_interval 8), 160 iters x 224 matches, lr 2e-5, ~9h.
Paired vs champion on identical eval seeds: iter_80 -0.068, iter_120 -0.081,
iter_160 -0.031 +/-0.069 = statistical parity (large_loss 0.067 vs 0.079 — a mild
tail improvement, not promotable). No promotion.

Campaign status after these runs: ALL FIVE training levers tested and closed —
scaling saturated, not exploitable, hidden info worthless, ACH failed, opponent
diversity neutral. The +0.4722 iter_275 39ch student is the genuine, robust
self-play plateau for this architecture/pipeline. Remaining non-training options:
pMCPA-style test-time search (serve-time boost, no training), a bigger net
(4->8 residual blocks, brute force), production human-paipu accumulation
(storage.Match.PaipuJSON — capture verified live), and the human game-review
product direction (mjai-reviewer-style; spawned as its own design session).

### Experiment: deep8 capacity campaign (2026-07-09/11) — PARITY CEILING, capacity closed

Brute-force lever: replay the champion pipeline at residual_blocks=8 (2x deep4).
Warm-start 51ch from the IQL anchor via load_compatible (deep2->deep4 mechanism),
60-iter delta ramp at batch 128 (anchor-start plays max-length games — the 224 OOM
lesson), then delta=1 extensions.

Trajectory (paired vs anchor, -0.0528): ramp iter_60 +0.138 (deep4 ref +0.13);
ext1 batch 224: 120=+0.242, 150=+0.303, 180=+0.356 (tail 0.077 = champion-level);
ext2 batch 224: 220=+0.371, 260=+0.396, 300=+0.379 — SATURATED ~+0.38, worse than
champion CI-separated. Leg 3 applied the Phase-B batch move (224->320, the exact
recipe that broke deep4's plateau): iter_330 +0.4528 (champion parity, -0.019
+/-0.075), iter_360 +0.4056 (post-peak oscillation, mirrors deep4's endgame; tail
0.069 = best seen — ensemble candidate).

Verdict: the batch move works on deep8 exactly as on deep4, but the destination is
the SAME ~+0.45-0.47 ceiling — deep8 reaches champion parity at 2x inference cost
and never CI-beats +0.4722. Not promotable. Capacity joins the closed levers.

Campaign status: SIX levers tested and closed — scaling saturated, not exploitable,
hidden info ~0, ACH failed, pool diversity neutral, capacity parity-bound. +0.47 is
a pipeline-level plateau independent of model size. The remaining ceiling-moving
mechanism is test-time search + expert iteration (search-improved targets distilled
back into the net), with serve-time ensembling (champion + deep8 iter_360's 0.069
tail) as a cheap adjacent win.

### Experiment: Phase-1 test-time search gate (2026-07-12/14) — FAILED, search closed

Setup: honest determinized pMCPA over the frozen champion (PR #161: RedealUnseen,
paired-CRN SearchPool, root-seat pinning, discount-consistent scoring, in-distribution
bootstraps; 11 defects fixed pre-merge across SDD/adversarial-loop/GitHub-Codex).
Gate: SearchPolicy(champion) vs raw greedy champion, paired duplicate-seat, 480
placements, seeds 870000+.

Results (fallback_count=0 in both runs — the machinery was flawless):
- K=16/M=4 (21h): vs champion -0.0375 +/-0.0745 (parity); vs anchor +0.4347;
  large_loss 0.079 (identical).
- Escalation K=32/M=6 (34h): vs champion -0.0833 +/-0.0715 (WORSE, CI-separated);
  vs anchor +0.3889; large_loss 0.092.

Interpretation: tripling the budget made search WORSE — more candidates gave the
rollout/value estimates more chances to override the champion's better greedy choice.
The champion's policy is more accurate than its own value head can re-rank through
shallow determinized search; without a search that outranks the policy there is no
expert-iteration teacher, so Phase 2 is not justified. Search closes as the SEVENTH
tested lever.

CAMPAIGN CONCLUSION: batch scaling saturated, not exploitable, hidden info ~0, ACH
failed, pool diversity neutral, capacity parity-bound at 2x cost, and test-time
search loses to the raw policy. +0.4722 (deep4 iter_275 student) is the genuine
ceiling of this pipeline, established seven independent ways. Remaining directions
are product-side: labelled human-game corpus (accumulating in prod since the paipu
fix), the post-game review tool, serve-time ensembling for tail risk, and an
eventual human-data SL refresh once the corpus is large.

(2026-07-14 addendum: a GPT-5.6 methodology audit + independent literature survey
overturned parts of this conclusion — see the Spec A entry below and the rebuild
specs under worklog/specs/. The seven-lever record above stands as
measured; its interpretation is now qualified by the observation defect and the
evaluation-statistics findings.)

### Experiment: Spec A close-out — obs double-count fix + eval hygiene (2026-07-14/15) — SHIPPED

- What: PR #166 (main 88c6d59). Fixed the interrupt-window double-count in
  `publicSeenCounts` (the claimable discard was counted twice in plane 37 and
  publicDangerScore at EVERY pon/chii/ron decision, all campaign — the engine
  appends to Discards before setting ActiveDiscard). Added seed-clustered CIs
  (`mean_placement_ci95_clustered`, `cluster_design_effect`) to duplicate-seat
  reports, persisted eval-config + simulator provenance (`bridge_lib_sha256`
  of a pre-eval immutable library snapshot), and shipped `fh-mj-compare` —
  the mandatory fail-closed gate tool (seed/config/protocol/provenance parity;
  labeled opt-ins `--allow-missing-config`, `--allow-bridge-mismatch`).
- Champion re-measurement (decision rule from the spec), screening window
  910000+, 120 seeds x 4 rotations, chongci, deep4 iter_275 champion, paired
  fixed-vs-buggy bridge via `fh-mj-compare --allow-bridge-mismatch`:
  - FIXED encoder: mean placement +0.3500 (clustered CI95 ±0.0561, naive
    ±0.0620), large_loss 0.0813.
  - BUGGY encoder: +0.3431 (clustered ±0.0585), large_loss 0.0875.
  - Paired delta (fixed − buggy): **+0.0069 ± 0.0176** — fixed ≥ buggy.
    VERDICT: the fix ships unconditionally (serving + training + eval); no
    compat flag. The champion is robust to the corrected input.
- Measured `cluster_design_effect` on the screening window: **0.80 (fixed) /
  0.88 (buggy)** — duplicate-seat rotations are mildly NEGATIVELY correlated
  within a wall seed, i.e. the duplicate format's variance reduction is real
  and the clustered CI is slightly TIGHTER than the naive one here. Spec B
  run-size planning can use design effect ≈ 0.85 (do not assume >1).
- Honesty note: the champion measures +0.3500 ± 0.056 on the FRESH screening
  window vs the +0.4722 ± ~0.08 recorded on the burned 870000+ window — the
  gap (≈ −0.12) exceeds the predicted ~0.035 winner's-curse bound, so window
  effects and selection bias together were inflating the headline number.
  All future comparisons are within-window paired deltas via fh-mj-compare;
  cross-window level comparisons like this one are diagnostic only.
- Artifacts: /root/fh-mahjong-runs/spec-a/{champion-fixed,champion-buggy,compare}.json
  (box); pre-fix bridge built from ec6800e in /root/fh-mahjong-prefix.

### Experiment: Spec B2b — event GRU + privileged critic + auxiliaries (2026-07-18/20) — **PASSED THE GATE, NEW CHAMPION CANDIDATE PROMOTED**

- What: warm-started deep4 iter275 with the B2b representation upgrade
  (event-history GRU window 128, privileged 12ch critic branch, aux heads
  belief/deal-in/rank-bust), trained 150 iters on the EXACT champion recipe
  (dense score deltas, γ=0.99, 320 matches/iter, lr 2e-5, entropy 0,
  ppo-epochs 2, chongci, 5 workers). PRs #169 (B1) + #172 (B2a) + #177 (B2b);
  12-round adversarial gauntlet pre-merge (see ledger).
- Gate protocol: the RATIFIED 10-item protocol (Codex debate-to-agreement,
  2026-07-19, appended to the B2b runbook). Determinism precheck PASSED
  bit-exact (480/480 identical champion-repeat placements). Frozen candidate
  = iter_075 (best screening delta +0.0396 of {25..150}; extension trigger
  not met — 100→125 screening decrease).
- Screening trajectory (910000+, 120 seeds, same-bridge paired):
  25:+0.0285 50:+0.0035 75:+0.0396 100:+0.0215 125:+0.0069 150:+0.0035.
- **CONFIRMATION VERDICT (950000+, 1500 seeds, back-to-back, same bridge,
  full provenance in /root/fh-mahjong-runs/b2b/gate-provenance.txt):**
  - candidate +0.4229 vs champion +0.3821; paired placement delta
    **+0.0408 ± 0.0203** (seed-clustered CI95) — CI clears zero
    (lower bound +0.0205). SIGNIFICANT.
  - tail criterion: large_loss 0.0552 vs 0.0613; point rule −0.0062 ≤ +0.015
    PASS; paired per-seed tail delta **−0.0062 ± 0.0077** — the candidate's
    tail is significantly BETTER, not merely non-inferior.
  - zero truncations; config_check strict except the window key
    (the intervention); bridge digests match.
- Interpretation: the representation rebuild (audit direction #1) delivered
  the campaign's FIRST confirmed champion-beating candidate, in the
  predicted +0.04..+0.12 band, with improved tail risk — after seven
  training levers and a search phase all failed. The +0.4722 headline was
  never the true bar (window-inflated; Spec A); the honest bar was
  +0.3821 ± 0.020 on this window, and the candidate clears it.
- Artifacts: /root/fh-mahjong-runs/b2b/ (ckpt/iter_075.pt sha 00f469b0…,
  confirm-{candidate,champion,compare}.json, gate-provenance.txt).
- NEXT (per ratified item 10): Spec B2c — serving integration (room →
  HTTPPolicy event threading, /act payload, review tool) BEFORE any
  deployment of the new champion.

## Maintenance Protocol For This Note

When a new experiment starts, append:

```text
### Experiment: <short name>

Run:
<remote run dir>

Question:
<what hypothesis this tests>

Data:
<datasets and policy sources>

Training:
<important hyperparameters and MLflow run id>

Evaluation:
<seed windows, seats, reports>

Result:
<metrics table>

Decision:
promoted / rejected / inconclusive / still running

Interpretation:
<what we learned and what to avoid repeating>
```

When a checkpoint is promoted or rejected, also update:

```text
ai/checkpoints/best-checkpoints.json
```

If a result affects the general roadmap, also update:

```text
docs/rl-papers/implementation-takeaways.md
docs/rl-papers/roadmap-and-development-plan.md
```

## Glossary

BC:

Behavior cloning. Supervised learning from heuristic or checkpoint actions.

AWBC:

Advantage-weighted behavior cloning. BC where high-return actions receive
larger weights.

IQL:

Implicit Q-learning. Offline RL method that learns Q, value, and policy without
naive max-Q exploitation over unsupported actions.

CQL:

Conservative Q-learning penalty. Penalizes high Q-values for many actions so
offline RL does not overestimate actions not well covered by data.

Duplicate-seat evaluation:

Evaluate policies on the same wall seeds with rotated seats so seat and wall
luck are less confounded.

Large-loss rate:

Fraction of evaluated seats whose final normalized reward crosses the large
loss threshold. For Chongci this is a tail-risk metric, not the main objective.

Positive-reward rate:

Fraction of seats ending with positive final net reward in Chongci.

Mean reward:

Primary expected-value metric. For Chongci, this is final net score change
divided by 1000.

Oracle training:

Training with privileged hidden-state auxiliary targets while keeping deployed
inference inputs visible-only.

## 2026-07-24 — anchor075-restart: second consecutive confirmed win (restart ladder lap 1)

Codex-ratified iter_075 weight restart (exact champion recipe, --base-seed 100000,
symmetric self-play, preflight-proved exact load via --champion). 150/150 iters,
healthy telemetry throughout (dealin_positive_rate ~0.12, rank coverage 1.0, zero truncation).

Screenings vs regenerated iter_075 comparator (910000+, 120 seeds, strict):
25: -0.0486±0.0641 | 50: -0.0264±0.0630 (kill rule passed) | 75: +0.0264±0.0717 |
100: -0.0250±0.0741 | 125: -0.0042±0.0742 | 150: -0.0597±0.0778. Extension rule
failed cleanly (150 worst); pre-registered selection = restart iter_075 (only positive).

Confirmation (990000+, 1500 seeds/side, back-to-back, main 05f63a6, strict, frozen
candidate sha ce9d867f803bb41a...): paired placement +0.0254 ± 0.0188 — SIGNIFICANT;
large_loss 0.0493 vs anchor 0.0523 (tail criterion passes, candidate better). GATE PASSED.

Lesson repeated: both confirmed champions were isolated screening peaks in unstable
trajectories — screening CIs (±0.07) cannot resolve +0.03-level effects; the
no-optional-stopping confirmation discipline is what finds them. (Codex insisted on
running this gate against my pessimistic prior; it was right.)

Registered as gate_qualified_research_champion (chongci_b2b_anchor075_restart_iter075,
serving_status blocked_on_b2c_runbook); anchor iter_075 entry marked superseded.
990000+ window now spent. Next lap (r2) authorized and launched: --champion restart
iter_075, base-seed 200000, dir b2b-anchor075r2-restart, confirmation window 1030000+;
if r2 confirms, next step is a NEW decision (no automatic r3). Deployment rule: B2c
runbook target frozen at start; no mid-runbook candidate swap.

## 2026-07-24 — deep16-rezero: pre-registration (capacity growth via ReZero blocks)

Design ratified via Codex consult (canonical session): `worklog/specs/
2026-07-24-deep16-rezero-design.md`, branch `claude/deep16-rezero`. Runbook:
`worklog/plans/2026-07-24-deep16-rezero-runbook.md`. Registering the gate
BEFORE launch per standing pre-registration discipline; launch itself is gated on
r2's own confirmation (sequencing ratified — see the entry above) and has not
started as of this write-up.

**Hypothesis under test:** does capacity (trunk depth) pay ON TOP OF the B2b event
representation, given a defensible function-preserving warm start? This is ONE
architectural intervention — 12 stacked `ReZeroResidualBlock`s (`x + alpha *
F(x)`, `alpha` a learned scalar initialized to 0, so the grown net is EXACTLY the
anchor at step 0 — no trailing GELU, unlike the legacy `ResidualBlock`, is what
makes zero-init identity possible here). GRU, aux heads, and every other recipe
knob stay fixed. Prior context: both confirmed champion-line wins so far came from
temporal representation (B2b) at 96ch/4 blocks; a pre-B2b deep8 capacity test
(trunk-only, no events) nulled at 2x cost — this is a second capacity attempt, now
stacked on top of the representation win instead of before it.

**Anchor:** r2's winner if r2's `1030000+` confirmation passes ("r2 iter_150" — sha
`518cc376...`, confirm and freeze the full digest at launch time); otherwise
restart-iter075 (`/root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt`,
sha `ce9d867f803bb41acad30f1f4c137e82d7946ed2c4db769e265d0c9cd08f75d4` — already a
confirmed gate-qualified champion, registered above). Frozen path+sha recorded at
launch time in the runbook.

**Gate parameters (ratified, binding):**
- Budget: 260 iterations x 320 matches/iter (1.73x param ratio vs the anchor),
  recipe otherwise byte-identical to the ratified champion recipe (dense per-hand
  score-delta reward, gamma=0.99, lr=2e-5, entropy 0, 2 PPO epochs).
- Preflight: state-dict sha check + a step-zero parity script (`grow_b2b_model`
  output torch.equal to the anchor on policy logits/value/Q/aux/greedy-action)
  MUST pass on the box before any training compute is spent.
- Worker benchmark: `fh-mj-collect-bench` gates `--num-workers` (adopt the
  fastest worker count with an EXACT digest match; if the projected lap at that
  count exceeds 7 days, STOP — a pool port is a separate, out-of-scope decision).
- Screening: iters 25/50/75/100/125/150/175/200/225/250/260 vs a REGENERATED
  anchor comparator, same current bridge, `910000+` window, 120 seeds, strict.
- Kill rule: ONLY at iter 100, if BOTH the iter-75 AND iter-100 champion-relative
  deltas are `< -0.06`. No other iteration triggers a kill.
- Hard stop at 260 — no extension (unlike the B2b runbook's conditional
  extension). Freeze the best HEALTHY pre-registered screening checkpoint; no
  substitution after seeing later results.
- Confirmation: fresh `1070000+` window, 1500 seeds/side, back-to-back, same
  bridge. Promotion requires BOTH the paired placement clustered 95% CI clearing
  0 AND `large_loss_rate(candidate) <= large_loss_rate(anchor) + 0.015` absolute.
- Retention: keep screening checkpoints + final; prune the rest after completion.
  `train_state.pt` written every 5 iterations so the lap survives box restarts.
- Alpha telemetry: `history.json` logs mean `|alpha|` across the 12 growth blocks
  per iteration. Alphas hugging 0 at the end is itself a RESULT (protocol null —
  growth stalled under the shared learning rate), not a bug.

**Kill/null semantics (binding, stated up front):** a null result here means THIS
PROTOCOL failed, NOT evidence of a capacity ceiling. On null, record the outcome
plainly (including the alpha-telemetry trace) and the next menu item is GRU
widening per the scale roadmap memory — not another depth attempt with a
different warm-start, and not an automatic r3-style repeat of this same lap.

Out of scope for this lap (per spec, unchanged): GoEnvPool port, matches-per-iter
changes, transformer encoders, aux-weight changes, deployment of any winner (a
B2c-style runbook governs that later, with growth-aware metadata already handled
by Task 3).

## 2026-07-27 — r2 restart lap: confirmation NULL (ladder exhausted at one confirmed lap)

r2 (anchor restart-iter075, base-seed 200000): screenings all negative (best iter_150
-0.0056±0.0682). Confirmation on 1030000+ (1500 seeds/side, candidate sha 518cc376...,
run survived a box reboot via operator relaunch): paired delta +0.0043 ± 0.0196 — NOT
significant; large_loss 0.052 vs 0.0557 (tail fine). GATE FAILED per pre-registered
criteria. r2 iter_150 not promoted; 1030000+ retired. Restart ladder: 1 confirmed win
(lap 1) then null (lap 2) — consistent with the anchor sitting at this recipe's basin.

Next (pre-registered, no new consult needed): deep4+12-rezero capacity lap (PR #182
merged) with anchor = restart-iter075 (sha ce9d867f...). Box preflight PASSED
(step-zero parity OK on the real anchor); worker benchmark (5/10/20 @ 320 matches,
exact-digest gate) running; launch follows per runbook (260 iters, screening 25..260,
kill only at 100, confirmation window 1070000+).

## 2026-08-02 — deep4+12-rezero capacity lap: confirmation NULL

260/260 iters (two OOM kills mid-run — 20-worker + 16GB master exceeded the 31GB box —
both recovered via resumable train state; finished at 10 workers after PR #187 exempted
num_workers from the resume config echo as semantics-neutral). Anchor: restart-iter075.

Screenings (910000+, vs anchor): 25:-0.035 | 50:-0.017 | 75:-0.058 | 100:-0.033 (kill
rule passed) | 125:-0.078 | 150:-0.021 | 175:-0.021 | 200:+0.028 (pre-registered best) |
225:-0.021 | 250:-0.022 | 260:+0.010. growth_alpha_mean_abs stayed ~0.0002-0.0006 the
whole run — ReZero growth blocks barely recruited (the pre-registered "capacity not
engaging" signature), small late uptick only.

Confirmation (1070000+, 1500 seeds/side, candidate iter_200 sha a785d5ab...):
-0.0027 ± 0.0203 — NOT significant; large_loss 0.0613 vs anchor 0.0517 (within the
+0.015 bound). GATE FAILED. 1070000+ retired.

Reading: trunk depth is declined by PPO at this recipe even WITH the event
representation — consistent with the original deep8 null, now at 1.73x params with a
provably function-preserving warm start. Third lap running where an isolated screening
peak (+0.028 here) drove the confirmation: 1 hit (restart lap), 2 misses (r2, this).
Next per ratified menu: GRU-width scaling (post-consult).

## 2026-08-02 — gru-width: pre-registration (event-encoder width scaling)

Design ratified via Codex consult (canonical session, 2026-08-02), following the
deep16-rezero recruitment null: `worklog/specs/2026-08-02-gru-width-design.md`,
branch `claude/gru-width`. Runbook: `worklog/plans/2026-08-02-gru-width-runbook.md`.
Registering the gate BEFORE launch per standing pre-registration discipline.

**Hypothesis under test:** does the SEQUENCE CORE itself have unused capacity, given that
generic trunk depth has now nulled twice (deep8 pre-events; deep4+12-rezero with events,
alphas never recruited) while both confirmed champion-line wins came from the event/temporal
representation? ONE architectural intervention: double the event GRU hidden width (128 ->
256), keeping the trunk's 128-dim event-feature interface fixed via an identity-masked
`[I|0]` output projection so step-zero behavior is EXACTLY the anchor's (function-preserving
warm start, same discipline as `grow_b2b_model`, but widening an existing recurrent layer in
place rather than stacking new blocks). Trunk, aux heads, and every other recipe knob stay
fixed — this isolates the sequence-core width variable from the already-nulled depth variable.

**Anchor:** restart-iter075 (unchanged; already a confirmed gate-qualified champion):

```
/root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt
sha256: ce9d867f803bb41acad30f1f4c137e82d7946ed2c4db769e265d0c9cd08f75d4
```

**Gate parameters (ratified, binding):**
- Budget: `iterations = ceil_to_5(150 * candidate_params / anchor_params)` with the
  MEASURED ratio (expected ~1.08x -> 165) x 320 matches/iter, recipe otherwise
  byte-identical to the ratified champion recipe (dense per-hand score-delta reward,
  gamma=0.99, lr=2e-5, entropy 0, 2 PPO epochs, chongci, 10 workers — memory-proven per
  the deep16 20-worker OOM lesson, no fresh worker benchmark for this lap).
- Preflight: state-dict sha check + a step-zero parity script (`widen_event_gru` output
  torch.equal to the anchor on event features/policy logits/value/Q/aux/greedy-action)
  MUST pass on the box before any training compute is spent; the same script also
  measures the param-count ratio that fixes the iteration budget.
- Screening: iterations 25/50/75/100/125/150/`<final>` (the computed budget, expected
  ~165) vs a REGENERATED anchor comparator, same current bridge, `910000+` window, 120
  seeds, strict (the deep4+12-rezero comparator is not reused — the bridge has moved).
  Candidate eval flags add `--model-event-hidden-dim 256 --model-event-output-dim 128`.
- Kill rule: ONLY at iter 100, if BOTH the iter-75 AND iter-100 champion-relative deltas
  are `< -0.06`. No other iteration triggers a kill.
- No extension; selection protocol UNCHANGED from prior laps — best eligible
  pre-registered screening checkpoint, healthy telemetry, no substitution after seeing
  later results (ratified per consult: sensitivity over false-launch cost).
- Confirmation: fresh `1110000+` window (unspent by any prior lap), 1500 seeds/side,
  back-to-back, same bridge. Promotion requires BOTH the paired placement clustered 95%
  CI clearing 0 AND `large_loss_rate(candidate) <= large_loss_rate(anchor) + 0.015`
  absolute.
- Resumable state every 5 iterations; `PYTHONUNBUFFERED=1` launch; orchestrator +
  screening chain live under `/root/fh-mahjong-runs/` (reboot-safe paths) — same
  discipline as the last two laps, since deep4+12-rezero needed two OOM-recovery resumes.

**Kill/null semantics (binding, stated up front):** a null result here means the SEQUENCE
CORE also has no unused capacity at this recipe under PPO — a THIRD capacity axis (after
trunk depth twice) declining to pay, not merely a bad warm-start protocol (step-zero parity
is proven mechanically sound before launch, unlike the depth-null's alpha-recruitment
ambiguity). Per the ratified scale roadmap, the next menu item after a null here is an
aux-weight ablation, not a further width/depth variant.

Out of scope for this lap (per spec, unchanged): trunk changes, transformer encoders,
window changes, aux weights, matches-per-iter changes, deployment of any winner (B2c
rollout proceeds independently with restart-iter075 regardless of this lap's outcome).

## 2026-08-06 — gru-width lap: positive near-miss, independently unconfirmed

Lap ran exactly as ratified (165 iters, ratio 1.0705, step-zero parity, kill@100
passed). Screenings vs restart-iter075 (910000+): monotonic climb -0.078 (50) →
-0.050 (75) → -0.011 (100) → +0.033 (125), staying positive at 150/165 (+0.013).
Selected iter_125 (sha d855aa83...).

Confirmation 1110000+ (1500/side): +0.0170 ± 0.0194 — gate failed by a hair
(tail passed, 0.0503 vs 0.0540). Codex-ratified single independent replication
(1150000+, 3000/side, replication ALONE confirmatory; pooling descriptive only):
+0.0029 ± 0.0140 — NOT significant, point estimate collapsed. Verdict per
pre-registration: near-miss unconfirmed; iter_125 RETIRED; no third window.
Descriptive pooled estimate +0.008 ± 0.022 — consistent with tiny-or-zero effect.

Scale-campaign scoreboard vs restart-iter075: restart ladder r2 null; deep16
ReZero recruitment null; gru-width unconfirmed near-miss. Champion line stands:
iter275 → iter_075 (+0.041) → restart-iter075 (+0.025), promotion in progress.
Next decision (consult): aux-weight ablation vs concluding recipe saturation.

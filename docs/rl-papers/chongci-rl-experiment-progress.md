# Chongci RL Experiment Progress Note

Last updated: 2026-05-30

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

The main promoted Chongci checkpoint remains:

```text
id: iql_lowlr_selfplay200_epoch003
path: /root/fh-mahjong-runs/chongci-selfplay-200-ablation-20260522-001945/checkpoints/iql_lowlr_3ep/epoch_003.pt
```

The latest experiments show a recurring pattern: reward-learning candidates can
reduce tail losses or look good on a quick screen, but independent gates often
reverse the signal. The immediate research bottleneck is no longer just "train
more"; it is evaluation stability, repeated-gate reliability, and separating
mean-reward improvement from large-loss control.

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

`rules.HometownRuleset.ResolveInterruptPriority()` iterated over a Go map.
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

The observation scalar count stays at `50` to avoid a model-shape migration.
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
    `docs/rl-papers/chongci-risk-target-design.md`: add visible match-history
    inputs and train an action-conditioned critic-side risk head before trying
    any serving-time guard.

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

- add visible Chongci match-history scalars,
- add action-conditioned risk probability/severity heads over the 204-action
  catalog,
- calibrate the risk head before using it for serving,
- only then test a top-policy-candidate risk guard.

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

# Chongci RL Experiment Progress Note

Last updated: 2026-05-28

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

## Recommended Next Experiments

### Step 1: Target The Exact Divergence States

Use the paired-trace large-loss and worst-delta seeds to create targeted
high-risk-state weighting instead of weighting every large-loss transition
equally. The next implementation should be more selective:

```text
first-divergence seed/seat filtering
large-loss transition weight: 4x to 6x only for selected high-risk groups
bc_weight: keep high, 3.0 to 4.0
policy_weight: lower, 0.25
lr: 5e-6 or lower
```

Promotion still requires the deterministic repeated gate.

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

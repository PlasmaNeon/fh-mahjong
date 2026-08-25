# RL Learning Roadmap And Mahjong AI Development Plan

This roadmap is a self-contained study-and-build path for the Fenghua Mahjong AI work. Use the linked article or documentation material in each stage, then do the repo-specific exercise before moving on.

The required learning path intentionally avoids video lectures. Classic papers and books still appear where they are the right source, but the default path favors maintained docs, written tutorials, and recent implementation references.

> Stages 0-8 are the study path. Current state is in
> [Where The Project Actually Is](#where-the-project-actually-is) and the running record in
> [`worklog/rl-experiment/`](../../worklog/rl-experiment/chongci-rl-experiment-progress.md).

The Mortal-style build order:

1. simulator correctness
2. heuristic trajectories
3. behavior cloning
4. duplicate evaluation
5. operation-level Q/value learning
6. mixed checkpoint self-play
7. live AI integration
8. Suphx-style oracle/global-reward auxiliaries after the core loop is stable

Mortal-style means the model should learn Q/value estimates for each legal operation from the current visible Mahjong state: discard from the hand, pass/win after a discard, chii, pon, kan, haitei decisions, and any future mode-specific actions. Training samples are individual decision transitions, not one sample per hand or match. The reward is still delayed: for Chongci, the main target is final match net score; for classic Fenghua, the main target is terminal hand payout.

## Code-First Loop

Use this loop when you want the code to drive the learning:

1. Generate a small deterministic trajectory dataset with `fh_mahjong_ai.scripts.generate_data`.
2. Train behavior cloning with `fh_mahjong_ai.scripts.train_bc`.
3. Evaluate exact/top-3/action-family agreement with `fh_mahjong_ai.scripts.evaluate`.
4. Train the first conservative value-learning pass with `fh_mahjong_ai.scripts.train_iql`.
5. Generate mixed self-play trajectories with frozen checkpoint opponents.
6. Promote a checkpoint only after duplicate-seat evaluation improves against the heuristic baseline and frozen checkpoint pool.

This loop still runs end to end and is the bootstrap path. Discrete IQL — Q, value, and policy heads from operation-level transitions with behavior-cloning regularization — is the offline baseline. Champions come from on-policy PPO self-play; see below.

## Mortal-Style Development Target

Goal: make the agent improve from its own operation-level experience, similar in spirit to Mortal's Q-value decision engine.

The target training unit is:

```text
visible observation at decision t
legal action mask
chosen operation action_id
next visible observation
terminal / truncated flag
final hand or match reward target
```

The model should learn:

```text
Q(observation_t, action_t) = expected future score from choosing this operation
V(observation_t) = expected future score from this decision state
policy(observation_t) = action distribution used for exploration and serving
```

Near-term policy:

- Keep the flat 204-action catalog because the Go bridge already validates it.
- Use dueling Q/value heads and action masking for every decision.
- Use IQL-style offline updates first, then add online self-play collection.
- Use a frozen checkpoint pool so one new model does not only learn to exploit its own clone.
- Evaluate with fixed-seed duplicate Chongci matches and report mean net reward, positive-reward rate, large-loss rate, and per-seat breakdown.

Later policy:

- Split the flat action space into decision-family heads if the flat head becomes a bottleneck.
- Add Suphx-style oracle/global reward prediction as auxiliary training, not as the first serving path.

## Where The Project Actually Is

As of 2026-08-25. Update this section on any promotion or campaign change.

**Trainer.** On-policy PPO self-play, `fh-mj-train-b2b`. Dense per-hand Chongci score-delta
reward (score/1000), `gamma=0.99`, `lr=2e-5`, entropy 0, 2 PPO epochs, 320 matches/iter,
symmetric all-four self-play from a warm start.

**Champion.** `chongci_b2b_anchor075_restart_iter075`
(`ai/checkpoints/anchors/b2b-anchor075-restart-iter075.pt`). Line, each step confirmed on a
fresh unspent window at 1500 paired seeds per side:
`deep4 iter_275 -> B2b iter_075 (+0.0408) -> restart-iter075 (+0.0254)`.

**Promotion.** Pre-registered gate only: screenings on a shared window, a kill rule fixed
before launch, one selection, one confirmation on a window no prior lap has spent. No
optional stopping, no substitution after seeing results. Screening CIs (≈±0.07) cannot
resolve +0.03-level effects, so confirmation is the step that finds a winner.

**Campaign closed 2026-08-06: local recipe saturation** — a statement about this recipe,
not an architecture or RL ceiling. Four confirmations against restart-iter075 failed to
clear it (restart r2 null, deep16-ReZero null, gru-width unconfirmed, data-scale-960 null).
Training reopens only for new information, a genuinely different objective, or
evidence-backed auxiliary changes.

Full record:
[`worklog/rl-experiment/chongci-rl-experiment-progress.md`](../../worklog/rl-experiment/chongci-rl-experiment-progress.md).

## Stage 0: Working Vocabulary

Goal: understand the words before touching algorithms.

Materials:

- [Hugging Face Deep RL Course: Introduction to Deep RL](https://huggingface.co/learn/deep-rl-course/en/unit1/introduction)
- [Gymnasium: Basic Usage](https://gymnasium.farama.org/main/introduction/basic_usage/)
- [Gymnasium: Create a Custom Environment](https://gymnasium.farama.org/main/introduction/create_custom_env/)

Learn:

- agent, environment, state, observation, action, reward, return
- MDP vs POMDP
- policy, value function, Q function, advantage
- trajectory, episode, rollout

Mahjong exercise:

- Map `SeatObservation` to observation, full hidden `GameState` to state, `action_id` to action, and terminal payout to return.
- Explain why Fenghua Mahjong is a POMDP: opponents' concealed hands and wall order are hidden.

## Stage 1: Tabular RL Foundations

Goal: understand value learning without neural networks.

Materials:

- [Hugging Face Deep RL Course: Q-Learning](https://huggingface.co/learn/deep-rl-course/en/unit2/introduction)
- [Gymnasium: Training an Agent](https://gymnasium.farama.org/main/introduction/train_agent/)
- [Gymnasium Tutorial: Training Agents with Action Masking](https://gymnasium.farama.org/main/tutorials/training_agents/action_masking_taxi/)
- Optional classic reference: [Sutton & Barto, Reinforcement Learning: An Introduction](https://incompleteideas.net/book/the-book-2nd.html), chapters 4-6

Learn:

- dynamic programming
- Monte Carlo returns
- TD learning
- SARSA and Q-learning
- bootstrapping vs full-return learning

Mahjong exercise:

- Take one generated trajectory and manually backfill the terminal payout to every decision.
- Compare learning from final payout against learning from a next-state value estimate.

## Stage 2: Deep RL Basics

Goal: understand how neural networks replace tables.

Materials:

- [PyTorch official DQN tutorial](https://docs.pytorch.org/tutorials/intermediate/reinforcement_q_learning.html)
- [TorchRL Tutorials](https://docs.pytorch.org/rl/main/tutorials/index.html)
- [CleanRL Documentation](https://docs.cleanrl.dev/)
- [Stable-Baselines3: Reinforcement Learning Tips and Tricks](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html)

Learn:

- replay buffers
- target networks
- policy gradient
- actor-critic
- action masking
- why discrete vs continuous action spaces change algorithm choice

Mahjong exercise:

- Read the current `ReplayBuffer`, `PolicyValueNet`, and `BehaviorCloningTrainer`.
- Write notes on why this project has a discrete masked action space instead of a continuous control problem.

## Stage 3: Imitation Learning And Behavior Cloning

Goal: get a useful agent before "real RL."

Materials:

- [imitation documentation: Behavioral Cloning](https://imitation.readthedocs.io/en/latest/algorithms/bc.html)
- [imitation tutorial: Train BC on Demonstrations](https://imitation.readthedocs.io/en/latest/tutorials/1_train_bc.html)
- [Minari documentation](https://minari.farama.org/main/)
- Local plan: [Phase 3A BC Pipeline](../../worklog/plans/2026-03-26-phase3a-bc-pipeline.md)

Learn:

- supervised policy learning
- cross-entropy over expert actions
- train/validation split
- top-1 and top-3 action agreement
- dataset bias

Mahjong exercise:

- Generate heuristic trajectories through the Go bridge.
- Train behavior cloning.
- Evaluate exact/top-3 agreement, then break agreement down by discard, chii, pon, kan, win, and pass.

## Stage 4: Mahjong-Specific Deep RL

Goal: understand why Suphx is the main reference.

Materials:

- [Suphx paper page](https://www.microsoft.com/en-us/research/publication/suphx-mastering-mahjong-with-deep-reinforcement-learning/)
- [Suphx project page](https://www.microsoft.com/en-us/research/project/suphx-mastering-mahjong-with-deep-reinforcement-learning/)
- Local report: [Suphx](./01-suphx.md)

Learn:

- supervised pretraining before RL
- discard-first training
- global reward prediction
- oracle guiding
- runtime policy adaptation
- no-pooling tile encoders

Mahjong exercise:

- Inspect `PolicyValueNet` and verify that the default encoder preserves tile-position semantics.
- Keep the v1 model as a no-pooling residual CNN over `39 x 42 x 1` tile planes plus scalar features.

## Stage 5: Mortal-Style Offline Q/Value Learning

Goal: improve beyond imitation while still using fixed operation-level datasets.

Materials:

- [Offline RL Hands-On](https://arxiv.org/abs/2011.14379)
- [Implicit Q-Learning](https://arxiv.org/abs/2110.06169)
- [TD3+BC / A Minimalist Approach to Offline RL](https://arxiv.org/abs/2106.06860)
- [Minari documentation](https://minari.farama.org/main/)
- [d3rlpy documentation](https://d3rlpy.readthedocs.io/en/stable/)
- [d3rlpy IQL API reference](https://d3rlpy.readthedocs.io/en/stable/references/algos.html#iql)

Learn:

- offline dataset coverage
- out-of-distribution action overestimation
- conservative policy improvement
- advantage-weighted behavior cloning
- why behavior cloning remains a serious baseline
- Q/value/policy separation
- why a Q head should predict reward-scaled value, not copied policy logits

Mahjong exercise:

- Add dataset manifests: seed range, policy source, commit SHA, action count, and observation shape.
- Run discrete IQL as the operation-level Q/value learner for this stage.
- Compare IQL checkpoints against behavior cloning and heuristic baselines on the same duplicate-seat seeds.
- Keep advantage-weighted behavior cloning and one-step conservative offline Q as ablations.
- Do not promote a checkpoint based on lower training loss alone; promote only by duplicate-seat match reward and large-loss control.

**A risk or auxiliary head is not usable until it is calibrated.** Require AUC above random,
monotonic risk bands, and acceptable severity error before wiring it into serving or a
promotion gate; coefficient sweeps do not substitute. Every Chongci large-loss head tried
here ranked at chance (AUC 0.4998, 0.5096, 0.4990). Details:
[`worklog/rl-experiment/20260825-chongci-iql-era-experiment-ledger.md`](../../worklog/rl-experiment/20260825-chongci-iql-era-experiment-ledger.md).

## Stage 6: Rewards And Credit Assignment

Goal: choose reward targets that fit Mahjong.

Materials:

- [TD or not TD](https://openreview.net/forum?id=HyiAuyb0b)
- [TD or not TD project page](https://lmbweb.informatik.uni-freiburg.de/Publications/2018/AB18/)
- [Stable-Baselines3: Tips on Reward Engineering and Evaluation](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html)
- [Gymnasium: Handling Time Limits](https://gymnasium.farama.org/main/tutorials/gymnasium_basics/handling_time_limits/)
- Local report: [TD or not TD](./06-td-or-not-td.md)

Learn:

- Monte Carlo vs TD targets
- sparse reward problems
- delayed reward
- value-head instability

Mahjong exercise:

- Start with terminal round payout as the value target.
- For Chongci, use final match net score as the main value target.
- Add optional win/loss or fan/score shaping only as ablations.
- Use discounted terminal returns for every operation-level transition before experimenting with one-step TD bootstrapping.

## Stage 7: POMDPs, Memory, And Oracle Training

Goal: handle hidden information without cheating.

Materials:

- [Variational Oracle Guiding, OpenReview](https://openreview.net/forum?id=pjqqxepwoMy)
- [Microsoft Research VLOG page](https://www.microsoft.com/en-us/research/publication/variational-oracle-guiding-for-reinforcement-learning/)
- [PettingZoo AEC API](https://pettingzoo.farama.org/main/api/aec/)
- [PettingZoo Environment Creation Tutorial](https://pettingzoo.farama.org/main/tutorials/custom_environment/)
- [DTQN](https://arxiv.org/abs/2206.01078)
- [GTrXL](https://arxiv.org/abs/1910.06764)

Learn:

- partial observability
- action-observation history
- transformer memory
- privileged information during training only
- train/inference mismatch

Mahjong exercise:

- Design oracle-only auxiliary targets: opponent concealed tile histograms, wall composition summaries, and hidden danger counts.
- Add tests proving deployed observations still leak no hidden opponent tiles.

## Stage 8: Second-Generation Mahjong Agent

Goal: understand future architecture choices.

Materials:

- Local report: [Tjong](./followups/15-tjong.md)
- [Tjong publication record](https://digitalcommons.njit.edu/fac_pubs/267/)
- [Rethinking Decision Transformer via HRL](https://proceedings.mlr.press/v235/ma24b.html)

Learn:

- hierarchical decision-making
- sequence models for long-context strategy
- fan/score backward shaping
- why one flat action head may be too blunt later

Mahjong exercise:

- Keep v1 as a flat 204-action policy for stability.
- Later split the policy into a hierarchy: decision family first, tile/meld choice second.

## Development Plan

1. Validate current baseline:
   - Run Go tests, Python tests, mock BC pipeline, and a tiny real-bridge pipeline.
2. Build data pipeline v1:
   - Generate deterministic heuristic self-play trajectories.
   - Save JSONL plus manifest.
   - Use fixed seed splits for train, validation, and evaluation.
3. Train BC v1:
   - Train current `PolicyValueNet`.
   - Report loss, value loss, exact agreement, top-3 agreement, and action-family agreement.
4. Upgrade model v1:
   - Use a no-pooling residual CNN plus scalar encoder.
   - Keep masked logits mandatory.
5. Add duplicate evaluation:
   - Use the same wall seeds with rotated seats against the heuristic baseline.
   - Track EV, win rate, large-loss rate, and action frequencies.
6. Add visible look-ahead features:
   - Implemented in the 58-scalar observation schema.
   - Keep `overall shanten` at scalar index 25.
   - Route-specific shanten, ukeire, wild preservation, score potential, and public danger heuristics now occupy scalar indices 29-41.
   - Chongci match/risk context now occupies scalar indices 42-57.
7. Add Mortal-style operation-level Q/value learning:
   - Use discrete IQL as the default reward learner.
   - Train Q, value, and policy from every discard/reaction/kan/win/pass operation.
   - Use final hand or Chongci match reward as the delayed target.
   - Keep behavior-cloning regularization.
   - Train direct paired-trace first-divergence reward-delta scorers before repeating same-state branch-label sweeps.
   - Add visible trajectory context and compact pre-divergence sequence rows to first-divergence scorers when holdout preflight shows seed-window overfitting.
   - Use source-heldout paired-trace preflight as the screen for sequence scorers; do not promote from train-window or full-report gains.
   - If a sequence scorer only barely passes source-heldout preflight, run a fresh independent seed-window preflight before any duplicate-seat or guarded-serving evaluation.
   - If robust source-balanced training moves the failure between sources, stop coefficient changes and build a larger multi-source dataset with whole-source heldout model selection.
   - Keep exact branch-CF shards as auxiliary supervision and diagnostics, not as the main promotion signal.
   - Promote only if duplicate evaluation improves over BC and heuristic baselines.
8. Add mixed self-play:
   - Generate random wall seeds and let checkpoint agents play through full matches.
   - Use a frozen opponent pool: heuristic, BC, current best IQL, and older checkpoints.
   - Store every operation transition from every learning seat.
   - Retrain IQL from mixed self-play plus heuristic data.
   - Promote checkpoints by fixed-seed duplicate arena results.
9. Add live serving:
   - Serve the Python/PyTorch model first.
   - Go still validates every returned action.
   - Keep hidden information out of deployed observations.

## Design Defaults

- Objective: expected score from each operation.
- Chongci training objective: dense per-hand score delta. Final match net score is the
  evaluation metric, deliberately kept independent of the training reward.
- Model: no-pooling residual CNN — 96 channels, 4 residual blocks, plus an event GRU — not
  a transformer.
- Bootstrap: behavior cloning.
- RL: on-policy PPO self-play, symmetric all-four, from a warm start.
- Evaluation: duplicate fixed-seed arena with pre-registered gates on fresh unspent
  windows, not raw win rate.
- Serving: Python inference service, not Go-native model inference.

## Acceptance Criteria

- You can explain MDP/POMDP, return, value, Q, policy, behavior cloning, offline RL, and oracle training in Mahjong terms.
- The BC pipeline trains from generated heuristic trajectories and produces deterministic evaluation reports.
- The agent never emits illegal actions after masking.
- A checkpoint is only considered better if it improves duplicate-seat evaluation against the heuristic baseline.
- Hidden information is never present in deployed policy inputs.

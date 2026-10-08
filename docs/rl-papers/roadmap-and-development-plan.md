# RL Study Roadmap

A reading-and-exercise path from RL basics to Mahjong-specific agents, tied to this codebase. Read
the linked material for each stage, then do the exercise before moving on. The path favors
maintained docs and written tutorials over video lectures.

The agent this repo actually ships is described in [`../ai-player.md`](../ai-player.md); the
results of trying these ideas are in [`../ai-findings.md`](../ai-findings.md).

## Build order

The Mortal-style sequence the codebase followed:

1. simulator correctness
2. heuristic trajectories
3. behavior cloning
4. duplicate evaluation
5. operation-level Q/value learning (offline)
6. online self-play (PPO)
7. live AI integration
8. oracle guiding, privileged critics, and auxiliary heads once the core loop is stable

Operation-level means every legal operation at every decision — discard, pass, win, chii, pon,
kan, haitei accept/refuse — is a training transition, not one sample per hand. Rewards are still
delayed: hand payout for classic Fenghua, match net score for Chongci.

## Code-first loop

1. Generate a small deterministic dataset: `fh-mj-generate-data`.
2. Behavior-clone it: `fh-mj-train-bc`.
3. Evaluate exact/top-3/action-family agreement: `fh-mj-evaluate`.
4. Run an offline value learner: `fh-mj-train-iql` (the historical baseline).
5. Run online self-play: `fh-mj-train-b2b`.
6. Gate with duplicate-seat evaluation and `fh-mj-compare` ([`../ai-evaluation.md`](../ai-evaluation.md)).

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
- Local code: `fh-mj-generate-data`, `fh-mj-train-bc` (see `ai/MODULES.md`)

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

## Acceptance Criteria

- You can explain MDP/POMDP, return, value, Q, policy, behavior cloning, offline RL, and oracle training in Mahjong terms.
- The BC pipeline trains from generated heuristic trajectories and produces deterministic evaluation reports.
- The agent never emits illegal actions after masking.
- A checkpoint is only considered better if it improves duplicate-seat evaluation against the heuristic baseline.
- Hidden information is never present in deployed policy inputs.

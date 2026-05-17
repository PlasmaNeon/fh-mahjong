# RL Learning Roadmap And Mahjong AI Development Plan

This roadmap is a self-contained study-and-build path for the Fenghua Mahjong AI work. Use the linked article or documentation material in each stage, then do the repo-specific exercise before moving on.

The required learning path intentionally avoids video lectures. Classic papers and books still appear where they are the right source, but the default path favors maintained docs, written tutorials, and recent implementation references.

The development direction is:

1. simulator correctness
2. heuristic trajectories
3. behavior cloning
4. duplicate evaluation
5. conservative offline RL
6. checkpoint self-play
7. live AI integration

## Code-First Loop

Use this loop when you want the code to drive the learning:

1. Generate a small deterministic trajectory dataset with `fh_mahjong_ai.scripts.generate_data`.
2. Train behavior cloning with `fh_mahjong_ai.scripts.train_bc`.
3. Evaluate exact/top-3/action-family agreement with `fh_mahjong_ai.scripts.evaluate`.
4. Train the first conservative value-learning pass with `fh_mahjong_ai.scripts.train_offline_q`.
5. Promote a checkpoint only after duplicate-seat evaluation improves against the heuristic baseline.

The current offline Q-learning trainer is intentionally conservative: it treats the masked action head as Q-values, uses TD targets `r + gamma max_a Q_target(s', a)`, adds a CQL-style penalty against unsupported legal actions, and keeps a behavior-cloning regularizer so the policy does not drift too far from the generated data.

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
- Local plan: [Phase 3A BC Pipeline](../superpowers/plans/2026-03-26-phase3a-bc-pipeline.md)

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

## Stage 5: Offline RL

Goal: improve beyond imitation without unstable online self-play.

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

Mahjong exercise:

- Add dataset manifests: seed range, policy source, commit SHA, action count, and observation shape.
- Run the conservative offline Q-learning scaffold as the first code-level TD exercise.
- Treat advantage-weighted behavior cloning or discrete IQL-style training as the next offline RL candidate, not naive max-Q over all 204 actions.

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
- Add optional win/loss bonus only as an ablation.
- Defer multi-round placement reward until single-round EV evaluation is stable.

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
   - Implemented in the 42-scalar observation schema.
   - Keep `overall shanten` at scalar index 25.
   - Route-specific shanten, ukeire, wild preservation, score potential, and public danger heuristics now occupy scalar indices 29-41.
7. Add offline RL:
   - Start with advantage-weighted behavior cloning or discrete IQL-style training.
   - Keep behavior-cloning regularization.
   - Promote only if duplicate evaluation improves over BC.
8. Add self-play and live serving:
   - Use frozen checkpoint pools.
   - Promote checkpoints by fixed-seed arena results.
   - Serve the Python/PyTorch model first; Go still validates every returned action.

## Design Defaults

- First objective: single-round expected payout.
- First model: no-pooling residual CNN, not transformer.
- First learning method: behavior cloning, not PPO.
- First RL improvement: conservative offline RL, not from-scratch online RL.
- First evaluation: duplicate fixed-seed arena, not raw random win rate.
- First serving path: Python inference service, not Go-native model inference.

## Acceptance Criteria

- You can explain MDP/POMDP, return, value, Q, policy, behavior cloning, offline RL, and oracle training in Mahjong terms.
- The BC pipeline trains from generated heuristic trajectories and produces deterministic evaluation reports.
- The agent never emits illegal actions after masking.
- A checkpoint is only considered better if it improves duplicate-seat evaluation against the heuristic baseline.
- Hidden information is never present in deployed policy inputs.

# RL Implementation Takeaways for fh-mahjong

This file turns the reading notes into concrete guidance for this repo.

## Best near-term training pipeline

1. Generate heuristic self-play trajectories with the Go simulator.
2. Train a behavior cloning policy on those trajectories.
3. Evaluate with fixed seeds and duplicate-style runs.
4. Train Mortal-style operation-level Q/value/policy updates with discrete IQL.
5. Generate mixed checkpoint self-play trajectories.
6. Promote checkpoints only through fixed-seed duplicate arenas.

The preferred direction is now Mortal-style first: every discard, pass, chii, pon, kan, win, and haitei decision is a training transition. The reward target remains delayed, but the Q/value/policy update is attached to the operation state that caused it.

## Best near-term model choice

For a strong and practical v1, use:

- a no-pooling residual CNN over tile planes
- scalar context features alongside the planes
- a dueling Q head for reward-based offline RL so state value and action advantage are separated
- channel attention as an explicit ablation, not an automatic default for old policy checkpoints
- the flat 204-action masked head until the training loop proves it needs split heads

This is closer to Mortal's operation-level Q-value style while still borrowing Suphx's tile-plane discipline. Split action heads remain a later optimization, not the first blocker.

## Best next-generation model direction

Once the training pipeline is stable, the most promising newer direction is:

- a history-aware transformer
- likely hierarchical
- trained with visible observation history plus optional oracle-only training heads

The most relevant references for that path are DTQN, GTrXL, and Tjong.

## Oracle / privileged-information training

This should stay on the roadmap. Practical oracle targets for this repo include:

- opponent concealed tile histograms
- wall composition summaries by tile face
- hidden dangerous-tile counts
- future draw-category summaries

These targets should be training-only. The deployed policy should still consume only legal visible observations exported by `rlenv`.

## Reward design ideas

Near term:

- use terminal round payout as the first reward target for the current single-round Fenghua mode
- use final match net score as the main reward target for Chongci mode
- keep optional small terminal win/loss bonus as an ablation, not the default objective
- train reward-based updates from a BC checkpoint and preserve BC regularization during offline policy improvement
- keep critic/Q training separate from the deployed policy logits so TD targets do not overwrite imitation quality
- do not initialize a Q head from policy logits by default; logits rank actions but are not calibrated payout predictions
- prefer discounted Monte Carlo terminal-return targets for the first offline reward learner: `gamma ** steps_to_done * terminal_round_payout`
- keep one-step TD as an explicit experiment after value calibration improves
- add a conservative Q penalty as an explicit offline-RL ablation, following Mortal's preference for conservative offline Q estimates
- do not repeat sparse first-divergence replay weighting unless the objective changes; filtered Chongci runs kept only 11 to 16 added risk-context rows, and explicit sparse-row oversampling still did not improve the selected-window gate
- shared-gradient large-loss auxiliary training is not automatically safer: the first all-anchor target-side run was active, improved EV versus replay-only all-anchor runs, but regressed selected-window large-loss rate
- lowering those auxiliary coefficients reproduced the same rejected selected-window behavior, so further coefficient sweeps are lower value than changing the objective or serving-time use of risk estimates
- the first calibrated large-loss auxiliary heads should not be used as serving guards: probability AUC was near random and predicted risk bands had nearly flat realized large-loss rates
- next Chongci risk-learning design is action-conditioned and critic-side: predict tail probability/severity for each legal action using visible match-history inputs, then calibrate before any serving-time guard. The action-conditioned heads and gathered dataset-action loss are implemented, but the first calibration-only run without richer history failed (`large-loss AUC 0.4998`), the first 58-scalar visible-context rerun still failed (`large-loss AUC 0.5096`), and balanced positive/negative risk-only training also failed ranking (`large-loss AUC 0.4990`). The next attempt needs stronger supervision such as paired counterfactual labels, per-action score-delta targets, or large-loss-enriched failing-window data.

Later:

- add multi-round or match-level value prediction when a placement contest mode exists
- use a Mortal-style global ranking / placement predictor to convert score and rank trajectory into delta expected placement value
- for Chongci, prioritize a global placement/ranking auxiliary model over simply making the tile CNN deeper
- add backward-propagated score or fan shaping only after single-round EV evaluation is stable
- make placement-aware reward the main objective only for full-match or contest play, not the current single-round agent

## Feature engineering ideas

The reading strongly supports adding rule-engine look-ahead features, especially for discard decisions:

- overall shanten (already implemented in observation scalar index 25)
- route-specific shanten (implemented in observation scalar indices 29-31)
- useful tile counts / ukeire (implemented in scalar indices 32 and 34)
- wild-preservation signals (implemented in scalar indices 36-37)
- estimated score potential (implemented in scalar index 38)
- public danger heuristics (implemented in scalar indices 39-41)
- Chongci match context: mode flag, hand progress, rank strength, leader pressure, large-loss safety, own bust safety, opponent large-loss pressure, normalized score/net progress, relative score gaps, next-rank pressure, lower-rank cushion, and public current-hand threat (implemented in scalar indices 42-57)

These features are compatible with the current Go heuristic analysis and should help both BC and RL.

## Evaluation ideas

- fixed-seed duplicate evaluation
- rotate seat assignments on the same wall
- track round EV, deal-in rate, win rate, and large-loss rate
- compare new checkpoints against the heuristic bot and a pool of frozen older checkpoints
- for Chongci, prefer mean final net reward, positive-reward rate, large-loss rate, and per-seat breakdown over raw win rate

## Recommended order of work

1. Keep the current best BC/IQL checkpoints as frozen baselines.
2. Implement mixed self-play trajectory generation with checkpoint seats and heuristic seats.
3. Store every operation-level transition from self-play, including policy source and checkpoint metadata.
4. Train discrete IQL on heuristic plus mixed self-play data by passing repeated `--data` inputs instead of merging or discarding older datasets.
5. Evaluate on fixed Chongci duplicate arenas against heuristic, BC, current IQL, and older checkpoint pools.
6. Promote only if mean net reward improves and large-loss rate does not regress.
7. Add oracle-only auxiliary heads after the operation-level self-play loop is stable.
8. Explore transformer and hierarchical models after the pipeline is stable.

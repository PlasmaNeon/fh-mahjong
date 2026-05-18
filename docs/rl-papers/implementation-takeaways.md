# RL Implementation Takeaways for fh-mahjong

This file turns the reading notes into concrete guidance for this repo.

## Best near-term training pipeline

1. Generate heuristic self-play trajectories with the Go simulator.
2. Train a behavior cloning policy on those trajectories.
3. Evaluate with fixed seeds and duplicate-style runs.
4. If BC plateaus, add an offline improvement stage such as IQL-style conservative policy improvement.
5. Only after that, move into online self-play RL with checkpoint arenas.

## Best near-term model choice

For a strong and practical v1, use:

- a no-pooling residual CNN over tile planes
- scalar context features alongside the planes
- split action heads by decision type where helpful

This is closer to the Suphx design and is a lower-risk fit for the current pipeline than a transformer-first approach.

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
- keep optional small terminal win/loss bonus as an ablation, not the default objective
- train reward-based updates from a BC checkpoint and preserve BC regularization during offline policy improvement
- keep critic/Q training separate from the deployed policy logits so TD targets do not overwrite imitation quality
- do not initialize a Q head from policy logits by default; logits rank actions but are not calibrated payout predictions
- prefer discounted Monte Carlo terminal-return targets for the first offline reward learner: `gamma ** steps_to_done * terminal_round_payout`
- keep one-step TD as an explicit experiment after value calibration improves
- add a conservative Q penalty as an explicit offline-RL ablation, following Mortal's preference for conservative offline Q estimates

Later:

- add multi-round or match-level value prediction when a placement contest mode exists
- use a Mortal-style global ranking / placement predictor to convert score and rank trajectory into delta expected placement value
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

These features are compatible with the current Go heuristic analysis and should help both BC and RL.

## Evaluation ideas

- fixed-seed duplicate evaluation
- rotate seat assignments on the same wall
- track round EV, deal-in rate, win rate, and large-loss rate
- compare new checkpoints against the heuristic bot and a pool of frozen older checkpoints

## Recommended order of work

1. Strengthen behavior cloning training and evaluation.
2. Rebuild the heuristic dataset with the expanded 42-scalar observation schema.
3. Retrain BC from scratch on the new observations and rerun duplicate evaluation.
4. Add oracle-only auxiliary heads.
5. Add online self-play with checkpoint promotion.
6. Explore transformer and hierarchical models after the pipeline is stable.

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

- terminal round payout
- optional small terminal win/loss bonus

Later:

- multi-round or match-level value prediction
- backward-propagated score or fan shaping
- placement-aware reward if full-match play becomes the main objective

## Feature engineering ideas

The reading strongly supports adding rule-engine look-ahead features, especially for discard decisions:

- overall shanten
- route-specific shanten
- useful tile counts
- wild-preservation signals
- estimated score potential
- danger or deal-in heuristics

These features are compatible with the current Go heuristic analysis and should help both BC and RL.

## Evaluation ideas

- fixed-seed duplicate evaluation
- rotate seat assignments on the same wall
- track round EV, deal-in rate, win rate, and large-loss rate
- compare new checkpoints against the heuristic bot and a pool of frozen older checkpoints

## Recommended order of work

1. Strengthen behavior cloning training and evaluation.
2. Add richer heuristic and look-ahead features to observations or auxiliary inputs.
3. Add oracle-only auxiliary heads.
4. Add conservative offline RL after BC.
5. Add online self-play with checkpoint promotion.
6. Explore transformer and hierarchical models after the pipeline is stable.

# Read Report: TD3+BC

- Original paper: [A Minimalist Approach to Offline Reinforcement Learning](https://arxiv.org/abs/2106.06860)

## Why it matters

This paper shows that a simple "stay near the behavior policy" bias can go a long way in offline RL.

## Main ideas

- keep the RL algorithm simple
- normalize inputs well
- add an explicit behavior cloning term so the learned policy does not drift too far from the data

## What seems most useful for fh-mahjong

- Even if we do not use TD3+BC literally because Mahjong is discrete, the principle is strong:
  keep the policy close to strong heuristic data early.
- This is a good mindset for any offline improvement stage after BC.

## Bottom line

The exact algorithm may differ for discrete Mahjong actions, but the lesson is important: conservative policy improvement is safer than aggressive extrapolation.

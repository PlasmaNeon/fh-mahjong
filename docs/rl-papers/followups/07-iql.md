# Read Report: Implicit Q-Learning

- Original paper: [Offline Reinforcement Learning with Implicit Q-Learning](https://arxiv.org/abs/2110.06169)

## Why it matters

IQL is one of the most practical follow-up algorithms for offline RL because it avoids directly maximizing over actions outside the dataset, which is exactly where many offline methods fail.

## Main ideas

- learn values from observed actions only
- avoid explicit out-of-distribution action queries
- extract a policy with advantage-weighted behavior cloning

## What seems most useful for fh-mahjong

- If BC plateaus, IQL is a strong next step for heuristic self-play data.
- It fits our setting better than naive offline Q-learning because Mahjong action coverage is sparse and structured.

## Bottom line

If we add an offline RL stage after BC, IQL should be near the top of the candidate list.

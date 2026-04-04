# Read Report: GTrXL

- Original paper: [Stabilizing Transformers for Reinforcement Learning](https://arxiv.org/abs/1910.06764)

## Why it matters

Transformers are attractive for memory-heavy RL, but vanilla transformer training can be unstable. GTrXL shows a more RL-friendly transformer design.

## Main ideas

- gated residual pathways
- architectural changes that make transformer training more stable under RL objectives
- better long-range credit assignment than short-memory baselines

## What seems most useful for fh-mahjong

- If we move to a transformer policy, GTrXL is a better starting point than dropping a plain transformer into the trainer.
- It is especially relevant once we care about longer betting, defense, and opponent-model patterns over time.

## Bottom line

GTrXL is less about Mahjong directly and more about choosing a transformer architecture that is realistic to train in RL.

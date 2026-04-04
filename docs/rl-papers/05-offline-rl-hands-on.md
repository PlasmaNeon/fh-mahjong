# Read Report: Offline Reinforcement Learning Hands-On

- Original paper: [Offline Reinforcement Learning Hands-On](https://arxiv.org/abs/2011.14379)

## What problem it tackles

Offline RL tries to learn from a fixed dataset without online interaction. The challenge is that value methods can overestimate actions that the dataset never really covers.

## Main ideas

The paper is a practical survey and tutorial. The most useful message is not one algorithm; it is that offline RL quality depends heavily on:

- dataset quality
- return quality
- action coverage and diversity

It also highlights that behavior cloning remains a strong baseline.

## Why it matters

This paper strongly supports our current roadmap:

1. build a good heuristic bot
2. generate trajectories
3. do behavior cloning first
4. only then add heavier RL methods

## What seems most useful for fh-mahjong

- Do not expect offline RL to rescue a weak dataset.
- Mix multiple policies when collecting data so the model sees more states and action styles.
- Treat behavior cloning as a serious benchmark, not a throwaway pre-step.

## Useful cautions

- Offline RL can become unstable when the model learns to prefer out-of-distribution actions.
- A clever algorithm is less important than having strong, diverse data.

## Bottom line

For this project, this paper mostly says: get the data pipeline right first, and do not skip the strong BC baseline.

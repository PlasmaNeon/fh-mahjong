# Read Report: Suphx

- Original paper: [Suphx: Mastering Mahjong with Deep Reinforcement Learning](https://arxiv.org/abs/2003.13590)
- Project page: [Microsoft Research - Suphx](https://www.microsoft.com/en-us/research/project/suphx-mastering-mahjong-with-deep-reinforcement-learning/)

## What problem it tackles

Mahjong is hard for RL because it is a four-player imperfect-information game with sparse rewards, long horizons, huge action branching, and strong domain structure around hand value and danger.

## Main ideas

Suphx combines three training tricks with a practical engineering stack:

1. Supervised pretraining on strong game logs.
2. Self-play reinforcement learning after pretraining.
3. Three Mahjong-specific ideas:
   - global reward prediction
   - oracle guiding
   - run-time policy adaptation

The system also separates decisions by action type instead of forcing one network to solve every choice equally well.

## Why it matters

This is still the most directly relevant paper for building a strong Mahjong agent. It is not just "deep RL works"; it shows which Mahjong-specific pieces are worth the extra complexity.

## What seems most useful for fh-mahjong

- Train the discard policy first. Suphx mainly improves discard decisions with RL before spending equal effort on every other action type.
- Use training-only privileged information. During training, the model can benefit from hidden-state targets even though inference must use only visible information.
- Add rule-engine look-ahead features. Suphx uses many future-looking features, which maps naturally to our shanten, ukeire, hand-route, and score-potential calculations.
- Avoid image-style pooling. Tile positions are semantic, so aggressive pooling over tile columns is a bad inductive bias.
- Consider long-horizon rewards. A separate reward predictor can help when final placement or multi-round outcomes matter more than one local action.

## Useful cautions

- Suphx is a very large system; we should copy the ideas, not the full scale.
- Its reward structure is tuned to riichi placement, not Fenghua round EV directly.
- Run-time policy adaptation is interesting, but it is not the first thing we need. A stable offline and self-play pipeline matters more.

## Bottom line

For this repo, the most valuable Suphx lessons are:

- discard-first training
- no-pooling tile encoder
- rule-based look-ahead features
- training-only oracle information
- reward shaping beyond immediate payoff

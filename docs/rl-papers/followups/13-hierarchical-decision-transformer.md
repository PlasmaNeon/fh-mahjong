# Read Report: Rethinking Decision Transformer via Hierarchical Reinforcement Learning

- Original paper: [Rethinking Decision Transformer via Hierarchical Reinforcement Learning](https://proceedings.mlr.press/v235/ma24b.html)

## Why it matters

Decision Transformer is attractive for offline sequence modeling, but plain sequence prediction is not always enough for difficult long-horizon control. This paper argues that hierarchical structure helps.

## Main ideas

- introduce hierarchy into the decision-transformer style setup
- improve trajectory stitching and long-horizon planning
- show that pure flat sequence models can struggle to combine useful sub-trajectories

## What seems most useful for fh-mahjong

- Mahjong decisions are naturally hierarchical:
  - decide whether to call, pass, or win
  - then decide which tile or meld pattern
- If we later explore transformer-based offline RL, hierarchy is likely to matter.

## Bottom line

This is more useful as architectural guidance than as a first implementation target, but it reinforces that one flat action head may be leaving performance on the table.

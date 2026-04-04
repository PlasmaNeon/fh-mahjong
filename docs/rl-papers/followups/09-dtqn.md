# Read Report: DTQN

- Original paper: [Deep Transformer Q-Networks for Partially Observable Reinforcement Learning](https://arxiv.org/abs/2206.01078)

## Why it matters

Mahjong is partially observable and history matters. DTQN is directly about replacing short-memory agents with transformer-based memory for POMDPs.

## Main ideas

- use a transformer over action-observation history
- let the model learn its own memory rather than relying only on a recurrent hidden state
- improve stability and performance in partially observable domains

## What seems most useful for fh-mahjong

- A history-aware model could track discard rhythms, call patterns, and danger signals better than a pure snapshot model.
- This is a strong candidate for a second-generation model after the first CNN pipeline is stable.

## Bottom line

If we want a more modern model than a static residual CNN, DTQN is one of the most relevant directions.

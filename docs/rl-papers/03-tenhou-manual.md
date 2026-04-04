# Read Report: Tenhou Manual

- Original source: [Tenhou Manual](https://tenhou.net/man/)

## What it is

This is not a research paper. It is the platform manual for Tenhou, a major online Mahjong server.

## Why it still matters

It is useful as an operational reference for:

- replay formats
- wall generation and seeds
- ranking conventions
- client and server semantics seen in real play data

## What seems most useful for fh-mahjong

- Fixed-seed reproducibility matters. The manual documents seeded wall generation, which is useful for replay exactness and duplicate evaluation.
- Real-platform replay structure is a good reminder that training and replay pipelines should preserve enough information to reconstruct a game exactly.
- If we later ingest external paipu, this kind of document is the bridge between raw logs and simulator-compatible trajectories.

## Useful cautions

- This is not a method paper, so it should not drive our model design.
- Tenhou conventions are riichi-oriented and do not directly transfer to Fenghua scoring or action space.

## Bottom line

The Tenhou manual is most useful for reproducibility and replay tooling, not for choosing the learning algorithm.

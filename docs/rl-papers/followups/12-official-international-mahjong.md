# Read Report: Official International Mahjong

- Original paper: [Official International Mahjong: A New Playground for AI Research](https://www.mdpi.com/1999-4893/16/5/235)

## Why it matters

This paper is useful mainly because it discusses evaluation and benchmarking in Mahjong AI, not because it gives the best training algorithm.

## Main ideas

- formalize Mahjong as an AI benchmark
- emphasize controlled experimental settings
- use duplicate-style evaluation to reduce variance

## What seems most useful for fh-mahjong

- Evaluate agents on the same walls and rotated seat assignments.
- Compare round EV, placement, and deal-in rate under matched randomness instead of only raw win rate.

## Bottom line

This is a strong argument for duplicate evaluation in our future arena harness.

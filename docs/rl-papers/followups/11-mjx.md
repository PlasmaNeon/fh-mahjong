# Read Report: Mjx

- Original paper PDF: [Mjx: A framework for Mahjong AI research](https://ieee-cog.org/2022/assets/papers/paper_162.pdf)

## Why it matters

This paper is about infrastructure rather than policy learning, but that is important. Mahjong AI can become bottlenecked by simulator throughput long before the model itself is the bottleneck.

## Main ideas

- build a Mahjong research framework optimized for AI experimentation
- emphasize simulator speed, reproducibility, and external AI integration

## What seems most useful for fh-mahjong

- Keep the Go simulator fast and deterministic.
- Treat batched trajectory generation as a first-class engineering task.
- Avoid architectures that force expensive per-step cross-language overhead if we want large-scale self-play later.

## Bottom line

This paper supports the design we already chose: keep the authoritative simulator clean, deterministic, and efficient before chasing more model complexity.

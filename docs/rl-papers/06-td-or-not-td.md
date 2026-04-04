# Read Report: TD or not TD

- Original paper: [TD or not TD: Analyzing the Role of Temporal Differencing in Deep Reinforcement Learning](https://arxiv.org/abs/1806.01175)

## What problem it tackles

A common assumption is that temporal-difference methods are always better than Monte Carlo returns for deep RL. This paper tests that assumption directly.

## Main ideas

The paper shows that finite-horizon Monte Carlo targets can be much stronger than people often expect, especially when function approximation changes the tradeoffs from classic tabular RL.

## Why it matters

Mahjong has sparse, delayed rewards and long horizons. In that setting, a noisy critic can do more harm than good early on.

## What seems most useful for fh-mahjong

- Start simple with round-end or episode-end returns when possible.
- Do not rush into heavily bootstrapped critics just because that sounds more "advanced."
- Evaluate whether Monte Carlo style targets are already enough to move beyond BC.

## Useful cautions

- Pure Monte Carlo can still have high variance.
- The best choice may depend on whether we optimize round EV, full-game rank, or both.

## Bottom line

This paper is a strong reminder that simpler targets may be the right first choice for Mahjong RL, especially before the rest of the pipeline is mature.

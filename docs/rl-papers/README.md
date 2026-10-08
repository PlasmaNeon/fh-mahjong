# RL Paper Read Reports

Paper summaries for the Fenghua Mahjong AI. How these ideas landed in the repo is in
[`../ai-player.md`](../ai-player.md); what worked is in [`../ai-findings.md`](../ai-findings.md).

## Primary references

1. [Suphx](./01-suphx.md)
2. [Variational Oracle Guiding](./02-variational-oracle-guiding.md)
3. [Tenhou Manual](./03-tenhou-manual.md)
4. [CBAM](./04-cbam.md)
5. [Offline Reinforcement Learning Hands-On](./05-offline-rl-hands-on.md)
6. [TD or not TD](./06-td-or-not-td.md)

## Follow-up reading

7. [Implicit Q-Learning (IQL)](./followups/07-iql.md)
8. [TD3+BC / A Minimalist Approach to Offline RL](./followups/08-td3-bc.md)
9. [Deep Transformer Q-Networks (DTQN)](./followups/09-dtqn.md)
10. [GTrXL](./followups/10-gtrxl.md)
11. [Mjx](./followups/11-mjx.md)
12. [Official International Mahjong](./followups/12-official-international-mahjong.md)
13. [Rethinking Decision Transformer via HRL](./followups/13-hierarchical-decision-transformer.md)
14. [Privileged Information in POMDP RL](./followups/14-privileged-information-pomdp.md)
15. [Tjong](./followups/15-tjong.md)

## Other directions surveyed

Tested in 2026-07; results in [`../ai-findings.md`](../ai-findings.md).

| Direction | Source | Outcome here |
|---|---|---|
| Regret-based policy gradient (ACH, LuckyJ) | [Actor-Critic Policy Optimization in a Large-Scale Imperfect-Information Game](https://openreview.net/forum?id=DTXZqTNV5nW) | Failed; regret minimization has no convergence guarantee in 4-player games |
| Opponent-hand prediction as an auxiliary task | [DouZero+](https://arxiv.org/abs/2204.02558) | Shipped as the belief head in B2b |
| Exploitability and population training | [SP-PSRO](https://arxiv.org/pdf/2207.06541), [self-play survey](https://arxiv.org/pdf/2408.01072) | Champion not exploitable; snapshot-pool opponents neutral |
| Run-time policy adaptation (pMCPA) | [Suphx](https://arxiv.org/pdf/2003.13590) | Determinized search lost to the raw policy |
| Massive-actor Monte-Carlo self-play | [DouZero](https://arxiv.org/abs/2106.06135) | Validates self-play without human data; not run as such |
| Belief-state search (ReBeL, Student of Games) | [ReBeL](https://arxiv.org/abs/2007.13544) | Skipped: 2-player theory, out of reach on one GPU |

## Study path

[`roadmap-and-development-plan.md`](./roadmap-and-development-plan.md) is a reading-and-exercise
sequence from RL vocabulary to Mahjong-specific agents, tied to this codebase. Suggested order:
the roadmap, Suphx, Variational Oracle Guiding, Offline RL Hands-On, TD or not TD, IQL and TD3+BC,
DTQN and GTrXL, Tjong.

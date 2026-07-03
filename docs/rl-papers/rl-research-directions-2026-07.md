# RL Research Directions — Beyond Pure Self-Play (2026-07)

Literature sweep answering: *we mainly rely on self-play (all-4 symmetric PPO +
Suphx feature-dropout oracle scaffold) — is there a better way to get a stronger
agent?* Filtered hard through this project's constraints:

- **No human game corpus.** Fenghua mahjong has no Tenhou-equivalent logs;
  Suphx / Mortal / NAGA all bootstrapped from millions of human games. Our
  substitutes are the heuristic bot lineage (BC → IQL anchor) and self-play.
- **Single 4090 + 24 cores.** Methods needing TPU pods or belief-state search
  farms are out of reach; the batched-inference collector (PR #142) makes
  experience ~6× cheaper but does not change the class of affordable methods.
- **Production opponents are human** — i.e. adaptive exploiters, which makes
  robustness (exploitability) a first-class concern, not just mean placement
  vs a fixed anchor.

Current baseline for context: deep4 iter_120 student, paired +0.2958 vs the IQL
anchor (−0.0528), large_loss halved, in production since PR #136.

## Findings, ranked by fit

### 1. Regret-based policy optimization — ACH (LuckyJ) — *the method bet*

Tencent's **LuckyJ** is the strongest known mahjong AI (10.68 dan stable rank
on Tenhou — above Suphx and every human/AI with 1000+ expert-room games). Its
core is **Actor-Critic Hedge (ACH)**, ICLR 2022: replace PPO's
maximize-discounted-return objective with **minimizing weighted cumulative
counterfactual regret** in policy-gradient form.

Why it matters here: self-play PPO in imperfect-information games has **no
convergence guarantee** — it can cycle or converge to exploitable policies.
Regret minimization converges toward Nash. ACH is a *drop-in-class* change:
same collector, same network, different update rule — implementable as an
alternative loss next to `ppo_update` and A/B-able on identical collection.

- Paper: https://openreview.net/forum?id=DTXZqTNV5nW
  ("Actor-Critic Policy Optimization in a Large-Scale Imperfect-Information
  Game")
- LuckyJ coverage: https://www.hcitinfo.com/owfd4aums23q.html

### 2. Auxiliary belief head (opponent-hand prediction) — *best effort/payoff*

**DouZero+** improved its DouDizhu champion with **opponent modeling** (predict
hidden hands as an auxiliary task); belief modeling is also the foundation of
ReBeL / Student of Games. The elegant fit for us: **self-play already produces
the labels for free** — the 51ch oracle observation contains the opponents'
true concealed hands. Instead of only weaning the net off the oracle channels
(feature-dropout), add an **auxiliary head that predicts those channels from
the 39ch public observation**. The deployable net learns to *infer* hidden
information rather than merely live without it. Near-zero extra collection
cost; small model/loss change.

- DouZero+: https://arxiv.org/abs/2204.02558

### 3. Exploitability: measure it, then fix it — *derisks everything*

The PSRO / league literature is unanimous: pure self-play against the current
self yields policies a **targeted exploiter beats badly** — and humans are
adaptive exploiters.

- **Measure (evaluation upgrade, cheap):** train an exploiter — plain PPO with
  3 seats frozen at the current champion, 1 learning seat — and report how much
  it wins by. If large, our anchor-relative +0.296 overstates real-world
  strength. This should become a standing gate metric alongside mean placement.
- **Fix (league-lite, infra exists):** mix **past-snapshot opponents** into
  self-play seats. The snapshot-pool infrastructure from the train_ppo Tier-2
  work (pool_max_size / pool_snapshot_interval) already exists and is unused by
  `train_selfplay_oracle`; wiring a fraction of seats (e.g. 25%) to sample past
  checkpoints counters cycling/self-overfitting.

- SP-PSRO: https://arxiv.org/pdf/2207.06541
- Population-based exploitability reduction: https://arxiv.org/pdf/2208.05083
- Self-play survey (2024): https://arxiv.org/pdf/2408.01072

### 4. Test-time adaptation — Suphx's pMCPA — *deploy-side endgame*

Suphx's third technique (we already adopted oracle guiding and evaluated GRP):
**parametric Monte-Carlo policy adaptation**. At play time, sample opponents'
hidden hands consistent with the observations, roll out short simulated
continuations, and fine-tune a per-round copy of the policy on them; reset to
the offline policy each round. It is the mahjong-practical version of
search (vanilla MCTS does not fit mahjong), buys strength with **zero training
change**, and needs modest simulation counts. Cost: GPU + latency at serve
time, so it belongs to the human-facing deployment phase.

- Suphx: https://arxiv.org/pdf/2003.13590

### 5. Validation + honest skips

- **DouZero** (validates our path): superhuman DouDizhu **from scratch — no
  human data, no search — on 48 cores + 4×1080Ti**, using simple deep
  Monte-Carlo returns and massive parallel actors. Our no-corpus,
  modest-hardware situation is not a dead end; experience volume is the fuel
  (which the batched collector now supplies). A DMC-style ablation (plain MC
  returns instead of GAE at high volume) is a cheap curiosity, not a priority.
  https://arxiv.org/abs/2106.06135
- **Skip: belief-state search training (ReBeL, Student of Games, Stochastic
  MuZero).** Sound and superhuman in poker/Scotland Yard, but built around
  2-player zero-sum public-belief-state theory; 4-player mahjong belief spaces
  plus our hardware make this a research program, not a lever.
  https://arxiv.org/abs/2007.13544 ·
  https://www.science.org/doi/10.1126/sciadv.adg3256
- **Below the bar:** recent academic mahjong papers (LsAc*-MJ 2024, TJONG 2024,
  MJ_RM 2025) are interesting reading but none approaches Suphx/LuckyJ
  strength; treat as idea sources only.
  https://onlinelibrary.wiley.com/doi/full/10.1155/2024/4558614

## Recommended roadmap (RL methods only)

| # | Direction | Type | Effort | Expected value |
|---|---|---|---|---|
| 1 | Exploitability probe (exploiter vs frozen champion) | evaluation | low | derisks everything; new standing gate metric |
| 2 | Snapshot-pool opponents in self-play | training diversity | low (infra exists) | counters self-play cycling/overfitting |
| 3 | Auxiliary belief head (predict opponents' hands from 39ch) | model/loss | low-medium | best effort-to-payoff; labels are free |
| 4 | ACH-style regret objective (A/B vs PPO, same collector) | algorithm | medium | biggest ceiling-raiser; LuckyJ's core |
| 5 | pMCPA run-time adaptation | deployment | medium-high | per-game strength vs humans; endgame polish |

Sequencing rationale: 1–2 tell us whether robustness (not raw strength) is the
real gap and harden the training signal; 3 exploits infrastructure we uniquely
already have (oracle labels); 4 is the evidence-backed algorithmic upgrade; 5
converts spare inference compute into strength exactly where it matters —
against humans.

Related in-repo context: `docs/rl-papers/chongci-rl-experiment-progress.md`
(campaign log through the deep4 iter_120 promotion),
`docs/superpowers/specs/2026-07-02-batched-inference-actors-design.md`
(experience-throughput enabler for all of the above).

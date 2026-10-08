# AI Findings

What the RL work has tried and what it established, 2026-03 to 2026-10. Each line is a
registered result; "±" is a clustered CI95 on a paired placement difference unless noted.
Protocol in [`ai-evaluation.md`](ai-evaluation.md), design in [`ai-player.md`](ai-player.md).

## Champion lineage

| Step | Checkpoint | Gain | Note |
|---|---|---|---|
| 0 | heuristic bot → BC → offline IQL anchor | — | offline methods never beat this anchor by much |
| 1 | self-play `iter_050` (small net) | +0.164 vs anchor | oracle feature-dropout + all-four self-play |
| 2 | deep4 `iter_120` | +0.296 vs anchor | 4 residual blocks, 120 iterations |
| 3 | deep4 `iter_275` | +0.47 vs anchor (+0.35 on a fresh window) | 320 matches/iteration; **production** |
| 4 | B2b `iter_075` | +0.0408 ± 0.0203 vs step 3 | event GRU + privileged critic + aux heads |
| 5 | `anchor075` (restart `iter_075`) | +0.0254 ± 0.0188 | restart of step 4 with new seeds; research champion |
| — | suit averaging of `anchor075` | +0.0369 ± 0.0107 | decision rule, no training |
| 6 | suit-augment `iter_150` (`c5ff807b`) | +0.0114 ± 0.0106 | both sides suit-averaged from here on |
| 7 | extension `iter_150` (`3fdfe246`) | +0.0159 ± 0.0101 | |
| 8 | control `iter_150` (`ea6d4d41`) | +0.0082 ± 0.0073 | |
| 9 | control `iter_150` (`f9662491`) | +0.0074 ± 0.0071 | strongest registered policy |

Steps 6–9 are 150-iteration continuation laps of the same recipe (suit-augmented collection).
Each confirmed a small gain; a 450-iteration lap from step 9 is running.

## Results by lever

### Worked

| Lever | Result |
|---|---|
| Online all-four self-play with Suphx oracle feature-dropout (51-channel net, oracle channels annealed out) | First policy to beat the offline anchor (+0.16, then +0.30 with depth and budget) |
| Bigger batch, 256 → 320 matches/iteration | Broke the deep4 plateau: +0.296 → +0.472 |
| Public event history (GRU) + privileged critic + aux heads (B2b) | +0.0408, tail significantly better |
| Weight restart with fresh seeds | +0.0254 (a second restart was null) |
| Suit-symmetry averaging at decision time | +0.0369, every tail metric better |
| Continued training with suit-augmented collection | +0.011, +0.016, +0.008, +0.007 per 150 iterations |
| Observation fix: claimable discard double-counted in the seen-tile plane | Shipped unconditionally (+0.0069 ± 0.0176, not worse) |

### Did not work

| Lever | Result |
|---|---|
| Offline RL on heuristic data (BC, AWBC, IQL, CQL, offline Q; ~100 variants, 2026-03..06) | Never a robust gain over the anchor |
| Large-loss / risk heads, action-EV and branch-counterfactual supervision | Risk heads ranked at chance (AUC 0.4998, 0.5096, 0.4990); guarded policies regressed EV |
| PPO against a frozen anchor, 16 matches/iteration, sparse reward | Regressed (−0.42 vs −0.06); reward noise swamped the gradient |
| GRP placement-value reward, entropy/lr changes | Parity |
| ACH regret objective (LuckyJ family) | −1.06 ± 0.08 vs PPO; never sharpened (4-player regret dynamics need not converge) |
| Snapshot-pool opponents | Parity (−0.031 ± 0.069) |
| deep8 (8 blocks) | Champion parity at 2× inference cost |
| Determinized test-time search (pMCPA-style) | −0.04 at K=16; −0.08 (worse) at K=32 |
| Perfect information at inference (51-channel net) | Parity with the 39-channel student: hidden information is worth ~0 to this policy |
| Second restart (r2) | +0.0043 ± 0.0196 |
| 12 dormant ReZero growth blocks (deep16) | −0.0027 ± 0.0203; the alphas never moved off zero |
| Wider event GRU (128 → 256) | +0.0170 ± 0.0194, replication +0.0029 ± 0.0140 |
| 960 matches/iteration with minibatch 768 | +0.0175, CI [−0.0010, +0.0360] |
| Asymmetric terminal placement bonus (10, 5, 1, −10) | No milestone reduced 4th-place share |
| From-scratch BC → PPO, 96×4 control and 192×24 big arm | Control −0.072 vs anchor075 (gate −0.060 failed); big arm −0.0589 ± 0.0211, level with the control |
| Face-symmetry averaging (72 views: suits × rank reversal × dragons) | +0.0087 ± 0.0102 over suit averaging |
| Checkpoint ensemble (log-prob mean of 3) | +0.0089 ± 0.0098 |
| Suit distillation (KL to the six-view average) | −0.0027 ± 0.0106; −0.0132 vs its control (hurt) |
| Second extension lap (300 iterations) | +0.0079 ± 0.0106 |
| Look-ahead planes (per-action shanten and useful tiles) | −0.0066 ± 0.0074 vs control |
| Search as an expert-iteration teacher (belief-weighted re-deals + privileged critic) | +0.0021 ± 0.0022 per contested decision; no rule beat the suit-averaged choice |

The champion was also not exploitable: a PPO best response trained against it with ~25k
matches ended slightly negative.

## Rules

- **Measure on a fresh window with clustered CIs, through `fh-mj-compare`.** Reused windows and
  screening peaks overstate gains.
- **One intervention per lap, registered in advance.** Every confirmed gain came from a lap
  that changed exactly one thing.
- **A bigger net needs proportionally more experience.** Compare at matched, sufficient
  budgets; promote converged performance.
- **Capacity alone does not help this recipe.** deep8, deep16, wider GRU, 3× parameters from
  scratch, and 3× data per iteration all nulled. The gains came from representation (events),
  decision rule (symmetry averaging), and more iterations.
- **Calibrate an auxiliary or risk head before using it**: AUC above chance, monotonic risk
  bands, acceptable severity error. Coefficient sweeps do not substitute.
- **Do not initialize a Q head from policy logits.** Logits rank actions; they are not payouts.
- **Paired-trace rows after the first divergence are not same-state counterfactuals.** Use them
  for calibration and mining, never as promotion evidence.
- **Search must out-rank the policy to be a teacher.** With this critic, one-step determinized
  search ranks no better than the suit-averaged policy, and more search budget made play worse.
- **Exact efficiency features are not the bottleneck.** Giving the net per-action shanten and
  useful-tile counts did not help.
- **Compare against the suit-averaged policy**, not the plain net. Averaging alone is worth about
  +0.04 against the plain version of the same checkpoint.
- **Keep the training reward independent of the evaluation metric.** Large-loss shaping, CQL,
  and placement bonuses stay ablations.

## Policy behavior

Measured on the strongest policies; descriptive, not gates.

- **Strength.** Suit-averaged `f9662491` vs three seats of production `iter275`: +0.149; vs
  `anchor075`: +0.113. Its predecessor `ea6d4d41` vs the heuristic bots: +0.455 (52% firsts).
- **Style.** Against production the edge is hand value (same win rate, wins worth ~10% more);
  against `anchor075` it is win frequency. It makes Seven Pairs in ~0.7% of hands (production
  1.2%) and more all-pung, Loner, and kong hands.
- **Routes.** Independence (大大胡, 50 points) appears in about half of all wins for every policy.
  The policy goes Independence when its Independence shanten I ≤ 3 and then never calls; at I = 4
  only if the standard hand is 3+ shanten; at I ≥ 5 it plays standard. "Independence iff
  I ≤ S + 1" matches 96% of its fork choices.
- **Known blind spot: Mixed One Suit (混一色).** When cutting the one off-suit tile is free (equal
  speed, +70 points), the policy takes it only ~half the time. On its own self-play, taking the
  flush cut instead gains +26 ± 15 points per instance (~1 per game). Wilds near the off-suit tile
  make it worse.

## Not yet tried

- Transformer or hierarchical sequence models (DTQN, GTrXL, Tjong-style decision hierarchy).
- An exploration lap (entropy > 0) or per-discard pattern-value features aimed at the flush blind
  spot.
- Training on human games: production paipu v2 now records clean per-decision provenance, but
  the corpus is small and no extraction pipeline exists.

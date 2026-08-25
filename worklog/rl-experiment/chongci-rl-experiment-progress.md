# Chongci RL Experiment Progress Note

**Last updated: 2026-08-25.** Running notebook for the Fenghua Mahjong RL work. Append here
after every data-generation run, training run, evaluation gate, promotion, or rejection.

Detailed 2026-03..06 offline-IQL experiments:
[`20260825-chongci-iql-era-experiment-ledger.md`](./20260825-chongci-iql-era-experiment-ledger.md)
— search it before proposing any risk head, auxiliary target, counterfactual supervision
scheme, or first-divergence replay objective.

## Status

**Recipe.** On-policy PPO self-play, `fh-mj-train-b2b`. Dense per-hand Chongci score-delta
reward (score/1000), `gamma=0.99`, `lr=2e-5`, entropy 0, 2 PPO epochs, 320 matches/iter,
symmetric all-four self-play from a warm start.

**Champion.** `chongci_b2b_anchor075_restart_iter075`.

```text
box:     /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt
in repo: ai/checkpoints/anchors/b2b-anchor075-restart-iter075.pt
sha256:  ce9d867f803bb41acad30f1f4c137e82d7946ed2c4db769e265d0c9cd08f75d4
line:    deep4 iter_275 -> B2b iter_075 (+0.0408) -> restart-iter075 (+0.0254)
```

**Campaign closed 2026-08-06: local recipe saturation.** Warm-started symmetric self-play
PPO at this reward and recipe is saturated — a claim about this recipe, not an architecture
or RL ceiling. Four confirmations against restart-iter075:

| Lap | Confirmation | Verdict |
|---|---|---|
| restart ladder r2 | +0.0043 ± 0.0196 | null |
| deep4+12-ReZero (depth) | −0.0027 ± 0.0203 | null; growth alphas never recruited |
| gru-width (sequence core) | +0.0170 ± 0.0194; replication +0.0029 ± 0.0140 | unconfirmed |
| data-scale-960/mb768 | +0.0175, CI95 [−0.0010, +0.0360] | null; protocol closed |

Training reopens only for new information, a genuinely different objective, or
evidence-backed auxiliary changes. Champion promotion (shadow → canary → frozen-SHA switch)
and production paipu provenance rank ahead of any new lap.

**Open thread.** Placement-reshape — additive terminal rank bonus `(10,5,1,−10)`. Stage 0
merged (PR #220); training not authorized. See
[`placement-reshape-experiment.md`](./placement-reshape-experiment.md).

## Design Commitments

Invariants. Breaking one is a design decision, not a tweak.

**Simulator boundary.** Go is the authority: `internal/engine/` owns the state machine,
`internal/rules/` owns Fenghua scoring, `internal/rl/` wraps deterministic reset/step and
observation encoding. Python returns an `action_id`; Go validates it against the legal set
before applying. An RL policy must never become a second rules implementation.

**Observation boundary.** The deployed policy receives visible information only. Hidden
opponent hands and wall order never reach inference; privileged inputs are a training-time
auxiliary.

```text
planes:       39 x 42 x 1   (51 channels in the oracle/privileged-critic variant)
scalars:      58
action space: 204 discrete actions
```

Constants: `ObservationPlaneChannels`, `ObservationPlaneHeight`, `ObservationScalarCount` in
`internal/rl/observation.go`. Tile-face order follows backend shanten order — man 0-8,
pin 9-17, sou 18-26, jihai 27-33, flower 34-41. Scalars: overall shanten at index 25;
route-specific shanten, ukeire, discard look-ahead, wild preservation, visible score
potential, and public danger at 29-41; Chongci match/risk context at 42-57.

**Action space.** Fixed 204-action catalog — discards, chii variants, pon, kan variants, win
actions, pass, haitei accept/refuse. Hierarchical heads deferred.

**Model.** No-pooling residual CNN over semantic tile planes (96 channels, 4 residual
blocks) plus a scalar encoder and an event GRU over decision history. No adaptive pooling,
so tile positions survive. Dueling Q head. Channel attention is an ablation.

**Reward.**

```text
classic Fenghua:   terminal single-hand payout for the acting seat
Chongci (eval):    final match net score change / 1000
Chongci (train):   dense per-hand score delta   <- what the champion recipe optimizes
```

Training reward and evaluation metric are deliberately different and must not be
synchronized — see the frozen `_EVAL_PLACEMENT_VALUES` comment in
`ai/src/fh_mahjong_ai/evaluate.py`. Large-loss shaping and CQL penalties are ablations,
never promotion criteria.

**Auxiliary heads require calibration before use:** AUC above random, monotonic risk bands,
acceptable severity error. Coefficient sweeps do not substitute.

## Evaluation And Promotion

Primary metric is mean placement / expected final net score; positive-reward rate and
large-loss rate are guardrails. Raw win rate is not usable — four same-strength agents drive
it toward 25% regardless of EV.

Every promotion runs a pre-registered gate: screenings on a shared window, a kill rule fixed
before launch, one selection, then a single confirmation on a fresh unspent window. No
optional stopping; no candidate substitution after seeing results.

- **Screening** — `--start-seed 910000 --online-episodes 120`. Selection only; never cite
  for promotion.
- **Confirmation** — fresh unspent window, 1500 seeds/side, back-to-back, compared via
  `fh-mj-compare`. Windows burn once. Spent: 870000+, 950000+, 990000+, 1030000+, 1070000+,
  1110000+, 1150000+, 1190000+.
- **Use clustered CIs** — `mean_placement_ci95_clustered` and `cluster_design_effect`, not
  the iid `mean_placement_ci95`; duplicate-seat rotations of one wall seed are correlated.
  Power (iid-optimistic, scale by measured design effect): 1500 seeds ≈ ±0.03 half-width;
  80% power needs ~550 seeds for a true +0.05, ~1530 for +0.03.
- **870000+ is retired for promotion decisions** — it both selected iter_200/240/275 and
  scored later gates, so numbers on it carry ~+0.035 winner's-curse bias.

Screening CIs (≈±0.07) cannot resolve +0.03-level effects, so confirmation is the only step
that distinguishes a winner from noise. Across five laps an isolated screening peak drove
the confirmation each time — one hit, four misses.

## Infrastructure

- **Python** — always `uv run --project ai ...`.
- **Training box** — remote WSL, RTX 4090. Datasets, checkpoints, MLflow runs, and reports
  under `/root/fh-mahjong-runs/`. Checkpoint binaries stay out of git except small anchors
  under `ai/checkpoints/anchors/`.
- **Behavior cloning** — the warm-start path: heuristic trajectories through the Go bridge,
  cross-entropy over heuristic actions, exact/top-3/action-family agreement.

## Campaign Record

### Experiment: Placement Reward-Shaping Pipeline Validation (bounded)

Run:
`/root/fh-mahjong-runs/placement-compare-20260621-012708`

Question:
Does the new `--reward-shaping placement` path (rank-based placement returns
instead of raw net-score returns) run end to end on the real Go bridge, and does
a small from-scratch comparison show any raw-vs-placement difference?

Data:
200 Chongci self-play episodes (seat 1 random, others heuristic), seed 800000,
single window of mixed self-play shards (`shards/`).

Training:
Two IQL runs on identical data, from scratch, 3 epochs, batch 256, lr 1e-4, cuda:
- raw MC return target (`iql-raw/epoch_003.pt`)
- `--reward-shaping placement` MC return target (`iql-placement/epoch_003.pt`)
During training the placement run showed the expected smaller value-target
magnitude (q≈0.033, value≈0.006 vs raw q≈0.142, value≈0.071) because placement
returns are bounded in [-1, 1].

Evaluation:
40-seed Chongci duplicate-seat eval (160 matches each), `--max-steps-per-episode
4000`. NOTE: a first eval pass with the default step cap truncated every match
(`match_truncated: 1.0`, all-zero reward); a high step cap is required for
Chongci matches to resolve.

Result:

| metric | raw | placement |
| --- | ---: | ---: |
| mean_reward | -2.0698 | -2.0726 |
| mean_reward_ci95 | 0.0166 | 0.0260 |
| large_loss_rate | 1.0000 | 0.9938 |
| positive_reward_rate | 0.0 | 0.0 |
| round outcomes | match_end 1.0 | match_end 1.0 |

Decision:
inconclusive (mechanics validated, no quality signal).

Interpretation:
The full new pipeline works on the 4090 with the real bridge: placement
data/return shaping, raw and placement IQL training, and fully-resolved
duplicate-seat eval with the new `mean_reward_ci95` field. But both 3-epoch
from-scratch models are degenerate (lose every match, ~100% large loss), so the
means are statistically indistinguishable and tell us nothing about placement
quality. A meaningful comparison needs the full protocol: warm-start from the
promoted Chongci checkpoint, an order of magnitude more data, more epochs, and
the placement `--target-mode global_ev_td` variant (train GlobalEV with
`--reward-shaping placement`, then bootstrap IQL Q targets from it). Also: always
pass a high `--max-steps-per-episode` for Chongci online/duplicate eval.

### Experiment: Full-Scale Warm-Started Placement / GlobalEV-TD Campaign

Run:
`/root/fh-mahjong-runs/placement-campaign-20260621-022616`

Question:
With proper warm-start from the promoted anchor and scaled anchor-in-the-loop
mixed self-play, does placement reward shaping (MC) or placement-aware
`--target-mode global_ev_td` beat the promoted Chongci anchor on a duplicate-seat
CI gate?

Data:
3 fresh windows of mixed self-play (300 Chongci episodes each, seeds 810000 /
820000 / 830000; promoted anchor in two seats + one random seat + heuristic,
seats rotated, GPU inference) plus the existing
`chongci-broader-mixed-selfplay-20260607-032601/.../anchor-fresh-balanced-tail2-760000-n200-npz`
dataset. Reused via repeated `--data`.

Training (all warm-started from the promoted anchor
`chongci-broader-mixed-iql-20260607-034720/.../epoch_001.pt`, 6 epochs, batch
256, lr 1e-4, cuda):
- raw MC return target
- `--reward-shaping placement` MC return target
- `--target-mode global_ev_td` bootstrapped from a placement-trained GlobalEV
  (`fh-mj-train-global-ev --reward-shaping placement`, 4 epochs)

Evaluation:
80-seed Chongci duplicate-seat eval, `--max-steps-per-episode 4000`, all matches
resolved (`match_end 1.0`). Anchor evaluated on the identical gate.

Result:

| variant | mean_reward | ci95 | large_loss_rate | positive_reward_rate |
| --- | ---: | ---: | ---: | ---: |
| anchor (promoted) | -0.0903 | 0.1291 | 0.2156 | 0.4406 |
| raw warm-start | -0.1749 | 0.1296 | 0.2469 | 0.4281 |
| placement | -0.2018 | 0.1293 | 0.2531 | 0.4250 |
| global_ev_td (placement) | -0.2053 | 0.1371 | 0.2750 | 0.4094 |

Decision:
rejected (no promotion). No candidate beats the anchor.

Interpretation:
The anchor is best on every metric. All three warm-start fine-tunes drifted
slightly worse, and placement / global_ev_td did not help. Individual gaps fall
within the wide 80-seed CI (~0.13), but the monotonic ordering of large-loss rate
(0.2156 -> 0.2469 -> 0.2531 -> 0.2750) and positive rate (0.4406 -> 0.4281 ->
0.4250 -> 0.4094) indicates a small but consistent regression from this
fine-tune recipe rather than pure noise. Likely causes: (1) 6-epoch fine-tuning
of an already well-tuned promoted checkpoint on a smaller/fresher data mix drifts
it (distribution shift / mild forgetting); (2) placement shaping changes the
target scale and, under a short fine-tune, did not produce a better policy.
What to try before concluding placement shaping is unhelpful: train candidates on
the anchor's full original data mix (not just ~1100 episodes) so fine-tuning does
not regress; use a lower LR / fewer epochs to limit drift; and widen the eval to
several hundred seeds to tighten the CI below the observed gaps. The placement
and global_ev_td code paths are correct and validated; this is a negative result
about the warm-start fine-tune recipe at this data scale, not a code failure.

### Experiment: Corrected Gentle-Recipe Placement Re-Run

Run:
`/root/fh-mahjong-runs/placement-campaign2-20260621-170935`

Question:
Campaign #1 used an aggressive fine-tune (lr 1e-4, 6 epochs, batch 256) that
might have caused the regression. The promoted anchor was actually built with a
gentle recipe (lr 2e-5, 1 epoch, batch 4096) on its own 409882-transition mix.
Does matching that gentle recipe, on the anchor's original data, let placement or
global_ev_td beat the anchor on a tighter (160-seed) CI gate?

Data:
Anchor's original training mix
(`chongci-broader-mixed-selfplay-20260607-032601/.../anchor-fresh-balanced-tail2-760000-n200-npz`,
409882 transitions) plus the reused campaign-#1 self-play windows (sp-a/b/c).
`--max-transitions 200000` per dataset.

Training (warm-start from the promoted anchor, lr 2e-5, 2 epochs, batch 4096,
bc-weight 0.03, cuda): raw MC, `--reward-shaping placement` MC, and
`--target-mode global_ev_td` from a placement-trained GlobalEV (3 epochs).

Evaluation:
160-seed Chongci duplicate-seat gate, `--max-steps-per-episode 4000`, all matches
resolved. Anchor re-evaluated on the identical gate.

Result:

| variant | mean_reward | ci95 | large_loss_rate | positive_reward_rate |
| --- | ---: | ---: | ---: | ---: |
| anchor (promoted) | -0.0902 | 0.0881 | 0.2094 | 0.4328 |
| raw warm-start | -0.5190 | 0.0825 | 0.3625 | 0.3047 |
| placement | -0.5113 | 0.0829 | 0.3609 | 0.3063 |
| global_ev_td (placement) | -0.5870 | 0.0807 | 0.3797 | 0.2797 |

Decision:
rejected (no promotion).

Interpretation:
All fine-tune variants regress hard versus the anchor with non-overlapping CIs
(160 seeds tightens ci95 to ~0.08, below the gaps), so this is significant, not
noise. Placement is statistically identical to raw (no benefit); global_ev_td is
worst. Counterintuitively the gentle recipe regressed WORSE than campaign #1's
aggressive recipe (raw -0.519 vs -0.175), which means campaign #2 introduced its
own confounds rather than isolating the recipe: `--max-transitions 200000` reads
the first 200k episode-ordered rows of each dataset (a biased subset), and batch
4096 with only ~390 steps gives poor IQL value estimates. So neither campaign is
a perfectly clean controlled test.

Robust cross-campaign conclusion: IQL warm-start fine-tuning of the promoted
anchor consistently fails to improve and significantly regresses it across two
very different hyperparameter regimes, and placement reward shaping never helps
(placement ~= raw in both campaigns). The anchor is a strong local optimum that
short IQL fine-tunes move away from.

Recommendation: shelve anchor warm-start fine-tuning and placement-as-objective
as the improvement lever. The placement / GlobalEV / eval-CI code is correct and
merged (PR #83) and stays available, but is not the path to a better Chongci
agent. Pivot research effort to: (a) the proven from-scratch mixed self-play loop
with a growing frozen checkpoint pool and duplicate-seat promotion (the only path
that ever produced a Chongci promotion), and (b) training-only oracle auxiliaries
(opponent tile / wall prediction feeding the value/Q heads, deployed visible-only)
to attack the POMDP directly. If anyone revisits fine-tuning, first remove the
confounds: no `--max-transitions` truncation, moderate batch size, and reproduce
the anchor's full auxiliary-term recipe; but the prior is now poor.

### Experiment: Live Self-Play Improvement Loop (fh-mj-selfplay-loop)

Run:
`/root/fh-mahjong-runs/selfplay-loop-20260621-233930`

Question:
Can the proven mixed self-play loop — generate with the current best, train a
fresh IQL candidate on accumulated data (never fine-tuning the rolling best), and
promote only on a CI-confirmed gain — advance past the promoted Chongci anchor,
the thing reward shaping and warm-start fine-tuning could not do?

Setup:
First live run of `fh-mj-selfplay-loop` (merged in PR #85). Warm-start from the
promoted anchor (`--fixed-init` and `--initial-best` =
`chongci-broader-mixed-iql-20260607-034720/.../epoch_001.pt`), `--base-data` = the
anchor's original 409882-transition mix. 6 iterations max, 300 episodes/iter
(current best in 2 seats + heuristic + random), fresh IQL each iter (4 epochs,
batch 256, lr 1e-4, no truncation), two-stage CI gate (60-seed screen -> 160-seed
confirm), patience 3, Chongci, GPU.

Result:
Early-stopped at patience after 3 consecutive non-promotions; no candidate
promoted. `current_best` stayed the anchor throughout.

| iter | decision | candidate screen mean | candidate confirm mean (ci95) |
| --- | --- | ---: | ---: |
| anchor | (baseline) | -0.0666 (screen) | -0.0902 (0.0881) |
| 1 | rejected_confirm | -0.0738 | -0.148 (0.0938) |
| 2 | rejected_screen | -0.2026 | not run |
| 3 | rejected_screen | -0.1987 | not run |

Decision:
rejected (no promotion). Loop exited cleanly (rc=0).

Interpretation:
The loop infrastructure is fully validated on real hardware: self-play
generation, fresh-IQL-on-accumulated-data training, the two-stage CI gate
(iter 1 correctly rejected on CI overlap; iters 2-3 cheaply rejected on the
screen without spending a confirm), best-eval caching, the resumable ledger, and
the patience early-stop all worked. The deployed best never regressed
(monotonic), which is the core safety property.

But like reward shaping and warm-start fine-tuning before it, a short self-play
loop did not beat the anchor. The cause is data scale, not the method: each
iteration added only 300 episodes against the anchor's 409882-transition base, so
3 iterations (~900 episodes) is far too little signal to move a well-tuned
checkpoint, and iter 1's candidate was already close (screen -0.074 vs anchor
-0.067) before regressing on confirm. To actually clear the anchor the loop needs
many more iterations and/or much larger episodes-per-iter, which is impractical at
the current single-env generation speed (~20-40 min per 300-episode window with
checkpoint seats). The aligned next step is the deferred parallel-generation
follow-up so the loop can run far more self-play per iteration, then re-run with
more iterations; the oracle-auxiliary direction remains the higher-upside
alternative. The loop itself (PR #85) is sound and ready to scale.

### Experiment: Streamed Big-Batch Loop (memory fixed; more data falsified)

Run:
`/root/fh-mahjong-runs/stream-loop-20260623-231641`

Question:
Now that training memory is no longer the wall (streaming replay, PR #88 + the
row-copy leak fix PR #89), does 1500 episodes/iter let the self-play loop beat the
promoted anchor? This is the clean re-test the earlier OOM/crash prevented.

Setup:
`fh-mj-selfplay-loop --stream-training --stream-shuffle-buffer 50000
--stream-workers 2`, 2 iterations, 1500 episodes/iter, warm-start fixed-init =
promoted anchor, base-data = anchor's original mix, gate 60-seed screen / 160-seed
confirm, patience 2, Chongci, cuda.

Result:
Finished cleanly (rc=0). No candidate promoted.

| iter | decision | candidate screen mean |
| --- | --- | ---: |
| anchor (baseline) | — | ~-0.067 screen / -0.0902 confirm |
| 1 | rejected_screen | -0.4629 |
| 2 | rejected_screen | -0.5401 |

Two findings:

1. Streaming training works. Both iterations trained the full accumulated dataset
   (~409 K base + ~1.85 M new transitions per iter) to completion with RAM steady
   at ~10 GB and zero crashes — versus the prior non-streaming run (OOM rc=137)
   and the first streamed run (DataLoader-worker leak, fixed in PR #89 by copying
   rows so buffered samples don't retain whole-shard views). Streaming + the
   memory fix are validated end to end on real 1500-episode data.

2. More data does NOT beat the anchor — it makes the policy worse, and worse with
   more accumulated data (iter 1 screen -0.4629, iter 2 -0.5401, both rejected at
   the cheap screen versus the anchor's ~-0.067). The "the loop only failed
   because each iteration had too few episodes" hypothesis is decisively
   falsified.

Decision:
rejected (no promotion); hypothesis falsified.

Interpretation and consequence for parallel generation:
This is the clean answer the streaming detour was built to get, and it is
negative. Likely mechanism: the loop's self-play data composition (anchor in 2
seats + one random seat + heuristic) is lower quality than the anchor's actual
training mix (specific teacher policies, no random seat), so fresh IQL on a
growing pile of it drifts the policy away from the well-tuned anchor — more data =
more drift = worse. Combined with the earlier negatives (reward shaping,
warm-start fine-tuning, 300-ep loop), the picture is consistent: offline IQL
retraining at this data composition/recipe cannot beat the anchor.

Critically, this falsifies the premise of the parallel-generation design that was
drafted around 2026-06-22 and shelved before it was ever committed (no such spec
exists in `worklog/specs/` — do not go looking for it):
generating MORE self-play data faster is pointless when more data degrades the
policy. Do NOT build parallel generation. The binding issue is data QUALITY /
training recipe, not data VOLUME or generation speed.

Recommended next directions (none is "more of the same"):
- Stop and accept the anchor as the current ceiling; the loop/streaming/eval
  tooling is built and the negative space is well mapped.
- If pursuing strength, change the DATA RECIPE, not the volume: reproduce the
  anchor's real training composition (teacher policies instead of a random seat),
  or curate/filter self-play data quality, before any further scaling.
- Or pivot to the oracle-auxiliary research direction, which does not depend on
  growing the offline dataset.

### Experiment: First Online PPO vs Frozen Anchor (slice 1)

Run:
`/root/fh-mahjong-runs/ppo-anchor-20260625-194705`

Question:
The project's first ONLINE/on-policy trainer (`fh-mj-train-ppo`, PR #91 + reward
fix PR #92). Warm-started from the promoted anchor (policy+value), the learning
seat plays Chongci vs 3 frozen-anchor seats and learns via masked clipped PPO from
the per-seat match reward. Can online RL beat the anchor where offline could not?

Setup:
40 iterations, 16 matches/iter, gamma 0.999, gae_lambda 0.95, lr 2e-5,
entropy_coef 0.01, ppo_epochs 4, minibatch 256, sample_temperature 1.0, Chongci,
cuda. Reward = env `step.rewards[seat]` (sparse: 0 until match end, then final net
score change / 1000 — the env exposes no per-hand deltas). Eval = 120-seed Chongci
duplicate CI gate; anchor evaluated on the identical seeds.

Pre-flight (important): the original `collect_rollouts` read reward from
`StepResult.info` round-outcome payouts, which the Go bridge leaves empty, so the
reward was always 0 (PPO would learn nothing). Fixed in PR #92 to read
`step.rewards[seat]`; verified non-zero on the bridge before the run.

Result:
PPO did NOT beat the anchor; it regressed.

| variant | mean_reward | ci95 | large_loss_rate | positive_reward_rate |
| --- | ---: | ---: | ---: | ---: |
| anchor | -0.0615 | 0.1040 | 0.2083 | 0.4500 |
| ppo_final (iter 40) | -0.4238 | 0.0987 | 0.3417 | 0.3229 |

CIs do not overlap; worse on every metric.

Learning curve (rollout mean_reward, learning seat vs 3 frozen anchors; anchor-vs-
anchor ~ 0): iter1 +0.50, iter2 -0.25, iter3 +0.18, iter20 -0.48, iter40 -0.14 —
swings +-0.5 with no upward trend, drifting negative. Entropy stayed ~0.07-0.17
nats (near-deterministic, minimal exploration); approx_kl ~ +-0.008 (updates
barely moved the policy).

Decision:
rejected (no promotion). The PPO infrastructure works end to end (rollouts,
GAE, clipped update, eval gate; no crash), but this configuration degraded the
policy.

Interpretation (fixable failure mode, not "online RL can't work"):
Catastrophic signal-to-noise. Three compounding causes:
1. Tiny batch — 16 matches/iter = only 16 noisy terminal-reward signals; the
   per-iteration reward variance (+-0.5) swamps the gradient.
2. Sparse terminal reward over a ~440-step learning-seat horizon — the env emits
   no per-hand deltas, so almost all credit must flow through the value critic;
   the direct reward signal is one number per match.
3. Minimal exploration — the warm-started policy is highly peaked (entropy ~0.1),
   and entropy_coef 0.01 did not keep it exploring, so PPO mostly drifted under
   noise rather than discovering better lines.
Net: 40 noisy updates slowly degraded the anchor.

Recommendations before scaling online RL (do NOT just rerun as-is):
- Much larger rollouts per update (hundreds of matches) to cut reward variance —
  this is the highest-leverage fix and it needs faster generation, so the
  shelved parallel-generation spec is now justified specifically for online RL.
- Add dense per-hand reward (requires Go env support to emit per-hand score
  deltas, or reconstruct from visible score scalars) to fix credit assignment.
- Raise entropy_coef / sample_temperature for real exploration; tune lr; more
  iterations once signal-to-noise is fixed.
- Consider the GlobalEV/GRP reward as the critic/return target (Suphx-style).
The PPO code paths (PR #91/#92) are correct and reusable; this is a
tuning/throughput/reward-density problem, not a code failure.

### Experiment: Oracle Guiding → Self-Play Feature-Dropout (deployable beat)

Run:
`/root/fh-mahjong-runs/sp-gate` (50-iter small net, first beat),
`/root/fh-mahjong-runs/sp-long` (80-iter small net),
`/root/fh-mahjong-runs/sp-big` + `/root/fh-mahjong-runs/sp-big-ext` (deeper 4-block net).
Anchor: `/root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt`.

Question:
Can a DEPLOYABLE imperfect-information agent beat the anchor, by combining the two
untried pieces of the Suphx/Mortal recipe: (1) a perfect-information scaffold
(51ch oracle observation = the 3 opponents' concealed hands) annealed away via
feature-dropout (δ 0→1), and (2) all-4 symmetric self-play (every seat is the
co-evolving net) instead of a fixed heuristic/anchor opponent?

Data:
Self-generated all-4 self-play (no offline dataset). 51ch oracle net warm-started
from the 39ch anchor via `build_oracle_model`. Deeper variant = `residual_blocks=4`
warm-started from the 2-block anchor (blocks 0-1 + heads + input conv copied, new
blocks' output convs zeroed → logit_corr 1.000 with the anchor).

Training:
all-4 self-play + feature-dropout (δ=0 first 20% iters, linear ramp 0→1 over the
next 60%, δ=1 final 20%); 256 matches/iter, lr 2e-5, entropy_coef 0, ppo_epochs 2,
max_grad_norm 0.5, gamma 0.99, chongci, max-steps 4000, cuda, 5 workers. sp-gate 50
iters; sp-long 80 iters; sp-big 60 iters (deeper); sp-big-ext resumes sp-big
iter_060 for 60 more δ=1 iters (→ iter_120). MLflow: N/A — these were run via
standalone scripts (`sp_big.py`, `sp_big_ext.py`), not the MLflow-integrated CLI;
metrics are in each run's `train.log` + `ckpt/history.json`.

Evaluation:
Deployable 39ch student extracted from the 51ch net (slice input conv), evaluated
NON-oracle (directly comparable to the anchor). Paired duplicate-seat, 120 episodes
× 4 seats = 480, start-seed 870000, chongci 50 hands, max-steps 4000. Anchor
evaluated on the identical seeds (`/root/fh-mahjong-runs/oracle-gate-baseline/eval-anchor.json`).
Reports under each run's `deploy/`/`eval-*` json.

Result:

| checkpoint | paired diff vs anchor | ci95 | large_loss |
| --- | ---: | ---: | ---: |
| anchor | 0.0 (mean_pl -0.0528) | — | 0.208 |
| sp-gate iter_050 (small, first beat) | +0.1639 | 0.0676 | 0.165 |
| sp-long iter_075 (small, longer) | +0.2125 | 0.0750 | 0.138 |
| sp-big iter_060 (deep4, 60 iters) | +0.1875 | 0.0719 | 0.150 |
| **sp-big-ext iter_120 (deep4, 120 iters)** | **+0.2958** | **0.0773** | **0.104** |

Decision:
promoted — `sp-big-ext` iter_120 (deep 4-block) → `current_chongci_reward_trained_best`
(PR #136), extracted standalone 39ch at
`/root/fh-mahjong-runs/deploy/selfplay-deep4-student-iter120-39ch.pt`. The prior
`iter_050` student moves to `fallbacks`; `iter_075` (+0.2125) is the runner-up/
fallback candidate at `/root/fh-mahjong-runs/deploy/selfplay-student-iter075-39ch.pt`.

Interpretation:
First deployable agent to robustly beat the anchor — the winning combination is the
Suphx feature-dropout scaffold + all-4 self-play (neither alone had cleared parity).
Depth initially looked worse (deep4 at 60 iters = +0.1875 < small-net +0.2125) but
that was UNDERTRAINING, not a capacity ceiling: given a fair 120-iter budget the
deeper net's δ=1 tail climbed 080/100/120 = +0.2042/+0.2903/+0.2958 and plateaued
well above the small net, halving large-loss (0.104 vs 0.208). Lesson: bigger nets
need proportionally more experience; compare at matched (sufficient) budgets, and
promote demonstrated (converged) performance, not potential. Serving had to learn
the checkpoint's architecture from the state dict (`infer_model_config`, PR #136),
since the promoted net is 4-block vs the 2-block default.

### Experiment: Phase B run #1 — bigger-batch extension of the deep4 champion

Run:
`/root/fh-mahjong-runs/phaseB1` (resumed from `/root/fh-mahjong-runs/sp-big-ext/ckpt/iter_120.pt`)

Question:
The deep4 champion's iteration-scaling had plateaued (+0.290 -> +0.296 over iters
100->120). Is gradient noise the binding constraint — i.e. does a bigger batch
per PPO update (more matches per iteration) break the plateau?

Data:
Self-generated all-4 self-play, delta=1 throughout (net already weaned).

Training:
Single variable vs the champion run: matches_per_iter 256 -> 320 (the intended
512 was OOM-killed — the process collector materializes ~3x the batch; fixed
post-hoc in PR #146). 155 iters (gi 121-275), nw=10, lr 2e-5, entropy 0,
ppo_epochs 2, chongci, cuda. No MLflow (standalone script /root/sp_phaseb1.py);
metrics in train.log + ckpt/history.json.

Evaluation:
Extracted 39ch students, paired duplicate-seat 120x4=480 episodes, start-seed
870000, vs the IQL anchor baseline (-0.0528). Promotion bar: CI lower bound
above the prior champion's +0.2958.

Result:

| checkpoint | paired diff | CI95 | CI lo | large_loss |
| --- | ---: | ---: | ---: | ---: |
| champion iter_120 (prior) | +0.2958 | 0.0773 | — | 0.104 |
| iter_200 | +0.3903 | 0.0825 | +0.3078 | 0.094 |
| iter_240 | +0.3861 | 0.0781 | +0.3080 | 0.073 |
| iter_275 | +0.4722 | 0.0815 | +0.3907 | 0.079 |

Standalone plain-39ch validation of iter_275: +0.4722 +/-0.0815 (exact match to
the --from-oracle eval; artifact self-contained at
`/root/fh-mahjong-runs/deploy/selfplay-deep4-student-iter275-39ch.pt`).

Decision:
promoted — iter_275 student -> `current_chongci_reward_trained_best`
(prior champion iter_120 retained in fallbacks; BC stays the generic fallback).

Interpretation:
Bigger-batch hypothesis confirmed even at 1.25x batch: the plateau was gradient
noise, not capacity or iteration count. The curve is still RISING at run end
(240 -> 275 jumped +0.086), so Phase B run #2 continues from iter_275 at
matches_per_iter 448 (enabled by the PR #146 collector memory fix). Operational
lessons: 512x16 needs ~38GB (3x-batch materialization) — fixed by worker-side
release + consume-mode concat; watcher aggregators must not be edited via sed
patterns that miss escaped quotes (evals ran, aggregation mislabeled).

### Experiment: ACH regret objective A/B (2026-07-07/08) — FAILED, keep PPO

Motivation: with scaling saturated (Phase B #2 parity at 448), the champion not
exploitable, and the oracle-ceiling eval showing hidden-info value ~0 (perfect-info
51ch iter_275 = +0.4361 vs the 39ch student's +0.4722 — parity, so belief modeling
ruled out), the remaining lever was the objective itself: clipped-NeuRD / ACH
(LuckyJ's family), merged as a drop-in for ppo_update in PR #147
(--objective ach --ach-beta; RolloutBatch unchanged; PPO default byte-identical).

A/B (both resume iter_275, identical seeds, 40 iters, batch 224 after OOM tuning,
delta held 1): PPO control +0.4306 vs anchor / large_loss 0.079 (validates champion
and eval); ACH beta=2 -0.6250 / large_loss 0.675; paired ACH-PPO = -1.0556 +/-0.077.
ACH never sharpened (entropy pinned ~1.73 vs PPO 0.14); mean_abs_logit 1.2-1.5
stayed BELOW beta=2 with saturation 4-15%, so beta was not the binding constraint
(beta sweep pointless). A from-scratch retry (IQL anchor, lr 1e-4) was projected
~30h on the 31GB box (the anchor plays max-length games; 224 OOM'd, 128 crawled)
and was killed per user decision.

Theory note: ACH/regret-min guarantees Nash convergence only in 2-player zero-sum
(the paper's 1-on-1 mahjong benchmark); in 4-player games regret dynamics reach
only coarse-correlated equilibria and need not sharpen — the observed failure is
consistent with the setting, not just the config. LuckyJ's 4-player method is
undisclosed. Verdict: ACH closed; PPO remains the objective.

Incidental find (blocking bug, fixed): the A/B crashed at iter 277 with
"duplicate action id 182 for ACTION_KAN" — root cause was NOT wilds but a wall
double-draw: dead-wall (kong/flower) replacement draws descend past wangpaiBoundary
into the live wall, and ExecuteSystemDraw never skipped those consumed indices, so
the same physical tile could be dispensed twice (phantom duplicate tile id in a
hand; corrupts counts/scoring). Fixed in PR #149 (front draw skips
isTileConsumedByDeadWall indices; fuzzer regression gate in
internal/rl/kan_dup_repro_test.go reproduced at seeds 15/47/68 pre-fix). The
related wild-in-kan rule enforcement (PR #148) was closed: a wild kan is
unreachable in normal play (a standard indicator leaves only 3 wild-face copies in
play; a kan needs 4). Rules clarified by the owner: wilds are jokers ONLY in the
concealed hand; in open melds / discards / calls they are strictly face-value.

### Experiment: pool-diversity run (2026-07-08/09) — PARITY, champion stands

The last untested training lever: the entire champion line was pure mirror
self-play (pool_max_size=1). Run: 39ch student extracted from iter_275, trained
via train_ppo (single learning seat, pure 39ch env) against a snapshot pool
(pool_max_size 6, snapshot_interval 8), 160 iters x 224 matches, lr 2e-5, ~9h.
Paired vs champion on identical eval seeds: iter_80 -0.068, iter_120 -0.081,
iter_160 -0.031 +/-0.069 = statistical parity (large_loss 0.067 vs 0.079 — a mild
tail improvement, not promotable). No promotion.

Campaign status after these runs: ALL FIVE training levers tested and closed —
scaling saturated, not exploitable, hidden info worthless, ACH failed, opponent
diversity neutral. The +0.4722 iter_275 39ch student is the genuine, robust
self-play plateau for this architecture/pipeline. Remaining non-training options:
pMCPA-style test-time search (serve-time boost, no training), a bigger net
(4->8 residual blocks, brute force), production human-paipu accumulation
(storage.Match.PaipuJSON — capture verified live), and the human game-review
product direction (mjai-reviewer-style; spawned as its own design session).

### Experiment: deep8 capacity campaign (2026-07-09/11) — PARITY CEILING, capacity closed

Brute-force lever: replay the champion pipeline at residual_blocks=8 (2x deep4).
Warm-start 51ch from the IQL anchor via load_compatible (deep2->deep4 mechanism),
60-iter delta ramp at batch 128 (anchor-start plays max-length games — the 224 OOM
lesson), then delta=1 extensions.

Trajectory (paired vs anchor, -0.0528): ramp iter_60 +0.138 (deep4 ref +0.13);
ext1 batch 224: 120=+0.242, 150=+0.303, 180=+0.356 (tail 0.077 = champion-level);
ext2 batch 224: 220=+0.371, 260=+0.396, 300=+0.379 — SATURATED ~+0.38, worse than
champion CI-separated. Leg 3 applied the Phase-B batch move (224->320, the exact
recipe that broke deep4's plateau): iter_330 +0.4528 (champion parity, -0.019
+/-0.075), iter_360 +0.4056 (post-peak oscillation, mirrors deep4's endgame; tail
0.069 = best seen — ensemble candidate).

Verdict: the batch move works on deep8 exactly as on deep4, but the destination is
the SAME ~+0.45-0.47 ceiling — deep8 reaches champion parity at 2x inference cost
and never CI-beats +0.4722. Not promotable. Capacity joins the closed levers.

Campaign status: SIX levers tested and closed — scaling saturated, not exploitable,
hidden info ~0, ACH failed, pool diversity neutral, capacity parity-bound. +0.47 is
a pipeline-level plateau independent of model size. The remaining ceiling-moving
mechanism is test-time search + expert iteration (search-improved targets distilled
back into the net), with serve-time ensembling (champion + deep8 iter_360's 0.069
tail) as a cheap adjacent win.

### Experiment: Phase-1 test-time search gate (2026-07-12/14) — FAILED, search closed

Setup: honest determinized pMCPA over the frozen champion (PR #161: RedealUnseen,
paired-CRN SearchPool, root-seat pinning, discount-consistent scoring, in-distribution
bootstraps; 11 defects fixed pre-merge across SDD/adversarial-loop/GitHub-Codex).
Gate: SearchPolicy(champion) vs raw greedy champion, paired duplicate-seat, 480
placements, seeds 870000+.

Results (fallback_count=0 in both runs — the machinery was flawless):
- K=16/M=4 (21h): vs champion -0.0375 +/-0.0745 (parity); vs anchor +0.4347;
  large_loss 0.079 (identical).
- Escalation K=32/M=6 (34h): vs champion -0.0833 +/-0.0715 (WORSE, CI-separated);
  vs anchor +0.3889; large_loss 0.092.

Interpretation: tripling the budget made search WORSE — more candidates gave the
rollout/value estimates more chances to override the champion's better greedy choice.
The champion's policy is more accurate than its own value head can re-rank through
shallow determinized search; without a search that outranks the policy there is no
expert-iteration teacher, so Phase 2 is not justified. Search closes as the SEVENTH
tested lever.

CAMPAIGN CONCLUSION: batch scaling saturated, not exploitable, hidden info ~0, ACH
failed, pool diversity neutral, capacity parity-bound at 2x cost, and test-time
search loses to the raw policy. +0.4722 (deep4 iter_275 student) is the genuine
ceiling of this pipeline, established seven independent ways. Remaining directions
are product-side: labelled human-game corpus (accumulating in prod since the paipu
fix), the post-game review tool, serve-time ensembling for tail risk, and an
eventual human-data SL refresh once the corpus is large.

(2026-07-14 addendum: a GPT-5.6 methodology audit + independent literature survey
overturned parts of this conclusion — see the Spec A entry below and the rebuild
specs under worklog/specs/. The seven-lever record above stands as
measured; its interpretation is now qualified by the observation defect and the
evaluation-statistics findings.)

### Experiment: Spec A close-out — obs double-count fix + eval hygiene (2026-07-14/15) — SHIPPED

- What: PR #166 (main 88c6d59). Fixed the interrupt-window double-count in
  `publicSeenCounts` (the claimable discard was counted twice in plane 37 and
  publicDangerScore at EVERY pon/chii/ron decision, all campaign — the engine
  appends to Discards before setting ActiveDiscard). Added seed-clustered CIs
  (`mean_placement_ci95_clustered`, `cluster_design_effect`) to duplicate-seat
  reports, persisted eval-config + simulator provenance (`bridge_lib_sha256`
  of a pre-eval immutable library snapshot), and shipped `fh-mj-compare` —
  the mandatory fail-closed gate tool (seed/config/protocol/provenance parity;
  labeled opt-ins `--allow-missing-config`, `--allow-bridge-mismatch`).
- Champion re-measurement (decision rule from the spec), screening window
  910000+, 120 seeds x 4 rotations, chongci, deep4 iter_275 champion, paired
  fixed-vs-buggy bridge via `fh-mj-compare --allow-bridge-mismatch`:
  - FIXED encoder: mean placement +0.3500 (clustered CI95 ±0.0561, naive
    ±0.0620), large_loss 0.0813.
  - BUGGY encoder: +0.3431 (clustered ±0.0585), large_loss 0.0875.
  - Paired delta (fixed − buggy): **+0.0069 ± 0.0176** — fixed ≥ buggy.
    VERDICT: the fix ships unconditionally (serving + training + eval); no
    compat flag. The champion is robust to the corrected input.
- Measured `cluster_design_effect` on the screening window: **0.80 (fixed) /
  0.88 (buggy)** — duplicate-seat rotations are mildly NEGATIVELY correlated
  within a wall seed, i.e. the duplicate format's variance reduction is real
  and the clustered CI is slightly TIGHTER than the naive one here. Spec B
  run-size planning can use design effect ≈ 0.85 (do not assume >1).
- Honesty note: the champion measures +0.3500 ± 0.056 on the FRESH screening
  window vs the +0.4722 ± ~0.08 recorded on the burned 870000+ window — the
  gap (≈ −0.12) exceeds the predicted ~0.035 winner's-curse bound, so window
  effects and selection bias together were inflating the headline number.
  All future comparisons are within-window paired deltas via fh-mj-compare;
  cross-window level comparisons like this one are diagnostic only.
- Artifacts: /root/fh-mahjong-runs/spec-a/{champion-fixed,champion-buggy,compare}.json
  (box); pre-fix bridge built from ec6800e in /root/fh-mahjong-prefix.

### Experiment: Spec B2b — event GRU + privileged critic + auxiliaries (2026-07-18/20) — **PASSED THE GATE, NEW CHAMPION CANDIDATE PROMOTED**

- What: warm-started deep4 iter275 with the B2b representation upgrade
  (event-history GRU window 128, privileged 12ch critic branch, aux heads
  belief/deal-in/rank-bust), trained 150 iters on the EXACT champion recipe
  (dense score deltas, γ=0.99, 320 matches/iter, lr 2e-5, entropy 0,
  ppo-epochs 2, chongci, 5 workers). PRs #169 (B1) + #172 (B2a) + #177 (B2b);
  12-round adversarial gauntlet pre-merge (see ledger).
- Gate protocol: the RATIFIED 10-item protocol (Codex debate-to-agreement,
  2026-07-19, appended to the B2b runbook). Determinism precheck PASSED
  bit-exact (480/480 identical champion-repeat placements). Frozen candidate
  = iter_075 (best screening delta +0.0396 of {25..150}; extension trigger
  not met — 100→125 screening decrease).
- Screening trajectory (910000+, 120 seeds, same-bridge paired):
  25:+0.0285 50:+0.0035 75:+0.0396 100:+0.0215 125:+0.0069 150:+0.0035.
- **CONFIRMATION VERDICT (950000+, 1500 seeds, back-to-back, same bridge,
  full provenance in /root/fh-mahjong-runs/b2b/gate-provenance.txt):**
  - candidate +0.4229 vs champion +0.3821; paired placement delta
    **+0.0408 ± 0.0203** (seed-clustered CI95) — CI clears zero
    (lower bound +0.0205). SIGNIFICANT.
  - tail criterion: large_loss 0.0552 vs 0.0613; point rule −0.0062 ≤ +0.015
    PASS; paired per-seed tail delta **−0.0062 ± 0.0077** — the candidate's
    tail is significantly BETTER, not merely non-inferior.
  - zero truncations; config_check strict except the window key
    (the intervention); bridge digests match.
- Interpretation: the representation rebuild (audit direction #1) delivered
  the campaign's FIRST confirmed champion-beating candidate, in the
  predicted +0.04..+0.12 band, with improved tail risk — after seven
  training levers and a search phase all failed. The +0.4722 headline was
  never the true bar (window-inflated; Spec A); the honest bar was
  +0.3821 ± 0.020 on this window, and the candidate clears it.
- Artifacts: /root/fh-mahjong-runs/b2b/ (ckpt/iter_075.pt sha 00f469b0…,
  confirm-{candidate,champion,compare}.json, gate-provenance.txt).
- NEXT (per ratified item 10): Spec B2c — serving integration (room →
  HTTPPolicy event threading, /act payload, review tool) BEFORE any
  deployment of the new champion.

### 2026-07-24 — anchor075-restart: second consecutive confirmed win (restart ladder lap 1)

Codex-ratified iter_075 weight restart (exact champion recipe, --base-seed 100000,
symmetric self-play, preflight-proved exact load via --champion). 150/150 iters,
healthy telemetry throughout (dealin_positive_rate ~0.12, rank coverage 1.0, zero truncation).

Screenings vs regenerated iter_075 comparator (910000+, 120 seeds, strict):
25: -0.0486±0.0641 | 50: -0.0264±0.0630 (kill rule passed) | 75: +0.0264±0.0717 |
100: -0.0250±0.0741 | 125: -0.0042±0.0742 | 150: -0.0597±0.0778. Extension rule
failed cleanly (150 worst); pre-registered selection = restart iter_075 (only positive).

Confirmation (990000+, 1500 seeds/side, back-to-back, main 05f63a6, strict, frozen
candidate sha ce9d867f803bb41a...): paired placement +0.0254 ± 0.0188 — SIGNIFICANT;
large_loss 0.0493 vs anchor 0.0523 (tail criterion passes, candidate better). GATE PASSED.

Lesson repeated: both confirmed champions were isolated screening peaks in unstable
trajectories — screening CIs (±0.07) cannot resolve +0.03-level effects; the
no-optional-stopping confirmation discipline is what finds them. (Codex insisted on
running this gate against my pessimistic prior; it was right.)

Registered as gate_qualified_research_champion (chongci_b2b_anchor075_restart_iter075,
serving_status blocked_on_b2c_runbook); anchor iter_075 entry marked superseded.
990000+ window now spent. Next lap (r2) authorized and launched: --champion restart
iter_075, base-seed 200000, dir b2b-anchor075r2-restart, confirmation window 1030000+;
if r2 confirms, next step is a NEW decision (no automatic r3). Deployment rule: B2c
runbook target frozen at start; no mid-runbook candidate swap.

### 2026-07-24 — deep16-rezero: pre-registration (capacity growth via ReZero blocks)

Design ratified via Codex consult (canonical session): `worklog/specs/
2026-07-24-deep16-rezero-design.md`, branch `claude/deep16-rezero`. Runbook:
`worklog/plans/2026-07-24-deep16-rezero-runbook.md`. Registering the gate
BEFORE launch per standing pre-registration discipline; launch itself is gated on
r2's own confirmation (sequencing ratified — see the entry above) and has not
started as of this write-up.

**Hypothesis under test:** does capacity (trunk depth) pay ON TOP OF the B2b event
representation, given a defensible function-preserving warm start? This is ONE
architectural intervention — 12 stacked `ReZeroResidualBlock`s (`x + alpha *
F(x)`, `alpha` a learned scalar initialized to 0, so the grown net is EXACTLY the
anchor at step 0 — no trailing GELU, unlike the legacy `ResidualBlock`, is what
makes zero-init identity possible here). GRU, aux heads, and every other recipe
knob stay fixed. Prior context: both confirmed champion-line wins so far came from
temporal representation (B2b) at 96ch/4 blocks; a pre-B2b deep8 capacity test
(trunk-only, no events) nulled at 2x cost — this is a second capacity attempt, now
stacked on top of the representation win instead of before it.

**Anchor:** r2's winner if r2's `1030000+` confirmation passes ("r2 iter_150" — sha
`518cc376...`, confirm and freeze the full digest at launch time); otherwise
restart-iter075 (`/root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt`,
sha `ce9d867f803bb41acad30f1f4c137e82d7946ed2c4db769e265d0c9cd08f75d4` — already a
confirmed gate-qualified champion, registered above). Frozen path+sha recorded at
launch time in the runbook.

**Gate parameters (ratified, binding):**
- Budget: 260 iterations x 320 matches/iter (1.73x param ratio vs the anchor),
  recipe otherwise byte-identical to the ratified champion recipe (dense per-hand
  score-delta reward, gamma=0.99, lr=2e-5, entropy 0, 2 PPO epochs).
- Preflight: state-dict sha check + a step-zero parity script (`grow_b2b_model`
  output torch.equal to the anchor on policy logits/value/Q/aux/greedy-action)
  MUST pass on the box before any training compute is spent.
- Worker benchmark: `fh-mj-collect-bench` gates `--num-workers` (adopt the
  fastest worker count with an EXACT digest match; if the projected lap at that
  count exceeds 7 days, STOP — a pool port is a separate, out-of-scope decision).
- Screening: iters 25/50/75/100/125/150/175/200/225/250/260 vs a REGENERATED
  anchor comparator, same current bridge, `910000+` window, 120 seeds, strict.
- Kill rule: ONLY at iter 100, if BOTH the iter-75 AND iter-100 champion-relative
  deltas are `< -0.06`. No other iteration triggers a kill.
- Hard stop at 260 — no extension (unlike the B2b runbook's conditional
  extension). Freeze the best HEALTHY pre-registered screening checkpoint; no
  substitution after seeing later results.
- Confirmation: fresh `1070000+` window, 1500 seeds/side, back-to-back, same
  bridge. Promotion requires BOTH the paired placement clustered 95% CI clearing
  0 AND `large_loss_rate(candidate) <= large_loss_rate(anchor) + 0.015` absolute.
- Retention: keep screening checkpoints + final; prune the rest after completion.
  `train_state.pt` written every 5 iterations so the lap survives box restarts.
- Alpha telemetry: `history.json` logs mean `|alpha|` across the 12 growth blocks
  per iteration. Alphas hugging 0 at the end is itself a RESULT (protocol null —
  growth stalled under the shared learning rate), not a bug.

**Kill/null semantics (binding, stated up front):** a null result here means THIS
PROTOCOL failed, NOT evidence of a capacity ceiling. On null, record the outcome
plainly (including the alpha-telemetry trace) and the next menu item is GRU
widening per the scale roadmap memory — not another depth attempt with a
different warm-start, and not an automatic r3-style repeat of this same lap.

Out of scope for this lap (per spec, unchanged): GoEnvPool port, matches-per-iter
changes, transformer encoders, aux-weight changes, deployment of any winner (a
B2c-style runbook governs that later, with growth-aware metadata already handled
by Task 3).

### 2026-07-27 — r2 restart lap: confirmation NULL (ladder exhausted at one confirmed lap)

r2 (anchor restart-iter075, base-seed 200000): screenings all negative (best iter_150
-0.0056±0.0682). Confirmation on 1030000+ (1500 seeds/side, candidate sha 518cc376...,
run survived a box reboot via operator relaunch): paired delta +0.0043 ± 0.0196 — NOT
significant; large_loss 0.052 vs 0.0557 (tail fine). GATE FAILED per pre-registered
criteria. r2 iter_150 not promoted; 1030000+ retired. Restart ladder: 1 confirmed win
(lap 1) then null (lap 2) — consistent with the anchor sitting at this recipe's basin.

Next (pre-registered, no new consult needed): deep4+12-rezero capacity lap (PR #182
merged) with anchor = restart-iter075 (sha ce9d867f...). Box preflight PASSED
(step-zero parity OK on the real anchor); worker benchmark (5/10/20 @ 320 matches,
exact-digest gate) running; launch follows per runbook (260 iters, screening 25..260,
kill only at 100, confirmation window 1070000+).

### 2026-08-02 — deep4+12-rezero capacity lap: confirmation NULL

260/260 iters (two OOM kills mid-run — 20-worker + 16GB master exceeded the 31GB box —
both recovered via resumable train state; finished at 10 workers after PR #187 exempted
num_workers from the resume config echo as semantics-neutral). Anchor: restart-iter075.

Screenings (910000+, vs anchor): 25:-0.035 | 50:-0.017 | 75:-0.058 | 100:-0.033 (kill
rule passed) | 125:-0.078 | 150:-0.021 | 175:-0.021 | 200:+0.028 (pre-registered best) |
225:-0.021 | 250:-0.022 | 260:+0.010. growth_alpha_mean_abs stayed ~0.0002-0.0006 the
whole run — ReZero growth blocks barely recruited (the pre-registered "capacity not
engaging" signature), small late uptick only.

Confirmation (1070000+, 1500 seeds/side, candidate iter_200 sha a785d5ab...):
-0.0027 ± 0.0203 — NOT significant; large_loss 0.0613 vs anchor 0.0517 (within the
+0.015 bound). GATE FAILED. 1070000+ retired.

Reading: trunk depth is declined by PPO at this recipe even WITH the event
representation — consistent with the original deep8 null, now at 1.73x params with a
provably function-preserving warm start. Third lap running where an isolated screening
peak (+0.028 here) drove the confirmation: 1 hit (restart lap), 2 misses (r2, this).
Next per ratified menu: GRU-width scaling (post-consult).

### 2026-08-02 — gru-width: pre-registration (event-encoder width scaling)

Design ratified via Codex consult (canonical session, 2026-08-02), following the
deep16-rezero recruitment null: `worklog/specs/2026-08-02-gru-width-design.md`,
branch `claude/gru-width`. Runbook: `worklog/plans/2026-08-02-gru-width-runbook.md`.
Registering the gate BEFORE launch per standing pre-registration discipline.

**Hypothesis under test:** does the SEQUENCE CORE itself have unused capacity, given that
generic trunk depth has now nulled twice (deep8 pre-events; deep4+12-rezero with events,
alphas never recruited) while both confirmed champion-line wins came from the event/temporal
representation? ONE architectural intervention: double the event GRU hidden width (128 ->
256), keeping the trunk's 128-dim event-feature interface fixed via an identity-masked
`[I|0]` output projection so step-zero behavior is EXACTLY the anchor's (function-preserving
warm start, same discipline as `grow_b2b_model`, but widening an existing recurrent layer in
place rather than stacking new blocks). Trunk, aux heads, and every other recipe knob stay
fixed — this isolates the sequence-core width variable from the already-nulled depth variable.

**Anchor:** restart-iter075 (unchanged; already a confirmed gate-qualified champion):

```
/root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt
sha256: ce9d867f803bb41acad30f1f4c137e82d7946ed2c4db769e265d0c9cd08f75d4
```

**Gate parameters (ratified, binding):**
- Budget: `iterations = ceil_to_5(150 * candidate_params / anchor_params)` with the
  MEASURED ratio (expected ~1.08x -> 165) x 320 matches/iter, recipe otherwise
  byte-identical to the ratified champion recipe (dense per-hand score-delta reward,
  gamma=0.99, lr=2e-5, entropy 0, 2 PPO epochs, chongci, 10 workers — memory-proven per
  the deep16 20-worker OOM lesson, no fresh worker benchmark for this lap).
- Preflight: state-dict sha check + a step-zero parity script (`widen_event_gru` output
  torch.equal to the anchor on event features/policy logits/value/Q/aux/greedy-action)
  MUST pass on the box before any training compute is spent; the same script also
  measures the param-count ratio that fixes the iteration budget.
- Screening: iterations 25/50/75/100/125/150/`<final>` (the computed budget, expected
  ~165) vs a REGENERATED anchor comparator, same current bridge, `910000+` window, 120
  seeds, strict (the deep4+12-rezero comparator is not reused — the bridge has moved).
  Candidate eval flags add `--model-event-hidden-dim 256 --model-event-output-dim 128`.
- Kill rule: ONLY at iter 100, if BOTH the iter-75 AND iter-100 champion-relative deltas
  are `< -0.06`. No other iteration triggers a kill.
- No extension; selection protocol UNCHANGED from prior laps — best eligible
  pre-registered screening checkpoint, healthy telemetry, no substitution after seeing
  later results (ratified per consult: sensitivity over false-launch cost).
- Confirmation: fresh `1110000+` window (unspent by any prior lap), 1500 seeds/side,
  back-to-back, same bridge. Promotion requires BOTH the paired placement clustered 95%
  CI clearing 0 AND `large_loss_rate(candidate) <= large_loss_rate(anchor) + 0.015`
  absolute.
- Resumable state every 5 iterations; `PYTHONUNBUFFERED=1` launch; orchestrator +
  screening chain live under `/root/fh-mahjong-runs/` (reboot-safe paths) — same
  discipline as the last two laps, since deep4+12-rezero needed two OOM-recovery resumes.

**Kill/null semantics (binding, stated up front):** a null result here means the SEQUENCE
CORE also has no unused capacity at this recipe under PPO — a THIRD capacity axis (after
trunk depth twice) declining to pay, not merely a bad warm-start protocol (step-zero parity
is proven mechanically sound before launch, unlike the depth-null's alpha-recruitment
ambiguity). Per the ratified scale roadmap, the next menu item after a null here is an
aux-weight ablation, not a further width/depth variant.

Out of scope for this lap (per spec, unchanged): trunk changes, transformer encoders,
window changes, aux weights, matches-per-iter changes, deployment of any winner (B2c
rollout proceeds independently with restart-iter075 regardless of this lap's outcome).

### 2026-08-06 — gru-width lap: positive near-miss, independently unconfirmed

Lap ran exactly as ratified (165 iters, ratio 1.0705, step-zero parity, kill@100
passed). Screenings vs restart-iter075 (910000+): monotonic climb -0.078 (50) →
-0.050 (75) → -0.011 (100) → +0.033 (125), staying positive at 150/165 (+0.013).
Selected iter_125 (sha d855aa83...).

Confirmation 1110000+ (1500/side): +0.0170 ± 0.0194 — gate failed by a hair
(tail passed, 0.0503 vs 0.0540). Codex-ratified single independent replication
(1150000+, 3000/side, replication ALONE confirmatory; pooling descriptive only):
+0.0029 ± 0.0140 — NOT significant, point estimate collapsed. Verdict per
pre-registration: near-miss unconfirmed; iter_125 RETIRED; no third window.
Descriptive pooled estimate +0.008 ± 0.022 — consistent with tiny-or-zero effect.

Scale-campaign scoreboard vs restart-iter075: restart ladder r2 null; deep16
ReZero recruitment null; gru-width unconfirmed near-miss. Champion line stands:
iter275 → iter_075 (+0.041) → restart-iter075 (+0.025), promotion in progress.
Next decision (consult): aux-weight ablation vs concluding recipe saturation.

## Maintenance Protocol

Record a lap twice: a pre-registration entry before any training compute is spent, and an
outcome entry when it ends.

```text
### <date> — <lap>: pre-registration (<one-line intervention>)

Hypothesis:      what this lap would prove, and what it would not
Spec / runbook:  worklog/specs/…, worklog/plans/…
Anchor:          path + sha256, frozen at launch
Intervention:    exactly ONE; everything else byte-identical to the champion recipe
Gate:            budget, preflight/parity check, screening iters + window, kill rule,
                 selection rule, fresh confirmation window, promotion criteria
Null semantics:  what a null here does and does not mean
Out of scope:    what this lap may not change
```

```text
### <date> — <lap>: <one-line verdict>

Run:            remote run dir, run_id
Screenings:     iter: delta ± CI; whether the kill rule passed
Selection:      pre-registered choice, sha256
Confirmation:   window, seeds/side, paired delta ± clustered CI95, large-loss vs anchor
Decision:       promoted / rejected / inconclusive
Interpretation: what was learned; what not to repeat
```

On promotion or rejection also update `ai/checkpoints/best-checkpoints.json` and, if the
roadmap changes, the "Where The Project Actually Is" section of
`docs/rl-papers/roadmap-and-development-plan.md`.

Keep old entries as written; record a reversal in a new entry.

## Glossary

**BC** — Behavior cloning. Supervised learning from heuristic or checkpoint actions.

**AWBC** — Advantage-weighted BC; high-return actions get larger weights.

**IQL** — Implicit Q-learning. Offline RL learning Q, value, and policy without naive max-Q
exploitation over unsupported actions. The offline baseline.

**CQL** — Conservative Q-learning penalty, so offline RL does not overestimate actions the
data does not cover.

**PPO** — The on-policy algorithm behind the champion recipe (`fh-mj-train-b2b`).

**Anchor** — The frozen champion a lap is measured against, pinned by path and sha256 at
launch. A lap that cannot prove it loaded the exact anchor does not start.

**Screening vs confirmation** — Screening is a cheap look on a shared reusable window (120
episodes) used only to pick a candidate. Confirmation is the single decisive gate on a fresh
unspent window (1500 seeds/side). Only confirmation numbers support a claim.

**Pre-registration** — Fixing budget, screening points, kill rule, selection rule, and
confirmation window in writing before launch.

**Duplicate-seat evaluation** — Same wall seeds with rotated seats, so seat and wall luck
are less confounded.

**Design effect** — Variance inflation from correlated duplicate-seat rotations of one wall
seed. Clustered CIs account for it; iid CIs read too tight.

**Mean reward / mean placement** — Primary metric. Final net score change divided by 1000.

**Large-loss rate** — Fraction of seats crossing the large-loss threshold. A guardrail.

**Positive-reward rate** — Fraction of seats ending with positive final net reward.

**Oracle training** — Privileged hidden-state auxiliary targets, with deployed inference
inputs kept visible-only.

**ReZero growth block** — `x + alpha * F(x)`, `alpha` a learned scalar init to 0, so a grown
network is exactly the anchor at step zero. Alphas that stay near zero are a result (growth
not recruited), not a bug.

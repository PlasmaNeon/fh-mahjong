# AI Evaluation and Promotion

How a checkpoint is measured, how a training lap is registered and judged, and how the training
box is operated. The design of the agent is in [`ai-player.md`](ai-player.md).

## The metric

**Mean placement** over duplicate-seat Chongci matches is the primary metric. Placement values
are fixed in `ai/src/fh_mahjong_ai/evaluate.py` (`_EVAL_PLACEMENT_VALUES`) and must not track
the training reward.

Guardrails: **large-loss rate** (share of seats past the large-loss threshold) and
**positive-reward rate**. Raw win rate is not usable — equal-strength agents push it toward 25%
whatever their EV.

**Duplicate seats.** The same wall seed is played four times with the candidate rotated through
every seat; the other three seats are the heuristic bots. This cancels most wall and seat luck.

## Tools

| Command | Use |
|---|---|
| `fh-mj-evaluate --duplicate-seats` | The gate run. `--batched-eval-slots 256` is ~30× faster than the sequential evaluator. `--symmetry-average suits` evaluates the suit-averaged policy. |
| `fh-mj-compare A.json B.json` | **Required for every verdict.** Seed-clustered paired difference; refuses mismatched seeds, configs, bridge builds, opponents, or evaluators. Read `mean_placement_ci95_clustered`, never the iid CI. |
| `fh-mj-evaluate --opponent-checkpoint` | Strong table: the candidate against three frozen checkpoint seats. A different measurement; pairs only with reports against the same opponent. |
| `fh-mj-benchmark` | Tenhou-style stat sheet (win, deal-in, average win/loss, patterns, routes). A yardstick, never a gate. |
| `fh-mj-serving-parity` | Hard gate before serving: evaluation path and serving path must pick identical actions. Zero decisions checked is a failure. |

Report pairing rules: batched reports pair only with batched reports of the same settings (the
batched forward can flip a near-tied argmax); strong-table reports pair only against the same
opponent checkpoint; symmetry averaging is a policy change, so it pairs with plain reports of
the same seeds.

## Statistics

- The four rotations of one wall seed are correlated; the measured design effect is ~0.85.
- Measured clustered CI95 half-widths on a paired difference: ±0.02 at 1,500 seeds, ±0.011 at
  5,000, ±0.007 at 10,000.
- Screening runs (120 seeds) carry ≈ ±0.07 CIs. They can order checkpoints but cannot resolve
  +0.03 effects. Both early confirmed champions were isolated screening peaks in noisy
  trajectories; most such peaks did not confirm.
- A window used both to select and to score a checkpoint inflates it (winner's curse). The
  original champion measured +0.47 on its reused window and +0.35 on a fresh one.
- At a strong table of the champion against itself, every seed scores exactly 0 (a deterministic
  policy plays the same game from every seat), so a strong-table delta is the candidate's own
  mean placement. A strong-table win can be a non-transitive exploit; check the reverse table
  before acting on it.

## Registering a lap

Every training lap or probe is registered in writing before any compute is spent:

```text
Question:      what the lap would show, and what it would not
Init:          checkpoint path + sha256, frozen at launch
Intervention:  exactly one; everything else identical to the current recipe
Seeds:         training range, evaluation window (fresh, never used)
Evaluation:    which checkpoint(s) are evaluated, against what, with which flags
Pass rule:     clustered CI95 lower bound > 0 and large-loss(candidate) ≤ comparator + 0.015
Null meaning:  what a fail does and does not close
```

Rules:
- One intervention per lap. A lap proves its init loaded exactly (step-zero parity) before
  training.
- No optional stopping, no reselecting among checkpoints after seeing results, no re-evaluating
  on another window after a fail.
- An evaluation window is used once and then retired.
- If the lap evaluates milestones, the selection rule and any kill rule are fixed in advance.
- Write the outcome next to the registration, including fails.

On promotion, update `ai/checkpoints/best-checkpoints.json` and the current-state table in
[`ai-player.md`](ai-player.md). To ship to production, replace the file in
`ai/checkpoints/deploy/` and `ai/Dockerfile.deploy`'s `--checkpoint` in the same PR.

## Seed windows (as of 2026-10-08)

Screening: `--start-seed 910000`, 120 seeds, reusable, never cited for promotion.

Spent evaluation windows (never reuse):

| Window | Used by |
|---|---|
| 870,000+ | early gates (retired: selection and scoring both) |
| 950,000+, 990,000+, 1,030,000+, 1,070,000+, 1,110,000+, 1,150,000+ (3,000), 1,190,000+ | B2b, restart, r2, deep16, gru-width, ds960 confirmations (1,500 seeds each unless noted) |
| 1,720,000–1,721,499 | big-arm confirmation |
| 2,100,000–2,100,199, 2,200,000–2,200,599 | strong-table screen and confirmation |
| 2,500,000–2,504,999 | suit-symmetry probe |
| 2,700,000, 2,710,000, 2,720,000, 2,730,000, 2,900,000, 3,100,000 (+5,000 each) | suit-augment laps, face/ensemble probes, distillation lap |
| 3,200,000–3,209,999, 3,260,000–3,279,999 | control confirmation, look-ahead lap |
| 4,150,000–4,159,999 | reserved: 450-iteration continuation lap |

Reserved but unspent: 1,300,000–1,301,499 (placement-reshape, never run); 3,300,000+ (a
throughput session). Training ranges in use go up to 4,143,999. Pick the next window above
4,160,000 and record it here when registering.

## Training box

- Remote WSL2 machine with an RTX 4090 (24 GB), 24 cores; runs under `/root/fh-mahjong-runs/`.
  Only small anchors and the deployed checkpoint are committed to git.
- Run each lap from its own checkout or worktree at a pinned commit with its own bridge build.
  Never `git pull` or rebuild the bridge in a checkout a running lap imports from.
- Launch laps as systemd units through a flock-guarded script (ssh can double-execute
  commands). Wrap `systemctl reset-failed` in `|| true` under `set -e`.
- Pause with `systemctl kill --signal=SIGSTOP <unit>` at an iteration boundary and resume with
  SIGCONT; the computation is unchanged.
- One GPU-heavy job at a time. A large evaluation beside a lap, or two training arms side by side,
  can exceed 24 GB; WSL then pages GPU memory and both stall for hours.
- `pgrep -f pattern` over ssh matches its own shell; use a bracket pattern (`[f]h-mj-train`).
  Set `PYTHONUNBUFFERED=1` under nohup.
- Cost reference: champion-size lap ~1 min/iteration (batched, 2 pipeline groups); a
  1,500-seed batched confirmation ~3.5 min; a 1,600-match strong table ~3 min.

# Big arm (192×24 scratch) on the batched collector — protocol

**Status: APPROVED by the user 2026-09-26.** Launch waits only on the training-parity condition below.
Codex consults are suspended until the user re-enables them, so terminal results return to the user.
Parent design: [`20260825-mortal-scale-scratch-design.md`](./20260825-mortal-scale-scratch-design.md)
(Amendments 1–4). Everything not stated here is Amendment 1's big arm, unchanged.

## Question

Does the 192×24 scratch package (8.42 M parameters, BC → PPO at 960 matches/iteration) beat
`anchor075`? The control arm (96×4) ended at −0.0722 against a −0.0600 recipe gate, so the
recipe itself is not proven; this run answers the practical question directly and records the
scale comparison as secondary.

## What changes from Amendment 1

**Collector only:** `--collector batched --pool-slots 320` instead of process workers 10 / chunk 320.
Justification:
- Measured 960/768 full cycle at this commit: collect 137–144 s, update 952–960 s → 18.2 min/iteration,
  ≈ 2.5 days for 200 iterations (process collector: 9.4 days); cgroup peak 26.9 GiB
  (status file, "Re-measured 960/768 bench").
- Training parity (`collector-parity-20260926`): control recipe, 10 iterations each collector, seeds
  1,800,000+; iter_010 of each screened on 120 seeds from 1,810,000. **Launch requires** both arms
  clean (no truncation, coverage 1.0), rows/iteration within ±3%, and the batched-vs-process screening
  delta's clustered CI95 containing 0.
- **Parity result (2026-09-27): PASS.** Both arms 10/10 clean (zero truncations, coverage 1.0); mean
  rows/iteration 654,617 (process) vs 653,605 (batched), −0.15%; iter_010 batched − process
  **+0.0062 ± 0.0466** (seed-clustered CI95 contains 0), deal-in 0.1014 vs 0.1009. Descriptive:
  batched entropy ran 0.089–0.092 against 0.093–0.097 in every iteration, and the process arm had a
  one-iteration approx-KL spike (1.32 at iteration 2); the batched sampler is exact inverse-CDF sampling
  of `softmax(logits/T)` in float64. Artifacts `/root/fh-mahjong-runs/collector-parity-20260926/`.
- The two collectors draw from different sampling RNG streams; that is the same class of change as a
  different base seed, and the rollout semantics (rows, labels, rewards, order) are pinned by the
  collector parity and golden-digest gates.

## Fixed before launch

| Item | Value |
|---|---|
| Init | `--scratch --init-from-bc bc-big/best.pt` (sha256 `3d95743b…`), transfer gate exact at step zero |
| Model | 192×24, `kernel_width=1`, `trunk_rezero`, event window 128, privileged critic, aux heads |
| Data | 960 matches/iteration, minibatch 768, `ppo_epochs` 2, `gamma` 0.99, entropy 0, chongci, step cap 4000 |
| Optimizer | two groups: BC-loaded 2e-5 throughout; new parameters 2e-4 for iterations 1–25, then 2e-5 |
| Budget | 200 iterations; `--train-state-every 5` |
| Training seeds | 1,500,000–1,691,999 (reserved, unspent) |
| Code / bridge | `main` at launch (≥ `66e9dab`), bridge built from it; both hashes recorded in the launch manifest |
| Containment | `MemoryHigh=44G`, `MemoryMax=48G`, swap 0, `oom.group=1`; guard: cgroup peak ≤ 38 GiB, tree RSS ≤ 40 GiB; watchdog retargeted to this unit |

## Screening, kill, selection

- Screens at 25/50/75/100/125/150/175/200 on the fixed 120-seed duplicate-seat window from 1,710,000,
  against an `anchor075` comparator **regenerated on the launch bridge** (the bridge changed in PR #242,
  and `fh-mj-compare` refuses cross-bridge pairs).
- Sole early kill: at iteration 100 iff `delta100 − delta75 ≤ 0` and `delta100 < −0.20`.
- Selection: the best healthy milestone by screening delta; an exact tie goes to the later milestone.
  No extension past 200, no rescreening, no reselection.

## Confirmation and verdict

- The selected checkpoint vs a regenerated `anchor075` on fresh seeds **1,720,000–1,721,499**
  (1,500 × 4 duplicate seats), via `fh-mj-compare`.
- **Pass iff** clustered CI95 lower bound > 0 **and** `large_loss(candidate) ≤ comparator + 0.015`.
  A pass makes the checkpoint a gate-qualified research champion; promotion and deployment are separate
  decisions.
- Secondary, same seeds, descriptive: selected big vs control `iter_200` (the control's best milestone).
  Data volumes differ (960 vs 320 matches/iteration), so this measures the package, not size alone.
- Descriptive only, after the verdict: the strong-table readout (big in one seat vs 3 `anchor075`) on
  seeds 2,300,000+.

## Governance

- No optional stopping, no post-hoc gate changes. A change needed mid-run is written here as an
  amendment before it takes effect.
- **Training speed-up work has GPU priority (user directive, 2026-09-27).** When a speed-up session
  needs the GPU, the lap is stopped at an iteration boundary and resumed from `train_state.pt` once the
  speed-up is merged and measured faster on this recipe. The resume adopts the new code only if it
  preserves semantics: the collector goldens, batched-vs-process parity and the full ai suite pass, and
  any float difference is summation order only. Each such resume is recorded in the status file with
  the commit, the measured speed-up, and the resume audit. A change that alters the objective,
  sampling, labels or data is not a speed-up and cannot be adopted mid-run.
- Infrastructure failures (guard kill, OOM, crash) are not scientific results; resume from
  `train_state.pt` is allowed and recorded as an operational deviation with the resume audit
  (the resumed iteration compared against its original emission).
- Live coordination goes in a new status file, `worklog/rl-experiment/20260926-big-arm-status.md`,
  created at launch. Every terminal result returns to the user.

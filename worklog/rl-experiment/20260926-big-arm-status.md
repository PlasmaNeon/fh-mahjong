# Big arm (192×24 scratch, batched collector) — live status

Protocol: [`worklog/specs/20260926-big-arm-batched-protocol.md`](../specs/20260926-big-arm-batched-protocol.md).
Owner session: `mortal-scale-scratch`. Box: the 4090 (`ssh wsl`).

## Current stage

**Lap RUNNING** since 2026-09-27 01:13:58 PDT (fresh from iteration 0), unit `bigarm-lap`. Projected
~7.2 min/iteration (collect ~140 s + update ~290 s with PR #248) → 200 iterations ≈ 24 h, ending about
2026-09-28 01:15 PDT.

## Launch manifest

| Item | Value |
|---|---|
| Commit | `2e9ae54` (main: protocol #246, update fixes #247 + #248) |
| Checkout | `/root/fh-mahjong-bigarm` |
| Bridge | `aad45ebe4972625d0d9332a487179615f27b72f8ce379aa5d484c48aedc7cdec` |
| Init | `bc-big/best.pt` sha256 `3d95743b…`; transfer gate at step zero |
| Anchor | `anchor075` sha256 `ce9d867f…` |
| Seeds | training 1,500,000–1,691,999; screens 1,710,000 (120); confirmation 1,720,000–1,721,499 |
| Runs dir | `/root/fh-mahjong-runs/big-arm/` (`launch-manifest.json`, `ckpt/`, `screen/`, `logs/`) |
| Guards | `cgroup_guard38.sh bigarm-lap 5`, `watchdog_lap.sh` (retargeted; launcher greps both) |
| Screens | `followup.sh` on the box: screens each milestone as it lands and applies the iteration-100 kill rule |

The anchor screening comparator is regenerated on this bridge (`screen/anchor-screen.json`). Rebuilding
the bridge at a different commit changes its hash even with identical Go sources (Go stamps the VCS
revision), and `fh-mj-compare` refuses cross-bridge pairs; the comparator built at `66e9dab` is kept in
`superseded/`.

Floats differ between processes by summation order: the collector's `cudnn.benchmark` and PR #248's
update autotune pick algorithms by timing.

## Screening (vs `anchor075`, 120 seeds × 4 from 1,710,000)

| Iteration | Delta | CI95 | Large-loss (cand / anchor) | Notes |
|---|---|---|---|---|
| 25 | | | | |
| 50 | | | | |
| 75 | | | | |
| 100 | | | | kill iff Δ100 − Δ75 ≤ 0 and Δ100 < −0.20 |
| 125 | | | | |
| 150 | | | | |
| 175 | | | | |
| 200 | | | | |

## Event log

- `2026-09-27 00:5x` — mortal-scale-scratch — collector training parity PASS (see protocol). Launch held ~1 h
  for PRs #247/#248 (update 161 → 48.6 ms/step on this recipe), per the user.
- `2026-09-27 01:05` — mortal-scale-scratch — **lap launched** on `2e9ae54`.
- `2026-09-27 01:10` — mortal-scale-scratch — **stopped during iteration 1** to give the speed-up session a
  clean GPU window (user directive: speed-up work has GPU priority). No checkpoint or `train_state` existed
  (first save is at iteration 5), so the lap relaunches fresh from iteration 0 on the same seeds rather
  than resuming; archived as `attempt1-paused-iter0/`. The anchor comparator run was stopped too and is
  regenerated before the first screen.
- `2026-09-27 01:13` — mortal-scale-scratch — **lap relaunched** fresh from iteration 0 on `2e9ae54`. The
  speed-up session measured the CUDA-graphed training step at 45.6 vs 46.5 ms/step on this recipe (2%, the
  update is GPU-bound at 192×24), so the lap does not wait for it. A bf16 trunk measured 25.0 ms/step, but it
  changes precision, so it is outside the mid-run adoption bar and is not for this lap.
- `2026-09-27 01:52` — mortal-scale-scratch — **paused after the iteration-5 `train_state`** for the speed-up
  session's collector/bf16 timing window (user directive). Iterations 2–5 ran 7.3 min each on `2e9ae54`,
  on projection. `pause-at-save.sh` stops the unit when `train_state.pt` changes, so nothing is recomputed.
- `—` — (add next event here)

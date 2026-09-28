# Big arm (192×24 scratch, batched collector) — live status

Protocol: [`worklog/specs/20260926-big-arm-batched-protocol.md`](../specs/20260926-big-arm-batched-protocol.md).
Owner session: `mortal-scale-scratch`. Box: the 4090 (`ssh wsl`).

## Current stage

**Lap COMPLETE 200/200** (2026-09-28 01:38 PDT): `Result=success`, exit 0, 200 history rows under run `8684c100…`, zero truncations, cgroup peak 32.47 GiB (guard 38), watchdog `CLEAN`. Selected `iter_200.pt` (sha256 `9835611d…`). **Confirmation RUNNING** on seeds 1,720,000–1,721,499: selected big, `anchor075` and control `iter_200`, all on the launch bridge.

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
| 25 | **−0.4181** | ±0.0652 (sig. YES) | 0.1458 / 0.0458 | control arm at 25: −0.4250. Placement +0.0431 vs anchor +0.4611; deal-in 0.0999 vs 0.1033 (candidate lower); 4th-share Δ +0.1396, training-utility Δ −0.3795. Screen took 54 min beside the lap (192×24 forward ~4.5 ms per decision) |
| 50 | **−0.3597** | ±0.0687 (sig. YES) | 0.1083 / 0.0458 | control at 50: −0.3708. Deal-in 0.1004 vs 0.1033 |
| 75 | **−0.2347** | ±0.0710 (sig. YES) | 0.0938 / 0.0458 | control at 75: −0.2903. Deal-in 0.1006 |
| 100 | **−0.1972** | ±0.0702 (sig. YES) | 0.0813 / 0.0458 | **kill rule not fired** (Δ100 − Δ75 = +0.0375 > 0). Control at 100: −0.2375. Deal-in 0.0978 |
| 125 | **−0.1611** | ±0.0774 (sig. YES) | 0.0625 / 0.0458 | control at 125: −0.1667. 4th-share Δ +0.0312 and large-loss Δ +0.0167 now straddle zero |
| 150 | **−0.1514** | ±0.0685 (sig. YES) | 0.0688 / 0.0458 | control at 150: −0.1097; the big arm falls behind the control here. Gain since 125: +0.0097 |
| 175 | **−0.1486** | ±0.0716 (sig. YES) | 0.0625 / 0.0458 | control at 175: −0.0861. Gain since 150: +0.0028 (plateau). 4th-share and large-loss deltas straddle zero; deal-in 0.0987 |
| 200 | **−0.1389** | ±0.0769 (sig. YES) | 0.0750 / 0.0458 | **selected** (best screening delta). Control at 200: −0.0722. 4th-share Δ +0.0250 [−0.0149, +0.0649]; large-loss Δ +0.0292 [−0.0002, +0.0586]; deal-in 0.0984 vs 0.1033 |

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
- `2026-09-27 02:00` — mortal-scale-scratch — **resumed from `train_state` (next iteration 6) on `cabaabc`**,
  adopting PR #250's graphed update step under the protocol's speed-up rule (the graph replays the eager
  step's kernels, within rtol 1e-5 on the box; `ppo_update` only; full ai suite green; Python-only, bridge
  snapshot unchanged). Registered operational deviation. Resume audit: one `run_id` (`8684c100…`), six
  history rows; iteration 6 steps 1,962,410, `optimizer_steps` 5,112 = 2 × ceil(1,962,410 / 768), zero
  truncations, label coverage 1.0, approx-KL 0.00101 / entropy 0.0844 / value loss 0.0155, all inside
  iterations 1–5. Iteration 6 ran 6.5 min including restart.
- `2026-09-27 02:32` — mortal-scale-scratch — **paused after the iteration-10 `train_state`** for the speed-up
  session's threaded-pool timing (active only at pipeline groups > 1; this lap runs groups = 1, so nothing
  to adopt). Iterations 7–10 ran 6.4 min each on `cabaabc`.
- `2026-09-27 02:38` — mortal-scale-scratch — resumed from `train_state` (next iteration 11) on `cabaabc`, no
  code change. Resume audit: one `run_id`, 11 rows; iteration 11 steps 1,947,164, `optimizer_steps` 5,072 =
  2 × ceil(1,947,164 / 768), zero truncations, coverage 1.0, approx-KL 0.00107 / entropy 0.0825 / value loss
  0.0159, inside iterations 8–10.
- `2026-09-27 03:11` — mortal-scale-scratch — **paused after the iteration-15 `train_state`** for the speed-up
  session's end-to-end timing of the opt-in recipe (bf16 trunk + 2 pipeline groups, its own clone and seeds).
  Iterations 12–15 ran 6.4 min each.
- `2026-09-27 03:19` — mortal-scale-scratch — resumed from `train_state` (next iteration 16) on `cabaabc`, no
  code change; the speed-up session's last planned window. Resume audit: one `run_id`, 16 rows; iteration 16
  steps 1,949,246, `optimizer_steps` 5,078 = 2 × ceil(1,949,246 / 768), zero truncations, coverage 1.0,
  approx-KL 0.00113 / entropy 0.0792 / value loss 0.0160, inside iterations 14–15. The three pauses cost
  ~20 min in all. The speed-up session measured the opt-in recipe (bf16 trunk + 2 pipeline groups) on this
  model at 3.6 min/iteration end to end; future laps only, bf16 pending a quality check.
- `2026-09-27 05:17` — mortal-scale-scratch — iteration-25 screen **−0.4181 ± 0.0652**, level with the control arm's −0.4250 at 25.
- `2026-09-27 08:10–22:33` — mortal-scale-scratch — screens 50–175 (table). The kill rule at 100 did not fire. The big arm tracked the control arm through 125, then flattened near −0.15 (gains +0.0097 and +0.0028 per 25) while the control reached −0.0861 at 175. The session's event waiter was broken from 06:05 (a macOS `paste` without `-` left its counter empty, so it never fired); the on-box orchestrator screened every milestone on time regardless. Test that a waiter fires before trusting it.
- `2026-09-28 00:23` — mortal-scale-scratch — **PAUSED by the user during iteration 199.** Last `train_state` = iteration 195, so a resume re-runs 196–200 (~32 min). The screening orchestrator is stopped; the iteration-200 screen and the confirmation wait for the user's resume.
- `2026-09-28` — mortal-scale-scratch — **resumed by the user** from the iteration-195 `train_state` on `cabaabc`; iterations 196–200 re-run, then the iteration-200 screen, selection and confirmation.
- `2026-09-28 01:38` — mortal-scale-scratch — **lap complete 200/200**, clean (see Current stage). Iteration 200: steps 1,880,430, `optimizer_steps` 4,898 = 2 × ceil(1,880,430 / 768).
- `2026-09-28 01:55` — mortal-scale-scratch — iteration-200 screen **−0.1389 ± 0.0769**, the best of the eight milestones → **`iter_200` selected**. Confirmation launched (`confirm.sh 200`).
- `—` — (add next event here)

# mortal-scale-scratch — live experiment status

**This file is the single source of truth for CURRENT mortal-scale-scratch run state.**

- **Durable protocol / rulings** → `../specs/20260825-mortal-scale-scratch-design.md` (Amendments 1–3)
- **Durable procedure** → `../plans/20260825-mortal-scale-scratch-runbook.md`
- **Consult thread** → Codex `01a0147d` (the thread that ruled the scale-campaign closure this experiment reopens); every terminal result returns there
- **Box** → `ssh wsl`, repo `/root/fh-mahjong`, bridge `/root/fh-mahjong/build/libfh_mahjong_bridge.so`, runs under `/root/fh-mahjong-runs/mortal-scale-scratch/`, uv at `/root/.local/bin/uv`
- **Live state (what is running right now)** → this file

## How to update this file

1. Edit **Current stage** in place — overwrite it, don't append. It must describe only *now*.
2. Add one line to **Event log** for anything another session would need to know.
3. Sign every event with your **session name** (`mortal-scale-scratch`, `fh-mahjong-5b`, …).
   Never write "I" or "the peer" — with 2+ sessions on this protocol those words have no referent.
4. Fill the screening tables from `fh-mj-compare` output only. A delta with no `fh-mj-compare`
   behind it is not a delta.
5. Do **not** copy this state into `MEMORY.md`. Memory gets the durable outcome when the
   experiment ends, not the running state.

---

## Current stage

**STAGE 5 — the control lap is RUNNING** as `msscratch-control.service` (launched
2026-08-27 10:43 PDT; 96×4, 200 iterations, 320/256, base seed 1,400,000; both guards
armed — `cgroup_guard38.sh` and a retargeted `watchdog_lap.sh`; 44/48 GiB containment).
Log `logs/control-lap.log`, checkpoints `control/ckpt/`. Iteration 1 took 468 s
including startup, so the lap projects to **≈ 26 hours**. Screen at iterations
25/50/75/100/125/150/175/200 per §7; the only early kill is at 100.

Stage 4 passed: the export's transfer gate was exact and the 960/768 bench cleared all
six go/no-go gates. **The big lap projects to ≈ 9.4 days** (0.29888 matches/s, 838.9 s
update → 67.5 min/iteration); no wall-time ceiling was ever registered, so this is
recorded, not a breach — but it belongs in the consult before the big lap is authorized.

Stage 3 is closed: both ReZero BC arms passed every Amendment 3 gate. The plain-trunk
attempts stay archived as diagnostic / failure evidence and are inadmissible for PPO
(`bc-control-plain/`, `bc-big-plain/`, logs and guard CSVs suffixed `-plain`).

Pinned for the rest of the experiment: box checkout `8ad2688` (`main`), bridge
`a487bcb7c2b15412589eac2303b5ce6ce009790249b0bd3662f5ae8d8ff44034` — unchanged across
every commit since it was built from `7e5d623`, as none of them touched Go; the dataset
was generated on the earlier bridge `66f7a061…` (same Go sources). Anchor `ce9d867f…`
(matches §0). Bench init `bench/big-init.pt` sha256 `4948963d…`.

## Reading the event-path telemetry

Iteration 1 of the control lap, the first live exercise of Amendment 4:

| key | iter 1 | reading |
|---|---|---|
| `event_slice_fro` | 0.31679 | started at exactly 0.0 (the `expect_zero_init` gate passed) |
| `event_slice_update_fro` | 0.31679 | identical to the norm — the whole of it was gained in one iteration |
| `event_slice_rms_ratio` | 0.01242 | still ~1.2 % of the non-event columns per element |
| `event_encoder_update_fro` | 8.0166 | against a param norm of 254.03 |
| `trunk_alpha_update_l2` | 0.00087 | alphas essentially still at their BC values |

**The event read-in is not dormant.** It left zero in the first iteration despite sitting
in the 2e-5 group, which is what Amendment 4 clause 3 predicted: an iteration is thousands
of optimizer steps, so the 10× lr gap alone never established dormancy. `rms_ratio` is the
number to watch at 25/50 — it says how much of the trunk's input the event path actually
accounts for, not merely that it is non-zero.

**Median convention:** `trunk_alpha_abs_median` uses `torch.median`, which returns the
lower middle element for an even count. The BC-stage `alphas.py` readout averages the two
middle elements. For the control's 4 alphas that reads 0.0409 here and 0.0505 there off
the same weights. Compare like with like.

## Stage checklist

| # | Stage | Runbook | State | Evidence |
|---|---|---|---|---|
| 1 | Bridge build + `uv sync` + digests | §1 | done 2026-08-26 | dataset bridge `66f7a061…` (box's binary at the time); training/eval bridge `a487bcb7…` rebuilt from checkout `7e5d623`; anchor sha256 `ce9d867f…` ✓ |
| 2 | BC dataset — 8,000 matches, seeds 1,300,000–1,307,999, `--learning-seat-rule seed-mod-4` | §2 | done 2026-08-26 | manifest sha256 `2898960f…`; 4,051,446 transitions from 8,000 episodes (43,063 s); per seat 0/1/2/3 = 1,009,528 / 1,013,787 / 1,015,300 / 1,012,831; 82 shards, 1,033,621,603 B on disk |
| 2a | A2 dataset gate — calculated resident ≤ 30.00 GiB, loader-only cgroup peak ≤ 32.00 GiB | §2 | PASS 2026-08-26 | 4,051,446 × 7,018 B = 26.48 GiB (arrays 26.50 GiB); loader-only `memory.peak` 29,475,266,560 B = 27.45 GiB; `anon`/`file` were read after the loader exited (233,472 / 359,747,584 B — not informative); `free -g` 47 free / 50 total; log `logs/gate2a.log` |
| 3 | BC control (96×4, k=1) — attempt 1, plain trunk (diagnostic only, inadmissible per Amendment 3 §3; archived as `bc-control-plain/`) | §3 | done 2026-08-26 | `best_epoch` 5, best val CE 0.13832, `stopped_early` true, `epochs_run` 10, all epochs `validation_events: zeroed`; best-epoch top-1 0.9556 (top-3 0.9942; discard 0.947, chii 0.969, pon 0.995, kan 0.973, pass 0.989, win 1.0); per seat 0/1/2/3 top-1 0.9555 / 0.9555 / 0.9560 / 0.9555 (n 103,988 / 96,965 / 97,277 / 109,209), recompute overall 0.9556 = report ✓; cgroup peak 31,261,163,520 B = 29.11 GiB, tree RSS peak 28.18 GiB; `best.pt` sha256 `8f5a227f354e2db20e3308f2c5bed219df8c7126ab0498213fdafa91fbb30cd7` |
| 4 | BC big (192×24, k=1) — attempt 1, plain trunk (archived as `bc-big-plain/`) | §3 | FAILED — policy CE flat at 1.6–1.8 from step 200 through epoch 3; epoch 1/2 val top-1 44.13 % / 44.71 % (≈ majority-discard baseline); stopped by hand, guard `UNIT-EXITED` (cgroup peak 28.25 GiB); artifacts kept in `bc-big-plain/` | `best_epoch`, val CE, top-1 (zeroed events) overall + per seat, `best.pt` sha256 |
| 3b | **BC control (96×4, k=1, `trunk_rezero`) — attempt 2, canonical** | §3 | **PASS 2026-08-27** | `best_epoch` 4, best val CE 0.122959, `stopped_early` true, `epochs_run` 9; zeroed-event val top-1 **0.9582** (top-3 0.9950), per seat 0/1/2/3 = 0.9584 / 0.9581 / 0.9587 / 0.9578, readout CE 0.1230; per family discard 0.9499, chii 0.9646, pon 0.9922, kan 0.9693, pass 0.9947, win 1.0, haitei 1.0 (n=12); alphas 4/4 finite and non-zero, \|α\| min/median/max 0.0289 / 0.0505 / 0.0871; guard `UNIT-EXITED`, cgroup peak 30,781,386,752 B = 28.67 GiB, tree RSS peak 28.17 GiB; `best.pt` sha256 `ccc8fd5172ea810d3d29f88473444cd6553b97e5fd4ae234706272dbb7a043aa` |
| 4b | **BC big (192×24, k=1, `trunk_rezero`) — attempt 2, canonical** | §3 | **PASS 2026-08-27** | `best_epoch` 3, best val CE 0.124828, `stopped_early` true, `epochs_run` 8; zeroed-event val top-1 **0.9581** (top-3 0.9951), per seat 0/1/2/3 = 0.9580 / 0.9580 / 0.9582 / 0.9581, readout CE 0.1248; per family discard 0.9494, chii 0.9703, pon 0.9902, kan 0.9519, pass 0.9956, win 1.0, haitei 1.0 (n=12); alphas 24/24 finite and non-zero, \|α\| min/median/max 3.24e-05 / 0.00492 / 0.02962; guard `UNIT-EXITED`, cgroup peak 30,792,699,904 B = 28.68 GiB, tree RSS peak 28.17 GiB; `best.pt` sha256 `3d95743b60646cd977c83a69691c9348a886e70535a08da8774cae8fd3ee1e17` |
| 4a | Bench-init export — `fh-mj-export-scratch-init` from `bc-big/best.pt` | §4 | **done 2026-08-27** | `big-init.pt` sha256 `4948963deea8cbf72a38e8ec53464ab18c5d1be9e74d7cc0efc93a75c6798cea`; transfer gate exact — `max_abs_logit_diff` 0.0, `max_abs_prob_diff` 0.0, `greedy_match_rate` 1.0, `loaded_tensors_identical` true, 132 loaded / 37 unloaded keys, probe seed 20260825 × 64 rows; `bc_checkpoint_sha256` `3d95743b…` = `bc-big/best.pt` ✓; record in `bench/big-init-transfer-gate.json` |
| 5 | Bench 960/768 (big only, `--champion big-init.pt`) | §4 | **PASS 2026-08-27 — all six go/no-go gates** | (1) unit `Result=success`, guard `UNIT-EXITED`, no kill, no CUDA OOM; (2) cgroup `memory.peak` 37,718,990,848 B = **35.13 GiB** ≤ 38.00 (margin 2.87); (3) tree RSS peak 40,526,745,600 B = **37.74 GiB** ≤ 40.00 (margin 2.26; report's `host_peak_rss_bytes` 37.75 GiB agrees); (4) CUDA allocated **6.47 GiB** ≤ 20.00, reserved 7.49 GiB; (5) `truncated_matches` 0 / rate 0.0, `dealin_positive_rate` 0.0931 > 0, `rank_label_coverage` 1.0; (6) seeds 1,700,000–1,700,959 complete by construction (`env.reset(seed=base_seed + m)`, m = 0..959, and coverage 1.0 means every match reached a terminal result), rollout digest `980106e6…`, rows 1,966,232, **optimizer_steps 5,122 = 2 × ceil(1,966,232 / 768) = 2 × 2,561 exactly** (ragged tail correct), no monitoring gaps. `all_digests_equal` / `rows_and_labels_equal` true but non-load-bearing at one worker count. Throughput `matches_per_second` 0.29888, `update_seconds` 838.90 → **4,050.9 s/iteration (67.5 min); 200 iterations ≈ 810,180 s ≈ 9.4 days** for the big lap |
| 6 | Control lap — 200 iters, 320/256, base seed 1,400,000 | §5 | running 2026-08-27 (`msscratch-control`) | iter 1 healthy: `lr_bc` 2e-05, `lr_heads` 2e-04 ✓, rows 653,728, `optimizer_steps` 5,108 = 2 × ceil(653,728 / 256) = 2 × 2,554 exactly ✓, `truncation_rate` 0.0, `dealin_positive_rate` 0.0922, `rank_label_coverage` 1.0; Amendment 4 telemetry live and the init gate passed (see above). 468 s/iter → ≈ 26 h |
| 7 | Control recipe gate (iter-200 delta ≥ −0.0600) | §7 | not started | `fh-mj-compare` at iter 200 |
| 8 | Big lap — 200 iters, 960/768, base seed 1,500,000 | §8 | not started | `history.json`, transfer-gate record, guard verdicts |
| 9 | Selection + confirmation (1500 × 4 seats, seed 1,720,000) | §9 | not started | primary + secondary `fh-mj-compare` |

## Screening comparator (generated once, reused for every screening of both arms)

`screen/anchor-screen-current-bridge.json`, sha256 `e077e6ef2c3c6732a843f9405d9a2e33b112add580a325b7de8c1b19be5c6235`,
generated 2026-08-27 from `anchor075` (`ce9d867f…`) on the pinned bridge — the report's own
`bridge_lib_sha256` reads `a487bcb7…` ✓. 480 episodes (120 seeds × 4 duplicate seats),
`truncation_count` 0, `rank_parity_mismatches` 0. Anchor baseline: `mean_reward` 0.91078
(CI95 0.11127), `mean_placement` 0.46111 (CI95 clustered 0.05408), `large_loss_rate`
0.04583 at threshold −1.0, `fourth_place_rate` 0.0875, `deal_in_rate` 0.10335.

Its `model_config` is correctly the anchor's own architecture — `kernel_width` 3,
`trunk_rezero` false, 96×4 — not the arms'. The §7 anchor command deliberately omits
`--model-kernel-width 1 --model-trunk-rezero`; passing them would build the wrong net.

## Screening — control arm

Window: 120 duplicate seats, `--start-seed 1710000`, against `anchor075` regenerated on the
current bridge. Delta = `fh-mj-compare mean_delta` (candidate − anchor).

| iteration | mean_delta | CI95 (clustered) | large_loss cand / anchor | telemetry healthy | notes |
|---|---|---|---|---|---|
| 25 | **−0.4250** | ±0.0743 (sig. YES) | 0.1479 / 0.0458 | yes | placement +0.0361 vs +0.4611; 4th-share Δ +0.1385, large-loss Δ +0.1021, training-utility Δ −0.3821; deal-in 0.0992 vs 0.1033; tail gate FAIL. No rule fires at 25 — §7: a scratch curve starting far below the anchor is not a kill |
| 50 | **−0.3708** | ±0.0687 (sig. YES) | 0.1313 / 0.0458 | yes | placement +0.0903; 4th-share Δ +0.1083, large-loss Δ +0.0854, training-utility Δ −0.3264; tail gate FAIL. Improvement 25→50 = **+0.0542 per 25 iters**, every secondary moving the right way. Reaching the §7 gate (−0.0600) from here needs +0.3108 over 150 iters = **+0.0518 per 25**, i.e. ~96 % of the current rate sustained with almost no decay |
| 75 | **−0.2903** | ±0.0706 (sig. YES) | 0.1333 / 0.0458 | yes | placement +0.1708; 4th-share Δ +0.1000, large-loss Δ +0.0875, training-utility Δ −0.2663; deal-in **0.0995 vs 0.1033 — candidate now better than the anchor**; tail gate FAIL. Improvement 50→75 = **+0.0805 per 25 iters — the rate accelerated**, not decayed. Reaching −0.0600 from here needs +0.2303 over 125 iters = **+0.0461 per 25**, i.e. 57 % of the latest rate; even the slowest interval seen so far (+0.0542) clears it with margin. Only non-monotone secondary: large_loss 0.1313 → 0.1333, effectively flat |
| 100 | | | | | kill iff `delta100 − delta75 ≤ 0` and `delta100 < −0.20` |
| 125 | | | | | |
| 150 | | | | | |
| 175 | | | | | |
| 200 | | | | | big arm authorized iff `≥ −0.0600` |

## Screening — big arm

Same window and comparator.

| iteration | mean_delta | CI95 (clustered) | large_loss cand / anchor | telemetry healthy | notes |
|---|---|---|---|---|---|
| 25 | | | | | |
| 50 | | | | | |
| 75 | | | | | |
| 100 | | | | | kill iff `delta100 − delta75 ≤ 0` and `delta100 < −0.20` |
| 125 | | | | | |
| 150 | | | | | |
| 175 | | | | | |
| 200 | | | | | |

## Confirmation

1500 paired seeds × 4 duplicate seats, `--start-seed 1720000`, one window, no reselection.
Both gates required per claim: clustered CI95 lower bound > 0 AND
`large_loss_rate(candidate) ≤ large_loss_rate(comparator) + 0.015`.

| claim | candidate | comparator | mean_delta | CI95 | large_loss | verdict |
|---|---|---|---|---|---|---|
| primary (practical gate) | big iter_??? | anchor075 | | | | |
| secondary (package) | big iter_??? | control iter_??? | | | | |

## Open notes for the consult thread

- (none)

## Amendment 4 + Stage 3 ruling — lap telemetry prerequisite

Amendment 4 ratifies the parameter groups unchanged (`trunk.0.weight`, zeroed event
columns included, stays in the `bc` group at `2e-5`; `event_encoder.*` stays in `heads`
at `2e-4` through iteration 25) and forbids attributing a flat iteration-25/50 delta to
"the event head has not engaged" without telemetry — inadmissible outright from
iteration 50 on. The Stage 3 terminal ruling added main-trunk alpha readouts and
corrected the integrity gate to fail closed.

Implemented in PR #233: `train_state.EventPathTelemetry` and `TrunkAlphaTelemetry` write
`event_slice_{fro,rms,max_abs,update_fro,rms_ratio}`, `event_encoder_{param_norm,update_fro}`
and `trunk_alpha_{count,finite_count,abs_min,abs_median,abs_max,l2,update_l2}` to every
`history.json` row; the iteration-0 event snapshot goes to `metadata["event_path_init"]`.
Observed magnitudes gate nothing. The integrity check does: a non-zero slice at iteration 0
on a fresh `--init-from-bc` lap raises before the first collection, and a non-finite readout
or an exactly-unchanged slice halts the lap **after** that iteration's history row,
checkpoint and train_state are durable. Reading rule in runbook §7.

**Ordering (ruling §5): merge PR #233, sync and pin that checkout on the box, and only then
run §4 export → §4 bench → §5 control lap.**

## Event log

Append only. `UTC timestamp — session-name — what happened.`

- `2026-08-25` — mortal-scale-scratch — runbook, status file and follow-up flag docs written; nothing launched.
- `2026-08-25` — mortal-scale-scratch — Amendment 2 ratified (thread `01a0147d`): 8,000 single-seat matches, dataset gates 30.00/32.00 GiB, bench through an exported scratch-init checkpoint. `fh-mj-generate-data --learning-seat-rule seed-mod-4` and `fh-mj-export-scratch-init` landed; runbook §0/§2/§3/§4 follow it.
- `2026-08-26 ~04:15Z` — mortal-scale-scratch — PR #223 merged to main (`9098aed`). Runbook §1 run on the box: `git pull` (a740662 → 9098aed), bridge rebuilt, `uv sync`. **Collision:** a placement-reshape Stage-1 lap (session `placement-reshape-bc`, pinned bridge `66f7a061…`, checkout frozen at `a740662`) was already running; the rebuild changed the source-path bridge to `cf4df3f2…`. The running lap was unaffected (the drift check hashes the per-run snapshot), the peer session restored the pinned bytes over `build/libfh_mahjong_bridge.so` (rebuilt copy kept as `…so.rebuilt-9098aed`), and the checkout stays at `9098aed` pending that session's decision. A first generation attempt (pid 1394200, wrong bridge) was stopped and its partial `bc-data/` deleted.
- `2026-08-26 ~04:45Z` — mortal-scale-scratch — Stage 2 launched with the peer session's OK against the pinned bridge `66f7a061…`; GPU stages queued behind placement-reshape.
- `2026-08-26 ~16:43Z` — mortal-scale-scratch — Stage 2 done (43,063 s): 4,051,446 transitions, manifest saved.
- `2026-08-26` — placement-reshape-bc — box declared free (lap 150/150 clean, registered NULL, no confirmation run). `/root/fh-mahjong-runs/placement-reshape/` is a read-only archive; its reserved window 1,300,000–1,301,499 was never spent.
- `2026-08-26` — mortal-scale-scratch — checkout → `main` `7e5d623`, bridge rebuilt (`a487bcb7…`), `uv sync`; Gate 2a PASS (26.48 / 27.45 GiB); BC control launched as `msscratch-bc-control`.
- `2026-08-26` — mortal-scale-scratch — BC control finished (early stop epoch 10, best 5, val top-1 0.9556, guard verdict `UNIT-EXITED`, no kill); per-seat readout run before BC big (both need the full dataset resident — never overlap them); BC big launched as `msscratch-bc-big`.
- `2026-08-27` — mortal-scale-scratch — BC big (attempt 1) stopped at epoch 3: no learning (val top-1 44.7 %, policy CE ≈1.7 throughout). Prerequisite failure per runbook §3; consult opened on thread `01a0147d` (options: ReZero trunk flag / BC lr-warmup+clip / block normalization).
- `2026-08-27` — mortal-scale-scratch — Amendment 3 ratified (thread `01a0147d`): `ModelConfig.trunk_rezero` / `--model-trunk-rezero`, both arms re-run BC under it, BC optimization frozen, acceptance gate (control top-1 ≥ 0.94, CE ≤ 0.20; big within 0.005 / 0.02 of control, per seat ≥ 0.93). Code + tests landed; plain-trunk runs archived as `bc-control-plain/` and `bc-big-plain/`.
- `2026-08-27` — mortal-scale-scratch — box updated to `af08333` (Amendment 3 code; bridge unchanged at `a487bcb7…`), plain-trunk logs and guard CSVs suffixed `-plain`, BC control attempt 2 launched as `msscratch-bc-control` with `--model-trunk-rezero`. Early signal: policy CE 1.99 → ~0.70 within epoch 1 (the plain 24-block trunk never left 1.6–1.8), i.e. the ReZero trunk trains.
- `2026-08-27` — mortal-scale-scratch — box chain armed as `msscratch-chain.service`: waits for BC control, runs the alpha + per-seat readouts, evaluates the Amendment 3 §5 control gate, and launches BC big **only** on PASS (fail-closed on any unparsed or out-of-range value; verdicts in `logs/chain-verdict.txt`). It stops after the big readout — export, bench and both PPO laps stay manual.
- `2026-08-27` — mortal-scale-scratch — Amendment 4 ratified (thread `01a0147d`): parameter groups stay as they are, no slice-specific lr; "the event head has not engaged" is not a default excuse for a flat iteration-25/50 delta and is inadmissible from iteration 50 on; event-slice + event-encoder telemetry is mandatory for both arms. Telemetry not yet implemented — blocks the §5 lap.
- `2026-08-27 08:41Z` — mortal-scale-scratch — BC control (ReZero) PASSED the §3 gate: top-1 0.9582, CE 0.1230, 4/4 alphas non-zero. Chain launched BC big automatically.
- `2026-08-27 10:20Z` — mortal-scale-scratch — BC big (ReZero) PASSED the §3 gate: top-1 0.9581 (control − 0.0001, limit 0.0050), CE 0.1248 (control + 0.0018, limit 0.0200), every seat ≥ 0.9580, 24/24 alphas non-zero. Amendment 3 is vindicated: the identical 24-block trunk that would not leave 44.7 % on plain blocks now matches a 4-block net. **Stage 3 complete; the chain stopped as designed.** Diagnostic worth carrying: 3.07× the parameters buys ~0.0000 on BC, and the big arm's alphas are an order of magnitude smaller than control's (median 0.0049 vs 0.0505) with the largest magnitudes in blocks 17–22 — the deep trunk is barely used at the BC ceiling, which is the heuristic itself. That says nothing yet about PPO.
- `2026-08-27` — mortal-scale-scratch — Stage 3 terminal ruling returned (thread `01a0147d`): Stage 3 passes; BC parity is not adverse evidence and updates no prior (it removes unequal BC quality as an alternative explanation for later PPO results); the alpha spread is diagnostic only but main-trunk alpha telemetry now rides both laps. **Correction: Amendment 4's integrity gate must FAIL CLOSED** — my warnings-only reading was overruled, "cannot change stopping" governs magnitudes, not the gate. PR #233 updated accordingly. Ordering fixed: merge #233 → sync/pin the box → §4 export → §4 bench → §5 control lap.
- `2026-08-27` — mortal-scale-scratch — PR #233 merged (`8ad2688`); box synced to it, `uv sync` clean, bridge digest unchanged (`a487bcb7…`, no Go in the diff). §4 export done — `big-init.pt` `4948963d…`, transfer gate exact (0.0 / 0.0 / 1.0, tensors identical). Bench 960/768 launched as `msscratch-bench`.
- `2026-08-27` — mortal-scale-scratch — §4 bench PASS on all six gates (cgroup 35.13 / tree 37.74 / CUDA 6.47 GiB; truncation 0; `optimizer_steps` 5,122 = 2 × ceil(1,966,232 / 768) exactly). Throughput projects the **big lap at ≈ 9.4 days** — recorded, not a breach (no ceiling was registered), but it goes to the consult before the big lap is authorized.
- `2026-08-27 10:43 PDT` — mortal-scale-scratch — §5 control lap launched (`msscratch-control`, both guards armed). `watchdog_lap.sh` had to be retargeted first: it hardcodes `UNIT=ds960-lap` and a `RUNS_DIR` inside the read-only data-scale-960 archive, so arming it as shipped would have watched the wrong unit and written into that archive. Iteration 1 healthy; Amendment 4's `expect_zero_init` gate passed against a real BC transfer and the event slice left zero immediately (`event_slice_fro` = `event_slice_update_fro` = 0.3168, `rms_ratio` 0.0124).
- `2026-08-28 07:5x UTC` — mortal-scale-scratch — §5 control lap **STOPPED BY USER at iteration 101/200**, not by any protocol rule. `msscratch-control` stopped, both guards cleaned up. Last checkpoint `control/ckpt/iter_101.pt`; `train_state.pt` last written at iteration 100, so a resume restarts from 100 (`--resume-from-state`, `--collector` is rejected-on-change). Screens recorded: 25 −0.4250, 50 −0.3708, 75 −0.2903 — improving, and the rate accelerated (+0.0542 then +0.0805 per 25). The iteration-100 screen was left running against the already-written `iter_100.pt`; its delta lands in `logs/compare-control-100.txt`. **The §7 recipe gate at iteration 200 was never reached, so the big arm is neither authorized nor refused.** GPU handover to the batched-b2b G1 session was NOT signalled — that session is holding off pulling PR #232 and rebuilding the bridge on this box until told, and the remaining screens depend on both staying as they are.
- `—` — (add next event here)

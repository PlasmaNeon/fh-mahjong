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

**STAGE 3 (ReZero) COMPLETE — both BC arms trained and both acceptance gates PASSED
(2026-08-27).** Control 96×4 and big 192×24, identical recipe, `--model-trunk-rezero`,
BC optimization frozen. Next: §4 `fh-mj-export-scratch-init` from `bc-big/best.pt`, then
the 960/768 bench, then the §5 control lap. **The §5 lap is blocked on the Amendment 4
event-path telemetry reaching the box** (see below). GPU lane otherwise free
(placement-reshape closed as a registered NULL; `/root/fh-mahjong-runs/placement-reshape/`
is a read-only archive).

The plain-trunk attempts stay archived as diagnostic / failure evidence and are
inadmissible for PPO (`bc-control-plain/`, `bc-big-plain/`, logs and guard CSVs
suffixed `-plain`).

Pinned for the rest of the experiment: checkout `7e5d623` (plus the Amendment 3 code at
`af08333`; Go sources unchanged, bridge digest identical), bridge
`a487bcb7c2b15412589eac2303b5ce6ce009790249b0bd3662f5ae8d8ff44034` (built from `7e5d623`;
the dataset was generated on the earlier bridge `66f7a061…` — same Go sources, docs-only
commits between), anchor `ce9d867f…` (matches §0).

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
| 4a | Bench-init export — `fh-mj-export-scratch-init` from `bc-big/best.pt` | §4 | not started | `big-init.pt` sha256, transfer-gate record |
| 5 | Bench 960/768 (big only, `--champion big-init.pt`) | §4 | not started | cgroup peak, tree RSS, CUDA peak, matches/s, projected wall time |
| 6 | Control lap — 200 iters, 320/256, base seed 1,400,000 | §5 | not started | `history.json`, transfer-gate record, guard verdicts |
| 7 | Control recipe gate (iter-200 delta ≥ −0.0600) | §7 | not started | `fh-mj-compare` at iter 200 |
| 8 | Big lap — 200 iters, 960/768, base seed 1,500,000 | §8 | not started | `history.json`, transfer-gate record, guard verdicts |
| 9 | Selection + confirmation (1500 × 4 seats, seed 1,720,000) | §9 | not started | primary + secondary `fh-mj-compare` |

## Screening — control arm

Window: 120 duplicate seats, `--start-seed 1710000`, against `anchor075` regenerated on the
current bridge. Delta = `fh-mj-compare mean_delta` (candidate − anchor).

| iteration | mean_delta | CI95 (clustered) | large_loss cand / anchor | telemetry healthy | notes |
|---|---|---|---|---|---|
| 25 | | | | | |
| 50 | | | | | |
| 75 | | | | | |
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

## Amendment 4 prerequisite — event-slice telemetry

Amendment 4 ratifies the parameter groups unchanged (`trunk.0.weight`, zeroed event
columns included, stays in the `bc` group at `2e-5`; `event_encoder.*` stays in `heads`
at `2e-4` through iteration 25) and forbids attributing a flat iteration-25/50 delta to
"the event head has not engaged" without telemetry. It requires, at init and after every
iteration, for **both** arms: the event-column slice's Frobenius norm, RMS and max-abs;
that slice's per-iteration Frobenius update norm; its per-element RMS ratio to the
non-event columns of `trunk.0.weight`; and the event encoder's parameter norm and
per-iteration update norm. Iteration-0 slice must be exactly zero; an exactly unchanged
slice across a completed iteration is an integrity failure and returns to consultation.
Diagnostic only — it cannot change stopping, selection, budget, or learning rates.

Implemented as `train_state.EventPathTelemetry`: `event_slice_{fro,rms,max_abs,update_fro,rms_ratio}`
and `event_encoder_{param_norm,update_fro}` in every `history.json` row, iteration-0 snapshot in
`metadata["event_path_init"]`. A frozen slice or a non-finite readout sets
`event_slice_integrity_failure` / `event_path_nonfinite` and logs a warning — it never raises,
because raising is the stopping behaviour the amendment rules out. Reading rule in runbook §7.

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
- `—` — (add next event here)

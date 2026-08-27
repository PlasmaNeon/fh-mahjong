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

**STAGE 3 (ReZero) — Amendment 3 ratified 2026-08-27: both arms rebuild their trunk from
`ReZeroResidualBlock` (`--model-trunk-rezero`); BC control and BC big are re-run under it
with BC optimization frozen; acceptance gate in runbook §3.** The plain-trunk BC control
(row 3, attempt 1) is diagnostic only and inadmissible for PPO; the plain-trunk big attempt
(row 4, attempt 1) is preserved as failure evidence in `bc-big-plain/`. Per-arm ReZero runs
write to `bc-control/` and `bc-big/` (plain control archived as `bc-control-plain/`).
Box is otherwise free (placement-reshape closed as a registered NULL;
`/root/fh-mahjong-runs/placement-reshape/` is a read-only archive). Next: BC big (§3),
export + bench (§4), control lap (§5).

Pinned for the rest of the experiment: checkout `7e5d623`, bridge
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

- `trunk.0.weight`'s zeroed event-input columns belong to the BC-loaded group
  (trained at `--lr`, e.g. 2e-5) while the event encoder trains at `--head-lr`
  (e.g. 2e-4) for iterations 1–25: the read-in weights of the event path grow
  from zero at the slow rate, not the fast one, for as long as they still live
  inside `trunk.0.weight` rather than the event encoder proper. Ratify or amend
  before interpreting the warm phase.

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
- `—` — (add next event here)

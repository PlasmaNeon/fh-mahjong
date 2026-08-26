# mortal-scale-scratch — live experiment status

**This file is the single source of truth for CURRENT mortal-scale-scratch run state.**

- **Durable protocol / rulings** → `../specs/20260825-mortal-scale-scratch-design.md` (Amendment 1, plus Amendment 2 on the BC dataset and the bench checkpoint)
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

**STAGE 2 RUNNING — BC dataset generation on the 4090 box** (pid 1404416, launched
2026-08-26 ~04:45 UTC, `fh-mj-generate-data --episodes 8000 --start-seed 1300000
--learning-seat-rule seed-mod-4`, log `/root/fh-mahjong-runs/mortal-scale-scratch/logs/gen-bc-data.log`).
CPU-only, single process. Everything after it (Gate 2a loader test, BC training, bench, laps)
is **queued behind the placement-reshape Stage-1 lap** that owns the GPU and the frozen
`/root/fh-mahjong` checkout (session `placement-reshape-bc`; ~2 days incl. screens + confirmation).
Standing conditions agreed with that session: no GPU work, no bridge rebuilds, no writes to
`/root/fh-mahjong` (repo or `build/`), keep > 100 GB free.

## Stage checklist

| # | Stage | Runbook | State | Evidence |
|---|---|---|---|---|
| 1 | Bridge build + `uv sync` + digests | §1 | done (see event log) | bridge sha256 `66f7a061f6314715d4c0cb2524861161f97f8ebe1aa8609f730ac274adf76cd9` (the box's pinned binary, shared with placement-reshape; NOT rebuilt); anchor sha256 `ce9d867f…` ✓; checkout `9098aed` |
| 2 | BC dataset — 8,000 matches, seeds 1,300,000–1,307,999, `--learning-seat-rule seed-mod-4` | §2 | RUNNING (pid 1404416) | dataset manifest digest, transition count, `per_seat_transitions` |
| 2a | A2 dataset gate — calculated resident ≤ 30.00 GiB, loader-only cgroup peak ≤ 32.00 GiB | §2 | not started | rows × 7,018 B, `memory.peak`, shard bytes, `free -g` |
| 3 | BC control (96×4, k=1) | §3 | not started | `best_epoch`, val CE, top-1 (zeroed events) overall + per seat, `best.pt` sha256 |
| 4 | BC big (192×24, k=1) | §3 | not started | `best_epoch`, val CE, top-1 (zeroed events) overall + per seat, `best.pt` sha256 |
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
- `—` — (add next event here)

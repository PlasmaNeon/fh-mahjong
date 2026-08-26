# mortal-scale-scratch — live experiment status

**This file is the single source of truth for CURRENT mortal-scale-scratch run state.**

- **Durable protocol / rulings** → `../specs/20260825-mortal-scale-scratch-design.md` (Amendment 1)
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

**NOT LAUNCHED — awaiting BC data generation.**

Code for both stages is on `experiment/mortal-scale-scratch` (PR #223) and Amendment 1 is
ratified. Nothing has been generated, trained, benched, or evaluated on the box.

## Stage checklist

| # | Stage | Runbook | State | Evidence |
|---|---|---|---|---|
| 1 | Bridge build + `uv sync` + digests | §1 | not started | bridge sha256, anchor sha256, git commit |
| 2 | BC dataset — 10,000 matches, seeds 1,300,000–1,309,999 | §2 | not started | dataset manifest digest, transition count |
| 2a | Loader-feasibility gate (resident bytes vs 52 GiB cap) | §2 | not started | computed GiB, `free -g` |
| 3 | BC control (96×4, k=1) | §3 | not started | `best_epoch`, val CE, top-1 (zeroed events), `best.pt` sha256 |
| 4 | BC big (192×24, k=1) | §3 | not started | `best_epoch`, val CE, top-1 (zeroed events), `best.pt` sha256 |
| 5 | Bench 960/768 (big only) | §4 | not started | cgroup peak, tree RSS, CUDA peak, matches/s, projected wall time |
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

## Event log

Append only. `UTC timestamp — session-name — what happened.`

- `2026-08-25` — mortal-scale-scratch — runbook, status file and follow-up flag docs written; nothing launched.
- `—` — (add next event here)

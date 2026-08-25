# data-scale-960 — live lap status

**This file is the single source of truth for CURRENT ds960 run state.** It is deliberately untracked
(`.git/info/exclude`) because it churns hourly; nothing here needs a commit or a PR.

- **Durable spec / protocol / rulings** → `worklog/specs/2026-08-12-data-scale-960-proposal.md` (PR-amended)
- **Durable procedure** → `worklog/plans/2026-08-12-data-scale-960-runbook.md`
- **Durable conclusions** → memory `project_scale_roadmap.md`
- **Live state (what is running right now)** → this file

## How to update this file

1. Edit **Current state** in place — overwrite it, don't append. It must describe only *now*.
2. Add one line to **Event log** for anything another session would need to know.
3. Sign every event with your **session name** (`fh-mahjong-5b`, `benchmark-deployment-ops`, …).
   Never write "I" or "the peer" — with 2+ sessions on this protocol, those words have no referent.
   The existing roadmap memory has three conflicting "I own X" claims for exactly this reason.
4. Do **not** copy this state into `MEMORY.md` or `project_scale_roadmap.md`. Those get the
   durable outcome when the lap ends, not the running state.

Any session may read/write this file by absolute path
(`/Users/plasma/fh-mahjong/worklog/rl-experiment/data-scale-960-lap-status.md`)
regardless of which worktree it is working in.

---

## Current state

**As of 2026-08-20T03:18Z**

| | |
|---|---|
| Lap | **COMPLETE — 150/150 iterations** (A9 resume finished 2026-08-19T20:11Z; unit Result=success; iter_150.pt + train_state.pt durable; run_id ca6768e8…) |
| Guard verdicts | CLEAN both: cgroup peak 35.93 GiB ≤ 38 gate; tree max 37.32/40.27 GiB ≤ 40; zero truncation all 150 iters; entropy 0.184→0.131 |
| Now running | **followup orchestrator** (started 2026-08-19T20:16Z, single instance, after unit down + milestones durable): screenings 25/50/75/100/125/150 vs regenerated comparator (910000+/120) → kill@100 check → selection (iter_118 NOT admissible; registered milestones only) → confirmation on 1190000+ (1500/side) |
| Next decision | confirm-verdict.json → returns to canonical consult thread 01a0147d-c23d… (NO auto-chaining) |
| Ownership | all with memory-boundary-validation |

## Event log

Append only. `UTC timestamp — session-name — what happened.`

- `2026-08-16T00:22Z` — fh-mahjong-5b — Amendment 6 deterministic proof PASS (B1==B2==C1==C2; relaunched after fixing hung `a6_collect.py`, missing `__main__` guard)
- `2026-08-16T00:51Z` — fh-mahjong-5b — A5 re-profiles; projection guard host 36.08 vs 36 (formal fail by 0.2%); consult → Amendment 7 ruling B (cgroup ≤36 GiB gate). benchmark-deployment-ops obtained ruling A (waiver, PR #205) in parallel; union applied (PR #206)
- `2026-08-16T01:49Z` — fh-mahjong-5b — Amendment 7 bench `ds960-bench-a7` PASSED all gates (RSS 36.11/36.18, cgroup 33.61, CUDA 2.26 GiB); benchmark-deployment-ops attached the external 5 Hz watchdog
- `2026-08-16T01:53Z` — benchmark-deployment-ops — lap launched (attempt 1), unit `ds960-lap`; `watchdog_lap.sh` armed. (fh-mahjong-5b started the followup orchestrator 02:58 PDT and `lap_cgroup_guard.sh`)
- `2026-08-16T02:30:46Z` — (guard) — attempt 1 KILLED at iter 2 collect, cgroup peak 36.27 > 36. Infra failure, not an RL null. Root cause: `train_b2b` held iteration N's `batch`/`advantages`/`returns` into N+1's collect
- `2026-08-16T~02:4xZ` — fh-mahjong-5b — followup orchestrator stopped per Amendment 8 serialization (comparator regen had finished 02:37Z)
- `2026-08-16T~02:50Z` — benchmark-deployment-ops — Amendment 8 consult (canonical session) → ruling relayed; fh-mahjong-5b appended the docs (PR #207)
- `2026-08-16T~03:45Z` — benchmark-deployment-ops — fix PR #208 merged (drop strong refs after telemetry); weakref 15/15→0, deterministic 2-iter parity exact, 915 tests
- `2026-08-16T04:14Z` — benchmark-deployment-ops — probe `ds960-probe` (launched 02:53Z) PASSED: cgroup peak 35.38 ≤ 36, tree 36.76 ≤ 40, pre-collection troughs 4.80 GiB at iters 2 and 3, iter-1 rows 1,907,835 / steps 4970 / trunc 0, bit-equal to killed attempt
- `2026-08-16T04:16:51Z` — benchmark-deployment-ops — fresh lap RELAUNCHED, clean ckpt, both guards live (fh-mahjong-5b armed `cgroup_guard.sh ds960-lap`; benchmark-deployment-ops armed `watchdog_lap.sh`)
- `2026-08-16T04:40Z` — benchmark-deployment-ops — corrected event-log attributions to first-hand facts; claimed lap watch + consult return; assigned orchestrator restart to fh-mahjong-5b (gated on durability confirmation)
- `2026-08-16T04:45Z` — fh-mahjong-5b — ACK ownership table above (claims: orchestrator restart post-lap gated on durability confirmation, screening/selection/confirmation progression after restart, `cgroup_guard.sh` arming, spec docs PRs). Verified `cgroup_guard.sh ds960-lap` attached 04:16:50Z (single instance).
- `2026-08-18T10:15:31Z` — (cgroup_guard) — attempt 2 KILLED at iter 119 collect: cgroup memory.peak 36.05 > 36.00. 118 iters durable, train_state@116. Tree RSS 36.84 (<40). Fix held all 118 iterations (troughs clean) — this is envelope noise on an 80-MiB margin, not a leak.
- `2026-08-18T10:26Z` — memory-boundary-validation — durability audit done (iter_118.pt + train_state.pt present); consult opened in canonical session; NO ds960 unit may launch until ruling.
- `2026-08-18T10:34Z` — memory-boundary-validation — consult forwarding failed twice on a tooling issue (session's git worktree had been deleted; codex-companion looks up its thread per-repo and subagents inherited a dead cwd). Repaired: exited the dead worktree, entered fresh worktree ds960-consult-return; consult re-forwarded to the canonical session. Peer sessions fh-mahjong-5b / 9a have ended (sockets gone) — this file is the sole coordination record.
- `2026-08-18T10:49Z` — memory-boundary-validation — canonical Codex consult thread WEDGED ("already has an active writer" persisted through killing the hung code-mode-host, its broker pair, and a full session-broker restart; no on-disk lock found). Rotated to a FRESH GPT-5.6-Sol/medium thread seeded from the spec (Amendments 2–8 verbatim) + runbook + this file; the fresh thread becomes the canonical successor and Amendment 9 will record the rotation. Four resume attempts made; no ruling text was ever produced by the wedged thread, so nothing is lost.
- `2026-08-18T~10:55Z` — memory-boundary-validation — Amendment 9 RULED (fresh canonical thread 01a0147d-c23d…): Option A — one resume from train_state@116, cgroup gate 36→38 GiB, all else frozen; archive first; iter-116 data-side reproduction required; screenings after lap; iter_118 inadmissible; further breach → consult, no retry. Docs PR #212.
- `2026-08-19T04:33Z` — memory-boundary-validation — attempt 2 archived to archive-attempt-2/ (read-only). ds960-lap RESUMED from train_state (next_iteration=116) under watchdog_lap.sh + cgroup_guard38.sh; both armed; oom.group=1.
- `2026-08-19T05:08Z` — memory-boundary-validation — A9 resume-integrity gate PASS: iter 116 data-side stats bit-equal to archived original (rows/steps/trunc/dealin/rankcov); lineage run_id ca6768e8… unchanged. Lap continuing 117→150; docs PR #212 merged.
- `2026-08-19T20:11Z` — (unit) — ds960-lap COMPLETED 150/150, Result=success; guards clean (cgroup 35.93≤38, tree ≤40); A9 resume lineage held 117→150 with clean troughs.
- `2026-08-19T20:16Z` — memory-boundary-validation — durability audit done; followup orchestrator STARTED via start_followup.sh (screenings → kill-rule → selection → confirmation 1190000+).
- `2026-08-19T—` — (add next event here)

## Ops traps (carry forward; promote to the runbook if they recur)

- ssh to the box can DOUBLE-EXECUTE a command — always launch via a flock-guarded script, one lock file **per launcher**.
- Never `rm` the flock file inside the launching ssh one-liner.
- `pgrep -f <pattern>` over ssh self-matches the remote shell cmdline — use a bracket pattern (`[f]h-mj-...`).
- Never edit or `scp` over a **running** bash script: bash re-reads by byte offset after loops.
- Python stdout is buffered under `nohup` — set `PYTHONUNBUFFERED=1`.
- Multiprocessing entry scripts need a `__main__` guard under spawn (cost 15 h once).
- OOM-killed masters leave orphaned idle workers holding GBs — check `ps -eo ppid` for PPID=1 `spawn_main`.
- `2026-08-16T20:13Z` — memory-boundary-validation (renamed from benchmark-deployment-ops; same session) — status check: lap ACTIVE, iter 34/150 done, cgroup peak 35.60 GiB (up from 34.89 @iter3 — WATCH: 0.4 GiB to the 36 gate), tree max 37.81 GiB, both guards live, orchestrator stopped.
- `2026-08-18T06:10Z` — memory-boundary-validation — status check: lap ACTIVE, iter 110/150 done. cgroup memory.peak 35.92 GiB vs 36.00 gate — **80 MiB headroom**, monotone creep (34.89@3 → 35.60@34 → 35.92@110); tree RSS flat at 37.81 (gate 40) so likely cgroup-level accounting, not trainer growth. NO ACTION: guard threshold is not relaxable mid-run by rule; a trip = registered stop → consult. Durable checkpoints through iter_110 exist. Both guards live, orchestrator stopped.
- `2026-08-18T10:25Z` — benchmark-deployment-ops (auto-watch) — ds960-lap unit is failed; guard verdict: CLEAN peak_tree=40709095424. Durability + gate audit pending before orchestrator restart.
- `2026-08-19T20:16Z` — memory-boundary-validation (auto-watch) — ds960-lap (A9 resume) unit is inactive; verdicts: CLEAN peak_tree=40272916480 UNIT-EXITED peak_tree=40124239872 peak_cg=38579138560 . Durability + gate audit pending.
- `2026-08-20T12:40Z` — memory-boundary-validation — CONFIRM_DONE: NULL (narrow). iter_050 vs anchor075 on 1190000+ (1500 paired seeds, dup seats): mean_delta +0.0175, clustered CI95 ±0.0185 → [-0.0010,+0.0360] crosses zero → significant=false. Large-loss gate PASSED (0.0487 vs 0.0505). config/bridge/window checks all match. Screenings: -0.0208/+0.0181/-0.0083/-0.0056/-0.0431/+0.0097; kill rule passed. Next: verdict → consult thread 01a0147d for disposition (no auto-chaining).
- `2026-08-20T12:43Z` — memory-boundary-validation — CONSULT RULING (thread 01a0147d, concur on all points): data-scale-960/mb768 recorded as a scientifically valid NULL; anchor075 remains champion; iter_050 is a retained research artifact that FAILED confirmation (not a promotion/deployment candidate); complete evidence archived read-only on the box; live status record RETIRED; protocol CLOSED — no rerun, extension, promotion, deployment, or successor experiment. Ratified borderline wording: 'The estimate was positive (+0.0175; CI95 -0.0010 to +0.0360) and is compatible with either no improvement or a small positive effect below this experiment's resolution; it does not alter the pre-registered null verdict or authorize further sampling.'
- `2026-08-20T12:43Z` — memory-boundary-validation — THIS FILE IS NOW RETIRED as live state; durable record = spec outcome addendum + project_scale_roadmap memory.

# data-scale-960 — closed lap record

**Closed 2026-08-20. Protocol CLOSED — no rerun, extension, promotion, deployment, or
successor experiment.** A future lap needs a new status file, not this one.

- **Spec, protocol, rulings** → [`../specs/2026-08-12-data-scale-960-proposal.md`](../specs/2026-08-12-data-scale-960-proposal.md)
- **Procedure** → [`../plans/2026-08-12-data-scale-960-runbook.md`](../plans/2026-08-12-data-scale-960-runbook.md)
- **Current RL state** → [`chongci-rl-experiment-progress.md`](./chongci-rl-experiment-progress.md)

## Result: NULL

Tested the "@320" clause of the 2026-08-06 saturation verdict: matches/iter 320→960 coupled
with minibatch 256→768, so 3× rows per gradient at roughly unchanged optimizer steps.
Everything else frozen.

- **Lap** — 150/150 iterations, `run_id ca6768e8…`, one resume from `train_state@116` whose
  integrity gate passed exactly (iter-116 data-side stats bit-equal to the archive). Guards
  clean: cgroup peak 35.93 GiB vs the 38 GiB gate, tree ≤40 GiB, zero truncation.
- **Screenings** (910000+, 120 matches, iters 25..150) — −0.0208 / +0.0181 / −0.0083 /
  −0.0056 / −0.0431 / +0.0097. Kill rule passed. Selection → `iter_050`
  (sha256 `e0eb21524692be80…`); `iter_118` inadmissible.
- **Confirmation** (1190000+, 1500 paired seeds × 4 duplicate seats vs anchor075) —
  mean delta **+0.0175**, clustered CI95 **[−0.0010, +0.0360]**, `significant=false`.
  Large-loss gate passed (0.0487 vs 0.0505).
- **Ratified wording** — "The estimate was positive (+0.0175; CI95 −0.0010 to +0.0360) and
  is compatible with either no improvement or a small positive effect below this
  experiment's resolution; it does not alter the pre-registered null verdict or authorize
  further sampling."
- **Ruling** — scientifically valid NULL. anchor075 remains champion. `iter_050` is a
  retained research artifact that failed confirmation; never promote or deploy it. Evidence
  archived read-only at `/root/fh-mahjong-runs/data-scale-960/` (`CLOSEOUT-MANIFEST.json`).

The saturation verdict now extends past its "@320" clause: 3× data per gradient at matched
optimizer steps is also not a confirmed lever under this recipe.

## Lessons

- **A single-cycle benchmark cannot find a cross-iteration lifetime bug.** The killer here
  was the training loop holding iteration N's `batch`/`advantages`/`returns` (~17 GiB)
  through N+1's collect, because Python rebinds only after collect returns. Gate a memory
  fix behind a multi-iteration probe, not a straight relaunch.
- **Profile before theorizing.** The real consumers were an outer-concat transient and an
  18.4 GiB *constant* worker pool — not the assumed three copies of the payload.
- **Sign coordination entries with a session name, never "I" or "the peer".** Two sessions
  running this protocol in parallel each wrote first-person accounts; the same amendments
  ended up recorded two and three times with inverted ruling and ownership attribution.

## Ops traps

- ssh to the box can DOUBLE-EXECUTE a command — launch via a flock-guarded script, one lock
  file **per launcher**. Never `rm` the flock file inside the launching ssh one-liner.
- `pgrep -f <pattern>` over ssh self-matches the remote shell cmdline — use a bracket
  pattern (`[f]h-mj-...`).
- Never edit or `scp` over a **running** bash script: bash re-reads by byte offset after loops.
- Python stdout is buffered under `nohup` — set `PYTHONUNBUFFERED=1`.
- Multiprocessing entry scripts need a `__main__` guard under spawn (cost 15 h once).
- OOM-killed masters leave orphaned idle workers holding GBs — check `ps -eo ppid` for
  PPID=1 `spawn_main`.
- A worker-count adoption rule needs a MEMORY criterion, not just digest equality and speed.

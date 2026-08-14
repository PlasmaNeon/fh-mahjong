# data-scale-960/mb768 Run Protocol (post-merge, RTX 4090 box)

Spec: `docs/superpowers/specs/2026-08-12-data-scale-960-proposal.md`
(RATIFIED 2026-08-12). This runbook transcribes the pre-registered protocol
into exact commands. ONE coupled intervention: `matches_per_iter 320 → 960`
AND `minibatch_size 256 → 768` (~equal optimizer steps and policy refreshes
per iteration, 3× rows per gradient). Everything else is frozen at the
champion recipe. No optional stopping, no auto-chaining — the result returns
to consultation.

Prereqs: merged main (PPO all-minibatch telemetry + `fh-mj-collect-bench
--full-cycle`) pulled on the box (`ssh wsl`, `/root/fh-mahjong`); bridge
rebuilt (`go build -buildmode=c-shared -o build/libfh_mahjong_bridge.so
./cmd/rlbridge`).

## 0. Anchor (frozen path + sha)

Unchanged from the gru-width / deep4+12-rezero laps — restart-iter075:

```
/root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt
sha256: ce9d867f803bb41acad30f1f4c137e82d7946ed2c4db769e265d0c9cd08f75d4
```

Confirm before spending any compute:

```
sha256sum /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt
```

## 1. Stage 0 preflight: full collect + PPO update cycle at 960/mb768

The 448-match run was the largest memory-proven collection; 960 is 2.1×
that, and `ppo_update` puts the ENTIRE rollout on the update device — so the
preflight must measure a complete collect + update cycle, not collection
alone. `--full-cycle` does exactly that: per worker count it collects 960
matches through the real post-PR-#146 spawn-context `ParallelB2bCollector`,
then runs GAE + one real `ppo_update` at the frozen recipe hyperparameters
on a fresh copy of the warm-started anchor, reporting host peak RSS (whole
phase, process tree), CUDA peak allocated/reserved, transition rows,
optimizer steps, matches/s, label coverage, truncation, and the (now
all-minibatch-aggregated) KL / clip fraction.

Bench seeds: `--base-seed 700000` (700000–700959). Deliberately outside
every burned or reserved window — prior training ranges (100k–148k,
200k–248k, 400k–453k, 4M, 8M), this lap's training range (500000–644000,
from base seed 500000 × 150 iters × 960), screening (910000+), and the
confirmation window (1190000+).

**Amendment 2 (2026-08-12):** the first bench run OOM'd the box at
workers=10 — single-task dispatch made every worker hold its whole 96-match
block (dmesg: workers at 5.1–6.7GB anon-rss, master 8.4GB, kernel kills).
The consult approved bounded sequential dispatch (`--dispatch-chunk`,
`PPOConfig.collect_dispatch_chunk`), digest-proven chunk-invariant; the cap
is FROZEN at **320** for this lap and must appear in both this bench command
and the launch command. See the spec's Amendment 2 for the full conditions.

```
PYTHONUNBUFFERED=1 uv run --project ai fh-mj-collect-bench \
  --champion /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt \
  --workers 10,16,20 \
  --matches 960 --base-seed 700000 \
  --dispatch-chunk 320 \
  --match-mode chongci --max-steps-per-episode 4000 \
  --event-window 128 \
  --model-residual-blocks 4 --model-privileged-critic --model-aux-heads \
  --full-cycle --minibatch-size 768 --ppo-epochs 2 \
  --gamma 0.99 --gae-lambda 0.95 --lr 2e-5 --entropy-coef 0 \
  --ppo-device cuda \
  --json /root/fh-mahjong-runs/data-scale-960/preflight-960-mb768.json
```

Warm-start note: `--champion` here is the complete post-B2b anchor going
through the default (growth-0) `build_b2b_model` path. For a
same-architecture B2b checkpoint that path is an identity load — every
tensor loads same-shape and the two "surgery" copies are full-width — so the
bench collects with exactly the anchor's weights. §2's parity check proves
this on the box before the lap launches.

Run the counts ONE AT A TIME if memory is tight (`--workers 20` alone
re-checks just the risky count; digests are comparable across invocations
because seeds and weights are fixed — but a single 10,16,20 invocation is
the canonical form, since it also compares digests in-process).

Go / no-go (ALL must hold; spec Stage 0 items 1–2):

1. The 960-match collection AND the mb768 update complete at every worker
   count — no OOM kill, no CUDA OOM.
2. `all_digests_equal: True` and `rows_and_labels_equal: True` — worker
   count must not alter collected rows or labels.
3. Host peak RSS gate — RESTATED by Amendment 3 (the original "≤ ~26 GB on
   the 31 GB box" gate is superseded): the box's WSL2 cap is raised to
   `memory=52GB` (Windows host has 64 GB; record the effective limit via
   `free -g` after `wsl --shutdown` + restart before the run counts), and
   the gate is **peak AGGREGATE process-tree RSS ≤ 40 GiB** with ≥ 12 GiB
   nominal headroom. Log master RSS and summed child RSS separately for
   diagnosis; the hard go/no-go is the aggregate figure. Recommended
   containment (not a substitute for the gate): cgroup-v2
   `memory.high=44GiB`, `memory.max=48GiB`, `memory.swap.max=0`,
   `memory.oom.group=1` around the bench/lap process tree. Still prefer
   the SMALLEST worker count whose throughput is acceptable — speed alone
   never justifies a count; memory failures killed a prior lap twice and
   this preflight twice.
4. CUDA peak allocated fits the 4090's 24 GB with headroom for the training
   loop's own model/optimizer copies (bench measures model + full rollout +
   update transients; keep peak ≤ ~20 GB).
5. Truncation ≈ 0 (the champion recipe's expectation at step cap 4000) and
   label coverage in the normal band (`dealin_positive_rate` > 0,
   `rank_label_coverage` ≈ 1 up to truncation).

**If 960 cannot complete under the existing path (memory or otherwise):
STOP. Return to consultation.** The GoEnvPool port is NOT auto-authorized —
it needs its own gauntlet (mind the `round_outcome` drop and the missing
B2b hindsight-label assembly: single-env-vs-pool parity would be required).

Wall-clock estimate (spec Stage 0 item 4): from the bench's steady
`matches/s` at the chosen worker count, `960 / (matches/s) + update_s` per
iteration; ballpark from old profiles (0.6–0.9 matches/s) is ~25–35
min/iter → 150 iters ≈ 2.5–3.5 days. Record the measured estimate in the
run log before launch.

## 2. Step-zero identity check (cheap, before launch)

Prove the growth-0 warm start from the post-B2b anchor is an exact identity
(same spirit as the gru-width parity gate):

```
uv run --project ai python - <<'EOF'
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.oracle import _b2b_model_env_config, build_b2b_model
from fh_mahjong_ai.storage import load_checkpoint

ANCHOR = "/root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt"

payload = torch.load(ANCHOR, map_location="cpu")
anchor_config = ModelConfig(**payload["metadata"]["model_config"])
live_env = EnvConfig(bridge_kind="go", match_mode="chongci",
                     max_steps_per_episode=4000, oracle_observation=True,
                     event_history_window=anchor_config.event_window)

anchor = PolicyValueNet(_b2b_model_env_config(live_env), anchor_config)
load_checkpoint(ANCHOR, anchor)

warm = build_b2b_model(_b2b_model_env_config(live_env), anchor_config, ANCHOR)

a_state, w_state = anchor.state_dict(), warm.state_dict()
assert a_state.keys() == w_state.keys()
for key in a_state:
    assert torch.equal(a_state[key], w_state[key]), f"tensor mismatch: {key}"
print("IDENTITY WARM START OK")
EOF
```

Do not launch unless it prints `IDENTITY WARM START OK`.

## 3. Launch

Amendment 3: the lap runs under the same verified 52 GiB WSL cap and the
same ≤ 40 GiB aggregate process-tree RSS gate as the preflight, monitored
continuously — crossing 40 GiB is a hard stop back to consultation. Use
the same cgroup-v2 containment (`memory.high=44GiB`, `memory.max=48GiB`,
`memory.swap.max=0`, `memory.oom.group=1`) when available.

```
PYTHONUNBUFFERED=1 uv run --project ai fh-mj-train-b2b \
  --champion /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt \
  --model-residual-blocks 4 \
  --checkpoint-dir /root/fh-mahjong-runs/data-scale-960/ckpt \
  --base-seed 500000 --iterations 150 \
  --matches-per-iter 960 --minibatch-size 768 \
  --collect-dispatch-chunk 320 \
  --num-workers <from §1 — smallest acceptable count with memory headroom> \
  --lr 2e-5 --entropy-coef 0 --ppo-epochs 2 --gamma 0.99 \
  --match-mode chongci --max-steps-per-episode 4000 --device cuda \
  --train-state-every 5
```

The ONLY deltas from the gru-width/champion launch are
`--matches-per-iter 960 --minibatch-size 768` (the coupled intervention),
`--collect-dispatch-chunk 320` (Amendment 2 collection transport —
digest-proven semantics-neutral, frozen for this lap),
`--base-seed 500000` (fresh range, verified non-overlapping), the run dir,
and no architecture surgery flag (unchanged net). lr is FROZEN at 2e-5 per
the ratification — a null is terminal for this protocol; there is no
post-null lr arm.

Seeds burned by training: 500000 + iter×960 for iter 1..150 →
500960..644960 + rows within each block; the reserved training range
500000–644000 (spec amendment 5) covers it; nothing overlaps screening
(910000+) or confirmation (1190000+).

History telemetry to watch (`history.json`): `approx_kl`/`clip_fraction`
are now aggregated over ALL minibatches (this lap is the first consumer —
do NOT compare raw values against pre-aggregation laps' history files,
where they were final-minibatch-only samples); `optimizer_steps` should sit
at `2 × ceil(rows/768)` ≈ the 320/mb256 laps' step count (that equality is
the point of the coupling); `dealin_positive_rate` > 0,
`rank_label_coverage` ≈ 1, `truncation_rate` 0 (the trainer halts > 2%).

## 4. Resume after a crash / box restart

```
PYTHONUNBUFFERED=1 uv run --project ai fh-mj-train-b2b \
  --model-residual-blocks 4 \
  --checkpoint-dir /root/fh-mahjong-runs/data-scale-960/ckpt \
  --base-seed 500000 --iterations 150 \
  --matches-per-iter 960 --minibatch-size 768 \
  --collect-dispatch-chunk 320 \
  --num-workers <same or adjusted — semantics-neutral, like the chunk cap> \
  --lr 2e-5 --entropy-coef 0 --ppo-epochs 2 --gamma 0.99 \
  --match-mode chongci --max-steps-per-episode 4000 --device cuda \
  --train-state-every 5 \
  --resume-from-state /root/fh-mahjong-runs/data-scale-960/ckpt/train_state.pt
```

Every flag except `--num-workers` and `--collect-dispatch-chunk` (both
semantics-neutral collection sharding, logged rather than rejected) must
match the launch exactly (the resume validates against the saved
`config_echo` and raises on drift, naming both values). The bridge .so is content-pinned across resumes; do not rebuild it
mid-lap.

## 5. Screening

At iterations 25/50/75/100/125/150, evaluate vs a comparator anchor
REGENERATED on the identical current bridge, `910000+` window, 120 seeds,
compared with `fh-mj-compare` (mandatory for any delta claim):

```
fh-mj-evaluate --checkpoint /root/fh-mahjong-runs/data-scale-960/ckpt/iter_XXX.pt \
  --model-residual-blocks 4 \
  --model-event-window 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 120 \
  --start-seed 910000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/data-scale-960/screen-XXX.json
```

Comparator, ONCE, before the first screening (the bridge has moved since
the gru-width comparator — do not reuse any prior lap's comparator JSON):

```
fh-mj-evaluate --checkpoint /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt \
  --model-residual-blocks 4 \
  --model-event-window 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 120 \
  --start-seed 910000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/data-scale-960/anchor-screen-current-bridge.json
```

```
fh-mj-compare /root/fh-mahjong-runs/data-scale-960/screen-XXX.json \
  /root/fh-mahjong-runs/data-scale-960/anchor-screen-current-bridge.json
```

## 6. Kill rule (ONLY at iter 100)

Stop the lap ONLY if BOTH the iter-75 AND iter-100 champion-relative
screening deltas are `< -0.06`. No other iteration triggers a kill.

## 7. Confirmation

Best pre-registered screening checkpoint (healthy telemetry, exact ties to
the later checkpoint — no substitution after seeing later results). Fresh
`1190000+` window (≤1150000 is all burned), 1500 seeds/side, back-to-back,
same bridge:

```
fh-mj-evaluate --checkpoint <selected>.pt \
  --model-residual-blocks 4 \
  --model-event-window 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 1500 \
  --start-seed 1190000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/data-scale-960/confirm-candidate.json

fh-mj-evaluate --checkpoint /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt \
  --model-residual-blocks 4 \
  --model-event-window 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 1500 \
  --start-seed 1190000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/data-scale-960/confirm-anchor.json

fh-mj-compare /root/fh-mahjong-runs/data-scale-960/confirm-candidate.json \
  /root/fh-mahjong-runs/data-scale-960/confirm-anchor.json
```

Gate (both required): paired placement clustered 95% CI lower bound > 0,
AND `large_loss_rate(candidate) <= large_loss_rate(anchor) + 0.015`.
Confirmation runs REGARDLESS of screening shape (no optional stopping).

## 8. After the result — back to consult, no auto-chaining

- **Confirm** *supports but does not prove* "gradient noise was binding"
  (no concurrent randomized 320 control). Next consult decision: rerun a
  capacity lap (GRU-width or deep16-ReZero) AT 960, budget scaled by
  measured param ratio. Not automatic.
- **Null** closes 960/768 under this recipe and removes the evidentiary
  basis for another capacity lap now. No lr arm. Ratified priorities
  (promotion, provenance, human corpus) continue unchanged.

## 9. Checkpoint retention

Keep the pre-registered screening checkpoints (25/50/75/100/125/150) plus
the selected checkpoint; prune the rest after the lap. `train_state.pt`
can be deleted once the lap is confirmed or nulled.

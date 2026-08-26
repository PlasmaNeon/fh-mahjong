# mortal-scale-scratch Run Protocol (RTX 4090 box)

**Spec:** `../specs/20260825-mortal-scale-scratch-design.md`. **Amendment 1**
(ratified 2026-08-25, Codex thread `01a0147d`) is the contract, and **Amendment 2**
(same thread, same day) supersedes it on the BC dataset (§2 here) and the big-arm
bench checkpoint (§4 here); every number in this runbook is transcribed from those
two and none of them may be tuned mid-experiment.

**Live state:** `../rl-experiment/20260825-mortal-scale-scratch-status.md` — that
file, not this one, records what has actually run.

Two arms, sequential on one GPU: **control** (96 ch × 4 blocks, `kernel_width=1`,
2.28 M params) and then, only if the control passes its recipe gate, **big**
(192 ch × 24 blocks, `kernel_width=1`, 8.42 M params). Both are BC → PPO from
random init on one shared BC dataset. `anchor075` is the external comparator.
Neither arm may be promoted or deployed; every terminal result — pass, null, or
infrastructure failure — returns to thread `01a0147d` with checkpoints,
histories, dataset and bridge hashes, initialization provenance, guard
telemetry, screening reports, and confirmation comparisons preserved.

## 0. Box, paths, frozen recipe

| | |
|---|---|
| Box | `ssh wsl` (WSL2 on the RTX 4090 host; `memory=52GB` cap, verify with `free -g` after a `wsl --shutdown` + restart) |
| Repo | `/root/fh-mahjong` |
| uv | `/root/.local/bin/uv` — every Python command is `uv run --project ai …` from `/root/fh-mahjong` |
| Bridge | `/root/fh-mahjong/build/libfh_mahjong_bridge.so` |
| Run root | `/root/fh-mahjong-runs/mortal-scale-scratch/` |
| Comparator | `/root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt`, sha256 `ce9d867f803bb41acad30f1f4c137e82d7946ed2c4db769e265d0c9cd08f75d4` |

Run-root layout: `bc-data/`, `bc-control/`, `bc-big/`, `bench/`, `control/ckpt`,
`big/ckpt`, `screen/`, `confirm/`. Run-root layout also holds `bench/big-init.pt`,
the digest-pinned bench checkpoint §4 exports before the big arm's bench.

Frozen for both arms (Amendment 1 §5) — collection and update recipe, observation
and action contracts, reward and auxiliary recipe, and the bridge bytes:

| | |
|---|---|
| `--ppo-epochs` | 2 |
| `--gamma` | 0.99 |
| `--entropy-coef` | 0 |
| `--match-mode` | chongci |
| `--max-steps-per-episode` | 4000 |
| `--collect-dispatch-chunk` | 320 |
| `--num-workers` | 10 |
| `--lr` (BC-loaded parameters) | 2e-5 for all 200 iterations |
| `--head-lr` / `--head-lr-iters` | 2e-4 for iterations 1–25, then 2e-5 |
| `--train-state-every` | 5 |
| iterations | 200 per arm, fixed before launch |

Per-arm:

| | control | big |
|---|---|---|
| `--model-channels` | 96 | 192 |
| `--model-residual-blocks` | 4 | 24 |
| `--model-kernel-width` | 1 | 1 |
| params | 2.28 M (0.83× champion) | 8.42 M (3.07× champion) |
| `--matches-per-iter` | 320 | 960 |
| `--minibatch-size` | 256 | 768 |
| `--base-seed` | 1400000 | 1500000 |

The control's 320/256 is a floor, not a scaled figure: dropping it to 266 to match
the parameter ratio would weaken the recipe control merely because its 1-D kernel
has fewer parameters. Both arms therefore execute approximately equal optimizer
steps per iteration while the big arm receives the pre-registered proportional-data
treatment.

Seed reservations (Amendment 1 §8, dataset range narrowed by Amendment 2 §1) —
no reuse, no overlap:

| range | use |
|---|---|
| 1,300,000–1,307,999 | BC dataset (8,000 matches, one learning seat each) |
| 1,308,000–1,309,999 | unused — released by Amendment 2 §1, not reallocated |
| 1,400,000–1,463,999 | control training (200 × 320) |
| 1,500,000–1,691,999 | big training (200 × 960) |
| 1,700,000–1,700,959 | bench (960) |
| 1,710,000+ | screening window (120 duplicate-seat seeds) |
| 1,720,000+ | confirmation window (1500 paired seeds) |

## 1. Prerequisites and digests

**Before anything else — the box is shared and the lane is GPU-serial.** Run
`pgrep -af "fh-mj|fh_mahjong_ai"` and read every `worklog/rl-experiment/*status*.md`. If any
lap, bench, or evaluation is running: do not `git pull`/`checkout`, do not rebuild the bridge,
and do not start GPU work; a running lap pins the bridge digest and (for its evaluations) the
checkout, and its drift check hashes its own snapshot, but a resume re-hashes the source path.
CPU-only dataset generation may run alongside with that lap's owner's agreement, against the
bridge already on disk — record that digest as this experiment's pin. Coordinate with the
owning session before touching `/root/fh-mahjong` at all.

```
ssh wsl
cd /root/fh-mahjong
git pull                     # only on an idle box (see above)
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.so ./cmd/rlbridge   # only on an idle box
uv sync --project ai --extra dev
sha256sum build/libfh_mahjong_bridge.so
sha256sum /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt
git rev-parse HEAD
```

Record the bridge sha256, the anchor sha256 (must equal the value in §0), and the
commit in the status file. The bridge is content-pinned for the whole experiment:
do not rebuild it between the dataset, the two laps, and the evaluations. Every
comparison in §7–§8 is made on this one binary.

## 2. Stage 1a — BC dataset (shared by both arms)

Exactly 8,000 heuristic matches, seeds 1,300,000–1,307,999, keeping exactly one
learning seat per match (Amendment 2 §1–§2):

```
PYTHONUNBUFFERED=1 uv run --project ai fh-mj-generate-data \
  --episodes 8000 --start-seed 1300000 \
  --learning-seat-rule seed-mod-4 \
  --output /root/fh-mahjong-runs/mortal-scale-scratch/bc-data \
  --manifest-output /root/fh-mahjong-runs/mortal-scale-scratch/bc-data/dataset-manifest.json \
  --format npz-shards --compressed-shards \
  --match-mode chongci --max-steps-per-episode 4000 \
  --bridge-lib /root/fh-mahjong/build/libfh_mahjong_bridge.so
```

`--learning-seat-rule seed-mod-4` keeps only the seat `(match_seed − 1,300,000)
mod 4` from each match and drops the other three seats' transitions **during
generation, before serialization**. `--seat-rule-base-seed` defaults to
`--start-seed`, which is the 1,300,000 the rule is defined against, so it is not
passed. Transition subsampling and post-load truncation are forbidden (Amendment
2 §2) — this flag is the only admissible reduction. The result is exactly 2,000
matches per seat and ≈4.16 M transitions.

`--compressed-shards` is storage-only (`read_transition_arrays` reads compressed
and uncompressed shards identically); it changes no sample and no ordering. The
shard directory's own index is `manifest.json`; `dataset-manifest.json` is the
provenance record written beside it.

Record in the status file: the manifest's transition count,
`per_seat_transitions` (four counts), `learning_seat_rule` and
`seat_rule_base_seed`, each chunk's `transitions_before_seat_filter` (the
all-seat count the filter reduced), seed range, bridge kind, git commit,
action-space size and observation dims, plus `sha256sum dataset-manifest.json`
and the shard directory's total size.

**Gate 2a — dataset memory, before any BC training starts (Amendment 2 §3).**
`fh-mj-train-bc` materializes the whole dataset in host RAM as `float32`
(`read_transition_arrays` with `BC_ARRAY_KEYS`); there is no transition cap or
streaming path on that CLI. Per transition that is 7,018 B: planes 39×42×1
`float32` (6,552 B), scalars 58 `float32` (232 B), action mask 204 `int8`,
action ids `int64`, episode index `int32`, seat `int16`, terminal rewards 4
`float32`.

Measured heuristic yield at `--match-mode chongci --max-steps-per-episode 4000`
is **2,079 transitions per match** across all four seats (3 matches from seed
1,300,000 through `GenerateHeuristicTrajectory`; every seat is a learning seat
and every decision is a row). All-seat 10,000 matches would therefore have been
≈20.8 M transitions ≈ **136 GiB resident** against a 52 GiB WSL cap — the
finding that produced Amendment 2. One seat in four over 8,000 matches is
≈4.16 M transitions ≈ **27.2 GiB**.

Record all of these, and gate on the two that are gates:

| quantity | source | requirement |
|---|---|---|
| manifest transition count | `dataset.transitions` | recorded |
| per-seat counts | `dataset.per_seat_transitions` | recorded, four seats |
| calculated resident bytes | rows × 7,018 B | **≤ 30.00 GiB** |
| loader-only cgroup `memory.peak` | measured below | **≤ 32.00 GiB** |
| shard bytes | `du -sb bc-data` | recorded |
| dataset / config / bridge digests | `sha256sum` | recorded |

BC training itself then runs under cgroup `memory.peak` ≤ **38.00 GiB**.

Calculated figure, straight from the manifest:

```
python3 - <<'EOF'
import json
m = json.load(open("/root/fh-mahjong-runs/mortal-scale-scratch/bc-data/dataset-manifest.json"))
d = m["dataset"]
n = int(d["transitions"])
print(n, "transitions ->", n * 7018 / 1024**3, "GiB calculated resident")
print("per seat:", d["per_seat_transitions"], "rule:", d["learning_seat_rule"], d["seat_rule_base_seed"])
EOF
du -sb /root/fh-mahjong-runs/mortal-scale-scratch/bc-data
free -g
```

Loader-only measurement — a **freshly created** cgroup (so `memory.peak` starts
at zero), §4's containment around it, and nothing in it but the load
`fh-mj-train-bc` itself performs:

```
mkdir -p /sys/fs/cgroup/msscratch-loader
echo 44G > /sys/fs/cgroup/msscratch-loader/memory.high
echo 48G > /sys/fs/cgroup/msscratch-loader/memory.max
echo 0   > /sys/fs/cgroup/msscratch-loader/memory.swap.max
echo 1   > /sys/fs/cgroup/msscratch-loader/memory.oom.group
echo $$  > /sys/fs/cgroup/msscratch-loader/cgroup.procs

PYTHONUNBUFFERED=1 uv run --project ai python - <<'EOF'
from pathlib import Path
from fh_mahjong_ai.scripts.train_bc import BC_ARRAY_KEYS
from fh_mahjong_ai.storage import read_transition_arrays
arrays = read_transition_arrays(
    Path("/root/fh-mahjong-runs/mortal-scale-scratch/bc-data"), keys=BC_ARRAY_KEYS)
rows = int(arrays["action_ids"].shape[0])
print(rows, "rows", sum(v.nbytes for v in arrays.values()) / 1024**3, "GiB of arrays")
print({k: (v.shape, str(v.dtype)) for k, v in arrays.items()})
EOF

cat /sys/fs/cgroup/msscratch-loader/memory.peak
grep -E '^(anon|file) ' /sys/fs/cgroup/msscratch-loader/memory.stat
echo $$ > /sys/fs/cgroup/cgroup.procs
```

Capture the `grep -E '^(anon|file) '` line immediately after reading `memory.peak`,
before the shell moves back to the root cgroup — `memory.peak` includes page cache
charged for shard reads, and with `memory.high=44G` nothing reclaims that cache
below the 32.00 GiB gate. Record both `anon` and `file` in the status file
alongside `memory.peak`.

The 44/48 GiB containment is not the gate — it exists so a breach is contained
instead of swapping; the go/no-go is the `memory.peak` value read after the load
returns. Move the shell back to the root cgroup afterwards so the lap's own
guards are not scoped to this one.

Any breach — calculated > 30.00 GiB or loader peak > 32.00 GiB — **stops and
returns to thread `01a0147d`.** Amendment 2 §3 makes no further sampling
reduction, streaming rewrite, swap, or retry automatic, and Amendment 1 §12
forbids shrinking the model, data, workers, or budget silently. Do not truncate
the dataset, do not swap the match mode, and do not reduce the match count on
this runbook's authority. The 32.00 GiB gate is judged on `memory.peak` as
ratified, regardless of the `anon`/`file` split — but a breach where `anon` ≤
30.00 GiB and `file` accounts for the excess over 32.00 GiB is reported to the
consult as a page-cache artefact, not silently passed and not silently retried.

## 3. Stage 1b — BC per arm

Each BC run below executes inside the same §4/§5 containment (cgroup-v2
`memory.high=44GiB`, `memory.max=48GiB`, `memory.swap.max=0`, `memory.oom.group=1`,
swap 0) with `cgroup_guard38.sh` armed exactly as §5 describes; the run's cgroup
`memory.peak` is ≤ **38.00 GiB** and is recorded in the status file at the end of
each BC run.

Optimizer and batch defaults are frozen unchanged (`--batch-size 64`, `--lr 3e-4`):
pass neither flag. Both arms use the same dataset, the same `--validation-fraction 0.1`
and the same `--split-seed 1300000`, so train/validation membership and shuffle are
identical across arms. The split is by whole-match episode index, never by transition.

Control:

```
PYTHONUNBUFFERED=1 uv run --project ai fh-mj-train-bc \
  --data /root/fh-mahjong-runs/mortal-scale-scratch/bc-data \
  --checkpoint-dir /root/fh-mahjong-runs/mortal-scale-scratch/bc-control \
  --epochs 30 --patience 5 --min-delta 1e-4 --min-epochs 5 \
  --validation-fraction 0.1 --split-seed 1300000 \
  --model-channels 96 --model-residual-blocks 4 --model-kernel-width 1 \
  --model-event-window 128 --model-privileged-critic --model-aux-heads \
  --report-output /root/fh-mahjong-runs/mortal-scale-scratch/bc-control/report.json \
  --device cuda
```

Big — identical but for the trunk and the output directory:

```
PYTHONUNBUFFERED=1 uv run --project ai fh-mj-train-bc \
  --data /root/fh-mahjong-runs/mortal-scale-scratch/bc-data \
  --checkpoint-dir /root/fh-mahjong-runs/mortal-scale-scratch/bc-big \
  --epochs 30 --patience 5 --min-delta 1e-4 --min-epochs 5 \
  --validation-fraction 0.1 --split-seed 1300000 \
  --model-channels 192 --model-residual-blocks 24 --model-kernel-width 1 \
  --model-event-window 128 --model-privileged-critic --model-aux-heads \
  --report-output /root/fh-mahjong-runs/mortal-scale-scratch/bc-big/report.json \
  --device cuda
```

At least 5 and at most 30 epochs; the run stops after 5 consecutive epochs without
an absolute validation-cross-entropy improvement of 1e-4, and the lowest-CE epoch
is byte-copied to `<checkpoint-dir>/best.pt` — that file, not the last epoch, is
what the PPO stage initializes from.

`best.pt` is refreshed as soon as a new lowest-CE epoch is checkpointed, so an
interrupted BC run always leaves a current `best.pt` behind. `--resume` restarts
patience and best-epoch tracking from the resumed epoch, and `write_training_report`
overwrites `--report-output` wholesale — the resumed run's `report.json` rebuilds
`epochs` from empty, so there is no merged `report.json` to read `best.pt` from.
Before resuming, archive the pre-resume `report.json` and `best.pt` (for example
`report.pre-resume.json` and `best.pre-resume.pt`) into the same checkpoint
directory. After the resumed run finishes, compare the two reports'
per-epoch `validation.mean_cross_entropy` by hand across both `epochs` lists and
select the checkpoint belonging to the overall lowest value — the pre-resume
`best.pre-resume.pt` or the resumed run's `best.pt` — before the PPO stage
initializes from it. Record which file won in the status file.

Record per arm from `report.json`: `best_epoch`, `best_validation_cross_entropy`,
`stopped_early`, `epochs_run`, and the best epoch's `validation.agreement_rate`
(legal-action-masked top-1) and `validation.mean_cross_entropy`. Every epoch's
`validation_events` must read `"zeroed"` — BC trains with `events=None`, so this is
the actual zero-event condition Amendment 1 §3 requires the numbers to be reported
under, and those numbers describe the BC stage only. Also record
`sha256sum bc-control/best.pt bc-big/best.pt`.

Amendment 2 §4 additionally requires that top-1 **per seat**. `report.json`
carries the overall figure only, so recompute it over the same split, sliced by
the shards' own `seats` array — the dataset holds one seat per match, so each
seat's rows come from its own ≈200 validation matches:

```
uv run --project ai python - <<'EOF'
from pathlib import Path
import numpy as np, torch
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.evaluate import compute_action_agreement_from_batches
from fh_mahjong_ai.model import PolicyValueNet, infer_model_config
from fh_mahjong_ai.scripts.train_bc import (
    BC_ARRAY_KEYS, iter_array_observation_action_batches, split_array_train_validation)
from fh_mahjong_ai.storage import read_transition_arrays

DATA = Path("/root/fh-mahjong-runs/mortal-scale-scratch/bc-data")
CKPT = Path("/root/fh-mahjong-runs/mortal-scale-scratch/bc-big/best.pt")   # and bc-control
DEVICE = "cuda"

arrays = read_transition_arrays(DATA, keys=BC_ARRAY_KEYS)
_, validation = split_array_train_validation(
    arrays["episode_index"], validation_fraction=0.1, seed=1300000)
payload = torch.load(CKPT, map_location="cpu")
model = PolicyValueNet(EnvConfig(), infer_model_config(payload["model"], payload.get("metadata"))).to(DEVICE)
model.load_state_dict(payload["model"])
model.eval()

def agreement(indices):
    return compute_action_agreement_from_batches(
        model, iter_array_observation_action_batches(arrays, indices, 4096),
        device=DEVICE, allow_zero_events=True)

overall = agreement(validation)
print(f"overall n={validation.size} top1={overall['agreement_rate']:.4f} ce={overall['mean_cross_entropy']:.4f}")
seats = arrays["seats"][validation]
for seat in sorted(int(s) for s in np.unique(seats)):
    rows = validation[seats == seat]
    seat_report = agreement(rows)
    print(f"seat {seat} n={rows.size} top1={seat_report['agreement_rate']:.4f} "
          f"ce={seat_report['mean_cross_entropy']:.4f}")
EOF
```

`validation_fraction` and `seed` here are the `--validation-fraction 0.1` and
`--split-seed 1300000` the training command was launched with — anything else
scores a different held-out set. `allow_zero_events=True` reproduces BC's own
zero-event condition. The printed `overall` must equal the best epoch's
`validation.agreement_rate` in `report.json`; if it does not, the split inputs
disagree with the run and the per-seat numbers are not the required readout.
Record all five figures per arm. They measure held-out imitation quality, not
PPO strength and not campaign success.

The big net is expected to fit heuristic play better. That is the starting point,
not a result. Non-finite loss, a loader mismatch, or no improvement at all is a
prerequisite failure — stop and consult.

## 4. Stage 2 preflight — bench (big arm only, before its lap)

Amendment 1 §11: run the full production collect + PPO update cycle at 960/768
before the big lap. Bench seeds 1,700,000–1,700,959. Containment while it runs:
cgroup-v2 `memory.high=44GiB`, `memory.max=48GiB`, `memory.swap.max=0`,
`memory.oom.group=1`.

Export the bench checkpoint first (Amendment 2 §5) — the step-zero net the lap
itself will construct, gated and digest-pinned:

```
mkdir -p /root/fh-mahjong-runs/mortal-scale-scratch/bench

uv run --project ai fh-mj-export-scratch-init \
  --bc /root/fh-mahjong-runs/mortal-scale-scratch/bc-big/best.pt \
  --out /root/fh-mahjong-runs/mortal-scale-scratch/bench/big-init.pt \
  --model-channels 192 --model-residual-blocks 24 --model-kernel-width 1 \
  --event-window 128 --privileged-critic --aux-heads \
  | tee /root/fh-mahjong-runs/mortal-scale-scratch/bench/big-init-transfer-gate.json

sha256sum /root/fh-mahjong-runs/mortal-scale-scratch/bench/big-init.pt
```

The command prints the same transfer-gate record §6 describes, and stores it in
the file's own `metadata["init"]["transfer_gate"]` alongside the BC digest; a
gate failure exits nonzero and writes nothing. Record `big-init.pt`'s sha256 and
the gate record in the status file before the bench runs.

```
PYTHONUNBUFFERED=1 uv run --project ai fh-mj-collect-bench \
  --champion /root/fh-mahjong-runs/mortal-scale-scratch/bench/big-init.pt \
  --model-channels 192 --model-residual-blocks 24 --model-kernel-width 1 \
  --model-privileged-critic --model-aux-heads \
  --workers 10 \
  --matches 960 --base-seed 1700000 \
  --dispatch-chunk 320 \
  --match-mode chongci --max-steps-per-episode 4000 \
  --event-window 128 \
  --full-cycle --minibatch-size 768 --ppo-epochs 2 \
  --gamma 0.99 --gae-lambda 0.95 --lr 2e-5 --entropy-coef 0 \
  --ppo-device cuda --minibatch-device-transfer \
  --json /root/fh-mahjong-runs/mortal-scale-scratch/bench/preflight-960-mb768.json
```

`fh-mj-collect-bench` has no `--scratch`/`--init-from-bc`, which is why the
initialization arrives as a file. `--champion big-init.pt` is an **identity
load**: `build_b2b_model` loads every tensor same-shape and then re-copies its
two surgical tensors (`trunk.0`, `value_head.0`) at their full width, so nothing
is left zeroed and the benched net matches the exported file's BC-loaded
prefixes and zeroed event columns exactly — the file's randomly-initialised
modules are not reproduced byte-for-byte (each process draws its own random
init), but its actions, trajectory lengths, rows, and memory envelope match the
big lap's step zero. Its `bad_skipped`/`bad_missing` check fails closed, so an
architecture mismatch between the export flags and the bench flags raises instead
of silently dropping layers.

Benching `bc-big/best.pt` directly is what Amendment 2 §5 rejects: that load is
equally verbatim, which leaves BC's untrained, nonzero event columns in `trunk.0`
multiplying a brand-new event GRU's output — a different policy, and therefore
different actions, rows and memory from the lap that `--init-from-bc` will start.

This is an infrastructure gate, not a parity gate; parity is `verify_bc_transfer`,
which the export runs here and the lap runs again inside itself (§6).

Go / no-go — ALL must hold:

1. The 960-match collection AND the mb768 update complete: no OOM kill, no CUDA OOM.
2. cgroup `memory.peak` ≤ **38.00 GiB**.
3. Peak aggregate process-tree RSS ≤ **40.00 GiB**.
4. CUDA peak allocated ≤ **20.00 GiB**.
5. Truncation ≈ 0, `dealin_positive_rate` > 0, `rank_label_coverage` ≈ 1.
6. Amendment 2 §6's load-bearing evidence is recorded: complete seed coverage of
   1,700,000–1,700,959, the rollout digest, rows, the expected optimizer-step
   arithmetic including the ragged tail (`2 × ceil(rows / 768)`), labels,
   truncation, telemetry, the memory/CUDA peaks above, and monitoring with no gaps.

`all_digests_equal` and `rows_and_labels_equal` are recorded too, but Amendment 2
§6 makes them **explicitly non-load-bearing**: both compare across worker counts,
and at the single frozen count of 10 they are trivially true.

Record the report's `matches_per_second` and `update_seconds`, and the projected wall
time (`960 / matches_per_second + update_seconds` per iteration × 200 iterations), in
the status file before the big lap launches. Any breach, monitoring gap, OOM, or integrity failure stops
the experiment and returns to consultation. Do not shrink the model, data, workers,
or budget.

## 5. Control lap

Guards armed first, as in the ds960 lap: `watchdog_lap.sh` (5 Hz tree RSS) and
`cgroup_guard38.sh` (kill on cgroup peak > 38 GiB, tree > 40 GiB, or any new
`memory.events` high/max/oom/oom_kill), same cgroup containment as §4.

```
PYTHONUNBUFFERED=1 uv run --project ai fh-mj-train-b2b \
  --scratch --init-from-bc /root/fh-mahjong-runs/mortal-scale-scratch/bc-control/best.pt \
  --model-channels 96 --model-residual-blocks 4 --model-kernel-width 1 \
  --event-window 128 --privileged-critic --aux-heads \
  --checkpoint-dir /root/fh-mahjong-runs/mortal-scale-scratch/control/ckpt \
  --base-seed 1400000 --iterations 200 \
  --matches-per-iter 320 --minibatch-size 256 \
  --collect-dispatch-chunk 320 --minibatch-device-transfer \
  --num-workers 10 \
  --lr 2e-5 --head-lr 2e-4 --head-lr-iters 25 \
  --entropy-coef 0 --ppo-epochs 2 --gamma 0.99 \
  --match-mode chongci --max-steps-per-episode 4000 --device cuda \
  --train-state-every 5
```

Resume after a crash or box restart: archive the prior attempt's directory first,
then re-issue the same command with `--resume-from-state
/root/fh-mahjong-runs/mortal-scale-scratch/control/ckpt/train_state.pt` added.
Every flag except `--num-workers` and `--collect-dispatch-chunk` must match the
launch exactly; the resume validates against the saved `config_echo` and raises on
drift, naming both values. The first resumed collection must reproduce its original
iteration's rows, optimizer steps, labels and truncation exactly. Do not rebuild
the bridge mid-lap.

Never pass `--fresh-run-overwrite` to continue a lap: it discards the run's
managed artifacts and starts iteration numbering over. Archive the prior
attempt's directory and resume with `--resume-from-state` instead.

Telemetry to watch in `history.json`: `lr_bc` = 2e-5 on every iteration, `lr_heads`
= 2e-4 for iterations 1–25 and 2e-5 from 26, `optimizer_steps` ≈ `2 × ceil(rows/256)`,
`truncation_rate` 0, `dealin_positive_rate` > 0, `rank_label_coverage` ≈ 1,
`approx_kl` and `clip_fraction` aggregated over all minibatches.

## 6. Initialization provenance (both laps, automatic)

`--init-from-bc` runs the Amendment 1 §4 transfer gate inside construction, before
any rollout is collected and before any artifact is moved: the BC file is read once
and its sha256 must equal the digest the model was built from; legal-action logits,
probabilities and greedy actions must equal the BC net's exactly on a seeded 64-row
probe; every loaded tensor must be byte-equal, with `trunk.0`'s trailing event
columns exactly zero. Any deviation aborts the launch.

An abort here returns to thread `01a0147d`. Do not loosen the gate or convert it
to a tolerance: BC forwards a zero event vector and this net has zero event
columns, so the event term is exactly 0.0 on both sides and any nonzero diff is a
real defect, never float noise. The same gate runs inside
`fh-mj-export-scratch-init` (§4), so a bench checkpoint that exists has passed it.

After iteration 1, confirm the record is on disk and copy it into the status file.
Every `iter_*.pt` carries it under `metadata["init"]`, and `train_state.pt` carries
the same block at its top level:

```
uv run --project ai python - <<'EOF'
import torch
p = "/root/fh-mahjong-runs/mortal-scale-scratch/control/ckpt/iter_001.pt"
init = torch.load(p, map_location="cpu")["metadata"]["init"]
g = init["transfer_gate"]
print(init["kind"], init["bc_checkpoint_path"], init["bc_checkpoint_sha256"])
print(g["bc_checkpoint_sha256"], g["max_abs_logit_diff"], g["max_abs_prob_diff"],
      g["greedy_match_rate"], g["loaded_tensors_identical"],
      len(g["loaded_keys"]), len(g["unloaded_keys"]))
EOF
```

Record `kind`, `bc_checkpoint_path`, `bc_checkpoint_sha256`, the three probe
quantities, and the loaded/unloaded key counts per arm. Resume preserves them.

## 7. Screening (both arms)

Screen at iterations **25/50/75/100/125/150/175/200** on one fixed fresh 120-seed
duplicate-seat window, `--start-seed 1710000`, against an `anchor075` comparator
**regenerated on the current bridge** — generate it once, before the first
screening, and reuse that one JSON for every screening of both arms:

```
uv run --project ai fh-mj-evaluate \
  --checkpoint /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt \
  --model-residual-blocks 4 \
  --model-event-window 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 120 \
  --start-seed 1710000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/mortal-scale-scratch/screen/anchor-screen-current-bridge.json
```

Control candidate at iteration XXX:

```
uv run --project ai fh-mj-evaluate \
  --checkpoint /root/fh-mahjong-runs/mortal-scale-scratch/control/ckpt/iter_XXX.pt \
  --model-channels 96 --model-residual-blocks 4 --model-kernel-width 1 \
  --model-event-window 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 120 \
  --start-seed 1710000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/mortal-scale-scratch/screen/control-XXX.json

uv run --project ai fh-mj-compare \
  /root/fh-mahjong-runs/mortal-scale-scratch/screen/control-XXX.json \
  /root/fh-mahjong-runs/mortal-scale-scratch/screen/anchor-screen-current-bridge.json
```

Big candidate at iteration XXX — the same two commands with
`--model-channels 192 --model-residual-blocks 24 --model-kernel-width 1`, the
`big/ckpt` path and `screen/big-XXX.json`.

`fh-mj-compare` is mandatory for every delta claim; the screening delta is its
`mean_delta` (candidate minus anchor), read together with `delta_ci95_clustered`.

**Kill rule (Amendment 1 §7).** The sole early kill is at iteration 100, and it
applies to each arm: stop iff `delta100 − delta75 <= 0` **and** `delta100 < −0.20`.
No other iteration triggers a kill, no later slope-based stopping, no adaptive
extension. Scratch curves start far below the anchor; that alone is not a kill.

**Control recipe gate (Amendment 1 §2).** After the control's full 200 iterations,
the big arm is authorized only if the control's iteration-200 screening delta versus
`anchor075` is **≥ −0.0600**, telemetry is healthy, and all integrity gates passed.
Otherwise stop and return to consultation: that is a recipe failure, not a scale
null, and scale remains untested. Control results may not tune BC, learning rates,
schedules, budgets, or big-arm configuration.

## 8. Big lap

Only after §4's bench passes and §7's control recipe gate passes.

```
PYTHONUNBUFFERED=1 uv run --project ai fh-mj-train-b2b \
  --scratch --init-from-bc /root/fh-mahjong-runs/mortal-scale-scratch/bc-big/best.pt \
  --model-channels 192 --model-residual-blocks 24 --model-kernel-width 1 \
  --event-window 128 --privileged-critic --aux-heads \
  --checkpoint-dir /root/fh-mahjong-runs/mortal-scale-scratch/big/ckpt \
  --base-seed 1500000 --iterations 200 \
  --matches-per-iter 960 --minibatch-size 768 \
  --collect-dispatch-chunk 320 --minibatch-device-transfer \
  --num-workers 10 \
  --lr 2e-5 --head-lr 2e-4 --head-lr-iters 25 \
  --entropy-coef 0 --ppo-epochs 2 --gamma 0.99 \
  --match-mode chongci --max-steps-per-episode 4000 --device cuda \
  --train-state-every 5
```

Same guards, same resume discipline, same screening schedule and kill rule as the
control. `optimizer_steps` ≈ `2 × ceil(rows/768)` — approximately the control's
count, which is the point of the 960/768 coupling.

## 9. Selection and confirmation

Selection: each arm's best **healthy registered** screening milestone by screening
delta, an exact tie going to the later milestone. Only the eight registered
iterations are admissible; no unregistered checkpoint may be substituted after
seeing later results.

Confirmation runs on one fresh window — 1500 paired seeds × 4 duplicate seats,
`--start-seed 1720000`, same bridge — for the selected big checkpoint, the
regenerated `anchor075`, and the selected control checkpoint:

```
uv run --project ai fh-mj-evaluate \
  --checkpoint /root/fh-mahjong-runs/mortal-scale-scratch/big/ckpt/iter_<sel>.pt \
  --model-channels 192 --model-residual-blocks 24 --model-kernel-width 1 \
  --model-event-window 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 1500 \
  --start-seed 1720000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/mortal-scale-scratch/confirm/confirm-big.json

uv run --project ai fh-mj-evaluate \
  --checkpoint /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt \
  --model-residual-blocks 4 \
  --model-event-window 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 1500 \
  --start-seed 1720000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/mortal-scale-scratch/confirm/confirm-anchor.json

uv run --project ai fh-mj-evaluate \
  --checkpoint /root/fh-mahjong-runs/mortal-scale-scratch/control/ckpt/iter_<sel>.pt \
  --model-channels 96 --model-residual-blocks 4 --model-kernel-width 1 \
  --model-event-window 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 1500 \
  --start-seed 1720000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/mortal-scale-scratch/confirm/confirm-control.json
```

Primary (practical gate) and secondary (the scale question):

```
uv run --project ai fh-mj-compare \
  /root/fh-mahjong-runs/mortal-scale-scratch/confirm/confirm-big.json \
  /root/fh-mahjong-runs/mortal-scale-scratch/confirm/confirm-anchor.json

uv run --project ai fh-mj-compare \
  /root/fh-mahjong-runs/mortal-scale-scratch/confirm/confirm-big.json \
  /root/fh-mahjong-runs/mortal-scale-scratch/confirm/confirm-control.json
```

Each claim requires **both**: clustered CI95 lower bound > 0
(`mean_delta − delta_ci95_clustered > 0`, read the clustered CI, never the naive
iid one) **and** `large_loss_rate(candidate) <= large_loss_rate(comparator) + 0.015`
(`large_loss_rate_a <= large_loss_rate_b + 0.015`). No second window, no enlarged N,
no reselection.

Interpretation (Amendment 1 §10): big-versus-anchor is the primary practical gate.
Big-versus-control identifies superiority of the larger-model/proportional-data
**package**, not architecture scale alone, because the two arms' data volumes
differ. "Scratch scale confirms" requires both gates. If the control passes its
recipe gate but big fails confirmation, this exact scratch-scale package closes as
null. If the control fails, scale remains untested.

## 10. After the result

Everything terminal returns to Codex thread `01a0147d`: the two BC reports, both
`history.json` files, the transfer-gate records, guard telemetry, all screening
reports, and the confirmation comparisons. Infrastructure failures are not
scientific nulls. Neither arm may be promoted or deployed automatically, and no
next lap is auto-chained.

Retention: keep each arm's eight registered screening checkpoints plus its selected
checkpoint, both `best.pt` BC checkpoints, `bench/big-init.pt` with its transfer-gate
record, and the dataset manifest; prune the rest after the experiment closes.
`train_state.pt` can be deleted once a lap is confirmed or nulled.

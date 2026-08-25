# gru-width Run Protocol (post-merge, RTX 4090 box)

Design: `worklog/specs/2026-08-02-gru-width-design.md`. This
runbook transcribes spec §4 (ratified gate parameters) into exact commands.
Prereqs: merged main (with this branch's Tasks 1-4) pulled on the box (`ssh
wsl`, `/root/fh-mahjong`); bridge rebuilt (`go build -buildmode=c-shared -o
build/libfh_mahjong_bridge.so ./cmd/rlbridge`).

## 0. Anchor (frozen path + sha)

Unchanged from the restart ladder / deep4+12-rezero laps — restart-iter075,
already a confirmed gate-qualified champion:

```
/root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt
sha256: ce9d867f803bb41acad30f1f4c137e82d7946ed2c4db769e265d0c9cd08f75d4
```

Confirm the sha matches on the box before spending any compute:

```
sha256sum /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt
```

## 1. Box preflight: param-count budget + step-zero parity

Two things proved together, on the box, before launch. `widen_event_gru`
requires an `EnvConfig` cross-check against the anchor's own construction
shapes, so build the SAME live env the real lap trains under (chongci,
step cap 4000).

```
uv run --project ai python - <<'EOF'
import math

import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.train_b2b import _b2b_model_env_config, widen_event_gru
from fh_mahjong_ai.storage import load_checkpoint

ANCHOR = "/root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt"
NEW_HIDDEN = 256

payload = torch.load(ANCHOR, map_location="cpu")
anchor_config = ModelConfig(**payload["metadata"]["model_config"])
assert anchor_config.event_output_dim == 0, "anchor is already widened"

live_env = EnvConfig(bridge_kind="go", match_mode="chongci",
                     max_steps_per_episode=4000, oracle_observation=True,
                     event_history_window=anchor_config.event_window)

anchor = PolicyValueNet(_b2b_model_env_config(live_env), anchor_config)
load_checkpoint(ANCHOR, anchor)
anchor.eval()

widened = widen_event_gru(ANCHOR, NEW_HIDDEN, env_config=live_env, device="cpu")
widened.eval()
assert widened.model_config.event_hidden_dim == NEW_HIDDEN
assert widened.model_config.event_output_dim == anchor_config.event_hidden_dim

# --- Budget: iterations = ceil_to_5(150 * candidate_params / anchor_params) ---
anchor_params = sum(p.numel() for p in anchor.parameters())
candidate_params = sum(p.numel() for p in widened.parameters())
ratio = candidate_params / anchor_params
iterations = math.ceil((150 * ratio) / 5) * 5
print(f"anchor_params={anchor_params} candidate_params={candidate_params} "
      f"ratio={ratio:.4f} iterations={iterations}")

# --- Step-zero parity: widened net's outputs EXACTLY equal the anchor's ---
window = anchor_config.event_window
for seed in range(4):
    rng = np.random.default_rng(seed)
    n = 8
    planes = torch.from_numpy(rng.random((n, 51, 42, 1), dtype=np.float32))
    scalars = torch.from_numpy(rng.random((n, 58), dtype=np.float32))
    mask = torch.ones((n, 204), dtype=torch.int8)
    mask[:, ::7] = 0
    events = torch.from_numpy(rng.integers(0, 0x10000, size=(n, window),
                                           dtype=np.uint32).astype(np.int64))
    lengths = torch.from_numpy(rng.integers(0, window + 1, size=(n,)).astype(np.int64))

    with torch.no_grad():
        a_logits, a_value = anchor(planes, scalars, mask, events=events, event_lengths=lengths)
        w_logits, w_value = widened(planes, scalars, mask, events=events, event_lengths=lengths)
        a_q, _ = anchor.q_values(planes, scalars, mask)
        w_q, _ = widened.q_values(planes, scalars, mask)
        a_feat = anchor.encode(planes, scalars, events, lengths)
        w_feat = widened.encode(planes, scalars, events, lengths)
        a_aux = anchor.aux_predictions(a_feat)
        w_aux = widened.aux_predictions(w_feat)

    assert torch.equal(a_feat, w_feat), f"event-feature mismatch seed={seed}"
    assert torch.equal(a_logits, w_logits), f"logits mismatch seed={seed}"
    assert torch.equal(a_value, w_value), f"value mismatch seed={seed}"
    assert torch.equal(a_q, w_q), f"Q mismatch seed={seed}"
    for key in ("belief", "dealin", "rank"):
        assert torch.equal(a_aux[key], w_aux[key]), f"aux[{key}] mismatch seed={seed}"
    assert torch.equal(a_logits.argmax(dim=-1), w_logits.argmax(dim=-1)), f"greedy-action mismatch seed={seed}"

print("STEP-ZERO PARITY OK")
EOF
```

Do not proceed past this point unless the script prints both the budget
line and `STEP-ZERO PARITY OK`. Any `AssertionError` means the widening
warm-start is unsound for this anchor and the lap must not launch. Freeze
the printed `iterations` value in §2's launch command (spec expects ~1.08x
-> 165; use the box's actual measured value, not the estimate, if it
differs).

## 2. Launch

```
PYTHONUNBUFFERED=1 uv run --project ai fh-mj-train-b2b \
  --champion /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt \
  --widen-event-hidden 256 \
  --model-residual-blocks 4 \
  --checkpoint-dir /root/fh-mahjong-runs/gru-width/ckpt \
  --base-seed 400000 --iterations <computed — expected ~165> --matches-per-iter 320 \
  --num-workers 10 \
  --lr 2e-5 --entropy-coef 0 --ppo-epochs 2 --gamma 0.99 \
  --match-mode chongci --max-steps-per-episode 4000 --device cuda \
  --train-state-every 5
```

`--num-workers 10`: memory-proven (deep4+12-rezero's 20-worker + 16GB
master OOM'd the 31GB box twice mid-run; 10 workers finished the lap
cleanly after PR #187 made `num_workers` a semantics-neutral resume field).
Do not raise it for this lap without a fresh worker benchmark and its own
memory-headroom check — see §6.

Recipe is otherwise byte-identical to the ratified champion recipe (dense
per-hand score-delta reward, `gamma=0.99`, 320 matches/iter, `lr=2e-5`,
entropy 0, 2 PPO epochs) — only the event-GRU width changes.

`--widen-event-hidden` and `--model-growth-blocks` are mutually exclusive
(the CLI errors if both are set > 0) — this lap uses only the former.

A fresh launch (no `--resume-from-state`) into a `--checkpoint-dir` that
already holds a prior run's `history.json`, `train_state.pt`, or any
`iter_*.pt` raises instead of silently overwriting/mixing that run's
checkpoints — point `--resume-from-state` at it to continue that run, use
a fresh empty directory, or pass `--fresh-run-overwrite` to explicitly
delete just those managed artifacts and start over in place.

Orchestrator/screening state lives entirely under `/root/fh-mahjong-runs/`
(checkpoint dir, `train_state.pt`, screening/comparator JSON reports) —
these paths are reboot-safe: `train_state.pt` (written every 5 iterations)
lets §5 resume across a box restart without re-deriving anything from
process memory, and no screening decision depends on a still-running
process's in-memory state.

## 3. Resume after a crash / box restart

Same launch command, with `--champion` optional (dropped or kept — it is
ignored once `--resume-from-state` is given). CRITICAL: `--widen-event-hidden`
is INERT on resume (it only routes the fresh-launch warm start) — the
load-bearing architecture flags on resume are `--model-event-hidden-dim 256`
and `--model-event-output-dim 128`, which must match the saved config echo
exactly or the resume raises:

```
PYTHONUNBUFFERED=1 uv run --project ai fh-mj-train-b2b \
  --model-residual-blocks 4 \
  --model-event-hidden-dim 256 --model-event-output-dim 128 \
  --checkpoint-dir /root/fh-mahjong-runs/gru-width/ckpt \
  --base-seed 400000 --iterations <computed — expected ~165> --matches-per-iter 320 \
  --num-workers 10 \
  --lr 2e-5 --entropy-coef 0 --ppo-epochs 2 --gamma 0.99 \
  --match-mode chongci --max-steps-per-episode 4000 --device cuda \
  --train-state-every 5 \
  --resume-from-state /root/fh-mahjong-runs/gru-width/ckpt/train_state.pt
```

Unlike the initial launch — where `--widen-event-hidden > 0` routes model
construction through `widen_event_gru` and the anchor's own saved config
(`event_hidden_dim=256`, `event_output_dim=128`) supersedes CLI flags — the
`--resume-from-state` path builds the model DIRECTLY from the CLI-supplied
`ModelConfig` (no anchor to derive it from) and validates it against the
state file's `config_echo`. `--widen-event-hidden` itself is not one of the
validated `ModelConfig` fields directly, but the effective widths it
implies (`event_hidden_dim=256`/`event_output_dim=128`, via
`--model-event-hidden-dim`/`--model-event-output-dim` if the resume path
ever needs them passed explicitly) ARE — a mismatch there raises
`ValueError` naming both the saved and requested values before touching
anything. Every other flag above (`--iterations`, `--matches-per-iter`,
`--lr`, etc.) must match the original launch exactly for the same reason.
`history.json` is reconciled automatically (rows at or after the resumed
iteration are dropped and re-appended). `num_workers` alone is exempt
(semantics-neutral, PR #187) — it is the one flag safe to change across a
resume, which is how §2's 10-worker choice was reached after the
deep4+12-rezero OOMs.

## 4. Screening

At iterations 25/50/75/100/125/150/`<final>`, evaluate against a comparator
anchor REGENERATED on the identical current bridge, `910000+` seed window
(120 seeds, strict). Candidate flags carry the new dims explicitly
(note: fh-mj-evaluate's greedy path builds the model FROM these flags — they are load-bearing here; metadata-authoritative loading applies to CheckpointPolicy/serving, not this path):

```
fh-mj-evaluate --checkpoint /root/fh-mahjong-runs/gru-width/ckpt/iter_XXX.pt \
  --model-residual-blocks 4 \
  --model-event-window 128 \
  --model-event-hidden-dim 256 --model-event-output-dim 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 120 \
  --start-seed 910000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/gru-width/screen-XXX.json
```

Regenerate the anchor comparator ONCE on the current bridge before the
first screening, at the same `910000+` window (the bridge has moved since
the deep4+12-rezero comparator was generated — do not reuse it):

```
fh-mj-evaluate --checkpoint /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt \
  --model-residual-blocks 4 \
  --model-event-window 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 120 \
  --start-seed 910000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/gru-width/anchor-screen-current-bridge.json
```

```
fh-mj-compare /root/fh-mahjong-runs/gru-width/screen-XXX.json \
  /root/fh-mahjong-runs/gru-width/anchor-screen-current-bridge.json
```

`<final>` is the last pre-registered screening point (the computed
iteration count from §1, expected ~165) — screen it in addition to
25/50/75/100/125/150, exactly like the earlier laps screened their own
hard-stop iteration.

## 5. Kill rule (ONLY at iter 100)

Stop the lap ONLY if BOTH the iter-75 AND iter-100 champion-relative
screening deltas are `< -0.06`. No other iteration triggers a kill. If
triggered: stop, diagnose, report — a scratch run or aux-weight change is a
NEW user decision, not automatic.

## 6. Hard stop at `<final>` — selection unchanged

No extension past the computed `<final>` iteration (this lap's budget is
fixed by the ratified param-ratio budget, same discipline as
deep4+12-rezero — not the B2b runbook's conditional extension). Selection
protocol is UNCHANGED from prior laps: freeze the best eligible
pre-registered screening checkpoint (healthy telemetry: nondecreasing
`dealin_positive_rate`/`rank_label_coverage`, zero truncation) among
{25, 50, 75, 100, 125, 150, `<final>`} — no substitution after seeing later
results, exact ties go to the later checkpoint.

## 7. Confirmation

Fresh `1110000+` window, 1500 seeds/side, back-to-back, same bridge:

```
fh-mj-evaluate --checkpoint <selected>.pt \
  --model-residual-blocks 4 \
  --model-event-window 128 \
  --model-event-hidden-dim 256 --model-event-output-dim 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 1500 \
  --start-seed 1110000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/gru-width/confirm-candidate.json

fh-mj-evaluate --checkpoint /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt \
  --model-residual-blocks 4 \
  --model-event-window 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 1500 \
  --start-seed 1110000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/gru-width/confirm-anchor.json

fh-mj-compare /root/fh-mahjong-runs/gru-width/confirm-candidate.json \
  /root/fh-mahjong-runs/gru-width/confirm-anchor.json
```

Promotion requires BOTH:
- paired placement clustered 95% CI clears 0 (lower bound > 0), AND
- `large_loss_rate(candidate) <= large_loss_rate(anchor) + 0.015` absolute.

No optional stopping; do not gate another checkpoint on this window.
`1110000+` has not been spent by any prior lap.

## 8. Checkpoint retention

Keep the pre-registered screening checkpoints (25/50/75/100/125/150/
`<final>`) plus the final selected checkpoint; prune the rest after the lap
completes. `train_state.pt` (written every 5 iterations) can be deleted
once the lap is confirmed or nulled — it exists only to survive restarts
mid-lap.

## 9. Worker-count memory criterion (adoption rule for THIS lap)

This lap does not run a fresh `fh-mj-collect-bench` sweep — it adopts the
10-worker count directly from the deep16 OOM lesson (§2's memory note): the
deep4+12-rezero lap's own worker benchmark had picked a higher count, which
OOM'd the 31GB box twice mid-run before finishing at 10. If a future lap
wants to raise `--num-workers` above 10 again, re-run `fh-mj-collect-bench`
AND separately confirm the box has enough free memory headroom for that
worker count's peak RSS (not just an exact-digest match) before adopting it
— speed and digest equality alone are insufficient; the deep16 lesson was a
memory failure, not a correctness failure.

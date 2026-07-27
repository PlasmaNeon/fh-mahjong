# deep16-rezero Run Protocol (post-merge, RTX 4090 box)

Design: `docs/superpowers/specs/2026-07-24-deep16-rezero-design.md`. This
runbook transcribes spec §6 (ratified gate parameters) into exact commands.
Prereqs: merged main (with this branch's Tasks 1-5) pulled on the box (`ssh
wsl`, `/root/fh-mahjong`); bridge rebuilt (`go build -buildmode=c-shared -o
build/libfh_mahjong_bridge.so ./cmd/rlbridge`).

## 0. Anchor selection (frozen path + sha)

Anchor is the r2 lap's winner if r2 confirms; otherwise fall back to the
restart-iter075 checkpoint that r2 itself was launched from (already a
confirmed gate-qualified champion — see the 2026-07-24 progress-doc entry).

Default (pending r2):

```
/root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt
sha256: ce9d867f803bb41acad30f1f4c137e82d7946ed2c4db769e265d0c9cd08f75d4
```

If r2's `1030000+` confirmation passes, use **r2 iter_150** instead (sha
`518cc376...` — confirm and record the full digest before launch):

```
/root/fh-mahjong-runs/b2b-anchor075r2-restart/ckpt/iter_150.pt
sha256: 518cc376... (confirm full digest with `sha256sum` on the box before freezing)
```

Whichever path is used, freeze it and its full `sha256sum` output in this
section (and in the progress-doc pre-registration entry) BEFORE step 1.
No mid-run swap once launched.

## 1. Preflight: state-dict + step-zero parity proof

Two checks, both on the box, before spending any training compute.

**1a. State-dict sanity** — confirm the frozen anchor's sha matches what was
recorded above:

```
sha256sum /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt
```

**1b. Step-zero parity script** — proves `grow_b2b_model` produces a network
whose outputs are EXACTLY identical to the anchor's at `alpha=0`, using the
real anchor checkpoint and its own `metadata["model_config"]` (not a
synthetic small config). Run with `uv run --project ai python - <<'EOF'`:

```python
import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.oracle import _b2b_model_env_config, grow_b2b_model
from fh_mahjong_ai.storage import load_checkpoint

ANCHOR = "/root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt"
GROWTH_BLOCKS = 12

payload = torch.load(ANCHOR, map_location="cpu")
model_config_meta = payload["metadata"]["model_config"]
anchor_config = ModelConfig(**model_config_meta)
assert anchor_config.growth_blocks == 0, "anchor is already grown"

# Live env: the exact chongci/event-window shape the real lap will train
# under (matches the fh-mj-train-b2b launch command below).
live_env = EnvConfig(bridge_kind="go", match_mode="chongci",
                     max_steps_per_episode=4000, oracle_observation=True,
                     event_history_window=anchor_config.event_window)

anchor = PolicyValueNet(_b2b_model_env_config(live_env), anchor_config)
load_checkpoint(ANCHOR, anchor)
anchor.eval()

grown = grow_b2b_model(ANCHOR, GROWTH_BLOCKS, device="cpu", env_config=live_env)
grown.eval()
assert grown.model_config.growth_blocks == GROWTH_BLOCKS
for i in range(GROWTH_BLOCKS):
    assert grown.state_dict()[f"growth.{i}.alpha"].item() == 0.0

rng = np.random.default_rng(0)
n, window = 8, anchor_config.event_window
for seed in range(4):
    rng = np.random.default_rng(seed)
    planes = torch.from_numpy(rng.random((n, 51, 42, 1), dtype=np.float32))
    scalars = torch.from_numpy(rng.random((n, 58), dtype=np.float32))
    mask = torch.ones((n, 204), dtype=torch.int8)
    mask[:, ::7] = 0
    events = torch.from_numpy(rng.integers(0, 0x10000, size=(n, window),
                                           dtype=np.uint32).astype(np.int64))
    lengths = torch.from_numpy(rng.integers(0, window + 1, size=(n,)).astype(np.int64))

    with torch.no_grad():
        a_logits, a_value = anchor(planes, scalars, mask, events=events, event_lengths=lengths)
        g_logits, g_value = grown(planes, scalars, mask, events=events, event_lengths=lengths)
        a_q, _ = anchor.q_values(planes, scalars, mask)
        g_q, _ = grown.q_values(planes, scalars, mask)
        a_feat = anchor.encode(planes, scalars, events, lengths)
        g_feat = grown.encode(planes, scalars, events, lengths)
        a_aux = anchor.aux_predictions(a_feat)
        g_aux = grown.aux_predictions(g_feat)

    assert torch.equal(a_logits, g_logits), f"logits mismatch seed={seed}"
    assert torch.equal(a_value, g_value), f"value mismatch seed={seed}"
    assert torch.equal(a_q, g_q), f"Q mismatch seed={seed}"
    for key in ("belief", "dealin", "rank"):
        assert torch.equal(a_aux[key], g_aux[key]), f"aux[{key}] mismatch seed={seed}"
    assert torch.equal(a_logits.argmax(dim=-1), g_logits.argmax(dim=-1)), f"greedy-action mismatch seed={seed}"

print("STEP-ZERO PARITY OK")
EOF
```

Do not proceed past this point unless the script prints `STEP-ZERO PARITY
OK`. Any `AssertionError` here means the growth warm-start is unsound for
this anchor and the lap must not launch.

## 2. Worker benchmark (adoption rule)

```
uv run --project ai fh-mj-collect-bench \
  --champion /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt \
  --model-growth-blocks 12 --workers 5,10,20 --matches 320 \
  --base-seed 300000 --device cuda
```

Adoption rule (this is a runbook decision, not code): pick the FASTEST
worker count among `--workers` whose digest is EXACTLY equal to the 5-worker
reference digest (the command reports `all_digests_equal` and exits 0 iff
every digest matches; a non-5 digest that diverges means fan-out changed
results and must be diagnosed before adopting a higher worker count — never
adopt on speed alone if `all_digests_equal` is `False`).

If the projected 260-iteration lap at the adopted worker count would take
longer than 7 days wall-clock, STOP and raise a new decision — a GoEnvPool
port is a SEPARATE decision, out of scope for this spec (§6, "Out of
scope").

## 3. Launch

```
uv run --project ai fh-mj-train-b2b \
  --champion /root/fh-mahjong-runs/b2b-anchor075-restart/ckpt/iter_075.pt \
  --model-growth-blocks 12 \
  --checkpoint-dir /root/fh-mahjong-runs/deep16-rezero/ckpt \
  --base-seed 300000 --iterations 260 --matches-per-iter 320 \
  --num-workers <adopted> \
  --lr 2e-5 --entropy-coef 0 --ppo-epochs 2 --gamma 0.99 \
  --match-mode chongci --max-steps-per-episode 4000 --device cuda \
  --train-state-every 5
```

`<adopted>` = the worker count selected in step 2. `--train-state-every 5`
writes `<checkpoint-dir>/train_state.pt` every 5 iterations (and always at
completion) so a multi-day lap survives a box restart — see §4 (resume).

Recipe is otherwise byte-identical to the ratified champion recipe (dense
per-hand score-delta reward, `gamma=0.99`, 320 matches/iter, `lr=2e-5`,
entropy 0, 2 PPO epochs) — only the trunk depth changes.

## 4. Resume after a crash / box restart

Same launch command, with `--champion` OPTIONAL (dropped or kept — it is
ignored once `--resume-from-state` is given) and `--resume-from-state`
pointed at the checkpoint dir's state file:

```
uv run --project ai fh-mj-train-b2b \
  --model-growth-blocks 12 \
  --checkpoint-dir /root/fh-mahjong-runs/deep16-rezero/ckpt \
  --base-seed 300000 --iterations 260 --matches-per-iter 320 \
  --num-workers <adopted> \
  --lr 2e-5 --entropy-coef 0 --ppo-epochs 2 --gamma 0.99 \
  --match-mode chongci --max-steps-per-episode 4000 --device cuda \
  --train-state-every 5 \
  --resume-from-state /root/fh-mahjong-runs/deep16-rezero/ckpt/train_state.pt
```

Every flag above (`--iterations`, `--matches-per-iter`, `--lr`, etc.) must
match the original launch exactly — `train_b2b` validates the caller's
config against the state file's `config_echo` and raises `ValueError`
naming the first mismatched field before touching anything. `history.json`
is reconciled automatically (rows at or after the resumed iteration are
dropped and re-appended, so a state file slightly stale relative to
`history.json` — e.g. the process died between a state-save and the next
one — does not produce duplicate rows). Resumed runs are bit-compatible in
intent, not proven bit-identical (CUDA nondeterminism); this is documented,
not a gap to fix.

## 5. Screening

At iterations 25/50/75/100/125/150/175/200/225/250/260, evaluate against a
comparator anchor REGENERATED on the identical current bridge, `910000+`
seed window (120 seeds, strict):

```
fh-mj-evaluate --checkpoint /root/fh-mahjong-runs/deep16-rezero/ckpt/iter_XXX.pt \
  --model-growth-blocks 12 \
  --model-residual-blocks 4 --model-event-window 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 120 \
  --start-seed 910000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/deep16-rezero/screen-XXX.json
```

```
fh-mj-compare /root/fh-mahjong-runs/deep16-rezero/screen-XXX.json \
  /root/fh-mahjong-runs/deep16-rezero/anchor-screen-current-bridge.json
```

(Regenerate the anchor comparator ONCE on the current bridge before the
first screening, at the same `910000+` window, so every screening iteration
compares against the SAME anchor report — `fh-mj-evaluate` on the frozen
anchor path with the non-growth flags, i.e. no `--model-growth-blocks`.)

`fh-mj-evaluate` also carries `growth_blocks` through checkpoint save
metadata / MLflow provenance (Task 4), so `--model-growth-blocks 12` on the
CLI is a belt-and-suspenders explicit-flag path — `infer_model_config`
recovers it from the checkpoint's `growth.{i}.alpha` keys either way.

## 6. Kill rule (ONLY at iter 100)

Stop the lap ONLY if BOTH the iter-75 AND iter-100 champion-relative
screening deltas are `< -0.06`. No other iteration triggers a kill. If
triggered: stop, diagnose, report — a scratch run or aux-weight change is a
NEW user decision, not automatic.

## 7. Hard stop at 260

No extension past iteration 260, regardless of trajectory shape (unlike the
B2b runbook's conditional extension rule — this lap's budget is fixed by
the ratified 1.73x param-ratio budget). Freeze the best HEALTHY
pre-registered screening checkpoint (nondecreasing telemetry: healthy
`dealin_positive_rate`, `rank_label_coverage`, zero truncation) — no
substitution after seeing later results.

## 8. Confirmation

Fresh `1070000+` window, 1500 seeds/side, back-to-back, same bridge:

```
fh-mj-evaluate --checkpoint <selected>.pt --model-growth-blocks 12 \
  --model-residual-blocks 4 --model-event-window 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 1500 \
  --start-seed 1070000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/deep16-rezero/confirm-candidate.json

fh-mj-evaluate --checkpoint <anchor>.pt \
  --model-residual-blocks 4 --model-event-window 128 \
  --model-privileged-critic --model-aux-heads \
  --event-history-window 128 --duplicate-seats --online-episodes 1500 \
  --start-seed 1070000 --match-mode chongci --device cuda \
  --report-output /root/fh-mahjong-runs/deep16-rezero/confirm-anchor.json

fh-mj-compare /root/fh-mahjong-runs/deep16-rezero/confirm-candidate.json \
  /root/fh-mahjong-runs/deep16-rezero/confirm-anchor.json
```

Promotion requires BOTH:
- paired placement clustered 95% CI clears 0 (lower bound > 0), AND
- `large_loss_rate(candidate) <= large_loss_rate(anchor) + 0.015` absolute.

No optional stopping; do not gate another checkpoint on this window.

## 9. Checkpoint retention

Keep the pre-registered screening checkpoints (25/50/75/100/125/150/175/
200/225/250/260) plus the final selected checkpoint; prune the rest after
the lap completes. `train_state.pt` (written every 5 iterations) can be
deleted once the lap is confirmed or nulled — it exists only to survive
restarts mid-lap.

## 10. Alpha telemetry (protocol null signal, not a bug)

`history.json` per-iteration rows log mean `|alpha|` across the 12 growth
blocks. If alphas hug 0 at the end of the lap (growth stalled — the shared
learning rate never pushed the new blocks away from identity), that is
itself the RESULT: a protocol null, not evidence the added capacity cannot
help. Record it plainly in the progress doc.

A null result here means THIS PROTOCOL failed, not that there is a capacity
ceiling. If it nulls, the next menu item is GRU widening (see the scale
roadmap memory), not another depth attempt with a different warm-start.

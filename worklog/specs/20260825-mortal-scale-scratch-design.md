# Mortal-scale from-scratch experiment — design

**Date:** 2026-08-25 · **Branch:** `experiment/mortal-scale-scratch` · **Status:** DRAFT — awaiting
user review, then the mandatory Codex consult (`01a0147d` thread) before any code lands or trains.

## 1. Question

Does network scale still help under this pipeline when the net is **trained from scratch at
Mortal-like size with proportionally more data**, rather than grown out of the champion?

Every prior capacity lap warm-started from `anchor075` (96 ch × 4 blocks, 2.26 M params) and
nulled or failed confirmation: deep8, deep4+12 ReZero (alphas never engaged), gru-width
(+0.0170 → collapsed), ds960 3× data (+0.0175, CI crosses 0). The 2026-08-20 ruling closed the
scale campaign and listed *scratch training* as the one untried lever (priority 5). This spec is
the fresh authorization for exactly that lever, granted by the user on 2026-08-25.

Suphx (256 ch × 50 blocks) and Mortal (192 ch × ~40 1-D blocks) both reached their size through a
**supervised stage on human logs** before RL. Fenghua has no human logs; the lineage's own root was
BC on heuristic-bot trajectories → IQL → PPO. This design reproduces that shape: BC on heuristic
data as the supervised stage, then PPO self-play.

## 2. Two findings that shape the design

1. **3×3 convs on a 42×1 plane waste two-thirds of every kernel.** Measured with
   `PolicyValueNet(EnvConfig(), ModelConfig(channels, residual_blocks))`:

   | channels × blocks | params (3×3 kernels) |
   |---|---|
   | 96 × 4 (champion) | 2.26 M |
   | 192 × 24 | 18.60 M |
   | 192 × 40 | 29.22 M |
   | 256 × 50 | 62.38 M |

   Mortal uses 1-D convs. With `(3,1)` kernels, 192 × 24 ≈ 6.3 M (~2.8× champion), which is the
   size point the user chose ("Mortal-like, ~5 M"). The kernel shape becomes a config field.
2. **There is no scratch path.** `fh-mj-train-b2b` errors without `--champion` (or a resume
   state); `fh-mj-train-bc` hard-codes `ModelConfig()` and a plain `PolicyValueNet` with no
   event/privileged/aux modules. Both need small, additive changes.

## 3. Arms

| arm | trunk | init | purpose |
|---|---|---|---|
| **big** | 192 ch × 24 blocks, kernel (3,1), channel_attention as champion | scratch: BC → PPO | the hypothesis |
| **control** | 96 ch × 4 blocks, kernel (3,1) | scratch: BC → PPO, identical recipe | attributes any delta to *scale* rather than to the scratch/BC recipe |
| comparator | `anchor075` (existing) | — | current champion; the bar to beat |

Both arms keep every B2b module (event GRU 128, privileged critic, aux heads) at the champion's
dims — only the plane trunk changes. The control uses `(3,1)` kernels too so the *only* difference
between arms is width/depth. (`(3,1)` vs `(3,3)` at 96 × 4 is a recipe change relative to the
champion; it is deliberately absorbed by the control, not by the hypothesis arm.)

GPU-serial: **control runs first** (cheap, ~1/3 the compute) so its curve is in hand before the
big lap is committed. If the control from scratch cannot get within −0.06 of `anchor075` by the
end of its budget, the *recipe* is the problem — stop and consult before spending the big lap.

## 4. Code changes (three, all additive, all default-preserving)

### 4.1 `ModelConfig.kernel_width: int = 3`
- `ai/src/fh_mahjong_ai/config.py`: new field, validated ∈ {1, 3}. Default 3 ⇒ every existing
  checkpoint and every existing test constructs byte-identical modules.
- `model.py`: `build_plane_scalar_encoders` stem, `ResidualBlock`, `ReZeroResidualBlock` take
  `kernel_size=(3, kernel_width), padding=(1, kernel_width // 2)`.
- `_shape_inferred_fields`: `kernel_width = state_dict["plane_stem.0.weight"].shape[3]` — so
  `infer_model_config`, serving (`fh-mj-serve-policy`), `fh-mj-evaluate`, and `fh-mj-compare` load
  the new nets with no further change. Also add to `model_config_args.py` (`--model-kernel-width`)
  and to `model_config_params()` per the `ai/CLAUDE.md` rule.
- Tests: default config state_dict keys+shapes unchanged; `kernel_width=1` forward shape; round-trip
  through `infer_model_config`; validation rejects 2.

### 4.2 `fh-mj-train-b2b --scratch [--init-from-bc <ckpt>]`
- `--scratch` is mutually exclusive with `--champion`, `--model-growth-blocks`,
  `--widen-event-hidden`; `--resume-from-state` still wins over both.
- Builds `PolicyValueNet(env, model_config)` with default PyTorch init (no surgery, no parity
  check — there is no anchor to be parity with). Metadata pins the full `ModelConfig` exactly as
  the warm-start path does, plus `init: "scratch"` and the BC checkpoint sha if given.
- `--init-from-bc`: strict-by-name load of the BC checkpoint's `plane_stem.*`, `plane_blocks.*`,
  `plane_head.*`, `scalar_encoder.*`, `trunk.*`, `policy_head.*`; every other module (event
  encoder, privileged critic, value/aux/risk heads, q_head) stays at random init. Any BC key that
  does not match a model key by name+shape is a hard error, not a warning — silent partial loads
  are this lane's known failure mode.
- Resume/train-state lineage, telemetry, `--train-state-every`: unchanged code paths.
- Tests: scratch build metadata; flag exclusivity; init-from-bc loads exactly the listed prefixes
  (and nothing else) and errors on a shape mismatch.

### 4.3 `fh-mj-train-bc` accepts model-config flags
- Add `add_model_config_args` / `model_config_from_args` (already used by train-b2b) so the BC
  stage can build the same trunk the PPO stage will load. Event/privileged/aux modules are
  constructed but receive **no gradient** in BC (policy cross-entropy only, empty event window
  — verify at implementation time that the B2b forward accepts an empty event batch; if not, BC
  builds the net with those flags off and 4.2's loader ignores their absence).
- Tests: BC on a tiny heuristic dataset with `--model-kernel-width 1 --model-residual-blocks 2`
  writes a checkpoint that 4.2's `--init-from-bc` accepts.

Nothing in `internal/`, the proto, or the Go bridge changes. Serving needs no code change
(config is inferred from shapes + metadata).

## 5. Protocol (to be ratified in the consult; numbers are the proposal)

### 5.1 Stage 1 — BC (both arms)
- Data: `fh-mj-generate-data` heuristic trajectories, one dataset shared by both arms
  (size: match the lineage's original BC dataset; exact count fixed at consult after measuring
  generation throughput). Seed range fresh and recorded.
- Train to validation-loss plateau with the existing `--validation-fraction`; report top-1 policy
  accuracy per arm. The big net is *expected* to fit heuristic play better; that is not the result,
  just the starting point.

### 5.2 Stage 2 — PPO self-play (per arm, sequential)
- Launch = the ds960 runbook command with `--scratch --init-from-bc`, `--model-*` flags for the
  arm, **and matches/iter scaled by measured parameter ratio** relative to the champion's 320
  (control: 320 × ratio(control/champion); big: 320 × ratio(big/champion), rounded to a multiple
  of the dispatch chunk). Minibatch scales with matches/iter so optimizer steps/iter stay ≈ equal
  (the ds960 coupling rule).
- Everything else frozen at the champion recipe: lr 2e-5, entropy 0, ppo_epochs 2, gamma 0.99,
  chongci, 10 workers, cgroup guards from the ds960 runbook.
- Iterations: 150 nominal. Scratch curves start far below the anchor, so the kill rule is
  **slope-based**, not level-based: kill at iter 100 iff the iter-75→100 screening delta is ≤ 0
  *and* iter 100 < −0.20 vs `anchor075`. (Ratify at consult.)
- Screenings at 25/50/75/100/125/150 vs regenerated `anchor075` on a fresh window; confirmation of
  the pre-registered best on a second fresh window, 1500 paired seeds × 4 duplicate seats,
  `fh-mj-compare` mandatory, gate = clustered CI95 > 0 AND large_loss ≤ comparator + 0.015.
- Seed ranges: everything ≥ 1,300,000 (used so far: 400000–700000 bases, 910000+, 1070000+,
  1110000+, 1150000+, 1190000+ windows). Exact allocation in the runbook.

### 5.3 Readouts
- Primary: big-arm confirmation delta vs `anchor075`.
- Secondary (the scale question proper): big-arm vs control-arm at matched *optimizer steps*, and
  the two screening curves overlaid. "Scale works" = big beats control with CI clear of 0; "scale
  is not the lever" = both arms land together.
- Memory/throughput: bench the big arm's full collect+PPO cycle before the lap (ds960 Amendment 2
  procedure); if it does not fit the 36 GiB gate at 10 workers, stop and consult — do not shrink
  the net silently.

## 6. Risks and known traps
- Scratch PPO was called infeasible in the 2026-06-24 spec; the BC stage is the mitigation, and the
  control arm is the detector if it is not enough.
- Throughput: collection inference is per-step; a ~3× net on the 4090 may push a 27-min iteration
  (ds960 at 960 matches) well past an hour. Bench first; the budget is set from the bench.
- `infer_model_config` must never guess `kernel_width` from anything but the stem weight shape.
- Pool wrapper drops `round_outcome`; gamma/truncation/loader invariants untouched — nothing here
  goes near them, keep it that way.
- Two Codex threads exist (`019f49e8` user-designated, `01a0147d` holds the ds960 lineage). Use
  **one**; this spec proposes `01a0147d` since it ruled the closure this experiment reopens.

## 7. Out of scope
- Suphx-scale (256 × 50): infeasible on the box; revisit only if the big arm confirms.
- Transformer/attention trunks, oracle-guided scratch, human data groundwork, any change to the
  reward, observation, or action catalog.
- Promoting or deploying either arm — a confirmed win returns to consult for a promotion decision
  under the existing B2c serving protocol.

## 8. Deliverables
1. This spec (reviewed) → implementation plan via `writing-plans`.
2. PR: code changes §4 with tests, CI gates green, `ai/CLAUDE.md` updated.
3. Runbook `worklog/plans/20260825-mortal-scale-scratch-runbook.md` + live status file
   `worklog/rl-experiment/mortal-scale-scratch-status.md` (created when the lap launches).
4. Consult ruling recorded as Amendment 1 here before anything trains.

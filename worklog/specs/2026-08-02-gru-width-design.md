# GRU-Width Lap: Event-Encoder Scaling via Identity-Masked Widening — Design

**Date:** 2026-08-02
**Branch:** `claude/gru-width` (off main)
**Status:** Design ratified via Codex consult (canonical session, 2026-08-02),
following the deep16 ReZero recruitment null. ONE intervention: event-encoder
width. Trunk, aux heads, and every recipe knob stay fixed.

## Rationale

Both confirmed champion-line wins came from temporal representation; generic
trunk depth has now nulled twice (deep8 pre-events; deep4+12-rezero with
events, alphas never recruited). The ratified menu's next lever scales the
SEQUENCE CORE: double the event GRU hidden width (128 -> 256) while keeping
the trunk's 128-dim event-feature interface fixed via an identity-masked
projection, so step-zero behavior is EXACTLY the anchor's.

## 1. Model (`config.py`, `model.py`)

- `ModelConfig` gains `event_output_dim: int = 0` — 0 means "equal to
  `event_hidden_dim`, no projection module" (dormant default: state_dict
  byte-identical to today). When `event_output_dim > 0` and
  `!= event_hidden_dim`, `EventEncoder` appends
  `self.output_proj = nn.Linear(event_hidden_dim, event_output_dim)` and the
  encoder's output dim (consumed by the trunk/value-head builders via the
  existing event-feature width) becomes `event_output_dim`. Bounds: same
  `MAX_HIDDEN_DIM` validation as other dims; also validate
  `event_output_dim == 0 or event_window > 0` is NOT required (config-level
  orthogonality; a projection without events is pointless but harmless —
  keep validation minimal, bounds only).
- Key namespace: `event_encoder.output_proj.{weight,bias}` — new keys only
  when the field is set (B2b dormancy pattern, proven by marshal test).
- Everywhere the model derives the event-feature width (trunk input columns,
  privileged value head input, shape inference), the effective width becomes
  `event_output_dim or event_hidden_dim` — grep for `event_hidden_dim` uses
  in model.py and update the derivations symmetrically.

## 2. Widening warm-start (`oracle.py`)

`widen_event_gru(anchor_checkpoint: Path, new_hidden_dim: int,
env_config: EnvConfig | None, device) -> PolicyValueNet`:

- Anchor must be a complete post-B2b checkpoint (metadata.model_config
  present) with `event_output_dim == 0` and `event_hidden_dim == H_old`
  (128); target config: `event_hidden_dim = new_hidden_dim` (256),
  `event_output_dim = H_old` (128). Reject anchors already widened/projected,
  reject `new_hidden_dim <= H_old`, env cross-check like `grow_b2b_model`.
- Weight surgery (step-zero exactness is the invariant; the parity test is
  the enforcement):
  - Embedding + side_proj: copied verbatim.
  - GRU `weight_ih_l0` (shape [3*H, E]): old-unit rows (each of the 3 gates'
    first H_old rows) copied; new-unit rows normally initialized.
  - GRU `weight_hh_l0` (shape [3*H, H]): per gate, the [old, old] block is
    copied; the [old-gate-rows, new-hidden-cols] block is ZEROED (old units
    must not see new-unit activations, or step-zero drifts); [new, old] and
    [new, new] blocks normally initialized (new-unit dynamics are free —
    their output is masked by the projection).
  - GRU biases (`bias_ih_l0`, `bias_hh_l0`): old-gate entries copied; new
    entries normally initialized.
  - `output_proj`: weight `[I_{H_old} | 0]` (identity over old units, zeros
    over new), bias zero.
  - Every non-event-encoder tensor: copied verbatim (strict; any
    missing/skipped non-encoder key raises).
- Step-zero parity (binding, tested): event features, policy logits, value,
  Q, aux outputs, and greedy actions EXACTLY equal the anchor's on random
  obs/event batches (torch.equal). This test is what catches any surgery
  mistake, including a missed old<-new zero block.
- `fh-mj-train-b2b` gains `--widen-event-hidden N` (default 0 = off;
  mutually exclusive with `--model-growth-blocks > 0` in one run — reject
  both set). Routing mirrors the growth path; checkpoints save the complete
  ModelConfig (event_hidden_dim=256, event_output_dim=128) via the existing
  metadata path.

## 3. Loading / serving / eval

- `infer_model_config`: derive `event_output_dim` presence/dims from
  `event_encoder.output_proj.weight` shape ([out, hidden]); extend the
  pre-construction derivable-fields check (claim vs derived); fail closed on
  projection keys without usable metadata (existing pattern). Legacy
  checkpoints without the field -> 0.
- `fh-mj-evaluate` gains `--model-event-output-dim` beside the existing
  event flags (and `--model-event-hidden-dim` if not already exposed —
  check model_config_args.py; add whichever is missing).
- Serving needs zero further changes (metadata-authoritative); provenance
  (report/MLflow) picks the new field up via model_config_params — verify
  it enumerates dataclass fields dynamically or add explicitly.

## 4. Runbook (gate parameters, ratified)

- Anchor: restart-iter075 (unchanged; sha ce9d867f...). 10 workers
  (memory-proven; deep16's 20-worker OOM lesson).
- Budget: `iterations = ceil_to_5(150 * candidate_params / anchor_params)`
  with the MEASURED ratio (expected ~1.08x -> 165) × 320 matches/iter.
- Preflight on the box: state-dict + step-zero parity via widen_event_gru.
- Screenings: 25/50/75/100/125/150/<final> vs regenerated restart-iter075
  comparator on 910000+ (regenerate — the bridge has moved since deep16's
  comparator). Candidate eval flags include the new dims.
- Kill rule: at 100 only, both 75 and 100 < -0.06.
- No extension; selection = best eligible screening checkpoint (protocol
  UNCHANGED per consult — sensitivity over false-launch cost).
- Confirmation: fresh 1110000+ window, 1500 seeds/side, paired CI > 0 AND
  large_loss <= anchor + 0.015.
- Resumable state every 5 iters; PYTHONUNBUFFERED launch; orchestrator +
  screening chain live under /root/fh-mahjong-runs/ (reboot-safe paths).

## Out of scope

Trunk changes, transformer encoders, window changes, aux weights,
matches-per-iter, deployment (B2c rollout proceeds independently with
restart-iter075).

## Risks

- Missed old<-new recurrent zeroing would silently break function
  preservation — caught deterministically by the step-zero parity test.
- Effective-width derivations scattered in model.py — the shape cross-check
  and full test suite guard inconsistencies.
- Memory: +~1MB params; collection profile unchanged; 10 workers safe.

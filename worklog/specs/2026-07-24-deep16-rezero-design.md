# deep4+12-rezero: Capacity Growth via Function-Preserving ReZero Blocks — Design

**Date:** 2026-07-24
**Branch:** `claude/deep16-rezero` (off main @ 186c300)
**Status:** Design ratified via Codex consult (canonical session, 2026-07-24); user directive: "test networks larger than deep8".

## Context

Both confirmed champion-line wins came from temporal representation (B2b) at
96ch/4 blocks; the pre-B2b deep8 test (trunk-only, no events) nulled at 2x
cost. This experiment tests whether capacity pays *on top of* the event
representation, with a defensible warm start. It is ONE architectural
intervention: trunk depth. The GRU, aux heads, and every recipe knob stay
fixed.

**Why ReZero:** `ResidualBlock.forward` is `GELU(x + attn(F(x)))`
(model.py:236) — zeroing a new block's weights yields `GELU(x)`, NOT `x`, so
classic zero-init identity surgery is impossible. A ReZero growth block
`x + alpha * F(x)` with scalar `alpha = 0` is exactly the identity at step 0.

## 1. Model (`ai/src/fh_mahjong_ai/model.py`, `config.py`)

- `ModelConfig` gains `growth_blocks: int = 0` (bounded `[0, MAX_RESIDUAL_BLOCKS]`
  in `__post_init__`, same DoS rationale as `residual_blocks`; default 0 =>
  state_dict identical to today — the B2b dormancy pattern).
- New `ReZeroResidualBlock(channels, channel_attention, attention_ratio)`:
  same two-conv `F` (and optional attention) as `ResidualBlock`, but
  `forward = x + self.alpha * self.channel_attention(self.layers(x))` with
  `self.alpha = nn.Parameter(torch.zeros(()))`. NO trailing GELU (pure
  identity at alpha=0 is the invariant).
- `PolicyValueNet`: growth blocks live in a SEPARATE module attribute
  (`self.growth = nn.Sequential(...)` applied immediately after the legacy
  residual stack, before pooling/flatten) so the legacy key namespace is
  byte-identical and anchor tensors load verbatim. Naming: `growth.{i}.*`,
  `growth.{i}.alpha`.

## 2. Growth warm-start (`ai/src/fh_mahjong_ai/oracle.py`)

- `grow_b2b_model(anchor_checkpoint: Path, growth_blocks: int, device) ->
  PolicyValueNet`: loads the anchor's complete `metadata.model_config`
  (fail-closed if absent — anchors are post-B2b and always carry it), builds
  the same config with `growth_blocks=N`, copies EVERY anchor tensor exactly
  (strict load of the anchor keys; only `growth.*` keys are new), leaves
  alphas at zero.
- `fh-mj-train-b2b` gains `--model-growth-blocks N` (default 0). When N>0 the
  `--champion` checkpoint must be a B2b-shaped anchor (event/priv/aux) and the
  builder routes through `grow_b2b_model`; the existing 39ch surgery path is
  untouched for N=0.
- **Step-zero parity (binding invariant, tested):** for random obs/event
  batches, the grown net's policy logits, value, Q outputs, aux outputs
  (belief/dealin/rank), and greedy actions are EXACTLY equal (torch.equal /
  argmax identity) to the anchor net's.

## 3. Metadata / loading / serving

- `model_config_metadata` (dataclass asdict) picks up `growth_blocks`
  automatically; `infer_model_config`:
  - derives the growth-block count from state-dict keys (`growth.{i}.alpha`
    presence, contiguous indices) in the pre-construction derivable-field
    check (mismatch vs metadata claim -> reject BEFORE construction);
  - legacy/b2b-metadata checkpoints without `growth_blocks` default 0;
  - `growth.*` keys with NO usable metadata -> fail closed (same policy as
    B2b keys).
- Serving needs no other change (B2c loading is metadata-authoritative); the
  shape cross-check covers growth tensors; `/healthz` architecture summary
  reflects the field via metadata.
- `fh-mj-evaluate` gains `--model-growth-blocks` for explicit-flag paths.

## 4. Trainer: resumable state (ratified gate requirement)

- `fh-mj-train-b2b` saves `train_state.pt` in the checkpoint dir every 5
  iterations (`--train-state-every 5` default when growth_blocks>0; flag
  available for all runs): model + optimizer + torch/numpy/python RNG states +
  next iteration index + config echo.
- `--resume-from-state PATH` restores all of it and continues to
  `--iterations`. Resumed runs must be bit-compatible in intent, not proven
  bit-identical (CUDA nondeterminism) — the state file exists so a multi-day
  lap survives box restarts, documented as such.

## 5. Worker benchmark harness (sequencing step 3)

- `fh-mj-collect-bench --champion CKPT [--model-growth-blocks N] --workers
  5,10,20 --matches 320 --base-seed S --match-mode chongci --device cuda`:
  runs COLLECTION ONLY per worker count with fixed weights; canonicalizes
  emission by match index; reports per-config wall-clock and a semantic
  digest: sha256 over (per-match seed list, obs-row bytes, action ids,
  rewards, dealin/rank labels, round-outcome telemetry) in match order.
  Digests must be IDENTICAL across worker counts (per-match seeding makes
  trajectories worker-count-independent; the harness proves it).
- Adoption rule (runbook, not code): pick the fastest worker count whose
  digest matches the 5-worker reference exactly. Pool port is out of scope
  for this spec (separate decision if projected lap > 7 days).

## 6. Runbook (doc deliverable, post-merge)

Ratified gate parameters:
- Anchor: r2 winner (or restart-iter075 if r2 fails); frozen path+sha.
- Budget: 260 iterations x 320 matches/iter (measured 1.73x param ratio),
  recipe otherwise byte-identical to the ratified champion recipe.
- Preflight: state-dict + step-zero parity proof on the box before launch.
- Screening: iters 25/50/75/100/125/150/175/200/225/250/260 vs regenerated
  anchor comparator on 910000+ (120 seeds, strict).
- Kill rule: ONLY at iter 100, if BOTH iter-75 and iter-100 deltas < -0.06.
- Hard stop at 260; no extension. Freeze best healthy pre-registered
  checkpoint; no substitution.
- Confirmation: fresh 1070000+ window, 1500 seeds/side, back-to-back, same
  bridge; paired placement CI clears 0 AND large_loss <= anchor + 0.015.
- Checkpoint retention: keep screening checkpoints + final; prune the rest
  after completion. train_state.pt every 5 iters.
- A null result = this protocol failed; NOT evidence of a capacity ceiling.
  If it nulls, next menu item is GRU widening (see scale roadmap memory).

## Out of scope

GoEnvPool port (separate decision), GRU widening, matches-per-iter changes,
transformer encoders, aux-weight changes, deployment of any winner (B2c
runbook governs that, with growth-aware metadata already handled by §3).

## Risks

- ReZero alpha learning rate coupling: alphas train with the shared lr; if
  growth stalls (alphas hug 0) that is a RESULT (protocol null), not a bug —
  telemetry logs mean |alpha| per iteration so we can see it.
- Worker-count nondeterminism (e.g. shared RNG in collection) would break the
  digest equality — the bench harness exists precisely to catch this before
  adopting more workers.
- Longer lap + shared box: screenings serialize behind training; the 5-iter
  state file bounds restart loss.

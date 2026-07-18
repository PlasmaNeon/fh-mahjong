# Spec B2b: Event Encoder + Privileged Critic + Auxiliaries — Training — Design

**Date:** 2026-07-16
**Branch:** `claude/spec-b2b-training` (off main @ ae29337)
**Status:** Approved design → implementation plan next

## Context

The training half of Spec B — the spec where multi-day 4090 compute gets
committed. Prerequisites all merged: Spec A (#166, fh-mj-compare gate +
seed windows), B1 (#169, event capture + codec), B2a (#172, search-honest
events at scale through every collection path). Spec C (categorical
rank/bust) rides here as an auxiliary head. Everything is config-gated and
dormant by default; nothing changes for existing checkpoints until a run
enables the new flags.

Decisions settled with the user:
- **Serving integration is DEFERRED to B2c**, executed only on promotion.
  B2b's deliverable is a gated candidate, evaluated through the Go bridge
  (which already carries events end-to-end).
- **Run budget: staged ~150 iters with kill criteria** (details in §6).
- Warm-start from champion iter275 with zero-init new paths (settled in the
  Spec B brainstorm; scratch only as fallback if warm-start stalls).

## 1. Model (`ai/src/fh_mahjong_ai/model.py`)

`ModelConfig` gains (all default-off/zero → the constructed module graph and
`state_dict` are IDENTICAL to today's, so `load_checkpoint` strict-compat
holds for every existing checkpoint):

```python
event_window: int = 0          # 0 = no event encoder (dormant)
event_embed_dim: int = 32
event_hidden_dim: int = 128
privileged_critic: bool = False
aux_heads: bool = False
```

### EventEncoder (new module, created only when `event_window > 0`)

- Input: `events` uint32 `[B, W]` (raw packed codec values) + `event_lengths`
  int32 `[B]`. The model decodes bits with torch ops (cheap, vectorized):
  token = `(type*4 + rel_seat)*64 + face` (= `events.py event_to_token`,
  range [0, 2048)), plus a 6-dim side feature per event
  (tsumogiri bit, haitei bit, rel_from one-hot 4).
- `nn.Embedding(2048, event_embed_dim)` + linear(6 → event_embed_dim) summed,
  then `nn.GRU(event_embed_dim, event_hidden_dim, batch_first=True)` over the
  PADDED sequence; the row feature is the GRU output gathered at index
  `length-1` (padded-with-mask, no pack_padded_sequence — simpler, no
  sort/unsort, fast at [B,128]). Rows with length 0 yield zeros.
- Fusion: `trunk` input dim grows to
  `plane_feature_dim + scalar_hidden_dim + event_hidden_dim`. Warm-start
  zero-inits the NEW trunk input columns, so the warm-started net's policy
  logits are exactly the champion's at step 0 (§5 test).

### Privileged critic (created only when `privileged_critic=True`)

- Collection runs `oracle_observation=True`: `RolloutBatch.planes` is 51ch.
- The POLICY path consumes `planes[:, :39]` only — the actor is
  information-legal by construction; the deployable artifact is the same
  net with the privileged/aux modules simply unused (no student-extraction
  step: the policy path never touches privileged weights).
- `privileged_encoder`: small conv stem over `planes[:, 39:51]` (12ch) →
  flatten → linear → GELU → 128 features, concatenated ONLY into the value
  head input (`trunk_hidden_dim + 128`). Variance reduction for GAE; policy
  and aux heads never see it.
- NOTE: the oracle-parity result from the oracle phases was about privileged
  POLICY inputs at inference. Privileged TRAINING targets/critics are a
  different mechanism (Tjong/ODMC precedent) — that distinction is the
  audit finding this spec tests.

### Auxiliary heads (created only when `aux_heads=True`; all read the PUBLIC shared trunk)

They predict hidden/hindsight quantities FROM public information — the
representation-shaping point. None feeds the policy head; all are
train-time only.

| head | output | target | loss |
|---|---|---|---|
| `belief_head` | `[B, 12, 42]` logits | the 12 oracle threshold planes (opponents' true hands) from `planes[:, 39:51]` | BCE |
| `dealin_head` | `[B, 1]` logit | 1 if THIS seat pays a ron in the hand containing this decision (hindsight) | BCE |
| `rank_head` | `[B, 5]` logits | terminal match result: rank 1-4 or busted (hindsight) — **Spec C** | CE |

Spec C posture: the GAE critic stays a scalar; the categorical head is
auxiliary (C-lite). A full categorical-critic replacement is a follow-up
ablation only if B2b underwhelms.

## 2. Data path (`ppo.py`, `oracle.py`)

- `RolloutBatch` gains `events: np.ndarray [N, W] uint32`,
  `event_lengths: np.ndarray [N] int32`, `dealin_labels: np.ndarray [N] float32`,
  `rank_labels: np.ndarray [N] int64` (−1 = no label, e.g. truncated match →
  masked out of the CE loss). All ride `_ROLLOUT_ARRAY_FIELDS` through
  concat/minibatching; `compute_gae` untouched (labels are per-row).
- `collect_selfplay_rollouts` (+ `ParallelSelfplayCollector` workers), the
  champion's process-collector path, 5 workers:
  - env config: `oracle_observation=True`, `event_history_window=128`;
    single-env bridges already surface `Observation.event_history` (B1).
  - Records the acted-on obs (51ch planes, scalars, mask) + its event row
    (tail-padded to W with length).
  - **Hindsight labels at episode assembly** (Python-side):
    - `dealin`: for each hand, if the round outcome is a ron paid by seat s
      (round outcome info from the env step info / reward decomposition —
      the collector already tracks round outcomes for metrics), every
      decision row of seat s in that hand gets 1, else 0.
    - `rank`: at match end, each seat's rows get its final placement 0-3,
      or 4 if busted; truncated matches get −1 (masked).
- `ppo_update`: loss = `ppo_policy + c_v·value + c_e·entropy +
  0.1·(belief_bce + dealin_bce + rank_ce)`. Fixed aux weight 0.1, no
  anneal (monitor; tune only with evidence). Metrics logged per-head.
- **No KL-to-champion**: warm-start + the PPO clip, watching `approx_kl`
  like every prior phase; add KL only if drift/collapse is actually
  observed (recorded as an explicit non-goal so nobody "helpfully" adds it).

## 3. Warm-start (`oracle.py` pattern)

`build_b2b_model(env_config, model_config, champion_checkpoint, device)`:
copy every tensor that exists in the champion; zero-init the new trunk
input columns (event slice); default-init the event encoder, privileged
encoder, and aux heads (their outputs don't perturb the policy: the event
path enters the trunk through zero columns, and privileged/aux paths don't
feed the policy head at all). Invariant test in §5.

## 4. Evaluation flags (`scripts/evaluate.py`, `evaluate.py`)

`fh-mj-evaluate` gains `--event-history-window N` (threads into EnvConfig →
bridge → the real deployable inference path: Go encode → packed events →
GRU) and builds the model via the existing model-config flags plus
`--model-event-window` / `--model-privileged-critic` etc. Spec A's
duplicate-seat reports persist evaluation config for fh-mj-compare parity
checks but do NOT yet include the window: add `event_history_window` to the
persisted report fields AND to `fh-mj-compare`'s `_COMPAT_KEYS` — a
window-on vs window-off run is a different protocol and must refuse to
compare as a strict gate.

## 5. Testing (all pre-merge, no training)

1. **Dormancy:** default `ModelConfig` builds a state_dict byte-identical
   in keys/shapes to today's; the champion checkpoint loads strict.
2. **Warm-start equivalence:** `build_b2b_model` output's policy logits on
   random (39ch-padded-to-51, scalars, mask, random events) == the
   champion's logits on the same 39ch obs (atol 1e-5) — events enter
   through zero columns, privileged/aux paths don't touch the policy.
3. **Event plumbing:** RolloutBatch fields survive concat + minibatch
   shuffling aligned with their rows; GRU gather-at-length correctness
   (hand-computed tiny GRU case); zero-length rows yield zeros.
4. **Hindsight labels:** synthetic episode fixtures — a hand ending in ron
   labels exactly the paying seat's rows of exactly that hand; rank labels
   match final placements; truncated matches → −1 and masked from CE.
5. **Aux losses:** finite, gradients flow to the trunk from each head;
   belief target slice == planes[:, 39:51].
6. **2-iter mock train:** train_selfplay_oracle-style loop with all flags
   on, mock bridge, writes checkpoints + history rows carrying the new
   metric keys.
7. Full suites; `fh-mj-evaluate --event-history-window` on mock.

## 6. Run protocol (post-merge runbook on the 4090; box is idle)

1. Rebuild bridge; warm-start from
   `/root/fh-mahjong-runs/deploy/selfplay-deep4-student-iter275-39ch.pt`.
2. Train: deep4 dims + `event_window=128`, `privileged_critic`, `aux_heads`;
   GRP placement reward (γ=1), lr 2e-5, entropy 0, ppo-epochs 2, chongci,
   5 workers, matches/iter as champion; **150 iters**, checkpoint every 5,
   MLflow on.
3. **Screening** every 25 iters: `fh-mj-evaluate --event-history-window 128`
   duplicate-seat vs the in-engine opponents on `--start-seed 910000`
   (120 seeds), compare vs the champion's fixed-encoder screening report
   (`/root/fh-mahjong-runs/spec-a/champion-fixed.json`) via `fh-mj-compare`.
4. **Kill rule:** at iter ≥ 50, if the paired screening delta vs champion is
   below −0.06 (champion-minus-CI), stop and diagnose (fallback posture:
   scratch run or aux-weight sweep — a NEW decision, not automatic).
5. **Promotion gate:** best screening checkpoint → confirmation window
   `--start-seed 950000`, 1500 seeds (~6h), both candidate and champion
   reports on the SAME window/bridge, verdict via `fh-mj-compare` (strict).
   Promote iff the paired delta clears 0 with the clustered CI (expected
   effect +0.04..+0.12 vs CI ±~0.03·√0.85).
6. On promotion: record in the progress note; **B2c spec** (serving
   integration: room passes `game.PublicEvents()` through the bot policy
   interface, /act payload + serve_policy gain events, review tool) before
   any deployment.

## Out of scope

- Serving/product integration (B2c, on promotion only).
- Full categorical-critic replacement (post-B2b ablation only if needed).
- Batched-collector event support in training (process collector suffices;
  pools already CARRY events per B2a if later wanted).
- KL-to-champion regularization (explicit non-goal absent observed drift).

## Risks

- Warm-start equilibrium disruption by aux gradients — bounded by the 0.1
  weight, screening cadence, and the iter-50 kill rule.
- Hindsight-label bugs silently mis-shaping representation — bounded by the
  synthetic-fixture tests (§5.4), the most bug-prone part of this spec.
- GRU throughput on 51ch+events rows — the 4090 is far from saturated at
  current batch sizes; if collection slows >2×, drop workers' window to 64
  as a measured fallback (config knob, no code change).

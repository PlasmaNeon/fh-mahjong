# ai/

> Python reinforcement learning package for Fenghua Mahjong.

## Overview

Go is the authoritative simulator; Python owns the model, data, checkpoints, training,
evaluation, and serving. A mock bridge covers smoke tests; real work uses the `ctypes` bridge to
the Go c-shared library (`cmd/rlbridge`).

Design: [`docs/ai-player.md`](../docs/ai-player.md). Measurement and promotion:
[`docs/ai-evaluation.md`](../docs/ai-evaluation.md). Results: [`docs/ai-findings.md`](../docs/ai-findings.md).
Per-module reference: [`MODULES.md`](MODULES.md).

## Commands

Always via uv — never plain `pip`/`python`:

```bash
uv sync --project ai --extra dev
uv run --project ai <command>
```

### Generate data
| Command | Purpose |
|---|---|
| `fh-mj-generate-data` | Heuristic trajectories → JSONL or sharded NumPy + manifest; `--learning-seat-rule seed-mod-4` keeps one seat per match |
| `fh-mj-generate-selfplay` | Mixed self-play (checkpoint/random/heuristic seats) |
| `fh-mj-convert-data` | JSONL → sharded NumPy replay storage |
| `fh-mj-generate-branch-counterfactuals` | Exact same-state legal-discard branch labels |
| `fh-mj-generate-sampled-branch-counterfactuals` | Greedy-vs-sampled branch pairs |
| `fh-mj-generate-targeted-branch-counterfactuals` | Branch labels at diagnostic-selected states |
| `fh-mj-build-paired-trace-action-ev-data` | Paired-trace divergences → action-EV NPZ schema |

### Train
| Command | Purpose |
|---|---|
| `fh-mj-train-bc` | Behavior cloning (the offline warm-start); accepts the shared `--model-*` flags including `--model-kernel-width` and `--model-trunk-rezero`; `--patience/--min-delta/--min-epochs` stop on validation cross-entropy and write `best.pt` |
| `fh-mj-train-awbc` | Advantage-weighted BC |
| `fh-mj-train-iql` | Discrete IQL (offline; the pre-PPO trainer) |
| `fh-mj-train-offline-q` | Conservative offline Q (experimental) |
| `fh-mj-train-global-ev` | Visible-state (or action-conditioned) global EV predictor |
| `fh-mj-train-pairwise-delta` | Direct paired-trace reward-delta predictor (diagnostic-only) |
| `fh-mj-train-branch-preference-policy` | Push exact branch labels into top-k proposals |
| `fh-mj-train-action-risk` | Action-conditioned large-loss risk heads |
| `fh-mj-train-ppo` | Online self-play PPO vs a frozen anchor |
| `fh-mj-train-oracle` | Phase-1 oracle (single-seat, perfect-information) |
| `fh-mj-train-selfplay-oracle` | Phase-2 self-play feature-dropout oracle |
| `fh-mj-train-b2b` | Spec B2b: event history + privileged critic + aux heads; `--scratch [--init-from-bc]` for random-init runs; `--head-lr/--head-lr-iters` for the two-group lr schedule; `--collector batched --pool-slots N` for env-pool collection; opt-in `--pool-pipeline-groups K` and `--trunk-dtype bfloat16` (batched on CUDA) for speed; `--suit-augment` (batched) collects each decision in a random suit-permuted view; `--suit-distill-coef β` (batched) adds β·KL toward the collection-time suit-averaged policy; `--lookahead-version 1` adds the 13 discard/call look-ahead planes (stem widened with zero columns, rejected-on-change at resume) |

### Evaluate and gate
| Command | Purpose |
|---|---|
| `fh-mj-evaluate` | Offline agreement and/or online live play; `--duplicate-seats` is the gate (the agent vs 3 heuristic bots); `--opponent-checkpoint` puts a frozen checkpoint in the other three seats instead (strong table); `--batched-eval-slots N` runs the greedy gate (heuristic or strong table) through the env pool with one batched forward per policy per round (`--symmetry-average suits` averages the policy over the 6 suit permutations, `faces` over all 72 face symmetries: suits × rank reversal × dragon permutations; `--ensemble-checkpoint` adds checkpoints to a log-probability-mean ensemble; `--opponent-sample-temperature T` makes strong-table opponents sample, batched only); look-ahead checkpoints (version from metadata) run only through the batched duplicate-seat path, vs the heuristic bots or a strong table; a v0 `--opponent-checkpoint` at a look-ahead table reads its native first 39 channels (`lookahead_adapter` in the `opponents` record) |
| `fh-mj-compare` | **Required for any promotion verdict** — seed-clustered paired diff; `--allow-window-mismatch` / `--allow-lookahead-mismatch` label a deliberate observation-protocol comparison (a report without `lookahead_version` reads as 0) |
| `fh-mj-benchmark` | Tenhou-style stat sheet vs heuristic bots, or vs a frozen checkpoint with `--opponent-checkpoint` (yardstick, NOT a gate); `--symmetry-average suits`, `--workers N`, or `--batched-eval-slots N` (env pool, one forward per policy per round) |
| `fh-mj-search-diagnostic` | Search-teacher diagnostic: 12 rules (uniform/belief re-deals × next-decision/hand horizon × margin z) vs the suit-averaged choice on true-state ground truth at contested discards; descriptive, spends screening seeds 910,000+ |
| `fh-mj-placement-calibrate` | Stage-0 λ calibration for terminal placement bonus; returns λ = 0.5·σ_R/σ_V on frozen 320-match anchor collection; fails closed on truncation and scale gates (RMS ≤1.35, |p99| ≤1.50, critic MSE ≤2.00); never adjusts λ |
| `fh-mj-evaluate-risk-guarded` | Action-risk checkpoint as a guard around an anchor |
| `fh-mj-reward-calibration` | Q/value calibration vs discounted terminal payout |

### Serve
| Command | Purpose |
|---|---|
| `fh-mj-serve-policy` | JSON HTTP policy server (`/act`, `/evaluate`, `/healthz`, `/reload`, `/warmup`); `--symmetry-average suits` serves the suit-averaged policy; refuses look-ahead checkpoints (`lookahead_version > 0`) at startup and reload |
| `fh-mj-reload-policy` | Hot-swap or inspect a running server's checkpoint (no torch import; starts instantly) |
| `fh-mj-serving-parity` | **Hard promotion gate**: eval-path vs serving-path action parity |
| `fh-mj-serving-smoke` | Load a manifest checkpoint and step a bridge for legality |

### Diagnose and profile
| Command | Purpose |
|---|---|
| `fh-mj-dataset-diagnostics` | Dataset coverage before training |
| `fh-mj-replay-policy-diagnostics` | Anchor vs candidate vs stored actions on existing data |
| `fh-mj-paired-trace` | Paired checkpoint traces, first-divergence contexts |
| `fh-mj-paired-trace-q-diagnostics` | Does Q rank preferred above avoided on divergences? |
| `fh-mj-branch-cf-calibration` | Preferred-action rates on exact branch shards |
| `fh-mj-branch-cf-diagnostics` | Branch-CF failure slices |
| `fh-mj-branch-cf-guard-diagnostics` | Guard preflight against exact branch labels |
| `fh-mj-targeted-branch-cf-diagnostics` | Targeted branch proposal quality |
| `fh-mj-global-ev-diagnostics` | Score paired divergences with a frozen global EV model |
| `fh-mj-action-ev-branch-cf-calibration` | Action-EV checkpoint vs exact branch labels |
| `fh-mj-export-scratch-init` | Write the step-zero `--scratch --init-from-bc` net as a gated checkpoint, for benching that initialization |
| `fh-mj-collect-bench` | Worker-count (`--workers`) or pool-slot (`--collector batched --pool-slots`) benchmark; digest-gated exact-semantics proof. `--preflight` decides whether a throughput target is arithmetically reachable before the sweep is booked |
| `fh-mj-collect-profile` | Measurement-only memory profile of collect + update |
| `fh-mj-selfplay-loop` | N CI-gated self-play iterations, resumable |
| `fh-mj-pipeline` | generate → train → evaluate in one command |
| `fh-mj-selfplay-smoke` | Mock-bridge end-to-end smoke |

### No console entry point

These four are real tools but are **not** in `[project.scripts]` — run them as modules:

```bash
uv run --project ai python -m fh_mahjong_ai.scripts.evaluate_q_guarded
uv run --project ai python -m fh_mahjong_ai.scripts.evaluate_tail_constrained
uv run --project ai python -m fh_mahjong_ai.scripts.extract_near_state_discards
uv run --project ai python -m fh_mahjong_ai.scripts.build_counterfactual_risk_data
```

## Architecture

```
Go c-shared lib  →  bridge.py / envpool.py  →  env.py       ← authoritative simulator
                        (ctypes, protobuf)      searchpool.py
                                ↓
   collectors: train_b2b.py (ParallelB2bCollector), batched_b2b.py (env pool),
               oracle.py, parallel_rollouts.py, batched_selfplay.py, offline_trainers.py
                                ↓
   storage.py (sharded NPZ + manifest)  ↔  buffer.py / streaming_buffer.py
                                ↓
   trainers: offline_trainers.py (BC/AWBC/IQL/offline-Q), ppo.py, ach.py,
             oracle.py, train_b2b.py (+ train_state.py for crash resume)
                                ↓
   checkpoints  →  serving.py  →  scripts/serve_policy.py  →  Go bot seat
                        ↓
   evaluate.py (duplicate-seat gate)  →  scripts/compare_reports.py
```

Go is the final legality authority at every stage: Python returns an `action_id`, Go decodes it against the current legal set before anything mutates game state.

### Campaign vocabulary

`MODULES.md` tags entries with the lap that introduced them. These are labels, not separate
code paths:

- **B2b** — event history + privileged critic + auxiliary heads, warm-started from the 39ch champion.
- **deep16-rezero** — width growth by stacking dormant ReZero residual blocks.
- **gru-width** — widening the event GRU in place via an identity-masked projection.
- **data-scale-960** — the 960-match scaling work: dispatch chunking, memory profiling, minibatch device transfer.
- **mortal-scale-scratch** — BC → PPO from random init: `kernel_width`, `trunk_rezero` (required for deep trunks; a plain 24-block stack does not train), BC early stopping, `--learning-seat-rule seed-mod-4`, `--scratch [--init-from-bc]` with the two-group lr schedule and the step-zero transfer gate.
- **Spec B2c** — serving: metadata-authoritative architecture recovery and the event wire contract.
- **batched-b2b-collector** — `batched_b2b.py`: B2b rollouts through one env pool with one batched forward per round.
- **suit symmetry / look-ahead** — `suit_symmetry.py` (averaging, augmentation, distillation) and the `lookahead_version` planes.

## Key Files

> **Per-module detail lives in [MODULES.md](MODULES.md)** — one entry per module,
> grouped by role, with the design rationale and failure modes.
> Open it when you are about to touch a specific module.

Quick map of what is where:

| Group | Modules |
|---|---|
| Contracts and configuration | `config.py`, `types.py`, `action_catalog.py`, `events.py` |
| Bridge and environment | `bridge.py`, `env.py`, `envpool.py`, `searchpool.py` |
| Model | `model.py` |
| Training | `ppo.py`, `ach.py`, `oracle.py`, `train_b2b.py`, `train_state.py`, `offline_trainers.py`, `batched_selfplay.py`, `batched_b2b.py`, `parallel_rollouts.py`, `selfplay_loop.py` |
| Data and storage | `data.py`, `buffer.py`, `streaming_buffer.py`, `storage.py`, `checkpoint_manifest.py` |
| Policies, search, serving | `policies.py`, `search.py`, `serving.py` |
| Evaluation and diagnostics | `evaluate.py`, `hand_stats.py`, `route_study.py`, `placement_bonus*.py`, `reward_calibration.py`, `global_ev*.py`, `paired_trace*.py`, `branch_c*.py`, `near_state_counterfactuals.py`, `risk_filter.py` |
| Infrastructure | `mlflow_tracking.py`, `memprobe.py`, `fdlimit.py`, `generated/proto/` |
| Scripts | `scripts/` — see the Commands section above for the CLI each one backs |
| Deployment | `checkpoints/deploy/`, `Dockerfile.compose`, `Dockerfile.deploy` |

## Gotchas

### Environment and tooling
- **Use uv for everything**: `uv sync --project ai --extra dev`, then `uv run --project ai ...`.
- The package requires CPython 3.12 (`ai/.python-version`).
- Multi-worker collection needs a raised fd limit; the training/bench/profile CLIs call
  `fdlimit.raise_file_descriptor_limit`.
- CI does not run the Python suite: `uv run --project ai pytest ai/tests` before merging.

### Go is the authority
- `fh-mj-serve-policy` is an inference boundary only; Go decodes and validates every returned
  `action_id`.
- Action selection assumes the fixed 204-action catalog from the Go bridge.
- `events.py` mirrors `internal/rl/eventcodec.go` — **change both or neither** (shared golden
  vector in `tests/test_events.py`).

### Observations and checkpoints
- `EnvConfig` defaults match the bridge: `39 x 42 x 1` planes, 58 scalars, 204 actions. B2b
  collection uses 51 channels (39 public + 12 privileged); **the policy path reads only the first
  39**.
- Legacy 42-scalar checkpoints are zero-padded to 58 in `storage.load_checkpoint()`.
- `event_window` is **not recoverable from tensor shapes**: `infer_model_config` needs
  `metadata["model_config"]` (or the older `metadata["b2b"]` block) and raises without it.
  `kernel_width` and `trunk_rezero` are shape-inferred, and metadata that disagrees is rejected.
- A new `ModelConfig` field must be added by hand to `model_config_args.model_config_params()`.
- BC trains with `events=None`; an event-enabled net's BC validation runs on zero events
  (`validation_events: "zeroed"`) and is not comparable to an event-fed evaluation.
- `fh-mj-train-bc --patience N` stops on validation `mean_cross_entropy` and copies the best epoch
  to `best.pt`; it requires a validation split.
- `fh-mj-serve-policy` refuses look-ahead checkpoints (`lookahead_version > 0`).

### Datasets
- Every dataset gets a manifest: seed range, policy source, bridge kind, source revision,
  action-space size, observation dimensions.
- Heuristic samples keep per-step `rewards` and round targets in `terminal_rewards`.
- Use `--format npz-shards` and chunked generation (`--chunk-size`, default 1000) for large runs.
- BC/AWBC load only current-observation arrays; IQL/offline-Q need next-state arrays and may need
  transition limits.
- `--learning-seat-rule seed-mod-4` keeps one seat per episode before serialization.

### Promotion discipline
Full protocol and the spent-window registry: [`docs/ai-evaluation.md`](../docs/ai-evaluation.md).
- **`fh-mj-compare` is required for every verdict.** Read `mean_placement_ci95_clustered`, never
  the iid CI.
- The default gate plays against three heuristic bots. A strong-table report
  (`--opponent-checkpoint`) pairs only with a report against the same opponent; a batched report
  only with a batched report of the same settings.
- Compare suit-averaged candidates against suit-averaged comparators.
- Screening: `--start-seed 910000`, never cited for promotion. Confirmation: a fresh,
  registered window, used once.
- `fh-mj-benchmark` is a yardstick, never a gate. `fh-mj-serving-parity` is a hard gate and
  fails when it checks zero decisions.
- Nothing edits `best-checkpoints.json` automatically; promotion is manual.
- `fh-mj-compare`'s printed `tail_gate` is the placement-reshape lap's rule, not the standard
  pass rule (large-loss ≤ comparator + 0.015).
- Risk-critic and action-EV runs calibrate critics; they never promote a policy. Paired-trace
  rows after the first divergence are not same-state counterfactuals.

### Training
- `fh-mj-train-b2b` defaults are the champion recipe (γ 0.99, lr 2e-5, entropy 0, 2 epochs,
  minibatch 256, grad norm 0.5, event window 128); pass `--matches-per-iter 320`.
- `--resume-from-state` rejects any change to the env, model, or PPO config — including
  `collector`, `pool_slots`, `pool_pipeline_groups`, `trunk_dtype`, `suit_augment` — except
  `iterations` and the resource fields `num_workers`, `collect_dispatch_chunk`,
  `minibatch_device_transfer`, which are logged and allowed.
- IQL: never initialize `q_head` from policy logits; keep BC regularization on; CQL and naive
  offline Q stay ablations.
- Record every non-default `--model-*` flag in MLflow and reports.
- `--head-lr/--head-lr-iters` (two AdamW groups, `bc` and `heads`) and the step-zero transfer
  gate apply only to `--scratch --init-from-bc`; see `MODULES.md` (`train_b2b.py`).
- `EventPathTelemetry` and `TrunkAlphaTelemetry` write event-path and ReZero-alpha readouts to
  `history.json`; an event slice that is non-zero at step zero, non-finite, or frozen halts the
  run after the iteration is saved.
- MLflow is opt-in (`--mlflow`); storage `ai/mlflow.db` and `ai/mlartifacts`, both gitignored.

### Collector determinism
- `tests/test_b2b_collector_parity.py` pins the process collector's output with golden digests.
  A failure means the code changed bytes; fix the code, never the constants.
- The two collectors are byte-identical only under greedy `inference_mode="per_row"`. In
  production `batched` mode, which rows share a forward depends on the slot count, so floats move
  at rounding level and sampled actions can differ.
- CUDA graphs are captured per collection call (and per full-size PPO minibatch) and never cached
  across calls. Nothing inside a captured step may sync the host (`.item()`, boolean indexing,
  data-dependent `if`). Zero graph-owned `.grad` buffers in place, never set them to `None`.
- Float gates: register a ceiling from a measurement in the regime it gates (CPU vs CUDA, fp32
  vs TF32, production width); gate greedily; pin fp32 around the gate; report a skipped gate as
  `passed: None`; fail a gate that checked zero items. Details in `MODULES.md`
  (`scripts/collect_bench.py`).

### Patching across the training modules

`train_b2b.py` calls `train_state.py` helpers as `train_state.X`, so one monkeypatch on
`fh_mahjong_ai.train_state.X` reaches both modules. In general, patch a name on the module that
**calls** it, not the one that defines it: `collect_b2b_rollouts` calls `build_bridge`, so patch
`fh_mahjong_ai.train_b2b.build_bridge`.

### Serving posture
- **Serve greedy.** Sampling caused visible blunders against humans, and the greedy champion was
  not exploitable. `--sample-*` flags are for experiments.
- `--symmetry-average suits` serves the suit-averaged policy (~3× the CPU latency of plain).
- Serving defaults to `ai/checkpoints/best-checkpoints.json`; override with `--checkpoint` or
  `FH_MAHJONG_AI_CHECKPOINT`.
- `FH_MJ_EVALUATE_TOKEN` is required in production; `/evaluate` is disabled without it.

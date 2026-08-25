# ai/

> Python reinforcement learning package for Fenghua Mahjong.

## Overview

This directory contains the Python-side RL stack. Go remains the authoritative simulator; Python owns model definition, data loading, checkpointing, and training orchestration. The package supports both a mock bridge for smoke tests and a real `ctypes` bridge to the Go c-shared library.

Reading order for a newcomer: **Commands** (what you can run) → **Architecture** (how data flows) → **Key Files** (per-module detail) → **Gotchas** (the invariants that bite).

## Commands

Always via uv — never plain `pip`/`python`:

```bash
uv sync --project ai --extra dev
uv run --project ai <command>
```

### Generate data
| Command | Purpose |
|---|---|
| `fh-mj-generate-data` | Heuristic trajectories → JSONL or sharded NumPy + manifest |
| `fh-mj-generate-selfplay` | Mixed self-play (checkpoint/random/heuristic seats) |
| `fh-mj-convert-data` | JSONL → sharded NumPy replay storage |
| `fh-mj-generate-branch-counterfactuals` | Exact same-state legal-discard branch labels |
| `fh-mj-generate-sampled-branch-counterfactuals` | Greedy-vs-sampled branch pairs |
| `fh-mj-generate-targeted-branch-counterfactuals` | Branch labels at diagnostic-selected states |
| `fh-mj-build-paired-trace-action-ev-data` | Paired-trace divergences → action-EV NPZ schema |

### Train
| Command | Purpose |
|---|---|
| `fh-mj-train-bc` | Behavior cloning (the offline warm-start); accepts the shared `--model-*` flags including `--model-kernel-width` |
| `fh-mj-train-awbc` | Advantage-weighted BC |
| `fh-mj-train-iql` | Discrete IQL — the main offline RL trainer |
| `fh-mj-train-offline-q` | Conservative offline Q (experimental) |
| `fh-mj-train-global-ev` | Visible-state (or action-conditioned) global EV predictor |
| `fh-mj-train-pairwise-delta` | Direct paired-trace reward-delta predictor (diagnostic-only) |
| `fh-mj-train-branch-preference-policy` | Push exact branch labels into top-k proposals |
| `fh-mj-train-action-risk` | Action-conditioned large-loss risk heads |
| `fh-mj-train-ppo` | Online self-play PPO vs a frozen anchor |
| `fh-mj-train-oracle` | Phase-1 oracle (single-seat, perfect-information) |
| `fh-mj-train-selfplay-oracle` | Phase-2 self-play feature-dropout oracle |
| `fh-mj-train-b2b` | Spec B2b: event history + privileged critic + aux heads; `--scratch [--init-from-bc]` for random-init runs |

### Evaluate and gate
| Command | Purpose |
|---|---|
| `fh-mj-evaluate` | Offline agreement and/or online live play; `--duplicate-seats` is the gate |
| `fh-mj-compare` | **Required for any promotion verdict** — seed-clustered paired diff |
| `fh-mj-benchmark` | Tenhou-style stat sheet vs heuristic bots (yardstick, NOT a gate) |
| `fh-mj-placement-calibrate` | Stage-0 λ calibration for terminal placement bonus; returns λ = 0.5·σ_R/σ_V on frozen 320-match anchor collection; fails closed on truncation and scale gates (RMS ≤1.35, |p99| ≤1.50, critic MSE ≤2.00); never adjusts λ |
| `fh-mj-evaluate-risk-guarded` | Action-risk checkpoint as a guard around an anchor |
| `fh-mj-reward-calibration` | Q/value calibration vs discounted terminal payout |

### Serve
| Command | Purpose |
|---|---|
| `fh-mj-serve-policy` | JSON HTTP policy server (`/act`, `/evaluate`, `/healthz`, `/reload`, `/warmup`) |
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
| `fh-mj-collect-bench` | Worker-count benchmark; digest-gated exact-semantics proof |
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
   collectors: train_b2b.py (ParallelB2bCollector), oracle.py, parallel_rollouts.py,
               batched_selfplay.py, offline_trainers.py
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

Module entries below are tagged with the spec that introduced them. These are historical
labels, not separate code paths:

- **B2b** — event history + privileged critic + auxiliary heads, warm-started from the 39ch champion.
- **deep16-rezero** — width growth by stacking dormant ReZero residual blocks.
- **gru-width** — widening the event GRU in place via an identity-masked projection.
- **data-scale-960** — the 960-match scaling work: dispatch chunking, memory profiling, minibatch device transfer.
- **mortal-scale-scratch** — `ModelConfig.kernel_width` (1 = Mortal-style (3,1) convs), `fh-mj-train-bc --model-*`, and `fh-mj-train-b2b --scratch [--init-from-bc]` — BC → PPO from random init, no anchor.
- **Spec B2c** — serving: metadata-authoritative architecture recovery and the event wire contract.

## Key Files

> **Per-module detail lives in [MODULES.md](MODULES.md)** — one entry for each of the
> 90 modules, grouped by role, with the design rationale and failure modes.
> Open it when you are about to touch a specific module.

Quick map of what is where:

| Group | Modules |
|---|---|
| Contracts and configuration | `config.py`, `types.py`, `action_catalog.py`, `events.py` |
| Bridge and environment | `bridge.py`, `env.py`, `envpool.py`, `searchpool.py` |
| Model | `model.py` |
| Training | `ppo.py`, `ach.py`, `oracle.py`, `train_b2b.py`, `train_state.py`, `offline_trainers.py`, `batched_selfplay.py`, `parallel_rollouts.py`, `selfplay_loop.py` |
| Data and storage | `data.py`, `buffer.py`, `streaming_buffer.py`, `storage.py`, `checkpoint_manifest.py` |
| Policies, search, serving | `policies.py`, `search.py`, `serving.py` |
| Evaluation and diagnostics | `evaluate.py`, `hand_stats.py`, `reward_calibration.py`, `global_ev*.py`, `paired_trace*.py`, `branch_c*.py`, `near_state_counterfactuals.py`, `risk_filter.py` |
| Infrastructure | `mlflow_tracking.py`, `memprobe.py`, `fdlimit.py`, `generated/proto/` |
| Scripts | `scripts/` — see the Commands section above for the CLI each one backs |
| Deployment | `checkpoints/deploy/`, `Dockerfile.compose`, `Dockerfile.deploy` |

## Gotchas

### Environment and tooling
- **Use uv for everything**: `uv sync --project ai --extra dev`, then `uv run --project ai ...`. Avoid non-uv package or environment commands in this repo.
- `ai/.python-version` pins the uv-managed interpreter. **The package requires CPython 3.12** (`requires-python = ">=3.12"`); there is no longer a 3.9 compatibility constraint, so `dataclass(slots=True)` and other 3.10+ features are fine.
- Multi-worker collection needs a raised fd limit — the training/bench/profile CLIs call `fdlimit.raise_file_descriptor_limit` for you.

### Go is the authority
- `fh-mj-serve-policy` is an inference boundary only. The Go server/bridge must decode and validate every returned `action_id` against the current legal action set before applying it.
- All action selection assumes the fixed 204-action catalog supplied by the Go bridge.
- `events.py` mirrors `internal/rl/eventcodec.go` — **change both or neither.**

### Observations and checkpoints
- `EnvConfig` defaults match the real Go bridge: `39 x 42 x 1` planes, 58 scalars, 204 actions. B2b models consume 51 channels (39 public + 12 privileged) but **the policy path only ever reads the first 39** — the actor is information-legal by construction.
- Legacy 42-scalar checkpoints are padded in `storage.load_checkpoint()` so old policy weights load while new Chongci match-context scalar weights start at zero.
- A B2b checkpoint's `event_window` is **not recoverable from tensor shapes**. `infer_model_config` needs `metadata["model_config"]` (or the older `metadata["b2b"]` block) and raises without it. When adding a `ModelConfig` field, add it to `model_config_args.py`'s `model_config_params()` by hand.
- `kernel_width` IS shape-inferred (`plane_stem.0.weight.shape[3]`); metadata that disagrees with it is rejected.
- BC trains with `events=None`, so an event-enabled net's offline validation runs under `allow_zero_events` — real planes and scalars, a zero event vector. The per-epoch report's `validation_events` says which case ran: `"zeroed"` = an event-enabled net validated with zero event features, `"none"` = the net has no event encoder, `null` = no validation ran. A zeroed agreement number describes the BC stage only; it is not comparable to an event-fed B2b evaluation.

### Datasets
- Dataset generation writes a manifest next to each JSONL file or shard directory with seed range, policy source, bridge kind, git commit, action-space size, and observation dimensions.
- Heuristic trajectory samples preserve per-step rewards in `rewards` and attach round-outcome targets separately in `terminal_rewards` for warm-start consumers.
- Prefer `--format npz-shards` for large generation runs (avoids a huge temporary JSONL); convert older JSONL with `fh-mj-convert-data`. Large Go-bridge exports should use chunked generation rather than one huge protobuf response (`--chunk-size` defaults to 1000).
- BC and AWBC load only current-observation/action/return arrays to stay within WSL memory on 50k+ datasets; IQL/offline-Q need next-state arrays and may need transition limits.
- New shards preserve `decision_indices` and `sample_weights` so paired-trace first-divergence cases map back into training rows; older shards without decision indices fall back to seed/seat/action matching.

### Promotion discipline
- **`fh-mj-compare` is the required tool for any promotion or lever verdict.** Read the *clustered* CI (`mean_placement_ci95_clustered`), never the naive iid one — the four seat-rotations of a wall seed are correlated.
- **Placement-reshape terminal bonus**: When training with `--placement-bonus-values` / `--placement-bonus-lambda`, evaluation adds per-episode 4th-place share, rank-share histogram, and asymmetric training utility to reports; `fh-mj-compare` emits `tail_metrics` (seed-clustered deltas for fourth_share / large_loss / training_utility) and `tail_gate` (registered thresholds −0.010 / −0.030 / +0.005, reported only); `significant` (canonical placement delta) remains the canonical promotion gate.
- Screening uses `--start-seed 910000` (cheap, unlimited, never cited for promotion). Confirmation — the only runs that may back a promotion — uses a **fresh window no prior lap has spent**, 1500 seeds/side, pre-registered before launch. A window burns once and is then retired; reusing one carries winner's-curse bias. Spent so far: `870000+`, `950000+`, `990000+`, `1030000+`, `1070000+`, `1110000+`, `1150000+`, `1190000+`.
- `fh-mj-benchmark` is a yardstick, not a gate. Never wire it into the selfplay loop or promotion path.
- `fh-mj-serving-parity` is a hard gate and is vacuity-proof: zero decisions checked is a failure.
- The selfplay loop never edits `best-checkpoints.json`; registry promotion is manual.
- Risk-critic and action-EV training runs are *calibration* experiments — they can accept or reject a critic, but they never promote the underlying policy checkpoint by themselves.
- Paired-trace rows after the first divergence are no longer same-state counterfactuals. Use them for risk calibration and data mining, never as promotion-gate proof.

### Training defaults worth knowing
- IQL should not initialize `q_head` from BC policy logits — policy logits are action scores, not reward-scaled Q estimates. `--init-q-from-policy` is an explicit ablation only.
- IQL uses `steps_to_done` to discount sparse terminal round payout as `gamma ** steps_to_done * terminal_reward`, matching the Mortal-style sparse-reward target shape.
- Keep BC regularization enabled on IQL. `--cql-weight` (Mortal-style conservative Q penalty over legal masked actions) stays an explicit ablation until duplicate-seat evaluation beats BC. Naive offline Q remains experimental for the same reason.
- Record every non-default architecture flag (`--model-channels`, `--model-residual-blocks`, `--model-channel-attention`, `--model-growth-blocks`, `--model-event-*`, `--model-kernel-width`) in MLflow and report outputs. `--partial-init-checkpoint` is for explicit ablations that add compatible layers.
- MLflow tracking is opt-in via `--mlflow`; local storage defaults to `ai/mlflow.db` with artifacts in `ai/mlartifacts`, both gitignored.

### Patching across the training modules

`train_b2b.py` calls `train_state.py`'s helpers as `train_state.X`, not through
`from .train_state import X`. That is deliberate: a monkeypatch on
`fh_mahjong_ai.train_state.X` then reaches **both** train_b2b's calls and
train_state's own internal ones. With a symbol import it would reach neither
reliably, and the test would pass while patching nothing.

The general rule when patching a name that a module *imported* (`build_bridge`,
`save_checkpoint`, `compute_gae`, `MahjongEnv`): patch it on the module that
**calls** it, not the one that defines it. `collect_b2b_rollouts` calls
`build_bridge`, so the target is `fh_mahjong_ai.train_b2b.build_bridge` — a
patch on `fh_mahjong_ai.bridge.build_bridge` would not rebind the copy
train_b2b already holds.

### Serving posture
- **Production serves GREEDY** (no sampling flags; temperature 0 = argmax) since 2026-07-11. The exploitability probe showed the greedy champion is not exploitable by a trained best-response, and sampling produced visible per-move blunders in human games. Sweep history (2026-07, deep4 student): T≤0.7 top-k 3 discard-only was aggregate cost-free (paired vs anchor +0.29..+0.31, large_loss ≤0.127); T=1.0 degraded tail risk (large_loss 0.158). The `--sample-*` flags remain available for experiments.
- Serving defaults to `ai/checkpoints/best-checkpoints.json`. Override the binary location with `--checkpoint` or `FH_MAHJONG_AI_CHECKPOINT`.
- `FH_MJ_EVALUATE_TOKEN` is **required in production** — `/evaluate` is fully disabled without it.

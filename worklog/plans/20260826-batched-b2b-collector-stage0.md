# batched-b2b-collector — Stage 0 implementation plan

**Spec:** `../specs/20260826-batched-b2b-collector-design.md` (ratified with amendments
2026-08-26). Stage 0 only: code + G0 gates on Mac/CPU. No box, no training use, no
default switch.

Branch `experiment/batched-b2b-collector`, worktree `.claude/worktrees/batched-b2b-collector`.
Bridge library for Go tests: `go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge`
(the default path `bridge.py:resolve_bridge_library_path` looks for). Python via
`uv run --project ai ...` only.

## Invariant that governs every task

**`collect_b2b_rollouts` (the process collector) must produce byte-identical
`RolloutBatch` + `match_telemetry` before and after this work.** The live
placement-reshape lap and every prior digest gate depend on it. Task 2 pins this with a
golden digest recorded from `main` before any edit.

## Tasks

Dependency order: T1 ∥ T2 → T3 → T4. Each task commits to the branch (no PR per task),
runs `uv run --project ai pytest ai/tests -q` for the files it touched plus the golden
digest test, and `gofmt -l . && go vet ./...` if it touched Go (it should not).

### T1 — pool decoding and configuration parity (`envpool.py`)

Spec change 1, amendment 1.

- `SlotMeta` gains `round_outcome: Optional[dict] = None`.
- `GoEnvPool._decode_response`: decode `state.round_outcome` with the bridge's existing
  `_decode_round_outcome` (find it on `CtypesGoBridge` in `bridge.py`; reuse, do not copy).
  `None` when the proto field is unset.
- `InProcessEnvPool.step`: forward `StepResult.info.get("round_outcome")` (and the reset
  result's, if present) into `SlotMeta.round_outcome`.
- `make_selfplay_pool`: copy `chongci_starting_score`, `chongci_bust_threshold`,
  `chongci_max_hands` from `env_config`, matching `train_b2b.py:503`.
- Tests (`ai/tests/test_envpool.py`):
  - Go pool, chongci, one slot stepped by a heuristic/random legal action loop: the
    **ordered** sequence of `round_outcome` payloads equals the sequence the single-env
    `CtypesGoBridge` path yields for the same seed (nonterminal boundary + terminal
    hand). Truncation-after-completed-hand case at a small `max_steps_per_episode`.
    Reset-terminal case (a seed whose match ends at reset, if constructible; otherwise
    an `InProcessEnvPool` with a stub bridge).
  - `InProcessEnvPool` forwards an injected `round_outcome`.
  - `make_selfplay_pool` config equality with the process collector's `cfg`
    (compare `asdict` minus `learning_seats`-irrelevant fields).

### T2 — shared finalizer, shared action helper, golden digest (`train_b2b.py`, `ppo.py`)

Spec change 2 and the logprob helper of change 3.

- **Golden digest first.** Before editing, record `_digest_batch(...)` from
  `scripts/collect_bench.py` over `collect_b2b_rollouts` on the Go bridge, chongci,
  `SMALL_MODEL` from `test_b2b_training.py`, `torch.manual_seed(0)` model init,
  `matches=3`, `base_seed=4242`, `max_steps_per_episode=20000`, plus a
  `hashlib.sha256(json.dumps(match_telemetry, sort_keys=True))`. Commit the two hex
  strings as constants in a new `ai/tests/test_b2b_collector_parity.py::test_process_collector_golden_digest`.
  This test is the invariant guard for T2–T4.
- Factor the per-match tail of `collect_b2b_rollouts` (from `is_truncated = ...` through
  the per-seat emission loop) into a pure `_finalize_b2b_match(ms, config, cfg,
  seed) -> tuple[dict[str, list], dict]` where `ms` is a small dataclass
  `_B2bMatchState` holding the per-seat lists, `seat_hand_ids`, `hand_outcomes`,
  `match_net`, `truncated`. Returns the seat-contiguous rows (planes, scalars, masks,
  actions, logprobs, values, rewards, dones, events, lengths, dealin, rank) and the
  telemetry dict. All fail-closed raises stay inside it. `collect_b2b_rollouts` builds a
  `_B2bMatchState` per match and calls it; its output is byte-identical (golden test).
- Add `action_selection: str = "sample"` kwarg to `collect_b2b_rollouts`; `"greedy"` =
  argmax over the masked logits, logprob = `dist.log_prob(action)`. Test-only.
- Add to `ppo.py` a shared helper `masked_logprob(logits_row: Tensor[A], temperature,
  action: int) -> float` = `masked_policy_distribution(logits/temperature).log_prob`,
  and make `collect_b2b_rollouts` use it (must not change its float output — the
  existing expression is exactly this; verify with the golden test).
- Move the "zero outcomes across completed chongci matches" check into a helper
  `_check_chongci_outcomes(chongci, completed, outcomes_seen)` both collectors call.

### T3 — the batched collector (`batched_b2b.py`) and G0.1–G0.5

Spec change 3, amendments 2–4.

- `collect_b2b_rollouts_batched(env_config, model, config, base_seed, pool,
  inference_mode="batched", action_selection="sample") -> RolloutBatch`, mirroring
  `batched_selfplay.collect_selfplay_rollouts_batched`'s round loop but with:
  - `_B2bMatchState` from T2 per slot; `match_net` accumulated from **every**
    `step_rewards` incl. the reset one; `round_outcome` on a returned slot closes the
    current `hand_id` exactly as `train_b2b.py:616` does (record it before the
    terminal/truncated check).
  - rows carry tail-windowed events (`row_events[:ev_len] = ev[-ev_len:]`, window =
    `model.model_config.event_window`) and lengths.
  - one `model(planes, scalars, mask, events=..., event_lengths=...)` per round on
    `config.device`; per-row action via `sample_masked_action` with the match's numpy
    RNG (or argmax when greedy); **logprob via `ppo.masked_logprob` on the Torch
    logits row**, not the numpy log-softmax; value from the same forward.
  - `inference_mode="per_row"` runs one forward per row (batch-composition-independent
    floats).
  - finalize via `_finalize_b2b_match`; flush in seed order; `truncated_matches`,
    `match_telemetry` populated; `_check_chongci_outcomes` at the end.
  - `effective_slots = min(pool.slots, matches_per_iter)`; log it.
  - the pool's `EnvConfig` must be built with `oracle_observation=True` and
    `event_history_window = model.model_config.event_window` — add
    `make_b2b_pool(env_config, model, config, slots)` in `batched_b2b.py` that does this
    via `make_selfplay_pool` and asserts the window.
- Tests (`ai/tests/test_b2b_collector_parity.py`, Go bridge, chongci, `SMALL_MODEL`,
  `event_window=8`, seeds chosen so the block includes ≥1 truncated and ≥1 bust match —
  find such seeds empirically and name them in the test):
  - **G0.1** greedy + per_row: digest of every `RolloutBatch` field and telemetry hash
    equal between the two collectors.
  - **G0.1b** greedy + batched: discrete fields exact; `old_logprobs`, `values`
    `np.allclose(atol=1e-6, rtol=1e-5)`.
  - **G0.2** sampled: digest equal for `pool_slots ∈ {1, 7, 64}`.
  - **G0.3** placement bonus on: truncated-match raise, zero-decision-seat raise, and
    the per-match bonus-sum check behave identically (parametrize over both collectors).
  - **G0.4** per-slot ordered `hand_outcomes` and `hand_id` assignment equal to the
    process collector's for the same seeds (expose via a test hook or by comparing
    `dealin_labels`/`rank_labels` blocks per seat — labels are a function of exactly
    these, so equality there plus the T1 ordered-outcome test covers it).
  - **G0.5** ragged GRU (`ai/tests/test_b2b_model.py`): batch of rows with lengths
    `{0, 1, W−1, W}` and padding filled with garbage ids vs the same rows one at a time:
    logits/values `allclose(atol=1e-6, rtol=1e-5)`; a length-0 row equals the
    no-history output.

### T4 — wiring, bench, resume, training parity

Spec changes 4–5, amendments 5–7.

- `train_b2b.train_b2b`: when `config.collector == "batched"`, build the pool with
  `make_b2b_pool` (from `bridge_env_config`), collect with
  `collect_b2b_rollouts_batched`, close the pool in the `finally` next to
  `collector.close()`; `num_workers` ignored with a logged notice. Reject
  `collector="batched"` together with `placement_bonus_values` **unless**
  `allow_batched_placement_bonus=True`? — No: keep it simple and honest — the batched
  collector supports the bonus (finalizer is shared); nothing to reject.
- `scripts/train_b2b.py`: `--collector {process,batched}` (default `process`),
  `--pool-slots`.
- `train_state.py`: add `("ppo_config", "pool_slots")` to `_RESUME_LOGGED_FIELDS` with a
  comment; `collector` stays rejected (default behaviour) — add
  `test_b2b_resume.py::test_resume_from_state_raises_on_different_collector` and
  `..._allows_different_pool_slots_with_notice`. Check `_fill_legacy_echo_defaults` for
  a state file saved before `collector`/`pool_slots` existed in `PPOConfig`; add the
  legacy defaults if the mechanism needs them (see the existing entries for
  `growth_blocks` etc.).
- Pool cleanup on exception test: a collector that raises mid-collection leaves no live
  pool (`pool.close()` called — use a spy pool).
- `scripts/collect_bench.py`: `--collector {process,batched}` and `--pool-slots`
  (comma list like `--workers`); batched path builds one persistent pool for warmup +
  steady rounds; digest machinery unchanged. Fix the CUDA peak measurement: snapshot
  `torch.cuda.max_memory_allocated()` for collection **before** the
  `reset_peak_memory_stats()` that precedes PPO, and report both. Full-cycle report gains
  `collector`, `pool_slots`, `effective_slots`.
- **G0.6** training parity (`ai/tests/test_b2b_collector_parity.py`): two iterations of
  `train_b2b` on Go bridge, chongci, `SMALL_MODEL`, `iterations=2`, `matches_per_iter=3`,
  `ppo_epochs=1`, `minibatch_size=64`, process vs batched (`per_row`, greedy via a
  monkeypatched `action_selection` default): saved checkpoint state dicts byte-equal
  (`torch.equal` on every tensor); then batched-mode within `allclose(atol=1e-5)` on
  every parameter.
- `ai/CLAUDE.md` + `ai/MODULES.md`: entry for `batched_b2b.py`; `train_b2b`,
  `envpool`, `collect_bench` entries updated; Gotchas line: "`collector` is
  rejected-on-change on resume; the batched collector must never touch the
  placement-reshape lineage".

## Done means

- `uv run --project ai pytest ai/tests -q` green.
- Golden digest test unchanged from its `main` value.
- `uv run --project ai fh-mj-collect-bench --collector batched --pool-slots 8,32
  --matches 32 --device cpu --bridge-kind go --champion <anchor075> --full-cycle`
  exits 0 with digest equality across slot counts.
- `gofmt -l .` empty, `go vet ./...`, `go test ./internal/rl/...` (no Go changes
  expected; confirm nothing drifted).

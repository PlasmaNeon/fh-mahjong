# Suit-Distillation Lap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--suit-distill-coef` (PPO + β·KL toward the collection-time suit-averaged policy) to the batched B2b trainer, then run the registered two-arm lap.

**Architecture:** The batched collector computes a six-view suit-averaged teacher per stored row (one extra no-grad forward per round) and stores it as `RolloutBatch.teacher_logprobs`; `ppo_update` adds `β · masked_distill_kl` to the loss. β = 0 leaves every code path and digest byte-identical.

**Tech Stack:** Python 3.12, PyTorch, NumPy, the Go c-shared bridge, uv, pytest.

**Spec:** `../specs/20261002-suit-distill-lap.md`

## Global Constraints

- β (`suit_distill_coef`) is 1.0 for the distill arm and 0 for the control; fixed, no sweep.
- β = 0 is byte-identical: the three process-collector golden digests (`ai/tests/test_b2b_collector_parity.py`) and every batched-collector digest test pass unchanged.
- β > 0 requires `collector="batched"`; β < 0 is an error; β is rejected-on-change by `--resume-from-state`; legacy train states read it as 0.0.
- Recipe (both arms): batched collector, 256 slots, 1 group, 320 matches/iteration, minibatch 256, 2 epochs, lr 2e-5, entropy 0, γ 0.99, chongci, step cap 4000, event window 128, privileged critic, aux heads, fp32, `--suit-augment`, 150 iterations, init `3fdfe246…`.
- Seeds: training base 3,000,000 (3,000,000–3,047,999, paired); evaluation 3,100,000–3,104,999 (5,000 × 4); pre-launch measurements on screening seeds (base 910,000) only.
- The lap's commit descends from `6c354655` (wild-run fix) and `785b3b85` (prevailing-wind fix); one bridge build for training and evaluation.
- Python through uv only: `uv run --project ai …`. Bridge-dependent tests need `FH_MAHJONG_BRIDGE_LIB=<abs path>/build/libfh_mahjong_bridge.so` (build with `go build -buildmode=c-shared -o build/libfh_mahjong_bridge.so ./cmd/rlbridge`).
- Docs: update the touched modules' entries in `ai/MODULES.md` and the CLI table in `ai/CLAUDE.md`; state the current behavior, no change narration.
- Box: a fresh clone at `/root/fh-mahjong-distill`; never pull or rebuild in `/root/fh-mahjong`; check `pgrep -af "[f]h-mj-"` before any box command; message peer sessions (`ListAgents`) before taking the GPU; run no other GPU job during the lap.
- PRs merge with `gh pr merge <n> --merge`.
- Work on branch `feat/suit-distill`, cut from `docs/suit-distill-spec` (it carries the spec and this plan).
- Test snippets appended to `ai/tests/test_suit_distill.py` list their imports first; put those imports in the file's import block.

## Review Focus

- Pipelined collection (`pool_pipeline_groups=2`) with β > 0: teacher rows must stay aligned with their decisions — Task 4 pins groups 1 vs 2 digest equality under greedy `per_row`.
- Matches that truncate at the step cap with β > 0: every emitted row must carry its teacher — Task 4 forces truncations (step cap 120) and checks row counts.
- The lap's `--minibatch-device-transfer` (host-gather) update path: the teacher must ride the per-minibatch gather — Task 5 parametrizes its KL tests over both transfer paths.
- A β > 0 update handed a batch without teacher rows (a process-collector batch, a hand-built batch): must raise, not silently skip the term — Task 5 test.
- CUDA-only paths (the graphed teacher forward and the captured update step with the `teacher` input) cannot run in CI — Task 6's on-box pace run must show finite `distill_kl` in `history.json` and no capture error.

---

### Task 1: Config, CLI and resume contract

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (`PPOConfig` fields and `__post_init__`, ~lines 172-198)
- Modify: `ai/src/fh_mahjong_ai/train_state.py` (`_LEGACY_ECHO_ADDITIONS`, `_LEGACY_ECHO_PINNED_VALUES`, ~lines 444-480)
- Modify: `ai/src/fh_mahjong_ai/scripts/train_b2b.py` (argparse ~line 64, validation ~line 248, `PPOConfig(...)` ~line 265)
- Modify: `ai/CLAUDE.md` (the `fh-mj-train-b2b` row)
- Create: `ai/tests/test_suit_distill.py`

**Interfaces:**
- Produces: `PPOConfig.suit_distill_coef: float = 0.0`; CLI flag `--suit-distill-coef`.

- [ ] **Step 1: Write the failing tests** — create `ai/tests/test_suit_distill.py`:

```python
"""Suit distillation (PPOConfig.suit_distill_coef): spec worklog/specs/20261002-suit-distill-lap.md."""

import os

import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.ppo import PPOConfig

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library"
)


def test_config_validates_the_coefficient():
    with pytest.raises(ValueError, match="suit_distill_coef"):
        PPOConfig(collector="process", suit_distill_coef=1.0)
    with pytest.raises(ValueError, match=">= 0"):
        PPOConfig(collector="batched", suit_distill_coef=-0.5)
    assert PPOConfig(collector="batched", suit_distill_coef=1.0).suit_distill_coef == 1.0
    assert PPOConfig().suit_distill_coef == 0.0


def test_cli_requires_the_batched_collector(monkeypatch, capsys, tmp_path):
    from fh_mahjong_ai.scripts import train_b2b as cli
    champion = tmp_path / "champion.pt"
    champion.write_bytes(b"")
    monkeypatch.setattr("sys.argv", ["fh-mj-train-b2b", "--suit-distill-coef", "1.0",
                                     "--champion", str(champion), "--checkpoint-dir", str(tmp_path),
                                     "--collector", "process"])
    with pytest.raises(SystemExit):
        cli.main()
    assert "--suit-distill-coef requires --collector batched" in capsys.readouterr().err


def test_resume_rejects_a_changed_coefficient_and_reads_legacy_states_as_off():
    from fh_mahjong_ai import train_state
    env = EnvConfig(bridge_kind="mock")

    def echo(coef):
        config = PPOConfig(device="cpu", collector="batched", suit_distill_coef=coef)
        return train_state._train_b2b_config_echo(config, ModelConfig(), env)

    train_state._validate_resume_config_echo(echo(1.0), echo(1.0))
    with pytest.raises(ValueError, match="suit_distill_coef"):
        train_state._validate_resume_config_echo(echo(1.0), echo(0.0))
    legacy = echo(0.0)
    del legacy["ppo_config"]["suit_distill_coef"]
    train_state._validate_resume_config_echo(echo(0.0), legacy)
    with pytest.raises(ValueError, match="suit_distill_coef"):
        train_state._validate_resume_config_echo(echo(1.0), legacy)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_suit_distill.py -q`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'suit_distill_coef'` and the CLI test's unrecognized argument).

- [ ] **Step 3: Implement**

In `ppo.py`, after the `suit_augment: bool = False` field:

```python
    # collector="batched": PPO adds suit_distill_coef * KL(teacher || policy), the teacher being
    # the collection-time policy averaged over the six suit views of each stored row
    # (RolloutBatch.teacher_logprobs). 0 = off and byte-identical. A recipe field.
    suit_distill_coef: float = 0.0
```

and extend `__post_init__`:

```python
    def __post_init__(self) -> None:
        if self.suit_augment and self.collector != "batched":
            raise ValueError("suit_augment=True requires collector='batched'")
        if self.suit_distill_coef < 0:
            raise ValueError(f"suit_distill_coef must be >= 0, got {self.suit_distill_coef}")
        if self.suit_distill_coef > 0 and self.collector != "batched":
            raise ValueError("suit_distill_coef > 0 requires collector='batched'")
```

In `train_state.py`, add to `_LEGACY_ECHO_ADDITIONS["ppo_config"]` after `"suit_augment",`:

```python
        "suit_distill_coef",  # absent before suit distillation (2026-10-02)
```

and to `_LEGACY_ECHO_PINNED_VALUES["ppo_config"]` after `"suit_augment": False,`:

```python
        "suit_distill_coef": 0.0,  # no run before the field existed distilled
```

In `scripts/train_b2b.py`, after the `--suit-augment` argument:

```python
    p.add_argument("--suit-distill-coef", type=float, default=0.0,
                   help="weight of the KL term toward the collection-time suit-averaged policy "
                        "(needs --collector batched; 0 = off). A recipe field: rejected-on-change "
                        "by --resume-from-state")
```

after the `--suit-augment requires --collector batched` check:

```python
    if args.suit_distill_coef < 0:
        p.error("--suit-distill-coef must be >= 0")
    if args.suit_distill_coef > 0 and args.collector != "batched":
        p.error("--suit-distill-coef requires --collector batched")
```

and in the `PPOConfig(...)` call add `suit_distill_coef=args.suit_distill_coef,` after `suit_augment=args.suit_augment,`.

In `ai/CLAUDE.md`, in the `fh-mj-train-b2b` row, after `` `--suit-augment` (batched) collects each decision in a random suit-permuted view`` append: `` ; `--suit-distill-coef β` (batched) adds β·KL toward the collection-time suit-averaged policy``.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_suit_distill.py ai/tests/test_b2b_resume.py ai/tests/test_suit_augment.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/src/fh_mahjong_ai/train_state.py ai/src/fh_mahjong_ai/scripts/train_b2b.py ai/CLAUDE.md ai/tests/test_suit_distill.py
git commit -m "feat(train): suit_distill_coef config, CLI flag and resume contract"
```

---

### Task 2: Teacher arithmetic in `suit_symmetry`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/suit_symmetry.py` (new helpers; `suit_averaged_log_probs` reuses them)
- Modify: `ai/MODULES.md` (the `suit_symmetry.py` entry)
- Test: `ai/tests/test_suit_distill.py`

**Interfaces:**
- Produces:
  - `stack_views(planes, scalars, masks, events, symmetries=SUIT_PERMUTATIONS) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]` — the k·n rows of every view, view-major.
  - `average_view_log_probs(logits, masks, symmetries=SUIT_PERMUTATIONS) -> np.ndarray` — float64 `[n, A]`, illegal = −inf; `logits` is `[k·n, A]` (numpy or torch, any device), view-major.
  - `teacher_log_probs(averaged: np.ndarray) -> np.ndarray` — float32 `[n, A]`, non-finite entries set to `np.finfo(np.float32).min`.

- [ ] **Step 1: Write the failing tests** — append to `ai/tests/test_suit_distill.py`:

```python
from conftest import small_model_config
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.suit_symmetry import (
    SUIT_PERMUTATIONS, average_view_log_probs, permute_rows, stack_views, suit_averaged_log_probs,
    teacher_log_probs, unpermute_action_values,
)


def _random_rows(n=7, window=8, seed=4):
    env = EnvConfig()
    rng = np.random.default_rng(seed)
    planes = rng.random((n, *env.plane_shape), dtype=np.float32)
    scalars = rng.random((n, env.scalar_features), dtype=np.float32)
    masks = (rng.random((n, env.action_space_size)) < 0.25).astype(np.int8)
    masks[:, 5] = 1
    events = rng.integers(0, 1 << 15, size=(n, window), dtype=np.uint32)
    lengths = rng.integers(0, window + 1, size=n).astype(np.int64)
    return planes, scalars, masks, events, lengths


def test_suit_averaged_log_probs_keeps_its_arithmetic():
    torch.manual_seed(3)
    model = PolicyValueNet(EnvConfig(), small_model_config(event_window=8)).eval()
    planes, scalars, masks, events, lengths = _random_rows()
    total, value = suit_averaged_log_probs(model, planes, scalars, masks, events, lengths)
    # The arithmetic as it stood before the helpers were factored out.
    n = planes.shape[0]
    views = [permute_rows(planes, scalars, masks, events, perm) for perm in SUIT_PERMUTATIONS]
    p, s, m, e = (np.concatenate(parts) for parts in zip(*views))
    with torch.inference_mode():
        logits, values = model(torch.from_numpy(p), torch.from_numpy(s), torch.from_numpy(m),
                               events=torch.from_numpy(e.astype(np.int64)),
                               event_lengths=torch.from_numpy(np.tile(lengths, 6)))
    logp = torch.log_softmax(logits.double(), dim=1).numpy()
    want = np.zeros((n, masks.shape[1]))
    for k, perm in enumerate(SUIT_PERMUTATIONS):
        want += unpermute_action_values(logp[k * n:(k + 1) * n], perm)
    want /= 6
    want[masks == 0] = -np.inf
    assert np.array_equal(total, want)
    assert np.array_equal(value, values.reshape(6, n).double().mean(dim=0).numpy())


def test_stack_views_is_view_major():
    planes, scalars, masks, events, _ = _random_rows(n=3)
    p, s, m, e = stack_views(planes, scalars, masks, events)
    assert p.shape[0] == 18
    assert np.array_equal(p[:3], planes) and np.array_equal(m[:3], masks)  # view 0 is identity
    second = permute_rows(planes, scalars, masks, events, SUIT_PERMUTATIONS[1])
    assert np.array_equal(p[3:6], second[0]) and np.array_equal(e[3:6], second[3])


def test_teacher_log_probs_is_float32_with_finite_masked_entries():
    averaged = np.array([[-0.5, -np.inf, -1.25]])
    teacher = teacher_log_probs(averaged)
    assert teacher.dtype == np.float32
    assert teacher[0, 1] == np.finfo(np.float32).min
    assert teacher[0, 0] == np.float32(-0.5) and teacher[0, 2] == np.float32(-1.25)


def test_average_view_log_probs_of_identical_views_is_the_view():
    masks = np.array([[1, 0, 1, 1] + [0] * 200], dtype=np.int8)
    logits = torch.randn(6, 204)
    logits[:] = logits[0]  # every view the same, and the actions untouched by these maps
    total = average_view_log_probs(logits[:, :], masks, symmetries=SUIT_PERMUTATIONS[:1] * 6)
    want = torch.log_softmax(logits[0].double(), dim=0).numpy()
    assert np.allclose(total[0, [0, 2, 3]], want[[0, 2, 3]])
    assert np.isneginf(total[0, 1])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_suit_distill.py -q -k "arithmetic or view or teacher_log_probs"`
Expected: FAIL with `ImportError: cannot import name 'average_view_log_probs'`.

- [ ] **Step 3: Implement** — in `suit_symmetry.py`, insert before `def suit_averaged_log_probs`:

```python
def stack_views(planes: np.ndarray, scalars: np.ndarray, masks: np.ndarray, events: np.ndarray,
                symmetries: tuple[FaceSymmetry, ...] = SUIT_PERMUTATIONS):
    """The k*n rows of every view of the n rows, view-major: view j holds rows j*n .. j*n+n-1."""
    views = [permute_rows(planes, scalars, masks, events, perm) for perm in symmetries]
    return tuple(np.concatenate(parts) for parts in zip(*views))


def average_view_log_probs(logits, masks: np.ndarray,
                           symmetries: tuple[FaceSymmetry, ...] = SUIT_PERMUTATIONS) -> np.ndarray:
    """float64 [n, A]: the mean over the views of log_softmax(view logits), re-indexed to the
    original actions; illegal actions -inf. `logits` [k*n, A] (numpy, or a torch tensor on any
    device) are view-major, as `stack_views` lays the rows out."""
    import torch

    n = masks.shape[0]
    logp = torch.log_softmax(torch.as_tensor(logits).double(), dim=1).cpu().numpy()
    total = np.zeros((n, masks.shape[1]), dtype=np.float64)
    for k, perm in enumerate(symmetries):
        total += unpermute_action_values(logp[k * n:(k + 1) * n], perm)
    total /= len(symmetries)
    total[masks == 0] = -np.inf
    return total


def teacher_log_probs(averaged: np.ndarray) -> np.ndarray:
    """float32 distillation targets from `average_view_log_probs` output: illegal actions at
    float32's finite minimum, the value PolicyValueNet masks logits to."""
    out = np.asarray(averaged).astype(np.float32)
    out[~np.isfinite(averaged)] = np.finfo(np.float32).min
    return out
```

and replace the body of `suit_averaged_log_probs` after its docstring with:

```python
    import torch

    n = planes.shape[0]
    p, s, m, e = stack_views(planes, scalars, masks, events, symmetries)
    to = lambda a: torch.from_numpy(np.ascontiguousarray(a)).to(device)  # noqa: E731
    ev = ln = None
    if getattr(model, "wants_events", False):
        ev = to(e.astype(np.int64))
        ln = to(np.tile(np.asarray(lengths, dtype=np.int64), len(symmetries)))
    with torch.inference_mode():
        logits, values = model(to(p), to(s), to(m), events=ev, event_lengths=ln)
    total = average_view_log_probs(logits, masks, symmetries)
    value = values.reshape(len(symmetries), n).double().mean(dim=0).cpu().numpy()
    return total, value
```

In `ai/MODULES.md`, in the `suit_symmetry.py` entry, after `` `suit_averaged_log_probs(..., symmetries=SUIT_PERMUTATIONS)` `` add: `` (built from `stack_views` and `average_view_log_probs`), and `teacher_log_probs` (float32 distillation targets, illegal actions at float32's finite minimum)``.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `FH_MAHJONG_BRIDGE_LIB=$(pwd)/build/libfh_mahjong_bridge.so uv run --project ai pytest ai/tests/test_suit_distill.py ai/tests/test_suit_symmetry.py ai/tests/test_serving_symmetry.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/suit_symmetry.py ai/MODULES.md ai/tests/test_suit_distill.py
git commit -m "feat(symmetry): stack_views, average_view_log_probs and teacher_log_probs"
```

---

### Task 3: `teacher_logprobs` through the batch, the digest and the row sink

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (`RolloutBatch`, last field)
- Modify: `ai/src/fh_mahjong_ai/scripts/collect_bench.py` (`_digest_batch`, `_semantic_digest_batch`)
- Modify: `ai/src/fh_mahjong_ai/train_b2b.py` (`_B2bMatchState.seat_teacher`, `_finalize_b2b_match`)
- Modify: `ai/src/fh_mahjong_ai/batched_b2b.py` (`_ArrayRowSink` dtypes, `_TEACHER_ROW_DTYPE`)
- Test: `ai/tests/test_suit_distill.py`

**Interfaces:**
- Consumes: `PPOConfig.suit_distill_coef` (Task 1).
- Produces: `RolloutBatch.teacher_logprobs: np.ndarray | None = None` (float32 `[N, A]`); `_B2bMatchState.seat_teacher: list[list]`; `_finalize_b2b_match` rows gain key `"teacher"` iff `config.suit_distill_coef > 0`; `_ArrayRowSink(capacity, dtypes=None)`; `batched_b2b._TEACHER_ROW_DTYPE = {"teacher": np.float32}`.

- [ ] **Step 1: Write the failing tests** — append to `ai/tests/test_suit_distill.py`:

```python
from dataclasses import replace

from fh_mahjong_ai.batched_b2b import _ARRAY_ROW_DTYPES, _TEACHER_ROW_DTYPE, _ArrayRowSink
from fh_mahjong_ai.ppo import RolloutBatch
from fh_mahjong_ai.scripts.collect_bench import _digest_batch, _semantic_digest_batch


def _tiny_batch(n=3):
    z = np.zeros((n, 2), np.float32)
    return RolloutBatch(planes=z, scalars=z, action_mask=z.astype(np.int8),
                        actions=np.zeros(n, np.int64), old_logprobs=np.zeros(n, np.float32),
                        values=np.zeros(n, np.float32), rewards=np.zeros(n, np.float32),
                        dones=np.ones(n, np.float32))


def test_digest_covers_the_teacher_only_when_present():
    batch = _tiny_batch()
    assert batch.teacher_logprobs is None
    zeros = replace(batch, teacher_logprobs=np.zeros((3, 204), np.float32))
    ones = replace(batch, teacher_logprobs=np.ones((3, 204), np.float32))
    assert _digest_batch(1, 1, zeros) != _digest_batch(1, 1, batch)
    assert _digest_batch(1, 1, zeros) != _digest_batch(1, 1, ones)
    # A batched forward rounds the teacher by batch composition, like old_logprobs.
    assert _semantic_digest_batch(1, 1, zeros) == _semantic_digest_batch(1, 1, ones)


def test_row_sink_carries_teacher_rows_and_refuses_a_short_teacher():
    sink = _ArrayRowSink(capacity=10, dtypes={**_ARRAY_ROW_DTYPES, **_TEACHER_ROW_DTYPE})
    rows = {"planes": [np.zeros((2, 3), np.float32)] * 2, "scalars": [np.zeros(4, np.float32)] * 2,
            "masks": [np.zeros(5, np.int8)] * 2, "events": [np.zeros(1, np.uint32)] * 2,
            "actions": [0, 1], "teacher": [np.full(5, -1.0, np.float32)] * 2}
    sink.write(rows)
    assert sink.arrays()["teacher"].shape == (2, 5)
    assert sink.arrays()["teacher"].dtype == np.float32
    with pytest.raises(RuntimeError, match="teacher"):
        sink.write({**rows, "teacher": rows["teacher"][:1]})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_suit_distill.py -q -k "digest or sink"`
Expected: FAIL with `ImportError: cannot import name '_TEACHER_ROW_DTYPE'`.

- [ ] **Step 3: Implement**

`ppo.py` — add as the LAST field of `RolloutBatch` (after `match_telemetry`; every construction site uses keywords):

```python
    # [N, A] float32: the collection-time suit-averaged policy's log-probabilities for each row,
    # in the view the row was stored in (suit_distill_coef > 0 only); illegal actions at
    # float32's finite minimum.
    teacher_logprobs: np.ndarray | None = None
```

`collect_bench.py` — in `_digest_batch`, extend the field set:

```python
    expected_fields = (set(_ROLLOUT_DIGEST_ARRAY_FIELDS)
                       | {"truncated_matches", "match_telemetry", "teacher_logprobs"})
```

and after the `match_telemetry` payload is hashed, before `return h.hexdigest()`:

```python
    # Hashed only when present, so every digest recorded before the field existed keeps its bytes.
    if batch.teacher_logprobs is not None and "teacher_logprobs" not in exclude:
        _update_array_digest(h, "teacher_logprobs", batch.teacher_logprobs)
```

Replace the body of `_semantic_digest_batch` with:

```python
    exclude = _ROLLOUT_TOLERANT_FIELDS
    if batch.teacher_logprobs is not None:  # a batched-forward float field, like old_logprobs
        exclude = exclude + ("teacher_logprobs",)
    return _digest_batch(base_seed, matches, batch, exclude=exclude)
```

`train_b2b.py` — in `_B2bMatchState`, after `seat_hand_ids`:

```python
    seat_teacher: list[list] = field(default_factory=lambda: [[], [], [], []])  # suit distillation
```

and in `_finalize_b2b_match`, after the per-seat `for k in range(4):` loop that fills `rows` and before `return rows, telemetry`:

```python
    if config.suit_distill_coef > 0:
        # Seat-contiguous like every other key; a seat without decisions has no teacher rows.
        rows["teacher"] = [row for k in range(4) for row in ms.seat_teacher[k]]
```

Add to its docstring's `Returns` paragraph: `` With `config.suit_distill_coef > 0`, `rows` also carries `"teacher"`.``

`batched_b2b.py` — after `_ARRAY_ROW_DTYPES`:

```python
# The suit-distillation teacher row (suit_distill_coef > 0), written through the sink like planes.
_TEACHER_ROW_DTYPE = {"teacher": np.float32}
```

and in `_ArrayRowSink`:

```python
    def __init__(self, capacity: int, dtypes: Optional[dict] = None) -> None:
        self.capacity = int(capacity)
        self.rows = 0
        self.dtypes = dict(_ARRAY_ROW_DTYPES if dtypes is None else dtypes)
        self.buffers: dict[str, np.ndarray] = {}
```

with `write` iterating `for key, dtype in self.dtypes.items():` instead of `_ARRAY_ROW_DTYPES.items()`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `FH_MAHJONG_BRIDGE_LIB=$(pwd)/build/libfh_mahjong_bridge.so uv run --project ai pytest ai/tests/test_suit_distill.py ai/tests/test_batched_assembly.py ai/tests/test_collect_bench.py ai/tests/test_b2b_collector_parity.py -q`
Expected: PASS (the three golden digests unchanged).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/src/fh_mahjong_ai/scripts/collect_bench.py ai/src/fh_mahjong_ai/train_b2b.py ai/src/fh_mahjong_ai/batched_b2b.py ai/tests/test_suit_distill.py
git commit -m "feat(train): carry teacher_logprobs through the batch, digest and row sink"
```

---

### Task 4: The teacher forward in the batched collector

**Files:**
- Modify: `ai/src/fh_mahjong_ai/batched_b2b.py` (`_collect_b2b_rollouts_batched`: teacher forward, `round_teacher`, `finish_round`, sink construction, `RolloutBatch(...)`; `_PHASE_TIMER_NOTE`)
- Modify: `ai/MODULES.md` (the `batched_b2b.py` entry)
- Test: `ai/tests/test_suit_distill.py`

**Interfaces:**
- Consumes: `stack_views`, `average_view_log_probs`, `teacher_log_probs`, `suit_averaged_log_probs` (Task 2); `_TEACHER_ROW_DTYPE`, `_ArrayRowSink(capacity, dtypes)`, `_B2bMatchState.seat_teacher`, `RolloutBatch.teacher_logprobs` (Task 3).
- Produces: batched collections with `teacher_logprobs` float32 `[N, A]` when `suit_distill_coef > 0`, `None` otherwise.

- [ ] **Step 1: Write the failing tests** — append to `ai/tests/test_suit_distill.py`:

```python
from conftest import SMALL_MODEL
from fh_mahjong_ai.batched_b2b import collect_b2b_rollouts_batched, make_b2b_pool

MATCHES, SEED = 4, 3100


def _collect(distill_coef=1.0, suit_augment=False, groups=1, max_steps=4000,
             action_selection="greedy", inference_mode="per_row"):
    env = EnvConfig(bridge_kind="go", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=max_steps, chongci_max_hands=4)
    torch.manual_seed(0)
    model = PolicyValueNet(EnvConfig(bridge_kind="go"),
                           ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True,
                                       aux_heads=True)).eval()
    cfg = PPOConfig(device="cpu", matches_per_iter=MATCHES, max_steps_per_episode=max_steps,
                    match_mode="chongci", collector="batched", suit_augment=suit_augment,
                    suit_distill_coef=distill_coef, pool_pipeline_groups=groups)
    pool = make_b2b_pool(env, model, cfg, 3)
    try:
        batch = collect_b2b_rollouts_batched(env, model, cfg, base_seed=SEED, pool=pool,
                                             inference_mode=inference_mode,
                                             action_selection=action_selection)
    finally:
        pool.close()
    return batch, model


@requires_go_lib
@pytest.mark.parametrize("suit_augment", [False, True])
def test_teacher_is_the_suit_averaged_policy_of_each_stored_row(suit_augment):
    batch, model = _collect(suit_augment=suit_augment)
    assert batch.teacher_logprobs.shape == batch.action_mask.shape
    assert batch.teacher_logprobs.dtype == np.float32
    for i in range(len(batch)):
        total, _ = suit_averaged_log_probs(model, batch.planes[i:i + 1], batch.scalars[i:i + 1],
                                           batch.action_mask[i:i + 1], batch.events[i:i + 1],
                                           batch.event_lengths[i:i + 1])
        assert np.array_equal(teacher_log_probs(total)[0], batch.teacher_logprobs[i]), i
    assert (batch.teacher_logprobs[batch.action_mask == 0] == np.finfo(np.float32).min).all()


@requires_go_lib
def test_coefficient_zero_collects_no_teacher():
    batch, _ = _collect(distill_coef=0.0)
    assert batch.teacher_logprobs is None


@requires_go_lib
@pytest.mark.parametrize("selection, mode", [("greedy", "per_row"), ("sample", "batched")])
def test_distilled_collection_is_deterministic(selection, mode):
    first, _ = _collect(suit_augment=True, action_selection=selection, inference_mode=mode)
    second, _ = _collect(suit_augment=True, action_selection=selection, inference_mode=mode)
    assert first.teacher_logprobs is not None
    assert _digest_batch(SEED, MATCHES, first) == _digest_batch(SEED, MATCHES, second)


@requires_go_lib
def test_teacher_rows_stay_aligned_under_pipelining_and_truncation():
    one, _ = _collect(max_steps=120)
    two, _ = _collect(max_steps=120, groups=2)
    assert one.truncated_matches > 0
    assert len(one.teacher_logprobs) == len(one) and len(two.teacher_logprobs) == len(two)
    assert _digest_batch(SEED, MATCHES, one) == _digest_batch(SEED, MATCHES, two)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `FH_MAHJONG_BRIDGE_LIB=$(pwd)/build/libfh_mahjong_bridge.so uv run --project ai pytest ai/tests/test_suit_distill.py -q -k "teacher_is or zero_collects or deterministic or aligned"`
Expected: FAIL (`AttributeError: 'NoneType' object has no attribute 'shape'` — nothing fills the teacher yet).

- [ ] **Step 3: Implement** — in `batched_b2b.py`:

Imports (replace the `suit_symmetry` import line):

```python
from .suit_symmetry import (SUIT_PERMUTATIONS, action_map, average_view_log_probs, permute_rows,
                            stack_views, suit_averaged_log_probs, teacher_log_probs)
```

Replace the sink construction:

```python
    distill = config.suit_distill_coef > 0
    # A match emits at most one row per step, so matches x step cap bounds the batch.
    sink = _ArrayRowSink(total * int(config.max_steps_per_episode),
                         {**_ARRAY_ROW_DTYPES, **(_TEACHER_ROW_DTYPE if distill else {})})
```

After the `graphed = [...]` list:

```python
    # suit_distill_coef: one six-view forward per round for the teacher. Called synchronously
    # (launch then fetch), so one instance serves every pipeline group.
    teacher_forward = (_GraphedForward(model, device, effective_slots * len(SUIT_PERMUTATIONS))
                       if distill and use_graphs else None)

    def round_teacher(pending_rows: list) -> np.ndarray:
        """float32 [n, A] distillation targets for the round's stored rows: the policy averaged
        over the six suit views of each row, in the view the row is stored in."""
        planes = np.stack([row[3] for row in pending_rows])
        scalars = np.stack([row[4] for row in pending_rows])
        masks = np.stack([row[5] for row in pending_rows])
        events = np.stack([row[6] for row in pending_rows])
        lengths = np.asarray([row[7] for row in pending_rows], dtype=np.int64)
        if inference_mode == "per_row":
            # One decision at a time: exactly suit_averaged_log_probs on that row.
            return np.concatenate([
                teacher_log_probs(suit_averaged_log_probs(
                    model, planes[i:i + 1], scalars[i:i + 1], masks[i:i + 1], events[i:i + 1],
                    lengths[i:i + 1], device=device)[0])
                for i in range(len(pending_rows))])
        p, s, m, e = stack_views(planes, scalars, masks, events)
        ln = np.tile(lengths, len(SUIT_PERMUTATIONS))
        if teacher_forward is not None:
            logits = teacher_forward(p, s, m, e, ln)[:, :-1]
        else:
            with torch.no_grad():
                logits, _ = model(torch.from_numpy(p).to(device), torch.from_numpy(s).to(device),
                                  torch.from_numpy(m).to(device),
                                  events=torch.from_numpy(e.astype(np.int64)).to(device),
                                  event_lengths=torch.from_numpy(ln).to(device))
        return teacher_log_probs(average_view_log_probs(logits, masks))
```

In `finish_round`, right after the existing `forward_seconds += time.perf_counter() - forward_start` and before `python_start = time.perf_counter()`:

```python
        teacher = None
        if distill:
            teacher_start = time.perf_counter()
            teacher = round_teacher(pending_rows)
            forward_seconds += time.perf_counter() - teacher_start
```

and in its per-row loop, after `ms.seat_hand_ids[seat].append(ms.hand_id)`:

```python
            if teacher is not None:
                ms.seat_teacher[seat].append(teacher[i])
```

In the final `RolloutBatch(...)`, add `teacher_logprobs=arrays.get("teacher"),` after `match_telemetry=match_telemetry,`.

In `_PHASE_TIMER_NOTE`, after the sentence ending `"to synchronise. "` add `"With suit_distill_coef > 0 it also spans the teacher's six-view forward. "`.

In `ai/MODULES.md`, append to the `batched_b2b.py` entry: `` `PPOConfig.suit_distill_coef` > 0 (rejected-on-change): after each round's acting forward, one more no-grad forward over the six suit views of the round's stored rows (`stack_views`, a `_GraphedForward` sized slots × 6 on CUDA; one decision at a time under `per_row`, where it equals `suit_averaged_log_probs` exactly) gives each row's teacher, stored per seat (`_B2bMatchState.seat_teacher`) and written through the sink as `RolloutBatch.teacher_logprobs`. The acting forward, `old_logprobs` and values are unchanged.``

- [ ] **Step 4: Run the tests to verify they pass**

Run: `FH_MAHJONG_BRIDGE_LIB=$(pwd)/build/libfh_mahjong_bridge.so uv run --project ai pytest ai/tests/test_suit_distill.py ai/tests/test_suit_augment.py ai/tests/test_b2b_collector_parity.py ai/tests/test_batched_assembly.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/batched_b2b.py ai/MODULES.md ai/tests/test_suit_distill.py
git commit -m "feat(train): batched collector stores the six-view suit-averaged teacher"
```

---

### Task 5: The distillation term in `ppo_update`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (`masked_distill_kl`; `_ppo_update`: teacher tensors, `metric_names`, `step_losses`, minibatch gather)
- Modify: `ai/src/fh_mahjong_ai/train_b2b.py` (the per-iteration `print`, ~line 2185)
- Modify: `ai/MODULES.md` (the `ppo.py` entry)
- Test: `ai/tests/test_suit_distill.py`

**Interfaces:**
- Consumes: `RolloutBatch.teacher_logprobs`, `PPOConfig.suit_distill_coef`.
- Produces: `masked_distill_kl(masked_logits: torch.Tensor, teacher: torch.Tensor, action_mask: torch.Tensor) -> torch.Tensor` (per-row KL, shape `[N]`); `ppo_update` metrics gain `"distill_kl"` when β > 0.

- [ ] **Step 1: Write the failing tests** — append to `ai/tests/test_suit_distill.py`:

```python
from fh_mahjong_ai.ppo import masked_distill_kl, ppo_update


def _update_batch(n=32, seed=0):
    """A no-event, no-aux net and a batch whose old_logprobs are that net's own."""
    torch.manual_seed(seed)
    model = PolicyValueNet(EnvConfig(), small_model_config())
    env = EnvConfig()
    rng = np.random.default_rng(seed)
    planes = rng.random((n, *env.plane_shape), dtype=np.float32)
    scalars = rng.random((n, env.scalar_features), dtype=np.float32)
    mask = (rng.random((n, env.action_space_size)) < 0.2).astype(np.int8)
    mask[:, 5] = 1
    with torch.no_grad():
        logits, values = model(torch.from_numpy(planes), torch.from_numpy(scalars),
                               torch.from_numpy(mask))
    logp = torch.log_softmax(logits, dim=-1)
    actions = np.array([rng.choice(np.flatnonzero(row)) for row in mask], dtype=np.int64)
    batch = RolloutBatch(planes=planes, scalars=scalars, action_mask=mask, actions=actions,
                         old_logprobs=logp[torch.arange(n), torch.from_numpy(actions)].numpy(),
                         values=values.reshape(-1).numpy(), rewards=np.zeros(n, np.float32),
                         dones=np.ones(n, np.float32))
    return model, batch, logp.numpy()


def _uniform_teacher(mask):
    legal = mask > 0
    teacher = np.full(mask.shape, np.finfo(np.float32).min, np.float32)
    teacher[legal] = np.repeat(-np.log(legal.sum(axis=1)), legal.sum(axis=1)).astype(np.float32)
    return teacher


def _run(model, batch, coef=1.0, lr=0.0, transfer=False):
    n = len(batch)
    config = PPOConfig(device="cpu", collector="batched", suit_distill_coef=coef, ppo_epochs=1,
                       minibatch_size=n, entropy_coef=0.0, minibatch_device_transfer=transfer)
    optimizer = torch.optim.SGD(model.parameters(), lr=lr)
    return ppo_update(model, optimizer, batch, np.zeros(n, np.float32), np.zeros(n, np.float32),
                      config)


def test_masked_distill_kl_matches_the_definition_and_has_finite_gradients():
    mask = torch.tensor([[1, 1, 0, 1], [0, 1, 1, 0]], dtype=torch.int8)
    logits = torch.randn(2, 4).masked_fill(mask == 0, torch.finfo(torch.float32).min)
    logits.requires_grad_(True)
    teacher = torch.tensor([[-1.0, -1.5, torch.finfo(torch.float32).min, -0.9],
                            [torch.finfo(torch.float32).min, -0.2, -1.7,
                             torch.finfo(torch.float32).min]])
    kl = masked_distill_kl(logits, teacher, mask)
    log_pi = torch.log_softmax(logits.detach(), dim=-1)
    for r in range(2):
        legal = mask[r] > 0
        want = (teacher[r][legal].exp() * (teacher[r][legal] - log_pi[r][legal])).sum()
        assert torch.allclose(kl[r], want, atol=1e-6)
    kl.sum().backward()
    assert torch.isfinite(logits.grad).all()


@pytest.mark.parametrize("transfer", [False, True])
def test_kl_is_zero_when_the_teacher_is_the_policy(transfer):
    model, batch, logp = _update_batch()
    teacher = np.where(batch.action_mask > 0, logp, np.finfo(np.float32).min).astype(np.float32)
    metrics = _run(model, replace(batch, teacher_logprobs=teacher), transfer=transfer)
    assert abs(metrics["distill_kl"]) < 1e-6


@pytest.mark.parametrize("transfer", [False, True])
def test_kl_is_positive_otherwise_and_a_step_lowers_it(transfer):
    model, batch, _ = _update_batch()
    batch = replace(batch, teacher_logprobs=_uniform_teacher(batch.action_mask))
    first = _run(model, batch, coef=10.0, lr=0.5, transfer=transfer)["distill_kl"]
    second = _run(model, batch, coef=10.0, lr=0.5, transfer=transfer)["distill_kl"]
    assert first > 0
    assert second < first


def test_a_distilling_update_refuses_a_batch_without_teacher_rows():
    model, batch, _ = _update_batch()
    with pytest.raises(ValueError, match="teacher_logprobs"):
        _run(model, batch)


def test_coefficient_zero_reports_no_distill_metric():
    model, batch, _ = _update_batch()
    assert "distill_kl" not in _run(model, batch, coef=0.0)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_suit_distill.py -q -k "kl or distilling or distill_metric"`
Expected: FAIL with `ImportError: cannot import name 'masked_distill_kl'`.

- [ ] **Step 3: Implement** — in `ppo.py`:

Before `def ppo_update(`:

```python
def masked_distill_kl(masked_logits: torch.Tensor, teacher: torch.Tensor,
                      action_mask: torch.Tensor) -> torch.Tensor:
    """Per-row KL(teacher || softmax(masked_logits)) over legal actions. `teacher` holds
    log-probabilities; its illegal entries may hold anything (float32's finite minimum in a
    batch). Both selections are torch.where, so no inf or NaN reaches the result or its
    gradient, and nothing syncs the host (CUDA-graph safe)."""
    legal = action_mask > 0
    zeros = torch.zeros_like(teacher)
    gap = torch.where(legal, teacher - torch.log_softmax(masked_logits, dim=-1), zeros)
    return (torch.where(legal, teacher.exp(), zeros) * gap).sum(dim=-1)
```

In `_ppo_update`, after the events block (`memprobe.probe("ppo_tensors_ready", ...)` follows it; insert just before that probe):

```python
    distill = config.suit_distill_coef > 0
    teacher_t = teacher_h = None
    if distill:
        if batch.teacher_logprobs is None:
            raise ValueError("suit_distill_coef > 0 but the batch carries no teacher_logprobs")
        teacher_np = np.asarray(batch.teacher_logprobs, dtype=np.float32)
        if host_transfer:
            teacher_h = torch.from_numpy(teacher_np)
        else:
            teacher_t = torch.from_numpy(teacher_np).to(device)
```

Replace the `metric_names` line:

```python
    metric_names = (list(_PPO_METRICS) + (list(_AUX_METRICS) if has_aux else [])
                    + (["distill_kl"] if distill else []))
```

In `step_losses`, immediately before `return loss, torch.stack([m.detach() for m in metrics])`:

```python
        if distill:
            distill_kl = masked_distill_kl(masked_logits, mb["teacher"], mb["mask"]).mean()
            loss = loss + config.suit_distill_coef * distill_kl
            metrics.append(distill_kl)
```

In the minibatch loop, after the `if has_aux:` block that fills `mb["belief"]`/`mb["dealin"]`/`mb["rank"]`:

```python
            if distill:
                mb["teacher"] = (teacher_h.index_select(0, idx_h).to(device) if host_transfer
                                 else teacher_t[idx])
```

In `train_b2b.py`, replace the per-iteration `print(...)` with:

```python
                distill_note = (f" distill_kl={metrics['distill_kl']:.4f}"
                                if "distill_kl" in metrics else "")
                print(f"iter {iteration}: policy_loss={metrics['policy_loss']:.4f} "
                      f"value_loss={metrics['value_loss']:.4f} entropy={metrics['entropy']:.4f} "
                      f"mean_reward={metrics['mean_reward']:.4f}{distill_note}")
```

In `ai/MODULES.md`, append to the `ppo.py` entry: `` `masked_distill_kl` is the per-row KL(teacher ‖ policy) over legal actions; with `suit_distill_coef` > 0, `ppo_update` adds `β · mean(masked_distill_kl)` against `RolloutBatch.teacher_logprobs` (gathered per minibatch on both transfer paths, a graph input on CUDA), reports it as `distill_kl`, and raises if the batch has no teacher rows.``

- [ ] **Step 4: Run the tests to verify they pass**

Run: `FH_MAHJONG_BRIDGE_LIB=$(pwd)/build/libfh_mahjong_bridge.so uv run --project ai pytest ai/tests/test_suit_distill.py ai/tests/test_ppo.py ai/tests/test_b2b_ppo.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suites and the Go gates**

Run: `gofmt -l . && go vet ./... && go test ./...` (expect no output from gofmt, all ok), then `go build -buildmode=c-shared -o build/libfh_mahjong_bridge.so ./cmd/rlbridge && FH_MAHJONG_BRIDGE_LIB=$(pwd)/build/libfh_mahjong_bridge.so uv run --project ai pytest ai/tests -q`
Expected: all pass, including the three collector golden digests.

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/src/fh_mahjong_ai/train_b2b.py ai/MODULES.md ai/tests/test_suit_distill.py
git commit -m "feat(train): PPO distillation term toward the suit-averaged teacher"
```

---

### Task 6: Merge, then the pre-launch measurements

**Files:**
- Modify: `worklog/specs/20261002-suit-distill-lap.md` (fill the pre-launch measurements section)
- Scratch only (not committed): `pace_check.sh`, `distill_kl_probe.py` in the session scratchpad

- [ ] **Step 1: Open and merge the PR.** Push the branch (it carries the spec, this plan and Tasks 1-5), open a PR titled `feat(train): suit distillation (--suit-distill-coef) + lap registration`, wait for CI (`gh pr checks <n>`), then `gh pr merge <n> --merge`. Record the merge commit `M` (`git rev-parse origin/main` after `git fetch`). Confirm `git merge-base --is-ancestor 785b3b85 M` and `git merge-base --is-ancestor 6c354655 M` both succeed.

- [ ] **Step 2: Prepare the box.** Check `ssh wsl 'pgrep -af "[f]h-mj-"'` prints nothing and `ListAgents` shows no session using the GPU (message any live peer that the GPU is being taken). Then:

```bash
ssh wsl 'export PATH=/root/.local/bin:/usr/local/go/bin:/usr/bin:/bin; set -e
[ -d /root/fh-mahjong-distill ] || git clone -q https://github.com/PlasmaNeon/fh-mahjong.git /root/fh-mahjong-distill
cd /root/fh-mahjong-distill && git fetch -q origin && git checkout -q M
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.so ./cmd/rlbridge && uv sync --project ai -q
sha256sum build/libfh_mahjong_bridge.so /root/fh-mahjong-runs/suit-augment-ext-20260930/aug/ckpt/iter_150.pt'
```

Expected: the checkpoint hash starts `3fdfe246`.

- [ ] **Step 3: Pace check (screening seeds, both arms side by side, 3 iterations).** Write `pace_check.sh` in the scratchpad, `scp` it to `/root/pace_check.sh`, run it with `setsid nohup … &`:

```bash
#!/bin/bash
# Pre-launch pace check for 20261002-suit-distill-lap: 3 iterations of each arm side by side on
# screening seeds (base 910000). Outputs are deleted after reading; nothing here is cited.
set -euo pipefail
ROOT=/root/fh-mahjong-runs/suit-distill-pace
REPO=/root/fh-mahjong-distill
INIT=/root/fh-mahjong-runs/suit-augment-ext-20260930/aug/ckpt/iter_150.pt
export PATH=/root/.local/bin:/usr/local/go/bin:/usr/bin:/bin PYTHONUNBUFFERED=1
mkdir -p $ROOT
cd $REPO
arm() {  # <name> <coef>
  uv run --project ai fh-mj-train-b2b --champion $INIT --model-residual-blocks 4 --event-window 128 \
    --privileged-critic --aux-heads --checkpoint-dir $ROOT/$1 --base-seed 910000 --iterations 3 \
    --matches-per-iter 320 --minibatch-size 256 --minibatch-device-transfer \
    --collector batched --pool-slots 256 --lr 2e-5 --entropy-coef 0 --ppo-epochs 2 --gamma 0.99 \
    --match-mode chongci --max-steps-per-episode 4000 --device cuda \
    --bridge-lib $REPO/build/libfh_mahjong_bridge.so --suit-augment --suit-distill-coef $2 \
    > $ROOT/$1.log 2>&1
}
arm distill 1.0 &
arm control 0 &
wait
echo PACE_DONE
```

When `/root/pace-check.log` (its stdout) shows `PACE_DONE`, read the iteration file times (`ls -l --time-style=+%H:%M:%S $ROOT/*/iter_*.pt`), the `iter N:` lines (the distill arm's must show a finite `distill_kl`), and grep both logs for `Traceback|Error|nan`. Seconds per iteration = the gap between `iter_002.pt` and `iter_003.pt` of the slower arm. Then `rm -rf /root/fh-mahjong-runs/suit-distill-pace /root/pace_check.sh`.

- [ ] **Step 4: Starting KL (screening seeds).** Write `distill_kl_probe.py` in the scratchpad, `scp` it to `/root/fh-mahjong-distill/distill_kl_probe.py`, and run `cd /root/fh-mahjong-distill && uv run --project ai python distill_kl_probe.py /root/fh-mahjong-runs/suit-augment-ext-20260930/aug/ckpt/iter_150.pt build/libfh_mahjong_bridge.so`:

```python
"""Pre-launch measurement for 20261002-suit-distill-lap: mean KL(teacher || net) of a checkpoint
over one 320-match collection on screening seeds (base 910000). Not committed."""
import sys
from pathlib import Path

import numpy as np
import torch

from fh_mahjong_ai.batched_b2b import collect_b2b_rollouts_batched, make_b2b_pool
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.ppo import PPOConfig, masked_distill_kl
from fh_mahjong_ai.serving import CheckpointPolicy

checkpoint, bridge = Path(sys.argv[1]), sys.argv[2]
model = CheckpointPolicy.from_checkpoint(checkpoint, device="cuda").model.eval()
env = EnvConfig(bridge_kind="go", bridge_library_path=bridge, match_mode="chongci",
                max_steps_per_episode=4000, oracle_observation=True, event_history_window=128)
cfg = PPOConfig(device="cuda", matches_per_iter=320, max_steps_per_episode=4000,
                match_mode="chongci", collector="batched", pool_slots=256, suit_augment=True,
                suit_distill_coef=1.0)
pool = make_b2b_pool(env, model, cfg, 256)
try:
    batch = collect_b2b_rollouts_batched(env, model, cfg, base_seed=910000, pool=pool)
finally:
    pool.close()
to = lambda a: torch.from_numpy(np.ascontiguousarray(a)).cuda()  # noqa: E731
kls = []
with torch.no_grad():
    for start in range(0, len(batch), 2048):
        rows = slice(start, start + 2048)
        logits, _ = model(to(batch.planes[rows]), to(batch.scalars[rows]), to(batch.action_mask[rows]),
                          events=to(batch.events[rows].astype(np.int64)),
                          event_lengths=to(batch.event_lengths[rows].astype(np.int64)))
        kls.append(masked_distill_kl(logits, to(batch.teacher_logprobs[rows]),
                                     to(batch.action_mask[rows])).cpu())
kl = torch.cat(kls)
print(f"rows={len(kl)} mean_kl={kl.mean():.5f} median={kl.median():.5f} "
      f"p99={torch.quantile(kl, 0.99):.5f}")
```

Then delete `/root/fh-mahjong-distill/distill_kl_probe.py`.

- [ ] **Step 5: Record the measurements.** Under the spec's `## Pre-launch measurements` heading, replace the two numbered intentions with the measured values (commit `M`, bridge hash, seconds per iteration with both arms running, the lap's expected training duration = 150 × that pace, and `rows / mean / median / p99` of the KL). Commit on a branch `docs/suit-distill-prelaunch`, open a PR, merge with `--merge` before Task 7.

---

### Task 7: Launch the lap and record the verdict

**Files:**
- Scratch only: `distill_lap.sh` in the session scratchpad, copied to `/root/distill_lap.sh`
- Modify (after the verdict): `worklog/specs/20261002-suit-distill-lap.md` (Outcome), delete `worklog/plans/20261002-suit-distill-implementation.md`

- [ ] **Step 1: Write and launch the lap script** (`setsid nohup /root/distill_lap.sh M > /root/distill-lap.log 2>&1 &`, after re-checking `pgrep -af "[f]h-mj-"` is empty):

```bash
#!/bin/bash
# Registered suit-distillation lap (worklog/specs/20261002-suit-distill-lap.md): distill (beta 1.0)
# and control (beta 0) arms side by side from extension iter_150, then the fixed iter_150
# evaluation. Usage: distill_lap.sh <commit>
set -euo pipefail
COMMIT=$1
ROOT=/root/fh-mahjong-runs/suit-distill-20261002
REPO=/root/fh-mahjong-distill
INIT=/root/fh-mahjong-runs/suit-augment-ext-20260930/aug/ckpt/iter_150.pt
export PATH=/root/.local/bin:/usr/local/go/bin:/usr/bin:/bin PYTHONUNBUFFERED=1
mkdir -p $ROOT/logs $ROOT/eval
if pgrep -f "[f]h-mj-" > /dev/null; then echo "ABORT: another fh-mj-* job is running"; exit 1; fi
cd $REPO && git fetch -q origin && git checkout -q "$COMMIT"
git merge-base --is-ancestor 785b3b85 HEAD && git merge-base --is-ancestor 6c354655 HEAD
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.so ./cmd/rlbridge
uv sync --project ai -q
BRIDGE=$REPO/build/libfh_mahjong_bridge.so
[ "$(sha256sum $INIT | cut -c1-8)" = 3fdfe246 ] || { echo "ABORT: init changed"; exit 1; }
echo "commit=$(git rev-parse HEAD) bridge=$(sha256sum $BRIDGE | cut -c1-64) init=$(sha256sum $INIT | cut -c1-64)" > $ROOT/manifest.txt
sed -e "s#^RUNS_DIR=.*#RUNS_DIR=$ROOT/logs#" /root/cgroup_guard38.sh > $ROOT/cgroup_guard38.sh
chmod +x $ROOT/cgroup_guard38.sh

train_arm() {  # <name> <coef>
  local unit=sdist-$1
  systemctl reset-failed $unit.service 2>/dev/null || true
  systemd-run --unit $unit -p MemoryHigh=22G -p MemoryMax=24G -p MemorySwapMax=0 -p OOMPolicy=kill \
    --working-directory=$REPO -E PYTHONUNBUFFERED=1 -E PATH=$PATH \
    -p StandardOutput=append:$ROOT/logs/$1.log -p StandardError=append:$ROOT/logs/$1.log \
    /root/.local/bin/uv run --project ai fh-mj-train-b2b \
    --champion $INIT --model-residual-blocks 4 --event-window 128 --privileged-critic --aux-heads \
    --checkpoint-dir $ROOT/$1/ckpt --base-seed 3000000 --iterations 150 \
    --matches-per-iter 320 --minibatch-size 256 --minibatch-device-transfer \
    --collector batched --pool-slots 256 \
    --lr 2e-5 --entropy-coef 0 --ppo-epochs 2 --gamma 0.99 \
    --match-mode chongci --max-steps-per-episode 4000 --device cuda \
    --bridge-lib $BRIDGE --train-state-every 5 --suit-augment --suit-distill-coef $2
  sleep 2
  echo 1 > /sys/fs/cgroup/system.slice/$unit.service/memory.oom.group
  nohup $ROOT/cgroup_guard38.sh $unit 5 > /dev/null 2>&1 &
}
train_arm distill 1.0
train_arm control 0
for name in distill control; do
  while [ "$(systemctl show -p ActiveState --value sdist-$name)" = active ]; do sleep 60; done
  echo "$name: $(systemctl show -p Result --value sdist-$name)" | tee -a $ROOT/manifest.txt
  [ "$(systemctl show -p Result --value sdist-$name)" = success ]
done

EVAL="--event-history-window 128 --model-event-window 128 --model-residual-blocks 4
  --model-privileged-critic --model-aux-heads --duplicate-seats --online-episodes 5000
  --start-seed 3100000 --match-mode chongci --device cuda --bridge-lib $BRIDGE --batched-eval-slots 256"
evaluate() {  # <name> <checkpoint> <symmetry>
  uv run --project ai fh-mj-evaluate --checkpoint $2 $EVAL --symmetry-average $3 \
    --report-output $ROOT/eval/$1.json > $ROOT/logs/eval-$1.log 2>&1
}
evaluate distill-suits $ROOT/distill/ckpt/iter_150.pt suits
evaluate ext150-suits $INIT suits
evaluate control-suits $ROOT/control/ckpt/iter_150.pt suits
evaluate distill-plain $ROOT/distill/ckpt/iter_150.pt none
evaluate ext150-plain $INIT none
cmp() { uv run --project ai fh-mj-compare $ROOT/eval/$1.json $ROOT/eval/$2.json | tee $ROOT/eval/compare-$1-vs-$2.txt; }
echo "=== PRIMARY"; cmp distill-suits ext150-suits
echo "=== secondary"; cmp distill-suits control-suits; cmp distill-plain ext150-plain; cmp control-suits ext150-suits
echo LAP_DONE
```

Expected within 3 minutes: both units `active`, `iter 1:` in each arm's log, the distill arm's line ending in a finite `distill_kl=`.

- [ ] **Step 2: Monitor.** Liveness = unit `active` and a rising `iter_*.pt` count in each arm's `ckpt/`. Do not start any other GPU job until `LAP_DONE`.

- [ ] **Step 3: Record the verdict.** Read `$ROOT/manifest.txt` and `$ROOT/eval/compare-*.txt`; confirm each report has 20,000 episodes and truncation rate 0. Apply the registered rule (primary CI95 lower bound > 0 and large-loss(distill) ≤ large-loss(ext150) + 0.015). Append `## Outcome — <date>: PASS|FAIL` to the spec with the five-row results table, the primary delta with CI95, the three secondary deltas, and (on a pass) the new strongest policy's path and hash. Delete this plan file in the same commit (its work has shipped). Open a docs PR, merge with `--merge`, and update the `project_suit_symmetry` memory.

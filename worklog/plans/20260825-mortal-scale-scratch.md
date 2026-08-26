# Mortal-Scale From-Scratch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `fh-mj-train-bc` and `fh-mj-train-b2b` build and train a 1-D-conv, Mortal-sized `PolicyValueNet` from scratch (BC on heuristic data → PPO), with no change to any existing checkpoint, serving path, or warm-start surgery.

**Architecture:** One new `ModelConfig` field (`kernel_width`, default 3 = today's 3×3) threads through the three conv sites in `model.py` and is recovered from `plane_stem.0.weight.shape[3]` by shape inference. `fh-mj-train-bc` gains the shared `--model-*` flags and writes full `model_config` metadata. `fh-mj-train-b2b` gains a `--scratch [--init-from-bc]` construction branch that sits beside the three existing warm-start branches and reuses everything after model construction unchanged.

**Tech Stack:** Python 3.12, PyTorch, pytest (`uv run --project ai pytest ai/tests`), mock bridge for tests.

**Spec:** `worklog/specs/20260825-mortal-scale-scratch-design.md`

## Global Constraints

- Default `ModelConfig()` must produce a byte-identical `state_dict` (keys and shapes) to today — every existing checkpoint, including the deployed champion, must keep loading.
- `kernel_width ∈ {1, 3}`; anything else raises `ValueError` in `ModelConfig.__post_init__`.
- Any BC-checkpoint key that does not load by exact name+shape in `--init-from-bc` is a hard error, never a warning.
- `--scratch` is mutually exclusive with `--champion`, `--model-growth-blocks > 0`, `--widen-event-hidden > 0`; `--resume-from-state` takes precedence over all of them (the resume path never constructs a model from flags).
- New `ModelConfig` field ⇒ add to `model_config_args.py` (`add_model_config_args`, `model_config_from_args`, `model_config_params`) — `ai/CLAUDE.md` rule.
- Nothing under `internal/`, `proto/`, or `cmd/` changes.
- Run from the worktree root `/Users/plasma/fh-mahjong/.claude/worktrees/mortal-scale-scratch`; test command is `uv run --project ai pytest ai/tests/<file> -q -p no:cacheprovider`. Before the final PR: `gofmt -l .` (must print nothing), `go vet ./...`, `go test ./...`, full `uv run --project ai pytest ai/tests -q -p no:cacheprovider` (baseline: 971 passed, 2 skipped).
- Commit after every task; commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: `ModelConfig.kernel_width`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/config.py` (`ModelConfig` dataclass, `__post_init__`)
- Modify: `ai/src/fh_mahjong_ai/model.py` (`build_plane_scalar_encoders` stem ~line 51, `ResidualBlock.__init__` ~line 293, `ReZeroResidualBlock.__init__` ~line 314, every `ResidualBlock(`/`ReZeroResidualBlock(` construction site, `_shape_inferred_fields` ~line 450)
- Modify: `ai/src/fh_mahjong_ai/model_config_args.py`
- Test: `ai/tests/test_model.py`, `ai/tests/test_checkpoint_loading.py`

**Interfaces:**
- Produces: `ModelConfig.kernel_width: int = 3`; CLI flag `--model-kernel-width`; `model_config_params()` key `"model_kernel_width"`; `infer_model_config` recovers `kernel_width` from shapes.

- [ ] **Step 1: Write the failing tests** (append to `ai/tests/test_model.py`)

```python
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet, infer_model_config
from conftest import SMALL_MODEL


def test_default_kernel_width_keeps_state_dict_shapes() -> None:
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"), ModelConfig(**SMALL_MODEL))
    stem = model.state_dict()["plane_stem.0.weight"]
    assert ModelConfig().kernel_width == 3
    assert tuple(stem.shape[2:]) == (3, 3)
    block = model.state_dict()["plane_blocks.0.layers.0.weight"]
    assert tuple(block.shape[2:]) == (3, 3)


def test_kernel_width_one_builds_1d_convs_and_forwards() -> None:
    env = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env, ModelConfig(**SMALL_MODEL, kernel_width=1))
    sd = model.state_dict()
    assert tuple(sd["plane_stem.0.weight"].shape[2:]) == (3, 1)
    assert tuple(sd["plane_blocks.0.layers.0.weight"].shape[2:]) == (3, 1)
    assert tuple(sd["plane_blocks.0.layers.2.weight"].shape[2:]) == (3, 1)
    planes = torch.zeros(2, 39, 42, 1)
    scalars = torch.zeros(2, 58)
    mask = torch.ones(2, 204, dtype=torch.int8)
    logits, value = model(planes, scalars, mask)
    assert logits.shape == (2, 204) and value.shape == (2,)


def test_kernel_width_one_has_one_third_conv_params() -> None:
    env = EnvConfig(bridge_kind="mock")
    wide = PolicyValueNet(env, ModelConfig(**SMALL_MODEL, kernel_width=3))
    narrow = PolicyValueNet(env, ModelConfig(**SMALL_MODEL, kernel_width=1))
    assert narrow.plane_blocks[0].layers[0].weight.numel() * 3 == wide.plane_blocks[0].layers[0].weight.numel()


def test_kernel_width_is_shape_inferred() -> None:
    env = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env, ModelConfig(**SMALL_MODEL, kernel_width=1))
    inferred = infer_model_config(model.state_dict())
    assert inferred.kernel_width == 1
    assert inferred == ModelConfig(**SMALL_MODEL, kernel_width=1)


def test_kernel_width_growth_blocks_follow_config() -> None:
    env = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env, ModelConfig(**SMALL_MODEL, kernel_width=1, growth_blocks=1))
    assert tuple(model.state_dict()["growth.0.layers.0.weight"].shape[2:]) == (3, 1)


@pytest.mark.parametrize("bad", [0, 2, 5])
def test_kernel_width_rejects_values_outside_one_and_three(bad: int) -> None:
    with pytest.raises(ValueError, match="kernel_width"):
        ModelConfig(**SMALL_MODEL, kernel_width=bad)
```

Also append to `ai/tests/test_checkpoint_loading.py` (metadata cross-check must catch a lie):

```python
def test_infer_model_config_rejects_kernel_width_metadata_mismatch() -> None:
    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.model import PolicyValueNet, infer_model_config
    from fh_mahjong_ai.storage import model_config_metadata
    from conftest import SMALL_MODEL

    model = PolicyValueNet(EnvConfig(bridge_kind="mock"), ModelConfig(**SMALL_MODEL, kernel_width=1))
    lying = model_config_metadata(ModelConfig(**SMALL_MODEL, kernel_width=3))
    with pytest.raises(ValueError):
        infer_model_config(model.state_dict(), {"model_config": lying})
```

(Check the top of `test_checkpoint_loading.py` for its existing imports; `pytest` is already imported there — if not, add it.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_model.py ai/tests/test_checkpoint_loading.py -q -p no:cacheprovider -k kernel_width`
Expected: FAIL — `TypeError: ModelConfig.__init__() got an unexpected keyword argument 'kernel_width'`

- [ ] **Step 3: Add the field and validation** in `ai/src/fh_mahjong_ai/config.py`

Inside `ModelConfig`, after `growth_blocks: int = 0`:

```python
    # --- mortal-scale-scratch: conv kernel width over the 42x1 plane axis.
    # 3 = the historical 3x3 kernel (default, state_dict-identical to today);
    # 1 = a (3,1) 1-D kernel (Mortal-style; two-thirds fewer conv params on a
    # width-1 plane, where a 3x3 kernel only ever multiplies padding).
    kernel_width: int = 3
```

At the end of `__post_init__` (after the existing `event_window` checks):

```python
        if self.kernel_width not in (1, 3):
            raise ValueError(f"kernel_width must be 1 or 3, got {self.kernel_width}")
```

- [ ] **Step 4: Thread `kernel_width` through `model.py`**

In `build_plane_scalar_encoders`:

```python
    kernel = (3, model_config.kernel_width)
    padding = (1, model_config.kernel_width // 2)
    plane_stem = nn.Sequential(
        nn.Conv2d(channels, model_config.channels, kernel_size=kernel, padding=padding),
        nn.GELU(),
    )
    plane_blocks = nn.Sequential(
        *[
            ResidualBlock(
                model_config.channels,
                channel_attention=model_config.channel_attention,
                attention_ratio=model_config.channel_attention_ratio,
                kernel_width=model_config.kernel_width,
            )
            for _ in range(model_config.residual_blocks)
        ]
    )
```

`ResidualBlock` and `ReZeroResidualBlock` — add a keyword parameter and use it in both convs:

```python
    def __init__(self, channels: int, channel_attention: bool = False, attention_ratio: int = 16,
                 kernel_width: int = 3) -> None:
        super().__init__()
        kernel = (3, kernel_width)
        padding = (1, kernel_width // 2)
        self.layers = nn.Sequential(
            nn.Conv2d(channels, channels, kernel_size=kernel, padding=padding),
            nn.GELU(),
            nn.Conv2d(channels, channels, kernel_size=kernel, padding=padding),
        )
```

Find every other construction site with `grep -n "ResidualBlock(" ai/src/fh_mahjong_ai/*.py` (the `growth` stack in `PolicyValueNet.__init__` ~line 163, and any in `train_b2b.py`'s `grow_b2b_model`) and pass `kernel_width=model_config.kernel_width` at each.

In `_shape_inferred_fields`, add to the `fields = dict(...)`:

```python
        kernel_width=int(state_dict["plane_stem.0.weight"].shape[3]),
```

Then read `_verify_metadata_matches_shapes` (grep for it) and confirm it compares every key returned by `_shape_inferred_fields` against metadata; if it iterates an explicit field list instead, add `"kernel_width"` to that list.

- [ ] **Step 5: Add the CLI flag and params key** in `ai/src/fh_mahjong_ai/model_config_args.py`

In `add_model_config_args`, after `--model-residual-blocks`:

```python
    parser.add_argument("--model-kernel-width", type=int, choices=(1, 3), default=defaults.kernel_width,
                        help="conv kernel width over the plane axis: 3 = historical 3x3 "
                             "(default), 1 = Mortal-style (3,1) 1-D kernels")
```

In `model_config_from_args`, add `kernel_width=args.model_kernel_width,` after `residual_blocks=...`. In `model_config_params`, add `"model_kernel_width": model_config.kernel_width,` after `"model_residual_blocks"`.

- [ ] **Step 6: Run the new tests and the model/loading/growth/gru-width/serving suites**

Run: `uv run --project ai pytest ai/tests/test_model.py ai/tests/test_checkpoint_loading.py ai/tests/test_b2b_growth.py ai/tests/test_gru_width.py ai/tests/test_serving.py ai/tests/test_serving_parity.py -q -p no:cacheprovider`
Expected: all PASS (the new ones plus every pre-existing test — the default path must be unchanged).

- [ ] **Step 7: Prove the default `state_dict` is byte-identical**

Run:
```bash
uv run --project ai python -c "
import torch
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet, infer_model_config
p = torch.load('ai/checkpoints/anchors/b2b-anchor075-restart-iter075.pt', map_location='cpu')
cfg = infer_model_config(p['model'], p.get('metadata'))
m = PolicyValueNet(EnvConfig(), cfg)
missing, unexpected = m.load_state_dict(p['model'], strict=True), None
print('anchor loads strict; kernel_width =', cfg.kernel_width)
"
```
Expected: prints `anchor loads strict; kernel_width = 3` with no exception.

- [ ] **Step 8: Commit**

```bash
git add ai/src/fh_mahjong_ai/config.py ai/src/fh_mahjong_ai/model.py ai/src/fh_mahjong_ai/model_config_args.py ai/tests/test_model.py ai/tests/test_checkpoint_loading.py
git commit -m "feat(ai): ModelConfig.kernel_width for 1-D plane convs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `fh-mj-train-bc` builds an arbitrary `ModelConfig` and records it

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/train_bc.py` (`train_bc` signature ~line 31, model construction ~line 86, `save_checkpoint` call(s), `main()` argparse)
- Test: `ai/tests/test_train_bc.py`

**Interfaces:**
- Consumes: `add_model_config_args`, `model_config_from_args`, `model_config_params` from `fh_mahjong_ai.model_config_args`; `model_config_metadata` from `fh_mahjong_ai.storage`.
- Produces: `train_bc(..., model_config: ModelConfig | None = None)`; every `epoch_*.pt` it writes carries `metadata={"model_config": model_config_metadata(model_config), "method": "behavior_cloning"}`.

- [ ] **Step 1: Write the failing test** (append to `ai/tests/test_train_bc.py`)

```python
def test_train_bc_accepts_model_config_and_records_it(tmp_path: Path) -> None:
    import torch
    from fh_mahjong_ai.config import ModelConfig
    from fh_mahjong_ai.model import infer_model_config

    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    _make_dataset(data_path, n=20)
    model_config = ModelConfig(channels=8, residual_blocks=2, kernel_width=1,
                               event_window=8, privileged_critic=True, aux_heads=True)
    train_bc(data_path=data_path, checkpoint_dir=ckpt_dir, epochs=1, batch_size=8,
             device="cpu", model_config=model_config)
    payload = torch.load(ckpt_dir / "epoch_001.pt", map_location="cpu")
    assert payload["metadata"]["model_config"]["kernel_width"] == 1
    assert infer_model_config(payload["model"], payload["metadata"]) == model_config
    assert "event_encoder.gru.weight_ih_l0" in payload["model"]


def test_train_bc_default_model_config_is_unchanged(tmp_path: Path) -> None:
    import torch
    from fh_mahjong_ai.config import ModelConfig

    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    _make_dataset(data_path, n=20)
    train_bc(data_path=data_path, checkpoint_dir=ckpt_dir, epochs=1, batch_size=8, device="cpu")
    payload = torch.load(ckpt_dir / "epoch_001.pt", map_location="cpu")
    assert payload["metadata"]["model_config"] == ModelConfig().__dict__
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_train_bc.py -q -p no:cacheprovider -k model_config`
Expected: FAIL — `TypeError: train_bc() got an unexpected keyword argument 'model_config'`

- [ ] **Step 3: Implement**

In `train_bc`'s signature add `model_config: Optional[ModelConfig] = None,` (after `validation_batch_size`). Replace

```python
    env_config = EnvConfig()
    model_config = ModelConfig()
```
with
```python
    env_config = EnvConfig()
    if model_config is None:
        model_config = ModelConfig()
```

Find every `save_checkpoint(` call in `train_bc.py` (grep) and pass `metadata={"model_config": model_config_metadata(model_config), "method": "behavior_cloning"}` (merge into any metadata dict already passed). Import `model_config_metadata` from `fh_mahjong_ai.storage` alongside the existing storage imports. Add `**model_config_params(model_config)` to the `log_params({...})` dict and `"model_config": model_config_metadata(model_config)` to the `report` dict.

In `main()`: `from fh_mahjong_ai.model_config_args import add_model_config_args, model_config_from_args, model_config_params`; call `add_model_config_args(parser)` after the existing flags; pass `model_config=model_config_from_args(args)` into `train_bc(...)`.

Note: the B2b event encoder receives no events in BC — `PolicyValueNet.encode` substitutes zeros when `events is None`, so those weights simply get no gradient. That is the intended behaviour (spec §4.3); do not add event handling to BC.

- [ ] **Step 4: Run the BC suite**

Run: `uv run --project ai pytest ai/tests/test_train_bc.py -q -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/train_bc.py ai/tests/test_train_bc.py
git commit -m "feat(ai): fh-mj-train-bc takes --model-* flags and records model_config

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `fh-mj-train-b2b --scratch [--init-from-bc]`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/train_b2b.py` (new `build_scratch_model` beside `build_b2b_model` ~line 67; `train_b2b` signature ~line 894; construction branch ~line 1363; checkpoint `metadata` dict ~line 1570)
- Modify: `ai/src/fh_mahjong_ai/scripts/train_b2b.py` (argparse + validation ~lines 16, 149–161, 190)
- Test: `ai/tests/test_b2b_training.py`

**Interfaces:**
- Consumes: BC checkpoints from Task 2 (`payload["model"]`, `payload["metadata"]["model_config"]`).
- Produces:
  ```python
  SCRATCH_BC_PREFIXES = ("plane_stem.", "plane_blocks.", "plane_head.", "scalar_encoder.", "trunk.", "policy_head.")

  def build_scratch_model(env_config: EnvConfig, model_config: ModelConfig, device: str = "cpu",
                          bc_checkpoint: Optional[Path] = None) -> PolicyValueNet
  ```
  `train_b2b(..., scratch: bool = False, init_from_bc: Optional[Path] = None)`. Checkpoint metadata gains `"init": {"kind": "scratch"|"champion", "bc_checkpoint_sha256": str|None}`.

- [ ] **Step 1: Write the failing tests** (append to `ai/tests/test_b2b_training.py`)

```python
def _bc_checkpoint(tmp_path, model_config):
    """A BC-stage checkpoint: full net, saved with model_config metadata (Task 2 format)."""
    from fh_mahjong_ai.storage import model_config_metadata
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"), model_config)
    path = tmp_path / "bc.pt"
    save_checkpoint(path, model, metadata={"model_config": model_config_metadata(model_config)})
    return model, path


def test_build_scratch_model_is_random_init_with_full_config(tmp_path):
    from fh_mahjong_ai.train_b2b import build_scratch_model
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    a = build_scratch_model(EnvConfig(bridge_kind="mock"), cfg)
    b = build_scratch_model(EnvConfig(bridge_kind="mock"), cfg)
    assert a.model_config == cfg
    assert tuple(a.state_dict()["plane_stem.0.weight"].shape[2:]) == (3, 1)
    assert not torch.equal(a.trunk[0].weight, b.trunk[0].weight)  # no anchor, no parity


def test_build_scratch_model_init_from_bc_loads_exactly_the_bc_prefixes(tmp_path):
    from fh_mahjong_ai.train_b2b import SCRATCH_BC_PREFIXES, build_scratch_model
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    bc_model, bc_path = _bc_checkpoint(tmp_path, cfg)
    model = build_scratch_model(EnvConfig(bridge_kind="mock"), cfg, bc_checkpoint=bc_path)
    bc_sd, sd = bc_model.state_dict(), model.state_dict()
    for key in sd:
        if key.startswith(SCRATCH_BC_PREFIXES):
            assert torch.equal(sd[key], bc_sd[key]), key
    assert not torch.equal(sd["value_head.0.weight"], bc_sd["value_head.0.weight"])
    assert not torch.equal(sd["event_encoder.gru.weight_ih_l0"], bc_sd["event_encoder.gru.weight_ih_l0"])


def test_build_scratch_model_init_from_bc_rejects_shape_mismatch(tmp_path):
    from fh_mahjong_ai.train_b2b import build_scratch_model
    bc_cfg = ModelConfig(**SMALL_MODEL, kernel_width=3, event_window=8, privileged_critic=True, aux_heads=True)
    _, bc_path = _bc_checkpoint(tmp_path, bc_cfg)
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    with pytest.raises(RuntimeError, match="init-from-bc"):
        build_scratch_model(EnvConfig(bridge_kind="mock"), cfg, bc_checkpoint=bc_path)


def test_build_scratch_model_init_from_bc_rejects_missing_prefix(tmp_path):
    from fh_mahjong_ai.train_b2b import build_scratch_model
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    _, bc_path = _bc_checkpoint(tmp_path, cfg)
    payload = torch.load(bc_path, map_location="cpu")
    del payload["model"]["policy_head.weight"]
    torch.save(payload, bc_path)
    with pytest.raises(RuntimeError, match="policy_head.weight"):
        build_scratch_model(EnvConfig(bridge_kind="mock"), cfg, bc_checkpoint=bc_path)


def test_train_b2b_scratch_two_iters_mock_records_init(tmp_path):
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=2, matches_per_iter=2,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="classic")
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    _, bc_path = _bc_checkpoint(tmp_path, cfg)
    ckpt_dir = tmp_path / "run"
    history = train_b2b(env, cfg, None, ckpt_dir, config, base_seed=3,
                        scratch=True, init_from_bc=bc_path)
    assert len(history) == 2
    payload = torch.load(ckpt_dir / "iter_002.pt", map_location="cpu")
    assert payload["metadata"]["init"]["kind"] == "scratch"
    assert len(payload["metadata"]["init"]["bc_checkpoint_sha256"]) == 64
    assert payload["metadata"]["model_config"]["kernel_width"] == 1


def test_train_b2b_scratch_rejects_champion_and_surgeries(tmp_path):
    env39, champion_path = _champion(tmp_path)
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=1, matches_per_iter=2, max_steps_per_episode=16,
                       ppo_epochs=1, minibatch_size=8, num_workers=1, match_mode="classic")
    cfg = ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True, aux_heads=True)
    with pytest.raises(ValueError, match="scratch"):
        train_b2b(env, cfg, champion_path, tmp_path / "a", config, scratch=True)
    with pytest.raises(ValueError, match="scratch"):
        train_b2b(env, cfg, None, tmp_path / "b", config, scratch=True, growth_blocks=1)
    with pytest.raises(ValueError, match="scratch"):
        train_b2b(env, cfg, None, tmp_path / "c", config, scratch=False)  # no champion, no scratch
```

Check how the existing `test_train_b2b_two_iters_mock` asserts on `history`/checkpoint names (lines ~93–115) and match its checkpoint filename pattern if it is not `iter_002.pt`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_b2b_training.py -q -p no:cacheprovider -k scratch`
Expected: FAIL — `ImportError: cannot import name 'build_scratch_model'`.

- [ ] **Step 3: Implement `build_scratch_model`** in `ai/src/fh_mahjong_ai/train_b2b.py`, directly after `build_b2b_model`

```python
SCRATCH_BC_PREFIXES = ("plane_stem.", "plane_blocks.", "plane_head.",
                       "scalar_encoder.", "trunk.", "policy_head.")


def build_scratch_model(env_config: EnvConfig, model_config: ModelConfig, device: str = "cpu",
                        bc_checkpoint: Optional[Path] = None) -> PolicyValueNet:
    """mortal-scale-scratch: a freshly initialised B2b net (no anchor, no
    surgery, no step-0 parity). With `bc_checkpoint`, the BC-stage weights for
    exactly `SCRATCH_BC_PREFIXES` are copied by name+shape; every other module
    (event encoder, privileged critic, value/aux/risk/q heads) keeps its random
    init. Any BC key under those prefixes that is absent from the model, or any
    model key under those prefixes absent from the BC checkpoint, or any shape
    mismatch, is a hard error -- a silent partial load is this lane's known
    failure mode. `env_config` must be the 39ch config (see `_b2b_model_env_config`)."""
    model = PolicyValueNet(env_config, model_config).to(device)
    if bc_checkpoint is None:
        model.eval()
        return model
    payload = torch.load(Path(bc_checkpoint), map_location="cpu")
    bc_state = payload["model"]
    target = model.state_dict()
    wanted_model = {k for k in target if k.startswith(SCRATCH_BC_PREFIXES)}
    wanted_bc = {k for k in bc_state if k.startswith(SCRATCH_BC_PREFIXES)}
    missing = sorted(wanted_model - wanted_bc)
    extra = sorted(wanted_bc - wanted_model)
    mismatched = sorted(k for k in wanted_model & wanted_bc
                        if tuple(bc_state[k].shape) != tuple(target[k].shape))
    if missing or extra or mismatched:
        raise RuntimeError(
            "--init-from-bc: BC checkpoint does not match the scratch model on the "
            f"loaded prefixes (missing={missing[:6]}, extra={extra[:6]}, "
            f"shape_mismatch={mismatched[:6]}) -- the BC stage must be trained with the "
            "same --model-* flags as this run"
        )
    with torch.no_grad():
        for key in wanted_model:
            target[key].copy_(bc_state[key].to(target[key].device))
    model.eval()
    return model
```

- [ ] **Step 4: Wire it into `train_b2b`**

Signature: add `scratch: bool = False, init_from_bc: Optional[Path] = None` after `accept_legacy_unpinned_state`. Immediately at the top of the function body (before any directory inspection):

```python
    if resume_from_state is None:
        if scratch and champion_checkpoint is not None:
            raise ValueError("scratch=True cannot be combined with a champion checkpoint")
        if scratch and (growth_blocks > 0 or widen_event_hidden > 0):
            raise ValueError("scratch=True cannot be combined with growth_blocks/widen_event_hidden surgery")
        if not scratch and champion_checkpoint is None:
            raise ValueError("champion_checkpoint is required unless scratch=True or resume_from_state is given")
        if init_from_bc is not None and not scratch:
            raise ValueError("init_from_bc requires scratch=True")
```

Construction branch (the `if growth_blocks > 0: ... elif widen_event_hidden > 0: ... else:` block ~line 1363) — add a branch *before* the final `else`:

```python
            elif scratch:
                model = build_scratch_model(_b2b_model_env_config(env_config), model_config, device,
                                            bc_checkpoint=init_from_bc)
```

Compute once, next to where `run_id` is established for a fresh run:

```python
    init_meta = {
        "kind": "scratch" if scratch else "champion",
        "bc_checkpoint_sha256": (hashlib.sha256(Path(init_from_bc).read_bytes()).hexdigest()
                                 if init_from_bc is not None else None),
    }
```
(`import hashlib` at the top if not already present.) On the resume path, read `init_meta` back from the state file if it is stored there; if the existing `train_state` payload has no such slot, set `init_meta = {"kind": "resumed", "bc_checkpoint_sha256": None}` — do not extend the train-state schema in this task.

Add `"init": init_meta,` to the checkpoint `metadata={...}` dict (~line 1570), after `"run_id": run_id,`.

- [ ] **Step 5: CLI** in `ai/src/fh_mahjong_ai/scripts/train_b2b.py`

Add after `--champion`:

```python
    p.add_argument("--scratch", action="store_true", default=False,
                   help="mortal-scale-scratch: build the B2b net from random init instead of "
                        "warm-starting from --champion (mutually exclusive with --champion, "
                        "--model-growth-blocks > 0 and --widen-event-hidden > 0)")
    p.add_argument("--init-from-bc", type=Path, default=None,
                   help="with --scratch: BC-stage checkpoint (fh-mj-train-bc, same --model-* "
                        "flags) whose plane trunk / scalar encoder / trunk / policy head are "
                        "copied in by exact name+shape; everything else stays random")
```

Replace the existing `if args.champion is None and args.resume_from_state is None: p.error(...)` with:

```python
    if args.resume_from_state is None:
        if args.scratch and args.champion is not None:
            p.error("--scratch and --champion are mutually exclusive")
        if args.scratch and (args.model_growth_blocks > 0 or args.widen_event_hidden > 0):
            p.error("--scratch cannot be combined with --model-growth-blocks or --widen-event-hidden")
        if not args.scratch and args.champion is None:
            p.error("--champion is required unless --scratch or --resume-from-state is given")
        if args.init_from_bc is not None and not args.scratch:
            p.error("--init-from-bc requires --scratch")
```

Pass `scratch=args.scratch, init_from_bc=args.init_from_bc` into the `train_b2b(...)` call.

- [ ] **Step 6: Run the B2b suites**

Run: `uv run --project ai pytest ai/tests/test_b2b_training.py ai/tests/test_b2b_resume.py ai/tests/test_b2b_growth.py ai/tests/test_gru_width.py ai/tests/test_b2b_ppo.py -q -p no:cacheprovider`
Expected: all PASS, including the pre-existing warm-start and resume tests (the resume `config_echo` already serialises the full `ModelConfig`, so `kernel_width` round-trips without changes to `train_state.py`).

- [ ] **Step 7: CLI smoke with the mock bridge**

Run:
```bash
uv run --project ai fh-mj-train-b2b --scratch --bridge-kind mock --checkpoint-dir /private/tmp/claude-501/-Users-plasma-fh-mahjong/dc7ce201-8d9e-40bf-9ebf-fce4bd5e6960/scratchpad/b2b-scratch-smoke \
  --model-channels 16 --model-residual-blocks 2 --model-kernel-width 1 --event-window 8 \
  --iterations 1 --matches-per-iter 2 --max-steps-per-episode 16 --ppo-epochs 1 --minibatch-size 8 --num-workers 1 --match-mode classic
```
Expected: exits 0, writes `iter_001.pt`. Then confirm `--scratch --champion x` errors with the mutual-exclusion message.

- [ ] **Step 8: Commit**

```bash
git add ai/src/fh_mahjong_ai/train_b2b.py ai/src/fh_mahjong_ai/scripts/train_b2b.py ai/tests/test_b2b_training.py
git commit -m "feat(ai): fh-mj-train-b2b --scratch [--init-from-bc] random-init path

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Docs, full gates, PR

**Files:**
- Modify: `ai/CLAUDE.md` (campaign vocabulary list ~line 120; `fh-mj-train-b2b` row ~line 45; the architecture-flag list ~line 186)
- Modify: `worklog/specs/20260825-mortal-scale-scratch-design.md` (status line only)

- [ ] **Step 1: Update `ai/CLAUDE.md`**

Campaign vocabulary — add after the `data-scale-960` bullet:

```markdown
- **mortal-scale-scratch** — `ModelConfig.kernel_width` (1 = Mortal-style (3,1) convs), `fh-mj-train-bc --model-*`, and `fh-mj-train-b2b --scratch [--init-from-bc]` — BC → PPO from random init, no anchor.
```

Row for `fh-mj-train-b2b`: change to `| `fh-mj-train-b2b` | Spec B2b: event history + privileged critic + aux heads; `--scratch [--init-from-bc]` for random-init runs |`.

Architecture-flag list (~line 186): add `--model-kernel-width` to the parenthesised list.

Add under the existing checkpoint-loading notes (near line 163): `- \`kernel_width\` IS shape-inferred (\`plane_stem.0.weight.shape[3]\`); metadata that disagrees with it is rejected.`

- [ ] **Step 2: Spec status**

In the spec header, change `**Status:** DRAFT — awaiting user review, then the mandatory Codex consult…` to `**Status:** code merged-pending (PR open); Codex consult on thread \`01a0147d\` required before any lap launches.`

- [ ] **Step 3: Run every CI gate**

```bash
gofmt -l .            # must print nothing
go vet ./...
go test ./...
uv run --project ai pytest ai/tests -q -p no:cacheprovider
```
Expected: gofmt silent; vet/test clean; AI suite ≥ 971 + new tests passed, 0 failed.

- [ ] **Step 4: Commit and open the PR**

```bash
git add ai/CLAUDE.md worklog/specs/20260825-mortal-scale-scratch-design.md
git commit -m "docs(ai): mortal-scale-scratch flags and kernel_width notes

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push -u origin experiment/mortal-scale-scratch
gh pr create --base main --title "feat(ai): mortal-scale from-scratch training path (kernel_width, BC model flags, --scratch)" --body "$(cat <<'EOF'
Implements the code half of `worklog/specs/20260825-mortal-scale-scratch-design.md`:

- `ModelConfig.kernel_width` (default 3, state_dict-identical; 1 = Mortal-style (3,1) convs), shape-inferred and metadata-cross-checked
- `fh-mj-train-bc --model-*` flags; BC checkpoints now carry full `model_config` metadata
- `fh-mj-train-b2b --scratch [--init-from-bc]` random-init branch; strict by-name BC load; `metadata["init"]`

No change to Go, proto, serving, or any warm-start surgery. No training authorized by this PR — the lap needs the Codex consult first.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review

- **Spec coverage:** §4.1 → Task 1; §4.2 → Task 3; §4.3 → Task 2; §8.2 (PR, CLAUDE.md) → Task 4. §5 (protocol/runbook) and §8.3–8.4 are deliberately *not* in this plan — they follow the Codex consult, which this plan does not pre-empt.
- **Placeholders:** none; every step has code or an exact command.
- **Type consistency:** `build_scratch_model(env_config, model_config, device, bc_checkpoint)` and `SCRATCH_BC_PREFIXES` are named identically in Task 3's tests and implementation; `train_bc(model_config=...)` matches Task 2's tests; the `--model-kernel-width` flag, `kernel_width` field, and `"model_kernel_width"` params key are consistent across Tasks 1–3.

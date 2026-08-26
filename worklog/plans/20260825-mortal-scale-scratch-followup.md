# Mortal-Scale Scratch — Amendment 1 Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the three code items Amendment 1 requires before any lap — BC early stopping on validation cross-entropy with best-checkpoint selection (A1 §3), the two-group learning-rate schedule (A1 §6), and the step-zero BC→B2b transfer gate (A1 §4) — then write the runbook and status file.

**Architecture:** Each item is additive and default-off, so every existing run/test path is byte-identical. BC: validation helpers gain a masked cross-entropy, the epoch loop gains patience + `best.pt`. PPO: `PPOConfig` gains `head_lr`/`head_lr_iters`; `train_b2b` builds two AdamW parameter groups keyed by `SCRATCH_BC_PREFIXES` (a pure function of parameter names, so resume rebuilds identical groups) and sets group lrs by iteration (idempotent). Transfer gate: a pure function in `train_b2b.py` run right after `build_scratch_model` with a BC checkpoint, recorded in `metadata["init"]["transfer_gate"]`, fail-closed.

**Tech Stack:** Python 3.12, PyTorch, pytest via `uv run --project ai pytest ai/tests/<file> -q -p no:cacheprovider`. Mock bridge for tests.

**Spec:** `worklog/specs/20260825-mortal-scale-scratch-design.md` — §4 plus **Amendment 1** (items 3, 4, 6 are the contract for this plan).

## Global Constraints

- Default behaviour unchanged: `patience=None` (no early stop, no `best.pt`), `head_lr=None` (single AdamW group at `config.lr`), transfer gate runs only when `init_from_bc` is given.
- Amendment 1 §6 exact values: BC-loaded parameters at `2e-5` throughout; parameters absent from BC (event encoder, value/Q, privileged critic, aux and risk heads) at `2e-4` for iterations 1–25, then `2e-5` from iteration 26, **retaining optimizer moments** (never rebuild the optimizer at the switch).
- Amendment 1 §3 exact values: patience 5 consecutive epochs without an absolute validation-CE improvement of `1e-4`; min 5 / max 30 epochs; select the lowest-validation-CE checkpoint. These are CLI defaults for the runbook, not hard-coded — the function takes them as parameters.
- Amendment 1 §4: prove step-zero equality for legal-action logits, probabilities, greedy actions, and loaded tensor bytes under zeroed events; record BC SHA, loaded/unloaded key sets; resume must preserve them (they live in `metadata["init"]`, which Task 3 of the first plan already persists in `train_state.pt`).
- Group membership = `name.startswith(SCRATCH_BC_PREFIXES)` — never a saved list, so a resumed run rebuilds the same groups and `optimizer.load_state_dict` matches.
- New `PPOConfig` fields flow through the existing `config_echo` automatically (asdict); do not touch `_RESUME_IGNORED_FIELDS`/`_RESUME_LOGGED_FIELDS`.
- `train_b2b.py` keeps every existing guard and ordering; add code only where named.
- Nothing under `internal/`, `proto/`, `cmd/` changes. Commit trailers: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Work from `/Users/plasma/fh-mahjong/.claude/worktrees/mortal-scale-scratch`. Final gates before PR update: `gofmt -l .`, `go vet ./...`, `go test ./...`, `cd web && npx tsc && npx vitest run`, full AI suite (baseline 994 passed / 2 skipped).

---

### Task 1: BC validation cross-entropy, patience, `best.pt`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/evaluate.py` (`compute_action_agreement_from_batches` ~line 655–706 and `compute_action_agreement` — the sibling that takes transitions)
- Modify: `ai/src/fh_mahjong_ai/scripts/train_bc.py` (`train_bc` signature ~line 31, epoch loop ~line 157–260, `main()` argparse ~line 300+)
- Test: `ai/tests/test_evaluate.py`, `ai/tests/test_train_bc.py`

**Interfaces:**
- Produces: validation report key `"mean_cross_entropy": float` (mean over validation rows of `-log softmax(masked_logits)[action_id]`); `train_bc(..., patience: Optional[int] = None, min_delta: float = 1e-4, min_epochs: int = 1)`; on early stop or completion with `patience` set, writes `checkpoint_dir / "best.pt"` (byte copy of the lowest-val-CE `epoch_*.pt`) and sets `report["best_epoch"]`, `report["best_validation_cross_entropy"]`, `report["stopped_early"]`, `report["epochs_run"]`; CLI `--patience`, `--min-delta`, `--min-epochs`.

- [ ] **Step 1: Failing tests** — append to `ai/tests/test_evaluate.py`:

```python
def test_offline_agreement_reports_mean_cross_entropy() -> None:
    import numpy as np
    import torch
    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.evaluate import compute_action_agreement_from_batches
    from fh_mahjong_ai.model import PolicyValueNet
    from conftest import SMALL_MODEL

    torch.manual_seed(0)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"), ModelConfig(**SMALL_MODEL))
    rng = np.random.default_rng(1)
    planes = rng.random((6, 39, 42, 1), dtype=np.float32)
    scalars = rng.random((6, 58), dtype=np.float32)
    mask = np.ones((6, 204), dtype=np.int8)
    action_ids = rng.integers(0, 204, size=6)
    batches = [{"planes": planes, "scalars": scalars, "action_mask": mask, "action_ids": action_ids}]
    report = compute_action_agreement_from_batches(model, batches, device="cpu")
    model.eval()
    with torch.no_grad():
        logits, _ = model(torch.from_numpy(planes), torch.from_numpy(scalars), torch.from_numpy(mask))
        expected = torch.nn.functional.cross_entropy(logits, torch.from_numpy(action_ids)).item()
    assert report["mean_cross_entropy"] == pytest.approx(expected, abs=1e-5)
```

Append to `ai/tests/test_train_bc.py`:

```python
def test_train_bc_patience_stops_early_and_writes_best(tmp_path: Path, monkeypatch) -> None:
    import torch
    from fh_mahjong_ai.scripts import train_bc as train_bc_mod

    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    _make_dataset(data_path, n=40)
    # Deterministic validation CE sequence: improves twice, then flat.
    seq = iter([2.0, 1.5, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4])
    real = train_bc_mod.compute_action_agreement

    def fake(model, transitions, **kw):
        out = real(model, transitions, **kw)
        out["mean_cross_entropy"] = next(seq)
        return out

    monkeypatch.setattr(train_bc_mod, "compute_action_agreement", fake)
    report_path = tmp_path / "report.json"
    train_bc(data_path=data_path, checkpoint_dir=ckpt_dir, epochs=10, batch_size=8, device="cpu",
             patience=2, min_delta=1e-4, min_epochs=1, report_path=report_path)
    report = json.loads(report_path.read_text())
    assert report["stopped_early"] is True
    assert report["epochs_run"] == 5          # best at 3; epochs 4 and 5 without improvement -> stop
    assert report["best_epoch"] == 3
    assert (ckpt_dir / "best.pt").read_bytes() == (ckpt_dir / "epoch_003.pt").read_bytes()
    assert torch.load(ckpt_dir / "best.pt", map_location="cpu")["metadata"]["model_config"]


def test_train_bc_min_epochs_blocks_early_stop(tmp_path: Path, monkeypatch) -> None:
    from fh_mahjong_ai.scripts import train_bc as train_bc_mod
    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    _make_dataset(data_path, n=40)
    real = train_bc_mod.compute_action_agreement

    def fake(model, transitions, **kw):
        out = real(model, transitions, **kw)
        out["mean_cross_entropy"] = 1.0
        return out

    monkeypatch.setattr(train_bc_mod, "compute_action_agreement", fake)
    report_path = tmp_path / "report.json"
    train_bc(data_path=data_path, checkpoint_dir=ckpt_dir, epochs=6, batch_size=8, device="cpu",
             patience=1, min_epochs=4, report_path=report_path)
    report = json.loads(report_path.read_text())
    assert report["epochs_run"] == 4 and report["best_epoch"] == 1


def test_train_bc_without_patience_is_unchanged(tmp_path: Path) -> None:
    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    _make_dataset(data_path, n=20)
    report_path = tmp_path / "report.json"
    train_bc(data_path=data_path, checkpoint_dir=ckpt_dir, epochs=2, batch_size=8, device="cpu",
             report_path=report_path)
    report = json.loads(report_path.read_text())
    assert report["stopped_early"] is False and report["epochs_run"] == 2
    assert not (ckpt_dir / "best.pt").exists()
```

(`_make_dataset` writes JSONL, so `train_bc` takes the `compute_action_agreement` branch — that is the one to monkeypatch. `json` is already imported in that test file.)

- [ ] **Step 2: Run, expect failure** — `uv run --project ai pytest ai/tests/test_evaluate.py ai/tests/test_train_bc.py -q -p no:cacheprovider -k "cross_entropy or patience or min_epochs or without_patience"` → KeyError `mean_cross_entropy` / TypeError `patience`.

- [ ] **Step 3: `mean_cross_entropy` in both helpers** (`evaluate.py`). Inside the batch loop after `logits, _ = model(...)`:

```python
            log_probs = torch.log_softmax(logits.float(), dim=1)
            nll_sum += float(-log_probs[torch.arange(logits.shape[0]), torch.from_numpy(action_ids).to(logits.device)].sum().item())
```
with `nll_sum = 0.0` initialised beside `exact_matches`, and `"mean_cross_entropy": nll_sum / total` added to the final dict (and `0.0` in the `total == 0` dict). Mirror the same in `compute_action_agreement` (the transitions variant) — read it first; it may delegate to the batches helper, in which case nothing more is needed.

- [ ] **Step 4: patience in `train_bc`**. Signature: add `patience: Optional[int] = None, min_delta: float = 1e-4, min_epochs: int = 1` after `model_config`. Before the loop: `best_ce = float("inf"); best_epoch = None; stale = 0; stopped_early = False; epochs_run = 0`. After each epoch's `checkpoint_path` is saved:

```python
            epochs_run = epoch
            val_ce = (epoch_report["validation"] or {}).get("mean_cross_entropy")
            if val_ce is not None:
                if val_ce < best_ce - min_delta:
                    best_ce, best_epoch, stale = float(val_ce), epoch, 0
                else:
                    stale += 1
                if patience is not None and epoch >= min_epochs and stale >= patience:
                    stopped_early = True
            ...  # existing mlflow/report bookkeeping stays
            if stopped_early:
                print(f"--- early stop at epoch {epoch}: no val CE improvement >= {min_delta} for {patience} epochs (best epoch {best_epoch})")
                break
```
After the loop, when `patience is not None and best_epoch is not None`: `shutil.copyfile(checkpoint_dir / f"epoch_{best_epoch:03d}.pt", checkpoint_dir / "best.pt")`. Always set `report["stopped_early"] = stopped_early`, `report["epochs_run"] = epochs_run`, `report["best_epoch"] = best_epoch`, `report["best_validation_cross_entropy"] = best_ce if best_epoch is not None else None` before the report is written. If `patience is not None` and `validation_count == 0`, raise `ValueError("--patience requires a validation split")` before training. CLI: `--patience` (int, default None), `--min-delta` (float, 1e-4), `--min-epochs` (int, 1); pass through.

- [ ] **Step 5: Run** `uv run --project ai pytest ai/tests/test_evaluate.py ai/tests/test_train_bc.py -q -p no:cacheprovider` → all pass.

- [ ] **Step 6: Commit** — `git add ai/src/fh_mahjong_ai/evaluate.py ai/src/fh_mahjong_ai/scripts/train_bc.py ai/tests/test_evaluate.py ai/tests/test_train_bc.py` ; `git commit -m "feat(ai): BC validation cross-entropy, patience early stop, best.pt"`.

---

### Task 2: Two-group learning-rate schedule in `train_b2b`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (`PPOConfig`, after `minibatch_device_transfer`)
- Modify: `ai/src/fh_mahjong_ai/train_b2b.py` (new helpers beside `build_scratch_model`; optimizer construction ~line 1609; iteration loop just before `ppo_update` ~line 1657; metrics after it)
- Modify: `ai/src/fh_mahjong_ai/scripts/train_b2b.py` (argparse + `PPOConfig(...)` construction)
- Test: `ai/tests/test_b2b_training.py`, `ai/tests/test_b2b_resume.py`

**Interfaces:**
- Produces:
  ```python
  # ppo.py
  head_lr: Optional[float] = None   # lr for parameters NOT loaded from BC; None = single group
  head_lr_iters: int = 0            # iterations 1..head_lr_iters use head_lr, then config.lr

  # train_b2b.py
  def split_bc_parameter_groups(model: nn.Module) -> tuple[list[nn.Parameter], list[nn.Parameter]]  # (bc_loaded, heads) by SCRATCH_BC_PREFIXES
  def build_optimizer(model: nn.Module, config: PPOConfig) -> torch.optim.AdamW
  def apply_lr_schedule(optimizer: torch.optim.AdamW, config: PPOConfig, iteration: int) -> dict[str, float]  # returns {"lr_bc": ..., "lr_heads": ...}
  ```
  `train_b2b` raises `ValueError` if `config.head_lr is not None and init_from_bc is None` (fresh run) — head groups are defined relative to a BC init. Per-iteration `metrics["lr_bc"]`, `metrics["lr_heads"]`. CLI `--head-lr`, `--head-lr-iters`.

- [ ] **Step 1: Failing tests** — append to `ai/tests/test_b2b_training.py`:

```python
def test_split_bc_parameter_groups_partitions_all_parameters():
    from fh_mahjong_ai.train_b2b import SCRATCH_BC_PREFIXES, split_bc_parameter_groups
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"), cfg)
    bc, heads = split_bc_parameter_groups(model)
    assert len(bc) + len(heads) == len(list(model.parameters()))
    names = dict(model.named_parameters())
    bc_ids = {id(p) for p in bc}
    for name, p in names.items():
        assert (id(p) in bc_ids) == name.startswith(SCRATCH_BC_PREFIXES), name
    assert any(n.startswith("event_encoder.") for n, p in names.items() if id(p) not in bc_ids)
    assert any(n.startswith("value_head.") for n, p in names.items() if id(p) not in bc_ids)


def test_lr_schedule_switches_after_head_lr_iters_and_keeps_moments():
    from fh_mahjong_ai.train_b2b import apply_lr_schedule, build_optimizer
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"), cfg)
    config = PPOConfig(lr=2e-5, head_lr=2e-4, head_lr_iters=25)
    opt = build_optimizer(model, config)
    assert len(opt.param_groups) == 2
    assert apply_lr_schedule(opt, config, 1) == {"lr_bc": 2e-5, "lr_heads": 2e-4}
    assert apply_lr_schedule(opt, config, 25) == {"lr_bc": 2e-5, "lr_heads": 2e-4}
    # take one step so moments exist, then switch
    loss = sum(p.sum() for p in model.parameters())
    loss.backward(); opt.step()
    state_before = {k: v["exp_avg"].clone() for k, v in opt.state.items() if "exp_avg" in v}
    assert apply_lr_schedule(opt, config, 26) == {"lr_bc": 2e-5, "lr_heads": 2e-5}
    assert opt.param_groups[1]["lr"] == 2e-5
    for k, v in opt.state.items():
        assert torch.equal(v["exp_avg"], state_before[k])


def test_build_optimizer_single_group_by_default():
    from fh_mahjong_ai.train_b2b import apply_lr_schedule, build_optimizer
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"), ModelConfig(**SMALL_MODEL))
    opt = build_optimizer(model, PPOConfig(lr=3e-5))
    assert len(opt.param_groups) == 1 and opt.param_groups[0]["lr"] == 3e-5
    assert apply_lr_schedule(opt, PPOConfig(lr=3e-5), 7) == {"lr_bc": 3e-5, "lr_heads": 3e-5}


def test_train_b2b_head_lr_requires_init_from_bc(tmp_path):
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True, max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=1, matches_per_iter=2, max_steps_per_episode=16,
                       ppo_epochs=1, minibatch_size=8, num_workers=1, match_mode="classic", head_lr=2e-4, head_lr_iters=1)
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    with pytest.raises(ValueError, match="head_lr"):
        train_b2b(env, cfg, None, tmp_path / "run", config, scratch=True)


def test_train_b2b_records_lr_telemetry_with_schedule(tmp_path):
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True, max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=3, matches_per_iter=2, max_steps_per_episode=16,
                       ppo_epochs=1, minibatch_size=8, num_workers=1, match_mode="classic",
                       lr=2e-5, head_lr=2e-4, head_lr_iters=2)
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    _, bc_path = _bc_checkpoint(tmp_path, cfg)
    history = train_b2b(env, cfg, None, tmp_path / "run", config, base_seed=5, scratch=True, init_from_bc=bc_path)
    assert [h["lr_heads"] for h in history] == [2e-4, 2e-4, 2e-5]
    assert all(h["lr_bc"] == 2e-5 for h in history)
```

Append to `ai/tests/test_b2b_resume.py` (model it on that file's existing resume test — same env/config construction, `train_state_every=1`, resume via `resume_from_state`): a scratch+BC run with `head_lr=2e-4, head_lr_iters=2, iterations=2`, then resume to `iterations=4`; assert the resumed history has `lr_heads == [2e-5, 2e-5]` for iterations 3–4 and that `optimizer.load_state_dict` did not raise (i.e. the run completes). Name it `test_resume_rebuilds_two_parameter_groups`.

- [ ] **Step 2: Run, expect failure** — `-k "parameter_groups or lr_schedule or single_group or head_lr or lr_telemetry"` → ImportError / TypeError on `head_lr`.

- [ ] **Step 3: `PPOConfig` fields** in `ppo.py` after `minibatch_device_transfer`:

```python
    # mortal-scale-scratch Amendment 1 §6: two AdamW parameter groups for
    # --scratch --init-from-bc runs. Parameters loaded from the BC stage
    # (SCRATCH_BC_PREFIXES) train at `lr` throughout; every other parameter
    # (event encoder, value/Q, privileged critic, aux and risk heads) trains at
    # `head_lr` for iterations 1..head_lr_iters, then at `lr`. The optimizer is
    # never rebuilt at the switch -- moments are retained. None = one group.
    head_lr: Optional[float] = None
    head_lr_iters: int = 0
```

- [ ] **Step 4: helpers in `train_b2b.py`** (after `build_scratch_model`):

```python
def split_bc_parameter_groups(model: nn.Module) -> tuple[list[nn.Parameter], list[nn.Parameter]]:
    """Partition parameters by name into (loaded-from-BC, heads) using
    SCRATCH_BC_PREFIXES. Pure function of parameter names, so a resumed run
    rebuilds identical groups and optimizer.load_state_dict matches."""
    bc, heads = [], []
    for name, param in model.named_parameters():
        (bc if name.startswith(SCRATCH_BC_PREFIXES) else heads).append(param)
    return bc, heads


def build_optimizer(model: nn.Module, config: PPOConfig) -> torch.optim.AdamW:
    if config.head_lr is None:
        return torch.optim.AdamW(model.parameters(), lr=config.lr)
    bc, heads = split_bc_parameter_groups(model)
    return torch.optim.AdamW([{"params": bc, "lr": config.lr, "name": "bc"},
                              {"params": heads, "lr": config.head_lr, "name": "heads"}], lr=config.lr)


def apply_lr_schedule(optimizer: torch.optim.AdamW, config: PPOConfig, iteration: int) -> dict[str, float]:
    """Set each group's lr for `iteration` (1-based). Idempotent, so calling it
    every iteration -- including the first after a resume -- is correct."""
    if config.head_lr is None or len(optimizer.param_groups) == 1:
        return {"lr_bc": config.lr, "lr_heads": config.lr}
    heads_lr = config.head_lr if iteration <= config.head_lr_iters else config.lr
    optimizer.param_groups[0]["lr"] = config.lr
    optimizer.param_groups[1]["lr"] = heads_lr
    return {"lr_bc": config.lr, "lr_heads": heads_lr}
```
(`nn` is `torch.nn`; import if the module doesn't already.)

- [ ] **Step 5: wire into `train_b2b`**. In the fresh-run validation block at the top (where the scratch checks live): `if config.head_lr is not None and init_from_bc is None: raise ValueError("head_lr requires scratch=True with init_from_bc (groups are defined relative to the BC-loaded prefixes)")` — fresh runs only (`resume_from_state is None`). Replace `optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr)` with `optimizer = build_optimizer(model, config)`. Directly before `metrics = ppo_update(...)`: `lrs = apply_lr_schedule(optimizer, config, iteration)`; after `metrics["steps"] = len(batch)`: `metrics.update(lrs)`. CLI: `p.add_argument("--head-lr", type=float, default=None, help=...)`, `p.add_argument("--head-lr-iters", type=int, default=0, help=...)`; pass `head_lr=args.head_lr, head_lr_iters=args.head_lr_iters` into `PPOConfig(...)`; in the CLI validation block add `if args.head_lr is not None and args.init_from_bc is None and args.resume_from_state is None: p.error("--head-lr requires --scratch --init-from-bc")`.

- [ ] **Step 6: Run** `uv run --project ai pytest ai/tests/test_b2b_training.py ai/tests/test_b2b_resume.py ai/tests/test_ppo.py -q -p no:cacheprovider` → all pass (existing tests untouched: default path is one group, telemetry keys are additive).

- [ ] **Step 7: Commit** — `git commit -m "feat(ai): two-group lr schedule for --scratch --init-from-bc (Amendment 1 §6)"`.

---

### Task 3: Step-zero BC→B2b transfer gate

**Files:**
- Modify: `ai/src/fh_mahjong_ai/train_b2b.py` (new `verify_bc_transfer` beside `build_scratch_model`; call site in the `elif scratch:` branch; `init_meta` construction)
- Test: `ai/tests/test_b2b_training.py`

**Interfaces:**
- Produces:
  ```python
  def verify_bc_transfer(model: PolicyValueNet, bc_checkpoint: Path, env_config: EnvConfig,
                         probe_seed: int = 20260825, probe_batch: int = 64) -> dict
  ```
  Returns the gate record (also raises `RuntimeError` on any failure):
  `{"probe_seed", "probe_batch", "max_abs_logit_diff", "max_abs_prob_diff", "greedy_match_rate", "loaded_keys": [...], "unloaded_keys": [...], "loaded_tensors_identical": True}`. `train_b2b` stores it as `init_meta["transfer_gate"]` when `init_from_bc` is given.

- [ ] **Step 1: Failing tests** — append to `ai/tests/test_b2b_training.py`:

```python
def test_verify_bc_transfer_passes_and_records(tmp_path):
    from fh_mahjong_ai.train_b2b import SCRATCH_BC_PREFIXES, build_scratch_model, verify_bc_transfer
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    _, bc_path = _bc_checkpoint(tmp_path, cfg)
    env39 = EnvConfig(bridge_kind="mock")
    model = build_scratch_model(env39, cfg, bc_checkpoint=bc_path)
    record = verify_bc_transfer(model, bc_path, env39)
    assert record["max_abs_logit_diff"] == 0.0 and record["greedy_match_rate"] == 1.0
    assert record["loaded_tensors_identical"] is True
    assert all(k.startswith(SCRATCH_BC_PREFIXES) for k in record["loaded_keys"])
    assert any(k.startswith("event_encoder.") for k in record["unloaded_keys"])
    assert set(record["loaded_keys"]) | set(record["unloaded_keys"]) == set(model.state_dict())


def test_verify_bc_transfer_fails_closed_on_perturbation(tmp_path):
    from fh_mahjong_ai.train_b2b import build_scratch_model, verify_bc_transfer
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    _, bc_path = _bc_checkpoint(tmp_path, cfg)
    env39 = EnvConfig(bridge_kind="mock")
    model = build_scratch_model(env39, cfg, bc_checkpoint=bc_path)
    with torch.no_grad():
        model.policy_head.bias.add_(0.5)
    with pytest.raises(RuntimeError, match="transfer gate"):
        verify_bc_transfer(model, bc_path, env39)


def test_train_b2b_init_metadata_carries_transfer_gate(tmp_path):
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True, max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=1, matches_per_iter=2, max_steps_per_episode=16,
                       ppo_epochs=1, minibatch_size=8, num_workers=1, match_mode="classic")
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    _, bc_path = _bc_checkpoint(tmp_path, cfg)
    train_b2b(env, cfg, None, tmp_path / "run", config, base_seed=3, scratch=True, init_from_bc=bc_path)
    payload = torch.load(tmp_path / "run" / "iter_001.pt", map_location="cpu")
    gate = payload["metadata"]["init"]["transfer_gate"]
    assert gate["greedy_match_rate"] == 1.0 and gate["loaded_tensors_identical"] is True
```

- [ ] **Step 2: Run, expect failure** — `-k transfer` → ImportError.

- [ ] **Step 3: Implement `verify_bc_transfer`**:

```python
def verify_bc_transfer(model: PolicyValueNet, bc_checkpoint: Path, env_config: EnvConfig,
                       probe_seed: int = 20260825, probe_batch: int = 64) -> dict:
    """Amendment 1 §4: prove the scratch model IS the BC policy at step zero.
    Rebuilds the BC net from the checkpoint, feeds both nets an identical
    seeded synthetic probe (BC with events=None, scratch with random events),
    and requires bit-equal masked logits, probabilities and greedy actions,
    plus byte-identical tensors for every loaded key. Fail closed."""
    payload = torch.load(Path(bc_checkpoint), map_location="cpu")
    bc_config = infer_model_config(payload["model"], payload.get("metadata"))
    bc_model = PolicyValueNet(env_config, bc_config)
    bc_model.load_state_dict(payload["model"], strict=True)
    bc_model.eval(); model.eval()
    sd = model.state_dict()
    loaded = sorted(k for k in sd if k.startswith(SCRATCH_BC_PREFIXES))
    unloaded = sorted(k for k in sd if not k.startswith(SCRATCH_BC_PREFIXES))
    bc_sd = bc_model.state_dict()
    mismatched = [k for k in loaded if not torch.equal(sd[k].cpu(), bc_sd[k].cpu())]
    if model.wants_events:
        ev = model.event_encoder.output_dim
        if not torch.equal(sd["trunk.0.weight"][:, -ev:].cpu(), torch.zeros_like(sd["trunk.0.weight"][:, -ev:].cpu())):
            mismatched.append("trunk.0.weight[event columns not zero]")
    gen = torch.Generator().manual_seed(probe_seed)
    channels, height, width = env_config.plane_shape
    planes = torch.rand((probe_batch, channels, height, width), generator=gen)
    scalars = torch.rand((probe_batch, env_config.scalar_features), generator=gen)
    mask = (torch.rand((probe_batch, env_config.action_space_size), generator=gen) > 0.3).to(torch.int8)
    mask[:, 0] = 1  # at least one legal action per row
    device = next(model.parameters()).device
    with torch.no_grad():
        ref, _ = bc_model(planes, scalars, mask)
        if model.wants_events:
            window = model.model_config.event_window
            events = torch.randint(0, 0x10000, (probe_batch, window), generator=gen)
            lengths = torch.full((probe_batch,), window, dtype=torch.int64)
            got, _ = model(planes.to(device), scalars.to(device), mask.to(device),
                           events=events.to(device), event_lengths=lengths.to(device))
        else:
            got, _ = model(planes.to(device), scalars.to(device), mask.to(device))
    got = got.cpu()
    legal = mask.bool()
    logit_diff = float((ref - got).abs()[legal].max().item())
    prob_diff = float((torch.softmax(ref, 1) - torch.softmax(got, 1)).abs().max().item())
    greedy = float((ref.argmax(1) == got.argmax(1)).float().mean().item())
    record = {"probe_seed": probe_seed, "probe_batch": probe_batch, "max_abs_logit_diff": logit_diff,
              "max_abs_prob_diff": prob_diff, "greedy_match_rate": greedy,
              "loaded_keys": loaded, "unloaded_keys": unloaded, "loaded_tensors_identical": not mismatched}
    if mismatched or logit_diff != 0.0 or greedy != 1.0:
        raise RuntimeError(f"--init-from-bc transfer gate FAILED: tensors_mismatched={mismatched[:6]}, "
                           f"max_abs_logit_diff={logit_diff}, greedy_match_rate={greedy}")
    return record
```
Note: the probe runs both nets on CPU-side inputs; the scratch model may be on CUDA — the `.to(device)` calls handle it, and float32 results are compared after `.cpu()`. If a CUDA run shows a non-zero diff purely from device arithmetic, that is a finding to report, not to loosen — the runbook launches the gate on the same device as training.

Wire in: in the `elif scratch:` branch after `model = build_scratch_model(...)`: `transfer_gate = verify_bc_transfer(model, init_from_bc, _b2b_model_env_config(env_config)) if init_from_bc is not None else None`. Add `"transfer_gate": transfer_gate` to `init_meta` (and `None` in the champion / legacy-resume dicts; update the three exact-dict test assertions from the previous plan accordingly). Import `infer_model_config` from `.model` if not already imported.

- [ ] **Step 4: Run** `uv run --project ai pytest ai/tests/test_b2b_training.py ai/tests/test_b2b_resume.py ai/tests/test_train_bc.py -q -p no:cacheprovider` → all pass.

- [ ] **Step 5: Commit** — `git commit -m "feat(ai): step-zero BC transfer gate recorded in init metadata (Amendment 1 §4)"`.

---

### Task 4: Docs, runbook, status file, gates, PR update

**Files:**
- Modify: `ai/CLAUDE.md` (train-bc / train-b2b rows + mortal-scale-scratch vocabulary bullet), `ai/MODULES.md` (`build_scratch_model` bullet: add `verify_bc_transfer`, `build_optimizer`/`apply_lr_schedule`)
- Create: `worklog/plans/20260825-mortal-scale-scratch-runbook.md`
- Create: `worklog/rl-experiment/20260825-mortal-scale-scratch-status.md`
- Modify: spec status line

- [ ] **Step 1: Docs** — one line each for `--patience/--min-delta/--min-epochs` + `best.pt` + `mean_cross_entropy`; `--head-lr/--head-lr-iters` (two AdamW groups by `SCRATCH_BC_PREFIXES`, moments retained at the switch, `lr_bc`/`lr_heads` in history); `metadata["init"]["transfer_gate"]`. State facts only, no change narration.

- [ ] **Step 2: Runbook** `worklog/plans/20260825-mortal-scale-scratch-runbook.md` — the Amendment 1 numbers verbatim, as exact commands on the 4090 box (`ssh wsl`, repo `/root/fh-mahjong`, runs under `/root/fh-mahjong-runs/mortal-scale-scratch/`):
  1. Build bridge + `uv sync`; record bridge sha256.
  2. BC data: `fh-mj-generate-data` for 10,000 heuristic matches, seeds 1,300,000–1,309,999, sharded NumPy output `bc-data/`; record dataset manifest digest. (Check `fh-mj-generate-data --help` on the box for the exact seed/count flags and paste them.)
  3. BC control: `fh-mj-train-bc --data bc-data --checkpoint-dir bc-control --epochs 30 --patience 5 --min-delta 1e-4 --min-epochs 5 --validation-fraction 0.1 --split-seed 1300000 --model-channels 96 --model-residual-blocks 4 --model-kernel-width 1 --model-event-window 128 --model-privileged-critic --model-aux-heads --report-output bc-control/report.json --device cuda`. BC big: same with `--model-channels 192 --model-residual-blocks 24 --checkpoint-dir bc-big`. Record `best_epoch`, val CE, top-1 (zeroed events) per arm.
  4. Bench (big only, before its lap): ds960 runbook `fh-mj-collect-bench` procedure at 960/768 with `--scratch --init-from-bc bc-big/best.pt` equivalents; gates cgroup ≤ 38.00 GiB, tree ≤ 40.00 GiB, CUDA ≤ 20.00 GiB, `memory.high=44GiB`, `memory.max=48GiB`, swap 0, `oom.group=1`; record throughput + projected wall time. Breach → stop, consult.
  5. Control lap: the ds960 launch command with `--scratch --init-from-bc bc-control/best.pt --model-channels 96 --model-residual-blocks 4 --model-kernel-width 1 --event-window 128 --privileged-critic --aux-heads --matches-per-iter 320 --minibatch-size 256 --collect-dispatch-chunk 320 --minibatch-device-transfer --num-workers 10 --lr 2e-5 --head-lr 2e-4 --head-lr-iters 25 --entropy-coef 0 --ppo-epochs 2 --gamma 0.99 --match-mode chongci --max-steps-per-episode 4000 --device cuda --iterations 200 --base-seed 1400000 --train-state-every 5 --checkpoint-dir /root/fh-mahjong-runs/mortal-scale-scratch/control/ckpt`.
  6. Big lap (only if control's iter-200 screening delta ≥ −0.0600): same with `--model-channels 192 --model-residual-blocks 24 --matches-per-iter 960 --minibatch-size 768 --base-seed 1500000 --init-from-bc bc-big/best.pt --checkpoint-dir .../big/ckpt`.
  7. Screenings 25/50/75/100/125/150/175/200: `fh-mj-evaluate` 120-seed duplicate-seat window `--start-seed 1710000` for candidate and regenerated anchor075, `fh-mj-compare`; kill only at iter 100 iff `delta100 − delta75 ≤ 0 and delta100 < −0.20`.
  8. Selection = best healthy screening (tie → later); confirmation 1500 paired seeds × 4 duplicate seats `--start-seed 1720000`, `fh-mj-compare`, gates CI95 lower > 0 and large_loss ≤ comparator + 0.015; big vs anchor075 primary, big vs selected control secondary on the same window.
  9. Everything terminal returns to Codex thread `01a0147d`; no promotion/deploy.
  Copy the exact `fh-mj-evaluate`/`fh-mj-compare` invocations from `worklog/plans/2026-08-12-data-scale-960-runbook.md` §screening/§confirmation, changing only seeds/paths.

- [ ] **Step 3: Status file** `worklog/rl-experiment/20260825-mortal-scale-scratch-status.md` — header (spec, runbook, thread id, box), a "Current stage" line (`NOT LAUNCHED — awaiting BC data generation`), a stage checklist (bridge/data/BC-control/BC-big/bench/control-lap/big-lap/confirm), and an empty screening table per arm. Sign entries by session name.

- [ ] **Step 4: Spec status line** → `**Status:** code complete incl. Amendment 1 items (PR #223); protocol ratified 2026-08-25; NOT LAUNCHED — see runbook + status file.`

- [ ] **Step 5: Gates** — `gofmt -l .` (silent), `go vet ./...`, `go test ./...`, `cd web && npx tsc && npx vitest run`, `uv run --project ai pytest ai/tests -q -p no:cacheprovider` (≥ 994 + new, 0 failed).

- [ ] **Step 6: Commit** — `git commit -m "docs: Amendment 1 runbook, status file, follow-up flag docs"`. Do not push (the controller pushes to PR #223).

---

## Self-review
- **Spec coverage:** A1 §3 → Task 1 (patience, min/max epochs are runbook flags, best checkpoint, val CE + top-1); §4 → Task 3; §6 → Task 2 (values, moments retained); §5/§7/§8/§9/§11 → Task 4 runbook; §2 gate (−0.0600 control rule) → runbook step 6.
- **Placeholders:** none; the generate-data flag check is an explicit instruction to read `--help` and paste, not a TBD.
- **Type consistency:** `split_bc_parameter_groups` / `build_optimizer` / `apply_lr_schedule` / `verify_bc_transfer` named identically in tests and code; `head_lr`/`head_lr_iters` consistent across `PPOConfig`, CLI, tests; `mean_cross_entropy` key consistent between Task 1 tests and code.

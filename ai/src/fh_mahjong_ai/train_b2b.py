"""B2b training: model surgery (ReZero block growth, event-GRU widening),
rollout collection with hindsight labels, and the `train_b2b` PPO loop.

Split out of `oracle.py`, whose docstring had said "Phase 1" for a thousand
lines of this. The crash-resume machinery this loop drives lives in
`train_state.py` and is called as `train_state.X` on purpose: one monkeypatch
target then covers both this module's calls and train_state's internal ones."""
from __future__ import annotations

import hashlib
import io
import logging
import multiprocessing as mp
import os
import queue as _queue
import random
import shutil
import traceback
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import torch
from torch import nn

from . import memprobe
from . import train_state
from .bridge import build_bridge, resolve_bridge_library_path
from .config import EnvConfig, ModelConfig
from .env import MahjongEnv
from .model import (
    PolicyValueNet,
    infer_model_config,
    _derive_growth_blocks,
    _reconstruct_env_config,
    _shape_inferred_fields,
)
from .parallel_rollouts import _split_counts
from .placement_bonus import exact_final_scores, placement_utilities, rank_occupancy
from .ppo import (
    RolloutBatch, PPOConfig, compute_gae, concat_rollout_batches, ppo_update,
    masked_policy_distribution, masked_logprob, _seat_step_reward,
    cpu_state_snapshot, _write_history_atomic,
)
from .storage import load_compatible_checkpoint, model_config_metadata, save_checkpoint

logger = logging.getLogger(__name__)


def _b2b_model_env_config(env_config: EnvConfig) -> EnvConfig:
    """Derive the 39ch EnvConfig used to CONSTRUCT a B2b `PolicyValueNet`.

    The privileged-critic branch (`_value_features` in model.py) assumes
    `policy_channels == 39` so it can slice the trailing 12 oracle channels
    (`planes[:, 39:51]`) out of a 51ch observation. Constructing the model
    directly from an `oracle_observation=True` (51ch) EnvConfig would instead
    set `policy_channels = 51`, which breaks that slice at the first privileged
    forward pass. Rollout envs still run with `oracle_observation=True` (51ch
    observations) — only the model's construction config differs."""
    return EnvConfig(
        action_space_size=env_config.action_space_size,
        scalar_features=env_config.scalar_features,
        bridge_kind=env_config.bridge_kind,
        bridge_library_path=env_config.bridge_library_path,
        match_mode=env_config.match_mode,
    )


def build_b2b_model(env_config: EnvConfig, model_config: ModelConfig,
                    champion_checkpoint: Path, device: str = "cpu") -> PolicyValueNet:
    """Warm-start the B2b net from the 39ch champion. The plane stem is
    UNCHANGED (39ch policy slice), so only two tensors need surgery:
    trunk.0 (event columns zeroed => step-0 logits == champion) and
    value_head.0 (privileged columns zeroed => step-0 values == champion).
    `env_config` must be a 39ch (oracle_observation=False) config — callers
    building a B2b net from an oracle env_config should first pass it through
    `_b2b_model_env_config`."""
    model = PolicyValueNet(env_config, model_config).to(device)
    _, report = load_compatible_checkpoint(Path(champion_checkpoint), model)
    payload = torch.load(Path(champion_checkpoint), map_location="cpu")
    # FAIL CLOSED on architecture mismatch: every champion tensor must either
    # load same-shape or be one of the two explicitly-widened tensors the
    # surgery below repairs. Anything else (e.g. a residual-block count
    # mismatch) would silently drop champion layers and break the step-0
    # equivalence invariant.
    surgical = {"trunk.0.weight", "value_head.0.weight"}
    new_module_prefixes = ("event_encoder.", "privileged_encoder.",
                           "belief_head.", "dealin_head.", "rank_head.")
    bad_skipped = [k for k in report["skipped_keys"] if k not in surgical]
    bad_missing = [k for k in report["missing_keys"]
                   if k not in surgical and not k.startswith(new_module_prefixes)]
    if bad_skipped or bad_missing:
        raise RuntimeError(
            "champion checkpoint is architecturally incompatible with the B2b model "
            f"config (skipped={bad_skipped[:6]}, missing={bad_missing[:6]}) — check "
            "--model-residual-blocks and width flags against the champion"
        )
    old_trunk_w = payload["model"]["trunk.0.weight"]      # [T, P+S]
    old_value_w = payload["model"]["value_head.0.weight"]  # [V, T]
    with torch.no_grad():
        w = model.trunk[0].weight                          # [T, P+S(+E)]
        w.zero_()
        w[:, : old_trunk_w.shape[1]].copy_(old_trunk_w.to(w.device))
        model.trunk[0].bias.copy_(payload["model"]["trunk.0.bias"].to(w.device))
        if model_config.privileged_critic:
            vw = model.value_head[0].weight                # [V, T+128]
            vw.zero_()
            vw[:, : old_value_w.shape[1]].copy_(old_value_w.to(vw.device))
            model.value_head[0].bias.copy_(payload["model"]["value_head.0.bias"].to(vw.device))
    model.eval()
    return model


SCRATCH_BC_PREFIXES = ("plane_stem.", "plane_blocks.", "plane_head.",
                       "scalar_encoder.", "trunk.", "policy_head.")


def build_scratch_model(env_config: EnvConfig, model_config: ModelConfig, device: str = "cpu",
                        bc_checkpoint: Optional[Path] = None) -> PolicyValueNet:
    """mortal-scale-scratch: a freshly initialised B2b net (no anchor, no
    surgery). With `bc_checkpoint`, the BC-stage weights for exactly
    `SCRATCH_BC_PREFIXES` are copied by name+shape; every other module (event
    encoder, privileged critic, value/aux/risk/q heads) keeps its random
    init. Any BC key under those prefixes that is absent from the model, or any
    model key under those prefixes absent from the BC checkpoint, or any shape
    mismatch, is a hard error -- a silent partial load is this lane's known
    failure mode. `env_config` must be the 39ch config (see `_b2b_model_env_config`).

    step-0 policy == BC policy: the event columns are zeroed so the untrained
    GRU contributes nothing until PPO moves them. BC trains with `events=None`,
    which makes `encode` feed the trunk a ZERO event vector, so the trailing
    `event_encoder.output_dim` columns of `trunk.0.weight` come out of the BC
    stage exactly as randomly initialised -- never once touched by a gradient.
    Copying them verbatim on top of this net's OWN brand-new event encoder
    (whose outputs are not zero) would inject pure noise into step-0 logits and
    silently make the run start somewhere other than the BC policy. Zeroing
    them is the same trick `build_b2b_model` uses for its 39ch-champion warm
    start, sized off the model's own encoder rather than a literal.

    `model_config.growth_blocks > 0` is rejected outright: ReZero growth
    tensors live under `growth.`, outside `SCRATCH_BC_PREFIXES`, so a BC load
    would leave them silently random -- exactly the partial load the strict
    prefix check above exists to prevent. `train_b2b`/the CLI reject
    `--scratch` with the growth surgery upstream of this too.

    The returned model carries `init_from_bc_sha256`: the sha256 of the BC
    checkpoint's bytes as actually loaded (None without `bc_checkpoint`).
    `train_b2b` records that digest in `metadata["init"]` rather than hashing
    the path a second time."""
    if model_config.growth_blocks > 0:
        raise ValueError(
            f"build_scratch_model: growth_blocks ({model_config.growth_blocks}) must be 0 -- "
            "the scratch path has no anchor to grow, and `growth.` tensors fall outside "
            "SCRATCH_BC_PREFIXES, so an --init-from-bc load would leave them silently random"
        )
    model = PolicyValueNet(env_config, model_config).to(device)
    # M4: `train_b2b` reads this instead of re-hashing the file itself, so the
    # provenance digest and the loaded weights are guaranteed to come from the
    # same bytes. None when this net is pure random init.
    model.init_from_bc_sha256 = None
    if bc_checkpoint is None:
        model.eval()
        return model
    bc_path = Path(bc_checkpoint)
    # Checked before torch.load so a mistyped path is a clear, actionable error
    # naming the flag, not a bare FileNotFoundError from deep inside torch.
    if not bc_path.is_file():
        raise FileNotFoundError(
            f"--init-from-bc: BC checkpoint {bc_path} does not exist (or is not a regular "
            "file) -- pass the fh-mj-train-bc checkpoint this run should start its plane "
            "trunk / scalar encoder / trunk / policy head from"
        )
    # M4: read the file exactly ONCE. `train_b2b` needs both the weights and a
    # sha256 of the bytes those weights came from; reopening the path for the
    # hash would let an atomic replacement land in between, so the recorded
    # digest would name bytes this run never loaded (the same reason
    # `storage.load_checkpoint_from_bytes` exists). The digest rides back on
    # the returned model as `init_from_bc_sha256`.
    data = bc_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    payload = torch.load(io.BytesIO(data), map_location="cpu")
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
            f"shape_mismatch={mismatched[:6]}) -- the BC stage must be trained with "
            "the model flags this run uses. fh-mj-train-bc's --model-event-window / "
            "--model-privileged-critic / --model-aux-heads correspond to "
            "fh-mj-train-b2b's --event-window / --privileged-critic / --aux-heads "
            "(fh-mj-train-b2b IGNORES the --model-* forms of those three); every "
            "other shared --model-* flag keeps the same name on both commands"
        )
    with torch.no_grad():
        for key in wanted_model:
            target[key].copy_(bc_state[key].to(target[key].device))
        if model.wants_events:
            # See the step-0 parity paragraph above. `event_encoder` exists
            # exactly when `wants_events`, and `encode` appends its output
            # LAST, so the event columns are the trailing `output_dim` of
            # trunk.0's input -- sized off the encoder itself so an
            # event_output_dim projection (the gru-width lap's shape) is
            # handled without a second source of truth.
            event_dim = model.event_encoder.output_dim
            model.trunk[0].weight[:, -event_dim:].zero_()
    model.init_from_bc_sha256 = digest
    model.eval()
    return model


def verify_bc_transfer(model: PolicyValueNet, bc_checkpoint: Path, env_config: EnvConfig,
                       probe_seed: int = 20260825, probe_batch: int = 64) -> dict:
    """Amendment 1 §4: prove the scratch model IS the BC policy at step zero.

    Rebuilds the BC net from the checkpoint, feeds both nets an identical
    seeded synthetic probe (BC with events=None, scratch with random events),
    and requires bit-equal masked logits, probabilities and greedy actions,
    plus byte-identical tensors for every loaded key. Fail closed: any
    difference raises, so a broken transfer aborts the launch before a single
    rollout is collected rather than quietly training something that is not
    the BC policy. The returned record rides into `metadata["init"]` as the
    per-run evidence that the transfer held.

    Bit-equality (not a tolerance) is the contract: BC runs with `events=None`,
    which feeds its trunk an exactly-zero event vector, and this net's trunk
    has exactly-zero event COLUMNS -- so on both sides the event term
    contributes exact 0.0 into an otherwise identical dot product over
    identical weights and identical inputs. Any nonzero diff is a real defect
    (a mis-copied tensor, an unzeroed column), never float noise.

    The claim is scoped to the POLICY path: logits, probabilities and greedy
    actions. Values and the auxiliary heads are deliberately not compared --
    the privileged critic, the value/aux/risk/q heads and the event encoder
    have no BC counterpart at all (they are the `unloaded_keys`), so there is
    nothing there for step 0 to be equal to.

    The BC reference net is moved onto the model's own device before the probe:
    comparing a CPU forward against a CUDA forward would differ in the last
    ulp purely from kernel/reduction differences and would abort every GPU
    launch. Same device, same shapes, same kernels => the same reduction order
    on both sides, which is what makes exact equality the right assertion.

    Single-read discipline (as in `build_scratch_model`, M4): the checkpoint
    bytes are read ONCE here, hashed, and required to match the digest
    `build_scratch_model` recorded on the model (`init_from_bc_sha256`). An
    atomic replacement of the path between the two reads would otherwise have
    this gate prove parity against bytes the model never loaded -- a passing
    gate for a transfer that never happened. A mismatch is a gate failure."""
    data = Path(bc_checkpoint).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    expected_digest = getattr(model, "init_from_bc_sha256", None)
    if digest != expected_digest:
        raise RuntimeError(
            "--init-from-bc transfer gate FAILED: BC checkpoint digest mismatch -- "
            f"{bc_checkpoint} now hashes to sha256 {digest}, but this model was built "
            f"from sha256 {expected_digest}. The file changed between "
            "`build_scratch_model`'s read and this gate (or the model was not built "
            "from it at all), so the probe below would prove parity against bytes this "
            "run never loaded"
        )
    payload = torch.load(io.BytesIO(data), map_location="cpu")
    bc_config = infer_model_config(payload["model"], payload.get("metadata"))
    bc_model = PolicyValueNet(env_config, bc_config)
    bc_model.load_state_dict(payload["model"], strict=True)
    device = next(model.parameters()).device
    bc_model = bc_model.to(device)
    bc_model.eval()
    model.eval()
    sd = model.state_dict()
    loaded = sorted(k for k in sd if k.startswith(SCRATCH_BC_PREFIXES))
    unloaded = sorted(k for k in sd if not k.startswith(SCRATCH_BC_PREFIXES))
    bc_sd = bc_model.state_dict()
    # `trunk.0.weight` is the one loaded key that is deliberately NOT a verbatim
    # copy: `build_scratch_model` zeroes its trailing event columns (BC never
    # trained them, and this net's event encoder is brand new). Byte-equality is
    # therefore asserted on the leading plane+scalar columns, and the trailing
    # columns are required to be exactly zero -- the two halves of the same
    # step-0 parity claim, both of which the probe below then exercises.
    event_dim = model.event_encoder.output_dim if model.wants_events else 0
    mismatched: list[str] = []
    for key in loaded:
        got_t, ref_t = sd[key].cpu(), bc_sd[key].cpu()
        if event_dim and key == "trunk.0.weight":
            if not torch.equal(got_t[:, :-event_dim], ref_t[:, :-event_dim]):
                mismatched.append(key)
            if not torch.equal(got_t[:, -event_dim:], torch.zeros_like(got_t[:, -event_dim:])):
                mismatched.append("trunk.0.weight[event columns not zero]")
            continue
        if not torch.equal(got_t, ref_t):
            mismatched.append(key)
    # The probe is NOT redundant with the tensor check above. That check proves
    # the loaded tensors are BC's; this proves nothing ELSE reaches the policy
    # output. A future module added to `encode`/`policy_head` -- another
    # embedding, a second fusion input, an unloaded normalisation -- would pass
    # the tensor check untouched (it is not under SCRATCH_BC_PREFIXES) while
    # silently moving step-0 logits away from BC. Only a forward pass catches
    # that class of change.
    gen = torch.Generator().manual_seed(probe_seed)
    channels, height, width = env_config.plane_shape
    planes = torch.rand((probe_batch, channels, height, width), generator=gen)
    scalars = torch.rand((probe_batch, env_config.scalar_features), generator=gen)
    mask = (torch.rand((probe_batch, env_config.action_space_size), generator=gen) > 0.3).to(torch.int8)
    mask[:, 0] = 1  # at least one legal action per row
    planes, scalars, mask = planes.to(device), scalars.to(device), mask.to(device)
    with torch.no_grad():
        ref, _ = bc_model(planes, scalars, mask)
        if model.wants_events:
            window = model.model_config.event_window
            events = torch.randint(0, 0x10000, (probe_batch, window), generator=gen)
            lengths = torch.full((probe_batch,), window, dtype=torch.int64)
            got, _ = model(planes, scalars, mask, events=events.to(device),
                           event_lengths=lengths.to(device))
        else:
            got, _ = model(planes, scalars, mask)
    ref, got = ref.cpu(), got.cpu()
    # Illegal actions are masked to `finfo.min` on BOTH sides, so a raw diff
    # there is meaningless (it subtracts two identical sentinels); the claim
    # under test is about the LEGAL action distribution.
    legal = mask.cpu().bool()
    logit_diff = float((ref - got).abs()[legal].max().item())
    prob_diff = float((torch.softmax(ref, 1) - torch.softmax(got, 1)).abs().max().item())
    greedy = float((ref.argmax(1) == got.argmax(1)).float().mean().item())
    record = {"probe_seed": probe_seed, "probe_batch": probe_batch,
              "bc_checkpoint_sha256": digest, "max_abs_logit_diff": logit_diff,
              "max_abs_prob_diff": prob_diff, "greedy_match_rate": greedy,
              "loaded_keys": loaded, "unloaded_keys": unloaded, "loaded_tensors_identical": not mismatched}
    # All four quantities are GATED, not merely recorded: the probability diff
    # covers the full row (including the masked sentinels), so it also catches a
    # divergence confined to actions the probe happened to mark illegal, which
    # `logit_diff` -- taken under `legal` only -- cannot see.
    if mismatched or logit_diff != 0.0 or prob_diff != 0.0 or greedy != 1.0:
        raise RuntimeError(f"--init-from-bc transfer gate FAILED: tensors_mismatched={mismatched[:6]}, "
                           f"max_abs_logit_diff={logit_diff}, max_abs_prob_diff={prob_diff}, "
                           f"greedy_match_rate={greedy}")
    del bc_model, bc_sd, payload, data
    return record


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
    every iteration -- including the first after a resume -- is correct.

    Invariant: the groups are looked up by the `name` `build_optimizer` stamped
    on them, and whether to schedule at all is decided by the optimizer's own
    shape rather than by `config.head_lr`. Keying off the config would let a
    config/optimizer disagreement (a two-group optimizer under a head_lr-less
    config) return early WITHOUT touching the optimizer, leaving the heads
    group running at a head lr while the returned telemetry reported `lr`.
    The returned dict always describes the lrs actually in force."""
    groups = {group.get("name"): group for group in optimizer.param_groups}
    if "bc" not in groups or "heads" not in groups:
        # A single-group optimizer: every parameter is already at `config.lr`
        # from construction, and there is no second group to schedule.
        return {"lr_bc": config.lr, "lr_heads": config.lr}
    heads_lr = (config.head_lr
                if config.head_lr is not None and iteration <= config.head_lr_iters
                else config.lr)
    groups["bc"]["lr"] = config.lr
    groups["heads"]["lr"] = heads_lr
    return {"lr_bc": config.lr, "lr_heads": heads_lr}


def _assert_b2b_anchor_matches_live_env(fn_name: str, anchor_env_config: EnvConfig,
                                        anchor_config: ModelConfig, env_config: EnvConfig) -> None:
    """Shared env cross-check for the B2b warm-start surgeries (`grow_b2b_model`,
    `widen_event_gru`): `env_config`, when given, must be the LIVE env config
    that collection will actually run under. The model is otherwise
    constructed purely from the anchor's own tensor shapes
    (`_reconstruct_env_config`), which says nothing about whether those
    shapes still match the live env — a stale anchor (older action-space
    size, different scalar-feature count, or a different event-history
    window) would silently train a model shaped to the wrong wire format,
    with `encode()`'s zero-pad/truncate masking the drift instead of
    failing. Passing `env_config` catches that up front."""
    live_env_config = _b2b_model_env_config(env_config)
    mismatches = []
    if anchor_env_config.action_space_size != live_env_config.action_space_size:
        mismatches.append(
            "action_space_size (anchor was trained under "
            f"{anchor_env_config.action_space_size}, live env provides "
            f"{live_env_config.action_space_size})"
        )
    if anchor_env_config.scalar_features != live_env_config.scalar_features:
        mismatches.append(
            "scalar_features (anchor was trained under "
            f"{anchor_env_config.scalar_features}, live env provides "
            f"{live_env_config.scalar_features})"
        )
    anchor_channels, anchor_area, _ = anchor_env_config.plane_shape
    live_channels, live_area, _ = live_env_config.plane_shape
    if (anchor_channels, anchor_area) != (live_channels, live_area):
        mismatches.append(
            "plane_shape (anchor was trained under "
            f"{anchor_env_config.plane_shape}, live env provides "
            f"{live_env_config.plane_shape})"
        )
    if anchor_config.event_window != env_config.event_history_window:
        mismatches.append(
            "event_window (anchor was trained under "
            f"{anchor_config.event_window}, live env provides "
            f"{env_config.event_history_window})"
        )
    if mismatches:
        raise RuntimeError(
            f"{fn_name}: anchor checkpoint's construction shapes do not match "
            "the live env_config collection will run under — " + "; ".join(mismatches)
            + ". Refusing to silently train a model shaped to a stale anchor."
        )


def grow_b2b_model(anchor_checkpoint: Path, growth_blocks: int, device: str = "cpu",
                   env_config: Optional[EnvConfig] = None) -> PolicyValueNet:
    """Warm-start a wider B2b net by stacking `growth_blocks` ReZero residual
    blocks (deep16-rezero) after a post-B2b anchor's existing plane trunk.
    Unlike `build_b2b_model` (39ch -> B2b surgery), this performs NO surgery:
    the anchor must already be a complete B2b checkpoint (event encoder,
    privileged critic, aux heads as applicable), and every one of its tensors
    must load into the grown net at identical shape — the new `growth.*`
    blocks are the ONLY architectural delta, and they are identity at
    alpha=0 (ReZeroResidualBlock), so step-0 outputs equal the anchor's
    exactly.

    `anchor_checkpoint`'s `metadata["model_config"]` is authoritative for the
    anchor's full architecture (event_window is not recoverable from tensor
    shapes alone, so an anchor without this key cannot be grown safely).
    Growing an already-grown anchor (`growth_blocks > 0` in its own config)
    is out of scope and rejected: this warm start does not attempt to
    reconcile two different ReZero stacks.

    `env_config`, when given, must be the LIVE env config that collection
    will actually run under (i.e. what the caller passes to `train_b2b`).
    The model is otherwise constructed purely from the anchor's own tensor
    shapes (`_reconstruct_env_config`), which says nothing about whether
    those shapes still match the live env — a stale anchor (older
    action-space size, different scalar-feature count, or a different
    event-history window) would silently train a model shaped to the wrong
    wire format, with `encode()`'s zero-pad/truncate masking the drift
    instead of failing. Passing `env_config` catches that up front. Callers
    that omit it (e.g. tests exercising `grow_b2b_model` in isolation, with
    no "live env" to check against) skip this cross-check."""
    anchor_checkpoint = Path(anchor_checkpoint)
    payload = torch.load(anchor_checkpoint, map_location="cpu")
    metadata = payload.get("metadata") or {}
    model_config_meta = metadata.get("model_config")
    if not isinstance(model_config_meta, dict):
        raise RuntimeError(
            "anchor lacks complete model_config metadata — grow_b2b_model requires a "
            "post-B2b checkpoint saved with metadata['model_config'] (event_window is not "
            "recoverable from tensor shapes alone)"
        )
    anchor_config = ModelConfig(**model_config_meta)
    # Adversarial round 13, medium finding: trust the STATE DICT, not the
    # metadata's growth_blocks claim -- an anchor whose metadata lies about
    # growth_blocks==0 while its tensors actually carry growth.*.alpha keys
    # (nonzero alphas) would otherwise load those tensors into "growth_blocks=0"
    # slots undetected, silently breaking the step-0 warm-start parity this
    # function exists to guarantee. `_derive_growth_blocks` counts alpha keys
    # directly off the state dict and fails closed on a malformed/tampered
    # index set, so this check cannot be fooled by metadata alone.
    #
    # Adversarial round 18, medium finding: round 13's check above only
    # covers an UNDER-claim (metadata says 0, state dict has real growth
    # tensors). The inverse -- metadata OVER-claims growth_blocks>0 while the
    # state dict carries NO growth.* keys at all (a stripped grown
    # checkpoint) -- used to sail straight through, since the old guard only
    # tested `derived_growth_blocks != 0`. Reuse the same shape (claim vs.
    # state-dict-derived) that `infer_model_config`'s
    # `_verify_metadata_matches_shapes` uses for every other ModelConfig
    # field: the claim and the derivation must AGREE, and the only value
    # this function is willing to grow from is 0/0. Any other combination --
    # over-claim, under-claim, or a genuinely-already-grown anchor where both
    # agree at a nonzero count -- raises, naming both values, since growing
    # an already-grown (or inconsistently-labeled) net is out of scope.
    derived_growth_blocks = _derive_growth_blocks(payload["model"])
    if anchor_config.growth_blocks != 0 or derived_growth_blocks != 0:
        raise RuntimeError(
            "anchor checkpoint is not a valid growth_blocks=0 base for grow_b2b_model: "
            f"metadata claims growth_blocks={anchor_config.growth_blocks}, but the state "
            f"dict's derived growth block count is {derived_growth_blocks} (field: "
            f"(claimed, shape_derived))=growth_blocks=({anchor_config.growth_blocks}, "
            f"{derived_growth_blocks}); growing an already-grown net (or a checkpoint "
            "whose metadata claim disagrees with its own tensors) is out of scope"
        )
    # Cross-check the metadata-claimed dims this warm start's construction
    # depends on (`channels`, `residual_blocks`) against the anchor's actual
    # tensor shapes, BEFORE any surgery -- the same claimed-vs-derived
    # discipline as the growth_blocks check just above, applied to the other
    # dims a wrong metadata claim could silently misattribute. Reuses
    # `infer_model_config`'s own shape-inference helper (`_shape_inferred_fields`,
    # which derives `channels` from the first plane-stem conv's weight shape
    # and `residual_blocks` from the count of distinct `plane_blocks.{i}`
    # indices) rather than re-deriving these formulas here.
    shape_fields = _shape_inferred_fields(payload["model"])
    dim_mismatches = {
        field: (getattr(anchor_config, field), shape_fields[field])
        for field in ("channels", "residual_blocks")
        if getattr(anchor_config, field) != shape_fields[field]
    }
    if dim_mismatches:
        raise RuntimeError(
            "grow_b2b_model: anchor metadata's construction dims do not match its own "
            f"tensor shapes (field: (claimed, shape_derived))={dim_mismatches} -- refusing "
            "to grow a model built from a mismatched claim"
        )
    grown_config = replace(anchor_config, growth_blocks=growth_blocks)
    anchor_env_config = _reconstruct_env_config(payload["model"], anchor_config)
    if env_config is not None:
        _assert_b2b_anchor_matches_live_env("grow_b2b_model", anchor_env_config, anchor_config, env_config)
    model = PolicyValueNet(anchor_env_config, grown_config).to(device)
    _, report = load_compatible_checkpoint(anchor_checkpoint, model)
    # FAIL CLOSED: every anchor tensor must load same-shape except the brand
    # new `growth.*` keys (missing from the anchor by construction, since it
    # predates this warm start). Anything else silently dropping an anchor
    # layer would break the step-0 parity invariant.
    bad_skipped = [k for k in report["skipped_keys"] if not k.startswith("growth.")]
    bad_missing = [k for k in report["missing_keys"] if not k.startswith("growth.")]
    if bad_skipped or bad_missing:
        raise RuntimeError(
            "anchor checkpoint is architecturally incompatible with the grown model "
            f"config (skipped={bad_skipped[:6]}, missing={bad_missing[:6]}) — its "
            "metadata['model_config'] does not match its own saved tensor shapes"
        )
    model.eval()
    return model


def widen_event_gru(anchor_checkpoint: Path, new_hidden_dim: int,
                    env_config: Optional[EnvConfig] = None, device: str = "cpu") -> PolicyValueNet:
    """Warm-start a wider event-GRU by identity-masked widening (gru-width
    lap, spec §2). Unlike `grow_b2b_model` (which stacks brand-new ReZero
    blocks that are identity at alpha=0), this WIDENS an existing recurrent
    layer in place: the anchor's `event_hidden_dim` (H_old) grows to
    `new_hidden_dim` (H_new > H_old), and a new `event_encoder.output_proj`
    (`event_output_dim = H_old`) projects the widened H_new-dim GRU output
    back down to the trunk's original H_old-dim interface, so every
    downstream consumer (trunk, privileged value head) sees an unchanged
    input width and step-0 outputs equal the anchor's exactly.

    The anchor must be a complete post-B2b checkpoint (`metadata['model_config']`
    present — event_window is not recoverable from tensor shapes alone) with
    `event_window > 0` (an active event encoder to widen) and
    `event_output_dim == 0` (dormant/un-widened: widening an already-widened
    anchor, or one whose own state dict already carries `output_proj` keys
    while its metadata claims otherwise, is out of scope and rejected — the
    claim and the state dict must agree, mirroring `grow_b2b_model`'s
    claimed-vs-derived discipline). `new_hidden_dim <= H_old` is rejected
    (this warm start only widens). `env_config`, when given, is cross-checked
    against the anchor's own construction shapes via the same helper
    `grow_b2b_model` uses (`_assert_b2b_anchor_matches_live_env`).

    Weight surgery (step-zero exactness is the invariant; the parity test is
    the enforcement) — PyTorch GRU gate order is r, z, n; each gate's weight
    block is `H` rows/cols wide:
      - `embedding`, `side_proj`, and every non-`event_encoder.gru`/
        `event_encoder.output_proj` tensor: copied verbatim (the surgical
        keys below are the ONLY architectural delta; anything else silently
        skipped/missing is a fail-closed error).
      - `weight_ih_l0` ([3*H_new, E]): per gate g, rows
        `[g*H_new : g*H_new+H_old]` (old units) copied from the anchor's
        `[g*H_old : (g+1)*H_old]`; the remaining `H_new-H_old` rows per gate
        (new units) keep their normal random init.
      - `weight_hh_l0` ([3*H_new, H_new]): per gate g, rows
        `[g*H_new : g*H_new+H_old]`, columns `[0:H_old]` (the [old, old]
        block) copied from the anchor; the SAME rows, columns `[H_old:H_new]`
        (old-gate-rows seeing new-hidden-cols) are ZEROED so old units never
        see new-unit activations (the invariant this whole surgery hinges
        on); the new-unit rows (any column) keep their normal random init.
      - `bias_ih_l0` / `bias_hh_l0` ([3*H_new]): per gate g, entries
        `[g*H_new : g*H_new+H_old]` copied; the remaining `H_new-H_old`
        entries per gate keep their normal random init.
      - `output_proj`: weight `[I_{H_old} | 0]` (identity over the old H_old
        units, zero over the new H_new-H_old units — so `gathered @
        weight.T` reproduces exactly the old units' hidden state), bias
        zero.

    Step-zero parity (binding, tested elsewhere): event features, policy
    logits, value, Q, aux outputs, and greedy actions EXACTLY equal the
    anchor's on random obs/event batches (`torch.equal`) — this is what
    catches any surgery mistake, including a missed old<-new zero block."""
    anchor_checkpoint = Path(anchor_checkpoint)
    payload = torch.load(anchor_checkpoint, map_location="cpu")
    metadata = payload.get("metadata") or {}
    model_config_meta = metadata.get("model_config")
    if not isinstance(model_config_meta, dict):
        raise RuntimeError(
            "anchor lacks complete model_config metadata — widen_event_gru requires a "
            "post-B2b checkpoint saved with metadata['model_config'] (event_window is not "
            "recoverable from tensor shapes alone)"
        )
    anchor_config = ModelConfig(**model_config_meta)
    if anchor_config.event_window <= 0:
        raise RuntimeError(
            f"anchor has event_window={anchor_config.event_window} — widen_event_gru requires "
            "an anchor with an active event encoder (event_window > 0) to widen"
        )
    # Trust the STATE DICT, not the metadata's event_output_dim claim (same
    # discipline as grow_b2b_model's derived-growth-blocks cross-check): an
    # anchor whose metadata lies about event_output_dim==0 while its tensors
    # actually carry an event_encoder.output_proj.* key (already widened, or
    # tampered) would otherwise be accepted as a fresh base, silently
    # double-widening it.
    derived_has_output_proj = "event_encoder.output_proj.weight" in payload["model"]
    if anchor_config.event_output_dim != 0 or derived_has_output_proj:
        raise RuntimeError(
            "anchor checkpoint is not a valid event_output_dim=0 base for widen_event_gru: "
            f"metadata claims event_output_dim={anchor_config.event_output_dim}, but the "
            f"state dict {'has' if derived_has_output_proj else 'does not have'} an "
            "event_encoder.output_proj.weight key; widening an already-widened (or "
            "inconsistently-labeled) anchor is out of scope"
        )
    # Cross-check the metadata-claimed `event_hidden_dim`/`event_embed_dim`
    # against the anchor's actual tensor shapes, BEFORE any surgery. The
    # manual GRU slicing a few lines down uses `old_hidden_dim` (read
    # straight off `anchor_config`, i.e. the metadata claim) to compute gate
    # row boundaries into `event_encoder.gru.weight_ih_l0`/`weight_hh_l0` --
    # those tensors are exempt from `load_compatible_checkpoint`'s
    # same-shape fail-closed check below (they're the surgical keys this
    # function is allowed to reshape), so a wrong `event_hidden_dim` claim
    # would otherwise slide straight past that check and silently
    # misattribute gate rows in the slicing instead of failing. Reuses
    # `infer_model_config`'s own shape-inference helper
    # (`_shape_inferred_fields`), which derives `event_hidden_dim` as
    # `weight_ih_l0.shape[0] // 3` and `event_embed_dim` as
    # `embedding.weight.shape[1]`.
    shape_fields = _shape_inferred_fields(payload["model"])
    dim_mismatches = {
        field: (getattr(anchor_config, field), shape_fields[field])
        for field in ("event_hidden_dim", "event_embed_dim")
        if field in shape_fields and getattr(anchor_config, field) != shape_fields[field]
    }
    if dim_mismatches:
        raise RuntimeError(
            "widen_event_gru: anchor metadata's event dims do not match its own tensor "
            f"shapes (field: (claimed, shape_derived))={dim_mismatches} -- refusing to "
            "widen a GRU built from a mismatched claim"
        )
    old_hidden_dim = anchor_config.event_hidden_dim
    if new_hidden_dim <= old_hidden_dim:
        raise RuntimeError(
            f"new_hidden_dim ({new_hidden_dim}) must be strictly greater than the anchor's "
            f"event_hidden_dim ({old_hidden_dim}) — widen_event_gru only widens"
        )
    widened_config = replace(anchor_config, event_hidden_dim=new_hidden_dim,
                             event_output_dim=old_hidden_dim)
    anchor_env_config = _reconstruct_env_config(payload["model"], anchor_config)
    if env_config is not None:
        _assert_b2b_anchor_matches_live_env("widen_event_gru", anchor_env_config, anchor_config, env_config)
    model = PolicyValueNet(anchor_env_config, widened_config).to(device)
    _, report = load_compatible_checkpoint(anchor_checkpoint, model)
    # FAIL CLOSED: every anchor tensor must load same-shape except the GRU's
    # own widened tensors and the brand new output_proj — anything else
    # silently dropping an anchor layer would break the step-0 parity
    # invariant.
    surgical_prefixes = ("event_encoder.gru.", "event_encoder.output_proj.")
    bad_skipped = [k for k in report["skipped_keys"] if not k.startswith(surgical_prefixes)]
    bad_missing = [k for k in report["missing_keys"] if not k.startswith(surgical_prefixes)]
    if bad_skipped or bad_missing:
        raise RuntimeError(
            "anchor checkpoint is architecturally incompatible with the widened model "
            f"config (skipped={bad_skipped[:6]}, missing={bad_missing[:6]}) — its "
            "metadata['model_config'] does not match its own saved tensor shapes"
        )
    anchor_state = payload["model"]
    with torch.no_grad():
        gru = model.event_encoder.gru
        h_old, h_new = old_hidden_dim, new_hidden_dim
        old_weight_ih = anchor_state["event_encoder.gru.weight_ih_l0"]  # [3*h_old, E]
        old_weight_hh = anchor_state["event_encoder.gru.weight_hh_l0"]  # [3*h_old, h_old]
        old_bias_ih = anchor_state["event_encoder.gru.bias_ih_l0"]      # [3*h_old]
        old_bias_hh = anchor_state["event_encoder.gru.bias_hh_l0"]      # [3*h_old]
        for gate in range(3):
            old_rows = slice(gate * h_old, (gate + 1) * h_old)
            new_old_rows = slice(gate * h_new, gate * h_new + h_old)
            gru.weight_ih_l0[new_old_rows, :].copy_(old_weight_ih[old_rows, :])
            gru.bias_ih_l0[new_old_rows].copy_(old_bias_ih[old_rows])
            gru.bias_hh_l0[new_old_rows].copy_(old_bias_hh[old_rows])
            # weight_hh: [old rows, old cols] copied verbatim; [old rows, new
            # cols] ZEROED (old units must never see new-unit activations, or
            # step-zero drifts). [new rows, any col] keep their normal init —
            # new-unit dynamics are free, since output_proj masks them out.
            gru.weight_hh_l0[new_old_rows, :h_old].copy_(old_weight_hh[old_rows, :])
            gru.weight_hh_l0[new_old_rows, h_old:].zero_()
        proj = model.event_encoder.output_proj
        assert proj is not None, "widened_config.event_output_dim == old_hidden_dim > 0"
        proj.weight.zero_()
        proj.weight[:, :h_old].copy_(torch.eye(h_old, dtype=proj.weight.dtype))
        proj.bias.zero_()
    model.eval()
    return model


def _assemble_hindsight_labels(rows: list[tuple[int, int]], hand_outcomes: dict[int, dict],
                               final_scores: dict[int, float], bust_threshold: float,
                               truncated: bool) -> tuple[np.ndarray, np.ndarray]:
    """Pure hindsight-label assembler (Spec B2b).

    `rows`: (seat, hand_id) tuples in EMISSION order (seat-contiguous blocks,
    matching the collector's flat emission order). `hand_outcomes`: hand_id ->
    decoded round-outcome dict (bridge's `_decode_round_outcome`); a hand with
    no entry (e.g. the mock bridge, which never produces `round_outcome`)
    contributes no deal-in signal. `final_scores`: seat -> final match score
    for all 4 seats. Returns `(dealin float32[N], rank int64[N])`.

    dealin[i] = 1.0 iff rows[i]'s hand closed as a non-draw `ACTION_RON` paid
    by that row's own seat (`discarder_seat == seat`); deal-in labels survive
    truncation (they are a fact about a hand that already closed).

    rank: -1 for every row when `truncated` (no valid final standings, since
    the match never reached a terminal state); otherwise each seat's 0-based
    COMPETITION rank (the count of non-busted seats with strictly greater
    score — tied scores SHARE a rank, matching the engine's standings; an
    arbitrary tiebreak would teach one tied leader it finished second), and
    4 for any seat whose score is <= `bust_threshold` (busted seats never
    receive a numeric placement)."""
    dealin = np.zeros(len(rows), dtype=np.float32)
    for i, (seat, hand_id) in enumerate(rows):
        outcome = hand_outcomes.get(hand_id)
        if outcome is None:
            continue
        if (not outcome.get("is_draw", False)
                and outcome.get("win_type_name") == "ACTION_RON"
                and int(outcome.get("discarder_seat", -1)) == seat):
            dealin[i] = 1.0

    if truncated:
        rank_by_seat = {seat: -1 for seat in final_scores}
    else:
        seats_sorted = sorted(final_scores)
        non_busted = [s for s in seats_sorted if final_scores[s] > bust_threshold]
        rank_by_seat = {
            s: sum(1 for other in non_busted if final_scores[other] > final_scores[s])
            for s in non_busted
        }
        for s in seats_sorted:
            rank_by_seat.setdefault(s, 4)

    rank = np.asarray([rank_by_seat.get(seat, -1) for seat, _ in rows], dtype=np.int64)
    return dealin, rank


@dataclass
class _B2bMatchState:
    """Per-match accumulator shared by the process collector
    (`collect_b2b_rollouts`) and the batched collector (`batched_b2b.py`).

    `seat_*` lists are indexed by seat (0-3) and hold one entry per decision
    that seat made, in decision order. `seat_hand_ids[k][i]` is the hand
    (0-based, incremented every time a step surfaces `round_outcome`) during
    which that decision was made; `hand_outcomes` maps hand_id -> decoded
    round-outcome dict. `match_net` is the per-seat match-level net reward
    accumulated from EVERY step's rewards (reset rewards included), in the
    bridge's units (score deltas / 1000). `truncated` is the env's truncation
    flag at match end. `_finalize_b2b_match` consumes one of these."""
    seat_planes: list[list] = field(default_factory=lambda: [[], [], [], []])
    seat_scalars: list[list] = field(default_factory=lambda: [[], [], [], []])
    seat_masks: list[list] = field(default_factory=lambda: [[], [], [], []])
    seat_actions: list[list] = field(default_factory=lambda: [[], [], [], []])
    seat_logprobs: list[list] = field(default_factory=lambda: [[], [], [], []])
    seat_values: list[list] = field(default_factory=lambda: [[], [], [], []])
    seat_rewards: list[list] = field(default_factory=lambda: [[], [], [], []])
    seat_events: list[list] = field(default_factory=lambda: [[], [], [], []])
    seat_lengths: list[list] = field(default_factory=lambda: [[], [], [], []])
    seat_hand_ids: list[list] = field(default_factory=lambda: [[], [], [], []])
    hand_id: int = 0
    hand_outcomes: dict[int, dict] = field(default_factory=dict)
    match_net: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=np.float64))
    truncated: bool = False

    def credit_step_rewards(self, rewards) -> None:
        """Add a step's (or the reset's) per-seat rewards to `match_net`
        unconditionally, and to the last recorded transition of every seat
        that has already acted (PPO telescoping credit)."""
        sr = np.asarray(rewards, dtype=np.float64)
        n = min(4, sr.shape[-1])
        self.match_net[:n] += sr[:n]
        for k in range(4):
            if self.seat_rewards[k]:
                self.seat_rewards[k][-1] += _seat_step_reward(rewards, k)

    def record_outcome(self, outcome) -> bool:
        """Close the current hand with `outcome` (a step's
        `info["round_outcome"]`); no-op on a falsy outcome. Returns whether
        an outcome was recorded."""
        if not outcome:
            return False
        self.hand_outcomes[self.hand_id] = outcome
        self.hand_id += 1
        return True


_B2B_ROW_KEYS = ("planes", "scalars", "masks", "actions", "logprobs", "values", "rewards",
                 "dones", "events", "lengths", "dealin", "rank")


def _finalize_b2b_match(ms: _B2bMatchState, config: PPOConfig, cfg: EnvConfig,
                        seed: int) -> tuple[dict[str, list], dict]:
    """Pure match-end tail shared by both B2b collectors.

    `ms`: the finished match's `_B2bMatchState`. `config`: the PPOConfig
    (placement bonus values/lambda, match_mode). `cfg`: the EnvConfig the
    bridge actually simulated under (chongci starting score / bust threshold
    are read from here so labels can never diverge from the played match).
    `seed`: the match seed, for telemetry and error messages.

    Returns `(rows, telemetry)`. `rows` maps each key in `_B2B_ROW_KEYS`
    (planes, scalars, masks, actions, logprobs, values, rewards, dones,
    events, lengths, dealin, rank) to a flat list in seat-contiguous emission
    order (seats 0..3, seats with zero decisions skipped); `telemetry` is the
    seed-keyed match-level dict. Applies the placement bonus to each seat's
    last transition (mutates `ms.seat_rewards`). Every placement-bonus
    fail-closed check (truncated match, zero-decision seat, nonzero bonus
    sum) raises from here.

    UNITS: the Go env emits chongci rewards as score deltas / 1000 in
    float32. Labels are computed in EXACT integer points: the accumulated
    float net is scaled back by 1000 and rounded (float32 drift over a match
    is << 0.5 points), so exact-threshold busts and score ties cannot flip on
    rounding order."""
    chongci = config.match_mode == "chongci"
    starting_score = float(cfg.chongci_starting_score) if chongci else 0.0
    bust_threshold = float(cfg.chongci_bust_threshold) if chongci else float("-inf")
    bonus_values = config.placement_bonus_values
    bonus_on = bonus_values is not None
    bonus_lambda = float(config.placement_bonus_lambda) if bonus_on else 0.0
    is_truncated = bool(ms.truncated)
    match_net = ms.match_net
    seat_rewards = ms.seat_rewards
    final_scores = {k: starting_score + round(float(match_net[k]) * 1000.0) for k in range(4)}
    int_scores = exact_final_scores(match_net, starting_score)
    assert [starting_score + round(float(match_net[k]) * 1000.0) for k in range(4)] == int_scores
    if bonus_on:
        if is_truncated:
            raise RuntimeError(
                f"placement bonus: match seed {seed} was truncated — no "
                "terminal rank exists; fail closed (spec Amendment 1 item 4). Any "
                "truncation under this objective is a protocol stop: raise "
                "max_steps_per_episode and/or investigate a stalling policy before "
                "retrying.")
        empty = [k for k in range(4) if not seat_rewards[k]]
        if empty:
            raise RuntimeError(
                f"placement bonus: match seed {seed} has zero-decision "
                f"seat(s) {empty}; fail closed")
    utilities = placement_utilities(int_scores, bonus_values) if bonus_on \
        else placement_utilities(int_scores)
    bonus = bonus_lambda * utilities if bonus_on else np.zeros(4)
    if bonus_on:
        if abs(float(bonus.sum())) > 1e-6:
            raise RuntimeError(f"placement bonus: per-match bonus sum {bonus.sum()} != 0")
        for k in range(4):
            seat_rewards[k][-1] += float(bonus[k])
    occ = rank_occupancy(int_scores)
    telemetry = {
        "seed": int(seed),
        "truncated": bool(is_truncated),
        "final_scores": [int(s) for s in int_scores],
        "trajectory_returns": [float(sum(seat_rewards[k])) - float(bonus[k]) for k in range(4)],
        "utilities": [float(u) for u in utilities],
        "bonus": [float(b) for b in bonus],
        "rank_occupancy": occ.tolist(),
        "tied_seats_surplus": int(4 - len(set(int_scores))),
        "busts": int(sum(1 for s in int_scores if s <= bust_threshold)),
    }
    label_rows: list[tuple[int, int]] = []
    for k in range(4):
        label_rows.extend((k, hid) for hid in ms.seat_hand_ids[k])
    dealin_labels, rank_labels = _assemble_hindsight_labels(
        label_rows, ms.hand_outcomes, final_scores, bust_threshold=bust_threshold,
        truncated=is_truncated)
    rows: dict[str, list] = {key: [] for key in _B2B_ROW_KEYS}
    offset = 0
    for k in range(4):
        n = len(ms.seat_actions[k])
        if n == 0:
            continue
        rows["planes"].extend(ms.seat_planes[k])
        rows["scalars"].extend(ms.seat_scalars[k])
        rows["masks"].extend(ms.seat_masks[k])
        rows["actions"].extend(ms.seat_actions[k])
        rows["logprobs"].extend(ms.seat_logprobs[k])
        rows["values"].extend(ms.seat_values[k])
        rows["rewards"].extend(seat_rewards[k])
        rows["dones"].extend([0.0] * (n - 1) + [1.0])
        rows["events"].extend(ms.seat_events[k])
        rows["lengths"].extend(ms.seat_lengths[k])
        rows["dealin"].extend(dealin_labels[offset : offset + n].tolist())
        rows["rank"].extend(rank_labels[offset : offset + n].tolist())
        offset += n
    return rows, telemetry


def _check_chongci_outcomes(chongci: bool, completed: int, outcomes_seen: int) -> None:
    """A completed chongci match ALWAYS surfaces at least one round outcome
    on the step path (internal/rl/env.go attaches boundary and terminal
    outcomes). Zero outcomes across completed matches means the bridge
    library predates that fix — deal-in supervision would silently degenerate
    to all-negative labels for the whole run. Both collectors call this."""
    if chongci and completed > 0 and outcomes_seen == 0:
        raise RuntimeError(
            "no round outcomes surfaced across "
            f"{completed} completed chongci matches — the Go bridge library "
            "predates chongci round-outcome delivery; rebuild it "
            "(go build -buildmode=c-shared ./cmd/rlbridge)"
        )


def collect_b2b_rollouts(env_config: EnvConfig, model: PolicyValueNet,
                         config: PPOConfig, base_seed: int,
                         action_selection: str = "sample") -> RolloutBatch:
    """Symmetric self-play PPO rollouts for Spec B2b: all four seats are the
    SAME `model`, each seat's transitions recorded seat-contiguously (mirrors
    `collect_selfplay_rollouts`). No feature-dropout (B2b's event/privileged
    channels are always on). Each row additionally carries its event-history
    (tail-padded to `model.model_config.event_window`) and, at match end, the
    hindsight `dealin_labels`/`rank_labels` assembled by
    `_assemble_hindsight_labels` from the `round_outcome` entries seen in
    `StepResult.info` (a step whose info carries `round_outcome` closes the
    CURRENT hand for all seats). `action_selection`: `"sample"` (training)
    draws from the temperature-scaled masked policy with the global torch
    RNG seeded per match; `"greedy"` (parity tests only) takes the argmax of
    the masked logits. Either way the logprob is `ppo.masked_logprob` of the
    chosen action."""
    if action_selection not in ("sample", "greedy"):
        raise ValueError(f"action_selection must be 'sample' or 'greedy', got {action_selection!r}")
    device = config.device
    window = int(model.model_config.event_window)
    cfg = EnvConfig(
        action_space_size=env_config.action_space_size,
        scalar_features=env_config.scalar_features,
        bridge_kind=env_config.bridge_kind,
        bridge_library_path=env_config.bridge_library_path,
        learning_seats=(0, 1, 2, 3),
        auto_play_heuristics=False,
        max_steps_per_episode=config.max_steps_per_episode,
        match_mode=config.match_mode,
        chongci_starting_score=env_config.chongci_starting_score,
        chongci_bust_threshold=env_config.chongci_bust_threshold,
        chongci_max_hands=env_config.chongci_max_hands,
        oracle_observation=True,
        event_history_window=window,
    )
    bridge = build_bridge(cfg)
    env = MahjongEnv(cfg, bridge=bridge)
    model.eval()
    chongci = config.match_mode == "chongci"
    rows_l: dict[str, list] = {key: [] for key in _B2B_ROW_KEYS}
    truncated_matches = 0
    completed_matches = 0
    outcomes_seen = 0
    bonus_on = config.placement_bonus_values is not None
    match_telemetry: list[dict] = []
    try:
        for m in range(config.matches_per_iter):
            obs = env.reset(seed=base_seed + m)
            torch.manual_seed(int(base_seed + m))
            reset_result = env.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                if bonus_on:
                    raise RuntimeError(
                        f"placement bonus: match seed {base_seed + m} ended at reset "
                        "(no four-seat terminal standing) — fail closed")
                continue
            # Match-level net per seat is accumulated UNCONDITIONALLY (incl.
            # reset-time autoplay rewards and payouts landing before a seat's
            # first decision) — the transition-crediting buffers only credit
            # seats that have already acted, which is correct for PPO
            # telescoping but would corrupt final scores for rank labels.
            ms = _B2bMatchState()
            if reset_result is not None:
                ms.credit_step_rewards(reset_result.rewards)
            step = None
            while True:
                seat = int(obs.seat)
                planes_np = np.asarray(obs.planes, dtype=np.float32)
                scalars_np = np.asarray(obs.scalars, dtype=np.float32)
                mask_np = np.asarray(obs.action_mask, dtype=np.int8)
                row_events = np.zeros(window, dtype=np.uint32)
                ev = np.asarray(obs.event_history, dtype=np.uint32)
                ev_len = min(int(ev.shape[0]), window)
                if ev_len > 0:
                    # TAIL of the history (newest events) — matches the
                    # serving-side TorchGreedyPolicy convention. Unreachable
                    # difference today (bridge window == model window) but the
                    # conventions must not drift.
                    row_events[:ev_len] = ev[-ev_len:]
                planes = torch.from_numpy(planes_np).unsqueeze(0).to(device)
                scalars = torch.from_numpy(scalars_np).unsqueeze(0).to(device)
                amask = torch.from_numpy(mask_np).unsqueeze(0).to(device)
                events_t = torch.from_numpy(row_events.astype(np.int64)).unsqueeze(0).to(device)
                length_t = torch.tensor([ev_len], dtype=torch.int64, device=device)
                with torch.no_grad():
                    logits, value = model(planes, scalars, amask, events=events_t, event_lengths=length_t)
                    if action_selection == "greedy":
                        action = int(torch.argmax(logits[0]).item())
                    else:
                        scaled = logits / max(config.sample_temperature, 1e-6)
                        action = int(masked_policy_distribution(scaled).sample()[0].item())
                    logprob = masked_logprob(logits[0], config.sample_temperature, action)
                    val = float(value[0].item())
                ms.seat_planes[seat].append(planes_np)
                ms.seat_scalars[seat].append(scalars_np)
                ms.seat_masks[seat].append(mask_np)
                ms.seat_actions[seat].append(action)
                ms.seat_logprobs[seat].append(logprob)
                ms.seat_values[seat].append(val)
                ms.seat_rewards[seat].append(0.0)
                ms.seat_events[seat].append(row_events)
                ms.seat_lengths[seat].append(ev_len)
                ms.seat_hand_ids[seat].append(ms.hand_id)
                step = env.step(action)
                ms.credit_step_rewards(step.rewards)
                if ms.record_outcome(step.info.get("round_outcome")):
                    outcomes_seen += 1
                if step.terminated or step.truncated:
                    break
                obs = step.observation
            ms.truncated = bool(step.truncated) if step is not None else False
            if ms.truncated:
                truncated_matches += 1
            else:
                completed_matches += 1
            rows, telemetry = _finalize_b2b_match(ms, config, cfg, base_seed + m)
            match_telemetry.append(telemetry)
            for key in _B2B_ROW_KEYS:
                rows_l[key].extend(rows[key])
    finally:
        close = getattr(bridge, "close", None)
        if callable(close):
            close()
    _check_chongci_outcomes(chongci, completed_matches, outcomes_seen)
    if not rows_l["actions"]:
        raise RuntimeError("collect_b2b_rollouts produced no decisions")
    return RolloutBatch(
        planes=np.stack(rows_l["planes"]).astype(np.float32),
        scalars=np.stack(rows_l["scalars"]).astype(np.float32),
        action_mask=np.stack(rows_l["masks"]).astype(np.int8),
        actions=np.asarray(rows_l["actions"], dtype=np.int64),
        old_logprobs=np.asarray(rows_l["logprobs"], dtype=np.float32),
        values=np.asarray(rows_l["values"], dtype=np.float32),
        rewards=np.asarray(rows_l["rewards"], dtype=np.float32),
        dones=np.asarray(rows_l["dones"], dtype=np.float32),
        truncated_matches=truncated_matches,
        events=np.stack(rows_l["events"]).astype(np.uint32),
        event_lengths=np.asarray(rows_l["lengths"], dtype=np.int32),
        dealin_labels=np.asarray(rows_l["dealin"], dtype=np.float32),
        rank_labels=np.asarray(rows_l["rank"], dtype=np.int64),
        match_telemetry=match_telemetry,
    )


def _b2b_worker_loop(env_config, model_config, ppo_config, task_q, result_q):
    import torch as _torch

    from .model import PolicyValueNet as _PVN

    _torch.set_num_threads(1)
    model = _PVN(_b2b_model_env_config(env_config), model_config)
    while True:
        task = task_q.get()
        if task is None:
            return
        worker_id, state_dict, base_seed, matches = task
        try:
            model.load_state_dict(state_dict)
            cfg = replace(ppo_config, matches_per_iter=matches, device="cpu")
            batch = collect_b2b_rollouts(env_config, model, cfg, base_seed=base_seed)
            result_q.put((worker_id, batch, None))
            batch = None  # release our reference; the queue keeps the object alive until the feeder thread has serialized it, then all copies are freed
        except Exception:  # noqa: BLE001 - report any worker failure to the parent
            result_q.put((worker_id, None, traceback.format_exc()))


class ParallelB2bCollector:
    """Spawn-context worker pool for Spec B2b self-play rollouts, concatenated
    into one RolloutBatch. Mirrors `ParallelSelfplayCollector` (seeding,
    seed-block splitting, result-queue conventions) minus `drop_prob` — B2b has
    no feature-dropout schedule.

    `worker_target` (adversarial round 9, medium finding) overrides the
    per-worker process entry point; defaults to `_b2b_worker_loop`, the
    production path. This exists ONLY so tests (e.g. `test_collect_bench.py`'s
    spawn-path perturbation regressions) can inject a test-only worker
    function -- picklable by `multiprocessing`'s spawn context because it is
    a plain module-level callable, not a closure -- instead of the previous
    `FH_MAHJONG_TEST_B2B_PERTURB_FIELD` environment variable the production
    worker used to read. That env var was a production-code hook: any
    process (a CI runner, a shell profile, an inherited env from a parent
    launcher) that happened to set it would silently corrupt real training
    data, since spawned child processes inherit the parent's environment.
    Production callers (`train_b2b`) never pass `worker_target`, so they are
    unaffected."""

    def __init__(self, env_config: EnvConfig, model_config: ModelConfig,
                 ppo_config: PPOConfig, num_workers: int,
                 worker_target: Optional[Callable] = None) -> None:
        if num_workers < 1:
            raise ValueError("num_workers must be >= 1")
        self.env_config = env_config
        self.model_config = model_config
        self.ppo_config = ppo_config
        self.num_workers = int(num_workers)
        self._worker_target = worker_target if worker_target is not None else _b2b_worker_loop
        self._ctx = mp.get_context("spawn")
        self._task_q = None
        self._result_q = None
        self._procs = []

    def start(self) -> None:
        self._task_q = self._ctx.Queue()
        self._result_q = self._ctx.Queue()
        self._procs = []
        for _ in range(self.num_workers):
            p = self._ctx.Process(
                target=self._worker_target,
                args=(self.env_config, self.model_config, self.ppo_config,
                      self._task_q, self._result_q),
                daemon=True,
            )
            p.start()
            self._procs.append(p)

    def collect(self, state_dict, base_seed: int, matches_per_iter: int) -> RolloutBatch:
        """Collect `matches_per_iter` matches, in bounded sequential dispatch
        rounds of at most `ppo_config.collect_dispatch_chunk` matches each
        (0 = one round, the legacy behavior). Chunking bounds per-worker
        resident trajectory memory at ~chunk/num_workers matches — without it
        every worker holds its ENTIRE matches/num_workers block before the
        first result returns, which OOM'd the 31GB box at 960 matches
        (data-scale-960 Amendment 2, 2026-08-12 consult). Chunks run over
        contiguous seed blocks in ascending order and concatenate in that
        order, so together with per-match seeding
        (`torch.manual_seed(base_seed + m)` in `collect_b2b_rollouts`) the
        result is bit-identical to a single dispatch — digest-pinned by
        test_collect_bench's chunk-parity tests.

        Amendment 5 (data-scale-960, 2026-08-15): the worker pool is closed
        after the FINAL dispatch's results have been received and before any
        remaining concatenation, then recreated on the next collect. The
        Amendment 4 profile measured the persistent pool at ~18.4GiB (10
        workers) held through the master's outer-concat transient — the two
        together are what breached the host ceiling at 960 matches. Teardown
        happens after every result is in hand, so seed coverage and canonical
        row order are untouched; the error paths inside `_collect_dispatch`
        already close the pool."""
        if not self._procs:
            self.start()
        cap = int(getattr(self.ppo_config, "collect_dispatch_chunk", 0) or 0)
        if cap <= 0 or cap >= matches_per_iter:
            batch = self._collect_dispatch(state_dict, base_seed, matches_per_iter,
                                           final_dispatch=True)
            memprobe.probe("collector_return", rows=len(batch), chunks=1)
            return batch
        chunks = []
        offset = 0
        while offset < matches_per_iter:
            count = min(cap, matches_per_iter - offset)
            final = (offset + count) >= matches_per_iter
            chunks.append(self._collect_dispatch(state_dict, int(base_seed + offset),
                                                 count, final_dispatch=final))
            memprobe.probe("chunk_collected", chunk_index=len(chunks) - 1,
                           matches=int(count), rows=len(chunks[-1]))
            offset += count
        batch = concat_rollout_batches(chunks, consume=True)
        memprobe.probe("collector_return", rows=len(batch), chunks=len(chunks))
        return batch

    def _collect_dispatch(self, state_dict, base_seed: int, matches_per_iter: int,
                          final_dispatch: bool = False) -> RolloutBatch:
        counts = _split_counts(matches_per_iter, self.num_workers)
        offset = 0
        dispatched = 0
        for worker_id, count in enumerate(counts):
            if count == 0:
                continue
            self._task_q.put((worker_id, state_dict, int(base_seed + offset), int(count)))
            offset += count
            dispatched += 1
        results: dict = {}
        received = 0
        while received < dispatched:
            try:
                worker_id, batch, err = self._result_q.get(timeout=30.0)
            except _queue.Empty:
                if any(p.exitcode is not None for p in self._procs):
                    self.close()
                    raise RuntimeError("a B2b rollout worker exited unexpectedly during collect")
                continue
            if err is not None:
                self.close()
                raise RuntimeError(f"B2b rollout worker {worker_id} failed:\n{err}")
            results[worker_id] = batch
            received += 1
        if final_dispatch:
            # Amendment 5: all of this collect's results are in hand — free the
            # pool's ~1.8GiB-per-worker runtime footprint before any further
            # (memory-transient) assembly. The next collect() restarts it.
            self.close()
            memprobe.probe("pool_closed_before_concat", workers=self.num_workers)
        ordered = [results[w] for w in sorted(results)]
        dispatch_batch = concat_rollout_batches(ordered, consume=True)
        memprobe.probe("dispatch_return", rows=len(dispatch_batch), workers=len(ordered))
        return dispatch_batch

    def close(self) -> None:
        if not self._procs:
            return
        for _ in self._procs:
            try:
                self._task_q.put(None)
            except Exception:  # noqa: BLE001
                pass
        for p in self._procs:
            p.join(timeout=10)
            if p.is_alive():
                p.terminate()
        self._procs = []


def train_b2b(env_config: EnvConfig, model_config: ModelConfig, champion_checkpoint: Optional[Path],
             checkpoint_dir: Path, config: PPOConfig, base_seed: int = 0,
             growth_blocks: int = 0, widen_event_hidden: int = 0, train_state_every: int = 5,
             resume_from_state: Optional[Path] = None,
             force_history_reset: bool = False,
             fresh_run_overwrite: bool = False,
             allow_bridge_mismatch: bool = False,
             accept_legacy_unpinned_state: bool = False,
             scratch: bool = False,
             init_from_bc: Optional[Path] = None) -> list[dict]:
    """Spec B2b training: warm-start the event-GRU/privileged-critic/aux-head
    net from the 39ch champion, then run PPO with the aux losses folded in
    automatically by `ppo_update` (it reads `model.model_config.aux_heads` and
    `batch.events`/`batch.dealin_labels`/`batch.rank_labels`). Mirrors
    `train_selfplay_oracle` minus feature-dropout/ACH/the batched-pool path —
    B2b has no dropout schedule and always trains PPO.

    `widen_event_hidden > 0` (gru-width identity-masked warm start) routes
    model construction through `widen_event_gru` instead: `champion_checkpoint`
    must then be a complete post-B2b anchor with a dormant (unwidened) event
    encoder (not the raw 39ch champion the `growth_blocks`/default surgery
    paths expect), and `model_config` is superseded by the widened model's
    own config (the anchor's saved architecture with `event_hidden_dim`
    widened to `widen_event_hidden` and `event_output_dim` set to the
    anchor's original width) so every downstream checkpoint save below
    records the true architecture. Mutually exclusive with
    `growth_blocks > 0` in the same run — both surgeries in one warm start
    is out of scope; the caller (the CLI) rejects that combination before
    this function is ever called.

    `growth_blocks > 0` (deep16-rezero capacity growth) routes model
    construction through `grow_b2b_model` instead: `champion_checkpoint` must
    then be a complete post-B2b anchor (not the raw 39ch champion the
    growth_blocks=0 surgery path expects), and `model_config` is superseded
    by the grown model's own config (the anchor's saved architecture plus
    `growth_blocks` ReZero blocks) so every downstream checkpoint save below
    records the true architecture, including `growth_blocks`.

    `scratch=True` (mortal-scale-scratch) routes model construction through
    `build_scratch_model` instead: there is NO anchor at all, so
    `champion_checkpoint` must be `None` and neither warm-start surgery may
    be requested (both combinations raise below) — the net is built purely
    from the caller's `model_config`, at random init, with no step-0 parity
    to preserve. `init_from_bc`, when given, additionally copies the BC
    stage's plane trunk / scalar encoder / trunk / policy head in by exact
    name+shape (`SCRATCH_BC_PREFIXES`); it requires `scratch=True`. Every
    `iter_*.pt` records which of the two construction paths produced this
    run under `metadata["init"]` (`{"kind": "scratch"|"champion",
    "bc_checkpoint_sha256": ..., "bc_checkpoint_path": ...}`) so a checkpoint's
    provenance is readable without the launch command. `train_state.pt`
    persists that same block, so a resume carries the original provenance
    forward into every checkpoint it goes on to write; only a LEGACY state
    predating that slot degrades to `{"kind": "resumed",
    "bc_checkpoint_sha256": None, "bc_checkpoint_path": None}`. It is
    deliberately not part of `config_echo` — a record of how the run started,
    not a config the resume has to match.

    Resumable state (deep16-rezero capacity lap survives box restarts):
    every `train_state_every` iterations, and always at completion, writes
    `<checkpoint_dir>/train_state.pt` (model + optimizer + torch/cuda/numpy/
    python RNG state + `next_iteration` + a `config_echo` of the three config
    dataclasses, atomically). `resume_from_state`, when given, SKIPS the
    champion/growth warm-start entirely — the model is built directly from
    the CALLER-supplied `model_config` (which must therefore already be the
    EFFECTIVE architecture the run trained under, i.e. for a growth_blocks>0
    lap, the anchor's own config with `growth_blocks` folded in — exactly
    what `config_echo["model_config"]` records) and its weights come from the
    state file, not from `champion_checkpoint`/`growth_blocks`. The
    caller-supplied `config`/`model_config`/`env_config` and `base_seed` are
    validated against the state file (any drift raises `ValueError` naming
    both values) before anything is restored, then training continues from
    `next_iteration` through `config.iterations`, appending to the existing
    `history.json` when it is valid. A missing or malformed history file is
    reset with a warning; checkpoint recovery still proceeds.

    A `next_iteration` already `> config.iterations` raises `ValueError`
    instead of returning an empty history — resuming always intends more
    training, so an exhausted target is an error, not a silent no-op
    (adversarial round 3, Finding 2).

    Every run (fresh or `--resume-from-state`) is tagged with a `run_id`
    (a fresh `uuid4().hex` for new runs; the state file's own `run_id` when
    resuming), persisted in both `train_state.pt["run_id"]` and
    `history.json`'s `{"run_id": ..., "rows": [...]}` wrapper. A resume
    requires `state.run_id == history.run_id` (mismatch raises, naming both)
    so a `train_state.pt` from one run can never be pointed at an unrelated
    run's `history.json`/checkpoints in the same directory. Legacy bare-list
    `history.json` files (written before `run_id` existed) are accepted only
    when the state file also predates `run_id` (both `None`); use
    `read_b2b_history_rows(path)` to read rows back regardless of format
    (adversarial round 3, Finding 1).

    Every `iter_*.pt` checkpoint also carries `metadata["run_id"]`
    (adversarial round 4, high finding). On EVERY resume (adversarial round
    5, high finding: not just when history.json is missing or corrupt --
    round 4's check ran only on that recovery path, so a resume with a
    perfectly valid, matching history.json never inspected checkpoint_dir at
    all), `_check_artifact_lineage_or_raise` validates every existing
    `iter_*.pt` artifact's `run_id` against the resuming state's `run_id`
    before proceeding -- a mismatch (or a legacy artifact with no `run_id`
    while the state has one) raises instead of silently mixing lineages; an
    empty checkpoint_dir passes through. `force_history_reset=True` (the
    CLI's `--force-history-reset`; the name predates this generalization but
    is kept to avoid a runbook-breaking rename -- see its `--help` text)
    skips ONLY that artifact-lineage check, on both the recovery path and
    this unconditional every-resume scan, never the base_seed/config_echo
    checks above.

    A resume also pins the Go simulator library itself, not merely the
    bridge_kind/bridge_library_path *configuration* `config_echo` already
    covers: `train_state.pt["bridge_sha256"]` records the sha256 of the
    library `env_config` resolved to AT SAVE TIME (see
    `_resolve_current_bridge_fingerprint`), and every resume recomputes it
    from the CURRENT resolution and raises, naming both digests, on any
    mismatch -- a rebuild of the .so at the same path leaves `config_echo`
    byte-identical while silently mixing simulator versions across the
    resume boundary (adversarial round 13, high finding). This is never
    safe -- a different simulator changes the very rules the model was
    trained under -- so `force_history_reset` does NOT cover it. The
    dedicated, explicitly attribution-breaking override is
    `allow_bridge_mismatch=True` (the CLI's `--allow-bridge-mismatch`,
    named after `fh-mj-compare`'s own `--allow-bridge-mismatch`), which
    proceeds anyway but logs a warning naming both digests. Mock-bridge runs
    (`bridge_kind != "go"`) have no library to pin: both digests are
    `None`, which compares equal and always passes.

    Snapshot-first ordering (adversarial round 21, high finding): the
    source-fingerprint-and-compare step described in the previous paragraph
    is skipped ENTIRELY whenever this lineage's content-addressed bridge
    snapshot (named by the SAVED digest) already exists in `checkpoint_dir`
    -- the mutable source is not read, hashed, or even resolved in that
    case. Rounds 13-20 always fingerprinted the source here first, so a
    deleted or rebuilt source bricked resume (an unrecoverable raise, since
    the source read/compare happened before the snapshot was ever
    consulted) even though the pinned snapshot bytes sat completely intact
    on disk -- `--allow-bridge-mismatch` could not help, because the
    exception fired before that flag was ever checked. `_resolve_bridge_
    snapshot_for_resume` (below) re-hashes the snapshot's OWN bytes against
    the saved digest and raises if they were tampered with or corrupted --
    the only failure mode an intact-looking snapshot can still have -- with
    no override, since corrupted bytes cannot be un-corrupted. Only when the
    snapshot is ABSENT does this fall back to the source-based recovery
    described above (round 20's missing-snapshot rules, unchanged).

    A Go-backed state saved with no digest at all (`bridge_sha256 is None`,
    i.e. a legacy `train_state.pt` from before this pinning existed) fails
    closed (adversarial round 19, high finding: round 16 accepted this
    unconditionally and left the pin at `None` FOREVER, permanently
    disabling drift detection for the rest of the run's life). Resuming it
    now raises `ValueError` naming the remedy, `accept_legacy_unpinned_state
    =True` (the CLI's `--accept-legacy-unpinned-state`), unless that flag is
    given. WITH the flag, the resume proceeds and establishes a NEW
    provenance boundary starting at this resume: the digest the library
    CURRENTLY resolves to is pinned as this lineage's baseline from here
    forward (recorded in every subsequent `train_state.pt`/`iter_*.pt`), a
    warning is logged naming the new digest, and drift detection resumes
    normally for the rest of the run. Iterations up to and including this
    resume point have unverifiable simulator provenance (nothing was ever
    pinned for them); only iterations from here forward are drift-protected
    again. Mock-bridge states are never affected -- they never enter this
    branch at all (`bridge_kind == "go"` is required).

    A fresh (non-`resume_from_state`) call fails closed if `checkpoint_dir`
    already contains ANY managed artifact -- `history.json`,
    `train_state.pt`, or an `iter_*.pt` checkpoint (adversarial round 6,
    high finding: without this, a mistaken fresh launch into a prior run's
    directory silently overwrote its early checkpoints while leaving later
    ones in place -- mixed lineage, and potentially days of lost progress).
    The `ValueError` names what was found and points at the two legitimate
    fixes: `resume_from_state` to continue that run, or a new/empty
    `checkpoint_dir` for a truly fresh one. `fresh_run_overwrite=True` (the
    CLI's `--fresh-run-overwrite`) is the explicit destructive override: it
    deletes exactly those managed artifacts -- nothing else in the
    directory -- logs what was removed, and then proceeds as a normal fresh
    run. A brand-new or genuinely empty `checkpoint_dir` always proceeds
    without asking (mkdir-if-absent, as before)."""
    # Adversarial review round 2, Finding 2: the routing below is
    # `widen_event_hidden > 0`, so any negative value (e.g. a fat-fingered
    # `-256`) silently falls through to the DEFAULT build_b2b_model path
    # instead of the requested widen_event_gru surgery. With the intended
    # post-B2b anchor for that surgery, the fallback path can succeed
    # outright (its shapes already match a B2b model), silently training the
    # unwidened architecture for a multi-day run before anyone notices.
    # Reject negative values outright; 0 remains the "disabled" sentinel and
    # the upper bound mirrors ModelConfig.MAX_HIDDEN_DIM (the same ceiling
    # event_hidden_dim itself is bounded by).
    if widen_event_hidden < 0:
        raise ValueError(
            f"train_b2b: widen_event_hidden ({widen_event_hidden}) must not be "
            "negative -- 0 disables the gru-width warm-start surgery; a negative "
            "value would silently fall through to the default (unwidened) "
            "build_b2b_model path instead of erroring"
        )
    if widen_event_hidden > ModelConfig.MAX_HIDDEN_DIM:
        raise ValueError(
            f"train_b2b: widen_event_hidden ({widen_event_hidden}) exceeds maximum "
            f"{ModelConfig.MAX_HIDDEN_DIM}"
        )
    if growth_blocks > 0 and widen_event_hidden > 0:
        raise ValueError(
            f"train_b2b: growth_blocks ({growth_blocks}) and widen_event_hidden "
            f"({widen_event_hidden}) cannot both be set in one run -- these are two "
            "distinct warm-start surgeries (ReZero depth growth vs. event-GRU width "
            "growth) and this function does not attempt to reconcile applying both to "
            "the same anchor in a single call"
        )
    # mortal-scale-scratch: the construction paths are mutually exclusive and
    # exactly one must be selectable. `resume_from_state` wins over all of
    # them -- it never constructs from these flags at all (the model comes
    # from the state file), so a resume is deliberately exempt from every
    # check here rather than being made to carry a redundant --scratch.
    # These run BEFORE checkpoint_dir is touched (mkdir/lock/artifact scan)
    # so a mis-flagged launch cannot leave a directory or a lock behind.
    if resume_from_state is None:
        if scratch and champion_checkpoint is not None:
            raise ValueError("scratch=True cannot be combined with a champion checkpoint")
        if scratch and (growth_blocks > 0 or widen_event_hidden > 0):
            raise ValueError("scratch=True cannot be combined with growth_blocks/widen_event_hidden surgery")
        if not scratch and champion_checkpoint is None:
            raise ValueError("champion_checkpoint is required unless scratch=True or resume_from_state is given")
        if init_from_bc is not None and not scratch:
            raise ValueError("init_from_bc requires scratch=True")
        # Amendment 1 §6: the two lr groups are defined by which parameters the
        # BC stage supplied (SCRATCH_BC_PREFIXES). Without a BC init there is
        # no such split -- every parameter is random -- so a head_lr here would
        # silently mean "train these arbitrary modules faster than those".
        if config.head_lr is not None and init_from_bc is None:
            raise ValueError(
                "head_lr requires scratch=True with init_from_bc (groups are defined "
                "relative to the BC-loaded prefixes)")
        # Amendment 1 §6: each field is INERT without the other, and inertness is
        # exactly what a mis-flagged launch cannot afford to discover after a
        # full lap. head_lr with head_lr_iters=0 (the DEFAULT) schedules a warm
        # phase of zero iterations -- every iteration is already past the
        # switch -- so the run silently trains single-rate. head_lr_iters
        # without head_lr never builds a second parameter group at all, so the
        # number is silently ignored. Both raise instead.
        if config.head_lr is not None and config.head_lr_iters < 1:
            raise ValueError(
                f"head_lr ({config.head_lr}) requires head_lr_iters >= 1 (got "
                f"{config.head_lr_iters}) -- a warm phase of zero iterations means "
                "head_lr is never applied and the run trains at a single rate")
        if config.head_lr_iters > 0 and config.head_lr is None:
            raise ValueError(
                f"head_lr_iters ({config.head_lr_iters}) requires head_lr -- without it "
                "there is only one parameter group and the iteration count is ignored")
    device = config.device
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    lock_file = train_state._acquire_checkpoint_dir_lock(checkpoint_dir)
    try:
        state_payload = None
        # Adversarial round 18, high finding: only ever set (non-None) by the
        # fresh `--fresh-run-overwrite` path below, when it moved existing
        # managed artifacts into a backup subdirectory instead of deleting
        # them. `backup_cleared` starts True so a resume (or a fresh run into
        # an empty directory, which never creates a backup) never attempts to
        # clean up a backup that doesn't exist. `durability_trigger` picks
        # which save this run's OWN first durable artifact is: `train_state.pt`
        # when periodic state saves happen at all (`train_state_every > 0`),
        # else the first `iter_*.pt` checkpoint (train_state_every == 0 means
        # train_state.pt is never written for the whole run -- see
        # `test_train_state_every_zero_still_blocks_publish_of_drifted_iteration`).
        overwrite_backup_dir: Optional[Path] = None
        backup_cleared = True
        durability_trigger = "state" if train_state_every > 0 else "checkpoint"
        if resume_from_state is not None:
            # weights_only=False: the state includes numpy/python RNG state (plain
            # tuples/arrays, not just tensors), which torch's default safe
            # unpickler rejects. train_state.pt is our own trusted output.
            # `_load_train_state_with_fallback` also covers the newest
            # generation being unreadable by falling back to `.prev` (see its
            # docstring; adversarial round 9, high finding).
            state_payload = train_state._load_train_state_with_fallback(Path(resume_from_state))
            saved_base_seed = state_payload.get("base_seed", train_state._RESUME_MISSING)
            if saved_base_seed != base_seed:
                raise ValueError(
                    "--resume-from-state base_seed mismatch: "
                    f"state file has {saved_base_seed!r}, requested base_seed is "
                    f"{base_seed!r} — resuming with a different seed schedule is "
                    "not supported (pass the base_seed the original run used)"
                )
            # Adversarial round 13, high finding: config_echo's env_config
            # section only records the bridge_kind/bridge_library_path
            # *configuration*, which stays byte-identical across a rebuild of
            # the .so at the same path -- pin the ACTUAL simulator binary via
            # its content digest instead, recomputed from the CURRENT
            # resolution (never trusted from the state file, which is exactly
            # what a rebuild-between-runs would stale-read).
            saved_bridge_sha256 = state_payload.get("bridge_sha256")
            # Adversarial round 16, high finding: a `train_state.pt` saved by
            # a run from BEFORE the fingerprint-pinning fix existed (rounds
            # 13-15) can legitimately have `bridge_sha256=None` even though
            # `bridge_kind == "go"` -- it simply never recorded one. Treating
            # that the same as the round-13 mismatch check below would raise
            # "bridge library mismatch" (None vs a real current digest) and
            # brick every pre-fix state file outright, which is exactly the
            # kind of state-bricking `force_history_reset` was invented to
            # avoid elsewhere in this function -- except this check does NOT
            # accept `force_history_reset` (see its docstring), so there
            # would be no override at all short of `--allow-bridge-mismatch`,
            # which also (deliberately) logs a scarier "simulator changed
            # mid-lineage" warning that doesn't fit this case. Instead: a
            # `None` SAVED digest on a `bridge_kind == "go"` resume warns
            # loudly and is treated as unpinned-legacy for the rest of THIS
            # run -- no drift comparison is attempted (there is nothing to
            # compare the current digest against), and periodic saves keep
            # writing `bridge_sha256=None` rather than quietly re-pinning to
            # whatever the library happens to hash to now.
            legacy_unpinned_go_resume = env_config.bridge_kind == "go" and saved_bridge_sha256 is None
            if legacy_unpinned_go_resume:
                # Adversarial round 19, high finding: round 16's fix accepted
                # this case unconditionally and kept the pin at `None` FOREVER
                # (every subsequent `_save_train_state` for this lineage wrote
                # `bridge_sha256=None` again), which permanently disabled
                # drift detection for the rest of the run's life instead of
                # merely tolerating the one pre-existing gap. Fail closed
                # instead: a Go-backed resume whose state lacks a digest now
                # raises unless the caller explicitly opts in via
                # `--accept-legacy-unpinned-state`
                # (`accept_legacy_unpinned_state=True`). Opting in does NOT
                # keep the pin null -- it establishes a NEW provenance
                # boundary starting at this resume: the digest the library
                # CURRENTLY resolves to is pinned as of now (recorded in
                # every subsequent `train_state.pt`/`iter_*.pt` going
                # forward), so drift protection resumes for the rest of the
                # run's life. Iterations up to and including this resume
                # point have unverifiable simulator provenance (nothing was
                # ever pinned for them); iterations from here forward are
                # fully covered again.
                if not accept_legacy_unpinned_state:
                    raise ValueError(
                        "--resume-from-state: this bridge_kind='go' train_state.pt "
                        "has bridge_sha256=None -- a LEGACY state saved before "
                        "bridge identity pinning existed. Resuming it silently "
                        "would leave drift detection permanently disabled for the "
                        "rest of this run's life. Pass "
                        "--accept-legacy-unpinned-state to acknowledge this "
                        "state's pre-boundary iterations have unverifiable "
                        "simulator provenance and pin the CURRENT bridge digest "
                        "as a new provenance boundary starting from this resume"
                    )
                current_bridge_path, current_bridge_sha256 = train_state._resolve_current_bridge_fingerprint(env_config)
                logger.warning(
                    "--accept-legacy-unpinned-state: resuming a bridge_kind='go' "
                    "train_state.pt with bridge_sha256=None -- this is a LEGACY "
                    "state saved before bridge identity pinning existed "
                    "(adversarial round 16). Establishing a NEW provenance "
                    "boundary starting now: the library currently resolves to "
                    "%r (bridge_sha256=%r), which is pinned as this lineage's "
                    "baseline from this resume forward. Iterations up to and "
                    "including this resume point have unverifiable simulator "
                    "provenance; only iterations from here forward are "
                    "drift-protected.",
                    current_bridge_path, current_bridge_sha256,
                )
                # Pin the CURRENT digest (not the missing saved one) -- unlike
                # round 16, this lineage is no longer permanently unpinned.
                saved_bridge_sha256 = current_bridge_sha256
                state_payload["bridge_library_path"] = current_bridge_path
            elif env_config.bridge_kind == "go" and train_state._bridge_snapshot_path(checkpoint_dir, saved_bridge_sha256).exists():
                # Adversarial round 21, high finding: rounds 13-20 always
                # fingerprinted the MUTABLE source here to compare it against
                # `saved_bridge_sha256` -- even though `_resolve_bridge_snapshot_
                # for_resume` below is perfectly capable of binding this run to
                # the pinned content-addressed snapshot WITHOUT ever touching
                # the source, when that snapshot is present. A deleted or
                # rebuilt source (e.g. the .so was cleaned up, or rebuilt at the
                # same path for unrelated reasons) made `_resolve_current_bridge_
                # fingerprint` above raise or report a mismatch immediately --
                # bricking resume (or requiring `--allow-bridge-mismatch`) even
                # though the pinned bytes were sitting completely intact in
                # `checkpoint_dir` and nothing about THIS lineage's provenance
                # was actually in question.
                #
                # Fix: snapshot-first. When the snapshot named by the SAVED
                # digest already exists, skip this whole source-fingerprint-
                # and-compare step entirely -- the source is not read, and a
                # deleted/rebuilt source cannot brick or even be observed by
                # this resume. `_resolve_bridge_snapshot_for_resume` below
                # re-hashes the snapshot's OWN bytes (never the source) and
                # raises if those bytes were tampered with/corrupted, which is
                # the only case that should still abort a resume with an
                # intact-looking snapshot on disk. Only when the snapshot is
                # ABSENT does control fall through to the elif-less path below
                # (round 20's existing missing-snapshot recovery, which in turn
                # falls back to the source -- see that function's docstring).
                pass
            else:
                current_bridge_path, current_bridge_sha256 = train_state._resolve_current_bridge_fingerprint(env_config)
                if current_bridge_sha256 != saved_bridge_sha256:
                    if not allow_bridge_mismatch:
                        raise ValueError(
                            "--resume-from-state bridge library mismatch: state file was "
                            f"saved under bridge_sha256={saved_bridge_sha256!r}, the "
                            f"CURRENT bridge resolution ({current_bridge_path!r}) hashes "
                            f"to bridge_sha256={current_bridge_sha256!r} -- the Go "
                            "simulator was rebuilt (or otherwise changed) since this run "
                            "started. Resuming under a different simulator binary is "
                            "never safe -- --force-history-reset does NOT override this "
                            "check. If you have deliberately confirmed the new binary is "
                            "an acceptable, attribution-breaking substitution, pass "
                            "--allow-bridge-mismatch to override"
                        )
                    logger.warning(
                        "--allow-bridge-mismatch: resuming despite a bridge library "
                        "mismatch (state file bridge_sha256=%r, current bridge_sha256=%r "
                        "at %r) -- attribution across this resume boundary is no longer "
                        "guaranteed",
                        saved_bridge_sha256, current_bridge_sha256, current_bridge_path,
                    )
            # Adversarial round 14, high finding: the bridge identity this run
            # threads into every _save_train_state call is pinned HERE, once,
            # to the VALIDATED saved digest -- never the freshly-recomputed
            # `current_bridge_sha256` above, even when --allow-bridge-mismatch
            # let a mismatch through. Recomputing per-save (round 13's
            # behavior) let a mid-run .so replacement quietly become the new
            # baseline; pinning to the saved value keeps the ORIGINAL
            # simulator identity as the one true baseline for this lineage.
            # A legacy-unpinned resume (round 19; see above) already rewrote
            # `saved_bridge_sha256`/`state_payload["bridge_library_path"]` to
            # the CURRENT resolution above -- this is that new provenance
            # boundary's baseline, not the (missing) original one.
            pinned_bridge_sha256 = saved_bridge_sha256
            pinned_bridge_path = state_payload.get("bridge_library_path")
            # Adversarial round 20, high finding: rebind this resumed run to
            # its content-addressed bridge snapshot the same way a fresh run
            # does -- see `_resolve_bridge_snapshot_for_resume`'s docstring
            # for the missing-snapshot/drifted-source recovery rules. Every
            # collector/rollout call below uses `bridge_env_config`, never
            # `env_config`, so the SOURCE path is never consulted again past
            # this point.
            if env_config.bridge_kind == "go":
                snapshot_path, pinned_bridge_sha256 = train_state._resolve_bridge_snapshot_for_resume(
                    env_config, checkpoint_dir, pinned_bridge_sha256, allow_bridge_mismatch)
                train_state._assert_bridge_pinned(env_config, pinned_bridge_sha256)
                bridge_env_config = replace(env_config, bridge_library_path=snapshot_path)
            else:
                bridge_env_config = env_config
            current_echo = train_state._train_b2b_config_echo(config, model_config, env_config)
            train_state._validate_resume_config_echo(current_echo, state_payload["config_echo"])
            model = PolicyValueNet(_b2b_model_env_config(env_config), model_config).to(device)
            model.load_state_dict(state_payload["model"])
            start_iteration = int(state_payload["next_iteration"])
            # Adversarial round 12, high finding: a target lower than the one
            # the state was saved under (but still above start_iteration, so
            # the exhausted-target check below wouldn't catch it) must raise
            # rather than silently truncating the run -- see
            # _validate_resume_iterations_not_truncating's docstring.
            saved_iterations = state_payload["config_echo"]["ppo_config"]["iterations"]
            train_state._validate_resume_iterations_not_truncating(
                config.iterations, saved_iterations, start_iteration)
            # Adversarial round 3, Finding 2: an exhausted target is a silent
            # no-op, not success -- the runbook's resume command always intends
            # MORE training, so a state already past config.iterations must raise
            # loudly instead of returning an empty history.
            if start_iteration > config.iterations:
                raise ValueError(
                    f"state is at iteration {start_iteration - 1}; --iterations "
                    f"{config.iterations} already satisfied — nothing to resume; "
                    "raise --iterations or stop"
                )
            run_id = state_payload.get("run_id")
            # mortal-scale-scratch: a resume never re-runs construction, so it
            # has no construction flags of its own to record -- it inherits
            # the lineage's. `_save_train_state` persists the `init` block, so
            # the checkpoints written after a resume keep saying "scratch"
            # (with the same BC digest) rather than degrading to "resumed" and
            # losing a long lap's provenance across a box restart. Only a
            # LEGACY state, written before that slot existed, has nothing to
            # read -- record "resumed" there rather than guessing at a kind.
            init_meta = state_payload.get("init") or {
                "kind": "resumed", "bc_checkpoint_sha256": None, "bc_checkpoint_path": None,
                "transfer_gate": None}
            history_path = checkpoint_dir / "history.json"
            history = train_state._load_resume_history(history_path, run_id, checkpoint_dir,
                                           start_iteration,
                                           force_history_reset=force_history_reset,
                                           resume_from_state=Path(resume_from_state))
            # Reconcile against a STALE state file: train_state.pt is only written
            # every `train_state_every` iterations (plus at completion), but
            # history.json is appended every iteration. Resuming from a state
            # older than the last history rows (e.g. state saved at iter 5, then
            # iters 6-7 ran and appended to history before the process died
            # without reaching the next state-save at iter 10) must not keep
            # those orphaned rows — the loop below re-runs and re-appends
            # iterations >= start_iteration from scratch, so keep only rows
            # strictly before start_iteration or they'd be duplicated.
            # Re-running iteration N after restoring the exact model/optimizer/
            # RNG state from before it is a deterministic replay of that
            # iteration (same seed derivation from base_seed+iteration, same
            # torch/numpy/python RNG state), so the per-iteration checkpoint
            # `iter_{N:03d}.pt` files it overwrites are recomputed identically —
            # safe to clobber by name, not a second distinct result.
            history: list[dict] = [row for row in history if int(row["iteration"]) < start_iteration]
            # Adversarial round 19, high finding: quarantine every live
            # `iter_N.pt` with `N >= start_iteration` to `iter_N.pt.stale`
            # BEFORE the loop below collects or publishes anything -- see
            # `_quarantine_stale_future_checkpoints`'s docstring for why an
            # old same-run_id checkpoint at/past the resume point is not
            # trustworthy evidence of the trajectory this resume is about to
            # replay. Immediately followed by durably persisting the
            # already-truncated `history` (computed just above) so a crash
            # in the gap before the loop's first iteration leaves on-disk
            # state self-consistent: no live checkpoint or history row past
            # `start_iteration - 1`.
            pending_stale_checkpoints = train_state._quarantine_stale_future_checkpoints(
                checkpoint_dir, start_iteration)
            _write_history_atomic(history_path, {"run_id": run_id, "rows": history})
        else:
            existing_artifacts = train_state._find_fresh_run_managed_artifacts(checkpoint_dir)
            if existing_artifacts and not fresh_run_overwrite:
                names = ", ".join(p.name for p in existing_artifacts)
                raise ValueError(
                    f"checkpoint_dir {checkpoint_dir} already contains managed "
                    f"training artifact(s) ({names}) but this is a fresh run "
                    "(no --resume-from-state was given) -- launching here would "
                    "silently reuse/overwrite a prior run's checkpoints, mixing "
                    "lineages and risking lost progress. Either pass "
                    "--resume-from-state pointed at this directory's "
                    "train_state.pt to continue that run, use a new/empty "
                    "checkpoint_dir for a truly fresh run, or pass "
                    "--fresh-run-overwrite to delete exactly these managed "
                    "artifacts and start fresh here"
                )
            # Adversarial round 18, high finding: --fresh-run-overwrite must be
            # TRANSACTIONAL. The old implementation deleted the prior run's
            # managed artifacts before doing anything else -- if champion/anchor
            # validation, model construction, or bridge-fingerprint resolution
            # then failed, checkpoint_dir was left destroyed with no
            # replacement. Fix: validate everything that can fail FIRST, while
            # the old artifacts are still untouched, and only once all of it
            # succeeds move (never delete outright) the existing managed
            # artifacts into a timestamped backup subdirectory. The backup is
            # removed later, once this run's own first durable artifact is
            # written (see the `overwrite_backup_dir`/`backup_cleared` handling
            # in the training loop below) -- so a failure at ANY point up to
            # and including early iterations of the new run still leaves the
            # old run fully recoverable from the backup directory via a manual
            # move.
            # Amendment 1 §4: only the `--scratch --init-from-bc` construction
            # below has a BC policy to be equal to; every other path leaves
            # this None (there is nothing to prove, not a gate that passed).
            transfer_gate = None
            if growth_blocks > 0:
                model = grow_b2b_model(champion_checkpoint, growth_blocks, device, env_config=env_config)
                model_config = model.model_config
            elif widen_event_hidden > 0:
                model = widen_event_gru(champion_checkpoint, widen_event_hidden,
                                        env_config=env_config, device=device)
                model_config = model.model_config
            elif scratch:
                model = build_scratch_model(_b2b_model_env_config(env_config), model_config, device,
                                            bc_checkpoint=init_from_bc)
                # Amendment 1 §4: prove step-0 == BC BEFORE anything is
                # collected, trained or moved. This raises on any deviation,
                # and it runs here -- inside construction, upstream of the
                # `--fresh-run-overwrite` backup move below -- so a failed
                # transfer aborts with the prior run's artifacts still in
                # place, exactly like the other constructor-side raises.
                if init_from_bc is not None:
                    transfer_gate = verify_bc_transfer(model, init_from_bc,
                                                       _b2b_model_env_config(env_config))
            else:
                model = build_b2b_model(_b2b_model_env_config(env_config), model_config, champion_checkpoint, device)
            # Adversarial round 14, high finding: pin the bridge identity for
            # this fresh run ONCE, before any rollout collection, so every
            # `_save_train_state` call below threads the SAME pinned digest
            # rather than each recomputing (and thus potentially rebasing
            # onto) whatever binary happens to be on disk at save time. Also
            # part of round 18's transactional ordering: this can raise (e.g.
            # a "go" bridge whose library is unreadable), so it too must run
            # before any existing artifact is touched.
            #
            # Adversarial round 20, high finding: this used to pin just a
            # digest of the SOURCE path, which every worker later re-resolved
            # and `dlopen`ed independently -- an ABA swap-and-restore of that
            # mutable path between this hash and a worker's later load defeats
            # the pin entirely. The source bytes are read ONCE here (never
            # re-read after this point); the actual snapshot COPY is deferred
            # until after the `--fresh-run-overwrite` backup-move below (so a
            # content-identical leftover snapshot from a PRIOR run in
            # `existing_artifacts` gets moved into the backup, not confused
            # with this run's own snapshot-to-be), and `bridge_env_config` --
            # bound to that snapshot, never the source -- is what every
            # collector/rollout call below actually uses.
            if env_config.bridge_kind == "go":
                pinned_bridge_path = str(resolve_bridge_library_path(env_config.bridge_library_path))
                bridge_source_bytes, pinned_bridge_sha256 = train_state._read_and_hash_bridge_source(pinned_bridge_path)
                train_state._assert_bridge_pinned(env_config, pinned_bridge_sha256)
            else:
                pinned_bridge_path, pinned_bridge_sha256 = train_state._resolve_current_bridge_fingerprint(env_config)
                bridge_source_bytes = None
            if existing_artifacts:
                names = ", ".join(p.name for p in existing_artifacts)
                overwrite_backup_dir = checkpoint_dir / f".overwrite-backup-{uuid.uuid4().hex}"
                overwrite_backup_dir.mkdir()
                for artifact_path in existing_artifacts:
                    # os.rename: same filesystem (both under checkpoint_dir), so
                    # this is an atomic move, not a copy+delete -- there is no
                    # window where the artifact exists in neither location.
                    os.rename(str(artifact_path), str(overwrite_backup_dir / artifact_path.name))
                backup_cleared = False
                logger.warning(
                    "--fresh-run-overwrite: moved %d prior managed artifact(s) from %s "
                    "into backup %s before starting fresh: %s. This backup is kept "
                    "until the new run writes its first durable checkpoint -- if the "
                    "new run fails before then, the old run is fully recoverable: move "
                    "these files back from %s into %s.",
                    len(existing_artifacts), checkpoint_dir, overwrite_backup_dir, names,
                    overwrite_backup_dir, checkpoint_dir,
                )
            if env_config.bridge_kind == "go":
                snapshot_path = train_state._write_bridge_snapshot_if_needed(
                    checkpoint_dir, pinned_bridge_sha256, bridge_source_bytes)
                bridge_env_config = replace(env_config, bridge_library_path=snapshot_path)
            else:
                bridge_env_config = env_config
            start_iteration = 1
            history = []
            run_id = uuid.uuid4().hex
            # mortal-scale-scratch: record which construction path built this
            # run's weights, alongside the run_id that identifies the lineage.
            # The digest comes from `build_scratch_model`, which hashed the
            # exact bytes it loaded the weights from (M4) -- so every
            # `iter_*.pt` this run writes names the BC checkpoint this model
            # actually came from, even if the file at `init_from_bc` is later
            # replaced mid-run. The path is kept alongside the digest because a
            # bare hash cannot be resolved back to a file by hand.
            init_meta = {
                "kind": "scratch" if scratch else "champion",
                "bc_checkpoint_sha256": getattr(model, "init_from_bc_sha256", None),
                "bc_checkpoint_path": str(init_from_bc) if init_from_bc is not None else None,
                # The step-0 transfer evidence (Amendment 1 §4): the probe's
                # diffs plus the exact loaded/unloaded key sets, so a lap can
                # be audited from any checkpoint it wrote. None on every path
                # with no BC init. `_save_train_state` persists `init` whole,
                # so a resume carries this forward unchanged.
                "transfer_gate": transfer_gate,
            }
            # A fresh run never has anything to quarantine -- either the
            # directory was empty/new, or `--fresh-run-overwrite` just moved
            # every prior managed artifact (including any leftover `.stale`
            # files -- see `_find_fresh_run_managed_artifacts`) into the
            # backup subdirectory above.
            pending_stale_checkpoints: list[Path] = []
        # Belt-and-braces final check before the training loop starts -- see
        # `_assert_bridge_pinned`'s docstring; both branches above already
        # call it right after establishing `pinned_bridge_sha256`, so this
        # should be unreachable in practice.
        train_state._assert_bridge_pinned(env_config, pinned_bridge_sha256)
        train_state._write_lock_owner(lock_file, run_id=run_id)
        model.train()
        optimizer = build_optimizer(model, config)
        if state_payload is not None:
            optimizer.load_state_dict(state_payload["optimizer"])
            torch.set_rng_state(state_payload["torch_rng"])
            if torch.cuda.is_available() and state_payload.get("cuda_rng") is not None:
                torch.cuda.set_rng_state_all(state_payload["cuda_rng"])
            np.random.set_state(state_payload["numpy_rng"])
            random.setstate(state_payload["python_rng"])
        # Amendment 4 (mortal-scale-scratch): snapshot the event pathway HERE --
        # after a resume has restored the weights, before the first iteration --
        # so update norms are true from the first recorded iteration either way.
        # `expect_zero_init` only for a FRESH --init-from-bc lap: a resume and a
        # champion warm start both legitimately carry a non-zero slice.
        event_path = train_state.EventPathTelemetry(
            model, expect_zero_init=(scratch and init_from_bc is not None and start_iteration == 1))
        trunk_alpha = train_state.TrunkAlphaTelemetry(model)
        event_path_init = event_path.initial_metrics()
        if event_path_init is not None:
            logger.info("event-path init: %s", event_path_init)
        collector = None
        pool = None
        if config.collector not in ("process", "batched"):
            # Fail closed: an unrecognized value must never quietly fall back
            # to the process collector and misattribute a whole lap.
            raise ValueError(
                f"unknown PPOConfig.collector {config.collector!r} "
                "(expected 'process' or 'batched')")
        if config.collector == "batched":
            # batched-b2b-collector spec change 4. The pool replaces the spawn
            # workers entirely: one process, `pool_slots` concurrent envs, one
            # batched forward per round on `config.device`. Imported here, not
            # at module scope, because `batched_b2b` imports this module's
            # shared match state and finalizer.
            from .batched_b2b import collect_b2b_rollouts_batched, make_b2b_pool
            if config.num_workers > 1:
                logger.info(
                    "collector=batched: num_workers=%d is ignored (collection runs in "
                    "this process against a %d-slot env pool)",
                    config.num_workers, config.pool_slots)
            # Same snapshot-bound env_config the process collectors get, so a
            # pooled lap can never reach the mutable source library path.
            pool = make_b2b_pool(bridge_env_config, model, config, config.pool_slots)
        elif config.num_workers > 1:
            # Adversarial round 20, high finding: threads the SNAPSHOT-bound
            # env_config into every worker, never the mutable source path --
            # see `bridge_env_config`'s construction above.
            collector = ParallelB2bCollector(bridge_env_config, model_config, config, config.num_workers)
            collector.start()
        # Adversarial round 15, high finding: shared across every
        # `_verify_bridge_unchanged` call this run so a persistently-allowed
        # mismatch (`--allow-bridge-mismatch`) logs its warning ONCE for the
        # whole run rather than once per check (2x per iteration).
        bridge_drift_warned: dict = {"warned": False}
        try:
            for iteration in range(start_iteration, config.iterations + 1):
                # Adversarial round 15, high finding: verify BEFORE collecting
                # this iteration's rollouts -- round 14's check ran only
                # inside `_save_train_state`, so with `train_state_every > 1`
                # (or 0, which never checks at all) a drifted binary could
                # collect, train, and publish several iterations' artifacts
                # before the next periodic save finally caught it.
                train_state._verify_bridge_unchanged(bridge_env_config, pinned_bridge_path, pinned_bridge_sha256,
                                         allow_bridge_mismatch, bridge_drift_warned)
                iter_seed = base_seed + iteration * config.matches_per_iter
                if pool is not None:
                    batch = collect_b2b_rollouts_batched(
                        bridge_env_config, model, config, base_seed=iter_seed, pool=pool)
                elif collector is not None:
                    state = cpu_state_snapshot(model)
                    batch = collector.collect(state, iter_seed, config.matches_per_iter)
                else:
                    batch = collect_b2b_rollouts(bridge_env_config, model, config, base_seed=iter_seed)
                if config.placement_bonus_values is not None:
                    # Spec Amendment 1 item 4: the collector already raises on
                    # an incomplete match, but never let a truncated batch
                    # reach GAE/optimizer under this objective.
                    if int(batch.truncated_matches) != 0:
                        raise RuntimeError(
                            f"iter {iteration}: {batch.truncated_matches} truncated match(es) "
                            "with the placement bonus enabled — fail closed before update")
                    if batch.match_telemetry is None or len(batch.match_telemetry) != config.matches_per_iter:
                        raise RuntimeError(f"iter {iteration}: match telemetry missing or incomplete")
                advantages, returns = compute_gae(batch.rewards, batch.values, batch.dones,
                                                  config.gamma, config.gae_lambda)
                # Amendment 1 §6: re-applied EVERY iteration, before the update
                # that consumes it. Idempotent by construction, so the first
                # iteration after a resume lands on this iteration's lr rather
                # than inheriting whatever the restored optimizer state carried.
                lrs = apply_lr_schedule(optimizer, config, iteration)
                metrics = ppo_update(model, optimizer, batch, advantages, returns, config)
                metrics["iteration"] = iteration
                metrics["mean_reward"] = float(np.sum(batch.rewards) / max(1.0, float(batch.dones.sum())))
                metrics["steps"] = len(batch)
                metrics.update(lrs)
                # Aux-supervision telemetry: an all-zero deal-in rate across many
                # iters is the corrupted-labels signature — watch it in history.json.
                if batch.dealin_labels is not None:
                    metrics["dealin_positive_rate"] = float(np.mean(batch.dealin_labels))
                if batch.rank_labels is not None:
                    metrics["rank_label_coverage"] = float(np.mean(batch.rank_labels >= 0))
                if batch.match_telemetry:
                    bonus = np.asarray([t["bonus"] for t in batch.match_telemetry], dtype=np.float64)
                    occ = np.asarray([t["rank_occupancy"] for t in batch.match_telemetry], dtype=np.float64)
                    metrics["bonus_mean"] = float(bonus.mean())
                    metrics["bonus_rms"] = float(np.sqrt(np.mean(bonus**2)))
                    metrics["bonus_abs_p99"] = float(np.percentile(np.abs(bonus), 99))
                    metrics["tied_seats_surplus_total"] = int(sum(t["tied_seats_surplus"] for t in batch.match_telemetry))
                    metrics["busts_total"] = int(sum(t["busts"] for t in batch.match_telemetry))
                    # per-seat 4th-slot occupancy: seat-bias detector (self-play
                    # aggregate is mechanically ~0.25; only the SPREAD is informative)
                    for k in range(4):
                        metrics[f"seat{k}_fourth_occupancy"] = float(occ[:, k, 3].mean())
                # Adversarial round 2, Finding 1: record growth-block ReZero alpha
                # magnitudes so the runbook's null-interpretation rule ("alphas
                # hugging 0 = protocol null signal") has telemetry to check
                # against. Omitted (not 0.0) for growth-free runs -- see
                # `_growth_alpha_mean_abs`'s docstring.
                growth_alpha_mean_abs = train_state._growth_alpha_mean_abs(model)
                if growth_alpha_mean_abs is not None:
                    metrics["growth_alpha_mean_abs"] = growth_alpha_mean_abs
                # Amendment 4: diagnostic only -- these keys never gate anything.
                event_path_metrics = event_path.record(model, iteration)
                if event_path_metrics is not None:
                    metrics.update(event_path_metrics)
                trunk_alpha_metrics = trunk_alpha.record(model)
                if trunk_alpha_metrics is not None:
                    metrics.update(trunk_alpha_metrics)
                metrics["truncated_matches"] = int(batch.truncated_matches)
                matches_total = max(1, int(config.matches_per_iter))
                truncation_rate = batch.truncated_matches / matches_total
                metrics["truncation_rate"] = float(truncation_rate)
                if truncation_rate > 0.02:
                    # Truncated matches keep censored partial returns with done=1
                    # (the champion recipe's semantics; truncations were ~0 at
                    # max-steps 4000). A policy could exploit that by stalling
                    # into the cap — a rising rate is that exploit's signature,
                    # so the run halts loudly instead of optimizing it.
                    raise RuntimeError(
                        f"iter {iteration}: truncation rate {truncation_rate:.1%} exceeds 2% — "
                        "a stalling policy can exploit censored truncation returns; "
                        "investigate before continuing (raise max_steps_per_episode or "
                        "inspect the policy)"
                    )
                # Amendment 8 (data-scale-960): drop the completed rollout and
                # GAE arrays NOW — every batch-derived telemetry/truncation
                # value above has been computed, and nothing below reads them.
                # Without this, ~17GiB of iteration N's rollout stayed
                # referenced through the WHOLE of iteration N+1's collection
                # (loop locals rebind only after the next collect returns),
                # which breached the 36GiB cgroup guard at iteration 2 of the
                # 960-match lap while the restarted worker pool held another
                # ~18GiB. Plain rebinding only: gc.collect()/allocator tuning
                # are explicitly NOT authorized by the ruling. Lifetime pinned
                # by test_b2b_training's weakref test.
                del batch, advantages, returns
                # Adversarial round 15, high finding: verify AGAIN here, after
                # the (potentially long-running) rollout collection + PPO
                # update but strictly BEFORE this iteration's `iter_N.pt`/
                # history row is written -- a binary that drifted DURING this
                # iteration's own collection/update must still block that
                # iteration's artifacts from being published, not just the
                # NEXT iteration's.
                train_state._verify_bridge_unchanged(bridge_env_config, pinned_bridge_path, pinned_bridge_sha256,
                                         allow_bridge_mismatch, bridge_drift_warned)
                save_checkpoint(
                    checkpoint_dir / f"iter_{iteration:03d}.pt", model,
                    # Pins the trained horizon/architecture so fh-mj-evaluate can
                    # refuse to run this checkpoint under a different effective
                    # window (silent mis-evaluation guard). The "b2b" four-flag
                    # block stays for older readers; "model_config" is the
                    # complete ModelConfig so Spec B2c loaders (infer_model_config)
                    # can reconstruct the architecture exactly instead of
                    # re-deriving it from tensor shapes. "run_id" (adversarial
                    # round 4, high finding) lets a `--resume-from-state` whose
                    # history.json is missing/corrupt verify this checkpoint's
                    # lineage against the resuming state file instead of
                    # silently mixing unrelated runs' checkpoints together --
                    # infer_model_config ignores unknown metadata keys, so this
                    # is additive and doesn't affect loading.
                    metadata={
                        "b2b": {
                            "event_window": int(model_config.event_window),
                            "privileged_critic": bool(model_config.privileged_critic),
                            "aux_heads": bool(model_config.aux_heads),
                            "residual_blocks": int(model_config.residual_blocks),
                        },
                        "model_config": model_config_metadata(model_config),
                        "run_id": run_id,
                        # mortal-scale-scratch: which construction path this
                        # lineage came from, so a checkpoint's provenance is
                        # readable off the file rather than only from the
                        # launch command -- see `init_meta` above.
                        "init": init_meta,
                        # Amendment 4: the iteration-0 event-path snapshot, so
                        # "the slice started at exactly zero" is auditable off
                        # any checkpoint rather than only from the run's log.
                        # Omitted for a model with no event encoder.
                        **({"event_path_init": event_path_init}
                           if event_path_init is not None else {}),
                        "objective": {
                            "placement_bonus_values": (list(config.placement_bonus_values)
                                                       if config.placement_bonus_values is not None else None),
                            "placement_bonus_lambda": float(config.placement_bonus_lambda),
                            "placement_bonus_calibration_digest": str(config.placement_bonus_calibration_digest),
                        },
                    })
                # Adversarial round 19, high finding: this iteration's FRESH
                # `iter_N.pt` just replaced whatever was quarantined at
                # `_quarantine_stale_future_checkpoints` time -- drop that
                # obsolete-trajectory `.stale` sibling now rather than
                # leaving it to the end-of-run sweep below, so a concurrent
                # directory listing never sees both the fresh checkpoint and
                # its quarantined predecessor at once for longer than
                # necessary.
                stale_sibling = checkpoint_dir / f"iter_{iteration:03d}.pt{train_state._STALE_CHECKPOINT_SUFFIX}"
                if stale_sibling in pending_stale_checkpoints:
                    stale_sibling.unlink(missing_ok=True)
                    pending_stale_checkpoints.remove(stale_sibling)
                # Adversarial round 18, high finding: this iteration's
                # `iter_*.pt` checkpoint just landed durably on disk. When
                # train_state_every == 0 (train_state.pt is never written for
                # this whole run), THIS is the new run's first durable
                # artifact -- safe to drop the `--fresh-run-overwrite` backup
                # of the old run's artifacts now that the new run has its own
                # durable output.
                if overwrite_backup_dir is not None and not backup_cleared and durability_trigger == "checkpoint":
                    shutil.rmtree(overwrite_backup_dir, ignore_errors=True)
                    backup_cleared = True
                history.append(metrics)
                # Adversarial round 3, Finding 1: wrap history rows with the run's
                # run_id so a `--resume-from-state` can bind history.json's
                # lineage to the resuming train_state.pt (see _load_resume_history)
                # instead of silently mixing unrelated runs. Use
                # `read_b2b_history_rows` to read this file back.
                _write_history_atomic(checkpoint_dir / "history.json", {"run_id": run_id, "rows": history})
                print(f"iter {iteration}: policy_loss={metrics['policy_loss']:.4f} "
                      f"value_loss={metrics['value_loss']:.4f} entropy={metrics['entropy']:.4f} "
                      f"mean_reward={metrics['mean_reward']:.4f}")
                is_last_iteration = iteration == config.iterations
                if train_state_every > 0 and (iteration % train_state_every == 0 or is_last_iteration):
                    train_state._save_train_state(
                        checkpoint_dir / "train_state.pt", model, optimizer,
                        next_iteration=iteration + 1, config=config, model_config=model_config,
                        env_config=env_config, base_seed=base_seed, run_id=run_id,
                        pinned_bridge_sha256=pinned_bridge_sha256,
                        pinned_bridge_path=pinned_bridge_path,
                        init=init_meta,
                    )
                    # Adversarial round 18, high finding: `train_state.pt` just
                    # landed durably -- this is the new run's first durable
                    # artifact when periodic state saves are enabled at all
                    # (see `durability_trigger`). Drop the `--fresh-run-
                    # overwrite` backup of the old run's artifacts now.
                    if overwrite_backup_dir is not None and not backup_cleared and durability_trigger == "state":
                        shutil.rmtree(overwrite_backup_dir, ignore_errors=True)
                        backup_cleared = True
                # Amendment 4 integrity gate, LAST in the iteration: this
                # iteration's history row, `iter_N.pt` and `train_state.pt` are
                # all durable above, so the evidence survives the halt. Raising
                # here stops the run before the next collection rather than
                # letting a lap that is not measuring what the protocol thinks
                # it is keep spending GPU hours.
                event_path.raise_if_halted()
        finally:
            if collector is not None:
                collector.close()
            if pool is not None:
                # Every pool slot holds a live Go env; an exception mid-
                # collection must not leak them for the rest of the process.
                pool.close()
        # Adversarial round 19, high finding: sweep any `.stale` files still
        # left over at successful run completion -- e.g. this resume's
        # `--iterations` target stopped short of some iteration numbers that
        # were quarantined at resume-start (`config.iterations` lower than
        # the highest quarantined iteration), so the per-iteration deletion
        # above never reached them. They are obsolete-trajectory checkpoints
        # by definition (see `_quarantine_stale_future_checkpoints`) and this
        # run is ending without ever regenerating them, so there is nothing
        # left to wait for.
        for stale_path in pending_stale_checkpoints:
            stale_path.unlink(missing_ok=True)
        return history
    finally:
        lock_file.close()

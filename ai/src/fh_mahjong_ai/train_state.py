"""Crash-resume machinery for `train_b2b`: the atomic `train_state.pt` writer
and its previous-generation fallback, resume config-echo validation, history
reconciliation, run-id lineage checks, stale-checkpoint quarantine, the
checkpoint-directory lock, and bridge-library pinning.

Split out of `oracle.py`. `train_b2b.py` is the only caller."""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import random
import re
import uuid
from dataclasses import asdict, fields, MISSING
from pathlib import Path
from typing import Optional

import numpy as np
import torch

from .bridge import resolve_bridge_library_path
from .config import EnvConfig, ModelConfig
from .ppo import _fsync_dir, PPOConfig
from .storage import model_config_metadata

logger = logging.getLogger(__name__)


_RESUME_MISSING = object()


def _resolve_current_bridge_fingerprint(env_config: EnvConfig) -> tuple[Optional[str], Optional[str]]:
    """(resolved_path, sha256) of the Go bridge library `env_config`'s CURRENT
    resolution points at, mirroring `fh-mj-compare`'s provenance digest
    (`evaluate._bridge_library_digest`) so a `--resume-from-state` run can
    pin the identical simulator binary a fresh launch would load, not just
    the `bridge_kind`/`bridge_library_path` *configuration* that
    `config_echo` already records (adversarial round 13, high finding:
    rebuilding the .so at the same path leaves `config_echo` byte-identical
    while the actual simulator changes under it).

    `bridge_kind != "go"` (e.g. the mock bridge used throughout tests) has
    no library to pin -- both are `None`, and `None == None` at the resume
    check below is a pass, matching `evaluate.py`'s existing convention.

    A `bridge_kind == "go"` run, by contrast, MUST have a real, readable
    simulator binary to pin. Adversarial round 16, high finding: this used
    to swallow `OSError` here too and return `(None, None)` -- indistinguish-
    able from a genuine mock config -- which let a fresh Go-backed run whose
    library was missing/unreadable pin `(None, None)` silently, and
    `_verify_bridge_unchanged`'s `pinned_bridge_sha256 is None` guard then
    no-ops for the WHOLE run, permanently disabling drift protection instead
    of refusing to start. So for `bridge_kind == "go"`, an `OSError` while
    resolving/reading the library now propagates (re-raised naming the
    resolved path and the underlying errno) instead of degrading to the
    mock sentinel. There is deliberately no retry here: a single failed
    read aborts the run even if a later read of the identical path would
    happen to succeed -- a transient/flaky read failure is not
    distinguishable, from this call alone, from a library that could vanish
    again mid-run, and "try again and hope" is exactly the silent-recovery
    behavior this fix removes."""
    if env_config.bridge_kind != "go":
        return None, None
    path = resolve_bridge_library_path(env_config.bridge_library_path)
    try:
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError as exc:
        raise OSError(
            f"cannot pin Go bridge library identity: failed to read {str(path)!r} "
            f"({exc.__class__.__name__} errno={exc.errno}: {exc.strerror or exc}) "
            "-- a bridge_kind='go' run must never start (or continue) with an "
            "unverifiable simulator identity. Fix the missing/unreadable "
            "library path and retry."
        ) from exc
    return str(path), digest


def _verify_bridge_unchanged(env_config: EnvConfig, pinned_bridge_path: Optional[str],
                              pinned_bridge_sha256: Optional[str], allow_bridge_mismatch: bool,
                              warned_state: dict) -> None:
    """Adversarial round 15, high finding: round 14's drift check lived ONLY
    inside `_save_train_state`, so it fired only on iterations that happened
    to coincide with a periodic state save (every `train_state_every`
    iterations, plus completion). Every OTHER iteration collected its
    rollouts, ran PPO, and published `iter_N.pt` + a `history.json` row
    under a simulator binary that had already drifted out from under the
    pinned identity -- `train_state_every > 1` let several such iterations
    through before the next save's check finally fired, and
    `train_state_every=0` (never state-saves) never checked at all.

    The fix: this check is now a standalone gate, called by `train_b2b`
    TWICE per iteration -- once before rollout collection starts, and once
    after the PPO update but before that iteration's `iter_N.pt`/history row
    is written -- so a drifted binary is caught before it can produce ANY
    artifact, regardless of `train_state_every`. `_save_train_state` no
    longer performs this check itself; it only ever writes the PINNED
    digest (see its docstring) once the caller has already verified it here.

    Cost: hashing a ~30MB Go bridge .so is a few milliseconds; doing it
    twice per iteration (versus once) is negligible next to a ~15-minute
    self-play iteration.

    `pinned_bridge_sha256 is None` (mock bridge) skips the check entirely,
    mirroring `_resolve_current_bridge_fingerprint`'s own convention.
    `allow_bridge_mismatch=True` downgrades a mismatch to a warning instead
    of raising -- logged ONCE for the whole run (via the shared mutable
    `warned_state` dict), not once per check, so a persistently drifted
    binary does not spam the log every iteration."""
    if pinned_bridge_sha256 is None:
        return
    current_bridge_path, current_bridge_sha256 = _resolve_current_bridge_fingerprint(env_config)
    if current_bridge_sha256 == pinned_bridge_sha256:
        return
    message = (
        "bridge library drift detected mid-run: this run pinned "
        f"bridge_sha256={pinned_bridge_sha256!r} ({pinned_bridge_path!r}) at "
        f"start, but the CURRENT bridge resolution ({current_bridge_path!r}) "
        f"now hashes to bridge_sha256={current_bridge_sha256!r} -- the Go "
        "simulator binary changed underneath this run (e.g. rebuilt at the "
        "same path mid-run). Continuing would publish a checkpoint/history "
        "row produced under a different simulator than the one this "
        "lineage is pinned to."
    )
    if not allow_bridge_mismatch:
        raise ValueError(
            message + " Aborting WITHOUT collecting/publishing anything for "
            "this iteration. If you have deliberately confirmed the new "
            "binary is an acceptable, attribution-breaking substitution, "
            "pass --allow-bridge-mismatch to downgrade this to a warning."
        )
    if not warned_state.get("warned"):
        logger.warning(
            message + " --allow-bridge-mismatch: continuing anyway (this "
            "warning is logged once for the run, not per iteration) -- "
            "attribution past this point is no longer guaranteed."
        )
        warned_state["warned"] = True


_BRIDGE_SNAPSHOT_GLOB = ".bridge-*.so"


def _bridge_snapshot_path(checkpoint_dir: Path, sha256: str) -> Path:
    """The content-addressed path a bridge library digest snapshots to:
    `<checkpoint_dir>/.bridge-<sha256-prefix16>.so`. Deterministic in both
    directions -- same content always names the same file, so concurrent
    creators (parallel workers, a fresh run vs a resume of the same
    lineage) converge on one path -- and the leading dot plus non-`iter_*.pt`
    name keeps it outside `_check_artifact_lineage_or_raise`'s `iter_*.pt`
    lineage scan by construction (see that function's docstring)."""
    return checkpoint_dir / f".bridge-{sha256[:16]}.so"


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write `data` to `path` via a tmp sibling + `fsync` + `os.replace`
    (mirrors `_atomic_torch_save`'s durability pattern), so a crash mid-copy
    never leaves a torn snapshot for a worker to `dlopen`."""
    tmp_path = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    with open(tmp_path, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)
    _fsync_dir(path.parent)


def _read_and_hash_bridge_source(source_path: str) -> tuple[bytes, str]:
    """Read `source_path` ONCE and return `(bytes, sha256-of-those-bytes)`.
    Every bridge-snapshot call site (fresh pin, resume recreation) routes
    through this single function so the digest that gets pinned/compared is
    always computed from the SAME bytes a snapshot write copies -- never
    from a second, independent read -- which is what closes the ABA window
    described in `_write_bridge_snapshot_if_needed`'s docstring."""
    resolved = Path(source_path)
    try:
        data = resolved.read_bytes()
    except OSError as exc:
        raise OSError(
            f"cannot pin Go bridge library identity: failed to read {str(resolved)!r} "
            f"({exc.__class__.__name__} errno={exc.errno}: {exc.strerror or exc}) "
            "-- a bridge_kind='go' run must never start (or continue) with an "
            "unverifiable simulator identity. Fix the missing/unreadable "
            "library path and retry."
        ) from exc
    return data, hashlib.sha256(data).hexdigest()


def _write_bridge_snapshot_if_needed(checkpoint_dir: Path, sha256: str, data: bytes) -> str:
    """Adversarial round 20, high finding: rounds 13-19 pinned/verified a
    sha256 of the bridge library's PATH, re-reading that path both at pin
    time and at every drift check -- but every rollout worker (parallel
    `spawn` workers, and the single-env path) independently `dlopen`s that
    same MUTABLE path later, on its own schedule. A swap-and-restore of the
    file between "hash" and a worker's later "load" defeats every check
    that came before (ABA); parallel workers racing a rebuild can even end
    up loading DIFFERENT binaries from each other. Hashing the path is not
    the same as binding to the bytes that get loaded.

    The fix: copy the verified library bytes ONCE into a run-owned,
    content-addressed snapshot (`_bridge_snapshot_path`) and thread THAT
    path into every `EnvConfig` handed to collection (see `train_b2b`'s
    `bridge_env_config`) -- so every worker loads the immutable snapshot,
    never the mutable source.

    Idempotent by construction: if a snapshot already exists at the
    content-addressed path for this content's digest with a matching size,
    the copy is skipped entirely -- the common case, since every worker of
    the same run (and a resume of the same lineage) computes the identical
    path for identical content. Returns the snapshot's path as a string."""
    snapshot_path = _bridge_snapshot_path(checkpoint_dir, sha256)
    already_present = False
    try:
        already_present = snapshot_path.stat().st_size == len(data)
    except OSError:
        already_present = False
    if not already_present:
        _write_bytes_atomic(snapshot_path, data)
    return str(snapshot_path)


def _create_bridge_snapshot(checkpoint_dir: Path, source_path: str) -> tuple[str, str]:
    """Read `source_path` once and (idempotently) copy it into this
    checkpoint dir's content-addressed bridge snapshot. Returns
    `(snapshot_path, sha256)`. See `_write_bridge_snapshot_if_needed` for
    the ABA rationale; kept as a single call for call sites (resume
    recreation) that don't need to split the read from the write."""
    data, sha256 = _read_and_hash_bridge_source(source_path)
    snapshot_path = _write_bridge_snapshot_if_needed(checkpoint_dir, sha256, data)
    return snapshot_path, sha256


def _resolve_bridge_snapshot_for_resume(env_config: EnvConfig, checkpoint_dir: Path,
                                        pinned_bridge_sha256: str,
                                        allow_bridge_mismatch: bool) -> tuple[str, str]:
    """Ensure this lineage's content-addressed bridge snapshot exists for a
    `--resume-from-state` run, returning `(snapshot_path, effective_sha256)`
    to thread into the resumed run's bridge `EnvConfig`.

    Snapshot-first (adversarial round 21, high finding): the common case is
    that the snapshot the ORIGINAL run created for `pinned_bridge_sha256` is
    still sitting in `checkpoint_dir` (it is a managed artifact -- see
    `_find_fresh_run_managed_artifacts` -- so nothing legitimate removes it).
    When present, its OWN bytes are re-hashed and compared against
    `pinned_bridge_sha256` -- a mismatch means the snapshot itself was
    tampered with or corrupted on disk and raises unconditionally (there is
    no override for this; the pinned bytes are gone either way). On a match,
    the snapshot is reused as-is and the caller's mutable SOURCE path is
    NEVER read, hashed, or even resolved -- a deleted or rebuilt source
    cannot brick this resume (that used to happen because the caller
    fingerprinted the source before ever reaching this function; see this
    resume path's docstring for the round-21 fix on that side).

    Only when the snapshot is MISSING does this function fall back to the
    source: if the source's CURRENT content still hashes to
    `pinned_bridge_sha256`, the snapshot is recreated from it (the source was
    never a problem, only the snapshot was lost -- e.g. `checkpoint_dir` was
    partially cleaned). If the source has since changed (rebuilt at the same
    path), recreating the snapshot under the OLD digest name is impossible --
    those exact bytes are gone -- so this raises unless the caller passed
    `--allow-bridge-mismatch`, in which case the CURRENT source is accepted
    as this lineage's new baseline: it is snapshotted under its own (new)
    digest, and that new digest is returned as the effective pin going
    forward (mirroring `--allow-bridge-mismatch`'s existing
    attribution-breaking semantics elsewhere in this module)."""
    snapshot_path = _bridge_snapshot_path(checkpoint_dir, pinned_bridge_sha256)
    if snapshot_path.exists():
        snapshot_bytes = snapshot_path.read_bytes()
        snapshot_actual_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
        if snapshot_actual_sha256 != pinned_bridge_sha256:
            raise ValueError(
                f"bridge snapshot {str(snapshot_path)!r} is corrupted: its "
                f"content-addressed name pins bridge_sha256={pinned_bridge_sha256!r} "
                f"but its CURRENT bytes hash to {snapshot_actual_sha256!r} -- the "
                "snapshot was tampered with or corrupted on disk after being "
                "written. This is never safe to resume from and has no "
                "override (the originally pinned bytes cannot be recovered "
                "from a corrupted snapshot); restore it from backup or start "
                "a fresh run."
            )
        return str(snapshot_path), pinned_bridge_sha256
    source_path = resolve_bridge_library_path(env_config.bridge_library_path)
    try:
        data, current_sha256 = _read_and_hash_bridge_source(str(source_path))
    except OSError as exc:
        raise OSError(
            f"cannot recreate missing bridge snapshot {str(snapshot_path)!r}: {exc}"
        ) from exc
    if current_sha256 == pinned_bridge_sha256:
        _write_bridge_snapshot_if_needed(checkpoint_dir, pinned_bridge_sha256, data)
        return str(snapshot_path), pinned_bridge_sha256
    if not allow_bridge_mismatch:
        raise ValueError(
            f"bridge library mismatch: snapshot {str(snapshot_path)!r} for pinned "
            f"bridge_sha256={pinned_bridge_sha256!r} is missing, and the source "
            f"library at {str(source_path)!r} no longer matches it (current "
            f"digest {current_sha256!r}) -- the source was rebuilt after the "
            "snapshot was lost, so the originally pinned bytes can no longer be "
            "recovered. Pass --allow-bridge-mismatch to accept the current "
            "source as this lineage's new baseline (it will be snapshotted and "
            "pinned going forward)"
        )
    logger.warning(
        "--allow-bridge-mismatch: bridge snapshot for bridge_sha256=%r was missing "
        "and the source has since changed (current digest %r at %r) -- accepting "
        "the CURRENT source as this lineage's new baseline",
        pinned_bridge_sha256, current_sha256, source_path,
    )
    new_snapshot_path = _write_bridge_snapshot_if_needed(checkpoint_dir, current_sha256, data)
    return new_snapshot_path, current_sha256


def _assert_bridge_pinned(env_config: EnvConfig, pinned_bridge_sha256: Optional[str]) -> None:
    """Adversarial round 16, high finding, belt-and-braces: a
    `bridge_kind="go"` run must never proceed with a null pinned digest --
    that is precisely the condition that let `_verify_bridge_unchanged`'s
    `pinned_bridge_sha256 is None` guard silently no-op for the whole run.
    Neither `_read_and_hash_bridge_source` nor `_resolve_bridge_snapshot_for_
    resume` can return `None` for a `bridge_kind == "go"` config (both raise
    instead), so this should be unreachable in practice; it exists as a hard
    stop against a future regression re-introducing that silent path.
    Called both immediately after each pinning path establishes
    `pinned_bridge_sha256` (before any snapshot/artifact mutation) and once
    more before the training loop starts, so a hypothetical bug anywhere in
    between is still caught."""
    if env_config.bridge_kind == "go" and pinned_bridge_sha256 is None:
        raise RuntimeError(
            "internal invariant violated: bridge_kind='go' but this run's "
            "pinned bridge digest is None -- refusing to start/continue "
            "training with an unpinned (unverifiable) simulator identity"
        )


def _train_b2b_config_echo(config: PPOConfig, model_config: ModelConfig, env_config: EnvConfig) -> dict:
    """Snapshot of the three config dataclasses that fully determine a
    `train_b2b` recipe, in plain-dict form so it round-trips through
    `torch.save`/`torch.load` and compares by value. Stored in
    `train_state.pt["config_echo"]` and re-derived from the CALLER-supplied
    configs on `--resume-from-state` for the mismatch check below."""
    return {
        "ppo_config": asdict(config),
        "model_config": model_config_metadata(model_config),
        "env_config": asdict(env_config),
    }


_RESUME_IGNORED_FIELDS = {
    # "iterations" is deliberately exempt: --resume-from-state's whole point is
    # to keep training PAST what the state file was saved under (e.g. resume a
    # 2-iteration state with --iterations 260), so a higher target here is the
    # expected, common case rather than a recipe drift.
    ("ppo_config", "iterations"),
}

# "num_workers" changes are logged rather than rejected: it only controls how
# collection work is sharded across worker processes, not the recipe itself.
# Per-match seeding makes trajectories worker-count-invariant -- proven by
# fh-mj-collect-bench's digest equality across 5/10/20 workers, which is that
# tool's entire purpose. So resuming a run at a different worker count (e.g.
# dropping from 20 to 10 to fit a smaller box after an OOM) is a legitimate
# operational adjustment, not a silent recipe drift, and must not block
# --resume-from-state the way every other field does.
_RESUME_LOGGED_FIELDS = {
    ("ppo_config", "num_workers"),
    # Same category as num_workers: collect_dispatch_chunk only bounds how
    # many matches are in flight per dispatch round, and chunk-parity digest
    # tests prove trajectories are chunk-invariant. Lowering it on resume
    # after an OOM is a legitimate operational adjustment, not recipe drift.
    ("ppo_config", "collect_dispatch_chunk"),
    # Amendment 5: minibatch_device_transfer changes only WHERE rollout
    # tensors live between optimizer steps (host vs update device), not any
    # value, permutation, or update — bit-parity pinned by test_ppo's
    # path-equivalence tests and the on-box gauntlet. Toggling it on resume
    # (e.g. to fit a card) is operational, not recipe drift.
    ("ppo_config", "minibatch_device_transfer"),
}

# Adversarial round 1 (high): a new field with a dataclass default (e.g.
# ModelConfig.event_output_dim, added for Spec B2c serving) appears in every
# freshly-built config echo, but a `train_state.pt` saved before that field
# existed has no such key -- `_validate_resume_config_echo`'s missing-vs-
# present comparison then reads that as an explicit drift (missing sentinel
# != 0) and refuses to resume a perfectly compatible multi-day run. Maps each
# section name to the dataclass whose `dataclasses.fields(...)` defaults
# back-fill a legacy echo's missing keys below.
#
# Adversarial round 5 (medium): round 1's fix originally back-filled ANY
# field missing from a saved echo -- for every dataclass, every field -- not
# just the two additions it was actually built to cover. That's fail-open:
# a malformed/edited state file missing an ESTABLISHED field (e.g.
# ppo_config.gamma, env_config.match_mode) would silently resume under
# today's default for that field instead of raising. Fixed by narrowing the
# back-fill to an explicit whitelist of PROVEN legacy additions -- fields
# that shipped with a default AFTER released `train_state.pt` files already
# existed without them. Nothing is whitelisted for env_config: every field
# there has been present since the section's first released echo, so a
# missing key there is never legitimate legacy silence.
#
# Extend this whitelist when (and only when) a new field ships after
# released states exist -- add "section": {"field_name"} for it, name it in
# a comment like the two below, and it starts getting the same treatment.
# A schema-version field on the echo was considered as a more scalable
# alternative and deferred: an explicit whitelist is equivalent to it while
# the list stays this short, and simpler to reason about.
_RESUME_SECTION_DATACLASSES = {
    "ppo_config": PPOConfig,
    "model_config": ModelConfig,
    "env_config": EnvConfig,
}

_LEGACY_ECHO_ADDITIONS = {
    "model_config": {
        "growth_blocks",       # absent from every train_state.pt saved before deep16-rezero
        "event_output_dim",    # absent from every train_state.pt saved before gru-width
        "trunk_rezero",        # absent before mortal-scale-scratch Amendment 3 (2026-08-27)
    },
    "ppo_config": {
        "collect_dispatch_chunk",  # absent from every train_state.pt saved before data-scale-960 Amendment 2
        "minibatch_device_transfer",  # absent from every train_state.pt saved before data-scale-960 Amendment 5
        "placement_bonus_values",             # absent before placement-reshape Stage 0 (2026-08-22)
        "placement_bonus_lambda",             # idem
        "placement_bonus_calibration_digest", # idem
        "head_lr",                            # absent before mortal-scale-scratch Amendment 1 §6 (2026-08-25)
        "head_lr_iters",                      # idem
    },
}


def _dataclass_field_defaults(cls: type) -> dict:
    """Map of field name -> default value for every field of `cls` that
    declares a plain or factory default. Fields with no default at all
    (there are currently none in `PPOConfig`/`ModelConfig`/`EnvConfig`) are
    simply omitted -- a legacy echo missing such a field would still fail
    the drift check below, which is correct: there's no safe default to
    assume for it."""
    defaults = {}
    for f in fields(cls):
        if f.default is not MISSING:
            defaults[f.name] = f.default
        elif f.default_factory is not MISSING:  # pragma: no cover - none exist today
            defaults[f.name] = f.default_factory()
    return defaults


def _fill_legacy_echo_defaults(section: str, current_section: dict, saved_section: dict) -> dict:
    """Return a copy of `saved_section` with any key that's WHITELISTED in
    `_LEGACY_ECHO_ADDITIONS` for this section, present in `current_section`,
    but ABSENT from `saved_section`, filled in with that field's dataclass
    default -- i.e. treat a pre-upgrade echo's silence about a *proven*
    legacy addition as "this run used the default", not as a mismatch.

    A key that IS present in `saved_section` (even if equal to the default)
    is left untouched and still compares strictly against the current value.
    A key missing from `saved_section` that is NOT in the whitelist is left
    missing here -- `_validate_resume_config_echo` then raises naming it,
    since there's no proof a legacy echo could ever have lacked it."""
    defaults = _dataclass_field_defaults(_RESUME_SECTION_DATACLASSES[section])
    whitelisted = _LEGACY_ECHO_ADDITIONS.get(section, frozenset())
    filled = {}
    normalized = dict(saved_section)
    for key in current_section:
        if key not in normalized and key in defaults and key in whitelisted:
            normalized[key] = defaults[key]
            filled[key] = defaults[key]
    if filled:
        logger.info(
            "--resume-from-state: %s echo predates field(s) %s -- filling each "
            "with its current dataclass default for the resume comparison "
            "(state file was saved before these fields existed)",
            section, sorted(filled),
        )
    return normalized


def _validate_resume_config_echo(current: dict, saved: dict) -> None:
    """Raise with a clear, specific message on the FIRST field that differs
    between the currently-supplied configs and the ones a `train_state.pt`
    was saved under. Resuming under a different recipe (a changed lr, event
    window, ...) silently corrupts the run (e.g. an optimizer whose momentum
    was tuned for a different lr), so any drift is an error, not a warning —
    except `ppo_config.iterations` (see `_RESUME_IGNORED_FIELDS`) and
    `ppo_config.num_workers` (see `_RESUME_LOGGED_FIELDS`), which is logged
    instead of raised."""
    for section in ("ppo_config", "model_config", "env_config"):
        current_section = current[section]
        saved_section = _fill_legacy_echo_defaults(section, current_section, saved[section])
        keys = sorted(set(current_section) | set(saved_section))
        for key in keys:
            if (section, key) in _RESUME_IGNORED_FIELDS:
                continue
            current_value = current_section.get(key, _RESUME_MISSING)
            saved_value = saved_section.get(key, _RESUME_MISSING)
            if current_value != saved_value:
                if (section, key) in _RESUME_LOGGED_FIELDS:
                    logger.info(
                        "--resume-from-state: %s.%s changed (state file has %r, "
                        "currently-supplied config has %r) -- proceeding: "
                        "worker count is semantics-neutral for collection "
                        "(per-match seeding makes trajectories worker-count-"
                        "invariant, proven by fh-mj-collect-bench's digest "
                        "equality across 5/10/20 workers)",
                        section, key, saved_value, current_value,
                    )
                    continue
                raise ValueError(
                    f"--resume-from-state config mismatch in {section}.{key}: "
                    f"state file has {saved_value!r}, currently-supplied config has "
                    f"{current_value!r} — resuming under a different recipe is not "
                    "supported (pass the same configs the original run used)"
                )


def _validate_resume_iterations_not_truncating(current_iterations: int, saved_iterations: int,
                                               start_iteration: int) -> None:
    """Raise if resuming would silently truncate the run's original target.

    `iterations` is exempt from `_validate_resume_config_echo`'s strict
    equality check (see `_RESUME_IGNORED_FIELDS`) because extending
    training past the original target is the whole point of
    `--resume-from-state`. But that exemption cuts both ways: nothing else
    validated a LOWER target either, so a state saved from a long run
    (e.g. `--iterations 260`) resumed with a mistyped smaller value that
    still exceeds the saved `next_iteration` (e.g. `--iterations 26`) used
    to run to completion and silently rewrite `train_state.pt` as a
    "finished" 26-iteration run, discarding the original 260-iteration
    target with no error at all (adversarial round 12, high finding).

    Only fires when the requested target would actually let training
    proceed (`start_iteration <= current_iterations`) but stop strictly
    short of the saved target -- a target at or below `start_iteration`
    can't train anything regardless of the original target, and is caught
    with a more specific message by the "already satisfied" exhausted-
    target check that runs after this one."""
    if start_iteration <= current_iterations < saved_iterations:
        raise ValueError(
            "--resume-from-state would truncate the run: state was saved "
            f"from a --iterations {saved_iterations} run (currently at "
            f"iteration {start_iteration - 1}), but --iterations "
            f"{current_iterations} was requested -- resuming with a lower "
            f"target than the run was saved under is not supported (pass "
            f"{saved_iterations} (or higher), or start a new run)"
        )


def _train_state_prev_path(path: Path) -> Path:
    """The one-generation-back sibling of a `train_state.pt`-style path,
    e.g. `train_state.pt` -> `train_state.prev.pt`."""
    path = Path(path)
    return path.with_name(path.stem + ".prev" + path.suffix)


def _train_state_is_loadable(path: Path) -> bool:
    """Whether `path` currently `torch.load`s cleanly. Used only to decide if
    an existing `train_state.pt` is worth preserving as `.prev` before being
    replaced -- a file that's already torn/corrupt from some earlier crash
    is not worth keeping around under a name that shadows a genuinely good
    `.prev` generation from further back."""
    try:
        torch.load(path, map_location="cpu", weights_only=False)
        return True
    except Exception:
        return False


def _atomic_torch_save(payload: dict, path: Path) -> None:
    """`torch.save` via a tmp-file + `os.replace`, so a crash mid-write never
    leaves a half-written `train_state.pt` for the next resume to load.

    Durability (adversarial round 9, high finding): the tmp file is flushed
    and `fsync`ed before the replace, and the parent directory is `fsync`ed
    afterward (platform-guarded -- see `_fsync_dir`) so the rename itself
    survives a power loss, not just the file's bytes.

    Generation retention (same finding): a host reset landing exactly
    between one `_atomic_torch_save` completing and the NEXT one finishing
    used to leave nothing to fall back to, because the previous (still-good)
    generation had already been clobbered in place. Now, if `path` already
    holds a file that loads cleanly, it is renamed to `_train_state_prev_path
    (path)` (`train_state.prev.pt`) BEFORE the new tmp file is put in its
    place -- so the old generation is only ever destroyed once the new one
    is fully written, fsynced, and a single atomic rename away from
    replacing it. `train_state.pt` and `train_state.prev.pt` are both
    managed artifacts of the fresh-dir guard / `--fresh-run-overwrite`
    deletion (see `_find_fresh_run_managed_artifacts`) but are never
    lineage-scanned as `iter_*.pt` files. A resume should use
    `_load_train_state_with_fallback`, which tries `path` first and falls
    back to `.prev` when the newest generation is unreadable."""
    path = Path(path)
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "wb") as f:
        torch.save(payload, f)
        f.flush()
        os.fsync(f.fileno())
    if path.exists() and _train_state_is_loadable(path):
        os.replace(path, _train_state_prev_path(path))
    os.replace(tmp_path, path)
    _fsync_dir(path.parent)


def _load_train_state_with_fallback(path: Path) -> dict:
    """Load a `--resume-from-state` payload from `path`, falling back to its
    `.prev` sibling generation (`_train_state_prev_path`) when `path` itself
    is unreadable (adversarial round 9, high finding) -- e.g. a host reset
    landed between `_atomic_torch_save` promoting the previous generation to
    `.prev` and completing the final rename, or corrupted the newest file
    outright. Logs which generation was actually loaded. Raises (chaining
    both underlying errors) only when BOTH generations are unreadable, or
    `path` is missing/unreadable with no `.prev` fallback on disk at all."""
    path = Path(path)
    prev_path = _train_state_prev_path(path)
    try:
        payload = torch.load(path, map_location="cpu", weights_only=False)
    except Exception as exc:
        if not prev_path.exists():
            raise
        logger.warning(
            "--resume-from-state: %s is unreadable (%s: %s); falling back to "
            "the previous generation %s",
            path, type(exc).__name__, exc, prev_path,
        )
        try:
            payload = torch.load(prev_path, map_location="cpu", weights_only=False)
        except Exception as prev_exc:
            raise RuntimeError(
                f"--resume-from-state: both {path} and its fallback generation "
                f"{prev_path} are unreadable ({type(exc).__name__}: {exc}; "
                f"fallback {type(prev_exc).__name__}: {prev_exc}) -- cannot "
                "resume from either generation"
            ) from prev_exc
        logger.warning("--resume-from-state: resumed from fallback generation %s", prev_path)
        return payload
    logger.info("--resume-from-state: loaded %s", path)
    return payload


def read_b2b_history_rows(path: Path) -> list[dict]:
    """Public accessor for `train_b2b`'s `history.json` rows, tolerant of both
    the current `{"run_id": ..., "rows": [...]}` wrapper (adversarial round 3,
    Finding 1: `run_id` binds a `history.json` to the `train_state.pt` it
    belongs to, so a resume can't silently splice unrelated run histories
    together) and the legacy bare-list format written before `run_id` existed.
    In-repo/box-side consumers of `history.json` (screening scripts,
    telemetry checks) should use this instead of `json.loads(...)` directly
    so they keep working across the format change."""
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        return data
    return data["rows"]


def _artifact_run_id(path: Path) -> Optional[str]:
    """`metadata["run_id"]` of an `iter_*.pt` checkpoint, or `None` if the
    checkpoint has no metadata / no `run_id` key (pre-round-4 checkpoint)."""
    payload = torch.load(path, map_location="cpu")
    metadata = payload.get("metadata") or {}
    return metadata.get("run_id")


_ITER_CHECKPOINT_NAME_RE = re.compile(r"^iter_(\d+)\.pt$")

_STALE_CHECKPOINT_SUFFIX = ".stale"


def _quarantine_stale_future_checkpoints(checkpoint_dir: Path, start_iteration: int) -> list[Path]:
    """Rename every `iter_N.pt` in `checkpoint_dir` with `N >= start_iteration`
    to `iter_N.pt.stale`, atomically (`os.replace` -- same filesystem, so this
    is a rename, never a copy+delete window). Returns the list of quarantined
    `.stale` paths.

    Adversarial round 19, high finding: `--resume-from-state` truncates
    `history.json`/its in-memory history back to `start_iteration` (see the
    caller, just below this function's call site), but pre-round-19 left any
    `iter_N.pt` for `N >= start_iteration` sitting on disk, live, until the
    replayed loop happened to reach and overwrite it by name. CUDA replay is
    not bit-identical (nondeterministic reductions, cuDNN algorithm
    selection), so a resumed iteration N can legitimately diverge from
    whatever produced the OLD `iter_N.pt` -- that old file still carries the
    resuming state's `run_id` (it is not a lineage mismatch by
    `_check_artifact_lineage_or_raise`'s test) but no longer descends from the
    trajectory this resume actually replays. Anything that reads `iter_N.pt`
    by name during the window between resume-start and that iteration's
    replay finishing -- concurrent screening/eval tooling, or a second crash
    mid-replay before the fresh file lands -- could silently select an
    obsolete-trajectory checkpoint with a same-`run_id` label that looks
    perfectly legitimate.

    The `.stale` suffix, not a `iter_*.pt` name, is deliberate: it drops the
    file out of every glob that matters without any glob needing to change
    for it --  `_check_artifact_lineage_or_raise`'s `iter_*.pt` scan,
    screening/eval tooling's own `iter_*.pt` globs, and (for the CLI's
    resume-then-later-fresh-launch path) `_find_fresh_run_managed_artifacts`'s
    `iter_*.pt` glob all already require a `.pt`-terminated name, which
    `iter_NNN.pt.stale` is not. `_find_fresh_run_managed_artifacts` also globs
    `iter_*.pt.stale` explicitly (see its docstring) so a leftover quarantine
    file from an interrupted resume is still covered by the fresh-dir guard
    and `--fresh-run-overwrite`.

    Called by `train_b2b`'s resume branch once, after every resume validation
    (base_seed, config_echo, iterations-not-truncating, artifact-lineage,
    bridge-digest) has already passed, and before `history.json` is persisted
    or the training loop starts -- so a crash between quarantine and the
    first replayed iteration leaves on-disk state self-consistent: a
    truncated `history.json`, no live checkpoint past `start_iteration - 1`,
    and every future iteration's prior attempt safely parked under `.stale`.
    The caller deletes each `.stale` file the moment its replacement
    `iter_N.pt` is durably written (see `train_b2b`'s loop body), and sweeps
    any still-quarantined leftovers at successful run completion (e.g. a
    resume whose `--iterations` target is lower than the number of files
    quarantined here, so some are never replaced this run)."""
    quarantined: list[Path] = []
    for artifact_path in sorted(checkpoint_dir.glob("iter_*.pt")):
        match = _ITER_CHECKPOINT_NAME_RE.match(artifact_path.name)
        if match is None or int(match.group(1)) < start_iteration:
            continue
        stale_path = artifact_path.with_name(artifact_path.name + _STALE_CHECKPOINT_SUFFIX)
        os.replace(artifact_path, stale_path)
        quarantined.append(stale_path)
    return quarantined


def _train_state_run_id(path: Path) -> Optional[str]:
    """`run_id` of a `train_state.pt`-style payload at `path` (`None` if the
    payload predates `run_id`). Raises if `path` is unreadable -- unlike an
    `iter_*.pt` checkpoint (see `_check_artifact_lineage_or_raise`'s torn-
    file tolerance), a destination train_state generation has no "at/past
    the resume point, training will regenerate it" escape hatch: it IS
    recovery evidence for the resume point, so an unreadable one can't be
    waved through."""
    payload = torch.load(path, map_location="cpu", weights_only=False)
    return payload.get("run_id")


def _check_artifact_lineage_or_raise(checkpoint_dir: Path, state_run_id: Optional[str],
                                     next_iteration: int,
                                     resume_from_state: Optional[Path] = None) -> None:
    """Guard EVERY `--resume-from-state` against silently mixing run
    lineages, whether or not `history.json` itself needed recovery
    (adversarial round 5, high finding: round 4 only ran this scan on the
    missing/corrupt-history path, so a resume with a perfectly valid,
    matching state/history pair never inspected checkpoint_dir's existing
    iter_*.pt artifacts at all -- a foreign checkpoint left behind by an
    unrelated run went undetected, since training only overwrites
    iterations >= start_iteration and leaves earlier foreign files in place
    for screening/retention tooling to pick up later).

    Scans `checkpoint_dir` for existing `iter_*.pt` artifacts -- ALL of
    them, including ones at iterations >= start_iteration that this resume
    is about to overwrite anyway: a foreign file sitting there is still
    evidence of a wrong directory even if training would clobber it a
    moment later. For each artifact, its saved `metadata["run_id"]` must
    equal `state_run_id` -- including the legacy case where both are `None`
    (pre-run_id artifact resuming from a pre-run_id state; nothing to
    compare, so it passes, preserving pre-round-4 behavior). Any artifact
    whose run_id differs (or is `None` while `state_run_id` is set --
    lineage can't be proven) raises. An empty or brand-new checkpoint_dir
    (no iter_*.pt at all) has nothing on disk to contradict the resume, so
    it passes through untouched -- relocating a state file into a fresh
    directory is fine.

    Note on cost: this does a full `torch.load` per `iter_*.pt` (metadata is
    stored inside the same pickled dict as the tensors, so there is no
    cheaper metadata-only read) with `map_location="cpu"` to avoid a GPU
    round-trip. For a large checkpoint_dir this is a one-off cost paid only
    at resume time (a rare event), not per training iteration.

    Torn-file tolerance (adversarial round 8, high finding): `iter_*.pt` is
    written non-atomically-no-more (storage.py's `save_checkpoint` now goes
    through a tmp-sibling + `os.replace`), but old runs and any crash that
    happened to land exactly between that `torch.save` and `os.replace`
    (or before this fix shipped) can still leave a torn/truncated file on
    disk. Without tolerance, `torch.load` raising on that file here would
    make `--resume-from-state` -- the feature that exists to survive a
    crash -- fail in precisely the crash window it is meant to cover. An
    unreadable artifact is handled by comparing its iteration number
    (parsed from the `iter_NNN.pt` filename) against `next_iteration`: at
    or past the resume point, training is about to regenerate that file
    anyway, so it is quarantined (renamed `<name>.corrupt`, with a logged
    warning) and the scan continues; before the resume point, the file is
    irreplaceable historical evidence that training will never rewrite, so
    the scan raises, naming the file (recoverable via
    `--force-history-reset`, which bypasses this entire scan -- see below).
    A filename that doesn't match `iter_<digits>.pt` can't be matched
    against `next_iteration` at all, so it raises rather than guessing.

    `--force-history-reset` (the `force_history_reset` flag on `train_b2b`)
    skips ONLY this check -- it is the general lineage-validation override,
    covering both the missing/corrupt-history recovery path and this
    unconditional every-resume scan -- never the base_seed/config_echo
    checks in `train_b2b`'s resume path.

    Destination train_state generations (adversarial round 11, high
    finding): the scan above only ever covered `iter_*.pt`. Resuming run A's
    state (from any path) into run B's checkpoint_dir proceeded unchallenged
    whenever B's history.json and iter_*.pt evidence were already gone
    (corrupt/missing history, pruned checkpoints) and all that remained was
    B's own `train_state.pt` / `train_state.prev.pt` -- exactly the recovery
    scenario the earlier rounds exist to protect. The very next
    `_atomic_torch_save` would then rotate/destroy B's last recovery point,
    silently splicing A's lineage into B's directory. `checkpoint_dir`'s
    `train_state.pt` and `train_state.prev.pt` are therefore inspected too,
    with `resume_from_state` (the exact file being resumed FROM) compared
    via `os.path.realpath` and skipped -- the overwhelmingly normal case is
    resuming the destination's own state in place, which is not foreign
    lineage to compare against itself. Any OTHER loadable generation found
    must carry the same `run_id` as `state_run_id` (mismatch, including a
    missing/`None` run_id while `state_run_id` is set, raises naming the
    file). Unlike `iter_*.pt`, there is no torn-file/at-resume-point
    tolerance here: an unreadable foreign generation can't have its lineage
    proven, so it raises rather than being quarantined -- recoverable only
    via `--force-history-reset`, same as the rest of this scan."""
    for artifact_path in sorted(checkpoint_dir.glob("iter_*.pt")):
        try:
            artifact_run_id = _artifact_run_id(artifact_path)
        except Exception as exc:
            match = _ITER_CHECKPOINT_NAME_RE.match(artifact_path.name)
            if match is not None and int(match.group(1)) >= next_iteration:
                quarantined_path = artifact_path.with_name(artifact_path.name + ".corrupt")
                os.replace(artifact_path, quarantined_path)
                logger.warning(
                    "%s is unreadable (%s: %s) and at/past the resume point "
                    "(iteration %s >= next_iteration %s) -- quarantined to %s; "
                    "training will regenerate it.",
                    artifact_path.name, type(exc).__name__, exc,
                    match.group(1), next_iteration, quarantined_path.name,
                )
                continue
            raise ValueError(
                f"{artifact_path.name} in checkpoint_dir is unreadable "
                f"({type(exc).__name__}: {exc}) and is needed historical "
                "evidence (its iteration is before the resume point, so "
                "training will never regenerate it) -- resuming cannot "
                "safely proceed without it (pass --force-history-reset if "
                "you are certain this file's loss is fine and want to skip "
                "the artifact-lineage scan entirely)"
            ) from exc
        if artifact_run_id != state_run_id:
            raise ValueError(
                f"{artifact_path.name} in checkpoint_dir carries "
                f"run_id={artifact_run_id!r}, which does not match the "
                f"resuming state file's run_id={state_run_id!r} -- resuming "
                "here would silently mix unrelated runs' checkpoints/history "
                "(point --resume-from-state at the checkpoint_dir that "
                "actually belongs to it, or pass --force-history-reset if "
                "you are certain this is a genuine torn-file recovery and "
                "not a lineage mixup)"
            )

    resume_from_state_real = (
        os.path.realpath(resume_from_state) if resume_from_state is not None else None
    )
    for state_name in ("train_state.pt", "train_state.prev.pt"):
        state_path = checkpoint_dir / state_name
        if not state_path.exists():
            continue
        if resume_from_state_real is not None and os.path.realpath(state_path) == resume_from_state_real:
            continue  # the destination's own state is what's being resumed, not foreign lineage
        try:
            generation_run_id = _train_state_run_id(state_path)
        except Exception as exc:
            raise ValueError(
                f"{state_path.name} in checkpoint_dir is unreadable "
                f"({type(exc).__name__}: {exc}) and its lineage relative to "
                "the resuming state file cannot be proven -- resuming cannot "
                "safely proceed without it (pass --force-history-reset if "
                "you are certain this file's loss is fine and want to skip "
                "the artifact-lineage scan entirely)"
            ) from exc
        if generation_run_id != state_run_id:
            raise ValueError(
                f"{state_path.name} in checkpoint_dir carries "
                f"run_id={generation_run_id!r}, which does not match the "
                f"resuming state file's run_id={state_run_id!r} -- resuming "
                "here would silently mix unrelated runs' train state (point "
                "--resume-from-state at the checkpoint_dir that actually "
                "belongs to it, or pass --force-history-reset if you are "
                "certain this is a genuine torn-file recovery and not a "
                "lineage mixup)"
            )


def _load_resume_history(path: Path, state_run_id: Optional[str], checkpoint_dir: Path,
                         next_iteration: int, force_history_reset: bool = False,
                         resume_from_state: Optional[Path] = None) -> list[dict]:
    """Load `history.json` for a `--resume-from-state` continuation, enforcing
    that its `run_id` matches the resuming state file's `run_id`.

    Format compatibility (adversarial round 3, Finding 1): a legacy bare-list
    `history.json` (written before `run_id` existed) has an implicit
    `run_id` of `None`. It is accepted as matching ONLY when `state_run_id`
    is also `None` (both pre-run_id) -- a state file that DOES carry a
    `run_id` resuming against a legacy bare-list history is rejected, since
    there is no way to confirm the two ever belonged together. Any other
    `run_id` mismatch (including two different UUIDs) raises, naming both,
    to stop a resume from silently merging unrelated run lineages/checkpoints
    into one checkpoint_dir.

    A missing or corrupt file resets history rows to `[]` with a warning, as
    before Finding 1 -- lineage is still preserved because the caller writes
    `state_run_id` into the fresh history going forward. Adversarial round 4,
    high finding: that reset used to run BEFORE any lineage check could catch
    a resume into the wrong checkpoint_dir. Adversarial round 5, high
    finding: round 4's fix only ran `_check_artifact_lineage_or_raise` on
    THIS missing/corrupt-history recovery path -- a resume with a perfectly
    valid, matching history.json never scanned checkpoint_dir's existing
    iter_*.pt artifacts at all, so a foreign checkpoint from an unrelated run
    could sit there undetected. The lineage scan now runs unconditionally on
    every resume (unless `force_history_reset` is set), before this file is
    even read, so both the recovery path and the normal valid-history path
    are covered by the same check. Adversarial round 11, high finding: the
    scan itself now also inspects checkpoint_dir's `train_state.pt` /
    `train_state.prev.pt` generations, not just `iter_*.pt` -- see
    `_check_artifact_lineage_or_raise`'s docstring. `resume_from_state` is
    threaded through so that check can skip the exact file being resumed
    FROM instead of comparing it against itself."""
    if not force_history_reset:
        _check_artifact_lineage_or_raise(checkpoint_dir, state_run_id, next_iteration,
                                         resume_from_state=resume_from_state)
    try:
        raw = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        reason = "missing" if isinstance(exc, FileNotFoundError) else "corrupt"
        logger.warning(
            "history.json is %s; history was reset from a corrupt or missing "
            "file. Per-iteration checkpoints are unaffected; only the JSON "
            "log rows are lost.",
            reason,
        )
        return []
    if isinstance(raw, list):
        history_run_id = None
        rows = raw
    else:
        history_run_id = raw.get("run_id")
        rows = raw.get("rows", [])
    if history_run_id != state_run_id:
        raise ValueError(
            "--resume-from-state run_id mismatch: train_state.pt has "
            f"run_id={state_run_id!r}, but history.json in the same "
            f"checkpoint_dir has run_id={history_run_id!r} -- resuming would "
            "silently mix unrelated run histories/checkpoints (point "
            "--resume-from-state at the checkpoint_dir whose history.json "
            "matches this train_state.pt, or start a fresh checkpoint_dir)"
        )
    return rows


def _save_train_state(path: Path, model: torch.nn.Module, optimizer: torch.optim.Optimizer,
                      next_iteration: int, config: PPOConfig, model_config: ModelConfig,
                      env_config: EnvConfig, base_seed: int, run_id: Optional[str],
                      pinned_bridge_sha256: Optional[str], pinned_bridge_path: Optional[str],
                      init: Optional[dict] = None) -> None:
    # Adversarial round 14, high finding: round 13's fix recomputed the
    # bridge fingerprint HERE, on every save -- so a .so rebuilt mid-run
    # (same path, new bytes) silently became the new saved baseline on the
    # very next periodic save, and a later --resume-from-state happily
    # accepted a run that had mixed two different simulator binaries under
    # one lineage. The fix: the bridge identity is now PINNED EXACTLY ONCE,
    # at run start (see train_b2b's fresh-run / resume branches, which
    # compute/derive `pinned_bridge_sha256`/`pinned_bridge_path` and pass
    # them in here) -- this function must never recompute those as the
    # values to STORE.
    #
    # Adversarial round 15, high finding: drift DETECTION used to also live
    # here, which meant it only ever fired on iterations that happened to
    # coincide with a periodic save -- every other iteration's checkpoint
    # and history row were published under a drifted binary before this
    # function ever ran. Detection has been hoisted out to the caller
    # (`train_b2b`, via `_verify_bridge_unchanged`), which now verifies
    # BEFORE rollout collection and again BEFORE this iteration's
    # checkpoint/history are written -- by the time `_save_train_state` is
    # reached, the caller has already confirmed no drift occurred for this
    # iteration (or that `--allow-bridge-mismatch` was given). This function
    # therefore only ever WRITES the pinned digest, never re-checks it.
    payload = {
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "torch_rng": torch.get_rng_state(),
        "cuda_rng": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
        "numpy_rng": np.random.get_state(),
        "python_rng": random.getstate(),
        "next_iteration": next_iteration,
        "config_echo": _train_b2b_config_echo(config, model_config, env_config),
        "base_seed": base_seed,
        "run_id": run_id,
        # Always the value PINNED at run start -- never the freshly recomputed
        # current one; see the drift-detection block above.
        "bridge_sha256": pinned_bridge_sha256,
        "bridge_library_path": pinned_bridge_path,
        # mortal-scale-scratch: the lineage's construction provenance
        # (`{"kind": "scratch"|"champion", "bc_checkpoint_sha256": ...}`),
        # threaded in from `train_b2b` so a `--resume-from-state` can carry it
        # forward into the checkpoints it goes on to write instead of
        # degrading them to `{"kind": "resumed"}`. Purely additive and
        # deliberately NOT part of `_train_b2b_config_echo`: it is a record of
        # how the run STARTED, not a config the resume must match, so it must
        # never make a legacy state (which has no `init` at all) fail the
        # resume mismatch check.
        "init": init,
    }
    _atomic_torch_save(payload, path)


def _growth_alpha_mean_abs(model: torch.nn.Module) -> Optional[float]:
    """Mean absolute value of every `ReZeroResidualBlock.alpha` in
    `model.growth`, or `None` for a growth-free model (`growth_blocks == 0`,
    an empty `nn.Sequential`).

    Adversarial round 2, Finding 1: `deep16-rezero`'s runbook null-
    interpretation rule ("alphas hugging 0 = protocol null signal") depends
    on these magnitudes actually being recorded somewhere — this feeds
    `train_b2b`'s per-iteration history rows. Returning `None` (rather than
    0.0) for growth-free runs lets callers distinguish "no growth blocks to
    report on" from "growth blocks present but still at/near their zero
    init" — `train_b2b` below omits the history key entirely in the `None`
    case rather than recording a misleading 0.0."""
    alphas = [block.alpha.detach().abs().item() for block in model.growth]
    if not alphas:
        return None
    return float(sum(alphas) / len(alphas))


class EventPathTelemetry:
    """mortal-scale-scratch Amendment 4: per-iteration readouts of the event
    pathway's read-in weights and of the event encoder itself.

    `build_scratch_model` zeroes the trailing `event_encoder.output_dim`
    columns of `trunk.0.weight` so a `--init-from-bc` run starts exactly at the
    BC policy. Those columns are the ONLY thing connecting the event GRU to the
    logits, and they sit inside `trunk.` -- so `split_bc_parameter_groups` puts
    them in the slow `bc` group (`--lr`, 2e-5) while the encoder that feeds them
    trains in the fast `heads` group (`--head-lr`, 2e-4) for iterations
    1..`head_lr_iters`. Amendment 4 ratified that split unchanged and forbade
    explaining a flat iteration-25/50 screening delta as "the event head has
    not engaged yet" unless these numbers support it (and forbade the excuse
    outright from iteration 50 on). Hence: measure it, don't argue about it.

    Non-load-bearing by ruling -- nothing here may change stopping, selection,
    budget, or learning rates, so an integrity failure (a slice that did not
    move at all across a completed iteration, or a non-finite readout) is
    logged loudly and flagged in `history.json` for a human to take back to the
    consult thread, never raised. Raising would be exactly the stopping
    behaviour the amendment rules out.

    Snapshots the model at construction, so build this right after the model is
    created or restored: a resumed run then reports true update norms from its
    first iteration instead of a hole. Returns `None` from every method for a
    model with no event encoder (`event_window == 0`), the same
    "omit rather than report a misleading 0.0" convention as
    `_growth_alpha_mean_abs`."""

    def __init__(self, model: torch.nn.Module) -> None:
        encoder = getattr(model, "event_encoder", None)
        self.event_columns = int(encoder.output_dim) if encoder is not None else 0
        self.enabled = self.event_columns > 0
        self._prev_slice: Optional[torch.Tensor] = None
        self._prev_encoder: Optional[torch.Tensor] = None
        if self.enabled:
            self._prev_slice, _ = self._trunk_columns(model)
            self._prev_encoder = self._encoder_vector(model)

    def _trunk_columns(self, model: torch.nn.Module) -> tuple[torch.Tensor, torch.Tensor]:
        """(event columns, non-event columns) of `trunk.0.weight`, detached on
        the CPU in float64 so the norms below are exact regardless of the
        training dtype/device."""
        weight = model.trunk[0].weight.detach().to("cpu", torch.float64)
        return weight[:, -self.event_columns:].clone(), weight[:, : -self.event_columns].clone()

    def _encoder_vector(self, model: torch.nn.Module) -> torch.Tensor:
        parts = [p.detach().to("cpu", torch.float64).reshape(-1)
                 for p in model.event_encoder.parameters()]
        return torch.cat(parts) if parts else torch.zeros(0, dtype=torch.float64)

    def initial_metrics(self) -> Optional[dict]:
        """The iteration-0 snapshot taken at construction. `event_slice_fro`
        must be exactly 0.0 for a fresh `--init-from-bc` scratch run; it is
        legitimately non-zero on a resume, which snapshots a partly trained
        model."""
        if not self.enabled:
            return None
        assert self._prev_slice is not None and self._prev_encoder is not None
        return {
            "event_slice_fro": float(torch.linalg.vector_norm(self._prev_slice).item()),
            "event_slice_max_abs": float(self._prev_slice.abs().max().item()),
            "event_encoder_param_norm": float(torch.linalg.vector_norm(self._prev_encoder).item()),
            "event_columns": self.event_columns,
        }

    def record(self, model: torch.nn.Module, iteration: int) -> Optional[dict]:
        """Measure the current model and advance the baseline. Call once per
        completed iteration, after the optimizer step."""
        if not self.enabled:
            return None
        event, other = self._trunk_columns(model)
        encoder = self._encoder_vector(model)
        slice_fro = float(torch.linalg.vector_norm(event).item())
        update = event - self._prev_slice
        update_fro = float(torch.linalg.vector_norm(update).item())
        encoder_update_fro = float(torch.linalg.vector_norm(encoder - self._prev_encoder).item())
        # Per-element RMS on both sides, so the ratio compares like with like
        # even though the two column blocks have very different widths.
        event_rms = float(event.pow(2).mean().sqrt().item())
        other_rms = float(other.pow(2).mean().sqrt().item()) if other.numel() else 0.0
        metrics = {
            "event_slice_fro": slice_fro,
            "event_slice_rms": event_rms,
            "event_slice_max_abs": float(event.abs().max().item()),
            "event_slice_update_fro": update_fro,
            "event_slice_rms_ratio": (event_rms / other_rms) if other_rms > 0.0 else float("inf"),
            "event_encoder_param_norm": float(torch.linalg.vector_norm(encoder).item()),
            "event_encoder_update_fro": encoder_update_fro,
        }
        nonfinite = sorted(k for k, v in metrics.items() if not np.isfinite(v))
        if nonfinite:
            metrics["event_path_nonfinite"] = True
            logger.warning(
                "iter %d: event-path telemetry is not finite (%s) -- Amendment 4 integrity "
                "failure, take this to the consult thread; the lap is NOT stopped by this "
                "readout.", iteration, ", ".join(nonfinite))
        if update_fro == 0.0:
            metrics["event_slice_integrity_failure"] = True
            logger.warning(
                "iter %d: the event-input columns of trunk.0.weight did not move at all "
                "(update Frobenius norm exactly 0) -- Amendment 4 integrity failure, take "
                "this to the consult thread; the lap is NOT stopped by this readout.",
                iteration)
        self._prev_slice = event
        self._prev_encoder = encoder
        return metrics


def _find_fresh_run_managed_artifacts(checkpoint_dir: Path) -> list[Path]:
    """Files in `checkpoint_dir` that a previous `train_b2b` run would have
    written -- `history.json`, `train_state.pt`, and any `iter_*.pt`
    checkpoint -- used to guard a fresh (non-`--resume-from-state`) launch
    against silently reusing a directory that already belongs to another
    run (adversarial round 6, high finding). An empty or brand-new
    directory returns `[]`. Anything else in the directory (e.g. stray
    notes, unrelated files) is intentionally not included -- the guard, and
    `--fresh-run-overwrite`'s move-to-backup (adversarial round 18: no longer
    a delete, see `train_b2b`'s fresh branch), only ever touch these managed
    names. `train_state.prev.pt` (adversarial round 9, high finding: the
    one-generation-back durability fallback `_atomic_torch_save` keeps
    alongside `train_state.pt`) is included here too -- it belongs to this
    run exactly as much as `train_state.pt` itself, and is never
    lineage-scanned as an `iter_*.pt` file. A `.overwrite-backup-*`
    subdirectory left behind by a still-completing (or previously
    interrupted) overwrite is never matched by any of the globs/names above
    -- it holds a PRIOR run's backed-up files, not this directory's own live
    artifacts, and must survive both this guard's inspection and any future
    overwrite's move logic untouched. `iter_*.pt.stale` (adversarial round 19,
    high finding: `_quarantine_stale_future_checkpoints`'s quarantined
    obsolete-trajectory checkpoints from an in-progress or interrupted
    `--resume-from-state`) is included too -- it is exactly as much this run's
    own managed artifact as a live `iter_*.pt`, just temporarily parked
    pending its replacement or an end-of-run sweep; a fresh launch must cover
    it the same way, not leave it behind as an untouched stray file.

    `.bridge-*.so` (adversarial round 20, high finding) -- the content-
    addressed bridge-library snapshot a Go-backed run pins its simulator
    identity to (see `_create_bridge_snapshot`) -- is included too: it is
    exactly as much this run's own managed artifact as `train_state.pt`,
    so a fresh launch into a directory that still holds one must fail
    closed (or, with `--fresh-run-overwrite`, move it into the backup)
    like every other managed artifact here, rather than silently leaving a
    stale, disconnected snapshot behind for a NEW run's digest to
    accidentally collide with."""
    found = [checkpoint_dir / name
             for name in ("history.json", "train_state.pt", "train_state.prev.pt")
             if (checkpoint_dir / name).exists()]
    found.extend(sorted(checkpoint_dir.glob("iter_*.pt")))
    found.extend(sorted(checkpoint_dir.glob("iter_*.pt" + _STALE_CHECKPOINT_SUFFIX)))
    found.extend(sorted(checkpoint_dir.glob(_BRIDGE_SNAPSHOT_GLOB)))
    return found


_RUN_LOCK_NAME = ".run.lock"


def _acquire_checkpoint_dir_lock(checkpoint_dir: Path):
    """Claim exclusive ownership of `checkpoint_dir` for the lifetime of this
    process, via `fcntl.flock(LOCK_EX | LOCK_NB)` on `<checkpoint_dir>/.run.lock`
    (adversarial round 7, high finding: the fresh-dir/lineage guards above are
    TOCTOU -- two concurrent `train_b2b` launches pointed at the same
    checkpoint_dir can both pass the artifact-inspection checks, mint
    different `run_id`s, and interleave writes to the same
    iter_*.pt/history.json/train_state.pt).

    Called at the very start of `train_b2b`, before ANY artifact inspection
    or deletion -- covers the fresh, `--fresh-run-overwrite`, and
    `--resume-from-state` paths alike. The lock is released when the
    returned file object is closed (train_b2b does this in a `finally` once
    the run ends) OR when the process dies for any other reason -- flock is
    tied to the open file description, so the OS releases it automatically
    on process exit/crash. That means there is no stale-lock file to clean
    up: a leftover `.run.lock` from a crashed run is inert and the next
    launch acquires it immediately.

    `LOCK_NB` (non-blocking) means a second launch against an
    already-locked directory fails immediately with a loud, named error
    instead of hanging indefinitely waiting for the first run to finish.

    `.run.lock` is deliberately excluded from
    `_find_fresh_run_managed_artifacts`'s names: it must survive both the
    fresh-dir guard's inspection and `--fresh-run-overwrite`'s deletion --
    if overwrite deleted it, a concurrent launch could slip in during the
    brief window between that deletion and this function reacquiring it for
    the new run."""
    lock_path = checkpoint_dir / _RUN_LOCK_NAME
    lock_file = open(lock_path, "a+")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        lock_file.close()
        raise RuntimeError(
            f"could not acquire exclusive lock on {lock_path} -- another "
            f"training process likely already owns checkpoint_dir "
            f"{checkpoint_dir} (running two train_b2b launches against the "
            "same directory would otherwise interleave writes to its "
            "iter_*.pt/history.json/train_state.pt); wait for that run to "
            "finish or point --checkpoint-dir at a different directory"
        ) from exc
    # Diagnostics only -- ownership is enforced by the flock above, not by
    # this content. Overwrite any stale pid/run_id from a prior holder.
    _write_lock_owner(lock_file, run_id=None)
    return lock_file


def _write_lock_owner(lock_file, *, run_id: Optional[str]) -> None:
    """Diagnostics-only: record the owning pid (and, once known, run_id) in
    an already-`flock`-held lock file. Never part of the locking mechanism
    itself -- callers must not rely on this content for correctness, only
    the flock held on `lock_file`'s fd does that."""
    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write(f"pid={os.getpid()} run_id={run_id}\n")
    lock_file.flush()

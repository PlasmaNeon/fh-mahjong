"""B2b crash-resume: the atomic train_state.pt writer, resume config-echo
validation, history reconciliation, run-id lineage, the checkpoint-directory
lock, and bridge-library pinning.

Was test_deep16_rezero.py; the model-growth half is in test_b2b_growth.py."""

import copy
import hashlib
import json
import logging
import multiprocessing as mp
import os
import re
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.train_b2b import train_b2b
from fh_mahjong_ai.train_state import (
    _acquire_checkpoint_dir_lock,
    _find_fresh_run_managed_artifacts,
    read_b2b_history_rows,
)
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.storage import save_checkpoint
from conftest import (
    MOCK_ENV,
    b2b_model_config,
    b2b_run_configs,
    save_b2b_anchor,
    save_champion39,
)


def test_train_state_written_every_n_iterations_and_atomic(tmp_path) -> None:
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=4)
    checkpoint_dir = tmp_path / "ckpt"

    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config,
                        base_seed=5, train_state_every=2)

    assert len(history) == 4
    state_path = checkpoint_dir / "train_state.pt"
    assert state_path.exists()
    assert not (checkpoint_dir / "train_state.pt.tmp").exists()
    state = torch.load(state_path, map_location="cpu", weights_only=False)
    # Last write happens at completion (iteration 4, a multiple of 2 anyway);
    # next_iteration must point one past the last completed iteration.
    assert state["next_iteration"] == 5
    assert state["config_echo"]["ppo_config"]["lr"] == config.lr
    assert state["config_echo"]["model_config"]["event_window"] == model_config.event_window
    assert state["base_seed"] == 5
    for key in ("model", "optimizer", "torch_rng", "numpy_rng", "python_rng", "run_id"):
        assert key in state
    assert state["run_id"]  # non-empty uuid4 hex for a fresh run
    raw_history = json.loads((checkpoint_dir / "history.json").read_text())
    assert raw_history["run_id"] == state["run_id"]


def test_resume_from_state_continues_iteration_count_and_history(tmp_path) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    state_before = torch.load(state_path, map_location="cpu", weights_only=False)
    assert state_before["next_iteration"] == 3
    # mortal-scale-scratch: train_state.pt persists the lineage's construction
    # provenance so a resume can carry it forward (see below).
    assert state_before["init"] == {"kind": "champion", "bc_checkpoint_sha256": None,
                                    "bc_checkpoint_path": None}

    config_resumed = replace(config_first, iterations=4)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=2,
                        resume_from_state=state_path)

    assert len(history) == 4
    assert [row["iteration"] for row in history] == [1, 2, 3, 4]
    history_on_disk = read_b2b_history_rows(checkpoint_dir / "history.json")
    assert [row["iteration"] for row in history_on_disk] == [1, 2, 3, 4]
    for i in (3, 4):
        saved = torch.load(checkpoint_dir / f"iter_{i:03d}.pt", map_location="cpu")
        assert saved["metadata"]["model_config"]["event_window"] == model_config.event_window
        # mortal-scale-scratch: the resume reads `init` back out of the state
        # file and keeps stamping the ORIGINAL provenance onto the checkpoints
        # it writes -- a lap that survives a box restart still says how it was
        # constructed instead of degrading to {"kind": "resumed"}.
        assert saved["metadata"]["init"] == {"kind": "champion", "bc_checkpoint_sha256": None,
                                             "bc_checkpoint_path": None}
    # Resuming must not have re-run the champion warm-start: iter_001/002
    # checkpoints from the first run are untouched (same file, not rewritten).
    assert (checkpoint_dir / "iter_001.pt").exists()
    assert (checkpoint_dir / "iter_002.pt").exists()


def test_resume_from_state_raises_on_different_lr(tmp_path) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"

    config_different_lr = replace(config_first, iterations=4, lr=config_first.lr * 2)
    with pytest.raises(ValueError, match="lr"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_different_lr,
                 base_seed=5, resume_from_state=state_path)


def test_resume_from_state_allows_different_num_workers_with_notice(tmp_path, caplog) -> None:
    # num_workers is semantics-neutral for collection: per-match seeding makes
    # trajectories worker-count-invariant (proven by fh-mj-collect-bench's
    # digest equality across 5/10/20 workers), so a resume that changes only
    # this field must proceed (with a logged notice) rather than raise -- e.g.
    # an operational resume at a lower worker count to avoid OOM.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    assert config_first.num_workers == 1

    config_resumed = replace(config_first, iterations=4, num_workers=2)
    with caplog.at_level(logging.INFO):
        history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                            base_seed=5, train_state_every=2,
                            resume_from_state=state_path)

    assert len(history) == 4
    assert any(
        "num_workers" in record.message and "1" in record.message and "2" in record.message
        for record in caplog.records
    )


def test_resume_from_state_raises_on_different_base_seed(tmp_path) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(
        tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
              base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(
            ValueError, match=r"base_seed.*state file has 5.*requested.*6"):
        train_b2b(
            env, model_config, champion_path, checkpoint_dir, config_resumed,
            base_seed=6, resume_from_state=state_path)


# --- Adversarial round 13, high finding: resume pins the bridge library ---

def test_resolve_current_bridge_fingerprint_mock_bridge_is_none() -> None:
    from fh_mahjong_ai.train_state import _resolve_current_bridge_fingerprint

    env = EnvConfig(bridge_kind="mock")
    assert _resolve_current_bridge_fingerprint(env) == (None, None)


def test_resolve_current_bridge_fingerprint_changes_when_library_is_rebuilt(tmp_path) -> None:
    # The digest must track the ACTUAL bytes at the resolved path, so a
    # rebuild of the .so at the SAME path (config unchanged) is detectable.
    from fh_mahjong_ai.train_state import _resolve_current_bridge_fingerprint

    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-binary-v1")
    env = EnvConfig(bridge_kind="go", bridge_library_path=str(lib_path))

    resolved_path, digest_v1 = _resolve_current_bridge_fingerprint(env)
    assert resolved_path == str(lib_path)
    assert digest_v1 is not None

    lib_path.write_bytes(b"go-bridge-binary-v2-REBUILT")
    _, digest_v2 = _resolve_current_bridge_fingerprint(env)
    assert digest_v2 is not None
    assert digest_v2 != digest_v1

    lib_path.write_bytes(b"go-bridge-binary-v1")
    _, digest_v1_again = _resolve_current_bridge_fingerprint(env)
    assert digest_v1_again == digest_v1


def test_resume_raises_on_bridge_library_rebuild(tmp_path, monkeypatch) -> None:
    # Simulates the adversarial scenario without needing a real .so: the
    # actual mock-bridge rollout collection is unaffected (bridge_kind stays
    # "mock" throughout), only the resolved fingerprint that train_b2b
    # persists/checks is patched to stand in for a "go" bridge whose binary
    # changed between the two launches -- config_echo alone (bridge_kind,
    # bridge_library_path) would NOT catch this, since neither changes.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    monkeypatch.setattr(
        "fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint",
        lambda env_config: ("/fake/libfh_mahjong_bridge.so", "sha-A"),
    )
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state = torch.load(checkpoint_dir / "train_state.pt", map_location="cpu", weights_only=False)
    assert state["bridge_sha256"] == "sha-A"
    assert state["bridge_library_path"] == "/fake/libfh_mahjong_bridge.so"

    monkeypatch.setattr(
        "fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint",
        lambda env_config: ("/fake/libfh_mahjong_bridge.so", "sha-B"),
    )
    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match=r"bridge library mismatch.*sha-A.*sha-B"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=5, resume_from_state=checkpoint_dir / "train_state.pt")


def test_resume_force_history_reset_does_not_override_bridge_mismatch(tmp_path, monkeypatch) -> None:
    # --force-history-reset is a DIFFERENT override (artifact-lineage only);
    # a different simulator binary is never safe to resume under regardless.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    monkeypatch.setattr(
        "fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint",
        lambda env_config: ("/fake/libfh_mahjong_bridge.so", "sha-A"),
    )
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)

    monkeypatch.setattr(
        "fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint",
        lambda env_config: ("/fake/libfh_mahjong_bridge.so", "sha-B"),
    )
    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="bridge library mismatch"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=5, resume_from_state=checkpoint_dir / "train_state.pt",
                 force_history_reset=True)


def test_resume_proceeds_when_bridge_library_identical(tmp_path, monkeypatch) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    monkeypatch.setattr(
        "fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint",
        lambda env_config: ("/fake/libfh_mahjong_bridge.so", "sha-A"),
    )
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, resume_from_state=checkpoint_dir / "train_state.pt")

    assert [row["iteration"] for row in history] == [1, 2]


def test_resume_mock_bridge_round_trip_unaffected(tmp_path) -> None:
    # No monkeypatching at all: an ordinary mock-bridge run's saved
    # bridge_sha256 is None, and None == None passes the resume check
    # exactly as before this fix.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state = torch.load(checkpoint_dir / "train_state.pt", map_location="cpu", weights_only=False)
    assert state["bridge_sha256"] is None

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, resume_from_state=checkpoint_dir / "train_state.pt")
    assert [row["iteration"] for row in history] == [1, 2]


def test_resume_allow_bridge_mismatch_overrides_with_warning(tmp_path, monkeypatch, caplog) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    monkeypatch.setattr(
        "fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint",
        lambda env_config: ("/fake/libfh_mahjong_bridge.so", "sha-A"),
    )
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)

    monkeypatch.setattr(
        "fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint",
        lambda env_config: ("/fake/libfh_mahjong_bridge.so", "sha-B"),
    )
    config_resumed = replace(config_first, iterations=2)
    with caplog.at_level(logging.WARNING):
        history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                            base_seed=5, resume_from_state=checkpoint_dir / "train_state.pt",
                            allow_bridge_mismatch=True)

    assert [row["iteration"] for row in history] == [1, 2]
    assert any("bridge" in record.message.lower() and "sha-a" in record.message.lower()
               for record in caplog.records)


# --- Adversarial round 14, high finding: periodic saves must not silently
# re-pin the bridge identity to whatever binary happens to be on disk at
# save time -- the digest is pinned ONCE, at run start, and every periodic
# save only checks for drift against that pinned value. ---

def test_periodic_save_raises_when_bridge_binary_is_swapped_mid_run(tmp_path, monkeypatch) -> None:
    # Simulates a .so rebuild landing on disk right after iteration 1
    # completes cleanly (both its pre-collection and post-update drift
    # checks saw the v1 digest, and its periodic save pinned bridge_sha256
    # to v1). Iteration 2's pre-collection check must detect the drift and
    # abort BEFORE collecting/publishing anything for iteration 2 -- round
    # 13's fix alone doesn't catch this because it only ever recomputed at
    # save time, so the rebuilt binary would just become the new baseline
    # silently.
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-v1")
    digest_v1 = hashlib.sha256(b"go-bridge-v1").hexdigest()

    calls = {"n": 0}

    def fake_resolve(env_config):
        calls["n"] += 1
        digest = hashlib.sha256(lib_path.read_bytes()).hexdigest()
        if calls["n"] == 3:
            # Call 1 = the fresh-run pin; calls 2 and 3 = iteration 1's
            # pre-collection and post-update checks (both still v1). Land
            # the rebuild right after call 3 so iteration 1 finishes clean
            # and iteration 2's pre-collection check (call 4) is the one
            # that sees v2.
            lib_path.write_bytes(b"go-bridge-v2-REBUILT")
        return str(lib_path), digest

    monkeypatch.setattr("fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint", fake_resolve)

    with pytest.raises(ValueError, match=r"bridge library drift"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config,
                 base_seed=5, train_state_every=1)

    # Iteration 1 published cleanly (no drift occurred during it).
    assert (checkpoint_dir / "iter_001.pt").exists()
    history_after_abort = read_b2b_history_rows(checkpoint_dir / "history.json")
    assert [row["iteration"] for row in history_after_abort] == [1]
    # Iteration 2 must NOT have published anything -- the round 15 fix:
    # the pre-collection check for iteration 2 aborts before that
    # iteration's checkpoint/history row is ever written.
    assert not (checkpoint_dir / "iter_002.pt").exists()

    # The last GOOD state (iteration 1's save) is untouched: still at
    # next_iteration=2, still holding the ORIGINAL v1 digest -- iteration 2's
    # aborted iteration must not have overwritten it with anything.
    state = torch.load(checkpoint_dir / "train_state.pt", map_location="cpu", weights_only=False)
    assert state["next_iteration"] == 2
    assert state["bridge_sha256"] == digest_v1


def test_periodic_save_digest_stable_across_saves_when_binary_unchanged(tmp_path, monkeypatch) -> None:
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=3)
    checkpoint_dir = tmp_path / "ckpt"
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-stable")
    digest = hashlib.sha256(b"go-bridge-stable").hexdigest()

    monkeypatch.setattr(
        "fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint",
        lambda env_config: (str(lib_path), hashlib.sha256(lib_path.read_bytes()).hexdigest()),
    )

    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config,
                        base_seed=5, train_state_every=1)

    assert len(history) == 3
    state = torch.load(checkpoint_dir / "train_state.pt", map_location="cpu", weights_only=False)
    assert state["bridge_sha256"] == digest
    assert state["next_iteration"] == 4


def test_periodic_save_allow_bridge_mismatch_warns_and_keeps_pinned_digest(tmp_path, monkeypatch,
                                                                            caplog) -> None:
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-v1")
    digest_v1 = hashlib.sha256(b"go-bridge-v1").hexdigest()

    calls = {"n": 0}

    def fake_resolve(env_config):
        calls["n"] += 1
        digest = hashlib.sha256(lib_path.read_bytes()).hexdigest()
        if calls["n"] == 3:
            lib_path.write_bytes(b"go-bridge-v2-REBUILT")
        return str(lib_path), digest

    monkeypatch.setattr("fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint", fake_resolve)

    with caplog.at_level(logging.WARNING):
        history = train_b2b(env, model_config, champion_path, checkpoint_dir, config,
                            base_seed=5, train_state_every=1, allow_bridge_mismatch=True)

    assert [row["iteration"] for row in history] == [1, 2]
    state = torch.load(checkpoint_dir / "train_state.pt", map_location="cpu", weights_only=False)
    # Even though the drift was allowed through, the save keeps the run's
    # ORIGINAL pinned digest -- never the drifted one.
    assert state["bridge_sha256"] == digest_v1
    drift_warnings = [record for record in caplog.records
                      if "bridge" in record.message.lower() and "drift" in record.message.lower()]
    assert len(drift_warnings) == 1, (
        "the warning must be logged ONCE for the whole run, not once per "
        f"_verify_bridge_unchanged call (iteration 2 alone triggers two): got {drift_warnings!r}"
    )


# --- Adversarial round 15, high finding: round 14's drift check lived ONLY
# inside `_save_train_state`, so it fired only on iterations that happened to
# coincide with a periodic state save. Every other iteration published its
# `iter_N.pt` + history row under a drifted binary before the next save's
# check finally caught it -- `train_state_every > 1` let several through,
# `train_state_every=0` never checked at all. The fix hoists the check into
# `_verify_bridge_unchanged`, called before collection AND before publishing
# each iteration's artifacts, regardless of `train_state_every`. ---

def test_train_state_every_zero_still_blocks_publish_of_drifted_iteration(tmp_path, monkeypatch) -> None:
    # train_state_every=0 means train_state.pt is NEVER written, so round
    # 14's fix (check lives inside _save_train_state) would never run at
    # all -- a drifted binary would silently collect and publish every
    # iteration forever. The round 15 fix's checks are independent of
    # train_state_every.
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-v1")
    digest_v1 = hashlib.sha256(b"go-bridge-v1").hexdigest()

    calls = {"n": 0}

    def fake_resolve(env_config):
        calls["n"] += 1
        digest = hashlib.sha256(lib_path.read_bytes()).hexdigest()
        if calls["n"] == 3:
            # Call 1 = fresh-run pin; calls 2/3 = iteration 1's
            # pre-collection/post-update checks (both still v1). Rebuild
            # lands right after, so iteration 2's pre-collection check
            # (call 4) is the one that sees v2.
            lib_path.write_bytes(b"go-bridge-v2-REBUILT")
        return str(lib_path), digest

    monkeypatch.setattr("fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint", fake_resolve)

    from fh_mahjong_ai import train_b2b as train_b2b_mod
    real_collect = train_b2b_mod.collect_b2b_rollouts
    collection_calls = {"n": 0}

    def counting_collect(*args, **kwargs):
        collection_calls["n"] += 1
        return real_collect(*args, **kwargs)

    monkeypatch.setattr("fh_mahjong_ai.train_b2b.collect_b2b_rollouts", counting_collect)

    with pytest.raises(ValueError, match=r"bridge library drift"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config,
                 base_seed=5, train_state_every=0)

    assert not (checkpoint_dir / "train_state.pt").exists()
    # Iteration 1 published cleanly; iteration 2 must not have collected or
    # published anything -- the pre-collection check aborted first.
    assert collection_calls["n"] == 1
    assert (checkpoint_dir / "iter_001.pt").exists()
    assert not (checkpoint_dir / "iter_002.pt").exists()
    history = read_b2b_history_rows(checkpoint_dir / "history.json")
    assert [row["iteration"] for row in history] == [1]


def test_train_state_every_three_still_blocks_publish_of_drifted_iteration(tmp_path, monkeypatch) -> None:
    # train_state_every=3 with a drift landing between iterations 1 and 2:
    # the next periodic save (iteration 3) would be round 14's ONLY chance
    # to notice -- by then iteration 2 (and its checkpoint/history row)
    # would already be published under the drifted binary. The round 15
    # fix catches it at iteration 2's pre-collection check instead.
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=4)
    checkpoint_dir = tmp_path / "ckpt"
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-v1")
    digest_v1 = hashlib.sha256(b"go-bridge-v1").hexdigest()

    calls = {"n": 0}

    def fake_resolve(env_config):
        calls["n"] += 1
        digest = hashlib.sha256(lib_path.read_bytes()).hexdigest()
        if calls["n"] == 3:
            lib_path.write_bytes(b"go-bridge-v2-REBUILT")
        return str(lib_path), digest

    monkeypatch.setattr("fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint", fake_resolve)

    with pytest.raises(ValueError, match=r"bridge library drift"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config,
                 base_seed=5, train_state_every=3)

    assert not (checkpoint_dir / "train_state.pt").exists()
    assert (checkpoint_dir / "iter_001.pt").exists()
    for i in (2, 3, 4):
        assert not (checkpoint_dir / f"iter_{i:03d}.pt").exists()
    history = read_b2b_history_rows(checkpoint_dir / "history.json")
    assert [row["iteration"] for row in history] == [1]


def test_resume_pre_collection_check_fires_before_any_collection(tmp_path, monkeypatch) -> None:
    # Swaps the pinned bridge identity AFTER --resume-from-state's own
    # startup validation passes (current == saved digest, so that check is
    # not what catches this) but BEFORE the resumed loop's first iteration
    # collects anything -- the round 15 fix's pre-collection check must be
    # the one that fires, and it must fire before any rollout collection.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    monkeypatch.setattr(
        "fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint",
        lambda env_config: ("/fake/libfh_mahjong_bridge.so", "sha-A"),
    )
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)

    calls = {"n": 0}

    def fake_resolve(env_config):
        calls["n"] += 1
        if calls["n"] == 1:
            # The resume-time startup validation: current == saved, passes.
            return "/fake/libfh_mahjong_bridge.so", "sha-A"
        # Every call after that -- i.e. the resumed loop's own checks --
        # sees a drifted binary.
        return "/fake/libfh_mahjong_bridge.so", "sha-B"

    monkeypatch.setattr("fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint", fake_resolve)

    from fh_mahjong_ai import train_b2b as train_b2b_mod
    real_collect = train_b2b_mod.collect_b2b_rollouts
    collection_calls = {"n": 0}

    def counting_collect(*args, **kwargs):
        collection_calls["n"] += 1
        return real_collect(*args, **kwargs)

    monkeypatch.setattr("fh_mahjong_ai.train_b2b.collect_b2b_rollouts", counting_collect)

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match=r"bridge library drift"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=5, resume_from_state=checkpoint_dir / "train_state.pt")

    assert collection_calls["n"] == 0
    assert not (checkpoint_dir / "iter_002.pt").exists()


def test_allow_bridge_mismatch_downgrades_pre_and_post_checks_to_one_warning(tmp_path, monkeypatch,
                                                                              caplog) -> None:
    # A binary that stays drifted for the WHOLE run triggers the
    # pre-collection AND post-update check every iteration (2 checks x 3
    # iterations = 6 potential warnings) -- --allow-bridge-mismatch must
    # still log only once for the entire run, not once per check.
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=3)
    checkpoint_dir = tmp_path / "ckpt"

    calls = {"n": 0}

    def fake_resolve(env_config):
        calls["n"] += 1
        # Call 1 is the fresh-run pin; every check after that sees a
        # binary that has already drifted away from the pinned value.
        return "/fake/libfh_mahjong_bridge.so", ("sha-pinned" if calls["n"] == 1 else "sha-drifted")

    monkeypatch.setattr("fh_mahjong_ai.train_state._resolve_current_bridge_fingerprint", fake_resolve)

    with caplog.at_level(logging.WARNING):
        history = train_b2b(env, model_config, champion_path, checkpoint_dir, config,
                            base_seed=5, train_state_every=0, allow_bridge_mismatch=True)

    assert [row["iteration"] for row in history] == [1, 2, 3]
    for i in (1, 2, 3):
        assert (checkpoint_dir / f"iter_{i:03d}.pt").exists()
    drift_warnings = [record for record in caplog.records
                      if "bridge" in record.message.lower() and "drift" in record.message.lower()]
    assert len(drift_warnings) == 1, (
        f"expected exactly one drift warning for the whole run, got {drift_warnings!r}"
    )


def test_resume_with_corrupt_history_succeeds_and_warns(tmp_path, caplog) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(
        tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
              base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"
    (checkpoint_dir / "history.json").write_text('[{"iteration": 1')

    config_resumed = replace(config_first, iterations=2)
    with caplog.at_level(logging.WARNING):
        history = train_b2b(
            env, model_config, champion_path, checkpoint_dir, config_resumed,
            base_seed=5, train_state_every=1, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [2]
    assert "history.json" in caplog.text
    assert "reset" in caplog.text
    assert "corrupt" in caplog.text
    assert "per-iteration checkpoints are unaffected" in caplog.text.lower()


def test_history_write_uses_atomic_replace_and_leaves_no_temp_file(
        tmp_path, monkeypatch) -> None:
    env, model_config, champion_path, config = b2b_run_configs(
        tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"
    replace_calls = []
    real_replace = os.replace

    def recording_replace(src, dst):
        replace_calls.append((Path(src), Path(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", recording_replace)
    train_b2b(env, model_config, champion_path, checkpoint_dir, config,
              base_seed=5, train_state_every=1)

    history_path = checkpoint_dir / "history.json"
    assert (checkpoint_dir / "history.json.tmp", history_path) in replace_calls
    assert history_path.exists()
    assert not (checkpoint_dir / "history.json.tmp").exists()


def test_train_state_written_at_completion_even_when_not_multiple_of_every(tmp_path) -> None:
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=3)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config,
             base_seed=5, train_state_every=5)

    state = torch.load(checkpoint_dir / "train_state.pt", map_location="cpu", weights_only=False)
    assert state["next_iteration"] == 4


def test_resume_from_stale_state_reconciles_history_no_duplicates(tmp_path) -> None:
    # CRITICAL repro (reviewer-reported): train_state.pt is only saved every
    # `train_state_every` iterations (here 5), but history.json is appended
    # every iteration. If the process advances past a save point without
    # reaching the next one (e.g. dies at iteration 7 with the last state
    # snapshot from iteration 5), resuming from that STALE state must not
    # replay iterations 6-7 on top of the already-appended rows -- pre-fix,
    # that produced [1,2,3,4,5,6,7,6,7,8]. The fix reconciles history.json
    # down to the state's next_iteration boundary before continuing.
    env, model_config, champion_path, config5 = b2b_run_configs(tmp_path, iterations=5)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config5,
             base_seed=5, train_state_every=5)
    state_path = checkpoint_dir / "train_state.pt"
    stale_state = torch.load(state_path, map_location="cpu", weights_only=False)
    assert stale_state["next_iteration"] == 6
    stale_state_bytes = state_path.read_bytes()  # snapshot the iter-5 state aside

    # Continue to iteration 7 without another state-save boundary (next one
    # is 10): this appends iterations 6 and 7 to history.json, but the
    # completion save at the end of THIS call overwrites train_state.pt with
    # a fresh (non-stale) next_iteration=8 snapshot.
    config7 = replace(config5, iterations=7)
    train_b2b(env, model_config, champion_path, checkpoint_dir, config7,
             base_seed=5, train_state_every=5, resume_from_state=state_path)
    history_after_7 = read_b2b_history_rows(checkpoint_dir / "history.json")
    assert [row["iteration"] for row in history_after_7] == [1, 2, 3, 4, 5, 6, 7]

    # Simulate the crash: the completion save at iteration 7 never made it to
    # disk (box died first) -- only the iter-5 snapshot survived.
    state_path.write_bytes(stale_state_bytes)

    config8 = replace(config5, iterations=8)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config8,
                        base_seed=5, train_state_every=5, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [1, 2, 3, 4, 5, 6, 7, 8]
    history_on_disk = read_b2b_history_rows(checkpoint_dir / "history.json")
    iterations_seen = [row["iteration"] for row in history_on_disk]
    assert iterations_seen == [1, 2, 3, 4, 5, 6, 7, 8]
    assert len(iterations_seen) == len(set(iterations_seen)), "no duplicate iteration rows"
    # The replayed iterations (6, 7) also overwrote iter_006.pt/iter_007.pt by
    # name during the crash-recovery run above; that's benign because
    # restoring the exact model/optimizer/RNG state before replaying makes
    # each re-run of iteration N a deterministic recomputation of the same
    # rollout+update, not a second distinct result.
    for i in range(1, 9):
        assert (checkpoint_dir / f"iter_{i:03d}.pt").exists()


def test_resume_growth_run_rejects_wrong_growth_blocks_then_succeeds_with_correct_config(tmp_path) -> None:
    # MINOR 1: exercise --resume-from-state together with a growth_blocks>0
    # lap. A caller who forgets that resume needs the GROWN model_config
    # (anchor's architecture + growth_blocks folded in, per train_b2b's
    # docstring) and instead passes growth_blocks=0 must get a clear,
    # naming ValueError from _validate_resume_config_echo -- not a silent
    # shape mismatch deeper in model loading. The correctly-reconstructed
    # grown config must then resume cleanly.
    anchor_config = b2b_model_config()
    anchor_path = save_b2b_anchor(tmp_path, anchor_config)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config_first = PPOConfig(device="cpu", iterations=2, matches_per_iter=2,
                             max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                             num_workers=1, match_mode="classic")
    checkpoint_dir = tmp_path / "ckpt"
    train_b2b(env, anchor_config, anchor_path, checkpoint_dir, config_first,
             base_seed=5, growth_blocks=2, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    assert state_path.exists()

    grown_config = replace(anchor_config, growth_blocks=2)
    wrong_config = replace(anchor_config, growth_blocks=0)
    config_resumed = replace(config_first, iterations=4)

    with pytest.raises(ValueError, match="growth_blocks"):
        train_b2b(env, wrong_config, anchor_path, checkpoint_dir, config_resumed,
                 base_seed=5, train_state_every=2, resume_from_state=state_path)

    history = train_b2b(env, grown_config, anchor_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=2, resume_from_state=state_path)
    assert [row["iteration"] for row in history] == [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# Adversarial review round 1 (gru-width branch): a new defaulted field (e.g.
# ModelConfig.event_output_dim) shows up in every freshly-built config echo
# but is absent from a train_state.pt saved before that field existed --
# _validate_resume_config_echo's missing-vs-present comparison must treat
# that silence as "this run used the field's dataclass default", not as a
# recipe drift, or every pre-upgrade multi-day run bricks on resume.
# ---------------------------------------------------------------------------

def _config_echo_triple():
    from fh_mahjong_ai import train_state as train_state_mod

    env = EnvConfig(bridge_kind="mock")
    model_config = ModelConfig()
    config = PPOConfig(device="cpu")
    return train_state_mod._train_b2b_config_echo(config, model_config, env)


def test_resume_config_echo_missing_new_defaulted_field_proceeds(caplog) -> None:
    from fh_mahjong_ai import train_state as train_state_mod

    current = _config_echo_triple()
    assert current["model_config"]["event_output_dim"] == 0
    saved = copy.deepcopy(current)
    del saved["model_config"]["event_output_dim"]  # simulate a pre-upgrade echo

    with caplog.at_level(logging.INFO):
        train_state_mod._validate_resume_config_echo(current, saved)  # must not raise

    assert any(
        "model_config" in record.getMessage() and "event_output_dim" in record.getMessage()
        for record in caplog.records
    )


def test_resume_config_echo_explicit_different_value_still_raises() -> None:
    from fh_mahjong_ai import train_state as train_state_mod

    current = _config_echo_triple()
    saved = copy.deepcopy(current)
    saved["model_config"]["event_output_dim"] = 4  # explicit, non-default, different value

    with pytest.raises(ValueError, match="event_output_dim"):
        train_state_mod._validate_resume_config_echo(current, saved)


def test_resume_config_echo_missing_field_generalizes_to_other_defaulted_fields(caplog) -> None:
    # Proves the fix isn't special-cased to event_output_dim: deleting a
    # DIFFERENT defaulted field (growth_blocks, added for deep16-rezero) from
    # the saved echo must also proceed, standing in for whatever the NEXT new
    # defaulted field turns out to be.
    from fh_mahjong_ai import train_state as train_state_mod

    current = _config_echo_triple()
    assert current["model_config"]["growth_blocks"] == 0
    saved = copy.deepcopy(current)
    del saved["model_config"]["growth_blocks"]

    with caplog.at_level(logging.INFO):
        train_state_mod._validate_resume_config_echo(current, saved)  # must not raise

    assert any(
        "model_config" in record.getMessage() and "growth_blocks" in record.getMessage()
        for record in caplog.records
    )


# ---------------------------------------------------------------------------
# Adversarial review round 5 (gru-width branch), medium finding: round 1's
# fix above back-filled ANY field missing from a saved echo -- not just the
# two proven legacy additions -- using ITS OWN dataclass's TODAY's default.
# That means a malformed/edited state file missing an established field
# (e.g. ppo_config.gamma, env_config.match_mode) silently resumed under
# today's default for that field instead of raising, a fail-open regression
# for every field except the two this was actually meant to cover. Fixed by
# whitelisting only the proven legacy additions (_LEGACY_ECHO_ADDITIONS);
# anything else missing must raise naming it.
# ---------------------------------------------------------------------------

def test_resume_config_echo_missing_ppo_gamma_raises_naming_it() -> None:
    from fh_mahjong_ai import train_state as train_state_mod

    current = _config_echo_triple()
    saved = copy.deepcopy(current)
    del saved["ppo_config"]["gamma"]

    with pytest.raises(ValueError, match="gamma"):
        train_state_mod._validate_resume_config_echo(current, saved)


def test_resume_config_echo_missing_env_match_mode_raises_naming_it() -> None:
    from fh_mahjong_ai import train_state as train_state_mod

    current = _config_echo_triple()
    saved = copy.deepcopy(current)
    del saved["env_config"]["match_mode"]

    with pytest.raises(ValueError, match="match_mode"):
        train_state_mod._validate_resume_config_echo(current, saved)


def test_resume_config_echo_missing_event_output_dim_still_proceeds_with_notice(caplog) -> None:
    # Unchanged behavior for a whitelisted legacy addition.
    from fh_mahjong_ai import train_state as train_state_mod

    current = _config_echo_triple()
    saved = copy.deepcopy(current)
    del saved["model_config"]["event_output_dim"]

    with caplog.at_level(logging.INFO):
        train_state_mod._validate_resume_config_echo(current, saved)  # must not raise

    assert any(
        "model_config" in record.getMessage() and "event_output_dim" in record.getMessage()
        for record in caplog.records
    )


def test_resume_config_echo_missing_growth_blocks_still_proceeds_with_notice(caplog) -> None:
    # Unchanged behavior for the other whitelisted legacy addition.
    from fh_mahjong_ai import train_state as train_state_mod

    current = _config_echo_triple()
    saved = copy.deepcopy(current)
    del saved["model_config"]["growth_blocks"]

    with caplog.at_level(logging.INFO):
        train_state_mod._validate_resume_config_echo(current, saved)  # must not raise

    assert any(
        "model_config" in record.getMessage() and "growth_blocks" in record.getMessage()
        for record in caplog.records
    )


def test_resume_config_echo_missing_nonwhitelisted_model_field_raises() -> None:
    # channels is a real, established ModelConfig field -- NOT in the
    # whitelist -- so its absence must raise, not silently default-fill.
    from fh_mahjong_ai import train_state as train_state_mod

    current = _config_echo_triple()
    saved = copy.deepcopy(current)
    del saved["model_config"]["channels"]

    with pytest.raises(ValueError, match="channels"):
        train_state_mod._validate_resume_config_echo(current, saved)


# ---------------------------------------------------------------------------
# Adversarial review round 3
# ---------------------------------------------------------------------------
#
# Finding 1 (high): resume could merge state with unrelated history --
# train_state.pt came from any path, but history.json was always loaded from
# checkpoint_dir with no lineage binding, so resuming run A's state into run
# B's directory silently mixed histories/checkpoints. Fix: a `run_id`
# (uuid4 hex) is generated at fresh-run start and persisted in both
# train_state.pt and history.json (wrapped as {"run_id": ..., "rows": [...]});
# resume requires state.run_id == history.run_id.
#
# Finding 2 (medium): an exhausted target (`next_iteration > config.iterations`)
# resumed as a silent no-op -- fixed to raise instead.

def test_resume_cross_directory_mismatched_run_id_raises(tmp_path) -> None:
    # The exact scenario from Finding 1: two independent runs, each with its
    # own train_state.pt + history.json. Pointing --resume-from-state at run
    # A's state file while resuming inside run B's checkpoint_dir (e.g. a
    # copy/paste mistake) must not silently splice A's lineage into B.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    train_b2b(env, model_config, champion_path, dir_a, config_first,
             base_seed=5, train_state_every=1)
    train_b2b(env, model_config, champion_path, dir_b, config_first,
             base_seed=5, train_state_every=1)

    state_from_a = dir_a / "train_state.pt"
    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="run_id"):
        train_b2b(env, model_config, champion_path, dir_b, config_resumed,
                 base_seed=5, train_state_every=1, resume_from_state=state_from_a)


def test_resume_matching_run_id_succeeds_and_persists(tmp_path) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    state_before = torch.load(state_path, map_location="cpu", weights_only=False)
    run_id_before = state_before["run_id"]
    assert run_id_before
    raw_history_before = json.loads((checkpoint_dir / "history.json").read_text())
    assert raw_history_before["run_id"] == run_id_before

    config_resumed = replace(config_first, iterations=4)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=2, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [1, 2, 3, 4]
    state_after = torch.load(state_path, map_location="cpu", weights_only=False)
    assert state_after["run_id"] == run_id_before
    raw_history_after = json.loads((checkpoint_dir / "history.json").read_text())
    assert raw_history_after["run_id"] == run_id_before
    assert [row["iteration"] for row in raw_history_after["rows"]] == [1, 2, 3, 4]


def test_resume_legacy_bare_list_history_and_no_run_id_state_is_compat(tmp_path) -> None:
    # MIGRATION: a state file, history.json, and iter_*.pt checkpoints all
    # written before this fix have no run_id at all (bare-list history.json,
    # no "run_id" in checkpoint metadata). That fully pre-run_id trio must
    # still be accepted -- everything is "pre-run_id" and there is nothing
    # to compare. (Since round 5's lineage scan now runs unconditionally on
    # every resume -- not only when history.json is missing/corrupt -- the
    # checkpoints must be downgraded here too, or the scan would correctly
    # flag them as carrying a real run_id the downgraded state doesn't have.)
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"

    # Downgrade state, history, and checkpoints to the legacy pre-run_id shape.
    state = torch.load(state_path, map_location="cpu", weights_only=False)
    del state["run_id"]
    torch.save(state, state_path)
    legacy_rows = read_b2b_history_rows(checkpoint_dir / "history.json")
    (checkpoint_dir / "history.json").write_text(json.dumps(legacy_rows))
    for artifact_path in checkpoint_dir.glob("iter_*.pt"):
        _strip_run_id_from_checkpoint_metadata(artifact_path)

    config_resumed = replace(config_first, iterations=4)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=2, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [1, 2, 3, 4]


def test_resume_run_id_state_with_bare_list_history_raises(tmp_path) -> None:
    # A state file WITH a run_id resuming against a legacy bare-list
    # history.json cannot be confirmed to belong together -- reject rather
    # than silently accepting unverified lineage.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"

    legacy_rows = read_b2b_history_rows(checkpoint_dir / "history.json")
    (checkpoint_dir / "history.json").write_text(json.dumps(legacy_rows))

    config_resumed = replace(config_first, iterations=4)
    with pytest.raises(ValueError, match="run_id"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=5, train_state_every=2, resume_from_state=state_path)


def test_resume_exhausted_target_raises_with_clear_message(tmp_path) -> None:
    # Finding 2: resuming an iter-N state with --iterations already <= N must
    # raise instead of silently exiting success with nothing trained.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"

    config_same_target = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="already satisfied"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_same_target,
                 base_seed=5, resume_from_state=state_path)

    config_lower_target = replace(config_first, iterations=1)
    with pytest.raises(ValueError, match="already satisfied"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_lower_target,
                 base_seed=5, resume_from_state=state_path)


# ---------------------------------------------------------------------------
# Adversarial review round 12
# ---------------------------------------------------------------------------
#
# Finding (high): "iterations" is exempted from the config-echo mismatch
# check UNCONDITIONALLY (see _RESUME_IGNORED_FIELDS), so nothing stops a
# LOWER target than the one the state was saved under, as long as it still
# clears the exhausted-target check below (start_iteration > iterations). A
# state saved from a long run (--iterations 260) resumed with a mistyped
# --iterations 26 (which is > next_iteration) runs to completion and
# silently rewrites train_state.pt as a "finished" 26-iteration run,
# discarding the original 260-iteration target with no error at all.

def _set_saved_iterations_target(state_path: Path, iterations: int) -> None:
    """Rewrite a train_state.pt's config_echo to claim it was saved under a
    different --iterations target, simulating a state that was saved
    mid-run from a longer original run (e.g. the 260-iteration run in the
    finding) without needing an actual 260-iteration test fixture."""
    state = torch.load(state_path, map_location="cpu", weights_only=False)
    state["config_echo"]["ppo_config"]["iterations"] = iterations
    torch.save(state, state_path)


def test_resume_below_saved_target_but_above_next_iteration_raises(tmp_path) -> None:
    # The finding's exact shape: saved target 8, state at next_iteration 3
    # (2 iterations done), resumed with --iterations 5 -- above
    # next_iteration (so the exhausted-target check does not fire) but
    # below the saved target of 8 (so it WOULD silently truncate the run).
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    assert torch.load(state_path, map_location="cpu",
                       weights_only=False)["next_iteration"] == 3
    _set_saved_iterations_target(state_path, 8)

    config_truncating = replace(config_first, iterations=5)
    with pytest.raises(ValueError, match=r"truncat.*8.*5|8.*5.*truncat"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_truncating,
                 base_seed=5, resume_from_state=state_path)


def test_resume_at_saved_target_is_a_normal_resume(tmp_path) -> None:
    # Equal target == normal resume: must NOT raise the truncation error.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    _set_saved_iterations_target(state_path, 8)

    config_same_target = replace(config_first, iterations=8)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_same_target,
                        base_seed=5, resume_from_state=state_path)
    assert [row["iteration"] for row in history] == [1, 2, 3, 4, 5, 6, 7, 8]


def test_resume_above_saved_target_is_an_explicit_extension(tmp_path) -> None:
    # Higher target == the documented, intended use of --resume-from-state:
    # explicitly training past the original target. Must NOT raise.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    _set_saved_iterations_target(state_path, 8)

    config_extended = replace(config_first, iterations=10)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_extended,
                        base_seed=5, resume_from_state=state_path)
    assert [row["iteration"] for row in history] == list(range(1, 11))


def test_resume_below_next_iteration_still_raises_exhausted_not_truncation(tmp_path) -> None:
    # A target below next_iteration is ALSO below the (higher, faked) saved
    # target here, so it satisfies both checks' trigger conditions -- but no
    # training can happen at all regardless of the original target, so the
    # existing "already satisfied" exhausted-target check (round 3) must be
    # the one that fires, not the new truncation message.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    _set_saved_iterations_target(state_path, 8)

    config_exhausted = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="already satisfied"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_exhausted,
                 base_seed=5, resume_from_state=state_path)


# ---------------------------------------------------------------------------
# Adversarial review round 4
# ---------------------------------------------------------------------------
#
# Finding (high): the round-1 "tolerate corrupt/missing history" recovery
# returned an empty history BEFORE the round-3 run_id comparison could ever
# run, so resuming run A's state.pt into run B's checkpoint_dir whose
# history.json was lost kept B's iter_*.pt files on disk while writing A's
# new checkpoints alongside them -- undetectable later since iteration
# checkpoints didn't carry run_id. Fix: iteration checkpoints now save
# run_id in metadata; a missing/corrupt history.json triggers a scan of
# checkpoint_dir's existing iter_*.pt artifacts (if any) whose metadata
# run_id must all match the resuming state's run_id, or the resume raises
# (mixed-lineage, fail closed) unless --force-history-reset is passed.

def _strip_run_id_from_checkpoint_metadata(path: Path) -> None:
    payload = torch.load(path, map_location="cpu")
    payload.get("metadata", {}).pop("run_id", None)
    torch.save(payload, path)


def test_resume_state_a_into_dir_with_bs_checkpoints_and_no_history_raises(tmp_path) -> None:
    # The exact round-4 scenario: run B's history.json is lost/corrupted, and
    # someone points --resume-from-state at run A's train_state.pt while
    # still inside run B's checkpoint_dir. Pre-fix this silently proceeded
    # (empty history) and clobbered/mixed B's checkpoints with A's lineage.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    train_b2b(env, model_config, champion_path, dir_a, config_first,
             base_seed=5, train_state_every=1)
    train_b2b(env, model_config, champion_path, dir_b, config_first,
             base_seed=5, train_state_every=1)

    state_from_a = dir_a / "train_state.pt"
    (dir_b / "history.json").unlink()  # simulate B's history.json being lost

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="run_id"):
        train_b2b(env, model_config, champion_path, dir_b, config_resumed,
                 base_seed=5, train_state_every=1, resume_from_state=state_from_a)


def test_resume_matching_run_id_artifacts_with_missing_history_proceeds_with_warning(
        tmp_path, caplog) -> None:
    # Genuine round-1 torn-file recovery: history.json is gone, but the
    # checkpoint_dir's existing iter_*.pt files all carry the SAME run_id as
    # the resuming state -- this is one run's own history being lost, not a
    # lineage mixup, so it must still proceed (with the existing warning).
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"
    (checkpoint_dir / "history.json").unlink()

    config_resumed = replace(config_first, iterations=2)
    with caplog.at_level(logging.WARNING):
        history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                            base_seed=5, train_state_every=1, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [2]
    assert "history.json" in caplog.text


def test_resume_into_relocated_empty_dir_with_missing_history_proceeds(tmp_path) -> None:
    # Relocating a state file into a brand-new, empty checkpoint_dir (no
    # iter_*.pt at all) has nothing on disk to contradict the resume, so it
    # must proceed even though history.json is also missing there.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    source_dir = tmp_path / "source"

    train_b2b(env, model_config, champion_path, source_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = source_dir / "train_state.pt"

    empty_dir = tmp_path / "relocated_empty"
    empty_dir.mkdir()

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, empty_dir, config_resumed,
                        base_seed=5, train_state_every=1, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [2]


def test_force_history_reset_overrides_mixed_lineage_check(tmp_path) -> None:
    # The explicit, documented-as-dangerous escape hatch: --force-history-
    # reset skips ONLY the artifact-lineage check, letting an operator who is
    # certain this is a genuine recovery (not a mixup) proceed anyway.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    train_b2b(env, model_config, champion_path, dir_a, config_first,
             base_seed=5, train_state_every=1)
    train_b2b(env, model_config, champion_path, dir_b, config_first,
             base_seed=5, train_state_every=1)

    state_from_a = dir_a / "train_state.pt"
    (dir_b / "history.json").unlink()

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, dir_b, config_resumed,
                        base_seed=5, train_state_every=1, resume_from_state=state_from_a,
                        force_history_reset=True)

    assert [row["iteration"] for row in history] == [2]


def test_force_history_reset_does_not_skip_base_seed_check(tmp_path) -> None:
    # --force-history-reset is documented to skip ONLY the artifact-lineage
    # check -- never the config/base_seed checks, which guard against a
    # different failure mode entirely (a genuinely different recipe/schedule).
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="base_seed"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=6, resume_from_state=state_path, force_history_reset=True)


def test_resume_legacy_artifacts_and_legacy_state_missing_history_is_compat(tmp_path) -> None:
    # Pre-run_id artifacts + a pre-run_id state file resuming with a missing
    # history.json must keep today's behavior (proceed with a warning) --
    # both sides predate run_id, so there is nothing to compare.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"

    _strip_run_id_from_checkpoint_metadata(checkpoint_dir / "iter_001.pt")
    state = torch.load(state_path, map_location="cpu", weights_only=False)
    del state["run_id"]
    torch.save(state, state_path)
    (checkpoint_dir / "history.json").unlink()

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=1, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [2]


def test_resume_run_id_state_with_legacy_artifact_and_missing_history_raises(tmp_path) -> None:
    # A state file WITH a run_id, resuming where the on-disk iter_*.pt
    # artifact predates run_id (no run_id in its metadata) and history.json
    # is also gone, cannot prove lineage -- must raise, not silently accept.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"

    _strip_run_id_from_checkpoint_metadata(checkpoint_dir / "iter_001.pt")
    (checkpoint_dir / "history.json").unlink()

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="run_id"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=5, train_state_every=1, resume_from_state=state_path)


def test_new_checkpoint_metadata_carries_run_id_and_infer_model_config_loads_it(tmp_path) -> None:
    from fh_mahjong_ai.model import infer_model_config

    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config, base_seed=5)

    saved = torch.load(checkpoint_dir / "iter_001.pt", map_location="cpu")
    assert "run_id" in saved["metadata"]
    assert saved["metadata"]["run_id"]

    recovered = infer_model_config(saved["model"], saved["metadata"])
    assert recovered.event_window == model_config.event_window


# ---------------------------------------------------------------------------
# Adversarial review round 5
# ---------------------------------------------------------------------------
#
# Finding (high): the round-4 artifact-lineage check only ran on the
# missing/corrupt-history recovery path (inside the `except` branch of
# `_load_resume_history`). With a VALID, matching state/history pair, it
# never ran at all -- so a foreign iter_*.pt file left in checkpoint_dir by
# an unrelated run (e.g. someone copied a state+history pair into a
# directory that already had leftover checkpoints from a different run) was
# never inspected. Training only overwrites iterations >= start_iteration,
# so any foreign earlier checkpoint stays on disk indefinitely where
# screening/retention tooling could still select it. Fix: run the lineage
# scan on EVERY resume, not just the recovery path; --force-history-reset
# remains the one documented override.

def test_resume_valid_history_with_one_foreign_run_id_artifact_raises(tmp_path) -> None:
    # Two independent runs. Run B's checkpoint_dir picks up a stray iter_*.pt
    # from run A (e.g. a bad copy), but run B's OWN state.pt/history.json
    # pair is fully valid and matching. The foreign artifact must still be
    # caught -- lineage validation cannot be gated on history.json being
    # broken.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    train_b2b(env, model_config, champion_path, dir_a, config_first,
             base_seed=5, train_state_every=1)
    train_b2b(env, model_config, champion_path, dir_b, config_first,
             base_seed=5, train_state_every=1)

    state_path_b = dir_b / "train_state.pt"
    # Plant a foreign checkpoint from run A into run B's checkpoint_dir,
    # alongside B's own valid, matching train_state.pt/history.json.
    shutil.copy(dir_a / "iter_001.pt", dir_b / "iter_002.pt")

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="run_id"):
        train_b2b(env, model_config, champion_path, dir_b, config_resumed,
                 base_seed=5, train_state_every=1, resume_from_state=state_path_b)


def test_resume_valid_history_all_matching_artifacts_proceeds(tmp_path) -> None:
    # Control: a normal resume where history.json is intact AND every
    # iter_*.pt on disk shares the resuming state's run_id must keep working
    # -- the new unconditional scan must not false-positive on the common
    # case.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=1, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [1, 2]


def test_resume_valid_history_with_legacy_foreign_artifact_raises(tmp_path) -> None:
    # Extend the round-4 "pre-run_id legacy artifact" coverage to the VALID
    # history path: a run_id-carrying state resuming against its own valid,
    # matching history.json, but with a legacy (no run_id in metadata)
    # iter_*.pt also sitting in checkpoint_dir, cannot prove that legacy
    # artifact belongs to this lineage -- must raise.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"

    _strip_run_id_from_checkpoint_metadata(checkpoint_dir / "iter_001.pt")

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="run_id"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=5, train_state_every=1, resume_from_state=state_path)


def test_force_history_reset_overrides_mixed_lineage_check_with_valid_history(tmp_path) -> None:
    # --force-history-reset is the general lineage override, not just a
    # missing/corrupt-history escape hatch: it must also let a resume proceed
    # past a foreign artifact when history.json is otherwise valid and
    # matching.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    train_b2b(env, model_config, champion_path, dir_a, config_first,
             base_seed=5, train_state_every=1)
    train_b2b(env, model_config, champion_path, dir_b, config_first,
             base_seed=5, train_state_every=1)

    state_path_b = dir_b / "train_state.pt"
    shutil.copy(dir_a / "iter_001.pt", dir_b / "iter_002.pt")

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, dir_b, config_resumed,
                        base_seed=5, train_state_every=1, resume_from_state=state_path_b,
                        force_history_reset=True)


def test_fresh_launch_into_dir_with_iter_checkpoint_raises_naming_it(tmp_path) -> None:
    # Adversarial round 6, high finding: a fresh (non-resume) launch into a
    # checkpoint_dir that already holds a prior run's iter_*.pt must fail
    # closed instead of silently overwriting early checkpoints while leaving
    # later ones in place (mixed lineage).
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first, base_seed=5)
    assert (checkpoint_dir / "iter_001.pt").exists()

    with pytest.raises(ValueError, match="iter_001.pt"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_first, base_seed=7)


def test_fresh_launch_into_dir_with_only_history_json_raises(tmp_path) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir(parents=True)
    (checkpoint_dir / "history.json").write_text(json.dumps({"run_id": "abc", "rows": []}))

    with pytest.raises(ValueError, match="history.json"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_first, base_seed=7)


def test_fresh_launch_into_empty_or_new_dir_proceeds(tmp_path) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"  # does not exist yet

    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_first, base_seed=5)

    assert len(history) == 1
    assert (checkpoint_dir / "iter_001.pt").exists()


def test_fresh_run_overwrite_removes_only_managed_artifacts_and_proceeds(tmp_path) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    assert (checkpoint_dir / "iter_001.pt").exists()
    assert (checkpoint_dir / "train_state.pt").exists()
    assert (checkpoint_dir / "history.json").exists()
    decoy = checkpoint_dir / "foo.txt"
    decoy.write_text("do not touch")

    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
                        base_seed=9, fresh_run_overwrite=True)

    assert len(history) == 1
    assert decoy.exists()
    assert decoy.read_text() == "do not touch"
    # The prior run's history was cleared, not merged with this run's.
    raw_history = json.loads((checkpoint_dir / "history.json").read_text())
    assert len(raw_history["rows"]) == 1


def test_fresh_run_overwrite_invalid_champion_preserves_old_artifacts(tmp_path) -> None:
    # Adversarial round 18, high finding: --fresh-run-overwrite must be
    # transactional. The old implementation deleted the prior run's managed
    # artifacts BEFORE constructing/validating the new model -- an invalid
    # champion/anchor checkpoint then left checkpoint_dir destroyed with no
    # replacement. The fix validates everything that can fail first, so a
    # failing overwrite must leave the old artifacts recoverable (either
    # untouched or moved into a backup subdirectory), never deleted outright.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    assert (checkpoint_dir / "iter_001.pt").exists()
    assert (checkpoint_dir / "train_state.pt").exists()
    assert (checkpoint_dir / "history.json").exists()

    bad_champion = tmp_path / "does-not-exist.pt"
    with pytest.raises(Exception):
        train_b2b(env, model_config, bad_champion, checkpoint_dir, config_first,
                 base_seed=9, fresh_run_overwrite=True)

    def _artifact_recoverable(name: str) -> bool:
        if (checkpoint_dir / name).exists():
            return True
        return any((backup_dir / name).exists()
                   for backup_dir in checkpoint_dir.glob(".overwrite-backup-*"))

    assert _artifact_recoverable("iter_001.pt")
    assert _artifact_recoverable("train_state.pt")
    assert _artifact_recoverable("history.json")


def test_fresh_run_overwrite_cleans_backup_after_first_durable_save(tmp_path) -> None:
    # A successful overwrite must eventually clean up its backup directory --
    # once this new run has written its own first durable artifact
    # (train_state.pt, since train_state_every > 0 here), the old run's
    # backed-up files are no longer needed to recover from a mid-run failure.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=9, fresh_run_overwrite=True, train_state_every=1)

    assert not list(checkpoint_dir.glob(".overwrite-backup-*"))
    assert (checkpoint_dir / "iter_002.pt").exists()


def test_fresh_run_overwrite_cleans_backup_after_first_checkpoint_when_state_every_zero(tmp_path) -> None:
    # train_state_every=0 means train_state.pt is never written at all (see
    # test_train_state_every_zero_still_blocks_publish_of_drifted_iteration),
    # so the first durable artifact for backup-cleanup purposes must be the
    # first iter_*.pt checkpoint instead.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=9, fresh_run_overwrite=True, train_state_every=0)

    assert not list(checkpoint_dir.glob(".overwrite-backup-*"))
    assert (checkpoint_dir / "iter_001.pt").exists()


def test_overwrite_backup_dir_excluded_from_managed_artifact_guard(tmp_path) -> None:
    # A leftover (or in-progress) `.overwrite-backup-*` directory must never
    # itself be treated as a managed artifact of a fresh launch -- it holds a
    # PRIOR run's backed-up files, not this directory's own live artifacts,
    # and must survive both the fresh-dir guard's inspection and any future
    # overwrite's deletion/move logic.
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()
    backup_dir = checkpoint_dir / ".overwrite-backup-deadbeef"
    backup_dir.mkdir()
    (backup_dir / "iter_001.pt").write_bytes(b"stale backup content")
    (backup_dir / "train_state.pt").write_bytes(b"stale backup content")
    (backup_dir / "history.json").write_text("{}")

    assert _find_fresh_run_managed_artifacts(checkpoint_dir) == []


def test_resume_path_unaffected_by_fresh_run_guard(tmp_path) -> None:
    # The guard must only apply to fresh (non-resume) launches; a legitimate
    # --resume-from-state into a populated checkpoint_dir (its own prior
    # iterations) must still work exactly as before.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"

    config_resumed = replace(config_first, iterations=4)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=2, resume_from_state=state_path)

    assert len(history) == 4
    assert [row["iteration"] for row in history] == [1, 2, 3, 4]


# --- Adversarial round 7, high finding: checkpoint_dir ownership lock ------
#
# The fresh-dir/lineage guards above are TOCTOU -- two concurrent train_b2b
# launches pointed at the same checkpoint_dir can both pass the artifact
# checks, mint different run_ids, and interleave writes to the same
# iter_*.pt/history.json/train_state.pt. `_acquire_checkpoint_dir_lock`
# closes that gap with an flock on `<checkpoint_dir>/.run.lock`. flock is
# per-process (per open file description, specifically), so exercising the
# "second launch is rejected" and "release on process exit" behavior
# honestly requires real separate processes, not threads or in-process
# monkeypatching -- hence multiprocessing.get_context("spawn") below.

def _hold_checkpoint_dir_lock_until_released(checkpoint_dir_str: str, ready, release) -> None:
    lock_file = _acquire_checkpoint_dir_lock(Path(checkpoint_dir_str))
    ready.set()
    release.wait(timeout=10)
    lock_file.close()


def _acquire_checkpoint_dir_lock_then_crash(checkpoint_dir_str: str) -> None:
    _acquire_checkpoint_dir_lock(Path(checkpoint_dir_str))
    # Deliberately exit without closing the lock file -- simulates a killed/
    # crashed training process. flock must be released by the OS when the
    # process dies, not by our own cleanup code, or a crashed run would
    # leave checkpoint_dir permanently unlaunchable.
    os._exit(0)


def test_concurrent_checkpoint_dir_lock_second_launch_raises(tmp_path) -> None:
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()
    ctx = mp.get_context("spawn")
    ready = ctx.Event()
    release = ctx.Event()
    holder = ctx.Process(target=_hold_checkpoint_dir_lock_until_released,
                         args=(str(checkpoint_dir), ready, release))
    holder.start()
    try:
        assert ready.wait(timeout=10), "holder process never acquired the lock"
        lock_path = checkpoint_dir / ".run.lock"
        with pytest.raises(RuntimeError, match=re.escape(str(lock_path))):
            _acquire_checkpoint_dir_lock(checkpoint_dir)
    finally:
        release.set()
        holder.join(timeout=10)
    assert holder.exitcode == 0


def test_checkpoint_dir_lock_released_when_owning_process_dies(tmp_path) -> None:
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()
    ctx = mp.get_context("spawn")
    proc = ctx.Process(target=_acquire_checkpoint_dir_lock_then_crash, args=(str(checkpoint_dir),))
    proc.start()
    proc.join(timeout=10)
    assert proc.exitcode == 0

    # The crashed process never closed its lock_file, but the OS releases
    # flock on process exit regardless -- this must succeed, not raise.
    lock_file = _acquire_checkpoint_dir_lock(checkpoint_dir)
    try:
        assert lock_file is not None
    finally:
        lock_file.close()


def test_fresh_run_overwrite_does_not_delete_run_lock(tmp_path) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    lock_path = checkpoint_dir / ".run.lock"
    assert lock_path.exists()
    # The fresh-dir guard's own artifact list must never include the lock
    # file -- if it did, --fresh-run-overwrite's deletion loop would remove
    # the very file protecting the run about to start.
    assert lock_path not in _find_fresh_run_managed_artifacts(checkpoint_dir)

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=9, fresh_run_overwrite=True)

    assert lock_path.exists()


def test_resume_path_acquires_checkpoint_dir_lock(tmp_path) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"

    config_resumed = replace(config_first, iterations=2)
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
             base_seed=5, train_state_every=1, resume_from_state=state_path)

    lock_path = checkpoint_dir / ".run.lock"
    assert lock_path.exists()
    assert f"pid={os.getpid()}" in lock_path.read_text()


# ---------------------------------------------------------------------------
# Adversarial review round 8
# ---------------------------------------------------------------------------
#
# Finding (high): iter_*.pt checkpoints were written non-atomically (a bare
# `torch.save`), and the resume lineage scan (`_check_artifact_lineage_or_
# raise`) does a full `torch.load` of EVERY iter_*.pt in checkpoint_dir. A
# crash mid-serialization of any single iter_*.pt therefore left a torn file
# that made every subsequent `--resume-from-state` -- the very feature meant
# to survive a crash -- raise on the unrelated `torch.load` failure, not on
# a genuine lineage problem. Fix: (1) `save_checkpoint` (storage.py, see
# test_storage.py) now writes atomically; (2) the lineage scan tolerates an
# unreadable/truncated artifact by comparing its iteration number (parsed
# from `iter_NNN.pt`) against the resuming state's `next_iteration`: an
# iteration at or past the resume point will be overwritten by training
# anyway, so the torn file is quarantined (renamed `<name>.corrupt`, warned,
# scan continues); an iteration before the resume point is irreplaceable
# historical evidence, so the scan raises, naming the file and pointing at
# `--force-history-reset` as the documented override.

def test_resume_raises_naming_torn_historical_checkpoint(tmp_path, caplog) -> None:
    # iter_002.pt is torn (crash mid-write), and its iteration (2) is BEFORE
    # the resume point (next_iteration=5) -- training will never regenerate
    # it, so this is unrecoverable historical evidence and must raise loudly
    # rather than being silently swept aside.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=4)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"
    state = torch.load(state_path, map_location="cpu", weights_only=False)
    assert state["next_iteration"] == 5

    torn_path = checkpoint_dir / "iter_002.pt"
    torn_path.write_bytes(b"not a valid torch checkpoint, truncated mid-write")

    config_resumed = replace(config_first, iterations=5)
    with pytest.raises(ValueError, match="iter_002.pt") as excinfo:
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=5, train_state_every=1, resume_from_state=state_path)
    assert "--force-history-reset" in str(excinfo.value)
    # The torn file must be left alone -- it is evidence, not garbage --
    # when the scan can't safely dispose of it.
    assert torn_path.exists()
    assert torn_path.read_bytes() == b"not a valid torch checkpoint, truncated mid-write"


def test_resume_quarantines_torn_checkpoint_at_or_past_resume_point(tmp_path, caplog) -> None:
    # iter_005.pt is torn, but its iteration (5) is AT the resume point
    # (next_iteration=5) -- exactly the crash window the resume feature
    # exists to survive: training died writing iter_005.pt before it could
    # also persist train_state.pt. Training is about to regenerate iter_005
    # anyway, so the torn file is quarantined (renamed .corrupt) instead of
    # blocking the resume it was meant to enable.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=4)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"
    state = torch.load(state_path, map_location="cpu", weights_only=False)
    assert state["next_iteration"] == 5

    torn_path = checkpoint_dir / "iter_005.pt"
    torn_path.write_bytes(b"not a valid torch checkpoint, truncated mid-write")
    quarantined_path = checkpoint_dir / "iter_005.pt.corrupt"

    config_resumed = replace(config_first, iterations=6)
    with caplog.at_level(logging.WARNING):
        history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                            base_seed=5, train_state_every=1, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [1, 2, 3, 4, 5, 6]
    assert "iter_005.pt" in caplog.text
    assert quarantined_path.exists()
    assert quarantined_path.read_bytes() == b"not a valid torch checkpoint, truncated mid-write"
    # Training regenerated iter_005.pt at the (now-vacated) original path,
    # with valid, loadable content -- resume genuinely proceeded.
    regenerated_payload = torch.load(torn_path, map_location="cpu")
    assert regenerated_payload["metadata"]["run_id"] == state["run_id"]


# ---------------------------------------------------------------------------
# Adversarial review round 9, finding 1 (high): train_state.pt power-loss
# durability
# ---------------------------------------------------------------------------
#
# `_atomic_torch_save` wrote the tmp file and `os.replace`d it into place
# with no `fsync` at all: a host power-loss between the write completing and
# the data actually reaching disk (or between the rename landing and the
# directory entry itself reaching disk) could leave a renamed
# `train_state.pt` unreadable -- and by then the PREVIOUS, still-good
# generation had already been overwritten, so there was nothing to fall
# back to. The fix fsyncs the tmp file and the parent directory around the
# replace, AND keeps one extra generation (`train_state.prev.pt`) so a
# resume always has two independent chances to find a loadable state.

def test_train_state_prev_generation_created_on_second_save(tmp_path) -> None:
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"
    state_path = checkpoint_dir / "train_state.pt"
    prev_path = checkpoint_dir / "train_state.prev.pt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config,
             base_seed=5, train_state_every=1)
    assert state_path.exists()
    assert not prev_path.exists(), "no prior generation existed yet, so nothing to keep as prev"
    first_state = torch.load(state_path, map_location="cpu", weights_only=False)
    assert first_state["next_iteration"] == 2

    config_resumed = replace(config, iterations=2)
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
             base_seed=5, train_state_every=1, resume_from_state=state_path)

    assert prev_path.exists(), "the second save must demote the prior valid generation to .prev"
    prev_state = torch.load(prev_path, map_location="cpu", weights_only=False)
    assert prev_state["next_iteration"] == 2
    current_state = torch.load(state_path, map_location="cpu", weights_only=False)
    assert current_state["next_iteration"] == 3


def test_resume_falls_back_to_prev_generation_when_current_is_corrupt(tmp_path, caplog) -> None:
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"
    state_path = checkpoint_dir / "train_state.pt"
    prev_path = checkpoint_dir / "train_state.prev.pt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config,
             base_seed=5, train_state_every=1)
    good_bytes = state_path.read_bytes()
    # Simulate a host reset landing between promoting the old generation to
    # .prev and finishing the write of the new one: .prev holds a genuinely
    # valid, loadable state, but the "current" file is torn/corrupt.
    prev_path.write_bytes(good_bytes)
    state_path.write_bytes(b"torn mid-write, not a valid torch file")

    config_resumed = replace(config, iterations=2)
    with caplog.at_level(logging.WARNING):
        history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                            base_seed=5, train_state_every=1, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [1, 2]
    assert "train_state.prev.pt" in caplog.text
    assert re.search(r"unreadable|falling back", caplog.text, re.IGNORECASE)


def test_resume_raises_clear_error_when_both_generations_are_corrupt(tmp_path) -> None:
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"
    state_path = checkpoint_dir / "train_state.pt"
    prev_path = checkpoint_dir / "train_state.prev.pt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config,
             base_seed=5, train_state_every=1)
    state_path.write_bytes(b"torn current generation")
    prev_path.write_bytes(b"torn prev generation")

    config_resumed = replace(config, iterations=2)
    with pytest.raises(Exception, match=r"(?i)unreadable"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=5, train_state_every=1, resume_from_state=state_path)


def test_fresh_run_overwrite_removes_both_train_state_generations(tmp_path) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"
    prev_path = checkpoint_dir / "train_state.prev.pt"
    assert state_path.exists()
    assert prev_path.exists()
    decoy = checkpoint_dir / "foo.txt"
    decoy.write_text("do not touch")

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=9, fresh_run_overwrite=True)

    assert not prev_path.exists()
    assert decoy.exists()
    assert decoy.read_text() == "do not touch"


# ---------------------------------------------------------------------------
# Adversarial review round 11, high finding: lineage scan ignores
# destination train_state files
# ---------------------------------------------------------------------------
#
# `_check_artifact_lineage_or_raise` only ever scanned `iter_*.pt`. Resuming
# run A's state (from any path) into run B's checkpoint_dir proceeded
# unchallenged whenever B's history/iter_*.pt evidence was already gone and
# all that remained was B's own `train_state.pt`/`train_state.prev.pt` --
# exactly the "history corrupt/missing, checkpoints pruned" recovery
# scenario the earlier rounds were built to protect. The very next
# `_atomic_torch_save` then rotates/destroys B's last recovery point,
# silently splicing A's lineage into B's directory. Fix: the scan now also
# inspects `train_state.pt` and `train_state.prev.pt` in checkpoint_dir,
# skipping the exact file being resumed FROM (compared via
# `os.path.realpath` -- the normal case is resuming the destination's own
# state), and requires any OTHER loadable generation found there to carry
# the same run_id as the resuming state.

def test_resume_state_a_into_dir_with_only_bs_train_state_raises_naming_it(tmp_path) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    train_b2b(env, model_config, champion_path, dir_a, config_first,
             base_seed=5, train_state_every=1)
    train_b2b(env, model_config, champion_path, dir_b, config_first,
             base_seed=5, train_state_every=1)

    state_from_a = dir_a / "train_state.pt"
    # Simulate history/checkpoints already lost/pruned in B -- only B's own
    # train_state.pt is left as evidence of B's lineage.
    (dir_b / "history.json").unlink()
    (dir_b / "iter_001.pt").unlink()

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="train_state.pt"):
        train_b2b(env, model_config, champion_path, dir_b, config_resumed,
                 base_seed=5, train_state_every=1, resume_from_state=state_from_a)


def test_resume_destinations_own_state_in_place_proceeds(tmp_path) -> None:
    # The normal, overwhelmingly common case: resuming checkpoint_dir's own
    # train_state.pt (the file the scan must recognize via realpath/samefile
    # as the thing BEING resumed from, not a foreign generation to compare
    # against itself).
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"
    (checkpoint_dir / "history.json").unlink()
    (checkpoint_dir / "iter_001.pt").unlink()

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=1, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [2]


def test_resume_matching_run_id_extra_train_state_generation_proceeds(tmp_path) -> None:
    # A `train_state.prev.pt` left behind by the SAME run (same run_id) is
    # not foreign lineage -- it must not block the resume.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"
    prev_path = checkpoint_dir / "train_state.prev.pt"
    assert prev_path.exists(), "train_state_every=1 across 2 saved iterations should mint a .prev"
    (checkpoint_dir / "history.json").unlink()
    (checkpoint_dir / "iter_001.pt").unlink()
    (checkpoint_dir / "iter_002.pt").unlink()

    config_resumed = replace(config_first, iterations=3)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=1, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [3]


def test_resume_unreadable_foreign_train_state_generation_raises(tmp_path) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    train_b2b(env, model_config, champion_path, dir_a, config_first,
             base_seed=5, train_state_every=1)
    train_b2b(env, model_config, champion_path, dir_b, config_first,
             base_seed=5, train_state_every=1)

    state_from_a = dir_a / "train_state.pt"
    (dir_b / "history.json").unlink()
    (dir_b / "iter_001.pt").unlink()
    # B's own train_state.pt (the destination generation, NOT the file being
    # resumed from) is torn -- lineage can't be proven, so this must raise
    # rather than silently waving it through.
    (dir_b / "train_state.pt").write_bytes(b"torn foreign generation")

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match=r"(?i)train_state.pt.*unreadable"):
        train_b2b(env, model_config, champion_path, dir_b, config_resumed,
                 base_seed=5, train_state_every=1, resume_from_state=state_from_a)


def test_force_history_reset_overrides_train_state_lineage_check(tmp_path) -> None:
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    train_b2b(env, model_config, champion_path, dir_a, config_first,
             base_seed=5, train_state_every=1)
    train_b2b(env, model_config, champion_path, dir_b, config_first,
             base_seed=5, train_state_every=1)

    state_from_a = dir_a / "train_state.pt"
    (dir_b / "history.json").unlink()
    (dir_b / "iter_001.pt").unlink()

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, dir_b, config_resumed,
                        base_seed=5, train_state_every=1, resume_from_state=state_from_a,
                        force_history_reset=True)

    assert [row["iteration"] for row in history] == [2]


def test_fresh_launch_into_dir_with_only_train_state_prev_raises(tmp_path) -> None:
    # Regression guard: `_find_fresh_run_managed_artifacts` already treats
    # `train_state.prev.pt` as a managed artifact of THIS run (round 9), so
    # a fresh (non-resume) launch into a directory holding only it must
    # still fail closed, exactly like `train_state.pt` or `iter_*.pt` alone.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir(parents=True)
    torch.save({"run_id": "abc"}, checkpoint_dir / "train_state.prev.pt")

    with pytest.raises(ValueError, match="train_state.prev.pt"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_first, base_seed=7)


def test_history_json_write_fsyncs_tmp_and_directory(tmp_path, monkeypatch) -> None:
    """Cheap, same-failure-mode fix as train_state.pt: `_write_history_atomic`
    must fsync the tmp file's contents and the parent directory's entry
    table, not just `os.replace` blind."""
    from fh_mahjong_ai import ppo as ppo_module

    fsynced_fds: list[int] = []
    real_fsync = os.fsync

    def _tracking_fsync(fd):
        fsynced_fds.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(ppo_module.os, "fsync", _tracking_fsync)
    path = tmp_path / "history.json"
    ppo_module._write_history_atomic(path, [{"iteration": 1}])

    assert json.loads(path.read_text()) == [{"iteration": 1}]
    assert len(fsynced_fds) >= 2, "expected at least one fsync for the tmp file and one for the dir"


# --- Adversarial round 16, high finding: an unreadable Go bridge library
# silently became the mock sentinel (None, None) instead of a startup
# error -- a fresh bridge_kind="go" run whose library is missing/unreadable
# pinned (None, None) exactly like a genuine mock config, and
# `_verify_bridge_unchanged`'s `pinned_bridge_sha256 is None` guard then
# no-ops for the WHOLE run, silently disabling drift protection instead of
# refusing to start. ---

def test_resolve_current_bridge_fingerprint_go_missing_library_raises(tmp_path) -> None:
    from fh_mahjong_ai.train_state import _resolve_current_bridge_fingerprint

    missing = tmp_path / "does-not-exist.so"
    env = EnvConfig(bridge_kind="go", bridge_library_path=str(missing))

    with pytest.raises(OSError, match=re.escape(str(missing))):
        _resolve_current_bridge_fingerprint(env)


def test_go_bridge_missing_library_aborts_before_any_collection(tmp_path, monkeypatch) -> None:
    # A go-kind config whose library path does not exist must raise at
    # startup -- before pinning succeeds, before any rollout collection --
    # never silently degrade to the mock sentinel (None, None).
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=2)
    missing = tmp_path / "does-not-exist.so"
    env = replace(env, bridge_kind="go", bridge_library_path=str(missing))
    checkpoint_dir = tmp_path / "ckpt"

    collection_calls = {"n": 0}

    def counting_collect(*args, **kwargs):
        collection_calls["n"] += 1
        raise AssertionError("collection must never run")

    monkeypatch.setattr("fh_mahjong_ai.train_b2b.collect_b2b_rollouts", counting_collect)

    with pytest.raises(OSError, match=re.escape(str(missing))):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config, base_seed=5)

    assert collection_calls["n"] == 0
    assert not (checkpoint_dir / "train_state.pt").exists()
    assert not (checkpoint_dir / "iter_001.pt").exists()


def test_go_bridge_transient_read_failure_still_aborts_no_silent_recovery(tmp_path, monkeypatch) -> None:
    # A read failure that would succeed on a LATER attempt must still abort
    # the run -- there is no retry-then-silently-proceed-unpinned path. This
    # guards against a fix that catches OSError and just tries again (or
    # falls through to (None, None) after one failed attempt).
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-binary-v1")
    env = EnvConfig(bridge_kind="go", bridge_library_path=str(lib_path))

    from fh_mahjong_ai.train_state import _resolve_current_bridge_fingerprint

    real_read_bytes = Path.read_bytes
    calls = {"n": 0}

    def flaky_read_bytes(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(5, "Input/output error")
        return real_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", flaky_read_bytes)

    with pytest.raises(OSError):
        _resolve_current_bridge_fingerprint(env)

    # Exactly one read attempt was made -- no internal retry that would have
    # quietly succeeded and pinned a digest anyway.
    assert calls["n"] == 1


def test_go_bridge_mock_config_unaffected_no_drift_checks(tmp_path) -> None:
    # A genuinely non-Go (mock) config must still resolve to (None, None)
    # with no raise, and a full train_b2b run under it proceeds untouched.
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    from fh_mahjong_ai.train_state import _resolve_current_bridge_fingerprint
    assert _resolve_current_bridge_fingerprint(env) == (None, None)

    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config,
                        base_seed=5, train_state_every=1)
    assert [row["iteration"] for row in history] == [1]
    state = torch.load(checkpoint_dir / "train_state.pt", map_location="cpu", weights_only=False)
    assert state["bridge_sha256"] is None


def test_fresh_go_run_invariant_blocks_null_pinned_digest(tmp_path, monkeypatch) -> None:
    # Belt-and-braces: even if some future bug lets the bridge-snapshot
    # pinning primitive return a None digest for a bridge_kind="go" config,
    # train_b2b's own `_assert_bridge_pinned` invariant must catch it and
    # refuse to start training unpinned. Adversarial round 20 moved the
    # fresh-run pinning primitive from `_resolve_current_bridge_fingerprint`
    # to `_read_and_hash_bridge_source` (which reads once and copies the
    # verified bytes into a content-addressed snapshot) -- this patches the
    # new seam.
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=1)
    # bridge_library_path is never actually resolved -- _read_and_hash_
    # bridge_source is monkeypatched below -- so it need not exist.
    env = replace(env, bridge_kind="go", bridge_library_path=str(tmp_path / "unused.so"))
    checkpoint_dir = tmp_path / "ckpt"

    monkeypatch.setattr(
        "fh_mahjong_ai.train_state._read_and_hash_bridge_source",
        lambda source_path: (b"fake-bytes", None),
    )

    with pytest.raises(RuntimeError, match=r"unpinned"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config, base_seed=5)

    assert not (checkpoint_dir / "train_state.pt").exists()


def _legacy_go_state_setup(tmp_path: Path, monkeypatch):
    """Shared setup for the round-19 legacy-unpinned-state tests: a
    bridge_kind='go' run whose `train_state.pt` has been mutated to simulate
    a legacy save from before bridge identity pinning existed
    (bridge_sha256=None), with rollout collection transparently redirected to
    the mock bridge (there is no real dlopen-able .so in a unit test)."""
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-binary-v1")
    env = replace(env, bridge_kind="go", bridge_library_path=str(lib_path))
    checkpoint_dir = tmp_path / "ckpt"

    from fh_mahjong_ai import train_b2b as train_b2b_mod
    real_collect = train_b2b_mod.collect_b2b_rollouts

    def collect_via_mock(env_config_arg, model, cfg, base_seed):
        return real_collect(replace(env_config_arg, bridge_kind="mock"), model, cfg,
                            base_seed=base_seed)

    monkeypatch.setattr("fh_mahjong_ai.train_b2b.collect_b2b_rollouts", collect_via_mock)

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"
    state = torch.load(state_path, map_location="cpu", weights_only=False)
    # Simulate a legacy save: no bridge_sha256 recorded at all.
    state["bridge_sha256"] = None
    state["bridge_library_path"] = None
    torch.save(state, state_path)

    current_digest = hashlib.sha256(lib_path.read_bytes()).hexdigest()
    return env, model_config, champion_path, config_first, checkpoint_dir, state_path, current_digest


def test_resume_legacy_go_state_with_null_digest_raises_without_flag(tmp_path, monkeypatch) -> None:
    # Adversarial round 19, high finding: round 16 accepted a legacy
    # (bridge_sha256=None) state unconditionally and pinned None FOREVER --
    # permanently disabling drift detection for the rest of the run's life
    # instead of merely tolerating the one pre-existing gap. Fail closed by
    # default: resuming must raise, naming the explicit opt-in remedy.
    (env, model_config, champion_path, config_first, checkpoint_dir, state_path,
     _current_digest) = _legacy_go_state_setup(tmp_path, monkeypatch)

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match=r"--accept-legacy-unpinned-state"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=5, train_state_every=1, resume_from_state=state_path)

    # Nothing published for the rejected resume attempt.
    assert not (checkpoint_dir / "iter_002.pt").exists()


def test_resume_legacy_go_state_with_flag_establishes_new_provenance_boundary(
        tmp_path, monkeypatch, caplog) -> None:
    # WITH the explicit flag, the resume proceeds -- but instead of staying
    # unpinned forever (round 16's behavior), it establishes a NEW
    # provenance boundary: the digest the library CURRENTLY resolves to is
    # pinned as this lineage's baseline from this resume forward, so drift
    # detection resumes for iterations from here on.
    (env, model_config, champion_path, config_first, checkpoint_dir, state_path,
     current_digest) = _legacy_go_state_setup(tmp_path, monkeypatch)

    config_resumed = replace(config_first, iterations=2)
    with caplog.at_level(logging.WARNING):
        history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                            base_seed=5, train_state_every=1, resume_from_state=state_path,
                            accept_legacy_unpinned_state=True)

    assert [row["iteration"] for row in history] == [1, 2]
    assert any("legacy" in record.message.lower() and "boundary" in record.message.lower()
              for record in caplog.records)

    resumed_state = torch.load(state_path, map_location="cpu", weights_only=False)
    # The new boundary pins the CURRENT digest going forward -- never stays
    # None.
    assert resumed_state["bridge_sha256"] == current_digest

    # And having established that boundary, a further resume WITHOUT the
    # flag proceeds normally (the state is no longer unpinned) and a drift
    # check against the same, unchanged library still passes.
    config_extended = replace(config_first, iterations=3)
    history2 = train_b2b(env, model_config, champion_path, checkpoint_dir, config_extended,
                         base_seed=5, train_state_every=1, resume_from_state=state_path)
    assert [row["iteration"] for row in history2] == [1, 2, 3]


def test_accept_legacy_unpinned_state_flag_is_noop_for_mock_bridge(tmp_path) -> None:
    # Mock-bridge states never carry a real digest at all (bridge_kind !=
    # "go" always resolves to (None, None)) -- the legacy-unpinned-state
    # branch requires bridge_kind == "go" and must never fire for them,
    # whether or not the flag is passed.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=1,
                        resume_from_state=checkpoint_dir / "train_state.pt",
                        accept_legacy_unpinned_state=True)
    assert [row["iteration"] for row in history] == [1, 2]
    state = torch.load(checkpoint_dir / "train_state.pt", map_location="cpu", weights_only=False)
    assert state["bridge_sha256"] is None


# --- Adversarial round 19, high finding: stale future checkpoints visible
# during a --resume-from-state replay. Resume truncates history.json/the
# in-memory history back to start_iteration, but pre-round-19 left any
# iter_N.pt for N >= start_iteration sitting on disk, live, under the SAME
# run_id, until the replayed loop happened to overwrite it by name. CUDA
# replay is not bit-identical, so an old iter_N.pt from before the crash can
# diverge from the trajectory this resume actually replays -- concurrent
# screening/eval tooling, or a second crash mid-replay, could silently pick
# up that obsolete-trajectory checkpoint. ---

def _build_iter_001_through_005_then_rewind_to_state_at_2(tmp_path, monkeypatch):
    """Produces a checkpoint_dir with iter_001.pt..iter_005.pt all durably on
    disk and history.json covering iterations 1-5, then rewinds
    train_state.pt back to the iteration-2 snapshot (next_iteration=3) --
    simulating a crash where training had already progressed past iteration 2
    (leaving iter_003.pt..005.pt behind from that progress) before the box
    died and only the iter-2 state snapshot survived. Returns
    (env, model_config, champion_path, config2, checkpoint_dir, state_path)."""
    env, model_config, champion_path, config2 = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config2,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    state_at_2_bytes = state_path.read_bytes()

    config5 = replace(config2, iterations=5)
    train_b2b(env, model_config, champion_path, checkpoint_dir, config5,
             base_seed=5, train_state_every=5, resume_from_state=state_path)
    for i in range(1, 6):
        assert (checkpoint_dir / f"iter_{i:03d}.pt").exists()

    # Rewind: only the iteration-2 snapshot "survived the crash".
    state_path.write_bytes(state_at_2_bytes)
    return env, model_config, champion_path, config2, checkpoint_dir, state_path


def test_resume_quarantines_stale_future_checkpoints_before_first_collection(
        tmp_path, monkeypatch) -> None:
    (env, model_config, champion_path, config2, checkpoint_dir,
     state_path) = _build_iter_001_through_005_then_rewind_to_state_at_2(tmp_path, monkeypatch)

    from fh_mahjong_ai import train_b2b as train_b2b_mod
    real_collect = train_b2b_mod.collect_b2b_rollouts
    collection_calls = {"n": 0}
    observed: dict = {}

    def counting_collect(*args, **kwargs):
        if collection_calls["n"] == 0:
            observed["stale_present"] = [
                (checkpoint_dir / f"iter_{i:03d}.pt.stale").exists() for i in (3, 4, 5)
            ]
            observed["live_absent"] = [
                not (checkpoint_dir / f"iter_{i:03d}.pt").exists() for i in (3, 4, 5)
            ]
            observed["history_on_disk"] = [
                row["iteration"] for row in read_b2b_history_rows(checkpoint_dir / "history.json")
            ]
        collection_calls["n"] += 1
        return real_collect(*args, **kwargs)

    monkeypatch.setattr("fh_mahjong_ai.train_b2b.collect_b2b_rollouts", counting_collect)

    config5 = replace(config2, iterations=5)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config5,
                        base_seed=5, train_state_every=5, resume_from_state=state_path)

    # Quarantine (and the durable truncated-history write) happened entirely
    # before the FIRST collection call.
    assert observed["stale_present"] == [True, True, True]
    assert observed["live_absent"] == [True, True, True]
    assert observed["history_on_disk"] == [1, 2]

    # By the end of the run, the replayed iterations published fresh
    # checkpoints and each one's .stale sibling was removed.
    assert [row["iteration"] for row in history] == [1, 2, 3, 4, 5]
    for i in (3, 4, 5):
        assert (checkpoint_dir / f"iter_{i:03d}.pt").exists()
        assert not (checkpoint_dir / f"iter_{i:03d}.pt.stale").exists()
    history_on_disk = [row["iteration"] for row in
                       read_b2b_history_rows(checkpoint_dir / "history.json")]
    assert history_on_disk == [1, 2, 3, 4, 5]


def test_resume_sweeps_leftover_stale_checkpoints_at_completion(tmp_path, monkeypatch) -> None:
    # A resume whose --iterations target stops SHORT of some quarantined
    # iteration numbers (here: target 4, but iter_005.pt.stale was
    # quarantined at resume-start) must not leave that .stale file behind
    # forever -- it is swept at successful completion since this run is
    # ending without ever regenerating it.
    (env, model_config, champion_path, config2, checkpoint_dir,
     state_path) = _build_iter_001_through_005_then_rewind_to_state_at_2(tmp_path, monkeypatch)

    config4 = replace(config2, iterations=4)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config4,
                        base_seed=5, train_state_every=4, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [1, 2, 3, 4]
    assert (checkpoint_dir / "iter_003.pt").exists()
    assert (checkpoint_dir / "iter_004.pt").exists()
    # iter_005.pt was never regenerated this run (target stopped at 4) -- its
    # quarantined .stale sibling must be swept, not left behind, and the live
    # name must never reappear on its own.
    assert not (checkpoint_dir / "iter_005.pt.stale").exists()
    assert not (checkpoint_dir / "iter_005.pt").exists()


def test_lineage_scan_ignores_stale_quarantined_checkpoints(tmp_path) -> None:
    # A checkpoint already quarantined to `.stale` (by
    # `_quarantine_stale_future_checkpoints`) must never be inspected by the
    # artifact-lineage scanner -- it drops out of the `iter_*.pt` glob the
    # moment it is renamed, regardless of what run_id it carries.
    from fh_mahjong_ai.train_state import _check_artifact_lineage_or_raise

    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()
    model = PolicyValueNet(MOCK_ENV, b2b_model_config())
    live_path = checkpoint_dir / "iter_003.pt"
    save_checkpoint(live_path, model, metadata={"run_id": "foreign-run"})
    stale_path = live_path.with_name(live_path.name + ".stale")
    os.rename(live_path, stale_path)

    # Must not raise despite the quarantined file's foreign run_id -- it is
    # invisible to the scan.
    _check_artifact_lineage_or_raise(checkpoint_dir, state_run_id="this-run", next_iteration=3)


def test_fresh_run_overwrite_moves_leftover_stale_checkpoints_into_backup(tmp_path) -> None:
    # A leftover `.stale` file from an interrupted resume is a managed
    # artifact exactly like a live iter_*.pt -- --fresh-run-overwrite must
    # cover it too, not leave it behind as an untouched stray file.
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()
    model = PolicyValueNet(MOCK_ENV, model_config)
    stale_path = checkpoint_dir / "iter_003.pt.stale"
    save_checkpoint(checkpoint_dir / "iter_003.pt", model)
    os.rename(checkpoint_dir / "iter_003.pt", stale_path)

    found = _find_fresh_run_managed_artifacts(checkpoint_dir)
    assert stale_path in found

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=9, fresh_run_overwrite=True, train_state_every=1)

    assert not stale_path.exists()


# --- Adversarial round 20, high finding: bridge digest not bound to loaded
# bytes (ABA). Round 13-19 pinned/verified a sha256 of the bridge library
# PATH, but workers independently `dlopen` that same mutable path later --
# a swap-and-restore between "hash" and "load" defeats every check, and
# parallel workers can even load DIFFERENT binaries from each other. The
# fix: at run start (fresh or resume), the verified library bytes are
# copied into a run-owned, content-addressed snapshot
# `<checkpoint_dir>/.bridge-<sha256-prefix16>.so`, and the `EnvConfig`
# threaded into every rollout collector (`collect_b2b_rollouts` /
# `ParallelB2bCollector`) is rebound to that snapshot path via
# `dataclasses.replace` -- so every worker loads the immutable snapshot,
# never the mutable source path, and per-iteration drift checks verify the
# SNAPSHOT (which nothing legitimate ever touches) instead of the source.
#
# These tests use `bridge_kind="go"` with a real (fabricated-content) file
# standing in for the `.so` -- `build_bridge` is monkeypatched so
# `collect_b2b_rollouts` never actually tries to `dlopen` the fake bytes
# (real Go-bridge dlopen tests are infeasible on this machine, which has no
# built `.so`); everything under test here -- the snapshot's existence and
# content, the `EnvConfig.bridge_library_path` actually threaded into
# collection, and the digest comparisons -- is provable without loading a
# real library.

def _fake_build_bridge_factory(calls: list):
    """Records every `EnvConfig` `collect_b2b_rollouts` builds a bridge
    from, then returns an ordinary mock bridge (bridge_kind is irrelevant to
    `MockMahjongBridge`) so collection proceeds without touching ctypes."""
    from fh_mahjong_ai.bridge import MockMahjongBridge

    def fake_build_bridge(cfg):
        calls.append(cfg)
        return MockMahjongBridge(cfg)

    return fake_build_bridge


def _go_bridge_run_configs(tmp_path: Path, *, iterations: int, lib_path: Path):
    _, champion_path = save_champion39(tmp_path)
    env = EnvConfig(bridge_kind="go", bridge_library_path=str(lib_path),
                    event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    model_config = b2b_model_config()
    config = PPOConfig(device="cpu", iterations=iterations, matches_per_iter=2, lr=2e-5,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="classic")
    return env, model_config, champion_path, config


def test_fresh_run_snapshots_bridge_and_threads_snapshot_into_collection(tmp_path, monkeypatch) -> None:
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-binary-v1")
    source_digest = hashlib.sha256(b"go-bridge-binary-v1").hexdigest()
    env, model_config, champion_path, config = _go_bridge_run_configs(
        tmp_path, iterations=1, lib_path=lib_path)
    checkpoint_dir = tmp_path / "ckpt"

    calls: list = []
    monkeypatch.setattr("fh_mahjong_ai.train_b2b.build_bridge", _fake_build_bridge_factory(calls))

    train_b2b(env, model_config, champion_path, checkpoint_dir, config,
             base_seed=5, train_state_every=1)

    snapshot_path = checkpoint_dir / f".bridge-{source_digest[:16]}.so"
    assert snapshot_path.exists()
    assert snapshot_path.read_bytes() == b"go-bridge-binary-v1"

    # The bridge was built from a config pointing at the SNAPSHOT, never the
    # mutable source path -- this is the config-threading half of the fix.
    assert len(calls) == 1
    assert calls[0].bridge_library_path == str(snapshot_path)
    assert calls[0].bridge_library_path != str(lib_path)

    state = torch.load(checkpoint_dir / "train_state.pt", map_location="cpu", weights_only=False)
    assert state["bridge_sha256"] == source_digest


def test_source_swap_mid_run_neither_aborts_nor_changes_snapshot_digest(tmp_path, monkeypatch) -> None:
    # The ABA regression itself: a swap-and-restore (or here, just a swap)
    # of the SOURCE path between iterations must not be observable by the
    # run at all -- it is bound to the snapshot, not the source.
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-binary-v1")
    source_digest = hashlib.sha256(b"go-bridge-binary-v1").hexdigest()
    env, model_config, champion_path, config = _go_bridge_run_configs(
        tmp_path, iterations=2, lib_path=lib_path)
    checkpoint_dir = tmp_path / "ckpt"

    calls: list = []
    monkeypatch.setattr("fh_mahjong_ai.train_b2b.build_bridge", _fake_build_bridge_factory(calls))

    real_save_checkpoint = save_checkpoint
    state = {"n": 0}

    def swapping_save_checkpoint(*args, **kwargs):
        real_save_checkpoint(*args, **kwargs)
        state["n"] += 1
        if state["n"] == 1:
            # Fires right after iteration 1's checkpoint lands, strictly
            # between its post-update drift check and iteration 2's
            # pre-collection drift check -- the swap happens truly mid-run.
            lib_path.write_bytes(b"go-bridge-binary-v2-SWAPPED")

    monkeypatch.setattr("fh_mahjong_ai.train_b2b.save_checkpoint", swapping_save_checkpoint)

    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config,
                        base_seed=5, train_state_every=1)

    assert [row["iteration"] for row in history] == [1, 2]
    snapshot_path = checkpoint_dir / f".bridge-{source_digest[:16]}.so"
    assert snapshot_path.read_bytes() == b"go-bridge-binary-v1"
    assert all(c.bridge_library_path == str(snapshot_path) for c in calls)


def test_mutated_snapshot_aborts_at_next_check(tmp_path, monkeypatch) -> None:
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-binary-v1")
    source_digest = hashlib.sha256(b"go-bridge-binary-v1").hexdigest()
    env, model_config, champion_path, config = _go_bridge_run_configs(
        tmp_path, iterations=2, lib_path=lib_path)
    checkpoint_dir = tmp_path / "ckpt"

    calls: list = []
    monkeypatch.setattr("fh_mahjong_ai.train_b2b.build_bridge", _fake_build_bridge_factory(calls))

    real_save_checkpoint = save_checkpoint
    state = {"n": 0}
    snapshot_path = checkpoint_dir / f".bridge-{source_digest[:16]}.so"

    def tampering_save_checkpoint(*args, **kwargs):
        real_save_checkpoint(*args, **kwargs)
        state["n"] += 1
        if state["n"] == 1:
            # Tamper with the snapshot itself (not the source) -- nothing
            # legitimate ever does this, so it must abort the run.
            snapshot_path.write_bytes(b"TAMPERED")

    monkeypatch.setattr("fh_mahjong_ai.train_b2b.save_checkpoint", tampering_save_checkpoint)

    with pytest.raises(ValueError, match="bridge library drift detected mid-run"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config,
                 base_seed=5, train_state_every=1)


def test_bridge_snapshot_recreated_on_resume_when_missing_and_source_intact(tmp_path, monkeypatch) -> None:
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-binary-v1")
    source_digest = hashlib.sha256(b"go-bridge-binary-v1").hexdigest()
    env, model_config, champion_path, config_first = _go_bridge_run_configs(
        tmp_path, iterations=1, lib_path=lib_path)
    checkpoint_dir = tmp_path / "ckpt"

    calls: list = []
    monkeypatch.setattr("fh_mahjong_ai.train_b2b.build_bridge", _fake_build_bridge_factory(calls))

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)

    snapshot_path = checkpoint_dir / f".bridge-{source_digest[:16]}.so"
    assert snapshot_path.exists()
    snapshot_path.unlink()  # simulate the snapshot being lost

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, resume_from_state=checkpoint_dir / "train_state.pt")

    assert [row["iteration"] for row in history] == [1, 2]
    assert snapshot_path.exists()
    assert snapshot_path.read_bytes() == b"go-bridge-binary-v1"


def test_bridge_snapshot_missing_and_source_drifted_raises_without_override(tmp_path, monkeypatch) -> None:
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-binary-v1")
    source_digest = hashlib.sha256(b"go-bridge-binary-v1").hexdigest()
    env, model_config, champion_path, config_first = _go_bridge_run_configs(
        tmp_path, iterations=1, lib_path=lib_path)
    checkpoint_dir = tmp_path / "ckpt"

    calls: list = []
    monkeypatch.setattr("fh_mahjong_ai.train_b2b.build_bridge", _fake_build_bridge_factory(calls))

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)

    snapshot_path = checkpoint_dir / f".bridge-{source_digest[:16]}.so"
    snapshot_path.unlink()
    lib_path.write_bytes(b"go-bridge-binary-v2-REBUILT")  # source rebuilt

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="bridge library mismatch"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=5, resume_from_state=checkpoint_dir / "train_state.pt")

    assert not snapshot_path.exists()


def test_bridge_snapshot_missing_and_source_drifted_allow_mismatch_rebinds(tmp_path, monkeypatch) -> None:
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-binary-v1")
    source_digest_v1 = hashlib.sha256(b"go-bridge-binary-v1").hexdigest()
    env, model_config, champion_path, config_first = _go_bridge_run_configs(
        tmp_path, iterations=1, lib_path=lib_path)
    checkpoint_dir = tmp_path / "ckpt"

    calls: list = []
    monkeypatch.setattr("fh_mahjong_ai.train_b2b.build_bridge", _fake_build_bridge_factory(calls))

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)

    snapshot_v1_path = checkpoint_dir / f".bridge-{source_digest_v1[:16]}.so"
    snapshot_v1_path.unlink()
    lib_path.write_bytes(b"go-bridge-binary-v2-REBUILT")
    source_digest_v2 = hashlib.sha256(b"go-bridge-binary-v2-REBUILT").hexdigest()

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, resume_from_state=checkpoint_dir / "train_state.pt",
                        allow_bridge_mismatch=True)

    assert [row["iteration"] for row in history] == [1, 2]
    snapshot_v2_path = checkpoint_dir / f".bridge-{source_digest_v2[:16]}.so"
    assert snapshot_v2_path.exists()
    assert snapshot_v2_path.read_bytes() == b"go-bridge-binary-v2-REBUILT"
    assert any(c.bridge_library_path == str(snapshot_v2_path) for c in calls)

    state = torch.load(checkpoint_dir / "train_state.pt", map_location="cpu", weights_only=False)
    assert state["bridge_sha256"] == source_digest_v2


def test_bridge_snapshot_is_a_managed_artifact(tmp_path) -> None:
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()
    snapshot_path = checkpoint_dir / ".bridge-0123456789abcdef.so"
    snapshot_path.write_bytes(b"snapshot-bytes")

    found = _find_fresh_run_managed_artifacts(checkpoint_dir)
    assert snapshot_path in found


# Adversarial round 21, high finding: a resume used to fingerprint the
# MUTABLE source before ever consulting the pinned, content-addressed
# snapshot -- so a deleted or rebuilt source bricked resume (raise on read)
# even when the pinned snapshot bytes sat intact in checkpoint_dir, and
# --allow-bridge-mismatch could not help because the source read failed
# first. The fix is snapshot-first ordering: locate the snapshot named by
# the SAVED digest, verify it, and bind to it WITHOUT ever touching the
# source when it is present and intact; the source is only consulted when
# the snapshot is absent (round 20's existing fallback rules).

def test_resume_proceeds_bound_to_snapshot_when_source_deleted(tmp_path, monkeypatch) -> None:
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-binary-v1")
    source_digest = hashlib.sha256(b"go-bridge-binary-v1").hexdigest()
    env, model_config, champion_path, config_first = _go_bridge_run_configs(
        tmp_path, iterations=1, lib_path=lib_path)
    checkpoint_dir = tmp_path / "ckpt"

    calls: list = []
    monkeypatch.setattr("fh_mahjong_ai.train_b2b.build_bridge", _fake_build_bridge_factory(calls))

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)

    snapshot_path = checkpoint_dir / f".bridge-{source_digest[:16]}.so"
    assert snapshot_path.exists()
    lib_path.unlink()  # the source is gone entirely -- reading it would raise OSError

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, resume_from_state=checkpoint_dir / "train_state.pt")

    assert [row["iteration"] for row in history] == [1, 2]
    assert all(c.bridge_library_path == str(snapshot_path) for c in calls)
    state = torch.load(checkpoint_dir / "train_state.pt", map_location="cpu", weights_only=False)
    assert state["bridge_sha256"] == source_digest


def test_resume_proceeds_bound_to_snapshot_when_source_rebuilt(tmp_path, monkeypatch) -> None:
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-binary-v1")
    source_digest = hashlib.sha256(b"go-bridge-binary-v1").hexdigest()
    env, model_config, champion_path, config_first = _go_bridge_run_configs(
        tmp_path, iterations=1, lib_path=lib_path)
    checkpoint_dir = tmp_path / "ckpt"

    calls: list = []
    monkeypatch.setattr("fh_mahjong_ai.train_b2b.build_bridge", _fake_build_bridge_factory(calls))

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)

    snapshot_path = checkpoint_dir / f".bridge-{source_digest[:16]}.so"
    assert snapshot_path.exists()
    # Source rebuilt to DIFFERENT bytes -- with the snapshot intact this must
    # be silently ignored: no raise, no --allow-bridge-mismatch needed, and
    # the snapshot's own bytes/digest must not change.
    lib_path.write_bytes(b"go-bridge-binary-v2-REBUILT")

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, resume_from_state=checkpoint_dir / "train_state.pt")

    assert [row["iteration"] for row in history] == [1, 2]
    assert all(c.bridge_library_path == str(snapshot_path) for c in calls)
    assert snapshot_path.read_bytes() == b"go-bridge-binary-v1"
    state = torch.load(checkpoint_dir / "train_state.pt", map_location="cpu", weights_only=False)
    assert state["bridge_sha256"] == source_digest


def test_resume_raises_when_snapshot_is_corrupted(tmp_path, monkeypatch) -> None:
    lib_path = tmp_path / "libfh_mahjong_bridge.so"
    lib_path.write_bytes(b"go-bridge-binary-v1")
    source_digest = hashlib.sha256(b"go-bridge-binary-v1").hexdigest()
    env, model_config, champion_path, config_first = _go_bridge_run_configs(
        tmp_path, iterations=1, lib_path=lib_path)
    checkpoint_dir = tmp_path / "ckpt"

    calls: list = []
    monkeypatch.setattr("fh_mahjong_ai.train_b2b.build_bridge", _fake_build_bridge_factory(calls))

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)

    snapshot_path = checkpoint_dir / f".bridge-{source_digest[:16]}.so"
    assert snapshot_path.exists()
    # Corrupt the snapshot in place -- its content-addressed name still
    # claims `source_digest`, but the bytes no longer hash to it. This must
    # raise (tampering/corruption), never silently fall back to the source
    # (which is still intact and would otherwise mask the corruption).
    snapshot_path.write_bytes(b"TAMPERED-SNAPSHOT-BYTES")

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="corrupt"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=5, resume_from_state=checkpoint_dir / "train_state.pt")


def test_resume_rejects_changed_placement_bonus(tmp_path) -> None:
    from fh_mahjong_ai.placement_bonus import PLACEMENT_RESHAPE_VALUES
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    # The bonus fields are RECIPE, not operational: any change must be rejected.
    changed = replace(config_first, iterations=4,
                      placement_bonus_values=PLACEMENT_RESHAPE_VALUES, placement_bonus_lambda=0.3)
    with pytest.raises(ValueError, match="placement_bonus"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, changed,
                 base_seed=5, resume_from_state=state_path)


def test_legacy_state_without_bonus_fields_normalizes() -> None:
    from fh_mahjong_ai.train_state import _LEGACY_ECHO_ADDITIONS
    assert {"placement_bonus_values", "placement_bonus_lambda",
            "placement_bonus_calibration_digest"} <= _LEGACY_ECHO_ADDITIONS["ppo_config"]

"""Batched B2b assembly releases each row as it is copied, so the RolloutBatch
build never holds the rows and the full output at once."""

import gc
import weakref

import numpy as np
import pytest
import torch

from conftest import SMALL_MODEL
from fh_mahjong_ai import batched_b2b as batched_b2b_module
from fh_mahjong_ai.batched_b2b import _stack_releasing, collect_b2b_rollouts_batched, make_b2b_pool
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig


@pytest.mark.parametrize("dtype,shape", [(np.float32, (51, 42, 1)), (np.int8, (204,)),
                                         (np.uint32, (8,))])
def test_stack_releasing_matches_np_stack(monkeypatch, dtype, shape):
    monkeypatch.setattr(batched_b2b_module, "_STACK_CHUNK_ROWS", 7)  # chunks cross row counts
    rng = np.random.default_rng(0)
    rows = [rng.integers(0, 100, size=shape).astype(dtype) for _ in range(53)]
    expected = np.stack(rows).astype(dtype, copy=False)
    out = _stack_releasing(rows, dtype)
    assert out.dtype == expected.dtype and out.shape == expected.shape
    assert out.tobytes() == expected.tobytes()
    assert rows == []


def test_stack_releasing_frees_every_source_row(monkeypatch):
    monkeypatch.setattr(batched_b2b_module, "_STACK_CHUNK_ROWS", 5)
    rows = [np.full((4, 3), i, dtype=np.float32) for i in range(23)]
    refs = [weakref.ref(r) for r in rows]
    out = _stack_releasing(rows, np.float32)
    gc.collect()
    assert all(ref() is None for ref in refs)
    assert out[22, 0, 0] == 22.0


@pytest.mark.skipif(not __import__("os").environ.get("FH_MAHJONG_BRIDGE_LIB"),
                    reason="needs the Go bridge library")
def test_collector_stores_rows_that_own_their_memory(monkeypatch):
    # A stored row that is a view into its round's shared array pins that whole
    # array until every row of the round is released, so the release-as-copied
    # assembly would free nothing. Every row reaching assembly must own its data.
    seen = {}
    real = batched_b2b_module._stack_releasing

    def spy(rows, dtype):
        key = str(np.dtype(dtype)) + str(np.asarray(rows[0]).shape)
        seen[key] = all(np.asarray(r).base is None for r in rows)
        return real(rows, dtype)

    monkeypatch.setattr(batched_b2b_module, "_stack_releasing", spy)
    env = EnvConfig(bridge_kind="go", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=4000)
    torch.manual_seed(0)
    model = PolicyValueNet(EnvConfig(bridge_kind="go"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    cfg = PPOConfig(device="cpu", matches_per_iter=2, max_steps_per_episode=4000,
                    match_mode="chongci")
    pool = make_b2b_pool(env, model, cfg, 2)
    try:
        batch = collect_b2b_rollouts_batched(env, model, cfg, base_seed=77, pool=pool,
                                             action_selection="greedy")
    finally:
        pool.close()
    assert len(seen) == 4 and all(seen.values()), seen
    assert batch.planes.shape[0] == batch.actions.shape[0] > 0

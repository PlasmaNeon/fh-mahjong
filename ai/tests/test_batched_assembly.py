"""Batched B2b assembly never holds the rows and the full output at once: each
match's rows are stacked into contiguous arrays when it finishes, and the final
build fills from those arrays, releasing each as it is copied."""

import gc
import os
import weakref

import numpy as np
import pytest
import torch

from conftest import SMALL_MODEL
from fh_mahjong_ai import batched_b2b as batched_b2b_module
from fh_mahjong_ai.batched_b2b import _concat_releasing, collect_b2b_rollouts_batched, make_b2b_pool
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig


@pytest.mark.parametrize("dtype,shape", [(np.float32, (51, 42, 1)), (np.int8, (204,)),
                                         (np.uint32, (8,))])
def test_concat_releasing_matches_np_concatenate(dtype, shape):
    rng = np.random.default_rng(0)
    parts = [rng.integers(0, 100, size=(n,) + shape).astype(dtype) for n in (1, 7, 30, 2)]
    expected = np.concatenate(parts).astype(dtype, copy=False)
    out = _concat_releasing(parts, dtype)
    assert out.dtype == expected.dtype and out.shape == expected.shape
    assert out.tobytes() == expected.tobytes()
    assert parts == []


def test_concat_releasing_frees_every_part():
    parts = [np.full((i + 1, 3), i, dtype=np.float32) for i in range(9)]
    refs = [weakref.ref(p) for p in parts]
    out = _concat_releasing(parts, np.float32)
    gc.collect()
    assert all(ref() is None for ref in refs)
    assert out[-1, 0] == 8.0 and out.shape == (45, 3)


@pytest.mark.skipif(not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library")
def test_assembly_parts_are_contiguous_per_match_arrays(monkeypatch):
    # Parts that were views into the collector's per-round arrays would pin
    # those rounds through assembly; every part must own its memory.
    seen = {}
    real = batched_b2b_module._concat_releasing

    def spy(parts, dtype):
        key = str(np.dtype(dtype)) + str(parts[0].shape[1:])
        seen[key] = (len(parts), all(isinstance(p, np.ndarray) and p.base is None for p in parts))
        return real(parts, dtype)

    monkeypatch.setattr(batched_b2b_module, "_concat_releasing", spy)
    env = EnvConfig(bridge_kind="go", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=4000)
    torch.manual_seed(0)
    model = PolicyValueNet(EnvConfig(bridge_kind="go"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    cfg = PPOConfig(device="cpu", matches_per_iter=3, max_steps_per_episode=4000,
                    match_mode="chongci")
    pool = make_b2b_pool(env, model, cfg, 2)
    try:
        batch = collect_b2b_rollouts_batched(env, model, cfg, base_seed=77, pool=pool,
                                             action_selection="greedy")
    finally:
        pool.close()
    assert len(seen) == 4, seen
    assert all(n == 3 and owned for n, owned in seen.values()), seen
    assert batch.planes.shape[0] == batch.actions.shape[0] > 0


class _FakeLibc:
    def __init__(self):
        self.calls = []

    def mallopt(self, param, value):
        self.calls.append((param, value))
        return 1


def test_mmap_threshold_pin_is_a_noop_off_linux(monkeypatch):
    monkeypatch.setattr(batched_b2b_module, "_mmap_threshold_pinned", False)
    monkeypatch.setattr(batched_b2b_module.sys, "platform", "darwin")
    called = []
    monkeypatch.setattr(batched_b2b_module.ctypes, "CDLL", lambda name: called.append(name))
    assert batched_b2b_module.pin_malloc_mmap_threshold() is False
    assert called == []


def test_mmap_threshold_pin_calls_mallopt_once_on_linux(monkeypatch):
    fake = _FakeLibc()
    monkeypatch.setattr(batched_b2b_module, "_mmap_threshold_pinned", False)
    monkeypatch.setattr(batched_b2b_module.sys, "platform", "linux")
    monkeypatch.setattr(batched_b2b_module.ctypes, "CDLL", lambda name: fake)
    assert batched_b2b_module.pin_malloc_mmap_threshold() is True
    assert batched_b2b_module.pin_malloc_mmap_threshold() is True
    assert fake.calls == [(-3, 128 * 1024)]


def test_mmap_threshold_pin_survives_missing_glibc(monkeypatch):
    def no_libc(name):
        raise OSError("not glibc")

    monkeypatch.setattr(batched_b2b_module, "_mmap_threshold_pinned", False)
    monkeypatch.setattr(batched_b2b_module.sys, "platform", "linux")
    monkeypatch.setattr(batched_b2b_module.ctypes, "CDLL", no_libc)
    assert batched_b2b_module.pin_malloc_mmap_threshold() is False

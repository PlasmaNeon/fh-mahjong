"""Batched B2b assembly writes each emitted match once, at its final offset, into
lazily committed batch buffers, so it never holds the rows and the batch at once."""

import mmap
import os

import numpy as np
import pytest
import torch

from conftest import SMALL_MODEL
from fh_mahjong_ai import batched_b2b as batched_b2b_module
from fh_mahjong_ai.batched_b2b import (
    _ArrayRowSink, _lazy_empty, collect_b2b_rollouts_batched, make_b2b_pool,
)
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig


def _match(rng, n):
    return {
        "actions": list(range(n)),
        "planes": [rng.random((51, 42, 1), dtype=np.float32) for _ in range(n)],
        "scalars": [rng.random(58, dtype=np.float32) for _ in range(n)],
        "masks": [rng.integers(0, 2, 204).astype(np.int8) for _ in range(n)],
        "events": [rng.integers(0, 2**31, 8).astype(np.uint32) for _ in range(n)],
    }


def test_sink_matches_stacking_every_row_in_emission_order():
    rng = np.random.default_rng(0)
    matches = [_match(rng, n) for n in (3, 1, 7, 0, 5)]
    sink = _ArrayRowSink(capacity=100)
    for m in matches:
        sink.write(m)
    arrays = sink.arrays()
    for key, dtype in (("planes", np.float32), ("scalars", np.float32),
                       ("masks", np.int8), ("events", np.uint32)):
        expected = np.stack([row for m in matches for row in m[key]]).astype(dtype)
        assert arrays[key].dtype == expected.dtype
        assert arrays[key].tobytes() == expected.tobytes()
        assert arrays[key].flags["C_CONTIGUOUS"]
    assert sink.rows == 16


def test_sink_refuses_to_overflow_its_capacity():
    rng = np.random.default_rng(1)
    sink = _ArrayRowSink(capacity=4)
    sink.write(_match(rng, 3))
    with pytest.raises(RuntimeError, match="exceed the sink capacity"):
        sink.write(_match(rng, 2))


def test_sink_refuses_ragged_match_rows():
    rng = np.random.default_rng(2)
    bad = _match(rng, 3)
    bad["events"] = bad["events"][:2]
    with pytest.raises(RuntimeError, match="events rows"):
        _ArrayRowSink(capacity=10).write(bad)


def test_lazy_empty_uses_a_noreserve_mapping_when_available(monkeypatch):
    # macOS has no MAP_NORESERVE; a zero flag exercises the Linux code path.
    monkeypatch.setattr(mmap, "MAP_NORESERVE", 0, raising=False)
    a = _lazy_empty((6, 5, 2), np.uint32)
    assert isinstance(a.base, (memoryview, mmap.mmap)) or a.base is not None
    assert a.shape == (6, 5, 2) and a.dtype == np.uint32 and a.flags["WRITEABLE"]
    a[:] = 7
    assert int(a.sum()) == 7 * 60


def test_lazy_empty_falls_back_when_the_mapping_is_refused(monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError("Cannot allocate memory")

    monkeypatch.setattr(mmap, "MAP_NORESERVE", 0, raising=False)
    monkeypatch.setattr(mmap, "mmap", refuse)
    a = _lazy_empty((4, 3), np.float32)
    assert a.shape == (4, 3) and a.dtype == np.float32 and a.base is None


def test_batch_arrays_keep_their_mapping_alive_and_pickle_only_written_rows(monkeypatch):
    import gc
    import pickle

    monkeypatch.setattr(mmap, "MAP_NORESERVE", 0, raising=False)
    rng = np.random.default_rng(3)
    match = _match(rng, 3)
    expected = np.stack(match["planes"])
    sink = _ArrayRowSink(capacity=10_000)
    sink.write(match)
    planes = sink.arrays()["planes"]
    del sink
    gc.collect()
    assert planes.tobytes() == expected.tobytes()  # the mapping outlives the sink
    assert len(pickle.dumps(planes)) < 2 * expected.nbytes  # no uncommitted tail


class _FakeLibc:
    def __init__(self):
        self.trims = 0

    def malloc_trim(self, pad):
        assert pad == 0
        self.trims += 1
        return 1


def test_release_freed_heap_is_a_noop_off_linux(monkeypatch):
    monkeypatch.setattr(batched_b2b_module, "_libc", None)
    monkeypatch.setattr(batched_b2b_module.sys, "platform", "darwin")
    called = []
    monkeypatch.setattr(batched_b2b_module.ctypes, "CDLL", lambda name: called.append(name))
    assert batched_b2b_module.release_freed_heap() is False
    assert called == []


def test_release_freed_heap_trims_on_linux(monkeypatch):
    fake = _FakeLibc()
    monkeypatch.setattr(batched_b2b_module, "_libc", fake)
    monkeypatch.setattr(batched_b2b_module.sys, "platform", "linux")
    assert batched_b2b_module.release_freed_heap() is True
    assert fake.trims == 1


def test_release_freed_heap_survives_missing_glibc(monkeypatch):
    def no_libc(name):
        raise OSError("not glibc")

    monkeypatch.setattr(batched_b2b_module, "_libc", None)
    monkeypatch.setattr(batched_b2b_module.sys, "platform", "linux")
    monkeypatch.setattr(batched_b2b_module.ctypes, "CDLL", no_libc)
    assert batched_b2b_module.release_freed_heap() is False


@pytest.mark.skipif(not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library")
def test_collector_batch_is_the_written_prefix_of_the_sink(monkeypatch):
    sinks = []
    real = batched_b2b_module._ArrayRowSink

    class Recording(real):
        def __init__(self, capacity, *args):
            super().__init__(capacity, *args)
            sinks.append(self)

    monkeypatch.setattr(batched_b2b_module, "_ArrayRowSink", Recording)
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
    (sink,) = sinks
    assert sink.capacity == 3 * 4000
    assert batch.planes.shape[0] == batch.actions.shape[0] == sink.rows > 0
    assert np.shares_memory(batch.planes, sink.buffers["planes"])
    assert batch.events.shape == (sink.rows, 8)

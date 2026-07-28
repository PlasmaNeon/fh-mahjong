"""Tests for fh_mahjong_ai.fdlimit (errno-24 robustness for multi-worker laps)."""

import resource

import pytest

from fh_mahjong_ai import fdlimit


def test_raises_soft_limit_to_hard(monkeypatch):
    calls = {}

    def fake_getrlimit(which):
        assert which == resource.RLIMIT_NOFILE
        return (1024, 65536)

    def fake_setrlimit(which, limits):
        assert which == resource.RLIMIT_NOFILE
        calls["limits"] = limits

    monkeypatch.setattr(fdlimit.resource, "getrlimit", fake_getrlimit)
    monkeypatch.setattr(fdlimit.resource, "setrlimit", fake_setrlimit)
    logs = []
    result = fdlimit.raise_file_descriptor_limit(log=logs.append)
    assert result == (1024, 65536)
    assert calls["limits"] == (65536, 65536)
    assert any("1024 -> 65536" in line for line in logs)


def test_noop_when_already_at_hard_limit(monkeypatch):
    monkeypatch.setattr(fdlimit.resource, "getrlimit", lambda _: (65536, 65536))

    def boom(*_args):
        raise AssertionError("setrlimit must not be called")

    monkeypatch.setattr(fdlimit.resource, "setrlimit", boom)
    assert fdlimit.raise_file_descriptor_limit(log=None) == (65536, 65536)


def test_infinite_hard_limit_targets_finite_value(monkeypatch):
    monkeypatch.setattr(
        fdlimit.resource, "getrlimit", lambda _: (1024, resource.RLIM_INFINITY)
    )
    calls = {}
    monkeypatch.setattr(
        fdlimit.resource,
        "setrlimit",
        lambda _which, limits: calls.setdefault("limits", limits),
    )
    result = fdlimit.raise_file_descriptor_limit(log=None)
    assert result == (1024, 65535)
    assert calls["limits"] == (65535, resource.RLIM_INFINITY)


def test_setrlimit_failure_logs_and_returns_old(monkeypatch):
    monkeypatch.setattr(fdlimit.resource, "getrlimit", lambda _: (1024, 65536))

    def denied(*_args):
        raise ValueError("not permitted")

    monkeypatch.setattr(fdlimit.resource, "setrlimit", denied)
    logs = []
    result = fdlimit.raise_file_descriptor_limit(log=logs.append)
    assert result == (1024, 1024)
    assert any("could not raise" in line for line in logs)


def test_real_call_never_raises_and_reports_current_limits():
    # Against the real OS: must not raise, and must return a sane pair.
    result = fdlimit.raise_file_descriptor_limit(log=None)
    assert result is not None
    old, new = result
    assert new >= old > 0


@pytest.mark.parametrize("entry", ["collect_bench", "train_b2b"])
def test_cli_entry_points_call_fdlimit(entry, monkeypatch):
    # The scripts must invoke the helper at startup; pin by import reference.
    import fh_mahjong_ai.scripts.collect_bench as cb
    import fh_mahjong_ai.scripts.train_b2b as tb

    module = {"collect_bench": cb, "train_b2b": tb}[entry]
    assert module.raise_file_descriptor_limit is fdlimit.raise_file_descriptor_limit

"""Measurement-only memory checkpoint probes (data-scale-960 Amendment 4).

The 2026-08-14 consult authorized a memory PROFILE of the unchanged
collection + update path before any copy-elimination engineering: the
960-match preflight master reached 33.8GiB anon-RSS (~3x a single copy of
the dataset), so the ruling requires measuring which intermediate copies
dominate — chunk-list accumulation, concat outputs, GAE arrays, dtype
conversions — rather than rewriting on hypothesis.

This module is that instrumentation's seam. Production code paths call
``probe("label", **info)`` at memory-relevant checkpoints; with no probe
installed (the default, and the only configuration outside
``fh-mj-collect-profile``) the call is a single global read and None
comparison — it never touches, copies, or reshapes data, so instrumented
paths remain byte-identical to uninstrumented ones (pinned by
test_collect_profile's parity test).

``rss_snapshot()`` is the driver-side measurement helper: master
VmRSS/VmHWM, smaps_rollup PSS, summed descendant RSS, and cgroup-v2
memory.current/memory.peak where each exists (absent sources report None
rather than failing — macOS dev boxes have none of /proc).
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

_probe_fn: Optional[Callable[[str, Dict[str, Any]], None]] = None


def set_memory_probe(fn: Optional[Callable[[str, Dict[str, Any]], None]]) -> None:
    """Install (or clear, with None) the process-global probe callback."""
    global _probe_fn
    _probe_fn = fn


def probe(label: str, **info: Any) -> None:
    fn = _probe_fn
    if fn is not None:
        fn(label, info)


def _read_status_kb(pid: int, keys: tuple) -> Dict[str, Optional[int]]:
    out: Dict[str, Optional[int]] = {k: None for k in keys}
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                for k in keys:
                    if line.startswith(k + ":"):
                        out[k] = int(line.split()[1]) * 1024  # kB -> bytes
    except (OSError, ValueError, IndexError):
        pass
    return out


def _descendant_pids(root_pid: int) -> list:
    out: list = []
    stack = [root_pid]
    while stack:
        pid = stack.pop()
        task_dir = f"/proc/{pid}/task"
        try:
            tids = os.listdir(task_dir)
        except OSError:
            continue
        for tid in tids:
            try:
                with open(f"{task_dir}/{tid}/children") as f:
                    children = [int(c) for c in f.read().split()]
            except (OSError, ValueError):
                continue
            out.extend(children)
            stack.extend(children)
    return out


def _pss_bytes(pid: int) -> Optional[int]:
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _cgroup_memory() -> Dict[str, Optional[int]]:
    current = peak = None
    try:
        with open("/proc/self/cgroup") as f:
            for line in f:
                parts = line.strip().split(":", 2)
                if len(parts) == 3 and parts[0] == "0":
                    base = "/sys/fs/cgroup" + parts[2]
                    for name, key in (("memory.current", "current"), ("memory.peak", "peak")):
                        try:
                            with open(f"{base}/{name}") as g:
                                value = int(g.read().strip())
                        except (OSError, ValueError):
                            value = None
                        if key == "current":
                            current = value
                        else:
                            peak = value
                    break
    except OSError:
        pass
    return {"cgroup_current_bytes": current, "cgroup_peak_bytes": peak}


def rss_snapshot() -> Dict[str, Optional[int]]:
    """Point-in-time memory accounting for this process and its descendants.

    All sources are best-effort: on /proc-less platforms every field is None
    except children_count (0). The Amendment 4 profile runs on the Linux box.
    """
    pid = os.getpid()
    status = _read_status_kb(pid, ("VmRSS", "VmHWM"))
    children = _descendant_pids(pid)
    children_rss = 0
    have_proc = os.path.isdir(f"/proc/{pid}")
    for child in children:
        child_status = _read_status_kb(child, ("VmRSS",))
        children_rss += child_status["VmRSS"] or 0
    snap: Dict[str, Optional[int]] = {
        "master_rss_bytes": status["VmRSS"],
        "master_hwm_bytes": status["VmHWM"],
        "master_pss_bytes": _pss_bytes(pid),
        "children_rss_bytes": children_rss if have_proc else None,
        "children_count": len(children),
    }
    snap.update(_cgroup_memory())
    return snap

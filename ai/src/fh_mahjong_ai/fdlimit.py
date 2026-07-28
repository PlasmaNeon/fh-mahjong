"""File-descriptor limit management for multi-worker collection.

torch's default ``file_descriptor`` tensor-sharing strategy passes one fd per
shared tensor through multiprocessing queues; a 20-worker collection lap moves
enough RolloutBatch tensors to exhaust WSL's default soft limit of 1024
(OSError errno 24, "Too many open files"). Raising the soft RLIMIT_NOFILE to
the hard limit at process start removes the operational ``ulimit -n`` footgun.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

try:  # pragma: no cover - resource is POSIX-only
    import resource
except ImportError:  # pragma: no cover
    resource = None  # type: ignore[assignment]


def raise_file_descriptor_limit(
    log: Optional[Callable[[str], None]] = print,
) -> Optional[Tuple[int, int]]:
    """Raise the soft RLIMIT_NOFILE to the hard limit.

    Returns ``(old_soft, new_soft)`` when the platform supports it, ``None``
    on platforms without the ``resource`` module. Never raises: a failed
    setrlimit (e.g. a hardened container) logs and leaves the limit as-is —
    the caller's workload then fails exactly as it would have before, with
    the log line pointing at the cause.
    """
    if resource is None:
        return None
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if hard == resource.RLIM_INFINITY:
        # Pick a generous finite target: unlimited hard caps still reject
        # RLIM_INFINITY soft values on some kernels.
        target = max(soft, 65535)
    else:
        target = hard
    if target <= soft:
        return (soft, soft)
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except (ValueError, OSError) as exc:
        if log is not None:
            log(f"fdlimit: could not raise RLIMIT_NOFILE {soft} -> {target}: {exc}")
        return (soft, soft)
    if log is not None:
        log(f"fdlimit: raised RLIMIT_NOFILE soft limit {soft} -> {target}")
    return (soft, target)

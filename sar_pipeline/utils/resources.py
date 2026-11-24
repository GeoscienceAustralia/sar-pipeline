"""Helpers to size parallel work to the resources available to the container.

``os.cpu_count()`` returns the number of cores on the host, not the CPU limit
of the container. Kubernetes CPU limits are applied as a CFS quota, which does
not change the CPU affinity, so ``os.sched_getaffinity`` also reports every
host core. The cgroup files are the only reliable source for the limits.
"""

import logging
import math
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_CGROUP_ROOT = Path("/sys/fs/cgroup")
# cgroup v1 reports "no limit" as a very large number (e.g. 9223372036854771712)
CGROUP_V1_UNLIMITED_THRESHOLD = 2**60
GIB = 1024**3


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except (OSError, ValueError):
        return None


def get_cgroup_cpu_limit(cgroup_root: Path = DEFAULT_CGROUP_ROOT) -> float | None:
    """Return the CPU limit (in CPUs) set by the cgroup, or None if unlimited
    or not available. Supports cgroup v2 (cpu.max) and v1 (cfs quota/period).
    """
    cgroup_root = Path(cgroup_root)

    # cgroup v2 : "<quota> <period>" or "max <period>"
    cpu_max = _read_text(cgroup_root / "cpu.max")
    if cpu_max is not None:
        parts = cpu_max.split()
        if not parts or parts[0] == "max":
            return None
        try:
            quota = int(parts[0])
            period = int(parts[1]) if len(parts) > 1 else 100_000
        except ValueError:
            return None
        if quota <= 0 or period <= 0:
            return None
        return quota / period

    # cgroup v1 : quota of -1 means unlimited
    quota = _read_text(cgroup_root / "cpu" / "cpu.cfs_quota_us")
    period = _read_text(cgroup_root / "cpu" / "cpu.cfs_period_us")
    if quota is None or period is None:
        return None
    try:
        quota, period = int(quota), int(period)
    except ValueError:
        return None
    if quota <= 0 or period <= 0:
        return None
    return quota / period


def get_cgroup_memory_limit_bytes(
    cgroup_root: Path = DEFAULT_CGROUP_ROOT,
) -> int | None:
    """Return the memory limit (bytes) set by the cgroup, or None if unlimited
    or not available. Supports cgroup v2 (memory.max) and v1 (limit_in_bytes).
    """
    cgroup_root = Path(cgroup_root)

    # cgroup v2 : bytes or "max"
    memory_max = _read_text(cgroup_root / "memory.max")
    if memory_max is not None:
        if memory_max == "max":
            return None
        try:
            limit = int(memory_max)
        except ValueError:
            return None
        return limit if limit > 0 else None

    # cgroup v1 : unlimited is reported as a very large number
    limit = _read_text(cgroup_root / "memory" / "memory.limit_in_bytes")
    if limit is None:
        return None
    try:
        limit = int(limit)
    except ValueError:
        return None
    if limit <= 0 or limit >= CGROUP_V1_UNLIMITED_THRESHOLD:
        return None
    return limit


def _host_cpu_count() -> int:
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0))
    return os.cpu_count() or 1


def _host_memory_bytes() -> int:
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


def compute_rtc_num_workers(
    memory_per_worker_gib: float,
    cgroup_root: Path = DEFAULT_CGROUP_ROOT,
) -> int:
    """Compute the number of parallel RTC burst workers that fit in the
    CPU and memory available to the container.

    The OPERA/RTC software forces every child burst process to run with
    ``memory_mode: single_block`` (whole burst in memory), so memory, not CPU,
    is usually the binding constraint. If ``num_workers`` is left at 0, RTC
    falls back to ``os.cpu_count()``, which is the host core count in a
    container and can start far more burst processes than the memory limit allows.

    Parameters
    ----------
    memory_per_worker_gib : float
        Peak memory expected for a single burst worker in GiB.
    cgroup_root : Path, optional
        Root of the cgroup filesystem, by default /sys/fs/cgroup.

    Returns
    -------
    int
        Number of workers, at least 1.
    """
    if memory_per_worker_gib <= 0:
        raise ValueError("memory_per_worker_gib must be greater than 0")

    cgroup_cpu_limit = get_cgroup_cpu_limit(cgroup_root)
    cpu_limit = cgroup_cpu_limit if cgroup_cpu_limit is not None else _host_cpu_count()

    cgroup_memory_limit = get_cgroup_memory_limit_bytes(cgroup_root)
    memory_limit = (
        cgroup_memory_limit if cgroup_memory_limit is not None else _host_memory_bytes()
    )

    cpu_workers = math.floor(cpu_limit)
    memory_workers = math.floor(memory_limit / (memory_per_worker_gib * GIB))
    num_workers = max(1, min(cpu_workers, memory_workers))

    logger.info(
        f"RTC num_workers : {num_workers}. "
        f"CPU limit : {cpu_limit} ({'cgroup' if cgroup_cpu_limit is not None else 'host'}), "
        f"memory limit : {memory_limit / GIB:.2f} GiB "
        f"({'cgroup' if cgroup_memory_limit is not None else 'host'}), "
        f"memory per worker : {memory_per_worker_gib} GiB"
    )
    return num_workers


def resolve_rtc_num_workers(
    num_workers: str | int,
    memory_per_worker_gib: float,
    cgroup_root: Path = DEFAULT_CGROUP_ROOT,
) -> int:
    """Resolve a ``--num-workers`` value of "auto" or a positive integer
    to the integer number of workers to use."""
    if isinstance(num_workers, str) and num_workers.strip().lower() == "auto":
        return compute_rtc_num_workers(memory_per_worker_gib, cgroup_root)
    try:
        value = int(num_workers)
    except (TypeError, ValueError):
        raise ValueError(
            f"num_workers must be 'auto' or a positive integer, got : {num_workers}"
        )
    if value < 1:
        raise ValueError(
            f"num_workers must be 'auto' or a positive integer, got : {num_workers}"
        )
    logger.info(f"RTC num_workers set explicitly : {value}")
    return value

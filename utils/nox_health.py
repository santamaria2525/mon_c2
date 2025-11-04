"""Utilities for monitoring Nox emulator health.

Provides lightweight process metrics aggregation and heuristics for
triggering recovery actions when resource usage suggests imminent
freezes.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - psutil is optional
    psutil = None  # type: ignore

# Target process names for Nox components
_NOX_PROCESS_NAMES = (
    "Nox.exe",
    "NoxVMHandle.exe",
    "nox_adb.exe",
    "ProjectTitan.exe",  # some installs use this wrapper
)

# Default thresholds (tuned for multi-instance setups)
DEFAULT_MAX_MEMORY_MB = 3800  # trigger restart when VM keeps >3.8GB
DEFAULT_LOW_CPU_PERCENT = 0.8  # considered idle if CPU below this
DEFAULT_LOW_CPU_STREAK = 8  # with 15s interval => about 2 minutes
DEFAULT_HIGH_CPU_PERCENT = 95.0  # high CPU for extended durations
DEFAULT_HIGH_CPU_STREAK = 6  # 90 seconds of near-constant 100% usage
DEFAULT_POLL_INTERVAL = 15.0  # seconds


@dataclasses.dataclass
class NoxMetrics:
    """Aggregate view of Nox processes."""

    timestamp: float
    total_cpu_percent: float
    total_memory_mb: float
    process_count: int
    per_process: List[Tuple[str, float, float]]  # (name, cpu %, rss MB)


class NoxHealthTracker:
    """Track successive metric breaches and suggest recovery actions."""

    def __init__(
        self,
        *,
        max_memory_mb: int = DEFAULT_MAX_MEMORY_MB,
        low_cpu_percent: float = DEFAULT_LOW_CPU_PERCENT,
        low_cpu_streak: int = DEFAULT_LOW_CPU_STREAK,
        high_cpu_percent: float = DEFAULT_HIGH_CPU_PERCENT,
        high_cpu_streak: int = DEFAULT_HIGH_CPU_STREAK,
    ) -> None:
        self.max_memory_mb = max_memory_mb
        self.low_cpu_percent = low_cpu_percent
        self.low_cpu_streak_target = low_cpu_streak
        self.high_cpu_percent = high_cpu_percent
        self.high_cpu_streak_target = high_cpu_streak

        self._low_cpu_streak = 0
        self._high_cpu_streak = 0
        self._high_memory_streak = 0

    def evaluate(self, metrics: 'NoxMetrics') -> Optional[str]:
        """Update streak counters and return recommended action string.

        Returns:
            "soft_reset" when a mild recovery (e.g. GPU refresh) is advised.
            "restart" when a full VM restart is recommended.
            None otherwise.
        """

        action: Optional[str] = None

        if metrics.total_memory_mb >= self.max_memory_mb:
            self._high_memory_streak += 1
        else:
            self._high_memory_streak = 0

        if metrics.total_cpu_percent <= self.low_cpu_percent:
            self._low_cpu_streak += 1
        else:
            self._low_cpu_streak = 0

        if metrics.total_cpu_percent >= self.high_cpu_percent:
            self._high_cpu_streak += 1
        else:
            self._high_cpu_streak = 0

        # Prolonged high memory usage: request full restart
        if self._high_memory_streak >= 4:
            action = "restart"
            self._high_memory_streak = 0  # avoid repeated triggers
        # Very high CPU for extended duration -> restart as well
        elif self._high_cpu_streak >= self.high_cpu_streak_target:
            action = "restart"
            self._high_cpu_streak = 0
        # Low CPU for extended duration while instance is expected to work
        elif self._low_cpu_streak >= self.low_cpu_streak_target:
            action = "soft_reset"
            self._low_cpu_streak = 0

        return action


def is_available() -> bool:
    """Return True when psutil is available for health checks."""

    return psutil is not None


def iter_nox_processes() -> Iterable['psutil.Process']:
    """Yield psutil.Process objects representing Nox components."""

    if psutil is None:
        return ()  # type: ignore[return-value]

    for proc in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
        name = (proc.info.get("name") or "").lower()
        if any(name.endswith(target.lower()) for target in _NOX_PROCESS_NAMES):
            yield proc


def collect_metrics() -> Optional[NoxMetrics]:
    """Collect aggregated metrics for all detected Nox processes."""

    if psutil is None:
        return None

    processes = list(iter_nox_processes())
    if not processes:
        return None

    total_cpu = 0.0
    total_memory = 0.0
    per_process: List[Tuple[str, float, float]] = []

    for proc in processes:
        try:
            cpu = proc.cpu_percent(interval=0.0)
            rss_mb = proc.memory_info().rss / (1024 * 1024)
            total_cpu += cpu
            total_memory += rss_mb
            per_process.append((proc.name(), cpu, rss_mb))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return NoxMetrics(
        timestamp=time.time(),
        total_cpu_percent=total_cpu,
        total_memory_mb=total_memory,
        process_count=len(per_process),
        per_process=per_process,
    )


def summarise(metrics: NoxMetrics) -> Dict[str, object]:
    """Transform metrics into a JSON-serialisable payload."""

    return {
        "timestamp": metrics.timestamp,
        "total_cpu_percent": round(metrics.total_cpu_percent, 2),
        "total_memory_mb": round(metrics.total_memory_mb, 1),
        "process_count": metrics.process_count,
        "processes": [
            {
                "name": name,
                "cpu_percent": round(cpu, 2),
                "memory_mb": round(mem, 1),
            }
            for name, cpu, mem in metrics.per_process
        ],
    }

"""
Windows high-resolution timer and idle-prevention helpers.

On modern Windows (10 2004+), ``timeBeginPeriod(1)`` alone is not enough:
the OS may still throttle timer resolution when it considers the system idle.
We combine three mechanisms to keep ``time.sleep()`` accurate (~1-2 ms):

1. **timeBeginPeriod(1)** – classic 1 ms timer request.
2. **NtSetTimerResolution** – NT kernel API, more authoritative.
3. **SetThreadExecutionState** – tells Windows the system is in active use,
   preventing idle-state timer throttling.

Because Windows can silently reclaim the resolution during long-running
sessions, all requests are **periodically refreshed** (default: every 30 s).
Callers only need to use :class:`HighResolutionTimer` as a context manager
or call :meth:`~HighResolutionTimer.tick` inside their loop.
"""

from __future__ import annotations

import sys
import time
from logging import getLogger

logger = getLogger(__name__)

__all__ = ["HighResolutionTimer"]

# ── platform gate ────────────────────────────────────────────────────────
_IS_WIN = sys.platform == "win32"

if _IS_WIN:
    import ctypes

    _winmm = ctypes.windll.winmm  # type: ignore[attr-defined]
    _kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    try:
        _ntdll = ctypes.windll.ntdll  # type: ignore[attr-defined]
    except Exception:
        _ntdll = None

    # SetThreadExecutionState flags
    _ES_CONTINUOUS = 0x80000000
    _ES_SYSTEM_REQUIRED = 0x00000001


# ── low-level helpers ────────────────────────────────────────────────────

def _request_timer_resolution() -> None:
    """Request ~1 ms timer resolution via Windows APIs."""
    if not _IS_WIN:
        return
    try:
        _winmm.timeBeginPeriod(1)
    except Exception:
        pass
    if _ntdll is not None:
        try:
            actual = ctypes.c_ulong()
            # 10 000 × 100 ns = 1 ms
            _ntdll.NtSetTimerResolution(10000, True, ctypes.byref(actual))
        except Exception:
            pass


def _release_timer_resolution() -> None:
    """Release the timer-resolution requests."""
    if not _IS_WIN:
        return
    try:
        _winmm.timeEndPeriod(1)
    except Exception:
        pass
    if _ntdll is not None:
        try:
            actual = ctypes.c_ulong()
            _ntdll.NtSetTimerResolution(10000, False, ctypes.byref(actual))
        except Exception:
            pass


def _prevent_idle() -> None:
    """Prevent Windows from entering idle / low-power timer states."""
    if not _IS_WIN:
        return
    _kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)


def _allow_idle() -> None:
    """Release idle prevention."""
    if not _IS_WIN:
        return
    _kernel32.SetThreadExecutionState(_ES_CONTINUOUS)


# ── public API ───────────────────────────────────────────────────────────

class HighResolutionTimer:
    """Keeps Windows timer resolution at ~1 ms for the duration of use.

    The timer resolution and idle-prevention flags are **re-requested**
    every *refresh_interval* seconds (default 30) to guard against the OS
    silently reclaiming them during long sessions.

    Usage as a **context manager**::

        with HighResolutionTimer():
            while running:
                timer.tick()   # must be called periodically
                ...

    Or manually::

        timer = HighResolutionTimer()
        timer.acquire()
        try:
            while running:
                timer.tick()
                ...
        finally:
            timer.release()

    Parameters
    ----------
    refresh_interval:
        Seconds between automatic re-requests.  30 s is a safe default that
        is frequent enough to prevent Windows from throttling, yet cheap
        enough to be invisible in profiling.
    """

    def __init__(self, refresh_interval: float = 30.0) -> None:
        self.refresh_interval = refresh_interval
        self._last_refresh: float = 0.0
        self._active: bool = False

    # ── context manager ──────────────────────────────────────────────

    def __enter__(self) -> "HighResolutionTimer":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()

    # ── lifecycle ────────────────────────────────────────────────────

    def acquire(self) -> None:
        """Request high timer resolution and idle prevention."""
        _request_timer_resolution()
        _prevent_idle()
        self._last_refresh = time.monotonic()
        self._active = True
        logger.debug("HighResolutionTimer acquired (refresh every %.0fs)", self.refresh_interval)

    def release(self) -> None:
        """Release timer resolution and idle prevention."""
        if not self._active:
            return
        _release_timer_resolution()
        _allow_idle()
        self._active = False
        logger.debug("HighResolutionTimer released")

    def tick(self) -> None:
        """Call periodically from the hot loop.

        Internally checks whether *refresh_interval* has elapsed and, if so,
        re-requests the high timer resolution and idle-prevention flags.
        The check itself is a simple ``monotonic()`` comparison – negligible
        overhead.
        """
        if not self._active:
            return
        now = time.monotonic()
        if now - self._last_refresh >= self.refresh_interval:
            _request_timer_resolution()
            _prevent_idle()
            self._last_refresh = now
            logger.debug("HighResolutionTimer refreshed")

"""
Wrapper around the sacn library for receiving DMX data via sACN (Streaming ACN) protocol.
This wrapper implements smoothing the input with a fixed framerate.

On sACN DMX receive, ``last_rx_data`` is updated.  If it differs from
``output_data``, the output moves toward the target at a fixed linear step
size every frame.  A user-provided callback is invoked at the configured
framerate with the smoothed output data.
"""

from __future__ import annotations

import sys
import time
import threading
from typing import Callable
from logging import getLogger

import sacn

logger = getLogger(__name__)

# On Windows, request 1 ms timer resolution so time.sleep() only overshoots
# by ~1-2 ms instead of ~15.6 ms.  This makes the coarse sleep before
# the spin-wait much more effective at releasing the CPU.
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)  # type: ignore[attr-defined]
    except Exception:
        logger.warning("Failed to set Windows timer resolution to 1 ms")


class SACNInput:
    """Receives sACN DMX data on a single universe with per-channel linear smoothing.

    Parameters
    ----------
    universe:
        sACN universe to listen on (1-based).
    start_channel:
        First DMX channel to extract (1-based, inclusive).
    n_channels:
        Number of consecutive DMX channels to extract.
    callback:
        Called every frame tick with a ``list[int]`` of length *n_channels*
        containing the current (smoothed) output values.
    framerate:
        How often (Hz) the smoothing loop ticks and the callback fires.
    time_full_change:
        Time in seconds for a full 0→255 ramp.  The per-tick step size is
        computed dynamically from elapsed ``dt``.  Set to 0 for instantaneous
        pass-through.
    bind_address:
        IP address to bind to for receiving multicast packets.
        Empty string or ``"0.0.0.0"`` binds to all interfaces.
    multicast:
        Whether to join the multicast group for the universe.
    """

    SLEEP_THRESHOLD: float = 0.005  # seconds

    def __init__(
        self,
        universe: int,
        start_channel: int,
        n_channels: int,
        callback: Callable[[list[int]], None],
        framerate: int = 30,
        time_full_change: float = 1.0,
        bind_address: str = "",
        multicast: bool = True,
        use_internal_loop: bool = True,
    ) -> None:
        self.universe: int = universe
        self.start_channel: int = start_channel
        self.n_channels: int = n_channels
        self.callback: Callable[[list[int]], None] = callback
        self.framerate: int = framerate
        self.time_full_change: float = time_full_change
        self.bind_address: str = bind_address
        self.multicast: bool = multicast
        self.use_internal_loop: bool = use_internal_loop

        # Internal state --------------------------------------------------------
        self._lock: threading.Lock = threading.Lock()
        self._last_rx_data: list[int] = [0] * n_channels
        self._output_data: list[int] = [0] * n_channels
        self._running: bool = False
        self._receiver: sacn.sACNreceiver | None = None
        self._thread: threading.Thread | None = None
        self._last_step_ts: float | None = None  # timestamp of last smoothing_step call

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Create the sACN receiver, register the universe listener, and
        start the background smoothing thread."""
        if self._running:
            logger.warning("SACNInput already running – ignoring start()")
            return

        self._running = True

        # Create receiver
        if self.bind_address:
            self._receiver = sacn.sACNreceiver(bind_address=self.bind_address)
        else:
            self._receiver = sacn.sACNreceiver()
        self._receiver.start()

        # Register listen callback
        @self._receiver.listen_on("universe", universe=self.universe)
        def _on_packet(packet: sacn.DataPacket) -> None:
            self._on_sacn_packet(packet)

        if self.multicast:
            self._receiver.join_multicast(self.universe)

        # Start smoothing thread (only when using the internal loop)
        if self.use_internal_loop:
            self._thread = threading.Thread(
                target=self._smoothing_loop,
                name=f"SACNInput-smooth-u{self.universe}",
                daemon=True,
            )
            self._thread.start()

        mode = "internal" if self.use_internal_loop else "external"
        logger.info(
            "SACNInput started (%s loop): universe=%d, channels=%d–%d, "
            "fps=%d, time_full_change=%.3fs",
            mode,
            self.universe,
            self.start_channel,
            self.start_channel + self.n_channels - 1,
            self.framerate,
            self.time_full_change,
        )

    def stop(self) -> None:
        """Stop the smoothing thread and shut down the sACN receiver."""
        if not self._running:
            return
        self._running = False

        # Wait for the smoothing thread to exit
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        # Tear down receiver
        if self._receiver is not None:
            try:
                if self.multicast:
                    self._receiver.leave_multicast(self.universe)
            except Exception:
                pass
            try:
                self._receiver.stop()
            except Exception:
                pass
            self._receiver = None

        logger.info("SACNInput stopped (universe=%d)", self.universe)

    @property
    def output_data(self) -> list[int]:
        """Return a snapshot of the current smoothed output."""
        with self._lock:
            return list(self._output_data)

    @property
    def last_rx_data(self) -> list[int]:
        """Return a snapshot of the last raw received data."""
        with self._lock:
            return list(self._last_rx_data)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_sacn_packet(self, packet: sacn.DataPacket) -> None:
        """Called by the sacn library on every incoming DMX packet."""
        if packet.dmxStartCode != 0x00:
            return  # ignore non-DMX data packets

        start: int = self.start_channel - 1  # 0-based index
        end: int = start + self.n_channels

        if len(packet.dmxData) < end:
            return  # not enough data in packet

        new_values: list[int] = list(packet.dmxData[start:end])

        with self._lock:
            self._last_rx_data = new_values

    def _compute_step_size(self, dt: float) -> int:
        """Compute the per-channel step size for a given time delta.

        The step is proportional to *dt* so that a full 0→255 ramp takes
        exactly *time_full_change* seconds.  If *time_full_change* is 0,
        the output jumps instantly to the target (step = 255).
        minimal step size is 1 to ensure progress when target differs from output.
        """
        if self.time_full_change <= 0:
            return 255
        return max(1, round(255.0 * dt / self.time_full_change))

    def smoothing_step(self) -> tuple[list[int], bool]:
        """Perform one smoothing tick and fire the callback.

        Call this from an external loop when ``use_internal_loop=False``.
        The step size is computed from the elapsed time since the last call
        (using ``time_full_change``) or falls back to the fixed ``step_size``.

        Returns a tuple ``(values, changed)`` where *values* is the current
        smoothed output and *changed* indicates whether any channel moved.
        """
        now: float = time.perf_counter()
        if self._last_step_ts is None:
            dt = 1.0 / self.framerate  # first call: assume one ideal frame
        else:
            dt = now - self._last_step_ts
        self._last_step_ts = now

        current_step: int = self._compute_step_size(dt)

        # Snapshot the target under lock
        with self._lock:
            target: list[int] = list(self._last_rx_data)

        # Move each channel toward target by at most current_step
        changed: bool = False
        for i in range(self.n_channels):
            diff: int = target[i] - self._output_data[i]
            if diff == 0:
                continue
            changed = True
            move: int = min(abs(diff), current_step)
            if diff > 0:
                self._output_data[i] += move
            else:
                self._output_data[i] -= move
            self._output_data[i] = max(0, min(255, self._output_data[i]))

        result: list[int] = list(self._output_data)

        # Fire the callback
        try:
            self.callback(result)
        except Exception:
            logger.exception("SACNInput callback error")

        return result, changed

    def _smoothing_loop(self) -> None:
        """Background thread that ticks at *framerate* Hz, calling
        :meth:`smoothing_step` each tick."""
        frame_period: float = 1.0 / self.framerate
        # Use time.perf_counter() instead of time.monotonic() because on
        # Windows, monotonic() uses GetTickCount64 (~15.6 ms resolution)
        # while perf_counter() uses QueryPerformanceCounter (sub-µs).
        clock = time.perf_counter
        _dbg_count: int = 0
        _dbg_work_total: float = 0.0
        _dbg_cb_total: float = 0.0
        _dbg_overshoot_total: float = 0.0
        _dbg_last_report: float = clock()

        while self._running:
            tick_start: float = clock()

            self.smoothing_step()

            work_done: float = clock()

            # Wait for the remainder of the frame period.
            # Sleep the coarse part (if > threshold remain) to release the CPU,
            # then spin-wait the tail using perf_counter for sub-ms accuracy.
            deadline: float = tick_start + frame_period
            remaining: float = deadline - clock()
            if remaining > self.SLEEP_THRESHOLD:
                time.sleep(remaining - self.SLEEP_THRESHOLD)
            while clock() < deadline:
                pass

            # Debug stats
            actual_end: float = clock()
            _dbg_count += 1
            _dbg_work_total += work_done - tick_start
            _dbg_overshoot_total += actual_end - deadline
            if actual_end - _dbg_last_report >= 5.0:
                avg_work = _dbg_work_total / _dbg_count * 1000
                avg_over = _dbg_overshoot_total / _dbg_count * 1000
                avg_total = (actual_end - _dbg_last_report) / _dbg_count * 1000
                logger.info(
                    "Timing (avg over %d ticks): work=%.2fms, "
                    "overshoot=%.2fms, total_period=%.2fms (target=%.2fms)",
                    _dbg_count, avg_work, avg_over, avg_total,
                    frame_period * 1000,
                )
                _dbg_count = 0
                _dbg_work_total = 0.0
                _dbg_overshoot_total = 0.0
                _dbg_last_report = actual_end


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)

    # Counters for measuring rates
    _input_count: int = 0
    _output_count: int = 0
    _max_step: int = 0
    _last_output: list[int] = []
    _stats_lock = threading.Lock()

    def _on_sacn_packet_hook_original(self_ref: SACNInput, packet: sacn.DataPacket) -> None:
        """Monkey-patched packet handler that also counts input frames."""
        global _input_count
        with _stats_lock:
            _input_count += 1
        # Call the original handler
        SACNInput._on_sacn_packet.__wrapped__(self_ref, packet)

    def test_callback(values: list[int]) -> None:
        """Callback that counts output frames and tracks max step size."""
        global _output_count, _max_step, _last_output
        with _stats_lock:
            _output_count += 1
            if _last_output:
                for i in range(len(values)):
                    step = abs(values[i] - _last_output[i])
                    if step > _max_step:
                        _max_step = step
            _last_output = list(values)

    # Wrap _on_sacn_packet to count input frames
    _original_on_sacn_packet = SACNInput._on_sacn_packet

    def _counting_on_sacn_packet(self: SACNInput, packet: sacn.DataPacket) -> None:
        global _input_count
        with _stats_lock:
            _input_count += 1
        _original_on_sacn_packet(self, packet)

    SACNInput._on_sacn_packet = _counting_on_sacn_packet  # type: ignore[assignment]

    TARGET_FPS = 20

    inp = SACNInput(
        universe=1,
        start_channel=1,
        n_channels=16,
        callback=test_callback,
        framerate=TARGET_FPS,
        time_full_change=2.0,
        multicast=True,
        use_internal_loop=False,  # driven from external loop below
    )
    inp.start()

    print("Listening for sACN on universe 1 (external loop) … (Ctrl+C to stop)")
    print(f"{'In FPS':>8s}  {'Out FPS':>8s}  {'Max Step':>8s}")
    print("-" * 30)

    clock = time.perf_counter
    frame_period: float = 1.0 / TARGET_FPS
    last_report: float = clock()

    try:
        while True:
            tick_start: float = clock()

            inp.smoothing_step()

            # Frame-rate limiter: sleep coarse, spin-wait the tail
            deadline: float = tick_start + frame_period
            remaining: float = deadline - clock()
            if remaining > SACNInput.SLEEP_THRESHOLD:
                time.sleep(remaining - SACNInput.SLEEP_THRESHOLD)
            while clock() < deadline:
                pass

            # Print stats every second
            now: float = clock()
            if now - last_report >= 1.0:
                with _stats_lock:
                    in_fps = _input_count
                    out_fps = _output_count
                    ms = _max_step
                    _input_count = 0
                    _output_count = 0
                    _max_step = 0
                print(f"{in_fps:>8d}  {out_fps:>8d}  {ms:>8d}")
                last_report = now
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        inp.stop()

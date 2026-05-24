"""
DualEffectManager — runs two EffectManagers in parallel and blends their outputs.

The first manager uses DMX channels 0–13, the second uses channels 14–27.
Outputs are blended additively (summed and clipped to 0–255), so each manager's
built-in master fader independently controls its contribution.

The preview image shows three panels stacked vertically:
  1. Final blended output (top)
  2. Effect Manager 1 output (middle)
  3. Effect Manager 2 output (bottom)
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import numpy as np
from nicegui import ui

from led_wall.effects.effect_manager import EffectManager
from led_wall.ui.settings_manager import SettingsManager
from led_wall.ui.preview_window import preview_setup, create_preview_frame, OutputCorrection

if TYPE_CHECKING:
    from led_wall.io_manager import IO_Manager

logger = logging.getLogger(__name__)

CHANNELS_PER_MANAGER = 14


class DualEffectManager:
    """Wraps two EffectManagers and blends their outputs additively."""

    def __init__(self, io_manager: IO_Manager, settings_manager: SettingsManager) -> None:
        self.IO_manager = io_manager
        self.settings_manager = settings_manager

        mgr0_settings = SettingsManager(parent=settings_manager, name="effect_mgr_0")
        mgr1_settings = SettingsManager(parent=settings_manager, name="effect_mgr_1")

        self.mgr0 = EffectManager(io_manager, mgr0_settings, mgr_index=0, embedded=True, channel_offset=0)
        self.mgr1 = EffectManager(io_manager, mgr1_settings, mgr_index=1, embedded=True, channel_offset=CHANNELS_PER_MANAGER)

        self._out0: np.ndarray | None = None
        self._out1: np.ndarray | None = None

        self._preview_image: ui.interactive_image | None = None
        self._fps_label: ui.label | None = None
        self._preview_height: int = 200
        self._preview_width: int = 100
        self._fps_frame_count: int = 0
        self._fps_last_report: float = 0.0
        self._fps_value: float = 0.0
        self.preview_timer = None

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """Initialize both effect managers."""
        self.mgr0.setup()
        self.mgr1.setup()
        # Take over the IO frame callback
        self.IO_manager.create_frame = self.run_loop

    # ------------------------------------------------------------------
    # Frame loop
    # ------------------------------------------------------------------

    def run_loop(self, channels: list[int], last_output: np.ndarray) -> np.ndarray:
        """Called by IO_Manager on every frame tick."""
        ch0 = channels[0:CHANNELS_PER_MANAGER]
        ch1 = channels[CHANNELS_PER_MANAGER:CHANNELS_PER_MANAGER * 2]

        # Pad channel slices with zeros if the input is shorter than expected
        if len(ch0) < CHANNELS_PER_MANAGER:
            ch0 = ch0 + [0] * (CHANNELS_PER_MANAGER - len(ch0))
        if len(ch1) < CHANNELS_PER_MANAGER:
            ch1 = ch1 + [0] * (CHANNELS_PER_MANAGER - len(ch1))

        out0 = self.mgr0.run_loop(ch0, last_output)
        out1 = self.mgr1.run_loop(ch1, last_output)

        blended = np.clip(
            out0.astype(np.uint16) + out1.astype(np.uint16), 0, 255
        ).astype(np.uint8)

        self._out0 = out0
        self._out1 = out1

        # FPS tracking (use manager 0's counter)
        self._fps_frame_count += 1
        now = time.perf_counter()
        dt = now - self._fps_last_report
        if dt >= 1.0:
            self._fps_value = self._fps_frame_count / dt
            self._fps_frame_count = 0
            self._fps_last_report = now
            if self._fps_label is not None:
                self._fps_label.set_text(f'{self._fps_value:.1f} FPS')

        return blended

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def init_preview(self, preview_image: ui.interactive_image, fps_label: ui.label | None = None) -> None:
        """Store reference to the preview image widget."""
        res = self.IO_manager.resolution
        dim = self.IO_manager.dimensions
        self._preview_height = 200
        aspect_ratio = dim[0] / dim[1]
        self._preview_width = int(self._preview_height * aspect_ratio)
        self._preview_image = preview_image
        self._fps_label = fps_label
        self._fps_last_report = time.perf_counter()
        self._fps_frame_count = 0

        # Also forward to sub-managers so they track state (but won't set up timers)
        self.mgr0.preview_image = preview_image
        self.mgr1.preview_image = preview_image

    def setup_preview(self) -> None:
        """Register the FastAPI preview endpoint and start the NiceGUI timer."""
        if not self._preview_image:
            raise ValueError("Preview image not initialized. Call init_preview() first.")

        io = self.IO_manager
        pw = self._preview_width
        ph = self._preview_height

        def _apply_corrections(buf: np.ndarray) -> np.ndarray:
            """Apply gamma correction and optional dithering to a raw uint8 buffer."""
            if io.gamma_correction is not None:
                use_dithering = io.dithering and io.gamma_correction != 'linear'
                if use_dithering:
                    buf = OutputCorrection.apply(buf.astype(np.uint16) * 10, io.gamma_correction, max_val=2550, output_type=np.uint16)
                    buf = OutputCorrection.apply_checkerboard_dithering(buf)
                else:
                    buf = OutputCorrection.apply(buf, io.gamma_correction)
            return buf

        def get_dual_preview() -> np.ndarray:
            """Build the 3-panel stacked preview image."""
            # Final blended output is always available in io.output_buffer
            frame_final = create_preview_frame(
                output_buffer=_apply_corrections(io.output_buffer),
                resolution=io.resolution,
                pixel_channels=io.pixel_channels,
                preview_width=pw,
                preview_height=ph,
            )

            # Per-manager previews — fall back to black if not yet available
            if self._out0 is not None:
                frame0 = create_preview_frame(
                    output_buffer=_apply_corrections(self._out0),
                    resolution=io.resolution,
                    pixel_channels=io.pixel_channels,
                    preview_width=pw,
                    preview_height=ph,
                )
            else:
                frame0 = np.zeros_like(frame_final)

            if self._out1 is not None:
                frame1 = create_preview_frame(
                    output_buffer=_apply_corrections(self._out1),
                    resolution=io.resolution,
                    pixel_channels=io.pixel_channels,
                    preview_width=pw,
                    preview_height=ph,
                )
            else:
                frame1 = np.zeros_like(frame_final)

            # Stack vertically: final (top) → mgr0 (middle) → mgr1 (bottom)
            return np.vstack([frame_final, frame0, frame1])

        self.preview_timer = preview_setup(
            self._preview_image,
            get_preview_frame=get_dual_preview,
            io_manager=None,  # We supply our own get_preview_frame
        )

    # ------------------------------------------------------------------
    # UI delegation
    # ------------------------------------------------------------------

    def effect_manager_ui_tabs(self) -> None:
        """Renders both effect managers inside named tabs."""
        with ui.tabs().classes('w-full') as mgr_tabs:
            tab_mgr0 = ui.tab('Effekt Manager 1')
            tab_mgr1 = ui.tab('Effekt Manager 2')

        with ui.tab_panels(mgr_tabs, value=tab_mgr0).classes('w-full'):
            with ui.tab_panel(tab_mgr0):
                self.mgr0.effect_manager_ui()
            with ui.tab_panel(tab_mgr1):
                self.mgr1.effect_manager_ui()

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Stop preview timer, both effect managers, and the IO loop."""
        if self.preview_timer is not None:
            try:
                self.preview_timer.deactivate()
                logger.info("Deactivated dual preview timer")
            except Exception as e:
                logger.error(f"Error deactivating preview timer: {e}")

        self.mgr0.shutdown()
        self.mgr1.shutdown()

        if self.IO_manager:
            try:
                self.IO_manager.stop_loop()
                logger.info("Stopped IO manager loop")
            except Exception as e:
                logger.error(f"Error stopping IO manager: {e}")

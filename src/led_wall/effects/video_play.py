import numpy as np
import logging
import time
from threading import Thread, current_thread
from nicegui import ui
from led_wall.effects.base_effect import BaseEffect
from led_wall.ui.video_manager import VideoManager
from led_wall.ui.settings_manager import SettingsManager

logger = logging.getLogger("utils")

class VideoPlay(BaseEffect):
    """
    Effect that plays a video file on the LED wall.
    """

    NAME = 'Video'
    DESCRIPTION = 'Plays a video file with mapping and scaling options. Supports looping and real-time playback.'
    CONTROLLS_LOOP = True

    def __init__(self, resolution: tuple[int, int], dimensions: tuple[int, int], rgbw: bool, settings_manager: SettingsManager = None) -> None:
        # Initialize VideoManager first because base class calls setup_settings
        self.video_manager = VideoManager(settings_manager, resolution=resolution, dimensions=dimensions)
        self.video_manager.preload()
        self.is_active = False
        self.loop_thread = None
        super().__init__(resolution, dimensions, rgbw, settings_manager)
        
    def setup_settings(self) -> None:
        """
        No standard settings elements needed, VideoManager handles everything.
        """
        self.settings_elements = []

    def ui_settings(self):
        """
        Custom UI for the effect settings page.
        """
        self.video_manager.create_ui()

    def on_ui_open(self):
        self.video_manager.start_preview()

    def on_ui_close(self):
        self.video_manager.stop_preview()
        if not self.is_active:
            self.video_manager.stop()

    def run_raw(self, DMX_channels, last_output: np.array) -> np.array:
        """
        Calculates the frame by grabbing it from the VideoManager.
        """
        self.update_inputs(DMX_channels)
        
        # Get frame from video manager (already mapped to LED resolution)
        frame = self.video_manager.get_frame()
        
        # frame is RGB (H, W, 3)
        res_w, res_h = self.resolution
        # Ensure it matches expected output shape (W, H, 3 or 4)
        # Note: self.resolution is (width, height)
        # np.array(frame) is (height, width, 3) because it comes from PIL/OpenCV
        # Transpose to (width, height, 3)
        frame = np.transpose(frame, (1, 0, 2))
        
        # Add master brightness
        master = self.inputs['master'].value / 255.0
        frame = (frame * master).astype(np.uint8)

        if self.rgbw:
            # Add W channel (all 0 for standard video)
            output = np.dstack((frame, np.zeros((res_w, res_h, 1), dtype=np.uint8)))
            return output
        
    def start(self):
        """
        Called when this effect is selected/activated.
        """
        super().start()
        self.is_active = True
        self.video_manager.reset_clock()
        
        # Take control of the loop if io_manager is available
        if self.io_manager:
            self.io_manager.stop_thread()
            
        self.loop_thread = Thread(target=self._drive_loop, daemon=True)
        self.loop_thread.start()

    def stop(self):
        """
        Clean up resources on stop.
        """
        self.is_active = False
        if self.loop_thread and self.loop_thread.is_alive() and self.loop_thread is not current_thread():
            self.loop_thread.join(timeout=1.0)
            
        super().stop()
        self.video_manager.preload()
        
        # Return control to IO_Manager
        if self.io_manager:
            self.io_manager.start_loop()

    def _drive_loop(self):
        """
        Internal loop to drive IO_Manager step synchronized with video.
        """
        # If we replaced the IO Manager thread while running inside it, 
        # we must wait for it to exit to avoid race conditions.
        if self.io_manager and self.io_manager.run_thread and self.io_manager.run_thread.is_alive():
            # Only join if we are NOT in that thread (which _drive_loop shouldn't be anyway)
            if self.io_manager.run_thread is not current_thread():
                try:
                    self.io_manager.run_thread.join(timeout=1.0)
                except Exception as e:
                    logger.warning(f"Could not join IO Manager thread: {e}")

        logger.debug("Video loop started.")
        fps = 30
        if hasattr(self.video_manager, '_fps') and self.video_manager._fps > 0:
            fps = self.video_manager._fps
            
        period = 1.0 / fps
        next_call = time.time()
        
        while self.is_active:
            now = time.time()
            if now >= next_call:
                if self.io_manager:
                    self.io_manager.step()
                
                next_call += period
                # Prevent drift buildup if we fall significantly behind
                if now > next_call + period:
                    next_call = now
            else:
                time.sleep(max(0.001, next_call - now))
        super().stop()
        self.video_manager.stop()
        logger.debug("Video loop stopped.")

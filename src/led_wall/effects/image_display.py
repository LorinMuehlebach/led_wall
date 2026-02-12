import numpy as np
from led_wall.effects.base_effect import BaseEffect
from led_wall.ui.media_manager import MediaManager
from led_wall.ui.settings_manager import SettingsManager

class ImageDisplay(BaseEffect):
    NAME = 'Bild'
    DESCRIPTION = 'Display an image on the LED wall with scaling and mapping options'

    def __init__(self, resolution: tuple[int, int], dimensions: tuple[int, int], rgbw: bool, settings_manager: SettingsManager = None) -> None:
        # Initialize media manager
        self.media_manager = MediaManager(settings_manager, resolution=resolution, dimensions=dimensions)
        super().__init__(resolution, dimensions, rgbw, settings_manager)
    
    def setup_settings(self) -> None:
        # No standard settings elements needed, MediaManager handles UI
        self.settings_elements = []

    def ui_settings(self):
        # Create the UI for the media manager
        self.media_manager.create_ui()

    def run_raw(self, DMX_channels, last_output: np.array) -> np.array:
        self.update_inputs(DMX_channels)
        
        # Get frame from media manager
        frame = self.media_manager.get_frame()
        
        # Convert (H, W, 3) to (W, H, 3)
        frame = np.transpose(frame, (1, 0, 2))
        
        # Apply master dimmer
        master = self.inputs['master'].value / 255.0
        frame = (frame * master).astype(np.uint8)

        if self.rgbw:
             # Add W channel
             output = np.dstack((frame, np.zeros((self.resolution[0], self.resolution[1], 1), dtype=np.uint8)))
             return output
        
        return frame

import numpy as np
import time
import math
from led_wall.effects.base_effect import BaseEffect
from led_wall.ui.show_inputs import Fader, RGBW_Color
from nicegui import ui
from led_wall.ui.settings_manager import SettingsManager, SettingsElement

class WaveEffect(BaseEffect):
    """
    Effect that displays a repeating wave pattern.
    """

    NAME = 'Wave Effect'
    DESCRIPTION = 'Displays a transition between two colors with a wave pattern. Controls for frequency, amplitude, and angle.'

    def __init__(self, resolution: tuple[int, int], dimensions: tuple[int, int], rgbw: bool, settings_manager=None) -> None:
        super().__init__(resolution, dimensions, rgbw, settings_manager)
        
        # Add custom inputs resembling Gradient but for waves
        self.inputs['color2'] = RGBW_Color([0, 0, 255, 0])
        self.inputs['frequency'] = Fader(50)  # Controls how many waves
        self.inputs['amplitude'] = Fader(50)  # Controls the "waviness"
        self.inputs['phase'] = Fader(0)       # Shifts the wave manually
        self.inputs['angle'] = Fader(0)       # Rotation
        
        self.res_x, self.res_y = self.resolution
        
        # Pre-calculate the coordinate grid for performance
        # We center the coordinates at 0,0 to rotate around the center
        x = np.linspace(-0.5, 0.5, self.res_x)
        y = np.linspace(-0.5, 0.5, self.res_y)
        # indexing='ij' ensures first dimension is width (x), second is height (y)
        self.xv, self.yv = np.meshgrid(x, y, indexing='ij')

    def run_raw(self, DMX_channels, last_output: np.array) -> np.array:
        """
        Calculates the wave pattern frame.
        """
        self.update_inputs(DMX_channels)
        
        # Get input values and normalize
        master = self.inputs['master'].value / 255.0
        c1 = np.array(self.inputs['rgbw_color'].get_channels()) * master
        c2 = np.array(self.inputs['color2'].get_channels()) * master
        
        freq_val = self.inputs['frequency'].value
        amp_val = self.inputs['amplitude'].value
        phase_val = self.inputs['phase'].value
        angle_val = self.inputs['angle'].value
        
        # Frequency (Line density): constant roughly 20 to 100
        # Map 0-255 to 10.0 - 100.0
        frequency = 10.0 + (freq_val / 255.0) * 90.0
        
        # Amplitude (Waviness): 
        # Map 0-255 to 0.0 - 0.2 (relative to screen size 1.0)
        amplitude = (amp_val / 255.0) * 0.1
        
        # Phase: map 0-255 to 0-2pi
        phase = (phase_val / 255.0) * 2 * np.pi
        
        # Angle: map 0-255 to 0-2pi
        angle = (angle_val / 255.0) * 2 * np.pi
        
        # Calculate projection vector (direction of propagation)
        cos_a = np.cos(angle)
        sin_a = np.sin(angle)
        
        # p is the primary axis coordinate (longitudinal distance)
        p = self.xv * cos_a + self.yv * sin_a
        
        # q is the perpendicular axis coordinate (transverse distance for waviness)
        q = -self.xv * sin_a + self.yv * cos_a
        
        # Create "Multiple wavy lines"
        # Base pattern is sin(frequency * p) -> straight lines
        # Distort p by adding amplitude * sin(q_freq * q)
        # q_freq needs to be unrelated to 'frequency' or related? 
        # Usually waviness has its own frequency, but we only have one 'frequency' knob unless we misuse amplitude or add another.
        # Let's fix waviness frequency to something reasonable visually or derive from frequency.
        # Repeating constant of 20.0 for transverse wave seems fine.
        
        distortion = amplitude * np.sin(q * 20.0)
        
        # The wave value (-1 to 1)
        # sin(freq * (p + distortion) + phase)
        val = np.sin(frequency * (p + distortion) + phase)
        
        # Normalize sine (-1 to 1) to (0 to 1) for color mix
        t = (val + 1) / 2.0
        
        # Reshape t for broadcasting: (res_x, res_y, 1)
        t_3d = t[:, :, np.newaxis]
        
        # Linear interpolation
        output_array = (c1 * (1.0 - t_3d) + c2 * t_3d).astype(np.uint8)
        
        return output_array

    def setup_settings(self) -> None:
        self.settings_elements: list[SettingsElement] = []

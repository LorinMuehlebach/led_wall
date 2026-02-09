import numpy as np
import logging
from led_wall.effects.base_effect import BaseEffect
from led_wall.datatypes import RGBW_Color, Fader

logger = logging.getLogger("utils")

class Gradient(BaseEffect):
    """
    Effect that displays a sliding gradient between two colors.
    """

    NAME = 'Gradient'
    DESCRIPTION = 'Displays a transition between two colors. Controls for start, nonlinear strength and direction.'

    def __init__(self, resolution: tuple[int, int], dimensions: tuple[int, int], rgbw: bool, settings_manager=None) -> None:
        super().__init__(resolution, dimensions, rgbw, settings_manager)
        
        # Add custom inputs for the gradient
        # They are added to the existing ones (master, rgbw_color, mode)
        # Order: master (1), rgbw_color (4), mode (1), color2 (4), change_start (1), change_strength (1), direction (1)
        self.inputs['color2'] = RGBW_Color([255, 255, 255, 255])
        self.inputs['change_start'] = Fader(127) # Default to center
        self.inputs['change_strength'] = Fader(0)
        self.inputs['direction'] = Fader(0)
        
        self.res_x, self.res_y = self.resolution
        # Pre-calculate the coordinate grid for performance
        # We center the coordinates at 0,0 to rotate around the center
        x = np.linspace(-0.5, 0.5, self.res_x)
        y = np.linspace(-0.5, 0.5, self.res_y)
        # indexing='ij' ensures first dimension is width (x), second is height (y)
        self.xv, self.yv = np.meshgrid(x, y, indexing='ij')

    def run_raw(self, DMX_channels, last_output: np.array) -> np.array:
        """
        Calculates the gradient frame.
        """
        # Note: update_inputs is called by the EffectManager before this method
        
        # Get input values and normalize to 0.0-1.0
        master = self.inputs['master'].value / 255.0
        c1 = np.array(self.inputs['rgbw_color'].get_channels()) * master
        c2 = np.array(self.inputs['color2'].get_channels()) * master
        
        start = self.inputs['change_start'].value / 255.0
        # Nonlinear scaling: x^2 gives more resolution at the lower end (near 0)
        strength_raw = self.inputs['change_strength'].value / 255.0
        strength = strength_raw ** 2
        # Convert DMX direction (0-255) to angle (0 to 2*PI)
        angle = (self.inputs['direction'].value / 255.0) * 2 * np.pi
        
        # Calculate projection vector based on angle
        dx = np.cos(angle)
        dy = np.sin(angle)
        
        # Project each point (xv, yv) onto the direction vector
        p = self.xv * dx + self.yv * dy
        
        # Calculate the slope based on strength
        # strength = 0 -> slope = 1.0 (fade over whole display)
        # strength = 1 -> slope = max resolution (sharp transition)
        max_res = max(self.res_x, self.res_y)
        slope = 0.5 + strength * (max_res - 0.5)
        
        # Calculate blend factor t (0.0 to 1.0)
        # We center the transition at 'start' (mapped from 0-1 to -0.5 to 0.5)
        t = np.clip((p - (start - 0.5)) * slope + 0.5, 0.0, 1.0)
        
        # Reshape t for broadcasting: (res_x, res_y, 1) to match color arrays (4,)
        t_3d = t[:, :, np.newaxis]
        
        # Linear interpolation between c1 and c2
        # (res_x, res_y, 4) array
        output_array = (c1 * (1.0 - t_3d) + c2 * t_3d).astype(np.uint8)
        
        return output_array

    def setup_settings(self) -> None:
        """
        Setup effect specific settings (not used here as all controls are via DMX).
        """
        self.settings_elements = []

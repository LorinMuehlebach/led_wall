import numpy as np
import logging
from led_wall.effects.base_effect import BaseEffect
from led_wall.ui.show_inputs import RGBW_Color, Fader

logger = logging.getLogger("utils")


class Circle(BaseEffect):
    """
    Effect that draws a circle on the LED wall.
    Outside the circle is color 1, inside is color 2.
    Faders control radius, X position and Y position.
    X/Y can move the circle center beyond the edges by the radius amount.
    """

    NAME = 'Kreis'
    DESCRIPTION = 'Zeichnet einen Kreis. Außen Farbe 1, innen Farbe 2. Steuerung über Radius, X- und Y-Position.'

    def __init__(self, resolution: tuple[int, int], dimensions: tuple[int, int], rgbw: bool, settings_manager=None) -> None:
        super().__init__(resolution, dimensions, rgbw, settings_manager)

        # Additional inputs: color2 (4), radius (1), pos_x (1), pos_y (1), blend (1)
        self.inputs['color2'] = RGBW_Color([255, 255, 255, 255])
        self.inputs['radius'] = Fader(127)
        self.inputs['pos_x'] = Fader(127)
        self.inputs['pos_y'] = Fader(127)
        self.inputs['blend'] = Fader(0)

        self.res_x, self.res_y = self.resolution
        dim_x, dim_y = self.dimensions

        # Physical size per pixel (meters per pixel)
        self.px_size_x = dim_x / self.res_x if self.res_x > 0 else 1.0
        self.px_size_y = dim_y / self.res_y if self.res_y > 0 else 1.0

        # Pre-calculate pixel coordinate grids in physical space (meters)
        x = np.arange(self.res_x, dtype=np.float32) * self.px_size_x
        y = np.arange(self.res_y, dtype=np.float32) * self.px_size_y
        # indexing='ij' -> first dim is x (width), second dim is y (height)
        self.xv, self.yv = np.meshgrid(x, y, indexing='ij')

        # Max physical extent for radius and position mapping
        self.phys_w = dim_x
        self.phys_h = dim_y

    def run_raw(self, DMX_channels, last_output: np.array) -> np.array:
        """
        Calculates a frame with a filled circle.
        """
        master = self.inputs['master'].value / 255.0
        c_outside = np.array(self.inputs['rgbw_color'].get_channels(), dtype=np.float32) * master
        c_inside = np.array(self.inputs['color2'].get_channels(), dtype=np.float32) * master

        # Radius in physical space: 0-255 maps to 0 .. max(phys_w, phys_h)/2
        max_radius = max(self.phys_w, self.phys_h)
        radius = (self.inputs['radius'].value / 255.0) * max_radius

        # X position in physical space: 0-255 maps to (-radius) .. (phys_w + radius)
        pos_x_norm = self.inputs['pos_x'].value / 255.0
        cx = -radius*2 + pos_x_norm * (self.phys_w + 4 * radius)

        # Y position in physical space: 0-255 maps to (-radius) .. (phys_h + radius)
        pos_y_norm = self.inputs['pos_y'].value / 255.0
        cy = -radius*2 + pos_y_norm * (self.phys_h + 4 * radius)

        # Blend width in physical space: 0 = hard edge, 255 = fade over max radius
        blend_norm = self.inputs['blend'].value / 255.0
        blend_width = blend_norm * max_radius

        # Euclidean distance in physical space (corrected for non-square pixels)
        dist = np.sqrt((self.xv - cx) ** 2 + (self.yv - cy) ** 2)

        if blend_width < 1e-6:
            # Hard edge
            inside_mask = dist <= radius
            output_array = np.empty((self.res_x, self.res_y, 4), dtype=np.uint8)
            output_array[:] = np.clip(c_outside, 0, 255).astype(np.uint8)
            output_array[inside_mask] = np.clip(c_inside, 0, 255).astype(np.uint8)
        else:
            # Smooth blend: t=1 inside, t=0 outside, smooth transition in between
            t = np.clip(1.0 - (dist - radius) / blend_width, 0.0, 1.0)
            t_3d = t[:, :, np.newaxis]  # (res_x, res_y, 1)
            # Reshape colors to (1, 1, 4) for explicit 4-channel broadcasting
            c_in = c_inside.reshape(1, 1, 4)
            c_out = c_outside.reshape(1, 1, 4)
            blended = c_in * t_3d + c_out * (1.0 - t_3d)
            output_array = np.clip(blended, 0, 255).astype(np.uint8)

        return output_array

    def setup_settings(self) -> None:
        """
        Setup effect-specific settings.
        """
        super().setup_settings()

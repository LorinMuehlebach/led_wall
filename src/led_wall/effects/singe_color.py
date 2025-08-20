import numpy as np
from inspect import getfullargspec
import logging

from nicegui import ui

from led_wall.effects.base_effect import BaseEffect
from led_wall.ui.settings_manager import SettingsManager, SettingsElement
from led_wall.datatypes import RGBW_Color, Fader, InputType

logger = logging.getLogger("utils")

class SingleColor(BaseEffect):
    """
    Base class for all effects
    """

    NAME = 'Single Color'
    DESCRIPTION = 'Effect that displays a single color'

    def run_raw(self, DMX_channels,last_output) -> dict[str, object]:
        """
        Returns a dictionary with all inputs for the effect.
        """

        #mix color with master fader
        out_color = np.array(self.inputs['rgbw_color'].get_channels()) * (np.array(self.inputs['master'].get_channels()) / 255)

        output_array = np.full((self.resolution[0], self.resolution[1], 4), out_color, dtype=np.uint8)
        return output_array

    def setup_settings(self) -> None:
        """
        create a settings page for the effect
        """
        self.settings_elements: list[SettingsElement] = []
        self.settings_elements.append(SettingsElement(
            label='Convert to RGBW',
            input=ui.switch,
            default_value=False,
            manager=self.settings_manager,
        ))
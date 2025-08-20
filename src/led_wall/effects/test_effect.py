import numpy as np
from inspect import getfullargspec
import logging

from nicegui import ui

from led_wall.effects.base_effect import BaseEffect
from led_wall.ui.settings_manager import SettingsManager, SettingsElement
from led_wall.datatypes import RGBW_Color, Fader, InputType
from led_wall.ui.slider import Slider

logger = logging.getLogger("utils")

class TestEffect(BaseEffect):
    """
    Base class for all effects
    """

    NAME = 'Test Effect'
    DESCRIPTION = 'Checks all Pixels and colors'


    def __init__(self,*args,**kwargs) -> None:
        """
        Initializes the effect with the given parameters.
        """
        super().__init__(*args,**kwargs) #initialize the base class

        #add new inputs
        self.inputs["background_color"] =  RGBW_Color([0, 0, 0, 0])  # Default color, can be set dynamically

        self.i = 0

    def run_raw(self, DMX_channels,last_output) -> dict[str, object]:
        """
        Returns a dictionary with all inputs for the effect.
        """

        #run effect
        self.i += self.settings_elements[0].value / 100  # Assuming the first setting is a speed slider
        self.i %= self.resolution[0] * self.resolution[1]

        position = int(self.i+0.5)

        output_array = np.full((self.resolution[0], self.resolution[1], 4), self.inputs['background_color'].get_channels(), dtype=np.uint8)
        output_array[position%self.resolution[0], :] = self.inputs['rgbw_color'].get_channels()
        output_array[:, position%self.resolution[1]] = [255, 255, 255, 0]

        #output_array = np.full((self.resolution[1], self.resolution[0], 4), color.get_channels(), dtype=np.uint8)
        return output_array

    def setup_settings(self) -> None:
        """
        create a settings page for the effect
        """
        self.settings_elements: list[SettingsElement] = []
        self.settings_elements.append(SettingsElement(
            label='Speed',
            input=Slider,
            min=0,
            max=100,
            default_value=50,
            manager=self.settings_manager,
        ))
        


# if __name__ in {"__main__", "__mp_main__"}:
#     # Example usage

#     from nicegui import ui, app
#     from led_wall.ui.dmx_channels import DMX_channels_Input
#     from led_wall.io_manager import IO_Manager

#     settings_manager = SettingsManager(path='settings.json')
#     settings_manager.load_from_file()  # Load settings from file if available

#     effect = BaseEffect(screen_dimensions=(35, 60), rgbw=True, settings_manager=settings_manager)

#     ui.label("Preview").classes('text-2xl font-bold mb-4')
#     with ui.element("div").classes('max-w-md'):
#         preview_image = ui.interactive_image().classes('w-full max-w-400')

#     ui.label("Effect Settings").classes('text-2xl font-bold mb-4')
#     with ui.element("div"):
#         effect.ui_settings()  # This would create the settings UI elements for the effect

#     ui.separator()
#     ui.label("Effect Inputs").classes('text-2xl font-bold mb-4')
#     with ui.element("div").classes('w-full'):
#         effect.ui_show() # This would show the UI elements for the effect

#     ui.separator()
    
#     dmx_inputs = DMX_channels_Input(10)
#     ui.label("DMX Channels").classes('text-2xl font-bold mb-4')
#     dmx_inputs.create_ui()

#     effect.on_input_change = lambda channels: dmx_inputs.update_sliders(channels)

#     io_manager = IO_Manager(resolution=(35, 60), dimensions=(6, 3), dmx_inputs=dmx_inputs, framerate=10, RGBW=True)

#     io_manager.init_preview(preview_image=preview_image)

#     io_manager.create_frame = effect.run_raw  # Set the effect's run method as the frame creator

#     #app.on_startup(io_manager.setup_preview)

#     from led_wall.ui.vue_test import OnOff

#     on_off_switch = OnOff("Enable Effect", on_change=lambda e: effect.set_enabled(e.value))

#     ui.run(
#         title='Led Wall',
#         host="0.0.0.0",
#         #window_size=(1800, 600),
#         dark=True
#     )
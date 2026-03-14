import os
import numpy as np
from inspect import getfullargspec
import logging

from nicegui import ui

from led_wall.ui.settings_manager import HiddenSettingsElement, SettingsManager, SettingsElement
from led_wall.datatypes import RGBW_Color, Fader, InputType

logger = logging.getLogger("utils")

class BaseEffect:
    """
    Base class for all effects
    """

    NAME = 'Base Effect'
    DESCRIPTION = 'Base effect that does nothing'
    CONTROLLS_LOOP = False

    def __init__(self,resolution: tuple[int, int],dimensions: tuple[int, int], rgbw: bool, settings_manager: SettingsManager = None) -> None:
        """
        Initializes the effect with the given parameters.
        """
        self.settings_manager:SettingsManager = settings_manager #used to save effect specific settings defined in "setup_settings"
        self.resolution:tuple[int, int] = resolution #pixel resolution
        self.dimensions:tuple[int, int] = dimensions #physical dimensions [m]
        self.rgbw:bool = rgbw
        self.on_input_change:callable = None #callback function to update the DMX faders
        self.io_manager = None # Reference to IO_Manager, set by EffectManager
        self.saved_inputs = settings_manager.get_setting("saved_inputs",{})

        self.setup_settings()

        #add custom inputs after the existing ones but never remove "master", "rgbw_color" and "mode" as they are reserved
        self.inputs : dict[str, InputType] = {
            'master': Fader(),
            'rgbw_color': RGBW_Color([0, 0, 0, 0]),
            'mode': Fader(), #selects the active effect
        }

    def run_raw(self, DMX_channels,last_output:np.array) -> np.array:
        """
        Returns a dictionary with all inputs for the effect.
        """
        self.update_inputs(DMX_channels)
        
        output_array = np.full((self.resolution[0], self.resolution[1], 4), [0,0,0,255], dtype=np.uint8) #placeholder outputs white

        return output_array

    def update_inputs(self,DMX_channels):
        #parse DMX_Channels
        processed_channel = 0
        for input_name in self.inputs:
            input = self.inputs[input_name]
            n_channels = input.n_channels

            #if save input for this input is enabled in the settings load the saved value
            if input.allow_saving and self.saved_inputs and input_name in self.saved_inputs:
                saved_channels = self.saved_inputs[input_name]
                if saved_channels is not None:
                    if input.__class__ == "RGBW_Color":
                        pass
                    input.save_in_settings = True #mark the input as saved in the settings to show it in the UI
                    input.set_channels(saved_channels)
                    return
            
            input.set_channels(DMX_channels[processed_channel:processed_channel + n_channels])
            processed_channel += n_channels

    def setup_settings(self) -> None:
        """
        create a settings page for the effect
        """
        self.settings_elements: list[SettingsElement] = []

        # self.settings_elements.append(SettingsElement(
        #     label='Convert to RGBW',
        #     input=ui.switch,
        #     default_value=False,
        #     manager=self.settings_manager,
        # ))
        # self.settings_elements.append(SettingsElement(
        #     label='Convert to RGBW 2',
        #     input=ui.switch,
        #     default_value=False,
        #     manager=self.settings_manager,
        # ))
        pass

    def start(self):
        """
        called on a switch to this effect
        """
        logger.debug(f"Starting effect {self.NAME}")

    def stop(self):
        """
        called on a switch away from this effect
        """
        logger.debug(f"Stopping effect {self.NAME}")

    def ui_change(self) -> None:
        """
        called if the user changes any of the effect inputs
        calls "on_input_change" with the updated DMX channels
        """
        dmx_channels = []
        for input_name in self.inputs:
            #save the input values in the settings if enabled, but only if there are channels to save
            input = self.inputs[input_name]
            if input.allow_saving:
                val_dict = self.saved_inputs
                if not input.save_in_settings:
                    if input_name in val_dict:
                        del val_dict[input_name]
                else:
                    val_dict[input_name] = input.get_channels()

                self.saved_inputs = val_dict #update the saved inputs with the new values for this input
                self.settings_manager.update_setting("saved_inputs", val_dict) #save the updated values for this input in the settings manager

            dmx_channels += self.inputs[input_name].get_channels()

        #call the callback to update the DMX faders with the new channels
        self.on_input_change(dmx_channels) if self.on_input_change else None

    def ui_settings(self) -> None:
        """
        Create the settings UI for the effect.
        This method is called when the effect is selected in the settings page.
        """
        with ui.column().classes('w-full'):
            for element in self.settings_elements:
                element.create_ui()

    def on_ui_open(self):
        """
        Called when the effect settings dialog is opened.
        """
        pass

    def on_ui_close(self):
        """
        Called when the effect settings dialog is closed.
        """
        pass

        
    def ui_show(self, channels=None) -> None:
        """
        Show the state of the effect in the UI.
        UI element provides all inputs needed at runtime.
        By default it is automatically created by the inputs if the "run" method
        """

        self.ui_inputs = []

        #ui.label(self.DESCRIPTION)
        with ui.row().classes('w-full'):
            for idx, input_element in enumerate(self.inputs):
                if idx == 2:
                    continue #skip "mode" input as it is only used to select the effect but not as an actual input for the effect
                
                with ui.column():
                    element_name = input_element.replace('_', ' ')
                    ui.label(element_name).classes('text-lg font-bold')
                    input_element = self.inputs[input_element]
                    if idx != 0: #if not master fader, allow saving the value in the settings
                        input_element.allow_saving = True #allow saving the input values in the settings

                    input_element.ui_input() #create the UI element for the input, but don't bind it to the input value yet to avoid triggering the callback when the UI is created
                    input_element.on_ui_input = None #reset callback to avoid triggering it when the UI is created
                    self.ui_inputs.append(input_element)

        #add callback to update the DMX channels when the UI is changed, but only if there are channels provided 
        # (to avoid triggering it when the UI is created) 
        if channels is not None:
            self.update_inputs(channels)
            for input in self.ui_inputs:
                input.on_ui_input = lambda e, self=self: self.ui_change()

                # #TODO check if needed
                # if hasattr(input, "slider"): #if the input has a slider element, bind the slider value to the input value to update it when the slider is changed
                #     input.slider.bind_value(input, 'value') #bind the slider value to the input value to update it when the slider is changed


if __name__ in {"__main__", "__mp_main__"}:
    # Example usage
    if __name__ == '__mp_main__' and 'NICEGUI_STARTED' not in os.environ:
        from nicegui import ui, app
        from led_wall.ui.dmx_channels import DMX_channels_Input
        from led_wall.io_manager import IO_Manager

        settings_manager = SettingsManager(path='settings.json')
        settings_manager.load_from_file()  # Load settings from file if available

        effect = BaseEffect(resolution=(35, 60), dimensions=(6, 3), rgbw=True, settings_manager=settings_manager)

        ui.label("Preview").classes('text-2xl font-bold mb-4')
        with ui.element("div").classes('max-w-md'):
            preview_image = ui.interactive_image().classes('w-full max-w-400')

        ui.label("Effect Settings").classes('text-2xl font-bold mb-4')
        with ui.element("div"):
            effect.ui_settings()  # This would create the settings UI elements for the effect

        ui.separator()
        ui.label("Effect Inputs").classes('text-2xl font-bold mb-4')
        with ui.element("div").classes('w-full'):
            effect.ui_show() # This would show the UI elements for the effect

        ui.separator()
        
        dmx_inputs = DMX_channels_Input(10)
        ui.label("DMX Channels").classes('text-2xl font-bold mb-4')
        dmx_inputs.create_ui()

        #ui.radio([1], value=0).props('inline')

        effect.on_input_change = lambda channels: dmx_inputs.update_sliders(channels)

        io_manager = IO_Manager(settings_manager, framerate=30, preview_in_window=True)

        io_manager.init_preview(preview_image=preview_image)

        io_manager.create_frame = effect.run_raw  # Set the effect's run method as the frame creator

        app.on_startup(io_manager.setup_preview)
        io_manager.start_loop()
        os.environ["NICEGUI_STARTED"] = "true" #needed so it only starts once
        

    ui.run(
        title='Led Wall',
        host="0.0.0.0",
        #window_size=(1800, 600),
        dark=True
    )
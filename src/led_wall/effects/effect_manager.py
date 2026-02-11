import logging
from threading import Thread
import time
import numpy as np
import cv2

from nicegui import ui

from led_wall.effects.base_effect import BaseEffect
from led_wall.io_manager import IO_Manager
from led_wall.ui.preview_window import preview_setup, create_preview_frame
from led_wall.datatypes import Color
from led_wall.ui.dmx_channels import DMX_channels_Input
from led_wall.ui.settings_manager import SettingsManager, SettingsElement
import led_wall.effects as effects_class

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class EffectManager():
    nof_effects = 8

    def __init__(self,IO_manager:IO_Manager,settings_manager:SettingsManager) -> None:
        self.IO_manager = IO_manager
        self.settings_manager = settings_manager

        #effect manager needs to be reloaded on changes to the IO_manager
        self.resolution = IO_manager.resolution
        self.dimension = IO_manager.dimensions
        self.pixel_channels = IO_manager.pixel_channels
        self.rgbw = IO_manager.pixel_channels == 4

        self.effect_type: list[SettingsElement] = []
        self.effects: list[BaseEffect] = []
        self.effect_setting_managers = []

        self.ui_select = []
        self.preview_image = None

        self.active_effect = 0

        self.status = "setup"

    def setup(self):
        #initialize the effects
        self.available_effects = effects_class.get_effects()
        self.default_effect = self.available_effects[0]

        #self.settings = []
        effect_options = {effect.__name__: effect.NAME for effect in self.available_effects}

        for i in range(self.nof_effects):
            settings_element =SettingsElement(
                label=None,
                input=ui.select,
                default_value=self.default_effect.__name__,
                settings_id=f'active_effect_{i}',
                on_change=lambda e, index=i: self.on_effect_selected(e, index),
                options=effect_options,
                manager=self.settings_manager,
            )
            self.effect_type.append(settings_element)
            effect_cls = effects_class.get_effect_class(settings_element.value)
            self.effect_setting_managers.append(SettingsManager(self.settings_manager,name=f"effect_settings_{i}"))
            effect = effect_cls(self.resolution, self.dimension, self.rgbw, self.effect_setting_managers[i])
            effect.io_manager = self.IO_manager
            self.effects.append(effect)
        self.effects[self.active_effect].start()

        self.status = "ready"

        self.effect_manager_ui.refresh()
        self.change_active_effect(index=self.active_effect)

        self.IO_manager.create_frame = self.run_loop
        

    @ui.refreshable
    def effect_manager_ui(self):
        self.all_tabs = []
        # Set initial value to prevent default selection of tab 1 during refresh/rebuild
        initial_tab_label = f'{self.active_effect + 1}'
        with ui.tabs(value=initial_tab_label).classes('w-full q-dark').on('update:model-value', self.on_tab_change) as self.tabs:
            for i in range(self.nof_effects):
                self.all_tabs.append(ui.tab(f'{i+1}'))
        
        # Sync the tabs.value to the specific tab object
        self.tabs.value = self.all_tabs[self.active_effect]

        with ui.tab_panels(self.tabs, value=self.all_tabs[self.active_effect]).classes('w-full'):
            for tab_idx in range(len(self.effect_type)):
                with ui.tab_panel(self.all_tabs[tab_idx]):
                    with ui.row().classes('w-full'):
                        with ui.element("div").classes('min-w-48').style('max-width: 180px').style('max-width: 180px'):
                            self.effect_type[tab_idx].create_ui()
                            
                            ui.element("div").style('height: 16px')  # Spacer
                            ui.label(self.effects[tab_idx].DESCRIPTION)
                            ui.element("div").style('height: 16px')  # Spacer
                            

                            with ui.dialog() as dialog, ui.card().classes('w-full max-w-full min-h-96').style('display: flex; flex-direction: column;'):
                                with ui.element("div").classes('flex-grow overflow-auto w-full'):
                                    self.effects[tab_idx].ui_settings()
                                ui.separator()

                                with ui.row().classes('w-full justify-end'):
                                    # Hook into dialog open/close to manage resources (e.g. video preview)
                                    def open_settings(eff=self.effects[tab_idx], dlg=dialog):
                                        eff.on_ui_open()
                                        dlg.open()

                                    def close_settings(eff=self.effects[tab_idx], dlg=dialog):
                                        eff.on_ui_close()
                                        dlg.close()

                                    ui.button('Close', on_click=close_settings)
                            
                            
                            ui.button('Einstellungen', on_click=open_settings)
                        with ui.element("div").classes('flex-grow'):
                            self.effects[tab_idx].ui_show()        


    @ui.refreshable
    def effect_setting_ui(self):
        self.effects[self.active_effect].ui_settings()

    @ui.refreshable
    def effect_show_ui(self):
        self.effects[self.active_effect].ui_show()

    def on_tab_change(self, event):
        """
        Called when a tab is changed in the tab_panels.
        Updates the active effect based on the selected tab.
        """
        if self.status == "setup":
            return
        
        # Find the index of the selected tab
        try:
            # event.args might be a string (label) or a list [label]
            val = event.args[0] if isinstance(event.args, list) else event.args
            tab_index = int(val) - 1  # Convert from 1-based to 0-based index
        except (ValueError, TypeError, IndexError):
            return

        channels = self.IO_manager.get_channels()
        slider_tab_idx = self.value_to_effect_idx(channels[5])
        if tab_index != slider_tab_idx:
            channels[5] = int(tab_index / self.nof_effects * 256)  # Update the channel value to reflect the new effect
            self.IO_manager.update_DMX_channels(channels)  # Trigger an update to apply the new effect immediately

    def change_active_effect(self, new_effect=None, index=None):
        if self.status == "setup":
            return
        
        if new_effect is not None:
            self.effects[self.active_effect].stop()
            self.effects[self.active_effect] = new_effect
        elif index is not None:
            if index < 0 or index >= self.nof_effects:
                raise ValueError(f"Index {index} is out of bounds for effects list.")
            self.effects[self.active_effect].stop()
            self.active_effect = index
        else:
            raise ValueError("Either new_effect or index must be provided to change the active effect.")
        
        #set channels to current dmx channels
        channels = self.IO_manager.get_channels()
        self.effects[self.active_effect].update_inputs(channels)
        self.effects[self.active_effect].start()
        self.effects[self.active_effect].on_input_change = self.IO_manager.update_DMX_channels

        # Sync UI tabs if they exist
        if hasattr(self, 'tabs') and self.tabs and hasattr(self, 'all_tabs'):
            # Programmatic update of tabs.value switches the visible tab
            self.tabs.value = self.all_tabs[self.active_effect]

        # Refresh dependent UIs
        self.effect_setting_ui.refresh()
        self.effect_show_ui.refresh()

    def on_effect_selected(self, event, index):
        """
        a new effect has been selected from the drop down menu
        """
        if self.status == "setup":
            return
        
        #initialize the new effect
        effect_cls = effects_class.get_effect_class(event.value)
        new_effect = effect_cls(self.resolution, self.dimension, self.rgbw, self.effect_setting_managers[index])
        new_effect.io_manager = self.IO_manager

        # If the effect being changed is the active one, use change_active_effect
        # to handle stop() and start() properly.
        if index == self.active_effect:
            self.change_active_effect(new_effect=new_effect)
        else:
            self.effects[index] = new_effect
            
        self.effect_manager_ui.refresh()

    def on_channel_change(self, event, index):
        if event is not None and event.value is None:
            return

        logger.debug(f"Changing effect to {index} ({self.effects[self.active_effect].NAME})")
        self.change_active_effect(index=index)
        
        #update UI
        for i, ui_element in enumerate(self.ui_select):
            if i == self.active_effect:
                if ui_element["radio"].value is None:
                    ui_element["radio"].value = ''
            else:
                ui_element["radio"].value = None

    def value_to_effect_idx(self, value):
        """
        converts artnet value to an effect instance
        """
        nof_effects = len(self.effects)
        effect_index = int(value / 256 * nof_effects) % nof_effects

        return effect_index

    def set_preview_image(self, preview_image: ui.interactive_image) -> None:
        self.preview_image = preview_image

    def run_loop(self,channels, last_output):
        """
        loop called by io manager
        """
        #check and switch active effect
        new_effect_index = self.value_to_effect_idx(channels[5])  # Example: using the first channel value to determine effect
        if new_effect_index != self.active_effect:
            self.change_active_effect(index=new_effect_index)

        self.effects[self.active_effect].update_inputs(channels)
        output = self.effects[self.active_effect].run_raw(channels, last_output)
        
        if self.IO_manager.preview_in_window:
            # If a preview image is set, update it with the new frame
            preview = create_preview_frame(
                output_buffer=self.IO_manager.output_buffer,
                resolution=self.resolution,
                pixel_channels=self.pixel_channels,
                preview_width=self.preview_width,
                preview_height=self.preview_height
            )
            cv2.imshow("Output", preview)
            cv2.waitKey(1)

        return output

    def init_preview(self,preview_image: ui.interactive_image) -> callable:
        """
        initializes the preview window for the led wall.
        """
        self.preview_height = 200
        aspect_ratio = self.dimension[0] / self.dimension[1]
        self.preview_width = int(self.preview_height * aspect_ratio)
        self.preview_image = preview_image

    def setup_preview(self) -> None:
        """
        sets up the preview window for the led wall.
        """        
        if not self.preview_image:
            raise ValueError("Preview image not initialized. Call init_preview() first.")

        # Closure to get the latest buffer and parameters
        def get_preview():
            return create_preview_frame(
                output_buffer=self.IO_manager.output_buffer,
                resolution=self.resolution,
                pixel_channels=self.pixel_channels,
                preview_width=self.preview_width,
                preview_height=self.preview_height
            )

        self.preview_timer = preview_setup(self.preview_image, io_manager=self.IO_manager)
    
    def shutdown(self):
        """
        shuts down the effect manager and all effects.
        """
        # Stop preview timer if it exists
        if hasattr(self, 'preview_timer') and self.preview_timer:
            try:
                self.preview_timer.deactivate()
                logger.info("Deactivated preview timer")
            except Exception as e:
                logger.error(f"Error deactivating preview timer: {e}")

        # Stop the active effect
        if hasattr(self, 'effects'):
            try:
                self.effects[self.active_effect].stop()
                logger.info("Stopped active effect")
            except Exception as e:
                logger.error(f"Error stopping effect: {e}")
        
        # Stop the IO manager loop
        if self.IO_manager:
            try:
                self.IO_manager.stop_loop()
                logger.info("Stopped IO manager loop")
            except Exception as e:
                logger.error(f"Error stopping IO manager: {e}")
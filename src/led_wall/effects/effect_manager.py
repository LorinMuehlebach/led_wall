import logging
from threading import Thread
import time
import numpy as np
import cv2

from nicegui import ui

from led_wall.effects.base_effect import BaseEffect
from led_wall.io_manager import IO_Manager
from led_wall.ui.preview_window import preview_setup
from led_wall.datatypes import Color
from led_wall.ui.dmx_channels import DMX_channels_Input
from led_wall.ui.preview_window import preview_setup
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

        self.ui_select = []
        self.preview_image = None

        self.active_effect = 0

        self.status = "setup"

        #initialize the effects
        self.available_effects = effects_class.get_effects()
        self.default_effect = self.available_effects[0]

        #self.settings = []
        self.settings_elements = []
        self.effects: list[BaseEffect] = []
        self.effect_setting_managers = []

        for i in range(self.nof_effects):
            settings_element =SettingsElement(
                label=None,
                input=ui.select,
                default_value=self.default_effect.NAME,
                settings_id=f'active_effect_{i}',
                on_change=lambda e, index=i: self.on_effect_selected(e, index),
                options=[effect.NAME for effect in self.available_effects],
                manager=self.settings_manager,
            )
            self.settings_elements.append(settings_element)
            effect_cls = effects_class.get_effect_class(settings_element.value)
            self.effect_setting_managers.append(SettingsManager(settings_manager,name=f"effect_settings_{i}"))
            self.effects.append(effect_cls(self.resolution, self.dimension, self.rgbw, self.effect_setting_managers[i]))
        self.effects[self.active_effect].start()

        self.status = "ready"

        self.IO_manager.create_frame = self.run_loop


    @ui.refreshable
    def effect_manager_ui(self):
        effects = effects_class.get_effects()

        with ui.list():
            for i in range(self.nof_effects):
                container = ui.item()
                container.props('tag="label"')
                with container:
                    radio =ui.radio([''], on_change=lambda e, index=i: self.on_channel_change(e, index))
                    if i == self.active_effect:
                        radio.value = ''

                    self.settings_elements[i].create_ui()

                self.ui_select.append({"radio": radio, "select": self.settings_elements[i]})

                #self.effects.append(effect)

    @ui.refreshable
    def effect_setting_ui(self):
        self.effects[self.active_effect].ui_settings()

    @ui.refreshable
    def effect_show_ui(self):
        self.effects[self.active_effect].ui_show()

    def change_active_effect(self,new_effect=None,index=None):
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
        
        self.effects[self.active_effect].start()
        self.effects[self.active_effect].on_input_change = self.IO_manager.update_DMX_channels
        #self.IO_manager.create_frame = self.effects[self.active_effect].run_raw
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

        if self.active_effect == index:
            self.change_active_effect(new_effect=new_effect)

        self.effects[index] = new_effect

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

    def set_preview_image(self, preview_image: ui.interactive_image) -> None:
        self.preview_image = preview_image

    def run_loop(self,channels, last_output):
        """
        loop called by io manager
        """
        self.effects[self.active_effect].update_inputs(channels)
        output = self.effects[self.active_effect].run_raw(channels, last_output)
        
        # if self.IO_manager.preview_in_window:
        #     # If a preview image is set, update it with the new frame
        #     cv2.imshow("Output", self.create_preview_frame())
        #     cv2.waitKey(1)

        return output


    #needs to be static to be handled correctly it cannot depend on self
    def create_preview_frame(self) -> np.ndarray:
        """
        returns the preview frame for the led wall.
        """

        frame = np.zeros((self.resolution[0], self.resolution[1], 3), dtype=np.uint8)
        if self.IO_manager.pixel_channels == 4:
            for i in range(self.resolution[0]):
                for j in range(self.resolution[1]):
                    frame[i,j] = np.array(Color.convert_rgbw2rgb(self.IO_manager.output_buffer[i,j]),dtype=np.uint8)
        else:
            frame = self.IO_manager.output_buffer


        frame = np.transpose(frame,(1,0,2)) #flip x and y axis
        frame = np.flip(frame, axis=2) # cv2 expects BGR format so we flip the RGB channels
        preblur_scaling = 4
        scaled_frame = cv2.resize(frame, (self.resolution[0]*preblur_scaling, self.resolution[1]*preblur_scaling), interpolation=cv2.INTER_AREA)

        #blurr the output
        #kernel = np.ones((10,20),np.float32)/200
        #blurred_image = cv2.filter2D(scaled_frame,-1,kernel)
        #blurred_image = cv2.GaussianBlur(scaled_frame,(20,20),0)
        blurred_image = cv2.GaussianBlur(scaled_frame, (15, 15), sigmaX=2, sigmaY=2)
        final_frame = cv2.resize(blurred_image, (self.preview_width, self.preview_height), interpolation=cv2.INTER_AREA)
        return final_frame

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

        #get_preview_frame = partial(self.create_preview_frame, self.output_buffer, self.preview_width, self.preview_height)
        preview_setup(self.preview_image, get_preview_frame=self.create_preview_frame)
        
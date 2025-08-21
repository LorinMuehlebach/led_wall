import time
import numpy as np
import cv2
from functools import partial
from threading import Thread

import asyncio
from pyartnet import ArtNetNode


from nicegui import ui

from led_wall.ui.settings_manager import SettingsElement, SettingsManager
from led_wall.utils import Color
from led_wall.ui.dmx_channels import DMX_channels_Input
from led_wall.ui.preview_window import preview_setup

class IO_Manager():
    """
    handles the io loop for the led wall.

    """
    output_buffer: np.ndarray = None


    def __init__(self,settings_manager:SettingsManager,framerate:int=30,preview_in_window:bool=False) -> None:
        """
        initializes the io manager.

        Parameters:
            resolution (tuple[int, int]): The resolution of the LED Wall
            dimensions (tuple[int, int]): The dimensions of the LED wall in Meter
            dmx_channel_inputs (DMX_channels_Input): The DMX channel inputs manager
            RGBW (bool): Whether the output is RGBW or not.
            framerate (int): The framerate of the output.

        """
        self.settings_manager = SettingsManager(parent=settings_manager, name="io_settings")
        self.dmx_channel_inputs = DMX_channels_Input(10)

        self.output_artnet_ip = '192.168.178.100'
        self.pixel_channels = 4
        self.resolution = (30,58) #resolution of the LED wall in pixels
        self.dimensions = (6, 3) #dimension of the LED wall in meters
        self.framerate = framerate
        self.preview_in_window = preview_in_window

        self.dmx_address = 1
        
        self.settings_elements = [
            SettingsElement(
                label='Auflösung Breite',
                input=ui.number,
                default_value=self.resolution[0],
                settings_id='resolution_width',
                on_change=lambda e, self=self: setattr(self, 'resolution', (int(e.value) if e.value is not None else self.resolution[0], self.resolution[1])),
                precision=0,
                suffix=" px",
                manager=self.settings_manager,
            ),
            SettingsElement(
                label='Auflösung Höhe',
                input=ui.number,
                default_value=self.resolution[1],
                settings_id='resolution_height',
                on_change=lambda e, self=self: setattr(self, 'resolution', (self.resolution[0], int(e.value) if e.value is not None else self.resolution[1])),
                precision=0,
                suffix=" px",
                manager=self.settings_manager,
            ),
            SettingsElement(
                label='Abmessungen Breite',
                input=ui.number,
                default_value=self.dimensions[0],
                settings_id='dimensions_width',
                on_change=lambda e, self=self: setattr(self, 'dimensions', (int(e.value) if e.value is not None else self.dimensions[0], self.dimensions[1])),
                precision=0,
                suffix=" m",
                manager=self.settings_manager
            ),
            SettingsElement(
                label='Abmessungen Höhe',
                input=ui.number,
                default_value=self.dimensions[1],
                settings_id='dimensions_height',
                on_change=lambda e, self=self: setattr(self, 'dimensions', (self.dimensions[0], int(e.value) if e.value is not None else self.dimensions[1])),
                precision=0,
                suffix=" m",
                manager=self.settings_manager
            ),
            SettingsElement(
                label='Framerate',
                input=ui.number,
                default_value=self.framerate,
                settings_id='framerate',
                on_change=lambda e, self=self: setattr(self, 'framerate', int(e.value) if e.value is not None else self.framerate),
                precision=0,
                manager=self.settings_manager
            ),
            SettingsElement(
                label='RGBW LEDs',
                input=ui.switch,
                default_value=self.pixel_channels == 4,
                manager=self.settings_manager
            ),
            SettingsElement(
                label='preview in window',
                input=ui.switch,
                default_value=self.preview_in_window,
                on_change=lambda e, self=self: setattr(self, 'preview_in_window', e.value),
                manager=self.settings_manager
            ),
            SettingsElement(
                label='Quelle',
                input=ui.select,
                settings_id='input_source',
                default_value="none",
                options=["artnet","dmx","none"],
                manager=self.settings_manager
            ),
            SettingsElement(
                label='DMX Adresse',
                input=ui.number,
                settings_id='dmx_address',
                default_value=self.dmx_address,
                on_change=lambda e, self=self: setattr(self, 'dmx_address', int(e.value) if e.value is not None else self.dmx_address),
                precision=0,
                manager=self.settings_manager
            ),
            SettingsElement(
                label='Artnet IP',
                input=ui.input,
                settings_id='artnet_ip',
                default_value=self.output_artnet_ip,
                on_change=lambda e, self=self: self.output_artnet_init(e.value) if e.value else None,
                manager=self.settings_manager
            ),
        ]


        self.output_buffer = np.zeros((self.resolution[0], self.resolution[1], self.pixel_channels), dtype=np.uint8)
        
        self.Output_ArtNetNode = None  # ArtNetNode instance for output

        self.create_frame = None #callback function to the selected effect

        self.ts_last_frame = 0
        self.run_thread = Thread(target=self.run_loop, daemon=True)

    @ui.refreshable
    def ui_settings(self) -> None:
        """
        Create the settings UI for this object
        This method is called on create ui settings
        """
        with ui.column().classes('w-full'):
            for element in self.settings_elements:
                element.create_ui()

    @ui.refreshable
    def dmx_channel_ui(self) -> None:
        self.dmx_channel_inputs.create_ui()

    def start_loop(self) -> None:
        self.run = True
        self.run_thread.start()

    def stop_loop(self) -> None:
        self.run = False
        try:
            self.run_thread.join()
        except Exception as e:
            print(f"Error stopping loop: {e}")

    def __del__(self):
        self.stop_loop()

    def run_loop(self):
        """
        loop which runs at the defined framerate
        """

        while self.run:
            while time.time() - self.ts_last_frame < 1 / self.framerate:
                # wait until the next frame is due
                time.sleep(max((1 / self.framerate) - (time.time() - self.ts_last_frame) - 0.001, 0.001))
            
            self.ts_last_frame = time.time()

            channels = self.dmx_channel_inputs.get_channels()
            frame = self.create_frame(channels, last_output=self.output_buffer) if self.create_frame else self.output_buffer

            self.output_buffer = frame

            #self.update_artnet()

    def output_artnet_init(self,ip):
        pass
        # self.Output_ArtNetNode = ArtNetNode(ip, 6454)
        # self.universes = []
        # for i in range(self.resolution[0]):
        #     u = self.Output_ArtNetNode.add_universe(i)
        #     u.add_channel(1,self.resolution[1] * self.pixel_channels)
        #     self.universes.append(u)

    def update_artnet(self):
        if not self.Output_ArtNetNode:
            return

        for i, u in enumerate(self.universes):
            u.update(self.output_buffer[i]) #todo expand array

    def update_DMX_channels(self, channels):
        self.dmx_channel_inputs.update_sliders(channels)

    #needs to be static to be handled correctly it cannot depend on self
    def create_preview_frame(self) -> np.ndarray:
        """
        returns the preview frame for the led wall.
        """

        frame = np.zeros((self.resolution[0], self.resolution[1], 3), dtype=np.uint8)
        if self.pixel_channels == 4:
            for i in range(self.resolution[0]):
                for j in range(self.resolution[1]):
                    frame[i,j] = np.array(Color.convert_rgbw2rgb(self.output_buffer[i,j]),dtype=np.uint8)
        else:
            frame = self.output_buffer


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
        aspect_ratio = self.dimensions[0] / self.dimensions[1]
        self.preview_width = int(self.preview_height * aspect_ratio)
        self.preview_image = preview_image

    def setup_preview(self) -> None:
        """
        sets up the preview window for the led wall.
        """
        if self.preview_in_window:
            return #do not show in browser
        
        if not self.preview_image:
            raise ValueError("Preview image not initialized. Call init_preview() first.")

        #get_preview_frame = partial(self.create_preview_frame, self.output_buffer, self.preview_width, self.preview_height)
        preview_setup(self.preview_image, get_preview_frame=self.create_preview_frame)
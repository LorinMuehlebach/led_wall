from __future__ import annotations
import logging
import numpy as np

from nicegui import ui, binding
from nicegui.events import ValueChangeEventArguments

from led_wall.ui.settings_element import SettingsElement
from led_wall.ui.slider import Slider

from led_wall.datatypes import Fader

logger = logging.getLogger("utils")

class DMX_channels_Input():
    ignore_external = binding.BindableProperty()
    channels = binding.BindableProperty()

    def __init__(self,n_channels:int,on_change=None):
        self.n_channels = n_channels
        self.channels = {i: 0 for i in range(n_channels)}
        self.sliders = []
        self.ignore_external = False
        self.on_change = on_change

    def create_ui(self):
        with ui.row().classes('w-full'):
            for i in range(self.n_channels):
                with ui.column().classes('w-1/10 flex items-center justify-center'):
                    ui.label(f'{i+1}').classes('w-1/4')
                    fader = Fader() #todo move on change
                    fader.ui_input(on_change=lambda e, channel=i: self._on_channel_change(channel, e))
                    fader.slider.bind_value(self.channels, i)

                    self.sliders.append(fader)

        SettingsElement(
            label='Ignore external inputs',
            input=ui.switch,
            default_value=True,
        ).input.bind_value(self,'ignore_external')

    def _on_channel_change(self, channel_index: int, event) -> None:
        """
        Handles the change event of a channel input.
        This method can be overridden to handle channel changes.
        """
        self._on_change(event)
        #logger.debug(f'Not implemented, Channel {channel_index + 1} changed to {event.value}')

    def _on_change(self,e):
        self.on_change(e) if self.on_change else None

    def update_sliders(self, values: list[int], external=False) -> None:
        """
        Updates the sliders with new values.
        :param values: List of values to set for each channel.
        """
        # if external and self.external_ignore_switch.value:
        #     logger.info('External ignore switch is on, not updating sliders.')
        #     return
        
        # if len(values) != self.n_channels:
        #     raise ValueError(f'Expected {self.n_channels} values, got {len(values)}')
        
        if external and self.ignore_external:
            logger.debug('External ignore switch is on, not updating sliders.')
            return

        for i, value in enumerate(values):
            value = max(0, min(255, value))
            self.channels[i] = value


        self._on_change(ValueChangeEventArguments(sender=self,client=external,value=self.get_channels()))
            
    def get_channels(self) -> list[int]:
        """
        Returns the current values of all channels.
        :return: List of channel values.
        """
        return [value for value in self.channels.values()]

if __name__ in {"__main__", "__mp_main__"}:
    import threading

    dmx_inputs = DMX_channels_Input(10)

    dmx_inputs.create_ui()


    dmx_inputs.update_sliders([125]*10)  # Example update

    #dmx_inputs.external_ignore_switch.value = True  # Example of setting the external ignore switch
    

    def delayed_update():
        import time
        while True:
            time.sleep(5)
            print("Updating sliders after 2 seconds")
            dmx_inputs.update_sliders(np.random.randint(0, 256, size=10).tolist(), external=True)
            print(dmx_inputs.get_channels())

    if __name__ == '__mp_main__':
        #guard to only run this once
        threading.Thread(target=delayed_update,daemon=True).start()  # Update after 5 seconds

    ui.run(
        title='dmx_test',
        host="0.0.0.0",
        #window_size=(1800, 600),
        dark=True
    )
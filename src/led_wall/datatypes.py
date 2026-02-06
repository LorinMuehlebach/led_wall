import logging

from nicegui import ui

from led_wall.ui.slider import Slider
from led_wall.ui.color_picker import ColorPicker
from led_wall.ui.color_wheel import ColorWheel
from led_wall.utils import Color

logger = logging.getLogger("utils")

class InputType:
    """
    Base class for all data types used in the application.
    This class can be extended to create custom data types.
    """
    number_of_channels: int = 1
    ignore_inputs: bool = False  # If True, the input will not be updated from input channels
    on_ui_input = None

    def get_channels(self) -> list[int]:
        """
        Returns the value of the DataType as a list of DMX channels.
        This method should be overridden by subclasses to provide custom behavior.
        """
        raise NotImplementedError("Subclasses must implement this method")

    def set_channels(self, channels: list[int]) -> None:
        """
        Sets the value of the DataType from a list of DMX channels.
        This method should be overridden by subclasses to provide custom behavior.
        """
        raise NotImplementedError("Subclasses must implement this method")  

    def ui_input(self, **kwargs) -> ui.element:
        """
        Creates a NiceGUI input element for the data type.
        This method should be overridden by subclasses to provide a custom input element.
        """
        raise NotImplementedError("Subclasses must implement this method")

class Fader(InputType):
    """
    Represents a fader from a single channel.
    """
    def __init__(self, value: int = 0, add_value_label =True) -> None:
        self.value = value   
        self.add_value_label = add_value_label
        self.n_channels = 1

    def get_channels(self) -> list[int]:
        """Returns the fader value as a list."""
        return [self.value]
    
    def set_channels(self, channels: list[int]) -> None:
        """Sets the fader value from a list."""
        if len(channels) != 1:
            raise ValueError("Fader must have exactly one channel")
        if not (0 <= channels[0] <= 255):
            raise ValueError("Fader value must be between 0 and 255")
        
        if self.ignore_inputs:
            return
        
        self.value = channels[0]

    def ui_input(self, **kwargs) -> ui.element:
        """
        Creates a NiceGUI input element for the fader.
        """
        external_on_change = kwargs.get("on_change") 
        
        def handle_change(e):
            self._on_change(e)
            if external_on_change:
                external_on_change(e)

        kwargs["on_change"] = handle_change
        with ui.column():
            self.slider = Slider(min=0, max=255, value=0, vertical=True, reverse=True,**kwargs)
            self.slider.bind_value(self, 'value')
            if self.add_value_label:
                ui.label().bind_text_from(self.slider, 'value')
        return self.slider

    def _on_change(self,e):
        self.on_ui_input(self.get_channels()) if self.on_ui_input else None

class ColorInput(Color,InputType):
    """
        A class to represent a color Input in RGB or RGBW format.

    """

    def __init__(self, *args,**kwargs):
        self.color_picker = None
        super().__init__(*args,**kwargs)

    def set_channels(self, channels):
        super().set_channels(channels)
        if self.color_picker:
            self.color_picker.set_color(self.as_hex()) 

    def ui_input(self, **kwargs) -> ui.element:
        """Creates a NiceGUI input element for the color."""
        # if self.MODE == 'rgbw':
        #     return ui.color_input(value=self.as_hex(), **kwargs)
        self.color_picker = ColorPicker(value=self.as_hex(),on_pick=lambda e :self._on_change(e.color),enable_white=self.MODE == 'rgbw', **kwargs)
        self.color_picker.set_color(self.as_hex())
        return self.color_picker

    def _on_change(self, value: str) -> None:
        """Handles changes to the input element."""
        self.set_hex(value)

        self.on_ui_input(self.get_channels()) if self.on_ui_input else None

class RGB_Color(ColorInput):
    """
        A class to represent a color in RGB format.
    """
    MODE = 'rgb'

    def __init__(self, *args, **kwargs):
        kwargs["type"] = 'rgb' #force RGB mode
        self.n_channels = 3
        super().__init__(*args, **kwargs)

class RGBW_Color(ColorInput):
    """
        A class to represent a color in RGBW format.
    """
    MODE = 'rgbw'
    number_of_channels: int = 4
    def __init__(self, *args, **kwargs):
        kwargs["type"] = 'rgbw' #force RGBW mode
        self.n_channels = 4
        super().__init__(*args, **kwargs)

class RGBWPicker(ColorInput,InputType):
    """
        A class to represent a color picker in RGBW format.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    def ui_input(self, **kwargs) -> ui.element:
        """Creates a NiceGUI input element for the color."""
        # if self.MODE == 'rgbw':
        #     return ui.color_input(value=self.as_hex(), **kwargs)
        with ui.row():
            self.color_picker = ColorWheel(value=self.as_hex(),**kwargs)
            self.slider = Slider(min=0, max=255, value=0, vertical=True, reverse=True, **kwargs)
        return
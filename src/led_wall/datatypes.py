import logging

from nicegui import ui

from led_wall.ui.slider import Slider
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
    #save value in settings
    allow_saving = False
    save_in_settings = False

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
        self.value = value   #not used anymore?
        self.add_value_label = add_value_label
        self.n_channels = 1
        self.slider = None

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
        if self.slider:
            self.slider.value = self.value

    def ui_input(self, **kwargs) -> ui.element:
        """
        Creates a NiceGUI input element for the fader.
        """
        external_on_change = kwargs.get("on_change") 
        add_binding = False #kwargs.pop("add_binding",True)
        
        def handle_change(e):
            if self.slider.value == self.value: #avoid triggering on_change if the value is the same
                return
            
            self.value = self.slider.value
            self._on_change(e)
            if external_on_change:
                external_on_change(e)

        kwargs["on_change"] = handle_change
        with ui.column():
            self.slider = Slider(min=0, max=255, value=0, vertical=True, reverse=True,**kwargs)
            if self.add_value_label:
                ui.label().bind_text_from(self.slider, 'value')

            if self.allow_saving:
                self.checkbox = ui.checkbox('save',on_change=lambda e: self._on_change(None))
                self.checkbox.bind_value(self,'save_in_settings')
        
        #if add_binding:
        #self.slider.bind_value(self, 'value')

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
        self.color_picker = ColorWheel(
            value=self.as_hex(),
            inline=True,
            on_change=lambda color: self._on_change(color),
        )
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
        self.slider = None
        self._value = [0, 0, 0, 0]
        super().__init__(*args, **kwargs)

    def ui_input(self, **kwargs) -> ui.element:
        """Creates a NiceGUI input element for the color."""

        self.value = self._value
        with ui.column():
            with ui.row().classes('items-stretch'):
                self.color_picker = ColorWheel(
                    value=self.as_hex(mode='rgb'), #color wheel only supports RGB, we will ignore the white channel here
                    inline=True,
                    on_change=lambda color: self._color_changed(color),
                )
                self.slider = Fader(value=self._value[3])
                self.slider.allow_saving = False
                self.slider.ui_input(on_change=lambda e: self._white_changed(e.value))

            if self.allow_saving:
                self.checkbox = ui.checkbox('save',on_change=lambda e: self._on_change(None))
                self.checkbox.bind_value(self,'save_in_settings')

        return self.color_picker
    
    def _white_changed(self, value: int) -> None:
        if isinstance(value,list):
            value = value[3]
        if value == self._value[3]:
            return
        self._value[3] = value
        
        self._on_change(None)

    def _color_changed(self, value: str) -> None:
        self.value = self._value #update RGB values from current channels to avoid losing the white channel value
        if value == self.as_hex(mode='rgb'):
            return
        self.set_hex(value,type='rgb') #update RGB values
        self._on_change(None)

    def _on_change(self,e):
        self.on_ui_input(self.get_channels()) if self.on_ui_input else None
    
    def set_channels(self, channels: list[int]) -> None:
        #super().set_channels(channels)
        if self.ignore_inputs:
            return
        
        self._value = channels
        if self.color_picker:
            self.value = self._value
            self.color_picker.set_color(self.as_hex(mode='rgb')) #update color picker, ignore white channel
        if self.slider:
            self.slider.value = self._value[3]

    def get_channels(self) -> list[int]:
        """Returns the fader value as a list."""
        return self._value

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
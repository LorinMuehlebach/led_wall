from typing import Optional

from typing_extensions import Self

from nicegui.element import Element
from nicegui.events import ColorPickEventArguments, GenericEventArguments, Handler, handle_event
from nicegui.elements.mixins.disableable_element import DisableableElement
from nicegui.elements.mixins.value_element import ValueElement
from nicegui import ui

class ColorPicker(ValueElement, DisableableElement):
    def __init__(self, *,
                 on_pick: Optional[Handler[ColorPickEventArguments]] = None,
                 value = None,  #initial color value
                 
                 enable_white: bool = False,  #enable white channel
                 auto_calc_white: bool = True,  #automatically calculate white channel
                 ) -> None:
        
        """Color Picker
        which is always open and allows the user to pick a color.

        This element is based on Quasar's `QMenu <https://quasar.dev/vue-components/menu>`_ and
        `QColor <https://quasar.dev/vue-components/color-picker>`_ components.

        :param on_pick: callback to execute when a color is picked
        :param value: whether the menu is already opened (default: `False`)
        """
        super().__init__(value=value)
        self._pick_handlers = [on_pick] if on_pick else []

        self.color = value if value else ColorPickEventArguments(sender=self, client=None, color='#00000000') #allways hex

        with self:
            def handle_change(e: GenericEventArguments):
                for handler in self._pick_handlers:
                    handle_event(handler, ColorPickEventArguments(sender=self, client=self.client, color=e.args))
            self.q_color = Element('q-color').on('change', handle_change)
        
        # with ui.context_menu():
        #     ui.menu_item('Flip horizontally')
        #     ui.menu_item('Flip vertically')

        if enable_white:
            self.auto_calc_white_checkbox = ui.checkbox('Weiss automatisch', value=auto_calc_white)
            if not self.auto_calc_white_checkbox.value:
                self.set_color(value.as_hex() if value else '#00000000')

    def change_auto_calc_white(self, value: bool) -> None:
        """Change the auto-calculate white channel setting."""
        self.auto_calc_white_checkbox.value = value
        if not value:
            self.set_color(self.value.as_hex() if self.value else '#00000000')

    def set_color(self, color: str) -> None:
        """Set the color of the picker.

        :param color: the color to set
        """
        self.q_color.props(f'model-value="{color}"')

    def on_pick(self, callback: Handler[ColorPickEventArguments]) -> Self:
        """Add a callback to be invoked when a color is picked."""
        self._pick_handlers.append(callback)
        return self

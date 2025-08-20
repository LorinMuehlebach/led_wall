from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .settings_manager import SettingsManager

from nicegui import ui


class SettingsElement():
    """SettingsElement is a custom input element for the settings page."""

    def __init__(self,
                 label: str|ui.element,
                 input: ui.element,
                 default_value,
                 manager: SettingsManager|None = None, 
                 on_change=None,
                 **options,
                ) -> None:

        self.label = label
        #self.input = input
        self.default_value = default_value
        self.options = options

        self.on_change = on_change

        self.manager = manager
        self.save_on_change = options.get('save_on_change', True)

        #register the element with the manager if provided
        #load the default value none from saved settings
        self.value = None
        self.settings_id = options.get('settings_id', label.lower().replace(' ', '_'))
        self.manager.init_setting_element(self,self.settings_id) if manager else None
        if self.value is None:
            self.value = default_value

        
        with ui.row().classes('flex items-center'):
            if isinstance(label, str):
                self.label = ui.label(label).classes('place-content-center')
            else:
                self.label = label

            self.input = input(value=self.value, on_change=self._on_change)

    def _on_change(self, e) -> None:
        """
            Handles the change event of the input element.
        """
        self.on_change(e) if self.on_change else None #execute the custom on_change callback if provided
        self.manager.settings_update(self, e.value) if self.manager else None #save changes
        
        

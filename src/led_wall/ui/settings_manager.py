from __future__ import annotations
from typing import TYPE_CHECKING

import threading
import json
import logging

from nicegui import ui
from nicegui.events import ValueChangeEventArguments

if TYPE_CHECKING: #hack to avoid circular imports
    from .settings_element import SettingsElement


logger = logging.getLogger("utils")

class SettingsManager:
    """SettingsManager is responsible for managing the settings of the application."""
    SAVE_TIMEOUT = 2  # seconds

    def __init__(self, parent: SettingsManager|None = None, name:str = None, path:str = None) -> None:
        self.settings_elements = []
        self.settings: dict[str, int | str | dict] = {} # Dictionary to hold settings or dict with key as setting ID and value as the setting value
        self.parent = parent
        self.name = name
        self.path = path

        self.timeout_thread = None

        self._settings_change_callbacks: dict[str, list[callable]] = {}

        #load settings from parent if provided
        if parent is not None:
            self.settings = parent.settings.get(name, {})
        
        elif path is not None:
            self.load_from_file()

    def init_setting_element(self, element: SettingsElement, key: str) -> None:
        """
        Initializes a settings element by registering it and loading the saved value or default value.
        """

        element.value = self.settings.get(key, element.default_value)
        self.settings[element.settings_id] = element.value #save setting into dict

        self.settings_elements.append(element)

    def settings_change(self, element: SettingsElement|SettingsManager, value:dict|int|str) -> None:
        """
        Updates the settings with the given key and value.
        If the value is None, it will remove the key from the settings.
        """
        if isinstance(element, SettingsElement):
            self.settings[element.settings_id] = value

            if element == "all":
                for key in self.settings:
                    if key in self._settings_change_callbacks:
                        for callback in self._settings_change_callbacks[key]:
                            callback(self.settings[key])
                return
            
            if element.settings_id in self._settings_change_callbacks:
                for callback in self._settings_change_callbacks[element.settings_id]:
                    callback(value)

        elif isinstance(element, SettingsManager):
            if element.name is not None:
                self.settings[element.name] = value
        else:
            raise ValueError("element must be of type SettingsElement or SettingsManager") 

        if self.parent is not None:
            self.parent.settings_change(self, self.settings)
        elif self.path is not None:
            #save the settings to a file
            self.save_with_timeout()
        
    def get_setting(self, key: str) -> int | str | dict:
        """
        Returns the value of the setting with the given key.
        If the key does not exist, it returns None.
        """
        return self.settings.get(key, None)

    def update_setting(self, setting_id: str, value) -> None:
        """
        Updates a setting directly by its ID.
        Handles ValueChangeEventArguments and triggers appropriate save mechanism.
        """
        if isinstance(value, ValueChangeEventArguments):
            value = value.value
        
        # Try to find the corresponding SettingsElement
        element = next((e for e in self.settings_elements if e.settings_id == setting_id), None)
        if element:
            self.settings_change(element, value)
        else:
            # Fallback if element not found: update dict directly and trigger save
            self.settings[setting_id] = value
            if self.parent:
                self.parent.settings_change(self, self.settings)
            elif self.path:
                self.save_with_timeout()

    def save_with_timeout(self) -> None:
        """
        Saves the file if no changes after the SAVE_TIMEOUT.
        """
        if self.timeout_thread is not None:
            self.timeout_thread.cancel()

        self.timeout_thread = threading.Timer(self.SAVE_TIMEOUT, self.save_to_file)
        self.timeout_thread.start()

    def save_to_file(self) -> None:
        """
        Saves the current settings to a file.
        """
        # Writing to a JSON file with indentation
        with open(self.path, "w") as outfile:
            json.dump(self.settings, outfile, indent=4)

    def load_from_file(self) -> None:
        """
        Loads settings from a file.
        """
        path = self.path
        try:
            with open(path, "r") as infile:
                self.settings = json.load(infile)

        except FileNotFoundError:
            logger.warning(f"Settings file {path} not found. Using default settings.")
        except json.JSONDecodeError:
            logger.warning(f"Error decoding JSON from {path}. Using default settings.")

    def register_on_setting_change(self, element: SettingsElement|SettingsManager, value:dict|int|str, callback:callable) -> None:
        """
        adds a new callback on a change of a setting
        """
        if element in self._settings_change_callbacks:
            self._settings_change_callbacks[element].append(callback)
        else:
            self._settings_change_callbacks[element] = [callback]


class SettingsElement():
    """SettingsElement is a custom input element for the settings page."""

    def __init__(self,
                 label: str,
                 input: ui.element,
                 default_value,
                 manager: SettingsManager|None = None, 
                 on_change=None,
                 **kwargs,
                ) -> None:

        self.label = label
        self.input = input
        self.default_value = default_value

        self.on_change = on_change

        self.manager = manager
        #self.save_on_change = kwargs.get('save_on_change', True)

        #register the element with the manager if provided
        #load the default value none from saved settings
        self.settings_id = kwargs.pop('settings_id', None) #label.lower().replace(' ', '_') in here is not possible as it would run on this line and give an error on None
        if self.settings_id is None:
            self.settings_id = label.lower().replace(' ', '_')
        self.manager.init_setting_element(self,self.settings_id) if manager else None
        if self.value is None:
            self.value = default_value
        else:
            event = ValueChangeEventArguments(sender=self, client=None, value=self.value)
            self.on_change(event) if self.on_change else None #update with loaded value from settings

        self.options = kwargs

    def create_ui(self) -> None:
        with ui.row().classes('flex items-center'):
            if self.label is not None:
                ui.label(self.label).classes('place-content-center')
            self.input(value=self.value, on_change=self._on_change, **self.options).bind_value(self, 'value')

    def _on_change(self, e) -> None:
        """
            Handles the change event of the input element.
        """
        self.on_change(e) if self.on_change else None #execute the custom on_change callback if provided
        self.manager.settings_change(self, e.value) if self.manager else None #save changes
        
        

import os
from nicegui import ui, app
import logging

from led_wall.ui.logging_config import getLogger
from led_wall.effects.effect_manager import EffectManager
from led_wall.ui.dmx_channels import DMX_channels_Input
from led_wall.ui.settings_manager import SettingsElement, SettingsManager
from led_wall.io_manager import IO_Manager


logger = getLogger(__name__)

# from led_wall.ui.translate import setup_translate
# _ = setup_translate() #lazy translate function

#top level SettingsManager
settings_manager = SettingsManager(path='settings.json')

#initialize main settings
app_settings = SettingsManager(parent=settings_manager, name="main_settings")

if "presets" not in settings_manager.settings:
    settings_manager.settings["presets"] = {}
if "selected_preset" not in app_settings.settings:
    app_settings.settings["selected_preset"] = "Show1"

presets = [key for key in settings_manager.settings["presets"]]


#handle all Input & Outputs
io_manager = IO_Manager(settings_manager=settings_manager)

effect_manager = None

#define main window ui
@ui.refreshable
def main_window(effect_manager):
    if effect_manager:
        with ui.row().classes('flex w-full'):
            with ui.element("div").classes('max-w-md'):
                ui.label("Vorschau").classes('text-2xl font-bold mb-4')
                preview_image = ui.interactive_image().classes('w-full max-w-400')
                effect_manager.init_preview(preview_image)

            with ui.element("div").classes('max-w-md'):
                ui.label("Effekte").classes('text-2xl font-bold mb-4')
                effect_manager.effect_manager_ui()

@ui.refreshable
def effect_settings_ui(effect_manager):
    effect_manager.effect_setting_ui()

@ui.refreshable
def show_ui(effect_manager, io_manager):
    effect_manager.effect_show_ui()

    ui.label("DMX channels").classes('text-1xl font-bold mb-4')
    io_manager.dmx_channel_ui()  # Create the settings UI for DMX inputs

def preset_change(e) -> None: 
    global effect_manager, io_manager

    if e.value not in settings_manager.settings["presets"]: #if it does not exist add it
        presets.append(e.value)
        settings_manager.settings["presets"][e.value] = {}
        settings_manager.save_with_timeout()
    
    logger.info(f"Preset changed to {e.value}")

    #create a new effect manager with the new preset settings
    effect_settings = SettingsManager(parent=SettingsManager(parent=settings_manager, name="presets"), name=e.value)
    effect_manager = EffectManager(IO_manager=io_manager, settings_manager=effect_settings)

    main_window.refresh(effect_manager)  # Refresh the main window to show the new effects
    effect_settings_ui.refresh(effect_manager)
    show_ui.refresh(effect_manager,io_manager)

    effect_manager.IO_manager.start_loop()

if app_settings.settings["selected_preset"] not in presets:
    #should never happen maybe manual edits to settings file
    presets.append(app_settings.settings["selected_preset"])

setting_elements = [
    SettingsElement(
        label='Voreinstellungen',
        input=ui.select,
        default_value=None,
        with_input = True,
        new_value_mode = 'add-unique',
        settings_id='selected_preset',
        on_change=preset_change,
        options=presets,
        manager=app_settings,
    )
]

if 'NICEGUI_STARTED' not in os.environ:
    app.on_startup(effect_manager.setup_preview)
    os.environ["NICEGUI_STARTED"] = "true" #needed so it only starts once

#main window structuring
main_window(effect_manager)

with ui.tabs().classes('w-full') as tabs:
    tab_show = ui.tab('Show')
    tab_setting = ui.tab('Einstellungen')

with ui.tab_panels(tabs, value=tab_setting).classes('w-full'):
    with ui.tab_panel(tab_show):
        show_ui(effect_manager,io_manager)
    with ui.tab_panel(tab_setting):
        ui.label('Effekt Einstellungen').classes('text-1xl font-bold mb-4')
        effect_settings_ui(effect_manager)

        ui.separator()
        ui.label('System Einstellungen').classes('text-1xl font-bold mb-4')
        with ui.column().classes('w-full'):
            for element in setting_elements:
                element.create_ui()

        with ui.expansion('Eingänge / Ausgänge').classes('w-full'):
            io_manager.ui_settings()  # Create the settings UI for IO Manager



ui.run(
    title='Led Wall',
    host="0.0.0.0",
    reload=False,
    #window_size=(1800, 600),
    dark=True
)
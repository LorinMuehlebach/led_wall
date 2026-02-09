import os
import signal
import sys
import asyncio
from nicegui import ui, app, Client, core
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

# Serve media files
app.add_static_files('/media', 'media')

effect_manager = None

#define main window ui
@ui.refreshable
def main_window(effect_manager):
    if effect_manager:
        with ui.row().classes('w-full flex flex-wrap gap-4'):
            with ui.element("div").classes('w-full md:w-1/4 min-w-[200px]'):
                ui.label("Vorschau").classes('text-2xl font-bold mb-4')
                preview_image = ui.interactive_image().classes('w-full max-w-400')
                effect_manager.init_preview(preview_image)

            with ui.element("div").classes('flex-1 min-w-[300px]'):
                ui.label("Effekte").classes('text-2xl font-bold mb-4')
                effect_manager.effect_manager_ui()

@ui.refreshable
def effect_settings_ui(effect_manager):
    effect_manager.effect_setting_ui()

@ui.refreshable
def show_ui(effect_manager, io_manager):
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

# Flag to prevent multiple shutdowns
_shutdown_in_progress = False

async def disconnect_all_clients():
    """Disconnect all clients from the server."""
    for client_id in list(Client.instances.keys()):
        try:
            await core.sio.disconnect(client_id)
        except Exception as e:
            logger.error(f"Error disconnecting client {client_id}: {e}")

def shutdown_handler(signum, frame):
    """Handle graceful shutdown on Ctrl+C"""
    global _shutdown_in_progress
    
    if _shutdown_in_progress:
        return
    
    _shutdown_in_progress = True
    logger.info("Received shutdown signal, cleaning up...")
    
    # Disconnect all NiceGUI clients
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(disconnect_all_clients())
        logger.info("Disconnecting clients...")
    except Exception as e:
        logger.error(f"Error disconnecting clients: {e}")
    
    # Stop the active effect
    if effect_manager and hasattr(effect_manager, 'effects'):
        try:
            effect_manager.effects[effect_manager.active_effect].stop()
            logger.info("Stopped active effect")
        except Exception as e:
            logger.error(f"Error stopping effect: {e}")
    
    # Stop the IO manager loop
    if io_manager:
        try:
            io_manager.stop_loop()
            logger.info("Stopped IO manager loop")
        except Exception as e:
            logger.error(f"Error stopping IO manager: {e}")
    
    # Save settings
    # try:
    #     settings_manager.save_to_file()
    #     logger.info("Settings saved")
    # except Exception as e:
    #     logger.error(f"Error saving settings: {e}")
    
    logger.info("Shutdown complete")
    
    if signum is not None:  # Only exit if called from signal handler
        sys.exit(0)

# Register signal handler for clean shutdown
signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

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
    app.on_shutdown(lambda: shutdown_handler(None, None))
    os.environ["NICEGUI_STARTED"] = "true" #needed so it only starts once

#main window structuring
main_window(effect_manager)

with ui.tabs().classes('w-full') as tabs:
    tab_show = ui.tab('Show')
    tab_setting = ui.tab('Einstellungen')

with ui.tab_panels(tabs, value=tab_show).classes('w-full'):
    with ui.tab_panel(tab_show):
        show_ui(effect_manager,io_manager)
    with ui.tab_panel(tab_setting):
        # ui.label('Effekt Einstellungen').classes('text-1xl font-bold mb-4')
        # effect_settings_ui(effect_manager)

        ui.separator()
        ui.label('System Einstellungen').classes('text-1xl font-bold mb-4')
        with ui.column().classes('w-full'):
            for element in setting_elements:
                element.create_ui()

        io_manager.ui_settings()  # Create the settings UI for IO Manager



ui.run(
    title='Led Wall',
    host="0.0.0.0",
    reload=False,
    #window_size=(1800, 600),
    dark=True
)
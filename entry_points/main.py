import os
import signal
import sys
import asyncio
import logging
import multiprocessing
import socket

from led_wall.ui.logging_config import getLogger
from led_wall.effects.effect_manager import EffectManager
from led_wall.ui.dmx_channels import DMX_channels_Input
from led_wall.ui.settings_manager import SettingsElement, SettingsManager
from led_wall.io_manager import IO_Manager, get_local_ip
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file
logger = getLogger("main")

user_data_dir = os.getenv("APPDATA") or os.path.expanduser("~/.config")  # Use APPDATA on Windows, otherwise use ~/.config
settings_dir = os.getenv("LED_WALL_DIR", os.path.join(user_data_dir, "LED_Wall"))  # Get the directory from environment variable, default to current directory

DEV = False
port = 8080
if (not DEV or __name__ != "__main__") and multiprocessing.current_process().name == 'MainProcess': # you can do `if True:` to bypass this to revert to the normal behavior, but that is slow...
    # Explanation: 2 reasons for running this code:
    # 1. not in dev mode, so there is no __mp_main__, this is already where NiceGUI will run
    # 2. or, in dev mode, and this is the __mp_main__, so we want to run this code

    initialized = False
    from nicegui import ui, app, Client, core
    from nicegui.events import ValueChangeEventArguments

    

    # from led_wall.ui.translate import setup_translate
    # _ = setup_translate() #lazy translate function

    #top level SettingsManager
    settings_manager = SettingsManager(path=os.path.join(settings_dir, 'settings.json'))

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
    media_dir = os.path.join(settings_dir, 'media')
    if not os.path.exists(media_dir):
        os.makedirs(media_dir)
    app.add_static_files('/media', media_dir)

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

    # @ui.refreshable
    # def effect_settings_ui(effect_manager):
    #     effect_manager.effect_setting_ui()

    @ui.refreshable
    def show_ui(effect_manager, io_manager):
        ui.label("DMX channels").classes('text-1xl font-bold mb-4')
        io_manager.dmx_channel_ui()  # Create the settings UI for DMX inputs

    def preset_change(e) -> None:
        global effect_manager, io_manager

        #check if it is the same preset, if so do nothing
        if e.value == app_settings.settings["selected_preset"] and effect_manager is not None:
            return

        if e.value not in settings_manager.settings["presets"]: #if it does not exist add it
            presets.append(e.value)
            settings_manager.settings["presets"][e.value] = {}
            settings_manager.save_with_timeout()
        
        logger.info(f"Preset changed to {e.value}")

        if effect_manager:
            effect_manager.shutdown()  # Stop all effects and cleanup resources before creating a new effect manager

        #create a new effect manager with the new preset settings
        effect_settings = SettingsManager(parent=SettingsManager(parent=settings_manager, name="presets"), name=e.value)
        effect_manager = EffectManager(IO_manager=io_manager, settings_manager=effect_settings)
        effect_manager.setup()  # Setup the effect manager with the new preset settings

        main_window.refresh(effect_manager)  # Refresh the main window to show the new effects
        #effect_settings_ui.refresh(effect_manager)
        show_ui.refresh(effect_manager,io_manager)

        effect_manager.setup_preview()  # Setup the preview before the UI is fully up
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

        if effect_manager:
            effect_manager.shutdown()  # Stop all effects and cleanup resources
            logger.info("Effect manager shutdown complete")
                
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
            options=presets,
            manager=app_settings,
        )
    ]

    preset_settinsElement = setting_elements[0]

    # if 'NICEGUI_STARTED' not in os.environ:
    #     os.environ["NICEGUI_STARTED"] = "true" #needed so it only starts once
    #     io_manager.start_loop()  # Start the IO manager loop before the UI is fully up
    #     effect_manager.setup()
    #     #effect_manager.setup_preview()  # Setup the preview before the UI is fully up
    #     app.on_startup(effect_manager.setup_preview)
    #     app.on_shutdown(lambda: shutdown_handler(None, None))
        

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
            ui.button("open settings folder", on_click=lambda: os.startfile(settings_dir)).classes('w-full')

    
    # print("Here are a bunch of startup tasks that must be run once, and before the server starts")
    # for _ in range(100000000):
    #     pass # some long running task
    # print("Before-server-start startup tasks are done")

    # from nicegui import ui, app # the normal import

    # @ui.page("/")
    # def index():
    #     print("Here are some tasks you want to run before every page load")
    #     ui.label("You page definitions go here")

    with ui.footer().classes('bg-transparent text-gray-500 flex justify-between items-center px-4 py-1'):
        ui.label('Created by Lorin Mühlebach').classes('text-xs font-light')
        ui.label(f'Server: {get_local_ip()}:{port}').classes('text-xs font-light')

    def delayed_startup_tasks():
        #print("Here are a bunch of startup tasks that also must be run once, but can be after the server has started")
        #io_manager.start_loop()  # Start the IO manager loop before the UI is fully up
        #effect_manager.setup()
        preset_change(ValueChangeEventArguments(sender=None, client=None, value=app_settings.settings["selected_preset"]))  # Trigger the preset change to initialize everything
        preset_settinsElement.on_change = preset_change  # Set the on_change callback for the preset settings element
        #print("After-server-start startup tasks are done")

    app.on_startup(delayed_startup_tasks)


if multiprocessing.current_process().name == 'MainProcess':
    ui.run(
        title='Led Wall',
        host="0.0.0.0",
        port=port,
        reload=DEV,
        #fullscreen=True,
        #frameless=False,
        #native=True,
        window_size=(1200, 900),
        dark=True
    )
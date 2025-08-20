from nicegui import ui, app
from led_wall.ui.dmx_channels import DMX_channels_Input
from led_wall.io_manager import IO_Manager

from led_wall.ui.settings_manager import SettingsManager, SettingsElement
import led_wall.effects as effects


print("Available effects:")
for effect in effects.get_effects():
    print(f" - {effect.NAME}")


def on_effect_selected(event):
    print(f"Selected effect: {event.value}")


effects = effects.get_effects()
effect_select = ui.select([effect.NAME for effect in effects],value=effects[0].NAME, on_change=on_effect_selected)

ui.separator()

settings_manager = SettingsManager(path='settings.json')
settings_manager.load_from_file()  # Load settings from file if available

effect = BaseEffect(screen_dimensions=(35, 60), rgbw=True, settings_manager=settings_manager)

ui.label("Preview").classes('text-2xl font-bold mb-4')
with ui.element("div").classes('max-w-md'):
    preview_image = ui.interactive_image().classes('w-full max-w-400')

ui.label("Effect Settings").classes('text-2xl font-bold mb-4')
with ui.element("div"):
    effect.ui_settings()  # This would create the settings UI elements for the effect

ui.separator()
ui.label("Effect Inputs").classes('text-2xl font-bold mb-4')
with ui.element("div").classes('w-full'):
    effect.ui_show() # This would show the UI elements for the effect

ui.separator()

dmx_inputs = DMX_channels_Input(10)
ui.label("DMX Channels").classes('text-2xl font-bold mb-4')
dmx_inputs.create_ui()

effect.on_input_change = lambda channels: dmx_inputs.update_sliders(channels)

io_manager = IO_Manager(resolution=(35, 60), dimensions=(6, 3), dmx_inputs=dmx_inputs, framerate=10, RGBW=True)

io_manager.init_preview(preview_image=preview_image)

io_manager.create_frame = effect.run_raw  # Set the effect's run method as the frame creator

#app.on_startup(io_manager.setup_preview)

ui.run(
        title='Led Wall',
        host="0.0.0.0",
        #window_size=(1800, 600),
        dark=True
    )
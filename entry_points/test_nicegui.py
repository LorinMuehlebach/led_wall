from threading import Thread
import time
from nicegui import ui

from led_wall.ui.slider import Slider
from led_wall.ui.color_picker import ColorPicker
from led_wall.datatypes import Color, Fader


# from led_wall.ui.preview_window import preview_setup
# from led_wall.ui.settings_element import SettingsElement

available_modules = [
    'fixed color',
    'color gradient',
    'picture mix',
    'flash',
    'video'
]

RGBW = True  # True for RGBW, False for RGB

#color = "#000000"  # Default color, can be set dynamically

@ui.refreshable
def dynamically_add_element(hex_color="#000000") -> None:
    """Dynamically add a new element to the UI."""
    ui.label(f'New Element {hex_color}').classes('text-h6')
    ui.button('Click Me', on_click=lambda: ui.notify('Button clicked!'))

with ui.row().classes('flex w-full'):
    with ui.card().tight().classes('no-shadow border-[0px] grow max-w-md background-color: transparent'):
        ui.label('Led Wall Control').classes('text-h4 text-center')
        ui.label('This is a simple control panel for the LED wall.').classes('text-center')
        #ui.image('https://picsum.photos/id/377/640/360').classes('grow max-w-md')
        video_image = ui.interactive_image().classes('w-full h-full')
    
    with ui.row().classes('grow'):
        with ui.tabs().classes('w-full') as tabs:
            tab_mode1 = ui.tab('Eine Farbe')
            tab_mode2 = ui.tab('Multi-Modus')
        with ui.tab_panels(tabs, value=tab_mode1).classes('w-full'):
            with ui.tab_panel(tab_mode1):
                #VerticalSlider('Brightness', on_change=lambda e: ui.notify(f'Brightness changed: {e.value}'))
                current_color = Color("#000000")  # Example color, can be set dynamically
                color_preview = None
                color_sliders = []

                def set_color(channel:int=None, value:int = None, hex_color: str = None,event=None) -> None:
                    if channel is not None and value is not None:
                        current_color.change_single_channel(channel, value)
                        color_preview.value = current_color.as_hex()
                    elif hex_color is not None:
                        current_color.set_hex(hex_color)
                        for i, slider in enumerate(color_sliders):
                            slider.value = current_color.get_channel_value(i)

                    dynamically_add_element.refresh(current_color.as_hex())

                color_preview = ui.color_input(
                    label='Farbe',
                    value=current_color.as_hex(),
                    on_change=lambda e: set_color(hex_color=e.value,event=e),
                    preview=True
                )

                with ui.list():
                    nof_sliders = 4 if RGBW else 3
                    for i in range(nof_sliders):
                        slider = Slider(min=0, max=100, value=0, vertical=True, reverse=True, on_change=lambda e, i=i: set_color(channel=i, value=e.value,event=e))
                        color_sliders.append(slider)

                ui.checkbox('input ignorieren')

                # SettingsElement(
                #     label='Brightness',
                #     input=ui.input,
                #     default_value='50',
                #     placeholder='Set brightness'
                # )

            with ui.tab_panel(tab_mode2):
                ui.label('Second tab')
                with ui.list():
                    for i in range(8):
                        ui.select(options=available_modules, on_change=lambda e: ui.notify(f'Selected: {e.value}'))


#dynamically_add_element()
from nicegui.element import Element

Fader(0).ui_input(on_change=lambda e: ui.notify(f'Fader changed: {e.value}'))
#Element('q-color').props['v-model'] = 'hexa'
ColorPicker(enable_white=True)

# count = 0
# def io_update(**kwargs: dict) -> None:
#     """Run the NiceGUI app in a separate thread."""
#     count = 0
#     while True:
#         count += 1
#         dynamically_add_element.refresh(f'#{count:06x}')
#         time.sleep(1)  # Simulate some processing time

# update_thread = Thread(target=io_update, kwargs={'title': 'Led Wall', 'dark': True})
# update_thread.start()

ui.run(
    title='Led Wall',
    host="0.0.0.0",
    #window_size=(1800, 600),
    dark=True
)

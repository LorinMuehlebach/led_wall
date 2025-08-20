from typing import Callable, Optional
from nicegui import ui, app

from nicegui.element import Element



class ColorWheel(Element, component='color_wheel.vue'):
    #STATIC_FILES_ADDED = False
    
    def __init__(self,value=None,inline=False,auto_resize=False,sliders="wv") -> None:
        super().__init__()

        #if not ColorWheel.STATIC_FILES_ADDED:
        app.add_static_files('/static', 'src/led_wall/static')
        ui.add_head_html('<script type="text/javascript" src="/static/jquery-3.7.1.min.js"></script>')
        ui.add_head_html('<script type="text/javascript" src="/static/jquery.wheelcolorpicker.min.js"></script>')
        ui.add_head_html('<link rel="stylesheet" href="/static/wheelcolorpicker.dark.css">')
        #    ColorWheel.STATIC_FILES_ADDED = True


        throttle = 0.05
        self.value = value if value else '#000000'

        self.set_color(self.value)

        def handle_change(e):
            color = e.args
            if self.value != color:
                self.set_color(color)
                ui.notify(f'Color changed {color}')
                self.value = color
            

        def handle_colorchange(e):
            color = e.args
            if self.value != color:
                self.set_color(color)
                ui.notify(f'Color changed {color}')
                self.value = color
            

        def handle_slidermove(e):
            ui.notify(f'Slider moved {e}')

        self.on('change', handle_change)
        self.on('colorchange', handle_colorchange,throttle=throttle)
        self.on('slidermove', handle_slidermove,throttle=throttle)

        #self.set_props("data-wcp-layout","block")

        self.props(f'data-wcp-preview="true" data-wcp-sliders="{sliders}" data-wcp-autoresize="{auto_resize}"')

    def set_color(self, color: str) -> None:
        self.value = color
        self.run_method('setColor', color)

    # def set_props(self, key,value) -> None:
    #     self.run_method('setAttr', key)

    def reset(self) -> None:
        #self.run_method('reset')
        pass


if __name__ in {"__main__", "__mp_main__"}:    

    color_wheel = ColorWheel()
    color_slider = ColorWheel(sliders="v")
    color_wheel2 = ColorWheel()

    ui.button('Set Color').on_click(lambda: color_wheel.set_color('#ff0000'))
    
    ui.run()
from typing import Callable, Optional
from nicegui import ui, app

from nicegui.element import Element



class ColorWheel(Element, component='color_wheel.vue'):
    #STATIC_FILES_ADDED = False
    
    def __init__(self, value: Optional[str] = None, inline: bool = False,
                 auto_resize: bool = True, sliders: str = "wv",
                 on_change: Optional[Callable[[str], None]] = None) -> None:
        super().__init__()

        #if not ColorWheel.STATIC_FILES_ADDED:
        app.add_static_files('/static', 'src/led_wall/static')
        ui.add_head_html('<script type="text/javascript" src="/static/jquery-3.7.1.min.js"></script>')
        ui.add_head_html('<script type="text/javascript" src="/static/jquery.wheelcolorpicker.min.js"></script>')
        ui.add_head_html('<link rel="stylesheet" href="/static/wheelcolorpicker.dark.css">')
        #    ColorWheel.STATIC_FILES_ADDED = True

        throttle = 0.05
        self.value = value if value else '#000000'
        self._on_change = on_change

        # Build options dict to pass to the Vue component / jQuery plugin
        options: dict = {
            'preview': True,
            'sliders': sliders,
            'autoresize': auto_resize,
        }
        if inline:
            options['layout'] = 'block'
            options['cssClass'] = 'color-block'

        self._props['options'] = options

        self.set_color(self.value)

        def _update_value(color: str) -> None:
            if self.value != color:
                self.value = color
                if self._on_change:
                    self._on_change(color)

        def handle_change(e):
            _update_value(e.args)

        def handle_colorchange(e):
            _update_value(e.args)

        self.on('change', handle_change)
        self.on('colorchange', handle_colorchange, throttle=throttle)

    def set_color(self, color: str) -> None:
        self.value = color
        self.run_method('setColor', color)

    # def set_props(self, key,value) -> None:
    #     self.run_method('setAttr', key)

    def reset(self) -> None:
        #self.run_method('reset')
        pass


if __name__ in {"__main__", "__mp_main__"}:    

    color_wheel_inline = ColorWheel(inline=True)

    color_wheel = ColorWheel(
        inline=True,
        on_change=lambda color: color_wheel_inline.set_color(color),
    )
    color_slider = ColorWheel(inline=True, sliders="v")

    ui.button('Set Color').on_click(lambda: color_wheel.set_color('#ff0000'))
    
    ui.run(dark=True)
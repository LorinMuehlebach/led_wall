from typing import Callable, Optional
from nicegui import ui, app

from nicegui.element import Element



class ColorWheel(Element, component='color_wheel.vue'):
    #STATIC_FILES_ADDED = False
    
    def __init__(self, value: Optional[str] = None, inline: bool = False,
                 auto_resize: bool = True, sliders: str = "wv",
                 size: int = 120,
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
        self._dragging = False

        # Build options dict to pass to the Vue component / jQuery plugin
        options: dict = {
            'preview': True,
            'sliders': sliders,
            'autoresize': auto_resize,
        }
        if inline:
            options['layout'] = 'block'
            options['autoResize'] = False
            options['cssClass'] = 'color-block'

        self._props['options'] = options
        self._props['widget_size'] = size

        self.set_color(self.value)

        def _update_value(color: str) -> None:
            if self.value != color:
                self.value = color

                if not color.startswith('#'):
                    color = '#' + color
                if self._on_change:
                    self._on_change(color)

        def handle_change(e):
            _update_value(e.args)

        def handle_colorchange(e):
            _update_value(e.args)

        def handle_dragstart(e):
            self._dragging = True

        def handle_dragend(e):
            self._dragging = False
            _update_value(e.args)

        self.on('change', handle_change)
        self.on('colorchange', handle_colorchange, throttle=throttle)
        self.on('dragstart', handle_dragstart)
        self.on('dragend', handle_dragend)

    def set_color(self, color: str) -> None:
        self.value = color
        if not self._dragging:
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
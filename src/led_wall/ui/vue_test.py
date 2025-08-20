from typing import Callable, Optional

from nicegui.element import Element


class OnOff(Element, component='custom_vue.vue'):

    def __init__(self, title: str, *, on_change: Optional[Callable] = None, libraries=['npm:lodash']) -> None:
        super().__init__()
        #self._props['title'] = title
        #self.on('change', on_change)

    def reset(self) -> None:
        #self.run_method('reset')
        pass
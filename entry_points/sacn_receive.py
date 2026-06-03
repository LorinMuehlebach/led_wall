#!/usr/bin/env python3
"""
sACN Receiver - Receive and display DMX channels via sACN (Streaming ACN / E1.31)
This application starts an sACN receiver and displays received DMX values.
"""
import logging
import time
from nicegui import ui, app

from led_wall.sacn_input import SACNInput
from led_wall.ui.settings_manager import SettingsElement, SettingsManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SACNReceiver:
    def __init__(self):
        self.settings_manager = SettingsManager(path='sacn_receive_settings.json')

        # sACN configuration (universes are 1-based)
        self.bind_address = ''
        self.start_universe = 1
        self.n_universes = 1
        self.start_channel = 1
        self.n_channels = 16
        self.time_full_change = 0.0
        self.multicast = True

        # Active SACNInput instances, one per universe
        self.inputs: dict[int, SACNInput] = {}
        self.is_listening = False

        # Data storage
        self.universe_data: dict[int, list[int]] = {}
        self.last_update = time.time()
        self.packet_count = 0

        # FPS counter state
        self._fps_frame_count: int = 0
        self._fps_last_log: float = time.monotonic()
        self._fps_current: float = 0.0

        # UI elements
        self.status_label = None
        self.listen_button = None
        self.packet_counter_label = None
        self.last_update_label = None
        self.fps_label = None
        self.channel_elements: dict[int, list] = {}

        # Settings elements
        self.settings_elements = [
            SettingsElement(
                label='Bind Address',
                input=ui.input,
                settings_id='bind_address',
                default_value=self.bind_address,
                on_change=lambda e: setattr(self, 'bind_address', e.value or ''),
                manager=self.settings_manager,
                placeholder='auto (local IP)'
            ),
            SettingsElement(
                label='Start Universe',
                input=ui.number,
                settings_id='start_universe',
                default_value=self.start_universe,
                on_change=lambda e: setattr(self, 'start_universe', int(e.value) if e.value is not None else 1),
                manager=self.settings_manager,
                precision=0,
                min=1,
                max=32768
            ),
            SettingsElement(
                label='Num Universes',
                input=ui.number,
                settings_id='n_universes',
                default_value=self.n_universes,
                on_change=lambda e: setattr(self, 'n_universes', int(e.value) if e.value is not None else 1),
                manager=self.settings_manager,
                precision=0,
                min=1,
                max=128
            ),
            SettingsElement(
                label='Start Channel',
                input=ui.number,
                settings_id='start_channel',
                default_value=self.start_channel,
                on_change=lambda e: setattr(self, 'start_channel', int(e.value) if e.value is not None else 1),
                manager=self.settings_manager,
                precision=0,
                min=1,
                max=512
            ),
            SettingsElement(
                label='Cols (Channels)',
                input=ui.number,
                settings_id='n_channels',
                default_value=self.n_channels,
                on_change=self._on_channel_count_change,
                manager=self.settings_manager,
                precision=0,
                min=1,
                max=512
            ),
            SettingsElement(
                label='Smoothing Time (s)',
                input=ui.number,
                settings_id='time_full_change',
                default_value=self.time_full_change,
                on_change=lambda e: setattr(self, 'time_full_change', float(e.value) if e.value is not None else 0.0),
                manager=self.settings_manager,
                precision=1,
                min=0,
                max=60,
                step=0.1
            ),
            SettingsElement(
                label='Multicast',
                input=ui.checkbox,
                settings_id='multicast',
                default_value=self.multicast,
                on_change=lambda e: setattr(self, 'multicast', bool(e.value)),
                manager=self.settings_manager,
            ),
        ]

    def _on_channel_count_change(self, event):
        if event.value is not None:
            self.n_channels = int(event.value)

    def _make_callback(self, universe: int):
        """Return a per-universe callback closure for SACNInput."""
        def _callback(data: list[int]) -> None:
            try:
                self.packet_count += 1
                self.last_update = time.time()

                self._fps_frame_count += 1
                now = time.monotonic()
                elapsed = now - self._fps_last_log
                if elapsed >= 1.0:
                    self._fps_current = self._fps_frame_count / elapsed
                    self._fps_frame_count = 0
                    self._fps_last_log = now

                self.universe_data[universe] = data
                self.update_universe_display(universe)
            except Exception as e:
                logger.error("Error processing sACN data for universe %d: %s", universe, e)
        return _callback

    def update_universe_display(self, universe: int):
        """Update the UI for a specific universe."""
        try:
            if universe not in self.channel_elements:
                return

            data = self.universe_data.get(universe, [])
            elements = self.channel_elements[universe]

            for i, (label, cell) in enumerate(elements):
                # SACNInput already slices from start_channel, so data[i] is channel i
                val = data[i] if i < len(data) else 0

                new_text = str(int(val))
                if label.text != new_text:
                    label.text = new_text

                intensity = val / 255.0
                bg_val = int(20 + 80 * intensity)
                cell.style(f'background-color: rgb({bg_val}, {bg_val}, {bg_val + (20 if val > 0 else 0)});')

            if self.packet_counter_label:
                self.packet_counter_label.text = f"Packets received: {self.packet_count}"
            if self.last_update_label:
                self.last_update_label.text = f"Last update: {time.strftime('%H:%M:%S', time.localtime(self.last_update))}"
            if self.fps_label:
                self.fps_label.text = f"FPS: {self._fps_current:.1f}"

        except Exception:
            pass  # Silent fail on UI race conditions during shutdown or re-render

    def start_listening(self):
        """Start sACN receiver(s)."""
        if self.is_listening:
            self.stop_listening()
            return

        try:
            for u in range(self.start_universe, self.start_universe + self.n_universes):
                inp = SACNInput(
                    universe=u,
                    start_channel=self.start_channel,
                    n_channels=self.n_channels,
                    callback=self._make_callback(u),
                    framerate=30,
                    time_full_change=self.time_full_change,
                    bind_address=self.bind_address,
                    multicast=self.multicast,
                    use_internal_loop=True,
                )
                inp.start()
                self.inputs[u] = inp

            self.is_listening = True
            end_u = self.start_universe + self.n_universes - 1
            self.update_status(
                f"Listening on {self.n_universes} universe(s) ({self.start_universe}–{end_u})",
                error=False
            )
            self.listen_button.props('color=negative icon=stop')
            self.listen_button.text = 'Stop'
            logger.info("Started sACN receiver: universes %d–%d", self.start_universe, end_u)

        except Exception as e:
            logger.error("Failed to start sACN receiver: %s", e)
            self.update_status(f"Failed to start: {e}", error=True)
            self.stop_listening()

    def stop_listening(self):
        """Stop all sACN receivers."""
        for inp in self.inputs.values():
            try:
                inp.stop()
            except Exception as e:
                logger.error("Error stopping SACNInput: %s", e)
        self.inputs.clear()
        self.is_listening = False

        self.update_status("Not listening", error=False)
        if self.listen_button:
            self.listen_button.props('color=positive icon=play_arrow')
            self.listen_button.text = 'Start Listening'
        logger.info("Stopped sACN receiver")

    def update_status(self, message: str, error: bool = False):
        if self.status_label:
            self.status_label.text = message
            if error:
                self.status_label.classes('text-red-500', remove='text-green-500 text-gray-500')
            else:
                self.status_label.classes('text-green-500', remove='text-red-500 text-gray-500')

    @ui.refreshable
    def render_channels(self):
        """Render the channel displays as a grid."""
        self.channel_elements = {}

        with ui.card().classes('w-full overflow-hidden p-0 bg-slate-900 border border-slate-700'):
            with ui.scroll_area().style('height: 600px; width: 100%;'):
                with ui.element('div').style(
                    f'display: grid; grid-template-columns: 60px repeat({self.n_channels}, 40px); gap: 1px; padding: 8px;'
                ):
                    # Header row
                    ui.label('Univ').classes('font-bold text-center text-xs text-gray-400')
                    for i in range(self.n_channels):
                        ui.label(f'{self.start_channel + i}').classes('text-[10px] text-center text-gray-500 font-mono')

                    # Data rows
                    for u in range(self.start_universe, self.start_universe + self.n_universes):
                        ui.label(f'{u}').classes('font-bold text-center self-center text-xs text-gray-300')

                        self.channel_elements[u] = []
                        for i in range(self.n_channels):
                            with ui.element('div').classes(
                                'flex items-center justify-center h-6 rounded text-[10px] font-mono text-white bg-gray-800 transition-colors'
                            ) as cell:
                                label = ui.label('0').style('pointer-events: none;')
                            self.channel_elements[u].append((label, cell))

    def create_ui(self):
        """Create the user interface."""
        ui.add_css('.q-linear-progress__model { transition: none !important; }')

        ui.label('sACN DMX Receiver').classes('text-3xl font-bold mb-4')

        with ui.card().classes('w-full max-w-4xl'):
            ui.label('Receiver Settings').classes('text-xl font-bold mb-2')

            with ui.grid(columns=2).classes('w-full gap-4'):
                for element in self.settings_elements:
                    element.create_ui()

            ui.button('Refresh Channels', on_click=self.render_channels.refresh).props('flat')

            ui.separator()

            with ui.row().classes('w-full items-center gap-4'):
                self.listen_button = ui.button(
                    'Start Listening',
                    on_click=lambda: self.start_listening(),
                    icon='play_arrow'
                ).props('color=positive')

                self.status_label = ui.label('Not listening').classes('text-gray-500')

        ui.separator()

        with ui.card().classes('w-full max-w-none'):
            ui.label('Received DMX Channels').classes('text-xl font-bold mb-2')

            with ui.row().classes('w-full gap-4 mb-4'):
                self.packet_counter_label = ui.label('Packets received: 0').classes('text-sm')
                self.last_update_label = ui.label('Last update: Never').classes('text-sm')
                self.fps_label = ui.label('FPS: 0.0').classes('text-sm')

            self.render_channels()

    def shutdown(self):
        """Clean shutdown."""
        logger.info("Shutting down sACN receiver...")
        self.stop_listening()
        self.settings_manager.save()
        logger.info("Shutdown complete")


receiver = SACNReceiver()

app.on_shutdown(receiver.shutdown)

receiver.create_ui()

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title='sACN DMX Receiver',
        host="0.0.0.0",
        port=8083,
        reload=False,
        dark=True,
    )

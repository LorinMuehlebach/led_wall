#!/usr/bin/env python3
"""
ArtNet Receiver - Receive and display DMX channels via ArtNet
This application starts an ArtNet server and displays received DMX values.
"""
import logging
import time
from stupidArtnet import StupidArtnetServer
from nicegui import ui, app

from led_wall.ui.settings_manager import SettingsElement, SettingsManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ArtNetReceiver:
    def __init__(self):
        # Settings manager for persistence
        self.settings_manager = SettingsManager(path='artnet_receive_settings.json')
        
        # ArtNet configuration
        self.listen_ip = '0.0.0.0'  # Listen on all interfaces
        self.listen_port = 6454
        self.start_universe = 0
        self.n_universes = 1
        self.start_channel = 1
        self.n_channels = 16
        
        # ArtNet server
        self.server = None
        self.listener_ids = []
        self.is_listening = False
        
        # Data storage
        self.universe_data = {}  # {universe: [data]}
        self.last_update = time.time()
        self.packet_count = 0
        
        # UI elements
        self.status_label = None
        self.listen_button = None
        self.packet_counter_label = None
        self.last_update_label = None
        self.channel_elements = {}  # {universe: [(label, container)]}
        
        # Settings elements
        self.settings_elements = [
            SettingsElement(
                label='Listen IP',
                input=ui.input,
                settings_id='listen_ip',
                default_value=self.listen_ip,
                on_change=lambda e: setattr(self, 'listen_ip', e.value),
                manager=self.settings_manager,
                placeholder='0.0.0.0 (all interfaces)'
            ),
            SettingsElement(
                label='Listen Port',
                input=ui.number,
                settings_id='listen_port',
                default_value=self.listen_port,
                on_change=lambda e: setattr(self, 'listen_port', int(e.value) if e.value is not None else 6454),
                manager=self.settings_manager,
                precision=0,
                min=1024,
                max=65535
            ),
            SettingsElement(
                label='Start Universe',
                input=ui.number,
                settings_id='universe',
                default_value=self.start_universe,
                on_change=lambda e: setattr(self, 'start_universe', int(e.value) if e.value is not None else 0),
                manager=self.settings_manager,
                precision=0,
                min=0,
                max=32767
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
                on_change=self.on_channel_count_change,
                manager=self.settings_manager,
                precision=0,
                min=1,
                max=512
            ),
        ]
    
    def on_channel_count_change(self, event):
        """Handle change in number of channels to display"""
        if event.value is not None:
            self.n_channels = int(event.value)
    
    def on_dmx_received(self, data, universe: int):
        """Callback when DMX data is received"""
        try:
            self.packet_count += 1
            self.last_update = time.time()
            
            # Store data
            self.universe_data[universe] = data
            
            # Update the specific universe display
            self.update_universe_display(universe)
            
        except Exception as e:
            logger.error(f"Error processing received DMX data for universe {universe}: {e}")
    
    def update_universe_display(self, universe: int):
        """Update the UI for a specific universe"""
        try:
            if universe not in self.channel_elements:
                return
            
            data = self.universe_data.get(universe, [])
            elements = self.channel_elements[universe]
            
            for i, (label, cell) in enumerate(elements):
                channel_idx = self.start_channel - 1 + i
                val = data[channel_idx] if channel_idx < len(data) else 0
                
                # Update UI elements directly (NiceGUI is thread-safe for these properties)
                new_text = str(int(val))
                if label.text != new_text:
                    label.text = new_text
                
                # Color intensity background
                intensity = val / 255.0
                bg_val = int(20 + 80 * intensity) # Range 20 to 100
                cell.style(f'background-color: rgb({bg_val}, {bg_val}, {bg_val + (20 if val > 0 else 0)});')
            
            # Update global stats roughly
            if self.packet_counter_label:
                self.packet_counter_label.text = f"Packets received: {self.packet_count}"
            if self.last_update_label:
                self.last_update_label.text = f"Last update: {time.strftime('%H:%M:%S', time.localtime(self.last_update))}"
                
        except Exception as e:
            pass # Silent fail on UI race conditions during shutdown or re-render
    
    def start_listening(self):
        """Start ArtNet receiver"""
        try:
            if self.is_listening:
                self.stop_listening()
                return
            
            # Create server
            self.server = StupidArtnetServer(port=self.listen_port)
            self.listener_ids = []
            
            # Register listeners for all universes in range
            for u in range(self.start_universe, self.start_universe + self.n_universes):
                # We need to capture the universe ID in the lambda
                l_id = self.server.register_listener(
                    universe=u,
                    callback_function=lambda data, u_id=u: self.on_dmx_received(data, u_id)
                )
                self.listener_ids.append(l_id)
            
            self.is_listening = True
            
            # Update UI
            self.update_status(f"Listening on {self.n_universes} Universes ({self.start_universe}-{self.start_universe + self.n_universes - 1}) on port {self.listen_port}", error=False)
            self.listen_button.props('color=negative icon=stop')
            self.listen_button.text = 'Stop'
            
            logger.info(f"Started ArtNet receiver for {self.n_universes} universes on port {self.listen_port}")
            
        except Exception as e:
            logger.error(f"Failed to start ArtNet receiver: {e}")
            self.update_status(f"Failed to start: {e}", error=True)
            self.is_listening = False
    
    def stop_listening(self):
        """Stop ArtNet receiver"""
        try:
            if self.server:
                self.server.close()
                del self.server
                self.server = None
            
            self.is_listening = False
            self.listener_ids = []
            
            # Update UI
            self.update_status("Not listening", error=False)
            self.listen_button.props('color=positive icon=play_arrow')
            self.listen_button.text = 'Start Listening'
            
            logger.info("Stopped ArtNet receiver")
            
        except Exception as e:
            logger.error(f"Error stopping receiver: {e}")
    
    def update_status(self, message: str, error: bool = False):
        """Update status label"""
        if self.status_label:
            self.status_label.text = message
            if error:
                self.status_label.classes('text-red-500', remove='text-green-500 text-gray-500')
            else:
                self.status_label.classes('text-green-500', remove='text-red-500 text-gray-500')
    
    @ui.refreshable
    def render_channels(self):
        """Render the channel displays as a table (Grid)"""
        self.channel_elements = {}
        
        # Calculate columns: Universe label + n_channels
        cols = self.n_channels + 1
        
        with ui.card().classes('w-full overflow-hidden p-0 bg-slate-900 border border-slate-700'):
             with ui.scroll_area().style('height: 600px; width: 100%;'):
                # Grid with fixed column widths for horizontal scrolling support
                with ui.element('div').style(f'display: grid; grid-template-columns: 60px repeat({self.n_channels}, 40px); gap: 1px; padding: 8px;'):
                    # Header row
                    ui.label('Univ').classes('font-bold text-center text-xs text-gray-400')
                    for i in range(self.n_channels):
                        ui.label(f'{self.start_channel + i}').classes('text-[10px] text-center text-gray-500 font-mono')
                    
                    # Data rows
                    for u in range(self.start_universe, self.start_universe + self.n_universes):
                        ui.label(f'{u}').classes('font-bold text-center self-center text-xs text-gray-300')
                        
                        self.channel_elements[u] = []
                        for i in range(self.n_channels):
                            with ui.element('div').classes('flex items-center justify-center h-6 rounded text-[10px] font-mono text-white bg-gray-800 transition-colors') as cell:
                                label = ui.label('0').style('pointer-events: none;')
                            self.channel_elements[u].append((label, cell))

    def create_ui(self):
        """Create the user interface"""
        # Remove transition animation from progress bars for instant feedback
        ui.add_css('.q-linear-progress__model { transition: none !important; }')
        
        ui.label('ArtNet DMX Receiver').classes('text-3xl font-bold mb-4')
        
        with ui.card().classes('w-full max-w-4xl'):
            ui.label('Receiver Settings').classes('text-xl font-bold mb-2')
            
            with ui.grid(columns=2).classes('w-full gap-4'):
                for element in self.settings_elements:
                    element.create_ui()
            
            # Button to refresh channel display if n_channels changed
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
            
            # Create channel displays
            self.render_channels()
    
    def shutdown(self):
        """Clean shutdown"""
        logger.info("Shutting down ArtNet receiver...")
        self.stop_listening()
        self.settings_manager.save()
        logger.info("Shutdown complete")


# Create the application
receiver = ArtNetReceiver()

# Setup shutdown handler
app.on_shutdown(receiver.shutdown)

# Create UI
receiver.create_ui()

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title='ArtNet DMX Receiver',
        host="0.0.0.0",
        port=8081,
        reload=False,
        dark=True
    )

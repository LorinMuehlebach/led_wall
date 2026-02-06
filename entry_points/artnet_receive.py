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
        self.universe = 0
        self.start_channel = 1
        self.n_channels = 10
        
        # ArtNet server
        self.server = None
        self.listener_id = None
        self.is_listening = False
        
        # Channel values storage
        self.channel_values = [0] * self.n_channels
        self.last_update = time.time()
        self.packet_count = 0
        
        # UI elements
        self.status_label = None
        self.listen_button = None
        self.packet_counter_label = None
        self.last_update_label = None
        self.channel_labels = []
        self.channel_progress_bars = []
        
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
                label='Universe',
                input=ui.number,
                settings_id='universe',
                default_value=self.universe,
                on_change=lambda e: setattr(self, 'universe', int(e.value) if e.value is not None else 0),
                manager=self.settings_manager,
                precision=0,
                min=0,
                max=32767
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
                label='Number of Channels',
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
            self.channel_values = [0] * self.n_channels
            # In a real app we might want to rebuild the UI, but for simplicity we'll just handle buffer sizing
            # The UI rebuild requires clearing and adding elements which is complex in this setup without refreshable
    
    def on_dmx_received(self, data):
        """Callback when DMX data is received"""
        try:
            self.packet_count += 1
            self.last_update = time.time()
            
            # data is a list of byte values [val1, val2, ...]
            # Extract the channels we're interested in
            for i in range(self.n_channels):
                # DMX channels are 1-based, data list is 0-based
                # if start_channel is 1, index is 0
                channel_index = self.start_channel - 1 + i
                
                if channel_index < len(data):
                    self.channel_values[i] = data[channel_index]
                else:
                    self.channel_values[i] = 0
            
            # Update UI - we shouldn't update on every packet if high FPS, but NiceGUI handles some debouncing
            # Throttling might be needed for very high traffic, but start with direct update
            self.update_channel_display()
            
        except Exception as e:
            logger.error(f"Error processing received DMX data: {e}")
    
    def update_channel_display(self):
        """Update the UI with current channel values"""
        try:
            # Update channel displays
            for i in range(min(len(self.channel_values), len(self.channel_labels))):
                value = self.channel_values[i]
                
                # Update label text only if changed to avoid DOM thrashing
                new_text = str(int(value))
                if self.channel_labels[i].text != new_text:
                    self.channel_labels[i].text = new_text
                
                # Update progress bar height (custom div)
                percentage = (value / 255.0) * 100
                # Note: We are updating the style directly. To avoid excessive IPC calls if value hasn't changed much,
                # we could check it, but simply setting style is reasonably efficient in NiceGUI.
                # Only update if changed? We assume value change triggers this.
                self.channel_progress_bars[i].style(f'height: {percentage:.1f}%')
            
            # Update status
            if self.packet_counter_label:
                self.packet_counter_label.text = f"Packets received: {self.packet_count}"
            
            if self.last_update_label:
                self.last_update_label.text = f"Last update: {time.strftime('%H:%M:%S', time.localtime(self.last_update))}"
            
        except Exception as e:
            logger.error(f"Error updating display: {e}")
    
    def start_listening(self):
        """Start ArtNet receiver"""
        try:
            if self.is_listening:
                self.stop_listening()
                return
            
            # Create server
            # Note: StupidArtnetServer binds to port 6454 and all interfaces
            self.server = StupidArtnetServer()
            
            # Register listener for the specified universe
            # Callback receives just the data buffer
            self.listener_id = self.server.register_listener(
                universe=self.universe,
                callback_function=self.on_dmx_received
            )
            
            self.is_listening = True
            
            # Update UI
            self.update_status(f"Listening on Port 6454 (Universe {self.universe})", error=False)
            self.listen_button.props('color=negative icon=stop')
            self.listen_button.text = 'Stop'
            
            logger.info(f"Started ArtNet receiver on port 6454, Universe {self.universe}")
            
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
        """Render the channel displays"""
        self.channel_labels = []
        self.channel_progress_bars = []
        
        with ui.grid(columns=2).classes('w-full gap-4'):
            for i in range(self.n_channels):
                with ui.card().classes('p-3'):
                    ui.label(f'Ch {self.start_channel + i}').classes('text-xs text-gray-500 mb-1')
                    
                    with ui.element('div').classes('relative w-full h-6 rounded overflow-hidden bg-gray-800'):
                        progress = ui.linear_progress(value=0,show_value=False).classes('absolute w-full h-full')
                        # Using raw style for centering and color since mix-blend-mode might be tricky with default colors
                        label = ui.label('0').classes('absolute w-full h-full flex items-center justify-center text-xs font-bold')
                        # Text shadow for visibility on both dark (filled) and light (empty) backgrounds
                        label.style('color: white; text-shadow: 0 0 2px black; z-index: 10;') 
                    
                    self.channel_labels.append(label)
                    self.channel_progress_bars.append(progress)

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
        
        with ui.card().classes('w-full max-w-4xl'):
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

#!/usr/bin/env python3
"""
ArtNet Sender - Send DMX channels via ArtNet
This application provides a UI to control DMX channels and send them to an ArtNet node.
"""
import logging
from stupidArtnet import StupidArtnet
from nicegui import ui, app

from led_wall.ui.dmx_channels import DMX_channels_Input
from led_wall.ui.settings_manager import SettingsElement, SettingsManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
#logger.setLevel(logging.DEBUG)  # Set to DEBUG for more detailed output


class ArtNetSender:
    def __init__(self):
        # Settings manager for persistence
        self.settings_manager = SettingsManager(path='artnet_send_settings.json')
        
        # ArtNet configuration
        self.artnet_ip = '127.0.0.1'
        self.universe = 0
        self.start_channel = 1
        self.fps = 30
        
        # Number of DMX channels to control
        self.n_channels = 10
        
        # StupidArtnet instance
        self.artnet = None
        self.is_sending = False
        
        # DMX channels input handler
        self.dmx_inputs = DMX_channels_Input(
            n_channels=self.n_channels,
            on_change=self.on_dmx_change
        )
        
        # UI elements
        self.status_label = None
        self.connect_button = None
        
        # Settings elements
        self.settings_elements = [
            SettingsElement(
                label='ArtNet Server IP',
                input=ui.input,
                settings_id='artnet_ip',
                default_value=self.artnet_ip,
                on_change=lambda e: setattr(self, 'artnet_ip', e.value),
                manager=self.settings_manager,
                placeholder='e.g., 192.168.1.100'
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
                label='FPS',
                input=ui.number,
                settings_id='fps',
                default_value=self.fps,
                on_change=lambda e: setattr(self, 'fps', int(e.value) if e.value is not None else 30),
                manager=self.settings_manager,
                precision=0,
                min=1,
                max=60
            ),
        ]
    
    def on_dmx_change(self, event):
        """Called when DMX channel values change"""
        if self.is_sending and self.artnet:
            try:
                # Get channel values
                channels = self.dmx_inputs.get_channels()
                
                # Create DMX packet (512 channels, initialize with 0)
                dmx_packet = [0] * 512
                
                # Fill in our channel values starting at start_channel
                for i, value in enumerate(channels):
                    channel_index = self.start_channel - 1 + i
                    if channel_index < 512:
                        dmx_packet[channel_index] = int(value)
                
                # Set the packet and send
                self.artnet.set(dmx_packet)
                self.artnet.show() # Disabled explicitly because start() handles it
                
                logger.debug(f"Sent DMX data: {channels}")
            except Exception as e:
                logger.error(f"Error sending ArtNet data: {e}")
                self.update_status(f"Error: {e}", error=True)
    
    def connect_artnet(self):
        """Initialize ArtNet connection"""
        try:
            if self.is_sending:
                # Disconnect
                self.disconnect_artnet()
                return
            
            # Validate inputs
            if not self.artnet_ip:
                self.update_status("Error: Please enter an ArtNet server IP", error=True)
                return
            
            # Create StupidArtnet instance
            # stupidArtnet takes: target_ip, universe, packet_size, fps, even_packet_size, broadcast
            self.artnet = StupidArtnet(
                target_ip=self.artnet_ip,
                universe=self.universe,
                packet_size=512,  # Standard DMX packet size
                fps=self.fps,
                even_packet_size=True,
                broadcast=False
            )
            
            # Start sending
            #self.artnet.start()
            self.is_sending = True
            
            # Update UI
            self.update_status(f"Connected to {self.artnet_ip} (Universe {self.universe})", error=False)
            self.connect_button.props('color=negative icon=stop')
            self.connect_button.text = 'Disconnect'
            
            # Send initial values
            self.on_dmx_change(None)
            
            logger.info(f"Connected to ArtNet node at {self.artnet_ip}, Universe {self.universe}")
            
        except Exception as e:
            logger.error(f"Failed to connect to ArtNet: {e}")
            self.update_status(f"Connection failed: {e}", error=True)
            self.is_sending = False
    
    def disconnect_artnet(self):
        """Stop ArtNet transmission"""
        try:
            if self.artnet:
                self.artnet.stop()
                self.artnet = None
            
            self.is_sending = False
            
            # Update UI
            self.update_status("Disconnected", error=False)
            self.connect_button.props('color=positive icon=cast')
            self.connect_button.text = 'Connect'
            
            logger.info("Disconnected from ArtNet")
            
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
    
    def update_status(self, message: str, error: bool = False):
        """Update status label"""
        if self.status_label:
            self.status_label.text = message
            if error:
                self.status_label.classes('text-red-500', remove='text-green-500 text-gray-500')
            else:
                self.status_label.classes('text-green-500', remove='text-red-500 text-gray-500')
    
    def create_ui(self):
        """Create the user interface"""
        ui.label('ArtNet DMX Sender').classes('text-3xl font-bold mb-4')
        
        with ui.card().classes('w-full max-w-4xl'):
            ui.label('Connection Settings').classes('text-xl font-bold mb-2')
            
            with ui.grid(columns=2).classes('w-full gap-4'):
                for element in self.settings_elements:
                    element.create_ui()
            
            ui.separator()
            
            with ui.row().classes('w-full items-center gap-4'):
                self.connect_button = ui.button(
                    'Connect',
                    on_click=self.connect_artnet,
                    icon='cast'
                ).props('color=positive')
                
                self.status_label = ui.label('Not connected').classes('text-gray-500')
        
        ui.separator()
        
        with ui.card().classes('w-full max-w-4xl'):
            ui.label('DMX Channels').classes('text-xl font-bold mb-2')
            ui.label(f'Channels will be sent starting at channel {self.start_channel}').classes('text-sm text-gray-500 mb-4')
            self.dmx_inputs.create_ui()
    
    def shutdown(self):
        """Clean shutdown"""
        logger.info("Shutting down ArtNet sender...")
        self.disconnect_artnet()
        #self.settings_manager.save()
        logger.info("Shutdown complete")


# Create the application
sender = ArtNetSender()

# Setup shutdown handler
app.on_shutdown(sender.shutdown)

# Create UI
sender.create_ui()

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title='ArtNet DMX Sender',
        host="0.0.0.0",
        port=8082,
        reload=False,
        dark=True
    )

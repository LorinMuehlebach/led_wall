#!/usr/bin/env python3
"""
sACN Sender - Send DMX channels via sACN (E1.31)
This application provides a UI to control DMX channels and send them via sACN/E1.31.
"""
import logging
import sacn
from nicegui import ui, app

from led_wall.ui.dmx_channels import DMX_channels_Input
from led_wall.ui.settings_manager import SettingsElement, SettingsManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
#logger.setLevel(logging.DEBUG)  # Set to DEBUG for more detailed output


class SACNSender:
    def __init__(self):
        # Settings manager for persistence
        self.settings_manager = SettingsManager(path='sacn_send_settings.json')
        
        # sACN configuration
        self.bind_ip = ''  # Empty string = bind to all interfaces
        self.universe = 1  # sACN universes start at 1
        self.start_channel = 1
        self.fps = 30
        self.multicast = True  # sACN typically uses multicast
        self.unicast_ip = '127.0.0.1'  # Unicast destination IP
        
        # Number of DMX channels to control
        self.n_channels = 10
        
        # sACN sender instance
        self.sender = None
        self.is_sending = False
        
        # DMX channels input handler
        self.dmx_inputs = DMX_channels_Input(
            n_channels=self.n_channels,
            on_change=self.on_dmx_change
        )
        
        # UI elements
        self.status_label = None
        self.connect_button = None
        self.unicast_ip_container = None  # Container for unicast IP field
        
        # Settings elements (created later in create_ui)
        self.settings_elements = []
    
    def _create_settings_elements(self):
        """Create settings elements (must be called within UI context)"""
        self.settings_elements = [
            SettingsElement(
                label='Universe',
                input=ui.number,
                settings_id='universe',
                default_value=self.universe,
                on_change=lambda e: setattr(self, 'universe', int(e.value) if e.value is not None else 1),
                manager=self.settings_manager,
                precision=0,
                min=1,
                max=63999
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
                max=44  # sACN spec recommends max 44 fps
            ),
            SettingsElement(
                label='Use Multicast',
                input=ui.switch,
                settings_id='multicast',
                default_value=self.multicast,
                on_change=self.on_multicast_change,
                manager=self.settings_manager,
            ),
            SettingsElement(
                label='Bind IP (optional)',
                input=ui.input,
                settings_id='bind_ip',
                default_value=self.bind_ip,
                on_change=lambda e: setattr(self, 'bind_ip', e.value),
                manager=self.settings_manager,
                placeholder='Leave empty for all interfaces'
            ),
        ]
    
    def on_multicast_change(self, e):
        """Handle multicast toggle"""
        self.multicast = e.value
        # Show/hide unicast IP field based on multicast setting
        if self.unicast_ip_container:
            self.unicast_ip_container.set_visibility(not self.multicast)
    
    def on_dmx_change(self, event):
        """Called when DMX channel values change"""
        if self.is_sending and self.sender:
            try:
                # Get channel values
                channels = self.dmx_inputs.get_channels()
                
                # Create DMX packet (512 channels, initialize with 0)
                dmx_packet = tuple([0] * 512)
                dmx_list = list(dmx_packet)
                
                # Fill in our channel values starting at start_channel
                for i, value in enumerate(channels):
                    channel_index = self.start_channel - 1 + i
                    if channel_index < 512:
                        dmx_list[channel_index] = int(value)
                
                # Set the DMX data for the universe
                self.sender[self.universe].dmx_data = tuple(dmx_list)
                
                logger.debug(f"Sent DMX data: {channels}")
            except Exception as e:
                logger.error(f"Error sending sACN data: {e}")
                self.update_status(f"Error: {e}", error=True)
    
    def connect_sacn(self):
        """Initialize sACN connection"""
        try:
            if self.is_sending:
                # Disconnect
                self.disconnect_sacn()
                return
            
            # Create sACN sender instance
            # Optional: bind_address for specific interface
            if self.bind_ip:
                self.sender = sacn.sACNsender(bind_address=self.bind_ip, fps=self.fps)
            else:
                self.sender = sacn.sACNsender(fps=self.fps)
            
            # Start sender
            self.sender.start()
            
            # Activate the universe
            self.sender.activate_output(self.universe)
            
            # Configure multicast or unicast
            if self.multicast:
                self.sender[self.universe].multicast = True
                mode_str = "Multicast"
            else:
                if not self.unicast_ip:
                    self.update_status("Error: Please enter a unicast destination IP", error=True)
                    self.sender.stop()
                    self.sender = None
                    return
                self.sender[self.universe].destination = self.unicast_ip
                self.sender[self.universe].multicast = False
                mode_str = f"Unicast to {self.unicast_ip}"
            
            self.is_sending = True
            
            # Update UI
            self.update_status(f"Sending on Universe {self.universe} ({mode_str})", error=False)
            self.connect_button.props('color=negative icon=stop')
            self.connect_button.text = 'Stop'
            
            # Send initial values
            self.on_dmx_change(None)
            
            logger.info(f"Started sACN sender on Universe {self.universe} ({mode_str})")
            
        except Exception as e:
            logger.error(f"Failed to start sACN sender: {e}")
            self.update_status(f"Connection failed: {e}", error=True)
            self.is_sending = False
            if self.sender:
                try:
                    self.sender.stop()
                except Exception:
                    pass
                self.sender = None
    
    def disconnect_sacn(self):
        """Stop sACN transmission"""
        try:
            if self.sender:
                self.sender.stop()
                self.sender = None
            
            self.is_sending = False
            
            # Update UI
            self.update_status("Stopped", error=False)
            self.connect_button.props('color=positive icon=cast')
            self.connect_button.text = 'Start'
            
            logger.info("Stopped sACN sender")
            
        except Exception as e:
            logger.error(f"Error stopping: {e}")
    
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
        ui.label('sACN (E1.31) DMX Sender').classes('text-3xl font-bold mb-4')
        
        with ui.card().classes('w-full max-w-4xl'):
            ui.label('Connection Settings').classes('text-xl font-bold mb-2')
            
            with ui.grid(columns=2).classes('w-full gap-4'):
                # Create settings elements within UI context
                self._create_settings_elements()
                for element in self.settings_elements:
                    element.create_ui()
                
                # Create unicast IP field separately with visibility control
                self.unicast_ip_container = ui.row().classes('flex items-center')
                with self.unicast_ip_container:
                    ui.label('Unicast Destination IP').classes('place-content-center')
                    self.unicast_ip_input = ui.input(
                        value=self.unicast_ip,
                        placeholder='e.g., 192.168.1.100',
                        on_change=lambda e: setattr(self, 'unicast_ip', e.value)
                    )
                # Set initial visibility based on multicast setting
                self.unicast_ip_container.set_visibility(not self.multicast)
            
            ui.separator()
            
            with ui.row().classes('w-full items-center gap-4'):
                self.connect_button = ui.button(
                    'Start',
                    on_click=self.connect_sacn,
                    icon='cast'
                ).props('color=positive')
                
                self.status_label = ui.label('Not sending').classes('text-gray-500')
        
        ui.separator()
        
        with ui.card().classes('w-full max-w-4xl'):
            ui.label('DMX Channels').classes('text-xl font-bold mb-2')
            ui.label(f'Channels will be sent starting at channel {self.start_channel}').classes('text-sm text-gray-500 mb-4')
            self.dmx_inputs.create_ui()
    
    def shutdown(self):
        """Clean shutdown"""
        logger.info("Shutting down sACN sender...")
        self.disconnect_sacn()
        logger.info("Shutdown complete")


# Create the application
sender = SACNSender()

# Setup shutdown handler
app.on_shutdown(sender.shutdown)

# Create UI
sender.create_ui()

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title='sACN (E1.31) DMX Sender',
        host="0.0.0.0",
        port=8083,
        reload=False,
        dark=True
    )

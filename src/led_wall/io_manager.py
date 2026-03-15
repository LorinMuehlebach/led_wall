import time
import numpy as np
from threading import Thread, current_thread
from logging import getLogger

from led_wall.MultiUniverseArtnet import StupidArtnet
from led_wall.sacn_input import SACNInput
from led_wall.win_utils import HighResolutionTimer


from nicegui import ui

from led_wall.ui.settings_manager import SettingsElement, SettingsManager
from led_wall.ui.dmx_channels import DMX_channels_Input
from led_wall.ui.preview_window import preview_setup, create_preview_frame, OutputCorrection

logger = getLogger(__name__)

class IO_Manager():
    """
    handles the io loop for the led wall.

    """
    output_buffer: np.ndarray = None
    SLEEP_THRESHOLD: float = 0.005  # seconds – spin-wait margin

    def __init__(self,settings_manager:SettingsManager,framerate:int=50,preview_in_window:bool=False) -> None:
        """
        initializes the io manager.

        Parameters:
            resolution (tuple[int, int]): The resolution of the LED Wall
            dimensions (tuple[int, int]): The dimensions of the LED wall in Meter
            dmx_channel_inputs (DMX_channels_Input): The DMX channel inputs manager
            RGBW (bool): Whether the output is RGBW or not.
            framerate (int): The framerate of the output.

        """
        self.settings_manager = SettingsManager(parent=settings_manager, name="io_settings")
        self.dmx_channel_inputs = DMX_channels_Input(14)

        # sACN input
        self.sacn_input: SACNInput | None = None
        self.input_universe = 1
        self.input_dmx_address = 1
        self.input_filter = 0.5  # seconds for a full 0-255 change

        
        self.pixel_channels = 4
        self.resolution = (30,58) #resolution of the LED wall in pixels
        self.dimensions = (6, 3) #dimension of the LED wall in meters
        self.framerate = framerate
        self.preview_in_window = preview_in_window
        
        self.output_artnet_ip = '192.168.178.100'
        self.output_artnet_port = 6454
        self.addressing_direction = 'vertical' #can be 'horizontal' or 'vertical'
        self.reverse_addressing = True
        self.consecutive_universes = 5
        self.device_order_reversed = True
        self.device_universes = 8
        self.black_on_close = True #whether to send black on close of the application, can be disabled for testing to prevent issues with StupidArtnet when restarting the loop multiple times in a short time
        self.gamma_correction = list(OutputCorrection.available_methods().keys())[0] #available gamma correction methods for the output, can be set to a specific method or None to disable gamma correction
        self.flip_top_bottom = False
        self.flip_left_right = False

        self.settings_menu = {
            "Display": [
                SettingsElement(
                    label='Auflösung Breite',
                    input=ui.number,
                    default_value=self.resolution[0],
                    settings_id='resolution_width',
                    on_change=lambda e, self=self: (setattr(self, 'resolution', (int(e.value) if e.value is not None else self.resolution[0], self.resolution[1])), self.output_artnet_init()),
                    precision=0,
                    suffix=" px",
                    manager=self.settings_manager,
                ),
                SettingsElement(
                    label='Auflösung Höhe',
                    input=ui.number,
                    default_value=self.resolution[1],
                    settings_id='resolution_height',
                    on_change=lambda e, self=self: (setattr(self, 'resolution', (self.resolution[0], int(e.value) if e.value is not None else self.resolution[1])), self.output_artnet_init()),
                    precision=0,
                    suffix=" px",
                    manager=self.settings_manager,
                ),
                SettingsElement(
                    label='Abmessungen Breite',
                    input=ui.number,
                    default_value=self.dimensions[0],
                    settings_id='dimensions_width',
                    on_change=lambda e, self=self: setattr(self, 'dimensions', (int(e.value) if e.value is not None else self.dimensions[0], self.dimensions[1])),
                    precision=0,
                    suffix=" m",
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='Abmessungen Höhe',
                    input=ui.number,
                    default_value=self.dimensions[1],
                    settings_id='dimensions_height',
                    on_change=lambda e, self=self: setattr(self, 'dimensions', (self.dimensions[0], int(e.value) if e.value is not None else self.dimensions[1])),
                    precision=0,
                    suffix=" m",
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='Framerate',
                    input=ui.number,
                    default_value=self.framerate,
                    settings_id='framerate',
                    on_change=lambda e, self=self: setattr(self, 'framerate', int(e.value) if e.value is not None else self.framerate),
                    precision=0,
                    manager=self.settings_manager,
                    min=10, max=60 #limit framerate to prevent issues with StupidArtnet at high framerates
                ),
                SettingsElement(
                    label='RGBW LEDs',
                    input=ui.switch,
                    default_value=self.pixel_channels == 4,
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='preview in window',
                    input=ui.switch,
                    default_value=self.preview_in_window,
                    on_change=lambda e, self=self: setattr(self, 'preview_in_window', e.value),
                    manager=self.settings_manager
                ),
            ],
            "Eingang": [
                SettingsElement(
                    label='DMX Adresse',
                    input=ui.number,
                    settings_id='input_dmx_address',
                    default_value=self.input_dmx_address,
                    on_change=lambda e, self=self: self.input_init(dmx_address=int(e.value) if e.value is not None else self.input_dmx_address),
                    precision=0,
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='Universum',
                    input=ui.number,
                    settings_id='input_universe',
                    default_value=self.input_universe,
                    on_change=lambda e, self=self: self.input_init(universum=int(e.value) if e.value is not None else self.input_universe),
                    precision=0,
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='Filter (s full change)',
                    input=ui.number,
                    settings_id='input_filter',
                    default_value=self.input_filter,
                    on_change=lambda e, self=self: self.input_init(filter=float(e.value) if e.value is not None else self.input_filter),
                    precision=2,
                    manager=self.settings_manager
                ),
            ],
            "Ausgang": [
                SettingsElement(
                    label='Artnet IP',
                    input=ui.input,
                    settings_id='artnet_ip',
                    default_value=self.output_artnet_ip,
                    on_change=lambda e, self=self: self.output_artnet_init(ip=e.value) if e.value else None,
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='Port',
                    input=ui.number,
                    settings_id='artnet_port',
                    default_value=self.output_artnet_port,
                    on_change=lambda e, self=self: (setattr(self, 'output_artnet_port', int(e.value) if e.value is not None else self.output_artnet_port), self.output_artnet_init()),
                    precision=0,
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='addressing direction',
                    input=ui.select,
                    settings_id='addressing_direction',
                    default_value=self.addressing_direction,
                    on_change=lambda e, self=self: (setattr(self, 'addressing_direction', e.value), self.output_artnet_init()),
                    options=['horizontal','vertical'],
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='flip top-bottom',
                    input=ui.switch,
                    settings_id='flip_top_bottom',
                    default_value=self.flip_top_bottom,
                    on_change=lambda e, self=self: setattr(self, 'flip_top_bottom', e.value),
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='flip left-right',
                    input=ui.switch,
                    settings_id='flip_left_right',
                    default_value=self.flip_left_right,
                    on_change=lambda e, self=self: setattr(self, 'flip_left_right', e.value),
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='reverse addressing',
                    input=ui.switch,
                    settings_id='reverse_addressing',
                    default_value=self.reverse_addressing,
                    on_change=lambda e, self=self: setattr(self, 'reverse_addressing', e.value),
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='device order reversed',
                    input=ui.switch,
                    settings_id='device_order_reversed',
                    default_value=self.device_order_reversed,
                    on_change=lambda e, self=self: setattr(self, 'device_order_reversed', e.value),
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='consecutive universes',
                    input=ui.number,
                    settings_id='consecutive_universes',
                    default_value=self.consecutive_universes,
                    on_change=lambda e, self=self: (setattr(self, 'consecutive_universes', int(e.value) if e.value is not None else self.consecutive_universes), self.output_artnet_init()),
                    precision=0,
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='device universes',
                    input=ui.number,
                    settings_id='device_universes',
                    default_value=self.device_universes,
                        on_change=lambda e, self=self: (setattr(self, 'device_universes', int(e.value) if e.value is not None else self.device_universes), self.output_artnet_init()),
                    precision=0,
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='black on close',
                    input=ui.switch,
                    settings_id='black_on_close',
                    default_value=self.black_on_close,
                    on_change=lambda e, self=self: setattr(self, 'black_on_close', e.value),
                    manager=self.settings_manager
                ),
                SettingsElement(
                    label='gamma correction',
                    input=ui.select,
                    settings_id='gamma_correction',
                    default_value=self.gamma_correction,
                    on_change=lambda e, self=self: setattr(self, 'gamma_correction', e.value),
                    options=OutputCorrection.available_methods(),
                    manager=self.settings_manager
                ),
            ]
        }

        self.output_buffer = np.zeros((self.resolution[0], self.resolution[1], self.pixel_channels), dtype=np.uint8)
        
        self.create_frame = None #callback function to the selected effect

        self.ts_last_frame = 0
        #no not start thread here to prevent issues with multiple instances of IO_Manager in the same process (e.g. when running multiple presets) which can cause multiple threads to be started and interfere with each other. Start the thread in the entry point instead.
        self.run = False
        self.run_thread = None 

        #start input
        self.is_initialized = True
        self._init_sacn_input()
        self.output_artnet_init()

    @ui.refreshable
    def ui_settings(self) -> None:
        """
        Create the settings UI for this object
        This method is called on create ui settings
        """

        for category, elements in self.settings_menu.items():
            with ui.expansion(category).classes('w-full'):
                with ui.column().classes('w-full ml-4'):
                    for element in elements:
                        element.create_ui()

        # with ui.expansion('Eingänge / Ausgänge').classes('w-full'):
        # with ui.column().classes('w-full'):
        #     for element in self.settings_elements:
        #         element.create_ui()

    @ui.refreshable
    def dmx_channel_ui(self) -> None:
        self.dmx_channel_inputs.create_ui()

    def start_loop(self) -> None:
        print("Starting IO loop thread...")
        # Prevent self-joining if called from within the loop thread
        if self.run_thread is not None:
            if self.run_thread is current_thread():
                self.run = True
                # logger.debug("start_loop called from within run_loop. Ignoring restart request.")
                return

            self.run = True
            if self.run_thread.is_alive():
                self.run = False
                try:
                    self.run_thread.join(timeout=1.0)  # Wait for the thread to finish if it's already running
                except RuntimeError:
                    pass
                logger.warning("Previous loop thread was still running. Restarted the loop.")
        
        # Always create a new thread since threads cannot be restarted
        self.run = True
        self.run_thread = Thread(target=self.run_loop, daemon=True)
        self.run_thread.start()

    def stop_loop(self) -> None:
        self.run = False

        # Stop sACN input
        if self.sacn_input is not None:
            self.sacn_input.stop()
            self.sacn_input = None

        if hasattr(self, 'artnet_sender'):
            self.artnet_sender.stop()
            del self.artnet_sender

        if self.run_thread is not None and self.run_thread.is_alive() and self.run_thread is not current_thread():
            try:
                self.run_thread.join(timeout=2.0)
                if self.run_thread.is_alive():
                    print("Warning: Thread did not stop within timeout")
            except Exception as e:
                print(f"Error stopping loop: {e}")

    def stop_thread(self) -> None:
        """
        Stops the loop thread without tearing down ArtNet resources.
        """
        self.run = False
        if self.run_thread is not None and self.run_thread.is_alive() and self.run_thread is not current_thread():
            try:
                self.run_thread.join(timeout=2.0)
            except Exception as e:
                logger.error(f"Error stopping loop thread: {e}")

    def __del__(self):
        if self.black_on_close:
            # Send black frame on close to prevent issues with StupidArtnet when restarting the loop multiple times in a short time
            self.output_buffer = np.zeros((self.resolution[0], self.resolution[1], self.pixel_channels), dtype=np.uint8)
            self.update_artnet_output()

        self.stop_loop()

    def step(self):
        """
        Single step of the loop.
        Calls sACN smoothing, updates sliders on change, renders the frame,
        and sends artnet output.
        """
        self.ts_last_frame = time.time()

        # Run one smoothing tick on the sACN input
        if self.sacn_input is not None:
            values, changed = self.sacn_input.smoothing_step()
            if changed:
                self.dmx_channel_inputs.update_sliders(values, external=True)

        channels = self.dmx_channel_inputs.get_channels()
        frame = self.create_frame(channels, last_output=self.output_buffer) if self.create_frame else self.output_buffer

        self.output_buffer = frame

        self.update_artnet_output()

    def run_loop(self):
        """
        loop which runs at the defined framerate.
        Uses perf_counter for sub-ms timing accuracy on Windows.
        """
        clock = time.perf_counter
        print("IO loop started.")
        last_log_time: float = clock()
        frame_count: int = 0
        actual_period_sum: float = 0.0
        last_tick: float = clock()
        with HighResolutionTimer() as hrt:
            while self.run:
                try:
                    tick_start: float = clock()
                    frame_period: float = 1.0 / max(min(self.framerate,60), 1) # Avoid division by zero

                    step_start: float = clock()
                    self.step()
                    step_end: float = clock()
                    step_duration: float = step_end - step_start

                    # Wait for the remainder of the frame period.
                    # Sleep the coarse part to release the CPU, then spin-wait
                    # the tail using perf_counter for sub-ms accuracy.
                    deadline: float = tick_start + frame_period
                    remaining: float = deadline - clock()
                    if remaining > self.SLEEP_THRESHOLD:
                        time.sleep(remaining - self.SLEEP_THRESHOLD)
                    while clock() < deadline:
                        pass

                    # Re-request high timer resolution periodically
                    # (Windows may silently reclaim it during long sessions)
                    hrt.tick()

                    # Timing stats
                    now: float = clock()
                    actual_period_sum += now - last_tick
                    last_tick = now
                    frame_count += 1
                    if now - last_log_time >= 2.0:
                        avg_period = actual_period_sum / frame_count if frame_count else 0
                        print(f"[IO] target: {frame_period*1000:.1f}ms ({1/frame_period:.0f}fps) | "
                              f"actual: {avg_period*1000:.1f}ms ({1/avg_period:.0f}fps) | step: {step_duration*1000:.1f}ms")
                        last_log_time = now
                        frame_count = 0
                        actual_period_sum = 0.0
                except Exception as e:
                    logger.error(f"Error in IO loop: {e}", exc_info=True)
                    time.sleep(0.5)  # Sleep briefly to avoid tight error loop
        print("IO loop stopped.")

    def get_channels(self):
        return self.dmx_channel_inputs.get_channels()

    def input_init(self, dmx_address: int | None = None, universum: int | None = None, filter: float | None = None) -> None:
        """(Re-)initialize the sACN input with updated parameters."""
        if dmx_address is not None:
            self.input_dmx_address = dmx_address
        if universum is not None:
            self.input_universe = universum
        if filter is not None:
            self.input_filter = filter

        self._init_sacn_input()

    def _init_sacn_input(self) -> None:
        """Create (or recreate) the SACNInput wrapper."""
        if not getattr(self, 'is_initialized', False):
            return

        # Tear down previous instance
        if self.sacn_input is not None:
            self.sacn_input.stop()

        self.sacn_input = SACNInput(
            universe=self.input_universe,
            start_channel=self.input_dmx_address,
            n_channels=self.dmx_channel_inputs.n_channels,
            callback=lambda values: None,  # driven externally via smoothing_step()
            framerate=self.framerate,
            time_full_change=self.input_filter,
            multicast=True,
            use_internal_loop=False,
        )
        self.sacn_input.start()
        logger.info(
            "sACN input initialized: universe=%d, start=%d, channels=%d, filter=%.2fs",
            self.input_universe, self.input_dmx_address,
            self.dmx_channel_inputs.n_channels, self.input_filter,
        )

    def output_artnet_init(self, ip:str=None):
        if ip is not None:
            self.output_artnet_ip = ip

        if not getattr(self, 'is_initialized', False):
            return

        # Clean up existing senders
        if hasattr(self, 'artnet_sender'):
            self.artnet_sender.stop()
            del self.artnet_sender
        
        # Number of segments (columns or rows) that correspond to universes
        num_segments = self.resolution[0] if self.addressing_direction == 'vertical' else self.resolution[1]
        packets_per_universe = self.pixel_channels * (self.resolution[1] if self.addressing_direction == 'vertical' else self.resolution[0])

        current_universe = 0
        consecutive_count = 0
        
        all_universes = []
        self.segment_to_universe = {}

        for i in range(num_segments):
            all_universes.append(current_universe)
            self.segment_to_universe[i] = current_universe
            
            consecutive_count += 1
            if consecutive_count >= self.consecutive_universes:
                current_universe += (self.device_universes - self.consecutive_universes) + 1
                consecutive_count = 0
            else:
                current_universe += 1
        
        self.artnet_sender = StupidArtnet(
            target_ip=self.output_artnet_ip,
            universes=all_universes,
            packet_size=packets_per_universe,
            fps=self.framerate,
            port=self.output_artnet_port
        )
        #not needed we will call show ourselves
        #self.artnet_sender.start()

    last_thread_id: int | None = None
    def update_artnet_output(self):
        if not hasattr(self, 'artnet_sender') or not self.artnet_sender:
            return
        
        # Check if multiple threads are trying to send data at the same time which can cause issues with StupidArtnet
        current_thread_id = current_thread().ident
        if self.last_thread_id is not None and self.last_thread_id != current_thread_id:
            import threading
            # Check if the previous thread is still active
            if any(t.ident == self.last_thread_id for t in threading.enumerate()):
                logger.warning(f"Multiple threads running in update_artnet_output: last_thread_id={self.last_thread_id}, current_thread_id={current_thread_id}")
        self.last_thread_id = current_thread_id

        width, height = self.resolution

        # Apply global flips if needed
        output_buffer = self.output_buffer
        if self.flip_top_bottom:
            output_buffer = np.flip(output_buffer, axis=1) # flip vertically
        if self.flip_left_right:
            output_buffer = np.flip(output_buffer, axis=0) # flip horizontally

        if self.gamma_correction is not None:
            output_buffer = OutputCorrection.apply(output_buffer, self.gamma_correction)
        
        if self.addressing_direction == 'vertical':
            for x in range(width):
                if x >= len(self.segment_to_universe):
                    break

                if self.reverse_addressing:
                    x = (width - 1) - x # flip
                
                # Apply device order mapping if needed (reverses blocks of columns)
                source_x = x
                if self.device_order_reversed and self.consecutive_universes > 0:
                    num_blocks = width // self.consecutive_universes
                    block_idx = x // self.consecutive_universes
                    if block_idx < num_blocks:
                        idx_in_block = x % self.consecutive_universes
                        reversed_block_idx = (num_blocks - 1) - block_idx
                        source_x = reversed_block_idx * self.consecutive_universes + idx_in_block

                # Get column data
                segment_data = output_buffer[source_x, :, :]
                
                # Flatten data to list of ints for StupidArtnet
                dmx_values = segment_data.flatten().tolist()
                self.artnet_sender.set(dmx_values, universe=self.segment_to_universe[x])
        else:
            for y in range(height):
                if y >= len(self.segment_to_universe):
                    break
                
                # Apply device order mapping if needed (reverses blocks of rows)
                source_y = y
                if self.device_order_reversed and self.consecutive_universes > 0:
                    num_blocks = height // self.consecutive_universes
                    block_idx = y // self.consecutive_universes
                    if block_idx < num_blocks:
                        idx_in_block = y % self.consecutive_universes
                        reversed_block_idx = (num_blocks - 1) - block_idx
                        source_y = reversed_block_idx * self.consecutive_universes + idx_in_block

                # Get row data
                segment_data = self.output_buffer[:, source_y, :]
                
                if self.reverse_addressing:
                    segment_data = np.flip(segment_data, axis=0) # flip horizontally
                
                dmx_values = segment_data.flatten().tolist()
                self.artnet_sender.set(dmx_values, universe=self.segment_to_universe[y])

        self.artnet_sender.show()

    def update_DMX_channels(self, channels):
        self.dmx_channel_inputs.update_sliders(channels)

    def init_preview(self,preview_image: ui.interactive_image) -> callable:
        """
        initializes the preview window for the led wall.
        """
        self.preview_height = 200
        aspect_ratio = self.dimensions[0] / self.dimensions[1]
        self.preview_width = int(self.preview_height * aspect_ratio)
        self.preview_image = preview_image

    def setup_preview(self) -> None:
        """
        sets up the preview window for the led wall.
        """
        if self.preview_in_window:
            return #do not show in browser
        
        if not self.preview_image:
            raise ValueError("Preview image not initialized. Call init_preview() first.")

        # Closure to get the latest buffer and parameters
        def get_preview():
            return create_preview_frame(
                output_buffer=self.output_buffer,
                resolution=self.resolution,
                pixel_channels=self.pixel_channels,
                preview_width=self.preview_width,
                preview_height=self.preview_height
            )

        self.preview_timer = preview_setup(self.preview_image, get_preview_frame=None, io_manager=self)

def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# class OutputCorrection:
#     @staticmethod
#     def apply(output_buffer: np.ndarray, method: str, max_val: int = 0xFF) -> np.ndarray:
#         if method == 'linear':
#             return output_buffer
#         elif method == 'quadratic':
#             return ((output_buffer ** 2) / max_val).astype(np.uint8)
#         elif method == 'cubic':
#             return ((output_buffer ** 3) / (max_val ** 2)).astype(np.uint8)
#         elif method == 'quadruple':
#             return ((output_buffer ** 4) / (max_val ** 3)).astype(np.uint8)
#         elif method == '2.2 gamma':
#             gamma = 2.2
#             return (max_val * ((output_buffer / max_val) ** gamma)).astype(np.uint8)
#         else:
#             raise ValueError(f"Unknown correction method: {method}")

#     @staticmethod
#     def available_methods():
#         return {"linear": "Linear (no correction)", 
#                 "quadratic": "Quadratic", 
#                 "cubic": "Cubic", 
#                 "quadruple": "Quadruple",
#                 "2.2 gamma": "Gamma 2.2 (approximation of sRGB)"}
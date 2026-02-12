import os
import numpy as np
import cv2
import logging
import base64
import time
from nicegui import ui
from led_wall.effects.base_effect import BaseEffect
from led_wall.datatypes import RGBW_Color, Fader
from led_wall.ui.settings_manager import SettingsElement
from led_wall.ui.media_manager import MediaManager
#from led_wall.ui.video_manager import VideoManager

logger = logging.getLogger("utils")
logger.setLevel(logging.DEBUG)

class ColorMix(BaseEffect):
    """
    Effect that blends between two colors using different noise patterns or an image.
    """

    NAME = 'Color Mix'
    DESCRIPTION = 'Blends two colors using selectable noise patterns or a grayscale image. Controls for blend balance and scale.'

    def __init__(self, resolution: tuple[int, int], dimensions: tuple[int, int], rgbw: bool, settings_manager=None) -> None:
        # Initialize media manager before super().__init__ because it might be needed by settings
        self.media_manager = MediaManager(settings_manager, resolution=resolution, dimensions=dimensions, grayscale=True)
        # Use specific IDs for backward compatibility and to avoid conflicts
        self.media_manager.media_path_setting_id = "noise_image_file"
        self.media_manager.fill_mode_setting_id = "noise_image_mapping"
        self.media_manager.offset_x_id = "noise_image_offset_x"
        self.media_manager.offset_y_id = "noise_image_offset_y"
        self.media_manager.scale_id = "noise_image_scale"
        self.media_manager.rotation_id = "noise_image_rotation"

        # self.video_manager = VideoManager(settings_manager, resolution=resolution, dimensions=dimensions, grayscale=True)
        # self.video_manager.media_path_setting_id = "noise_video_file"
        # self.video_manager.fill_mode_setting_id = "noise_video_mapping"
        # self.video_manager.offset_x_id = "noise_video_offset_x"
        # self.video_manager.offset_y_id = "noise_video_offset_y"
        # self.video_manager.scale_id = "noise_video_scale"
        # self.video_manager.rotation_id = "noise_video_rotation"
        
        super().__init__(resolution, dimensions, rgbw, settings_manager)
        
        # Ensure media directory exists
        if not os.path.exists('media'):
            os.makedirs('media')

        # Add custom inputs for the color mix
        # Existing in BaseEffect: master (1), rgbw_color (4), mode (1)
        # Total channels used so far: 6
        # New inputs:
        self.inputs['color2'] = RGBW_Color([255, 255, 255, 255]) # 4 channels
        self.inputs['blend'] = Fader(127) # 1 channel - shifts the blend balance
        self.inputs['noise_scale'] = Fader(127) # 1 channel - scale/frequency of the noise
        self.inputs['animation_speed'] = Fader(0) # 1 channel - speed of the noise animation

        self.res_x, self.res_y = self.resolution
        self._noise_pattern = None
        self._last_noise_settings = None
        self._base_small_noise = None
        self._last_base_settings = None

    def _get_media_files(self):
        if not os.path.exists('media'):
            return []
        files = [f for f in os.listdir('media') if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))]
        return sorted(files)

    def run_raw(self, DMX_channels, last_output: np.array) -> np.array:
        """
        Calculates the noise blend frame.
        """
        # update_inputs is called by EffectManager before this method
        
        # Get input values and normalize
        master = self.inputs['master'].value / 255.0
        c1 = np.array(self.inputs['rgbw_color'].get_channels()) * master
        c2 = np.array(self.inputs['color2'].get_channels()) * master
        
        blend_offset = (self.inputs['blend'].value / 255.0) * 2.0 - 1.0
        
        # Only regenerate noise if the pattern type, scale, mode or image has changed
        noise = self._generate_noise()
        
        # Apply blend offset to noise values and clip to [0, 1]
        # t = 0 means color 1, t = 1 means color 2
        t = np.clip(noise + blend_offset, 0.0, 1.0)
        
        # Reshape for broadcasting (res_x, res_y, 1) to match color channels
        t_3d = t[:, :, np.newaxis]
        
        # Linear interpolation: result = c1 * (1-t) + c2 * t
        output_array = (c1 * (1.0 - t_3d) + c2 * t_3d).astype(np.uint8)
        
        return output_array

    def _generate_noise(self):
        """Generates or retrieves the cached noise pattern based on current settings."""
        mix_mode = self.settings_manager.get_setting('mix_mode') or 'Noise'

        if mix_mode == 'Video':
            # Get frame from VideoManager (H, W, 3)
            frame = self.video_manager.get_frame()
            # Use only one channel (as it's grayscale) and transpose to (W, H)
            return frame[:, :, 0].T.astype(float) / 255.0

        category = self.settings_manager.get_setting('noise_pattern_type')
        if category is None:
            category = 1 # Default to Smooth Noise
            
        noise_scale = self.inputs['noise_scale'].value
        animation_speed = self.inputs['animation_speed'].value / 255.0

        # Base settings determine the underlying noise pattern
        base_settings = (mix_mode, category, noise_scale, 
                        self.settings_manager.get_setting(self.media_manager.media_path_setting_id),
                        self.settings_manager.get_setting(self.media_manager.fill_mode_setting_id),
                        self.settings_manager.get_setting(self.media_manager.offset_x_id),
                        self.settings_manager.get_setting(self.media_manager.offset_y_id),
                        self.settings_manager.get_setting(self.media_manager.scale_id),
                        self.settings_manager.get_setting(self.media_manager.rotation_id))
        
        # Determine grid size for noise generation (min 2, max full resolution)
        min_grid = 2
        max_grid = max(self.res_x, self.res_y)
        grid_size = int(min_grid + (noise_scale / 255.0) * (max_grid - min_grid))
        grid_size = max(min_grid, grid_size)

        # 1. Regenerate base noise grid if base settings changed
        if self._base_small_noise is None or self._last_base_settings != base_settings:
            if mix_mode == 'Image':
                # Get frame from MediaManager (H, W, 3)
                frame = self.media_manager.get_frame()
                # Use only one channel (as it's grayscale) and transpose to (W, H)
                self._base_small_noise = frame[:, :, 0].T.astype(float) / 255.0
            else:
                # Use a deterministic seed from settings
                rng = np.random.RandomState(seed=int(category) * 1000 + noise_scale)
                
                # For animation, we generate a larger grid so we can scroll through it
                # We make it 2x2 grid size for easy tiling/scrolling
                source_grid = grid_size * 2
                
                if category == 0: # White Noise / Random Blocks
                    self._base_small_noise = rng.rand(source_grid, source_grid)
                elif category == 1: # Smooth Noise
                    self._base_small_noise = rng.rand(source_grid, source_grid)
                elif category == 2: # Horizontal Stripes
                    self._base_small_noise = rng.rand(source_grid, 1)
                else: # Vertical Stripes (category 3)
                    self._base_small_noise = rng.rand(1, source_grid)
            
            self._last_base_settings = base_settings
            self._noise_pattern = None # Invalidate final pattern

        # 2. Derive final noise pattern from base (applying animation if speed > 0)
        current_time = time.time() if animation_speed > 0 else 0
        current_settings = base_settings + (animation_speed, current_time)

        if self._noise_pattern is None or self._last_noise_settings != current_settings:
            if mix_mode == 'Image':
                # Image mode currently doesn't support scrolling animation here 
                # (handled by MediaManager if needed, but we just use the static frame)
                self._noise_pattern = self._base_small_noise
            else:
                if animation_speed > 0:
                    # Calculate fractional offset [0, grid_size)
                    offset = (current_time * animation_speed * 10.0) % grid_size
                    int_offset = int(offset)
                    
                    # Extract window of size (grid_size, grid_size) starting from int_offset
                    # Our base grid is (grid_size*2, grid_size*2)
                    if category == 2: # Horizontal Stripes
                        window = self._base_small_noise[int_offset : int_offset + grid_size, :]
                    elif category == 3: # Vertical Stripes
                        window = self._base_small_noise[:, int_offset : int_offset + grid_size]
                    else: # Grid noise
                        window = self._base_small_noise[int_offset : int_offset + grid_size, 
                                                       int_offset : int_offset + grid_size]
                    
                    small_noise = window
                else:
                    # Just take the first (grid_size, grid_size) block
                    if category == 2:
                        small_noise = self._base_small_noise[:grid_size, :]
                    elif category == 3:
                        small_noise = self._base_small_noise[:, :grid_size]
                    else:
                        small_noise = self._base_small_noise[:grid_size, :grid_size]

                # Resize to actual resolution
                interp = cv2.INTER_NEAREST if category == 0 else cv2.INTER_LINEAR
                self._noise_pattern = cv2.resize(small_noise, (self.res_y, self.res_x), interpolation=interp)
                
            self._last_noise_settings = current_settings
            
        return self._noise_pattern

    def _update_noise_preview(self):
        """Updates the noise preview image in the UI."""
        if not hasattr(self, 'noise_preview') or self.noise_preview is None:
            return
            
        noise = self._generate_noise()
        if noise is None:
            return

        # Convert noise [0, 1] to [0, 255] grayscale
        preview_noise = (noise * 255).astype(np.uint8)
        # Duplicate to 3 channels for preview (H, W, 3) 
        # Note: noise is (width, height), so we need to transpose back for image display
        preview_rgb = cv2.merge([preview_noise, preview_noise, preview_noise]).transpose(1, 0, 2)
        
        try:
            from led_wall.ui.media_manager import create_preview_frame
            
            # Calculate preview size based on physical dimensions
            dim_w, dim_h = self.dimensions
            preview_max_width = 800
            aspect_ratio = dim_w / dim_h
            preview_w = preview_max_width
            preview_h = int(preview_max_width / aspect_ratio)
            
            preview_bytes = create_preview_frame(preview_rgb, self.resolution, (preview_w, preview_h), self.dimensions)
            img_str = base64.b64encode(preview_bytes).decode()
            self.noise_preview.set_source(f'data:image/jpeg;base64,{img_str}')
        except Exception as e:
            logger.error(f"Error updating noise preview: {e}")

    def setup_settings(self) -> None:
        """
        Setup effect specific settings.
        """
        # Migration: if noise_pattern_type was 4 (Image), switch to mix_mode='Image'
        if self.settings_manager.get_setting('noise_pattern_type') == 4:
            self.settings_manager.update_setting('noise_pattern_type', 1) # Reset to a valid noise pattern
            self.settings_manager.update_setting('mix_mode', 'Image')

        self.settings_elements = [
            SettingsElement(
                label='Mix Mode',
                input=ui.select,
                default_value='Noise',
                manager=self.settings_manager,
                options=['Noise', 'Image', 'Video'],
                settings_id='mix_mode'
            ),
            SettingsElement(
                label='Noise Pattern',
                input=ui.select,
                default_value=1,
                manager=self.settings_manager,
                options={
                    0: 'White Noise',
                    1: 'Smooth Noise',
                    2: 'Horizontal Stripes',
                    3: 'Vertical Stripes'
                },
                settings_id='noise_pattern_type'
            )
        ]

    def ui_settings(self) -> None:
        """
        Custom settings UI with tabs for Noise and Image modes.
        """
        # Get current mode to set initial tab
        current_mode = self.settings_manager.get_setting('mix_mode') or 'Noise'
        
        with ui.tabs().classes('w-full').on('update:model-value', self.handle_tab_change) as tabs:
            noise_tab = ui.tab('Noise')
            image_tab = ui.tab('Image')
            video_tab = ui.tab('Video')
            # Ensure tabs value is set correctly on init based on current mode
            if current_mode == 'Noise':
                tabs.value = noise_tab
            elif current_mode == 'Image':
                tabs.value = image_tab
            # elif current_mode == 'Video':
            #     tabs.value = video_tab
        
        with ui.tab_panels(tabs, value=tabs.value).classes('w-full') as panels:
            with ui.tab_panel(noise_tab).classes('w-full'):
                # Only show Noise Pattern in this tab
                with ui.column().classes('w-full'):
                    for element in self.settings_elements:
                        if element.settings_id == 'noise_pattern_type':
                            element.on_change = lambda e: self._update_noise_preview()
                            element.create_ui()
                
                # Add noise parameters (animation_speed)
                ui.label('Noise Parameters').classes('text-sm font-semibold text-gray-400 mt-4 px-4')
                
                with ui.column().classes('w-full px-4 pb-4'):
                    def on_animation_change(e):
                        self.ui_change()
                        self._update_noise_preview()

                    # Add Noise Preview
                    ui.label('Noise Preview').classes('text-sm font-semibold text-gray-400 mt-4')
                    self.noise_preview = ui.image('').classes('w-full object-contain mb-2 q-pa-md')

                    with ui.row().classes('w-full q-gutter-sm'):
                        with ui.column():
                            # Add Blend and Noise Scale inputs
                            ui.label('Blend / Balance').classes('text-xs text-gray-500 mt-2')
                            self.inputs['blend'].ui_input()
                            self.inputs['blend'].on_ui_input = on_animation_change
                        
                        with ui.column():
                            ui.label('Noise Scale / Frequency').classes('text-xs text-gray-500 mt-2')
                            self.inputs['noise_scale'].ui_input()
                            self.inputs['noise_scale'].on_ui_input = on_animation_change

                        with ui.column():
                            # Add animation speed slider (0 is static)
                            ui.label('Animation Speed').classes('text-xs text-gray-500 mt-2')
                            self.inputs['animation_speed'].ui_input()
                            self.inputs['animation_speed'].on_ui_input = on_animation_change
                    
                    # Trigger initial preview update
                    self._update_noise_preview()
                    
                    # Add a timer to animate the preview if speed > 0
                    def animate_preview():
                        if self.inputs['animation_speed'].value > 0:
                            self._update_noise_preview()
                    
                    ui.timer(0.05, animate_preview)
                
            with ui.tab_panel(image_tab).classes('w-full p-0'):
                # Use our media_manager instance to show image selection and mapping
                self.media_manager.create_ui(add_preview=True, padding=False)

            # with ui.tab_panel(video_tab).classes('w-full p-0'):
            #     # Use our video_manager instance to show video selection and mapping
            #     self.video_manager.create_ui(add_preview=True, padding=False)

    def handle_tab_change(self, event):
        new_mode = event.args[0] if isinstance(event.args, list) else event.args
        logger.debug(f"ColorMix: Switching mix_mode to {new_mode}")
        self.settings_manager.update_setting('mix_mode', new_mode)
        
        # Sync the mix_mode SettingsElement if it exists
        for element in self.settings_elements:
            if element.settings_id == 'mix_mode':
                element.value = new_mode
        
        if new_mode == 'Noise':
            self._update_noise_preview()
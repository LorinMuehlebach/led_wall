import os
import numpy as np
import cv2
import logging
from nicegui import ui
from led_wall.effects.base_effect import BaseEffect
from led_wall.datatypes import RGBW_Color, Fader
from led_wall.ui.settings_manager import SettingsElement
from led_wall.ui.media_manager import MediaManager

logger = logging.getLogger("utils")

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

        self.res_x, self.res_y = self.resolution
        self._noise_pattern = None
        self._last_noise_settings = None

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
        noise_scale = self.inputs['noise_scale'].value
        
        # Get current mix mode and noise pattern
        mix_mode = self.settings_manager.get_setting('mix_mode') or 'Noise'
        category = self.settings_manager.get_setting('noise_pattern_type')
        if category is None:
            category = 1 # Default to Smooth Noise
            
        # Media Manager settings are handled internally by MediaManager
        current_settings = (mix_mode, category, noise_scale, 
                          self.settings_manager.get_setting(self.media_manager.media_path_setting_id),
                          self.settings_manager.get_setting(self.media_manager.fill_mode_setting_id),
                          self.settings_manager.get_setting(self.media_manager.offset_x_id),
                          self.settings_manager.get_setting(self.media_manager.offset_y_id),
                          self.settings_manager.get_setting(self.media_manager.scale_id),
                          self.settings_manager.get_setting(self.media_manager.rotation_id))
        
        # Only regenerate noise if the pattern type, scale, mode or image has changed
        if self._noise_pattern is None or self._last_noise_settings != current_settings:
            if mix_mode == 'Image':
                # Get frame from MediaManager (H, W, 3)
                frame = self.media_manager.get_frame()
                # Use only one channel (as it's grayscale) and transpose to (W, H)
                noise = frame[:, :, 0].T.astype(float) / 255.0
            else:
                # Use a deterministic seed based on settings to keep noise static but varied per setting
                rng = np.random.RandomState(seed=int(category) * 1000 + noise_scale)
                
                # Determine grid size for noise generation (min 2, max full resolution)
                min_grid = 2
                max_grid = max(self.res_x, self.res_y)
                # Scale determines how many blocks/features there are. 
                # 0 = very coarse/large blocks, 255 = very fine/small blocks
                grid_size = int(min_grid + (noise_scale / 255.0) * (max_grid - min_grid))
                grid_size = max(min_grid, grid_size)

                # Generate noise pattern [0, 1] based on type
                if category == 0: # White Noise / Random Blocks
                    if grid_size >= max_grid:
                        noise = rng.rand(self.res_x, self.res_y)
                    else:
                        small_noise = rng.rand(grid_size, grid_size)
                        # dsize is (width, height) = (res_y, res_x) to get (res_x, res_y) array
                        noise = cv2.resize(small_noise, (self.res_y, self.res_x), interpolation=cv2.INTER_NEAREST)
                
                elif category == 1: # Smooth Noise
                    small_noise = rng.rand(grid_size, grid_size)
                    noise = cv2.resize(small_noise, (self.res_y, self.res_x), interpolation=cv2.INTER_LINEAR)
                    
                elif category == 2: # Horizontal Stripes
                    # Random values for each "row" in the small grid
                    small_noise = rng.rand(grid_size, 1)
                    noise = cv2.resize(small_noise, (self.res_y, self.res_x), interpolation=cv2.INTER_LINEAR)

                else: # Vertical Stripes (category 3)
                    # Random values for each "column" in the small grid
                    small_noise = rng.rand(1, grid_size)
                    noise = cv2.resize(small_noise, (self.res_y, self.res_x), interpolation=cv2.INTER_LINEAR)
                    
            self._noise_pattern = noise
            self._last_noise_settings = current_settings
        
        # Use the cached static noise pattern
        noise = self._noise_pattern
        
        # Apply blend offset to noise values and clip to [0, 1]
        # t = 0 means color 1, t = 1 means color 2
        t = np.clip(noise + blend_offset, 0.0, 1.0)
        
        # Reshape for broadcasting (res_x, res_y, 1) to match color channels
        t_3d = t[:, :, np.newaxis]
        
        # Linear interpolation: result = c1 * (1-t) + c2 * t
        output_array = (c1 * (1.0 - t_3d) + c2 * t_3d).astype(np.uint8)
        
        return output_array

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
                options=['Noise', 'Image'],
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
        
        with ui.tabs().classes('w-full') as tabs:
            noise_tab = ui.tab('Noise')
            image_tab = ui.tab('Image')
        
        with ui.tab_panels(tabs, value=noise_tab if current_mode == 'Noise' else image_tab).classes('w-full') as panels:
            with ui.tab_panel(noise_tab):
                # Only show Noise Pattern in this tab
                for element in self.settings_elements:
                    if element.settings_id == 'noise_pattern_type':
                        element.create_ui()
                
            with ui.tab_panel(image_tab):
                # Use our media_manager instance to show image selection and mapping
                self.media_manager.create_ui(add_preview=True)

        # Update mix_mode when tab changes
        tabs.on_value_change(lambda e: self.settings_manager.update_setting('mix_mode', 'Noise' if e.value == noise_tab else 'Image'))
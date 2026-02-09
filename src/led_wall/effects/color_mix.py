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
        
        # Determine category (0-4) and scale for caching
        category = self.settings_manager.get_setting('noise_pattern_type')
        if category is None:
            category = 1 # Default to Smooth Noise
            
        mapping_mode = self.settings_manager.get_setting('noise_image_mapping') or 'Verhältniss'
        offset_x = self.settings_manager.get_setting('noise_image_offset_x') or 0.0
        offset_y = self.settings_manager.get_setting('noise_image_offset_y') or 0.0
        img_scale = self.settings_manager.get_setting('noise_image_scale') or 1.0

        image_file = self.settings_manager.get_setting('noise_image_file')
        current_settings = (category, noise_scale, image_file, mapping_mode, offset_x, offset_y, img_scale)
        
        # Only regenerate noise if the pattern type, scale, or image has changed
        if self._noise_pattern is None or self._last_noise_settings != current_settings:
            if category == 4: # Image
                if not image_file:
                    noise = np.zeros((self.res_x, self.res_y))
                else:
                    path = os.path.join('media', image_file)
                    try:
                        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                        if img is None:
                            logger.error(f"Could not load image {path}")
                            noise = np.zeros((self.res_x, self.res_y))
                        else:
                            # self.res_x is width, self.res_y is height
                            if mapping_mode == 'Verhältniss':
                                # resize to match LED wall resolution
                                # cv2.resize takes (width, height)
                                noise = cv2.resize(img, (self.res_x, self.res_y), interpolation=cv2.INTER_LINEAR)
                            else:
                                # Pixels mapping with scale and offset
                                target = np.zeros((self.res_x, self.res_y))
                                h, w = img.shape
                                new_h, new_w = int(h * img_scale), int(w * img_scale)
                                if new_h > 0 and new_w > 0:
                                    img_resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                                    
                                    # Calculate start position (centered + offset)
                                    # target axis 0 is width (x), axis 1 is height (y)
                                    start_x = int((self.res_x - new_w) / 2 + offset_x * self.res_x)
                                    start_y = int((self.res_y - new_h) / 2 + offset_y * self.res_y)
                                    
                                    # Crop source and target to fit
                                    t_start_x = max(0, start_x)
                                    t_end_x = min(self.res_x, start_x + new_w)
                                    t_start_y = max(0, start_y)
                                    t_end_y = min(self.res_y, start_y + new_h)
                                    
                                    s_start_x = max(0, -start_x)
                                    s_end_x = s_start_x + (t_end_x - t_start_x)
                                    s_start_y = max(0, -start_y)
                                    s_end_y = s_start_y + (t_end_y - t_start_y)
                                    
                                    if t_end_x > t_start_x and t_end_y > t_start_y:
                                        target[t_start_x:t_end_x, t_start_y:t_end_y] = img_resized[s_start_y:s_end_y, s_start_x:s_end_x]
                                noise = target

                            noise = noise.astype(float) / 255.0
                    except Exception as e:
                        logger.error(f"Error loading image {path}: {e}")
                        noise = np.zeros((self.res_x, self.res_y))
            else:
                # Use a deterministic seed based on settings to keep noise static but varied per setting
                rng = np.random.RandomState(seed=category * 1000 + noise_scale)
                
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
        def select_file(**kwargs):
            options = self._get_media_files()
            # Ensure the current value is in the options to avoid NiceGUI crash
            if kwargs.get('value') not in options:
                kwargs['value'] = None
            return ui.select(options=options, **kwargs)

        self.settings_elements = [
            SettingsElement(
                label='Noise Pattern',
                input=ui.select,
                default_value=1,
                manager=self.settings_manager,
                options={
                    0: 'White Noise',
                    1: 'Smooth Noise',
                    2: 'Horizontal Stripes',
                    3: 'Vertical Stripes',
                    4: 'Image'
                },
                settings_id='noise_pattern_type'
            ),
            SettingsElement(
                label='Image File',
                input=select_file,
                default_value=None,
                manager=self.settings_manager,
                settings_id='noise_image_file'
            ),
            SettingsElement(
                label='Mapping Mode',
                input=ui.select,
                default_value='Verhältniss',
                manager=self.settings_manager,
                options=['Verhältniss', 'Pixels'],
                settings_id='noise_image_mapping'
            ),
            SettingsElement(
                label='Offset X',
                input=ui.slider,
                default_value=0.0,
                manager=self.settings_manager,
                settings_id='noise_image_offset_x',
                min=-1.0, max=1.0, step=0.01
            ),
            SettingsElement(
                label='Offset Y',
                input=ui.slider,
                default_value=0.0,
                manager=self.settings_manager,
                settings_id='noise_image_offset_y',
                min=-1.0, max=1.0, step=0.01
            ),
            SettingsElement(
                label='Image Scale',
                input=ui.slider,
                default_value=1.0,
                manager=self.settings_manager,
                settings_id='noise_image_scale',
                min=0.1, max=10.0, step=0.1
            )
        ]

    def ui_settings(self) -> None:
        """
        Custom settings UI with upload and mapping dialog.
        """
        # Mapping setting IDs to be shown in the dialog
        mapping_ids = ['noise_image_mapping', 'noise_image_offset_x', 'noise_image_offset_y', 'noise_image_scale', 'noise_image_file']
        
        with ui.column().classes('w-full'):
            # Create UI for non-mapping settings
            for element in self.settings_elements:
                if element.settings_id not in mapping_ids:
                    element.create_ui()

        # Initialize and create the reusable dialog
        media_dialog = MediaManager(self.settings_manager, resolution=self.resolution, grayscale=True)
        media_dialog.create_ui()

            #ui.button('Adjust Image Mapping', on_click=dialog.open, icon='straighten').classes('w-full mt-2')
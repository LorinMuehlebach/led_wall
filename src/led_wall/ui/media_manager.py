import os
import io
import base64
import numpy as np
import logging
import math
import asyncio
from PIL import Image
import cv2
from nicegui import ui, run
from nicegui.events import ValueChangeEventArguments
from led_wall.ui.settings_manager import SettingsManager, SettingsElement

logger = logging.getLogger("utils")

class MediaManager:
    """
    A reusable dialog for uploading, selecting, and mapping images for effects.
    """
    TITLE = "Media Upload & Mapping"
    SELECT_BUTTON_LABEL = "Select Image"
    UPLOAD_BUTTON_LABEL = "Upload Image"
    GALLERY_TITLE = "Select Image"
    FILE_TYPE_LABEL = "image"
    ALLOWED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp')

    def __init__(self, settings_manager: SettingsManager, 
                 resolution: tuple[int, int] = (30, 60),
                 dimensions: tuple[float, float] = (6, 3),
                 grayscale: bool = False) -> None:
        
        self.settings_manager = settings_manager
        self.resolution = resolution
        self.dimensions = dimensions
        self.media_path_setting_id = "media_file"
        self.fill_mode_setting_id = "mode"
        self.offset_x_id = "offset_x"
        self.offset_y_id = "offset_y"
        self.scale_id = "scale"
        self.rotation_id = "rotation"
        self.grayscale = grayscale
        
        self.dialog = None
        self.preview = None
        self.select_dialog = None
        self.gallery_container = None
        self.current_image_label = None
        self.warning_label = None
        self._preview_timer = None
        self._current_image = None
        self._last_loaded_path = None

    def _get_media_files(self):
        if not os.path.exists('media'):
            os.makedirs('media')
        files = [f for f in os.listdir('media') if f.lower().endswith(self.ALLOWED_EXTENSIONS)]
        return sorted(files)

    def _handle_upload(self, e):
        if not os.path.exists('media'):
            os.makedirs('media')
        path = os.path.join('media', e.name)
        with open(path, 'wb') as f:
            f.write(e.content.read())
        ui.notify(f'Uploaded {e.name}')
        # Refresh the gallery if it exists
        if self.gallery_container:
            self._refresh_gallery()
    
    def _handle_delete(self, filename):
        """Delete an image file from the media folder."""
        path = os.path.join('media', filename)
        if os.path.exists(path):
            try:
                os.remove(path)
                ui.notify(f'Deleted {filename}')
                # If this was the selected image, clear the selection
                current = self.settings_manager.get_setting(self.media_path_setting_id)
                if current == filename:
                    self.settings_manager.update_setting(self.media_path_setting_id, None)
                    asyncio.create_task(self._load_and_update())
                # Refresh the gallery
                if self.gallery_container:
                    self._refresh_gallery()
            except Exception as e:
                ui.notify(f'Error deleting {filename}: {e}', type='negative')
    
    def _select_image(self, filename):
        """Select an image from the gallery."""
        self.settings_manager.update_setting(self.media_path_setting_id, filename)
        if self.current_image_label:
            self.current_image_label.text = f'Current: {filename}'
        asyncio.create_task(self._load_and_update())
        if self.select_dialog:
            self.select_dialog.close()
    
    def _refresh_gallery(self):
        """Refresh the image gallery view."""
        if not self.gallery_container:
            return
        self.gallery_container.clear()
        with self.gallery_container:
            files = self._get_media_files()
            current_img = self.settings_manager.get_setting(self.media_path_setting_id)
            
            if not files:
                ui.label(f'No {self.FILE_TYPE_LABEL}s found. Upload a {self.FILE_TYPE_LABEL} to get started.').classes('text-gray-500 italic')
            else:
                with ui.grid(columns=3).classes('w-full gap-2'):
                    for filename in files:
                        with ui.card().classes('p-2 cursor-pointer hover:bg-gray-100'):
                            is_selected = (filename == current_img)
                            img_path = f'/media/{filename}'
                            
                            with ui.column().classes('items-center gap-1'):
                                # Thumbnail image
                                ui.image(img_path).classes('w-24 h-24 object-contain').on('click', lambda f=filename: self._select_image(f))
                                
                                # Filename with selection indicator
                                label_text = f'✓ {filename[:15]}...' if len(filename) > 15 else f'✓ {filename}' if is_selected else filename[:15] + '...' if len(filename) > 15 else filename
                                ui.label(label_text).classes('text-xs text-center' + (' font-bold text-green-600' if is_selected else ''))
                                
                                # Delete button
                                ui.button(icon='delete', on_click=lambda f=filename: self._handle_delete(f)).props('flat dense size=sm color=red')
    
    def _open_select_dialog(self):
        """Open the selection dialog with gallery view."""
        with ui.dialog() as self.select_dialog, ui.card().classes('w-full max-w-2xl'):
            with ui.column().classes('w-full p-4'):
                ui.label(self.GALLERY_TITLE).classes('text-lg font-bold mb-2')
                
                # Upload button
                with ui.row().classes('w-full mb-4'):
                    upload = ui.upload(on_upload=self._handle_upload, auto_upload=True).classes('hidden')
                    ui.button(self.UPLOAD_BUTTON_LABEL, icon='cloud_upload', on_click=lambda: upload.run_method('pickFiles'))
                
                # Gallery container
                self.gallery_container = ui.column().classes('w-full max-h-96 overflow-auto')
                self._refresh_gallery()
                
                ui.button('Close', on_click=self.select_dialog.close).classes('mt-4 self-end')
        
        self.select_dialog.open()

    def _request_preview_update(self):
        """
        Throttles the preview update to prevent lag during slider movement.
        """
        if self._preview_timer:
            self._preview_timer.active = False
            try:
                self._preview_timer.delete()
            except (ValueError, AttributeError):
                pass
            self._preview_timer = None
        
        # 0.2s delay for responsive preview updates
        self._preview_timer = ui.timer(0.2, self._update_preview, once=True)

    async def _load_and_update(self):
        """
        Loads the image in a background thread and updates the preview.
        """
        if self.preview:
            self.preview.style('opacity: 0.5; transition: opacity 0.2s;')
        
        # Move heavy I/O and processing to a background thread
        await run.io_bound(self._load_image)
        
        if self.preview:
            self.preview.style('opacity: 1.0;')
        self._update_preview()

    def _load_image(self):
        """
        Loads the selected image into memory and scales it down for preview performance.
        """
        img_file = self.settings_manager.get_setting(self.media_path_setting_id)
        if not img_file:
            self._current_image = None
            self._last_loaded_path = None
            return

        path = os.path.join('media', img_file)
        if not os.path.exists(path):
            self._current_image = None
            self._last_loaded_path = None
            return

        try:
            with Image.open(path) as img:
                # Resize large images to save memory but ensure we have enough resolution for the wall
                limit = max(400, self.resolution[0], self.resolution[1])
                img.thumbnail((limit, limit))
                self._current_image = img.convert('RGB')
                self._last_loaded_path = img_file
        except Exception as e:
            logger.error(f"Error loading image into memory: {e}")
            self._current_image = None
            self._last_loaded_path = None

    def get_mapped_image(self) -> Image.Image:
        """
        Applies transformations to the in-memory image and returns proper sized image.
        """
        # Checks if we need to load image
        current_file = self.settings_manager.get_setting(self.media_path_setting_id)
        if current_file != self._last_loaded_path:
             self._load_image()

        res_w, res_h = self.resolution
        
        # Create black canvas
        mapped_img = Image.new('RGB', (res_w, res_h), (0, 0, 0))

        if self._current_image is None:
            return mapped_img

        try:
            mapping_mode = self.settings_manager.get_setting(self.fill_mode_setting_id) or 'Verhältniss'
            offset_x = self.settings_manager.get_setting(self.offset_x_id) or 0.0
            offset_y = self.settings_manager.get_setting(self.offset_y_id) or 0.0
            img_scale = self.settings_manager.get_setting(self.scale_id) or 1.0
            rotation = self.settings_manager.get_setting(self.rotation_id) or 0.0
            
            if mapping_mode == 'Verhältniss':
                # Verhältniss mode: apply rotation, scale, and offset
                rotated_img = self._current_image.rotate(-rotation, expand=True, fillcolor=(0, 0, 0))
                w, h = rotated_img.size
                new_w, new_h = int(res_w * img_scale), int(res_h * img_scale)
                if new_w > 0 and new_h > 0:
                    img_resized = rotated_img.resize((new_w, new_h), Image.LANCZOS)
                    
                    # Calculate start position (centered + offset)
                    pos_x = int((res_w - new_w) / 2 + offset_x * res_w)
                    pos_y = int((res_h - new_h) / 2 + offset_y * res_h)
                    
                    mapped_img.paste(img_resized, (pos_x, pos_y))
                
                # Clear warning for Verhältniss mode
                if self.warning_label:
                    self.warning_label.set_visibility(False)
            else:
                # Pixel mode: use image at exact resolution, ignore scaling/offsets
                img_w, img_h = self._current_image.size
                
                if img_w == res_w and img_h == res_h:
                    # Image matches resolution perfectly - use it directly
                    mapped_img = self._current_image.copy()
                    if self.warning_label:
                        self.warning_label.set_visibility(False)
                else:
                    # Media doesn't match resolution - show warning
                    if self.warning_label:
                        self.warning_label.text = f'⚠️ {self.FILE_TYPE_LABEL.capitalize()} resolution ({img_w}x{img_h}) does not match LED wall resolution ({res_w}x{res_h})'
                        self.warning_label.set_visibility(True)
                    # Still display what we have (centered)
                    pos_x = max(0, (res_w - img_w) // 2)
                    pos_y = max(0, (res_h - img_h) // 2)
                    crop_x = max(0, (img_w - res_w) // 2)
                    crop_y = max(0, (img_h - res_h) // 2)
                    
                    if img_w <= res_w and img_h <= res_h:
                        # Image is smaller - center it
                        mapped_img.paste(self._current_image, (pos_x, pos_y))
                    else:
                        # Image is larger - crop from center
                        cropped = self._current_image.crop((crop_x, crop_y, crop_x + res_w, crop_y + res_h))
                        mapped_img = cropped
            
            # Apply grayscale conversion if enabled
            if self.grayscale:
                mapped_img = mapped_img.convert('L').convert('RGB')
                
            return mapped_img

        except Exception as e:
            logger.error(f"Error mapping image: {e}")
            return mapped_img

    def get_frame(self) -> np.ndarray:
        img = self.get_mapped_image()
        return np.array(img)

    def _update_preview(self):
        """
        Applies transformations to the in-memory image and updates the preview.
        """

        self._preview_timer = None
        if not self.preview:
            return
        
        if self._current_image is None:
            self.preview.set_source('')
            return

        try:
            # self.resolution is (width, height) in pixels
            res_w, res_h = self.resolution
            # self.dimensions is (width, height) in meters
            dim_w, dim_h = self.dimensions
            
            # Calculate preview size based on physical dimensions to show correct aspect ratio
            # Use a maximum preview width of 800px and scale height proportionally
            preview_max_width = 800
            aspect_ratio = dim_w / dim_h
            preview_w = preview_max_width
            preview_h = int(preview_max_width / aspect_ratio)
            preview_resolution = (preview_w, preview_h)
            
            mapped_img = self.get_mapped_image()
            
            # Convert PIL image to numpy array for create_preview_frame
            frame = np.array(mapped_img)
            
            # Use create_preview_frame to generate upscaled preview with blur
            preview_bytes = create_preview_frame(frame, self.resolution, preview_resolution, self.dimensions)
            
            # Convert to base64 for NiceGUI
            img_str = base64.b64encode(preview_bytes).decode()
            self.preview.set_source(f'data:image/jpeg;base64,{img_str}')
                
        except Exception as e:
            logger.error(f"Error generating preview from memory: {e}")
            self.preview.set_source('')

    def create_dialog(self):
        with ui.dialog() as self.dialog, ui.card().classes('w-full max-w-lg'):
            self.create_ui()

        return self.dialog
    
    def create_ui(self, dialog=None, add_preview=True, padding=True):
        """
        Creates the UI elements for the media upload and mapping dialog.
        """
        padding_class = 'p-4' if padding else 'p-0'
        with ui.column().classes(f'w-full {padding_class}'):
            ui.label(self.TITLE).classes('text-lg font-bold')
            
            # Media selection controls
            current_val = self.settings_manager.get_setting(self.media_path_setting_id)
            current_display = current_val if current_val else f'No {self.FILE_TYPE_LABEL} selected'
                        
            ui.button(self.SELECT_BUTTON_LABEL, icon='photo_library', on_click=self._open_select_dialog).classes('w-full mb-4')
            
            self.current_image_label = ui.label(f'Current: {current_display}').classes('text-sm text-gray-600 mb-2')
            if add_preview:
                # Preview of the current media
                self.preview_ui()
            
            # Warning label for resolution mismatch
            self.warning_label = ui.label('').classes('text-orange-500 text-sm font-semibold')
            self.warning_label.set_visibility(False)

            ui.separator().classes('my-4')
            ui.label(f'{self.FILE_TYPE_LABEL.capitalize()} Mapping / Position').classes('text-sm font-semibold text-gray-400')
            
            def create_internal_number(label, setting_id, min_val, max_val, step):
                current = self.settings_manager.get_setting(setting_id)
                if current is None:
                    # Fallback to sensible defaults if settings are empty
                    current = 1.0 if 'scale' in setting_id else 0.0
                
                def handle_change(e):
                    self.settings_manager.update_setting(setting_id, e.value)
                    self._request_preview_update()

                ui.number(label=label, value=current, min=min_val, max=max_val, step=step,
                            format='%.2f', on_change=handle_change).classes('w-full')

            create_internal_number('Offset X', self.offset_x_id, -1.0, 1.0, 0.01)
            create_internal_number('Offset Y', self.offset_y_id, -1.0, 1.0, 0.01)
            create_internal_number('Scale', self.scale_id, 0.1, 10.0, 0.1)
            create_internal_number('Rotation', self.rotation_id, 0, 359, 1)
            
            with ui.row().classes('w-full items-center mb-4'):
                ui.label('Mode').classes('w-24')
                current_mode = self.settings_manager.get_setting(self.fill_mode_setting_id) or 'Verhältniss'
                ui.select(['Verhältniss', 'Pixels'], value=current_mode,
                            on_change=lambda e: [self.settings_manager.update_setting(self.fill_mode_setting_id, e.value), self._request_preview_update()]).classes('flex-grow')

            if dialog is not None:
                ui.button('Speichern', on_click=dialog.close).classes('mt-4 self-end')

            self._load_image()  # Load image into memory immediately to speed up first preview
            self._update_preview()  # Load initial preview if there's already a selected image

    def preview_ui(self):
        # Preview of the current image
        self.preview = ui.image('').classes('w-full object-contain mb-2 q-pa-md')


def create_preview_frame(frame: np.ndarray, resolution: tuple[int, int], preview_resolution: tuple[int, int], dimensions: tuple[float, float]) -> Image.Image:
    preblur_scaling = 4
    frame = np.flip(frame, axis=2) # cv2 expects BGR format so we flip the RGB channels

    scaled_frame = cv2.resize(frame, (resolution[0]*preblur_scaling, resolution[1]*preblur_scaling), interpolation=cv2.INTER_AREA)

    #blurr the output
    #kernel = np.ones((10,20),np.float32)/200
    #blurred_image = cv2.filter2D(scaled_frame,-1,kernel)
    #blurred_image = cv2.GaussianBlur(scaled_frame,(20,20),0)
    blurred_image = cv2.GaussianBlur(scaled_frame, (15, 15), sigmaX=2, sigmaY=2)
    final_frame = cv2.resize(blurred_image, (preview_resolution[0], preview_resolution[1]), interpolation=cv2.INTER_AREA)
    _, imencode_image = cv2.imencode('.jpg', final_frame) 
    return imencode_image.tobytes()


if __name__ in {"__main__", "__mp_main__"}:
    from nicegui import app
    
    # Mock settings manager for testing
    settings_manager = SettingsManager(path='test_settings.json')

    RESOLUTION = (30,58) #resolution of the LED wall in pixels
    DIMENSIONS = (6, 3) #dimension of the LED wall in meters
    
    preview_height = 200
    aspect_ratio = DIMENSIONS[0] / DIMENSIONS[1]
    preview_width = int(preview_height * aspect_ratio)
    PREVIEW_RESOLUTION = (preview_width, preview_height)

    # Serve media files for the preview
    if not os.path.exists('media'):
        os.makedirs('media')
    app.add_static_files('/media', 'media')

    @ui.page('/')
    def test_page():
        ui.label('Media Upload Dialog Test').classes('text-2xl mb-4')
        
        # Initialize the dialog with test resolution and dimensions
        media_dialog = MediaManager(settings_manager, resolution=RESOLUTION, dimensions=DIMENSIONS, grayscale=True)
        
        media_dialog.create_ui()  # Create the UI elements before creating the dialog to ensure they are initialized
        
        dialog = media_dialog.create_dialog()
        
        ui.button('Open Media Dialog', on_click=dialog.open)
        
        ui.label('Current Settings:').classes('mt-8 text-lg')
        settings_label = ui.label('')
        
        def update_settings_display():
            settings_label.text = str(settings_manager.settings)
        
        ui.timer(1.0, update_settings_display)

    ui.run(port=8083)

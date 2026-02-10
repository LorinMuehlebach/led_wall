import os
import logging
import asyncio
from threading import Thread
import time
import numpy as np
from PIL import Image
from nicegui import ui, run
from deffcode import FFdecoder, Sourcer
from led_wall.ui.media_manager import MediaManager, create_preview_frame
from led_wall.ui.settings_manager import SettingsManager
from led_wall.ui.preview_window import preview_setup

logger = logging.getLogger("utils")

class VideoManager(MediaManager):
    """
    A reusable dialog for uploading, selecting, and mapping videos for effects.
    Uses deffcode for video decoding and resizing.
    """
    TITLE = "Video Upload & Mapping"
    SELECT_BUTTON_LABEL = "Select Video"
    UPLOAD_BUTTON_LABEL = "Upload Video"
    GALLERY_TITLE = "Select Video"
    FILE_TYPE_LABEL = "video"
    ALLOWED_EXTENSIONS = ('.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.ts')

    def __init__(self, settings_manager: SettingsManager, 
                 resolution: tuple[int, int] = (30, 60),
                 dimensions: tuple[float, float] = (6, 3),
                 grayscale: bool = False,
                 fps: int = 10) -> None:
        
        super().__init__(settings_manager, resolution, dimensions, grayscale)
        self.media_path_setting_id = "video_file"
        self._decoder = None
        self._frame_generator = None
        self._video_start_time = 0
        self._frames_displayed = 0
        self._fps = fps # Framerate for the preview playback
        self._preview_timer = None
        self._unique_id = str(id(self)) # Unique ID for this instance

    def get_frame(self) -> np.ndarray:
        """
        Returns the current frame at LED resolution for the effect loop.
        Handles real-time sync and looping.
        """
        current_time = time.time()
        elapsed = current_time - self._video_start_time
        target_frame = int(elapsed * self._fps)

        if self._frame_generator is None:
            # No video loaded, return blank frame
            return np.zeros((self.resolution[1], self.resolution[0], 3), dtype=np.uint8)

        # Catch up: Pull frames until we reached the target frame
        frame = None
        while self._frames_displayed <= target_frame:
            frame = next(self._frame_generator)
            self._frames_displayed += 1
                    
        if frame is not None:
            self._last_frame = frame
            return frame

        return getattr(self, '_last_frame', np.zeros((self.resolution[1], self.resolution[0], 3), dtype=np.uint8))

    def _get_preview_frame(self) -> bytes:
        """
        Generates the next frame for the preview window.
        """
        # Calculate preview resolution
        dim_w, dim_h = self.dimensions
        preview_max_width = 400
        aspect_ratio = dim_w / dim_h
        preview_w = preview_max_width
        preview_h = int(preview_max_width / aspect_ratio)

        # Get raw mapped frame
        led_frame = self.get_frame()
        
        # Apply blurry upscaling for preview
        return create_preview_frame(led_frame, self.resolution, (preview_w, preview_h), self.dimensions)

    def _start_decoder(self, video_file, settings=None, start_time=0):
        """Starts the deffcode decoder with mapping transformations in FFmpeg filters."""
        if self._decoder is not None:
            try:
                self._decoder.terminate()
            except Exception:
                pass
        
        path = os.path.join('media', video_file)
        if not os.path.exists(path):
            self._frame_generator = None
            return

        try:
            if settings:
                _, mapping_mode, offset_x, offset_y, img_scale, rotation = settings
            else:
                mapping_mode = self.settings_manager.get_setting(self.fill_mode_setting_id) or 'Verhältniss'
                offset_x = self.settings_manager.get_setting(self.offset_x_id) or 0.0
                offset_y = self.settings_manager.get_setting(self.offset_y_id) or 0.0
                img_scale = self.settings_manager.get_setting(self.scale_id) or 1.0
                rotation = self.settings_manager.get_setting(self.rotation_id) or 0.0

            res_w, res_h = self.resolution
            
            # Build FFmpeg filter graph for transformations
            filters = [f"fps={self._fps}"]
            
            if mapping_mode == 'Verhältniss':
                # Rotate
                if rotation != 0:
                    rad = -rotation * np.pi / 180.0
                    filters.append(f"rotate={rad}:fillcolor=black:ow='rotw({rad})':oh='roth({rad})'")
                
                # Scale
                new_w, new_h = max(1, int(res_w * img_scale)), max(1, int(res_h * img_scale))
                filters.append(f"scale={new_w}:{new_h}")
                
                # Pad (Position)
                px = f"(ow-iw)/2+{offset_x}*ow"
                py = f"(oh-ih)/2+{offset_y}*oh"
                filters.append(f"pad={res_w}:{res_h}:{px}:{py}:color=black")
            else:
                # Pixel mode: Center and pad/crop
                filters.append(f"pad=max(iw\\,{res_w}):max(ih\\,{res_h}):(ow-iw)/2:(oh-ih)/2:color=black")
                filters.append(f"crop={res_w}:{res_h}:(iw-ow)/2:(ih-oh)/2")

            if self.grayscale:
                filters.append("format=gray,format=rgb24")

            ffparams = {
                "-custom_resolution": (res_w, res_h),
                "-vf": ",".join(filters),
                "-ss": str(start_time)
            }
            
            self._decoder = FFdecoder(path, frame_format="rgb24", verbose=False, **ffparams).formulate()
            self._frame_generator = self._decoder.generateFrame()
            self._video_start_time = time.time() - start_time
            self._frames_displayed = int(start_time * self._fps)
            
        except Exception as e:
            logger.error(f"Error starting video decoder: {e}")
            self._frame_generator = None

    def preview_ui(self):
        """Use interactive image for preview with automated updates from preview_window.py."""
        self.preview = ui.interactive_image().classes('w-full object-contain mb-2 q-pa-md')
        # Setup preview with unique URL but keep reference to timer so we can control it
        self._preview_timer = preview_setup(
            self.preview, 
            get_preview_frame=self._get_preview_frame, 
            interval=1.0/self._fps,
            url_path=f'/video/frame/{self._unique_id}'
        )
        # Immediately deactivate timer, it should only run when requested
        self._preview_timer.active = False

    def start_preview(self):
        """Enable preview generation."""
        if self._preview_timer:
            self._preview_timer.active = True

    def stop_preview(self):
        """Disable preview generation to save resources."""
        if self._preview_timer:
            self._preview_timer.active = False
            # Also stop decoder if we are not the active effect? 
            # We don't know if we are active here easily.
            # But stopping decoder is safe; if main loop needs it, it will restart it in get_frame.
            # However, restarting decoder might reset playback position.
            # So better NOT stop decoder here if it might be running for main loop.
            # Ideally we only stop decoder if we know it's not needed.
            # For now, let's assume stopping preview just stops the intense polling.
            pass

    def _update_preview(self):
        """No manual update needed as preview_window uses a timer."""
        self._preview_timer = None
        pass

    def _load_image(self):
        """
        Resets the decoder when the selected video changes.
        """
        self._frame_generator = None
        if self._decoder:
            try:
                self._decoder.terminate()
            except Exception:
                pass
            self._decoder = None
        if hasattr(self, '_last_frame'):
            del self._last_frame

    def stop(self):
        """Clean up resources."""
        if self._decoder:
            try:
                self._decoder.terminate()
            except Exception:
                pass
            self._decoder = None
        print("VideoManager stopped and decoder terminated.")
        self._frame_generator = None
        if hasattr(self, '_last_frame'):
            del self._last_frame

    def _refresh_gallery(self):
        """Custom gallery view for videos using movie icons instead of image previews."""
        if not self.gallery_container:
            return
        self.gallery_container.clear()
        with self.gallery_container:
            files = self._get_media_files()
            current_vid = self.settings_manager.get_setting(self.media_path_setting_id)
            
            if not files:
                ui.label(f'No {self.FILE_TYPE_LABEL}s found. Upload a {self.FILE_TYPE_LABEL} to get started.').classes('text-gray-500 italic')
            else:
                with ui.grid(columns=3).classes('w-full gap-2'):
                    for filename in files:
                        with ui.card().classes('p-2 cursor-pointer hover:bg-gray-100'):
                            is_selected = (filename == current_vid)
                            
                            with ui.column().classes('items-center gap-1'):
                                # Cinema icon for videos
                                ui.icon('movie', size='50px').classes('text-gray-400' + (' text-blue-500' if is_selected else '')).on('click', lambda f=filename: self._select_image(f))
                                
                                label_text = f'✓ {filename[:15]}...' if len(filename) > 15 else f'✓ {filename}' if is_selected else filename[:15] + '...' if len(filename) > 15 else filename
                                ui.label(label_text).classes('text-xs text-center' + (' font-bold text-green-600' if is_selected else ''))
                                
                                # Delete button
                                ui.button(icon='delete', on_click=lambda f=filename: self._handle_delete(f)).props('flat dense size=sm color=red')

    def preload(self):
        """
        Initializes/Resets the decoder to the beginning so it is ready to play.
        Executes in a separate thread to avoid blocking.
        """
        print("Preloading video...")
        video_file = self.settings_manager.get_setting(self.media_path_setting_id)
        if not video_file:
            return

        # Get settings to check for changes
        mapping_mode = self.settings_manager.get_setting(self.fill_mode_setting_id) or 'Verhältniss'
        offset_x = self.settings_manager.get_setting(self.offset_x_id) or 0.0
        offset_y = self.settings_manager.get_setting(self.offset_y_id) or 0.0
        img_scale = self.settings_manager.get_setting(self.scale_id) or 1.0
        rotation = self.settings_manager.get_setting(self.rotation_id) or 0.0
        current_settings = (video_file, mapping_mode, offset_x, offset_y, img_scale, rotation)

        def _run_preload():
            self._start_decoder(video_file, current_settings, start_time=0)
            self._last_mapping_settings = current_settings
            print("Video preloaded inside thread.")

        Thread(target=_run_preload).start()

    def reset_clock(self):
        """
        Resets the timing storage so playback matches current time as start time.
        Useful when resuming preloaded video.
        """
        self._video_start_time = time.time()
        self._frames_displayed = 0

if __name__ in {"__main__", "__mp_main__"}:
    from nicegui import app
    
    # Mock settings manager for testing
    settings_manager = SettingsManager(path='test_settings_video.json')

    RESOLUTION = (30,58) #resolution of the LED wall in pixels (width, height)
    DIMENSIONS = (6, 3) #dimension of the LED wall in meters (width, height)
    
    # Serve media files
    if not os.path.exists('media'):
        os.makedirs('media')
    app.add_static_files('/media', 'media')

    @ui.page('/')
    def test_page():
        ui.label('Video Manager Test').classes('text-2xl mb-4')
        
        video_manager = VideoManager(settings_manager, resolution=RESOLUTION, dimensions=DIMENSIONS)
        video_manager.create_ui()
        
        dialog = video_manager.create_dialog()
        ui.button('Open Video Dialog', on_click=dialog.open)

    ui.run(port=8084)

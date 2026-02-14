#!/usr/bin/env python3
import base64
import time
from typing import Callable

import cv2
import numpy as np
from fastapi import Response

from nicegui import Client, app, core, run, ui

USE_THREAD_FOR_PREVIEW = False

# Flag to prevent processing during shutdown
_is_shutting_down = False

@app.on_shutdown
def _handle_preview_shutdown():
    global _is_shutting_down
    _is_shutting_down = True

# In case you don't have a webcam, this will provide a black placeholder image.
black_1px = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAAXNSR0IArs4c6QAAAA1JREFUGFdjYGBg+A8AAQQBAHAgZQsAAAAASUVORK5CYII='
placeholder = Response(content=base64.b64decode(black_1px.encode('ascii')), media_type='image/png')

def convert(frame: np.ndarray) -> bytes:
    """Converts a frame from OpenCV to a JPEG image.

    This is a free function (not in a class or inner-function),
    to allow run.cpu_bound to pickle it and send it to a separate process.
    """
    _, imencode_image = cv2.imencode('.jpg', frame)
    return imencode_image.tobytes()


def create_preview_frame(output_buffer: np.ndarray, resolution: tuple[int, int], pixel_channels: int, preview_width: int, preview_height: int) -> np.ndarray:
    """
    returns the preview frame for the led wall.
    """
    from led_wall.utils import Color
    
    frame = np.zeros((resolution[0], resolution[1], 3), dtype=np.uint8)
    if pixel_channels == 4:
        # Vectorized RGBW to RGB conversion
        white_contrib = (output_buffer[:, :, 3:4].astype(np.uint16) * np.array(Color.WHITE)) // 255
        frame = np.minimum(output_buffer[:, :, :3].astype(np.uint16) + white_contrib, 255).astype(np.uint8)
    else:
        frame = output_buffer

    frame = np.transpose(frame, (1, 0, 2))  # flip x and y axis
    frame = np.flip(frame, axis=2)  # cv2 expects BGR format so we flip the RGB channels
    preblur_scaling = 4
    scaled_frame = cv2.resize(frame, (resolution[0] * preblur_scaling, resolution[1] * preblur_scaling), interpolation=cv2.INTER_AREA)

    # blur the output
    blurred_image = cv2.GaussianBlur(scaled_frame, (15, 15), sigmaX=2, sigmaY=2)
    final_frame = cv2.resize(blurred_image, (preview_width, preview_height), interpolation=cv2.INTER_AREA)
    return final_frame


def create_preview_image(output_buffer,resolution,pixel_channels, gamma_correction:callable = None, preview_height = 200) -> bytes:
    preview_width = int((resolution[1] / resolution[0]) * preview_height)
    if gamma_correction is not None:
        output_buffer = OutputCorrection.apply(output_buffer, gamma_correction)
    frame = create_preview_frame(output_buffer, resolution, pixel_channels, preview_width, preview_height)
    jpeg_bytes = convert(frame)
    return jpeg_bytes

def preview_setup(video_image:ui.interactive_image,webcam:bool = False,get_preview_frame:Callable[[], np.ndarray]=None, io_manager=None, interval: float = 0.1, url_path: str = '/video/frame') -> ui.timer:
    # OpenCV is used to access the webcam.
    if webcam:
        video_capture = cv2.VideoCapture(0)
    else:
        # Use a dummy video capture for testing without a webcam.
        # This will provide a black placeholder image.
        video_capture = None


    @app.get(url_path)
    # Thanks to FastAPI's `app.get` it is easy to create a web route which always provides the latest image from OpenCV.
    async def grab_video_frame() -> Response:
        if _is_shutting_down:
            return placeholder

        if get_preview_frame is None:
            if io_manager is not None:
                args = (io_manager.output_buffer, io_manager.resolution, io_manager.pixel_channels, io_manager.gamma_correction)
                jpeg = await run.cpu_bound(create_preview_image, *args)
                return Response(content=jpeg, media_type='image/jpeg')
            
            if not webcam:
                return placeholder
        
            if not video_capture.isOpened():
                return placeholder
            # The `video_capture.read` call is a blocking function.
            # So we run it in a separate thread (default executor) to avoid blocking the event loop.
            _, frame = await run.io_bound(video_capture.read)
            if frame is None:
                return placeholder
            # `convert` is a CPU-intensive function, so we run it in a separate process to avoid blocking the event loop and GIL.
        else:
            frame = get_preview_frame()
        
        if isinstance(frame, bytes):
            return Response(content=frame, media_type='image/jpeg')
            
        try:
            if USE_THREAD_FOR_PREVIEW:
                jpeg = await run.cpu_bound(convert, frame)
            else:
                jpeg = convert(frame)
        except Exception:
            return placeholder
        return Response(content=jpeg, media_type='image/jpeg')

    # For non-flickering image updates and automatic bandwidth adaptation an interactive image is much better than `ui.image()`.
    #video_image = ui.interactive_image().classes('w-full h-full')
    # A timer constantly updates the source of the image.
    # Because data from same paths is cached by the browser,
    # we must force an update by adding the current timestamp to the source.
    timer = ui.timer(interval=interval, callback=lambda: video_image.set_source(f'{url_path}?{time.time()}'))
    
    async def disconnect() -> None:
        """Disconnect all clients from current running server."""
        for client_id in Client.instances:
            await core.sio.disconnect(client_id)

    async def cleanup() -> None:
        # This prevents ugly stack traces when auto-reloading on code change,
        # because otherwise disconnected clients try to reconnect to the newly started server.
        await disconnect()
        # Release the webcam hardware so it can be used by other applications again.
        if video_capture is not None:
            # Only release if we actually opened a webcam.
            video_capture.release()

    app.on_shutdown(cleanup)
    
    return timer

# All the setup is only done when the server starts. This avoids the webcam being accessed
# by the auto-reload main process (see https://github.com/zauberzeug/nicegui/discussions/2321).
#app.on_startup(preview_setup)


class OutputCorrection:
    @staticmethod
    def apply(output_buffer: np.ndarray, method: str, max_val: int = 0xFF) -> np.ndarray:
        if method == 'linear':
            return output_buffer
        elif method == 'quadratic':
            return ((output_buffer ** 2) / max_val).astype(np.uint8)
        elif method == 'cubic':
            return ((output_buffer ** 3) / (max_val ** 2)).astype(np.uint8)
        elif method == 'quadruple':
            return ((output_buffer ** 4) / (max_val ** 3)).astype(np.uint8)
        elif method == '2.2 gamma':
            gamma = 2.2
            return (max_val * ((output_buffer / max_val) ** gamma)).astype(np.uint8)
        else:
            raise ValueError(f"Unknown correction method: {method}")

    @staticmethod
    def available_methods():
        return {"linear": "Linear (no correction)", 
                "quadratic": "Quadratic", 
                "cubic": "Cubic", 
                "quadruple": "Quadruple",
                "2.2 gamma": "Gamma 2.2 (approximation of sRGB)"}
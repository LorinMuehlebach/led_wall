# LED Wall Control Software - Copilot Instructions

## Project Overview
This project is a high-performance LED Wall Control Software designed to convert ArtNet/DMX signals into control signals for a large-scale LED Matrix. It supports real-time effects, video playback, and a web-based UI for configuration and preview.

## Core Technologies
- **Language**: Python 3.10+ (managed with `uv`)
- **UI Framework**: [NiceGUI](https://nicegui.io/) (FastAPI-based)
- **Networking**: `stupidArtnet` / `pyartnet` for ArtNet I/O.
- **Image/Video Processing**: `NumPy` (core data handling), `OpenCV`, `Pillow`.
- **Frontend Extensions**: Vue.js and React components integrated into NiceGUI.

## Project Structure
- `entry_points/`: Main execution scripts. `main.py` is the primary entry point.
- `src/led_wall/`: Core library code.
    - `effects/`: Contains the effect system and all individual effect implementations.
    - `ui/`: NiceGUI-based UI components and managers.
    - `io_manager.py`: Handles the I/O loop, ArtNet server/client, and frame timing.
    - `pixels.py`: Datatypes for pixel and array management.
    - `settings_manager.py`: Hierarchical settings system with JSON persistence.
- `media/`: Storage for images and videos used by effects.

## Architecture & Coding Patterns

### 1. Effect Development
All effects must inherit from `BaseEffect` in `src/led_wall/effects/base_effect.py`.
- **Required Method**: `run_raw(self, DMX_channels, last_output)`
    - Returns a `np.array` of shape `(width, height, 4)` (RGBW).
    - `DMX_channels` is the raw list of DMX values for this effect's mapped channels.
- **Input Management**: Define inputs in `self.inputs` using `Fader`, `RGBW_Color`, etc. These are automatically mapped to DMX channels.
- **Settings**: Use `setup_settings()` to define UI-configurable parameters using `SettingsElement`.

### 2. I/O Loop
The `IO_Manager` manages the main loop:
1. Receives DMX data via ArtNet.
2. Calls the `EffectManager` to get the next frame.
3. Sends the frame out via ArtNet to the LED hardware.
4. Manages global resolution, framerate, and physical dimensions.

### 3. Settings System
- Settings are managed by `SettingsManager`.
- They are hierarchical (nested managers).
- Values are automatically saved to `settings.json` (or other specified files).
- UI components should use `SettingsElement` to bind UI widgets (like `ui.number` or `ui.switch`) directly to setting values.

### 4. Data Format
- Internal pixel data is almost always `uint8` NumPy arrays.
- Standard shape: `(width, height, 4)` where index 3 is the White channel in RGBW.
- Addressing can be horizontal or vertical, often requiring row/column reversals depending on hardware wiring (handled in `io_manager.py`).

## Coding Standards
- **Type Hinting**: Use type hints for all function signatures and complex variables.
- **Logging**: Use the standard `logging` module. Prefer `logger = getLogger(__name__)`.
- **Async**: Use `asyncio` for non-blocking operations, especially in UI and network logic.
- **Numpy**: Vectorize operations whenever possible for performance. Avoid manual loops over pixels in `run_raw`.

## Common Tasks for Copilot
- **Creating new effects**: Implementation should follow the `BaseEffect` pattern and reside in `src/led_wall/effects/`.
- **Modifying UI**: Use NiceGUI elements. Ensure any new setting is registered with the `SettingsManager`.
- **I/O Tweaks**: Handle ArtNet universe mapping and pixel reordering in `io_manager.py` or `MultiUniverseArtnet.py`.

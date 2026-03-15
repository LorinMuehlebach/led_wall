import numpy as np
import time
import random
from dataclasses import dataclass
from led_wall.effects.base_effect import BaseEffect
from led_wall.ui.show_inputs import Fader, RGBW_Color


@dataclass
class Spot:
    """Individual spot with independent timing."""
    x: int
    y: int
    last_cycle_time: float
    is_on: bool
    on_duration: float
    off_duration: float


class StroboEffect(BaseEffect):
    """
    Strobe effect with configurable speed, on-time, randomness, and spot size.
    """

    NAME = 'Strobo'
    DESCRIPTION = 'Strobe effect with adjustable speed, on-time percentage, randomness, and size (full screen to random spots).'

    def __init__(self, resolution: tuple[int, int], dimensions: tuple[int, int], rgbw: bool, settings_manager=None) -> None:
        super().__init__(resolution, dimensions, rgbw, settings_manager)
        
        # Add custom inputs after existing ones (master, rgbw_color, mode)
        self.inputs['color2'] = RGBW_Color([0, 0, 0, 0])  # Second color (shown when strobe is off)
        self.inputs['speed'] = Fader(128)      # Flash speed (0=slow, 255=fast)
        self.inputs['ontime'] = Fader(128)     # On-time percentage (0=0%, 255=100%)
        self.inputs['randomness'] = Fader(0)   # Timing randomness (0=none, 255=max)
        self.inputs['size'] = Fader(0)         # Spot size (0=full screen, 255=tiny spots)
        
        self.res_x, self.res_y = self.resolution
        
        # Global timing state (for full screen mode)
        self.last_cycle_time = time.time()
        self.is_on = False
        self.current_on_duration = 0.0
        self.current_off_duration = 0.0
        self._calculate_durations()
        
        # Spot state for independent random spots
        self.spots: list[Spot] = []
        self.num_spots = 0
        self.current_spot_diameter = 0

    def _calculate_durations(self, speed_val: int = 128, ontime_val: int = 128, randomness_val: int = 0) -> tuple[float, float]:
        """
        Calculate on and off durations based on speed and on-time percentage.
        Speed 0 = ~2 Hz (500ms cycle), Speed 255 = ~25 Hz (40ms cycle)
        Returns (on_duration, off_duration)
        """
        # Map speed 0-255 to cycle time 500ms - 40ms
        min_cycle = 0.04   # 40ms = 25 Hz (fastest)
        max_cycle = 0.5    # 500ms = 2 Hz (slowest)
        
        cycle_time = max_cycle - (speed_val / 255.0) * (max_cycle - min_cycle)
        
        # On-time percentage (0-255 maps to 5%-95%)
        ontime_pct = 0.05 + (ontime_val / 255.0) * 0.90
        
        # Apply randomness to cycle time
        if randomness_val > 0:
            randomness_factor = (randomness_val / 255.0) * 0.5  # Up to 50% variation
            random_offset = (random.random() - 0.5) * 2 * randomness_factor
            cycle_time *= (1 + random_offset)
        
        on_duration = cycle_time * ontime_pct
        off_duration = cycle_time * (1 - ontime_pct)
        
        self.current_on_duration = on_duration
        self.current_off_duration = off_duration
        
        return on_duration, off_duration

    def _init_spots(self, size_val: int, speed_val: int, ontime_val: int, randomness_val: int) -> None:
        """
        Initialize spots with independent timing.
        """
        # Calculate spot parameters based on size value
        # Higher size_val = more spots but smaller, packed closer together
        # Spot diameter as fraction of screen: 1.0 (full) -> 0.05 (tiny)
        spot_diameter_frac = 1.0 - (size_val / 255.0) * 0.95
        spot_diameter = max(1, int(min(self.res_x, self.res_y) * spot_diameter_frac))
        
        # Number of spots increases as size decreases - pack them more densely
        # Use smaller spacing factor for closer packing
        spacing = max(1, spot_diameter // 2)  # Spots can overlap
        max_spots = max(1, (self.res_x * self.res_y) // (spacing * spacing))
        num_spots = min(max_spots, 1 + int((size_val / 255.0) * 40))
        
        self.current_spot_diameter = spot_diameter
        
        # Only regenerate spots if count changed
        if self.num_spots != num_spots:
            self.num_spots = num_spots
            current_time = time.time()
            self.spots = []
            
            for _ in range(num_spots):
                on_dur, off_dur = self._calculate_durations(speed_val, ontime_val, randomness_val)
                # Randomize initial phase so spots don't all start synchronized
                random_phase = random.random() * (on_dur + off_dur)
                
                spot = Spot(
                    x=random.randint(0, self.res_x - 1),
                    y=random.randint(0, self.res_y - 1),
                    last_cycle_time=current_time - random_phase,
                    is_on=random.choice([True, False]),
                    on_duration=on_dur,
                    off_duration=off_dur,
                )
                self.spots.append(spot)

    def _update_spot_timing(self, spot: Spot, speed_val: int, ontime_val: int, randomness_val: int) -> None:
        """
        Update timing for a single spot.
        """
        current_time = time.time()
        elapsed = current_time - spot.last_cycle_time
        
        if spot.is_on:
            if elapsed >= spot.on_duration:
                spot.is_on = False
                spot.last_cycle_time = current_time
                spot.on_duration, spot.off_duration = self._calculate_durations(speed_val, ontime_val, randomness_val)
                # Move spot to new random position
                spot.x = random.randint(0, self.res_x - 1)
                spot.y = random.randint(0, self.res_y - 1)
        else:
            if elapsed >= spot.off_duration:
                spot.is_on = True
                spot.last_cycle_time = current_time
                spot.on_duration, spot.off_duration = self._calculate_durations(speed_val, ontime_val, randomness_val)

    def _render_spots(self, color: np.ndarray, color2: np.ndarray) -> np.ndarray:
        """
        Render all active spots to the output array.
        Uses color2 as background, color for active spots.
        No color mixing - each pixel is either color or color2.
        """
        output_array = np.full((self.res_x, self.res_y, 4), color2, dtype=np.uint8)
        half_d = self.current_spot_diameter // 2
        color_uint8 = color.astype(np.uint8)
        
        for spot in self.spots:
            if not spot.is_on:
                continue
            
            x_start = max(0, spot.x - half_d)
            x_end = min(self.res_x, spot.x + half_d + 1)
            y_start = max(0, spot.y - half_d)
            y_end = min(self.res_y, spot.y + half_d + 1)
            
            # Create circular spot using vectorized operations
            xs = np.arange(x_start, x_end)
            ys = np.arange(y_start, y_end)
            xx, yy = np.meshgrid(xs, ys, indexing='ij')
            dist = np.sqrt((xx - spot.x) ** 2 + (yy - spot.y) ** 2)
            mask = dist <= half_d
            
            # Apply color where mask is True (direct assignment, no mixing)
            for i, x in enumerate(range(x_start, x_end)):
                for j, y in enumerate(range(y_start, y_end)):
                    if mask[i, j]:
                        output_array[x, y] = color_uint8
        
        return output_array

    def run_raw(self, DMX_channels, last_output: np.array) -> np.array:
        """
        Calculate the strobe effect frame.
        """
        self.update_inputs(DMX_channels)
        
        # Get input values
        master = self.inputs['master'].value / 255.0
        color = np.array(self.inputs['rgbw_color'].get_channels(), dtype=np.float32) * master
        color2 = np.array(self.inputs['color2'].get_channels(), dtype=np.float32) * master
        speed_val = self.inputs['speed'].value
        ontime_val = self.inputs['ontime'].value
        randomness_val = self.inputs['randomness'].value
        size_val = self.inputs['size'].value
        
        # Full screen mode (size = 0)
        if size_val == 0:
            # Handle global timing
            current_time = time.time()
            elapsed = current_time - self.last_cycle_time
            
            if self.is_on:
                if elapsed >= self.current_on_duration:
                    self.is_on = False
                    self.last_cycle_time = current_time
                    self._calculate_durations(speed_val, ontime_val, randomness_val)
            else:
                if elapsed >= self.current_off_duration:
                    self.is_on = True
                    self.last_cycle_time = current_time
                    self._calculate_durations(speed_val, ontime_val, randomness_val)
            
            # Create output array
            if self.is_on:
                return np.full((self.res_x, self.res_y, 4), color, dtype=np.uint8)
            else:
                return np.full((self.res_x, self.res_y, 4), color2, dtype=np.uint8)
        
        # Spot mode (size > 0)
        self._init_spots(size_val, speed_val, ontime_val, randomness_val)
        
        # Update timing for each spot independently
        for spot in self.spots:
            self._update_spot_timing(spot, speed_val, ontime_val, randomness_val)
        
        # Render spots
        return self._render_spots(color, color2)

    def start(self):
        """
        Called on a switch to this effect.
        """
        super().start()
        self.last_cycle_time = time.time()
        self.is_on = False
        self.spots = []
        self.num_spots = 0

    def stop(self):
        """
        Called on a switch away from this effect.
        """
        super().stop()

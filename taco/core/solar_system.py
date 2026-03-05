import re
from enum import IntEnum

import numpy as np

from taco.core.easing import quint_ease_in, quint_ease_out
from taco.core.solar_system_data import SolarSystemConnection


class AnimationState(IntEnum):
    GROWING = 0
    PAUSED = 1
    SHRINKING = 2
    IDLE = 3


# Default colours as (R, G, B, A) tuples in 0-255
DEFAULT_DRAW_COLOR = (172, 207, 243, 255)
HIGHLIGHT_DRAW_COLOR = (255, 255, 255, 255)
ALERTING_DRAW_COLOR = (255, 0, 0, 255)
CHARACTER_LOCATION_DRAW_COLOR = (0, 200, 0, 255)
CHARACTER_ALERT_DRAW_COLOR = (255, 140, 0, 255)


def color_to_rgba32(c: tuple[int, int, int, int]) -> int:
    """Convert (R, G, B, A) to packed ABGR int32 (matches C# Utility.ColorToRgba32)."""
    r, g, b, a = c
    return (a << 24) | (b << 16) | (g << 8) | r


class SolarSystem:
    __slots__ = (
        "native_id", "name", "x", "y", "z",
        "x2d", "y2d", "x3d", "y3d", "z3d",
        "region_id", "connected_to", "xyz",
        "draw_color", "draw_size", "is_3d",
        "is_highlighted", "is_alerting", "is_selected",
        "alert_state", "highlight_state",
        "_step_alert", "_step_highlight", "_alert_pulse_count",
        "_is_flash", "_name_regex",
    )

    def __init__(self, native_id: int, name: str, x: float, y: float, z: float,
                 x2d: float = 0.0, y2d: float = 0.0, region_id: int = 0):
        self.native_id = native_id
        self.name = name
        self.x = x
        self.y = y
        self.z = z

        # Store original 3D coords for mode switching
        self.x3d = x
        self.y3d = y
        self.z3d = z

        # Store 2D schematic coords
        self.x2d = x2d
        self.y2d = y2d

        # Region
        self.region_id = region_id

        self.connected_to: list[SolarSystemConnection] = []

        xf = float(x)
        yf = float(y)
        zf = float(z)
        self.xyz = np.array([xf, yf, zf], dtype=np.float32)

        self.is_highlighted = False
        self.is_alerting = False
        self.is_selected = False

        self.alert_state = AnimationState.IDLE
        self.highlight_state = AnimationState.IDLE
        self.draw_size = 0.0
        self.draw_color = DEFAULT_DRAW_COLOR

        self._step_alert = 1
        self._step_highlight = 0
        self._alert_pulse_count = 0
        self._is_flash = False

        # Build case-insensitive word-boundary regex for system name
        self._name_regex = re.compile(
            r'\b' + re.escape(name) + r'\b', re.IGNORECASE
        )

    @property
    def xf(self) -> float:
        return float(self.x)

    @property
    def yf(self) -> float:
        return float(self.y)

    @property
    def zf(self) -> float:
        return float(self.z)

    def set_map_mode(self, mode: str):
        """Switch between '3d' projection and '2d' schematic coordinates."""
        if mode == "2d":
            self.x = self.x2d
            self.y = self.y2d
            self.z = 0.0
        else:
            self.x = self.x3d
            self.y = self.y3d
            self.z = self.z3d
        self.xyz = np.array([float(self.x), float(self.y), float(self.z)], dtype=np.float32)

    @property
    def name_regex(self) -> re.Pattern:
        return self._name_regex

    @property
    def is_highlighted_and_alerting(self) -> bool:
        return self.is_highlighted and self.is_alerting

    @property
    def draw_color_rgba_floats(self) -> tuple[float, float, float, float]:
        """Return draw colour as (R, G, B, A) in 0.0-1.0 range."""
        r, g, b, a = self.draw_color
        return (r / 255.0, g / 255.0, b / 255.0, a / 255.0)

    @property
    def draw_color_argb32(self) -> int:
        return color_to_rgba32(self.draw_color)

    def match_name_regex(self, log_line: str) -> bool:
        return bool(self._name_regex.search(log_line))

    # --- Animation tick processing ---

    def process_tick(self) -> bool:
        htr = self._process_highlight_tick()
        atr = self._process_alert_tick()
        return htr or atr

    def _process_alert_tick(self) -> bool:
        max_tick = 30
        if 0 < self._step_alert < max_tick and self.alert_state != AnimationState.IDLE:
            if self.alert_state == AnimationState.GROWING:
                self._step_alert += 1
            elif self.alert_state == AnimationState.SHRINKING:
                self._step_alert -= 1

        if self._step_alert >= max_tick and self.alert_state == AnimationState.GROWING:
            self.alert_state = AnimationState.SHRINKING
            self._step_alert -= 1
        elif self._step_alert <= 0 and self.alert_state == AnimationState.SHRINKING:
            self.alert_state = AnimationState.GROWING
            self._step_alert += 1
            self._alert_pulse_count += 1

        if self._alert_pulse_count > 4:
            self.alert_state = AnimationState.IDLE
            self.is_alerting = False
            self.draw_color = DEFAULT_DRAW_COLOR
            self.draw_size = 0.0
            self._alert_pulse_count = 0
            return True
        else:
            if self.alert_state in (AnimationState.GROWING, AnimationState.SHRINKING):
                self.draw_size = quint_ease_in(self._step_alert, 1, 100, max_tick)
            return False

    def _process_highlight_tick(self) -> bool:
        max_tick = 20
        if 0 < self._step_highlight < max_tick and self.highlight_state != AnimationState.IDLE:
            if self.highlight_state == AnimationState.GROWING:
                self._step_highlight += 1
            elif self.highlight_state == AnimationState.SHRINKING:
                self._step_highlight -= 1

        if self._step_highlight >= max_tick and self.highlight_state == AnimationState.GROWING:
            self.highlight_state = AnimationState.PAUSED if not self._is_flash else AnimationState.SHRINKING
            self._step_highlight -= 1
        elif self._step_highlight <= 0 and self.highlight_state == AnimationState.SHRINKING:
            self._step_highlight += 1
            self.highlight_state = AnimationState.IDLE
            self.is_highlighted = False
            self._is_flash = False
            self.draw_color = DEFAULT_DRAW_COLOR
            self.draw_size = 0.0
            return True

        if self.highlight_state == AnimationState.GROWING:
            self.draw_size = quint_ease_out(self._step_highlight, 1, 10, max_tick)
        elif self.highlight_state == AnimationState.SHRINKING:
            self.draw_size = quint_ease_in(self._step_highlight, 1, 10, max_tick)

        return False

    def reset_highlight(self):
        self._step_highlight += 1
        self.highlight_state = AnimationState.IDLE
        self.is_highlighted = False
        self.draw_color = DEFAULT_DRAW_COLOR
        self.draw_size = 0.0

    def clear_alert(self):
        self.draw_size = 0.0

    def clear_highlight(self):
        self.draw_size = 0.0

    def start_alert(self):
        self.is_alerting = True
        self.alert_state = AnimationState.GROWING
        self.draw_color = ALERTING_DRAW_COLOR
        self._step_alert = 1

    def start_highlight(self, flash: bool = False):
        self.is_highlighted = True
        self.highlight_state = AnimationState.GROWING
        self.draw_color = HIGHLIGHT_DRAW_COLOR
        self._is_flash = flash
        self._step_highlight = 1

"""Port of SolarSystemManager.cs - manages system data, VBOs, alerts, pathfinding."""
import json
import os
import sys
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from taco.core.path_info import PathInfo
from taco.core.pathfinder import SolarSystemPathFinder
from taco.core.solar_system import (
    SolarSystem, AnimationState, DEFAULT_DRAW_COLOR,
    CHARACTER_LOCATION_DRAW_COLOR, CHARACTER_ALERT_DRAW_COLOR, color_to_rgba32,
)
from taco.core.solar_system_data import SolarSystemConnection, SolarSystemData
from taco.core.system_stats import SystemStats


class SolarSystemManager:
    def __init__(self):
        self._solar_systems: dict[int, SolarSystem] = {}
        self._names: dict[str, int] = {}

        # VBO data arrays
        self._system_vbo_content: Optional[np.ndarray] = None
        self._system_color_vao_content: Optional[np.ndarray] = None
        self._system_element_vao_content: Optional[np.ndarray] = None

        # Connection arrays
        self.connection_vbo_content: Optional[np.ndarray] = None
        self.connection_color_vao_content: Optional[np.ndarray] = None
        self.connection_vao_content: Optional[np.ndarray] = None
        self.connection_vertex_count: int = 0

        # Dirty flags
        self.is_system_vbo_dirty = True
        self.is_system_vao_dirty = True
        self.is_color_vao_dirty = True
        self.is_system_vbo_data_dirty = True
        self.is_system_vao_data_dirty = True
        self.is_system_color_vao_data_dirty = True
        self.is_connection_vbo_data_dirty = True
        self.is_connection_vao_data_dirty = True
        self.is_connection_color_data_dirty = True
        self.is_connection_vbo_dirty = True
        self.is_connection_vao_dirty = True
        self.is_connection_color_vao_dirty = True

        # Home system / character
        self._home_system_id = -1
        self._character_location = -1
        self._character_location_systems: set[int] = set()

        # Crosshairs
        self._red_crosshair_ids: deque[int] = deque(maxlen=50)
        self._green_crosshair_ids: deque[int] = deque(maxlen=50)

        # Animation tracking
        self._alert_systems: list[int] = []
        self._highlight_systems: list[int] = []

        # Uniforms
        self._uni_system_ids = [-1] * 10
        self._uni_colors = [(1.0, 1.0, 1.0, 1.0)] * 10
        self._uni_sizes = [0.0] * 10
        self._are_uniforms_clean = False

        # Pathfinding
        self.path_finder: Optional[SolarSystemPathFinder] = None
        self._pathfinding_data: Optional[list[SolarSystemData]] = None
        self._pathfinding_queue: deque[PathInfo] = deque()
        self._pathfinding_cache: dict[int, PathInfo] = {}
        self._max_pathfinding_cache = 5000
        self._processing_path = False
        self._ok_to_process_paths = False

        # Stats
        self._system_stats: dict[int, SystemStats] = {}
        self._max_alert_age = 15
        self._max_alerts = 15

        # Region data
        self._region_names: dict[int, str] = {}
        self._region_centroids: dict[int, tuple[float, float]] = {}
        self._region_labels: list[tuple[str, float, float, float]] = []
        self._current_map_mode: str = "3d"

    # --- Properties ---

    @property
    def home_system_id(self) -> int:
        return self._home_system_id

    @property
    def character_location(self) -> int:
        return self._character_location

    @property
    def solar_systems(self) -> dict[int, SolarSystem]:
        return self._solar_systems

    @property
    def system_count(self) -> int:
        return len(self._solar_systems)

    @property
    def names(self) -> dict[str, int]:
        return self._names

    @property
    def name_list(self) -> list[str]:
        return list(self._names.keys())

    @property
    def red_crosshair_ids(self) -> deque[int]:
        return self._red_crosshair_ids

    @property
    def green_crosshair_ids(self) -> deque[int]:
        return self._green_crosshair_ids

    @property
    def system_vbo_content(self) -> Optional[np.ndarray]:
        return self._system_vbo_content

    @property
    def system_color_vao_content(self) -> Optional[np.ndarray]:
        return self._system_color_vao_content

    @property
    def system_element_vao_content(self) -> Optional[np.ndarray]:
        return self._system_element_vao_content

    @property
    def all_vbos_clean(self) -> bool:
        return not (self.is_system_vbo_dirty or self.is_system_vao_dirty or self.is_color_vao_dirty)

    @property
    def is_data_clean(self) -> bool:
        return not (self.is_system_vbo_data_dirty or
                    self.is_system_vao_data_dirty or
                    self.is_system_color_vao_data_dirty)

    @property
    def are_uniforms_clean(self) -> bool:
        return self._are_uniforms_clean

    @property
    def uniform_systems(self) -> list[int]:
        return self._uni_system_ids

    @property
    def uniform_colors(self) -> list[tuple[float, float, float, float]]:
        return self._uni_colors

    @property
    def uniform_sizes(self) -> list[float]:
        return self._uni_sizes

    @property
    def pathfinding_cache(self) -> dict[int, PathInfo]:
        return self._pathfinding_cache

    @property
    def is_processing_paths(self) -> bool:
        return len(self._pathfinding_queue) > 0

    @property
    def max_alert_age(self) -> int:
        return self._max_alert_age

    @max_alert_age.setter
    def max_alert_age(self, value: int):
        self._max_alert_age = value

    @property
    def max_alerts(self) -> int:
        return self._max_alerts

    @max_alerts.setter
    def max_alerts(self, value: int):
        self._max_alerts = value

    @property
    def character_location_systems(self) -> set[int]:
        return self._character_location_systems

    @property
    def region_labels(self) -> list[tuple[str, float, float, float]]:
        return self._region_labels

    # --- Data Loading ---

    def load_system_data(self, data: list[SolarSystemData]) -> bool:
        self._pathfinding_data = data
        self.path_finder = SolarSystemPathFinder(data)
        self._ok_to_process_paths = True

        for sys_data in data:
            solar = SolarSystem(sys_data.native_id, sys_data.name, sys_data.x, sys_data.y, sys_data.z,
                               x2d=sys_data.x2d, y2d=sys_data.y2d, region_id=sys_data.region_id)
            solar.connected_to = []

            if sys_data.connected_to:
                for conn_data in sys_data.connected_to:
                    conn = SolarSystemConnection(
                        to_system_id=conn_data.to_system_id,
                        to_system_native_id=conn_data.to_system_native_id,
                        is_regional=conn_data.is_regional,
                    )
                    solar.connected_to.append(conn)

            self._names[solar.name] = sys_data.id
            self._solar_systems[sys_data.id] = solar

        self._load_region_names()
        return self.system_count > 0

    def set_map_mode(self, mode: str):
        """Switch all systems between '3d' projection and '2d' schematic."""
        self._current_map_mode = mode
        for system in self._solar_systems.values():
            system.set_map_mode(mode)
        self.is_system_vbo_data_dirty = True
        self.is_connection_vbo_data_dirty = True
        self._compute_region_centroids()

    def _load_region_names(self):
        """Load region name lookup from regions.json."""
        if getattr(sys, 'frozen', False):
            base = os.path.join(sys._MEIPASS, "taco", "resources")
        else:
            base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources")
        path = os.path.normpath(os.path.join(base, "data", "regions.json"))
        if os.path.exists(path):
            with open(path, "r") as f:
                raw = json.load(f)
            self._region_names = {int(k): v for k, v in raw.items()}
        self._compute_region_centroids()

    def _compute_region_centroids(self):
        """Compute average position of all systems per region for label placement."""
        self._region_labels = []
        if not self._region_names:
            return

        # Accumulate positions per region
        region_sums: dict[int, list[float]] = {}  # region_id -> [sum_x, sum_y, sum_z, count]
        for system in self._solar_systems.values():
            rid = system.region_id
            if rid == 0 or rid not in self._region_names:
                continue
            if rid not in region_sums:
                region_sums[rid] = [0.0, 0.0, 0.0, 0.0]
            region_sums[rid][0] += system.xf
            region_sums[rid][1] += system.yf
            region_sums[rid][2] += system.zf
            region_sums[rid][3] += 1.0

        for rid, (sx, sy, sz, count) in region_sums.items():
            if count > 0:
                name = self._region_names[rid]
                self._region_labels.append((name, sx / count, sy / count, sz / count))

    # --- VBO Init ---

    def init_vbo_data(self) -> bool:
        self._init_system_vbo_content()
        self._init_system_element_vao_content()
        self._init_system_color_vao_content()
        self._extract_connections()
        return self.all_vbos_clean

    def _init_system_vbo_content(self):
        count = self.system_count
        self._system_vbo_content = np.zeros((count, 3), dtype=np.float32)
        for sys_id, system in self._solar_systems.items():
            self._system_vbo_content[sys_id] = system.xyz
        self.is_system_vbo_dirty = (len(self._system_vbo_content) != count)

    def _init_system_element_vao_content(self):
        count = self.system_count
        self._system_element_vao_content = np.arange(count, dtype=np.int32)
        self.is_system_vao_dirty = (len(self._system_element_vao_content) != count)

    def _init_system_color_vao_content(self):
        count = self.system_count
        default_color = color_to_rgba32(DEFAULT_DRAW_COLOR)
        self._system_color_vao_content = np.full(count, default_color, dtype=np.uint32)
        self.is_color_vao_dirty = (len(self._system_color_vao_content) != count)

    def _extract_connections(self):
        drawn = set()
        connection_count = 0

        for sys_id, system in self._solar_systems.items():
            if sys_id in drawn:
                continue
            connection_count += len(system.connected_to)
            drawn.add(sys_id)

        drawn.clear()
        self.connection_vertex_count = connection_count * 2

        self.connection_vbo_content = np.zeros((self.connection_vertex_count, 3), dtype=np.float32)
        self.connection_vao_content = np.arange(self.connection_vertex_count, dtype=np.int32)
        self.connection_color_vao_content = np.zeros((self.connection_vertex_count, 4), dtype=np.float32)

        i = 0
        regional_color = np.array([40.0 / 255.0, 0.0 / 255.0, 10.0 / 255.0, 1.0], dtype=np.float32)
        normal_color = np.array([10.0 / 255.0, 0.0 / 255.0, 120.0 / 255.0, 1.0], dtype=np.float32)

        # Draw regional (red) lines first, then normal (blue) on top
        for is_regional_pass in (True, False):
            drawn_pass = set()
            for sys_id, system in self._solar_systems.items():
                if sys_id in drawn_pass:
                    continue
                for conn in system.connected_to:
                    if conn.to_system_id not in self._solar_systems:
                        continue
                    if conn.is_regional != is_regional_pass:
                        continue
                    # Start vertex
                    self.connection_vbo_content[i] = [system.xf, system.yf, system.zf]
                    color = regional_color if conn.is_regional else normal_color
                    self.connection_color_vao_content[i] = color
                    i += 1

                    # End vertex
                    target = self._solar_systems[conn.to_system_id]
                    self.connection_vbo_content[i] = [target.xf, target.yf, target.zf]
                    self.connection_color_vao_content[i] = color
                    i += 1

                drawn_pass.add(sys_id)

        self.is_connection_vbo_data_dirty = False
        self.is_connection_vao_data_dirty = False
        self.is_connection_color_data_dirty = False

    # --- VBO Refresh ---

    def refresh_vbo_data(self) -> bool:
        self._refresh_system_vbo_data()
        self._refresh_element_vao_data()
        self._refresh_color_vao_data()
        return self.is_data_clean

    def _refresh_system_vbo_data(self):
        if not self.is_system_vbo_data_dirty:
            return
        for i in range(self.system_count):
            self._system_vbo_content[i] = self._solar_systems[i].xyz
        self.is_system_vbo_data_dirty = False
        self.is_system_vbo_dirty = True

    def _refresh_element_vao_data(self):
        if not self.is_system_vao_data_dirty:
            return
        for i in range(self.system_count):
            self._system_element_vao_content[i] = i
        self.is_system_vao_data_dirty = False
        self.is_system_vao_dirty = True

    def _refresh_color_vao_data(self):
        if not self.is_system_color_vao_data_dirty:
            return
        for i in range(self.system_count):
            if i in self._character_location_systems:
                if self._solar_systems[i].is_alerting:
                    self._system_color_vao_content[i] = color_to_rgba32(CHARACTER_ALERT_DRAW_COLOR)
                else:
                    self._system_color_vao_content[i] = color_to_rgba32(CHARACTER_LOCATION_DRAW_COLOR)
            else:
                self._system_color_vao_content[i] = self._solar_systems[i].draw_color_argb32
        self.is_system_color_vao_data_dirty = False
        self.is_color_vao_dirty = True

    # --- Home / Character ---

    def set_current_home_system(self, system_id: int):
        if self._home_system_id != -1:
            self.clear_current_system()

        self._home_system_id = system_id
        if self._home_system_id == -1:
            return

        self.add_green_crosshair(self._home_system_id)

        for red_id in list(self._red_crosshair_ids):
            self._pathfinding_queue.append(PathInfo(
                from_system=self._home_system_id, to_system=red_id
            ))

        if self._home_system_id != -1 and self._character_location != -1:
            self._pathfinding_queue.append(PathInfo(
                from_system=self._character_location, to_system=self._home_system_id
            ))

    def set_character_location(self, system_id: int):
        self._character_location = system_id
        if self._character_location == -1:
            return

        for red_id in list(self._red_crosshair_ids):
            self._pathfinding_queue.append(PathInfo(
                from_system=system_id, to_system=red_id
            ))

        if self._home_system_id != -1:
            self._pathfinding_queue.append(PathInfo(
                from_system=system_id, to_system=self._home_system_id
            ))

    def clear_character_location(self):
        self._character_location = -1

    def clear_current_system(self):
        self._home_system_id = -1
        self._green_crosshair_ids.clear()

    def set_character_location_systems(self, system_ids):
        self._character_location_systems.clear()
        for sid in system_ids:
            if sid >= 0 and sid in self._solar_systems:
                self._character_location_systems.add(sid)
        self.is_system_color_vao_data_dirty = True

    def clear_character_location_systems(self):
        self._character_location_systems.clear()
        self.is_system_color_vao_data_dirty = True

    # --- Alerts / Highlights ---

    def incoming_tick(self) -> bool:
        self._process_tick()
        return len(self._alert_systems) > 0 or len(self._highlight_systems) > 0

    def _process_tick(self):
        # Process alerts
        to_remove = []
        for sys_id in self._alert_systems:
            if self._solar_systems[sys_id].process_tick():
                to_remove.append(sys_id)

        if to_remove:
            self._are_uniforms_clean = False
            for sys_id in to_remove:
                self._solar_systems[sys_id].clear_alert()
                self._alert_systems.remove(sys_id)
        to_remove.clear()

        # Process highlights
        for sys_id in self._highlight_systems:
            if self._solar_systems[sys_id].process_tick():
                to_remove.append(sys_id)

        if to_remove:
            for sys_id in to_remove:
                self._solar_systems[sys_id].clear_highlight()
                self._highlight_systems.remove(sys_id)

        # Only mark uniforms dirty when there are active animations
        if self._alert_systems or self._highlight_systems:
            self._are_uniforms_clean = False

    def add_alert(self, system_id: int, intel_report: str | None = None):
        if system_id not in self._alert_systems:
            # Reset highlights
            for hl_id in self._highlight_systems:
                self._solar_systems[hl_id].reset_highlight()
            self._highlight_systems.clear()

            self._alert_systems.append(system_id)
            self._solar_systems[system_id].start_alert()

            # Queue pathfinding from all monitored (green crosshair) systems
            for green_id in list(self._green_crosshair_ids):
                if green_id >= 0:
                    cache_id = self.generate_unique_path_id(green_id, system_id)
                    if cache_id not in self._pathfinding_cache:
                        self.find_and_cache_path(green_id, system_id)

            self._are_uniforms_clean = False

        # Update stats
        if system_id in self._system_stats:
            self._system_stats[system_id].update(intel_report)
        else:
            stats = SystemStats(system_id)
            if intel_report is not None:
                stats.last_intel_report = intel_report
            self._system_stats[system_id] = stats

        # Move to back of red crosshair queue
        if system_id in self._red_crosshair_ids and len(self._red_crosshair_ids) > 1:
            new_queue = deque(maxlen=50)
            for sid in self._red_crosshair_ids:
                if sid != system_id:
                    new_queue.append(sid)
            self._red_crosshair_ids = new_queue

        self._red_crosshair_ids.append(system_id)

        while len(self._red_crosshair_ids) > self._max_alerts:
            expired_id = self._red_crosshair_ids.popleft()
            self._system_stats.pop(expired_id, None)

    def add_green_crosshair(self, system_id: int):
        self._green_crosshair_ids.append(system_id)
        while len(self._green_crosshair_ids) > 10:
            self._green_crosshair_ids.popleft()

    def add_highlight(self, system_id: int, flash: bool = False):
        if system_id not in self._highlight_systems and not self._solar_systems[system_id].is_alerting:
            self._highlight_systems.append(system_id)
            self._solar_systems[system_id].start_highlight(flash)
            self._are_uniforms_clean = False

    def remove_highlight(self, system_id: int):
        if system_id in self._highlight_systems:
            self._solar_systems[system_id].highlight_state = AnimationState.SHRINKING

    def remove_expired_alerts(self):
        if self._max_alert_age == 0:
            return

        older_than = datetime.now() - timedelta(minutes=self._max_alert_age)
        expired = [
            stats.system_id for stats in self._system_stats.values()
            if not stats.expired and stats.last_report < older_than
        ]

        if expired:
            new_queue = deque(maxlen=50)
            while self._red_crosshair_ids:
                sid = self._red_crosshair_ids.popleft()
                if sid not in expired:
                    new_queue.append(sid)
                else:
                    del self._system_stats[sid]
            self._red_crosshair_ids = new_queue

    # --- Uniforms ---

    def build_uniforms(self):
        total = len(self._alert_systems) + len(self._highlight_systems)
        system_count = min(total, 10)

        self._uni_system_ids = [-1] * 10
        self._uni_colors = [(1.0, 1.0, 1.0, 1.0)] * 10
        self._uni_sizes = [0.0] * 10

        i = 0
        if len(self._alert_systems) <= 10:
            for sys_id in self._alert_systems:
                self._uni_system_ids[i] = sys_id
                self._uni_sizes[i] = self._solar_systems[sys_id].draw_size
                self._uni_colors[i] = self._solar_systems[sys_id].draw_color_rgba_floats
                i += 1
        else:
            reset_at = len(self._alert_systems) - 10
            started = False
            j = 0
            for sys_id in self._alert_systems:
                if j == reset_at and not started:
                    i = 0
                    started = True
                if started:
                    self._uni_system_ids[i] = sys_id
                    self._uni_sizes[i] = self._solar_systems[sys_id].draw_size
                    self._uni_colors[i] = self._solar_systems[sys_id].draw_color_rgba_floats
                j += 1
                i += 1

        if i < system_count:
            for sys_id in self._highlight_systems:
                if sys_id in self._alert_systems:
                    continue
                self._uni_system_ids[i] = sys_id
                self._uni_sizes[i] = self._solar_systems[sys_id].draw_size
                self._uni_colors[i] = self._solar_systems[sys_id].draw_color_rgba_floats
                i += 1
                if i == system_count:
                    break

        while i < 10:
            self._uni_system_ids[i] = -1
            self._uni_colors[i] = (1.0, 1.0, 1.0, 1.0)
            self._uni_sizes[i] = 0.0
            i += 1

        self._are_uniforms_clean = True

    # --- Pathfinding ---

    @staticmethod
    def generate_unique_path_id(from_system_id: int, to_system_id: int) -> int:
        return (from_system_id * 10000) + to_system_id

    def find_path(self, from_system_id: int, to_system_id: int) -> Optional[PathInfo]:
        if from_system_id >= 0 and to_system_id >= 0 and self.path_finder:
            return self.path_finder.find_path(from_system_id, to_system_id)
        return None

    def find_and_cache_path(self, from_system_id: int, to_system_id: int):
        temp_path = PathInfo(from_system=from_system_id, to_system=to_system_id)
        if temp_path.path_id not in self._pathfinding_cache:
            self._pathfinding_queue.append(temp_path)

    def process_pathfinding_queue(self):
        """Process one path from the queue (called from QTimer or QThread)."""
        if not self._ok_to_process_paths or self._processing_path:
            return

        self._processing_path = True
        if self._pathfinding_queue:
            working = self._pathfinding_queue.popleft()
            result = self.path_finder.find_path(working.from_system, working.to_system)
            working.total_jumps = result.total_jumps
            working.path_systems = result.path_systems

            cache_id = self.generate_unique_path_id(working.from_system, working.to_system)
            if cache_id not in self._pathfinding_cache:
                if len(self._pathfinding_cache) >= self._max_pathfinding_cache:
                    self._pathfinding_cache.clear()
                self._pathfinding_cache[cache_id] = working

        self._processing_path = False

    def get_system_stats(self, system_id: int) -> Optional[SystemStats]:
        return self._system_stats.get(system_id)

"""Main application window. Ported from MainForm.cs."""
import json
import os
import sys
import re
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QCompleter, QMenu, QApplication,
    QStatusBar,
)
from PyQt6.QtCore import Qt, QTimer, QStringListModel
from PyQt6.QtGui import QAction, QKeySequence, QIcon

from taco.config.taco_config import TacoConfig
from taco.core.alert_trigger import (
    AlertTrigger, AlertType, RangeAlertOperator, RangeAlertType,
)
from taco.core.solar_system_data import SolarSystemData
from taco.core.solar_system_manager import SolarSystemManager
from taco.intel.log_entry import LogEntry, LogEntryType, LogFileType
from taco.intel.log_watcher import LogWatcher
from taco.intel.local_watcher import LocalWatcher
from taco.audio.sound_manager import SoundManager
from taco.ui.gl_map_widget import GLMapWidget
from taco.ui.intel_panel import IntelPanel
from taco.ui.config_panel import ConfigPanel
from taco.ui.theme import apply_theme


def _resource_path(relative: str) -> str:
    if getattr(sys, 'frozen', False):
        base = os.path.join(sys._MEIPASS, "taco", "resources")
    else:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources")
    return os.path.normpath(os.path.join(base, relative))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("T.A.C.O. Twosday: Python Edition v2.1.0")
        self.setMinimumSize(800, 600)

        # Core
        self._config = TacoConfig.load()
        self._manager = SolarSystemManager()
        self._sound_manager = SoundManager()

        # State
        self._process_logs = False
        self._is_full_screen = False
        self._mute_sound = False
        self._char_locations: dict[str, int] = {}
        self._followed_chars: set[str] = set()
        self._refocus_index: int = 0
        self._sticky_highlights: set[int] = set()
        self._alert_triggers: list[AlertTrigger] = []
        self._ignore_strings: list[re.Pattern] = []
        self._ignore_systems: list[int] = []

        # Log watchers
        self._log_watchers: dict[str, LogWatcher] = {}
        self._local_watcher: LocalWatcher | None = None

        # Load data
        self._load_system_data()
        self._sound_manager.load_sounds()
        self._load_config()

        # Apply saved map mode
        if self._config.map_mode == "2d":
            self._manager.set_map_mode("2d")

        # Build UI
        self._build_ui()
        self._setup_shortcuts()

        # Apply theme
        apply_theme(QApplication.instance(), self._config.dark_mode)

        # Set window state
        self._set_window_state()

    def _load_system_data(self):
        json_path = _resource_path("data/systemdata.json")
        if not os.path.exists(json_path):
            return

        with open(json_path, 'r') as f:
            raw = json.load(f)

        systems = [SolarSystemData.from_dict(d) for d in raw]
        self._manager.load_system_data(systems)

    def _load_config(self):
        # Load alert triggers
        self._alert_triggers = [
            AlertTrigger.from_dict(d) for d in self._config.alert_triggers
        ]

        # Load ignore strings
        self._ignore_strings = []
        for s in self._config.ignore_strings:
            try:
                self._ignore_strings.append(re.compile(r'\b' + re.escape(s) + r'\b', re.IGNORECASE))
            except re.error:
                pass

        # Load ignore systems
        self._ignore_systems = list(self._config.ignore_systems)

        # Home system
        if self._config.preserve_home_system and self._config.home_system_id != -1:
            self._manager.set_current_home_system(self._config.home_system_id)

        # Monitored systems (green crosshairs, excluding home)
        for sys_id in self._config.monitored_systems:
            if sys_id != self._manager.home_system_id:
                self._manager.add_green_crosshair(sys_id)

        # Start with a clean slate — don't restore sticky highlights from config
        self._sticky_highlights = set()

        # Manager limits
        self._manager.max_alert_age = self._config.max_alert_age
        self._manager.max_alerts = self._config.max_alerts

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter = self._splitter

        # Left: GL map
        self._gl_widget = GLMapWidget(self._manager, self)
        self._gl_widget.camera_distance = self._config.camera_distance
        self._gl_widget.look_at[0] = self._config.look_at_x
        self._gl_widget.look_at[1] = self._config.look_at_y
        self._gl_widget.map_text_size = self._config.map_text_size
        self._gl_widget.persistent_labels = self._config.persistent_system_labels
        self._gl_widget.show_alert_age = self._config.show_alert_age
        self._gl_widget.display_char_names = self._config.display_character_names
        self._gl_widget.show_char_locations = self._config.show_character_locations
        self._gl_widget.sticky_highlight_systems = self._sticky_highlights
        self._gl_widget.landmark_systems = set(self._config.landmark_systems)
        if self._config.map_mode == "2d":
            self._gl_widget.set_map_mode("2d")

        self._gl_widget.system_clicked.connect(self._on_system_clicked)
        self._gl_widget.system_hovered.connect(self._on_system_hovered)
        self._gl_widget.system_right_clicked.connect(self._on_system_right_clicked)

        splitter.addWidget(self._gl_widget)

        # Right: tabs panel
        self._right_panel = QWidget()
        right_panel = self._right_panel
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(2, 2, 2, 2)

        # Search bar
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search:"))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("System name...")
        self._search_completer = QCompleter(self._manager.name_list)
        self._search_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._search_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._search_input.setCompleter(self._search_completer)
        self._search_completer.activated.connect(self._on_search)
        self._search_input.returnPressed.connect(self._on_search)
        search_row.addWidget(self._search_input)
        right_layout.addLayout(search_row)

        # Control buttons
        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("Start")
        self._start_btn.clicked.connect(self._on_start_stop)
        btn_row.addWidget(self._start_btn)

        mute_btn = QPushButton("Mute")
        mute_btn.setCheckable(True)
        mute_btn.toggled.connect(self._on_mute_toggle)
        btn_row.addWidget(mute_btn)
        right_layout.addLayout(btn_row)

        # Intel + Config tabs
        self._tab_widget = IntelPanel()
        right_layout.addWidget(self._tab_widget)

        # Config panel
        self._config_panel = ConfigPanel(
            self._config, self._manager.name_list,
            system_names_dict=self._manager.names,
            sound_manager=self._sound_manager,
            char_names_func=lambda: sorted(self._char_locations.keys()),
        )
        self._config_panel.config_changed.connect(self._on_config_changed)
        self._config_panel.alerts_changed.connect(self._on_alerts_changed)
        self._config_panel.channel_added.connect(self._on_channel_added)
        self._config_panel.channel_removed.connect(self._on_channel_removed)
        self._config_panel.dark_mode_changed.connect(self._on_dark_mode_changed)
        self._config_panel.persistent_labels_changed.connect(self._on_persistent_labels_changed)
        self._config_panel.map_text_size_changed.connect(self._on_map_text_size_changed)
        self._config_panel.landmarks_changed.connect(self._on_landmarks_changed)
        self._config_panel.map_mode_changed.connect(self._on_map_mode_changed)

        # Pre-create tabs for configured channels so they're always visible
        for channel in self._config.custom_channels:
            name = channel.get("name", "")
            if name:
                self._tab_widget.add_channel_tab(name, name)

        # System tab goes after channels; new channels will insert before it
        self._tab_widget.init_system_tab()
        self._tab_widget.addTab(self._config_panel, "Settings")

        splitter.addWidget(right_panel)
        splitter.setSizes([700, 500])

        main_layout.addWidget(splitter)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

        # Start animation
        self._gl_widget.start_animation()

    def _setup_shortcuts(self):
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        self.addAction(quit_action)

        esc_action = QAction("Exit Fullscreen", self)
        esc_action.setShortcut(QKeySequence("Escape"))
        esc_action.triggered.connect(self._exit_fullscreen)
        self.addAction(esc_action)

        fullscreen_action = QAction("Toggle Fullscreen", self)
        fullscreen_action.setShortcut(QKeySequence("F11"))
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        self.addAction(fullscreen_action)

        hide_panel_action = QAction("Hide Panel", self)
        hide_panel_action.setShortcut(QKeySequence("Ctrl+H"))
        hide_panel_action.triggered.connect(self._toggle_panel)
        self.addAction(hide_panel_action)

    def _set_window_state(self):
        w = self._config.window_size_x if self._config.preserve_window_size else 800
        h = self._config.window_size_y if self._config.preserve_window_size else 600
        if self._config.preserve_window_size:
            self.resize(w, h)
        if self._config.preserve_window_position:
            x = self._config.window_position_x
            y = self._config.window_position_y
            # Always clamp to primary monitor
            primary = QApplication.primaryScreen()
            if primary:
                avail = primary.availableGeometry()
                # Use config size (not self.width()) since widget may not be laid out yet
                x = max(avail.x(), min(x, avail.x() + avail.width() - w))
                y = max(avail.y(), min(y, avail.y() + avail.height() - h))
            self.move(x, y)
        if self._config.preserve_full_screen_status and self._config.is_full_screen:
            self._toggle_fullscreen()
        # Ensure window is visible and focused
        self.raise_()
        self.activateWindow()

    # --- Log Processing ---

    def _on_start_stop(self):
        if self._process_logs:
            self._stop_logs()
        else:
            self._start_logs()

    def _start_logs(self):
        log_path = self._config.log_path if self._config.override_log_path else None

        # Start custom channel watchers
        for channel in self._config.custom_channels:
            if not channel.get("monitor", True):
                continue
            name = channel["name"]
            prefix = channel["prefix"]

            self._tab_widget.add_channel_tab(name, name)

            watcher = LogWatcher(prefix, LogFileType.CHAT, log_path)
            watcher.new_log_entry.connect(lambda entry, n=name: self._on_new_log_entry(entry, n))
            started = watcher.start_watch()
            self._log_watchers[name] = watcher
            if started:
                self._write_system_intel(f"Monitoring channel: {name} ({prefix})")
            else:
                self._write_system_intel(f"WARNING: Could not find logs for channel: {name} ({prefix})")

        # Start game log watcher
        if self._config.monitor_game_log:
            watcher = LogWatcher("", LogFileType.GAME, log_path)
            watcher.new_log_entry.connect(lambda entry: self._on_new_log_entry(entry, "Game"))
            watcher.combat_event.connect(self._on_combat_event)
            watcher.start_watch()
            self._log_watchers["__game__"] = watcher

        # Start local watcher
        self._local_watcher = LocalWatcher(log_path)
        self._local_watcher.system_change.connect(self._on_system_change)
        self._local_watcher.start_watch()

        self._process_logs = True
        self._start_btn.setText("Stop")
        self._status_bar.showMessage("Monitoring...")
        self._write_system_intel("Log monitoring started")

    def _stop_logs(self):
        for watcher in self._log_watchers.values():
            watcher.stop_watch()
        self._log_watchers.clear()

        if self._local_watcher:
            self._local_watcher.stop_watch()
            self._local_watcher = None

        self._process_logs = False
        self._start_btn.setText("Start")
        self._status_bar.showMessage("Stopped")
        self._write_system_intel("Log monitoring stopped")

    def _on_new_log_entry(self, entry: LogEntry, channel_name: str = ""):
        if entry.entry_type in (LogEntryType.NEW_CHAT_LOG, LogEntryType.OPEN_CHAT_LOG):
            # Track character from log file listener
            if entry.character_name and entry.character_name not in self._char_locations:
                self._char_locations[entry.character_name] = -1
            if self._config.display_new_file_alerts or self._config.display_open_file_alerts:
                self._write_system_intel(
                    f"[{channel_name}] {entry.entry_type.name}: {entry.file_name}"
                )
            return

        if entry.entry_type != LogEntryType.CHAT_EVENT:
            return
        if not entry.parse_success:
            return

        # Game log entries are for combat detection only, not intel alerts
        if entry.log_type == LogFileType.GAME:
            return

        content = entry.line_content

        # Check ignore strings
        for pattern in self._ignore_strings:
            if pattern.search(content):
                return

        # Match system names
        matched_systems = []
        for sys_id, system in self._manager.solar_systems.items():
            if sys_id in self._ignore_systems:
                continue
            if system.match_name_regex(content):
                matched_systems.append(sys_id)

        # Write intel to channel tab
        time_str = entry.log_time or datetime.now().strftime("%H:%M:%S")
        player = entry.player_name or "?"
        display = f"[{time_str}] {player} > {content}"

        system_names = [self._manager.solar_systems[sid].name for sid in matched_systems
                        if sid in self._manager.solar_systems]
        self._tab_widget.write_intel(channel_name, display, system_names=system_names)

        if not matched_systems:
            return

        # Check if channel has alerting enabled
        channel_alert = True
        for ch in self._config.custom_channels:
            if ch.get("name") == channel_name:
                channel_alert = ch.get("alert", True)
                break

        # Process alerts for matched systems.
        # Collect all ranged trigger matches across systems, play only the closest.
        best_ranged = None  # (jumps, trigger, sys_id, ref_name)
        for sys_id in matched_systems:
            self._manager.add_alert(sys_id, content)

            if not channel_alert:
                continue

            # Custom triggers fire immediately (text-based, no distance concept)
            self._evaluate_custom_triggers(content)

            # Collect best ranged match for this system
            match = self._find_closest_ranged_match(sys_id)
            if match is not None:
                jumps, trigger, ref_name = match
                if best_ranged is None or jumps < best_ranged[0]:
                    best_ranged = (jumps, trigger, sys_id, ref_name)

        # Play only the single closest ranged alert
        if best_ranged:
            jumps, trigger, sys_id, ref_name = best_ranged
            now = datetime.now()
            if (trigger.repeat_interval == 0 or
                    trigger.trigger_time < now - timedelta(seconds=max(trigger.repeat_interval, 5))):
                trigger.trigger_time = now
                self._play_alert_sound(trigger)
                if channel_name:
                    sys_name = self._manager.solar_systems[sys_id].name if sys_id in self._manager.solar_systems else "?"
                    jump_label = "jump" if jumps == 1 else "jumps"
                    self._tab_widget.write_intel(
                        channel_name, f"  ** ALERT: {sys_name} — {jumps} {jump_label} from {ref_name} **"
                    )

        # Add jump info to display
        if self._manager.home_system_id != -1:
            for sys_id in matched_systems:
                path_id = self._manager.generate_unique_path_id(
                    self._manager.home_system_id, sys_id
                )
                if path_id in self._manager.pathfinding_cache:
                    path = self._manager.pathfinding_cache[path_id]
                    jumps = path.total_jumps
                    if jumps < 0:
                        continue
                    name = self._manager.solar_systems[sys_id].name if sys_id in self._manager.solar_systems else "?"
                    self._tab_widget.write_intel(
                        channel_name, f"  ^ {name}: {jumps} jumps from home"
                    )

    def _evaluate_custom_triggers(self, content: str):
        """Fire custom (text-match) triggers immediately — they have no distance concept."""
        for trigger in self._alert_triggers:
            if not trigger.enabled or trigger.type != AlertType.CUSTOM:
                continue
            if trigger.text and trigger.text.lower() in content.lower():
                now = datetime.now()
                if (trigger.repeat_interval == 0 or
                        trigger.trigger_time < now - timedelta(seconds=trigger.repeat_interval)):
                    trigger.trigger_time = now
                    self._play_alert_sound(trigger)

    def _find_closest_ranged_match(self, system_id: int):
        """Find the closest ranged trigger match for a system across all triggers.
        Returns (jumps, trigger, ref_name) or None."""
        best = None
        for trigger in self._alert_triggers:
            if not trigger.enabled or trigger.type != AlertType.RANGED:
                continue
            # Check repeat interval before doing pathfinding work
            now = datetime.now()
            if not (trigger.repeat_interval == 0 or
                    trigger.trigger_time < now - timedelta(seconds=max(trigger.repeat_interval, 5))):
                continue

            match = self._find_closest_for_trigger(trigger, system_id)
            if match is not None:
                jumps, ref_name = match
                if best is None or jumps < best[0]:
                    best = (jumps, trigger, ref_name)
        return best

    def _find_closest_for_trigger(self, trigger: AlertTrigger, system_id: int):
        """Find the closest reference point for a single ranged trigger.
        Returns (jumps, ref_name) or None."""
        candidates = []

        if trigger.range_to == RangeAlertType.HOME:
            for green_id in list(self._manager.green_crosshair_ids):
                if green_id >= 0:
                    ref_name = self._manager.solar_systems[green_id].name if green_id in self._manager.solar_systems else "home"
                    candidates.append((green_id, ref_name))
        elif trigger.range_to == RangeAlertType.SYSTEM:
            if trigger.system_id >= 0:
                ref_name = trigger.system_name or "target"
                candidates.append((trigger.system_id, ref_name))
        elif trigger.range_to == RangeAlertType.ANY_CHARACTER:
            for char_name, char_loc in self._char_locations.items():
                if char_loc >= 0:
                    candidates.append((char_loc, char_name))
        elif trigger.range_to == RangeAlertType.ANY_FOLLOWED_CHARACTER:
            for char_name in self._followed_chars:
                char_loc = self._char_locations.get(char_name, -1)
                if char_loc >= 0:
                    candidates.append((char_loc, char_name))

        best = None
        for target_id, ref_name in candidates:
            result = self._check_range_match(trigger, system_id, target_id)
            if result is not None and (best is None or result < best[0]):
                best = (result, ref_name)
        return best

    def _check_range_match(self, trigger: AlertTrigger, system_id: int, target_system: int):
        """Check if system_id is within trigger's range of target_system.
        Returns jump count if in range, None otherwise. Does NOT play sound."""
        path_id = self._manager.generate_unique_path_id(target_system, system_id)
        if path_id not in self._manager.pathfinding_cache:
            result = self._manager.find_path(target_system, system_id)
            if result is None:
                return None
            self._manager.pathfinding_cache[path_id] = result

        path = self._manager.pathfinding_cache[path_id]
        jumps = path.total_jumps

        if jumps < 0:
            return None

        upper_ok = False
        if trigger.upper_limit_operator == RangeAlertOperator.EQUAL:
            upper_ok = (jumps == trigger.upper_range)
        elif trigger.upper_limit_operator == RangeAlertOperator.LESS_THAN_OR_EQUAL:
            upper_ok = (jumps <= trigger.upper_range)
        elif trigger.upper_limit_operator == RangeAlertOperator.LESS_THAN:
            upper_ok = (jumps < trigger.upper_range)

        if not upper_ok:
            return None

        lower_ok = True
        if trigger.lower_range > 0:
            if trigger.lower_limit_operator == RangeAlertOperator.GREATER_THAN_OR_EQUAL:
                lower_ok = (jumps >= trigger.lower_range)
            elif trigger.lower_limit_operator == RangeAlertOperator.GREATER_THAN:
                lower_ok = (jumps > trigger.lower_range)

        if upper_ok and lower_ok:
            return jumps
        return None

    def _play_alert_sound(self, trigger: AlertTrigger):
        if self._mute_sound:
            return
        if trigger.sound_id >= 0:
            if not self._sound_manager.play_sound_by_id(trigger.sound_id):
                # sound_id didn't resolve — try sound_path as fallback
                self._sound_manager.play_custom_sound(trigger.sound_path)
        elif trigger.sound_path:
            self._sound_manager.play_custom_sound(trigger.sound_path)
        else:
            self._sound_manager.play_sound_by_id(0)

    def _on_combat_event(self, filename: str, char_name: str, event_type: int):
        from taco.intel.log_entry import CombatEventType
        if event_type == CombatEventType.START:
            self._write_system_intel(f"Combat started: {char_name}")
        else:
            self._write_system_intel(f"Combat stopped: {char_name}")

    def _on_system_change(self, system_name: str, char_name: str):
        """Handle character system change from local watcher."""
        if not char_name:
            return

        # Always track the character, even before system resolves
        if char_name not in self._char_locations:
            self._char_locations[char_name] = -1

        # Try to find system by name
        sys_id = self._manager.names.get(system_name, -1)

        # Try by native ID if name didn't match
        if sys_id == -1:
            try:
                native_id = int(system_name)
                for sid, system in self._manager.solar_systems.items():
                    if system.native_id == native_id:
                        sys_id = sid
                        break
            except ValueError:
                pass

        if sys_id >= 0:
            self._char_locations[char_name] = sys_id
            self._manager.set_character_location(sys_id)
            if self._config.show_character_locations:
                resolved = [v for v in self._char_locations.values() if v >= 0]
                self._manager.set_character_location_systems(resolved)
            # Update GL widget with only followed characters for icon + label rendering
            self._gl_widget.char_locations = {
                cn: sid for cn, sid in self._char_locations.items()
                if cn in self._followed_chars
            }
            if char_name in self._followed_chars:
                self._gl_widget.pan_to_system(sys_id)
            name = self._manager.solar_systems[sys_id].name if sys_id in self._manager.solar_systems else system_name
            self._write_system_intel(f"{char_name} moved to {name}")
            self._status_bar.showMessage(f"{char_name}: {name}")
        else:
            self._write_system_intel(f"{char_name} detected (system: {system_name})")

    def _write_system_intel(self, text: str):
        time_str = datetime.now().strftime("%H:%M:%S")
        self._tab_widget.write_intel("System", f"[{time_str}] {text}")

    # --- GL Events ---

    def _on_system_clicked(self, system_id: int):
        if system_id in self._manager.solar_systems:
            system = self._manager.solar_systems[system_id]
            self._manager.add_highlight(system_id, flash=True)

            # Toggle sticky highlight
            if system_id in self._sticky_highlights:
                self._sticky_highlights.discard(system_id)
            else:
                self._sticky_highlights.add(system_id)
            self._gl_widget.sticky_highlight_systems = self._sticky_highlights

            stats = self._manager.get_system_stats(system_id)
            info = f"{system.name} (ID: {system_id})"
            if stats and not stats.expired:
                info += f" - Reports: {stats.report_count}"
                age = datetime.now() - stats.last_report
                info += f", Last: {int(age.total_seconds())}s ago"
            self._status_bar.showMessage(info)

    def _on_system_hovered(self, system_id: int, name: str):
        self._status_bar.showMessage(name)

    def _on_system_right_clicked(self, system_id: int, pos):
        menu = QMenu(self)

        if system_id >= 0 and system_id in self._manager.solar_systems:
            system = self._manager.solar_systems[system_id]

            if system_id == self._manager.home_system_id:
                remove_home = menu.addAction(f"Remove Home System")
                remove_home.triggered.connect(self._remove_home_system)
            else:
                set_home = menu.addAction(f"Set Home: {system.name}")
                set_home.triggered.connect(lambda: self._set_home_system(system_id))

            is_monitored = system_id in self._manager.green_crosshair_ids
            if is_monitored and system_id != self._manager.home_system_id:
                unmonitor = menu.addAction(f"Unmonitor {system.name}")
                unmonitor.triggered.connect(lambda: self._unmonitor_system(system_id))
            elif system_id != self._manager.home_system_id:
                monitor = menu.addAction(f"Monitor {system.name}")
                monitor.triggered.connect(lambda: self._monitor_system(system_id))

            zoom_to = menu.addAction(f"Zoom to {system.name}")
            zoom_to.triggered.connect(lambda: self._gl_widget.zoom_to_system(system_id))

            follow = menu.addAction(f"Follow: {system.name}")
            follow.triggered.connect(lambda: self._follow_system(system_id))

            menu.addSeparator()

            ignore = menu.addAction(f"Ignore {system.name}")
            ignore.triggered.connect(lambda: self._add_ignore_system(system_id))

            menu.addSeparator()

        # Map Range From submenu
        range_menu = menu.addMenu("Map Range From")
        range_home = range_menu.addAction("Home System")
        range_home.setCheckable(True)
        range_home.setChecked(self._config.map_range_from == 0)
        range_home.triggered.connect(lambda: self._set_map_range_from(0))
        range_char = range_menu.addAction("Character Location")
        range_char.setCheckable(True)
        range_char.setChecked(self._config.map_range_from == 1)
        range_char.triggered.connect(lambda: self._set_map_range_from(1))

        follow_menu = menu.addMenu("Follow Characters")
        if self._char_locations:
            for char_name in sorted(self._char_locations.keys()):
                action = follow_menu.addAction(char_name)
                action.setCheckable(True)
                action.setChecked(char_name in self._followed_chars)
                action.triggered.connect(lambda checked, cn=char_name: self._toggle_follow_character(cn, checked))
        else:
            no_chars = follow_menu.addAction("(no characters detected)")
            no_chars.setEnabled(False)

        refocus_action = menu.addAction("Refocus")
        refocus_action.triggered.connect(self._refocus_camera)

        mute_action = menu.addAction("Mute Sounds" if not self._mute_sound else "Unmute Sounds")
        mute_action.triggered.connect(lambda: self._on_mute_toggle(not self._mute_sound))

        toggle_labels = menu.addAction("Hide Labels" if self._gl_widget.persistent_labels else "Show Labels")
        toggle_labels.triggered.connect(
            lambda: setattr(self._gl_widget, 'persistent_labels', not self._gl_widget.persistent_labels)
        )

        toggle_panel = menu.addAction("Hide Panel" if self._right_panel.isVisible() else "Show Panel")
        toggle_panel.triggered.connect(self._toggle_panel)

        map_mode_label = "Switch to 2D" if self._config.map_mode == "3d" else "Switch to 3D"
        toggle_map = menu.addAction(map_mode_label)
        toggle_map.triggered.connect(self._toggle_map_mode)

        menu.exec(pos)

    def _set_home_system(self, system_id: int):
        self._manager.set_current_home_system(system_id)
        self._config.home_system_id = system_id
        self._config.save()
        name = self._manager.solar_systems[system_id].name if system_id in self._manager.solar_systems else "?"
        self._write_system_intel(f"Home system set to {name}")

    def _remove_home_system(self):
        self._manager.clear_current_system()
        self._config.home_system_id = -1
        self._config.save()
        self._write_system_intel("Home system removed")

    def _monitor_system(self, system_id: int):
        self._manager.add_green_crosshair(system_id)
        name = self._manager.solar_systems[system_id].name if system_id in self._manager.solar_systems else "?"
        self._write_system_intel(f"Monitoring {name}")

    def _unmonitor_system(self, system_id: int):
        if system_id in self._manager.green_crosshair_ids:
            self._manager.green_crosshair_ids.remove(system_id)
        name = self._manager.solar_systems[system_id].name if system_id in self._manager.solar_systems else "?"
        self._write_system_intel(f"Stopped monitoring {name}")

    def _add_ignore_system(self, system_id: int):
        if system_id not in self._ignore_systems:
            self._ignore_systems.append(system_id)
            self._config.ignore_systems.append(system_id)
            self._config.save()

    # --- Search ---

    def _on_search(self):
        name = self._search_input.text().strip()
        if not name:
            return
        name_lower = name.lower()
        sys_id = -1
        for n, sid in self._manager.names.items():
            if n.lower() == name_lower:
                sys_id = sid
                break
        if sys_id >= 0:
            self._gl_widget.zoom_to_system(sys_id)
            self._manager.add_highlight(sys_id, flash=True)
            self._search_input.clear()
        else:
            self._status_bar.showMessage(f'System "{name}" not found')

    # --- Config events ---

    def _on_config_changed(self):
        self._manager.max_alert_age = self._config.max_alert_age
        self._manager.max_alerts = self._config.max_alerts
        self._gl_widget.show_alert_age = self._config.show_alert_age
        self._gl_widget.display_char_names = self._config.display_character_names
        self._gl_widget.show_char_locations = self._config.show_character_locations
        self._load_config()

    def _on_alerts_changed(self):
        self._alert_triggers = [
            AlertTrigger.from_dict(d) for d in self._config.alert_triggers
        ]

    def _on_channel_added(self, name: str, prefix: str):
        self._tab_widget.add_channel_tab(name, name)
        if self._process_logs:
            log_path = self._config.log_path if self._config.override_log_path else None
            watcher = LogWatcher(prefix, LogFileType.CHAT, log_path)
            watcher.new_log_entry.connect(lambda entry, n=name: self._on_new_log_entry(entry, n))
            watcher.start_watch()
            self._log_watchers[name] = watcher
        self._write_system_intel(f"Custom channel added: {name}")

    def _on_channel_removed(self, name: str):
        if name in self._log_watchers:
            self._log_watchers[name].stop_watch()
            del self._log_watchers[name]
        self._tab_widget.remove_channel_tab(name)
        self._write_system_intel(f"Custom channel removed: {name}")

    def _on_dark_mode_changed(self, dark: bool):
        apply_theme(QApplication.instance(), dark)

    def _on_persistent_labels_changed(self, checked: bool):
        self._gl_widget.persistent_labels = checked

    def _on_map_text_size_changed(self, value: int):
        self._gl_widget.map_text_size = value

    def _on_landmarks_changed(self, landmark_ids: list):
        self._gl_widget.landmark_systems = set(landmark_ids)

    def _on_map_mode_changed(self, mode: str):
        self._manager.set_map_mode(mode)
        self._gl_widget.set_map_mode(mode)

    def _toggle_map_mode(self):
        new_mode = "2d" if self._config.map_mode == "3d" else "3d"
        self._config.map_mode = new_mode
        self._on_map_mode_changed(new_mode)
        # Re-center camera on followed character after coordinate swap
        for char_name in self._followed_chars:
            sys_id = self._char_locations.get(char_name, -1)
            if sys_id >= 0:
                self._gl_widget.pan_to_system(sys_id)
                break

    def _on_mute_toggle(self, muted: bool):
        self._mute_sound = muted
        self._sound_manager.muted = muted

    def _set_map_range_from(self, value: int):
        self._config.map_range_from = value
        label = "Home System" if value == 0 else "Character Location"
        self._write_system_intel(f"Map range from: {label}")

    # --- Panel / Fullscreen ---

    def _toggle_panel(self):
        self._right_panel.setVisible(not self._right_panel.isVisible())

    def _follow_system(self, system_id: int):
        self._gl_widget.zoom_to_system(system_id)
        self._manager.add_highlight(system_id, flash=True)

    def _toggle_follow_character(self, char_name: str, checked: bool):
        if checked:
            self._followed_chars.add(char_name)
            # Zoom to this character's current location if known
            sys_id = self._char_locations.get(char_name, -1)
            if sys_id >= 0:
                self._gl_widget.zoom_to_system(sys_id)
        else:
            self._followed_chars.discard(char_name)
        self._config.camera_follow_character = len(self._followed_chars) > 0
        # Update map to show only followed characters
        self._gl_widget.char_locations = {
            cn: sid for cn, sid in self._char_locations.items()
            if cn in self._followed_chars
        }

    def _refocus_camera(self):
        # Build list of targets: followed characters + home system
        targets = []
        for char_name in sorted(self._followed_chars):
            sys_id = self._char_locations.get(char_name, -1)
            if sys_id >= 0:
                targets.append((sys_id, char_name))
        if self._manager.home_system_id >= 0:
            home = self._manager.home_system_id
            name = self._manager.solar_systems[home].name if home in self._manager.solar_systems else "Home"
            targets.append((home, name))
        if not targets:
            self._status_bar.showMessage("No targets to refocus on")
            return
        self._refocus_index = self._refocus_index % len(targets)
        sys_id, label = targets[self._refocus_index]
        self._gl_widget.zoom_to_system(sys_id)
        self._status_bar.showMessage(f"Refocus: {label}")
        self._refocus_index = (self._refocus_index + 1) % len(targets)

    def _toggle_fullscreen(self):
        if self._is_full_screen:
            self.showNormal()
        else:
            self.showFullScreen()
        self._is_full_screen = not self._is_full_screen

    def _exit_fullscreen(self):
        if self._is_full_screen:
            self._toggle_fullscreen()

    # --- Close ---

    def closeEvent(self, event):
        self._stop_logs()
        self._gl_widget.stop_animation()

        # Save config
        self._config.is_full_screen = self._is_full_screen
        if not self._is_full_screen:
            # Clamp saved position to primary monitor so next launch is always visible
            x, y = self.x(), self.y()
            primary = QApplication.primaryScreen()
            if primary:
                avail = primary.availableGeometry()
                x = max(avail.x(), min(x, avail.x() + avail.width() - self.width()))
                y = max(avail.y(), min(y, avail.y() + avail.height() - self.height()))
            self._config.window_position_x = x
            self._config.window_position_y = y
            self._config.window_size_x = self.width()
            self._config.window_size_y = self.height()

        self._config.camera_distance = self._gl_widget.camera_distance
        self._config.look_at_x = float(self._gl_widget.look_at[0])
        self._config.look_at_y = float(self._gl_widget.look_at[1])

        if self._config.preserve_home_system:
            self._config.home_system_id = self._manager.home_system_id

        # Save monitored systems (green crosshairs, excluding home)
        home_id = self._manager.home_system_id
        self._config.monitored_systems = [
            sid for sid in self._manager.green_crosshair_ids if sid != home_id
        ]

        self._config.selected_systems = list(self._sticky_highlights)
        self._config.save()

        event.accept()

"""Config sub-tabs UI. Ported from MainForm.Designer.cs config section."""
from PyQt6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QCheckBox, QSpinBox, QLineEdit, QPushButton,
    QComboBox, QListWidget, QListWidgetItem, QGroupBox, QFileDialog,
    QMessageBox, QSplitter, QTextEdit, QScrollArea, QCompleter,
)
from PyQt6.QtCore import Qt, pyqtSignal

from taco.config.taco_config import TacoConfig
from taco.core.alert_trigger import (
    AlertTrigger, AlertType, RangeAlertOperator, RangeAlertType,
)
from taco.audio.sound_manager import SOUND_LIST, SoundManager
from taco.intel.log_path_detector import get_default_log_path


class ConfigPanel(QTabWidget):
    config_changed = pyqtSignal()
    alerts_changed = pyqtSignal()
    home_system_changed = pyqtSignal(int)
    channel_added = pyqtSignal(str, str)     # name, prefix
    channel_removed = pyqtSignal(str)        # name
    dark_mode_changed = pyqtSignal(bool)
    persistent_labels_changed = pyqtSignal(bool)
    map_text_size_changed = pyqtSignal(int)
    landmarks_changed = pyqtSignal(list)
    map_mode_changed = pyqtSignal(str)

    def __init__(self, config: TacoConfig, system_names: list[str],
                 system_names_dict: dict[str, int] | None = None,
                 sound_manager: SoundManager | None = None,
                 char_names_func=None, parent=None):
        super().__init__(parent)
        self._config = config
        self._system_names = system_names
        self._system_names_dict = system_names_dict or {}  # name -> system_id
        self._sound_manager = sound_manager
        self._char_names_func = char_names_func  # callable returning list[str]
        self._loading_alerts = False
        self._editing_index = -1  # -1 = not editing

        self._init_channels_tab()
        self._init_alerts_tab()
        self._init_lists_tab()
        self._init_landmarks_tab()
        self._init_misc_tab()
        self._init_info_tab()

    def _init_channels_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Custom channels
        group = QGroupBox("Custom Intel Channels")
        glayout = QVBoxLayout(group)

        self._channel_list = QListWidget()
        for ch in self._config.custom_channels:
            self._channel_list.addItem(f"{ch.get('name', '')} ({ch.get('prefix', '')})")
        glayout.addWidget(self._channel_list)

        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("Name:"))
        self._channel_name_input = QLineEdit()
        self._channel_name_input.setPlaceholderText("e.g. Delve Intel")
        add_row.addWidget(self._channel_name_input)

        add_row.addWidget(QLabel("Prefix:"))
        self._channel_prefix_input = QLineEdit()
        self._channel_prefix_input.setPlaceholderText("e.g. delve.imperium")
        add_row.addWidget(self._channel_prefix_input)
        glayout.addLayout(add_row)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Channel")
        add_btn.clicked.connect(self._on_add_channel)
        btn_row.addWidget(add_btn)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._on_remove_channel)
        btn_row.addWidget(remove_btn)
        glayout.addLayout(btn_row)

        layout.addWidget(group)

        # Game log
        self._monitor_game_log = QCheckBox("Monitor Game Log")
        self._monitor_game_log.setChecked(self._config.monitor_game_log)
        self._monitor_game_log.toggled.connect(self._on_config_changed)
        layout.addWidget(self._monitor_game_log)

        layout.addStretch()
        self.addTab(tab, "Channels")

    def _init_alerts_tab(self):
        # Scroll area so the tab doesn't force a huge minimum size
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)

        # --- Alert list with checkboxes ---
        list_group = QGroupBox("Alert List")
        list_layout = QVBoxLayout(list_group)

        list_row = QHBoxLayout()
        self._alert_list = QListWidget()
        self._alert_list.currentRowChanged.connect(self._on_alert_selection_changed)
        self._alert_list.itemChanged.connect(self._on_alert_item_checked)
        list_row.addWidget(self._alert_list)

        # Move up/down buttons
        move_col = QVBoxLayout()
        move_col.addStretch()
        self._move_up_btn = QPushButton("\u25B2")
        self._move_up_btn.setFixedSize(28, 28)
        self._move_up_btn.setToolTip("Move Up")
        self._move_up_btn.clicked.connect(self._on_move_alert_up)
        move_col.addWidget(self._move_up_btn)
        self._move_down_btn = QPushButton("\u25BC")
        self._move_down_btn.setFixedSize(28, 28)
        self._move_down_btn.setToolTip("Move Down")
        self._move_down_btn.clicked.connect(self._on_move_alert_down)
        move_col.addWidget(self._move_down_btn)
        move_col.addStretch()
        list_row.addLayout(move_col)
        list_layout.addLayout(list_row)

        # Action buttons row
        action_row = QHBoxLayout()
        self._play_alert_btn = QPushButton("Play Selected")
        self._play_alert_btn.setEnabled(False)
        self._play_alert_btn.clicked.connect(self._on_play_selected_alert)
        action_row.addWidget(self._play_alert_btn)

        self._edit_alert_btn = QPushButton("Edit Selected")
        self._edit_alert_btn.setEnabled(False)
        self._edit_alert_btn.clicked.connect(self._on_edit_selected_alert)
        action_row.addWidget(self._edit_alert_btn)

        self._cancel_edit_btn = QPushButton("Cancel Edit")
        self._cancel_edit_btn.setVisible(False)
        self._cancel_edit_btn.clicked.connect(self._on_cancel_edit)
        action_row.addWidget(self._cancel_edit_btn)

        self._remove_alert_btn = QPushButton("Remove Selected")
        self._remove_alert_btn.setEnabled(False)
        self._remove_alert_btn.clicked.connect(self._on_remove_alert)
        action_row.addWidget(self._remove_alert_btn)
        list_layout.addLayout(action_row)

        layout.addWidget(list_group)

        # --- Add Range Based Alert ---
        self._range_group = QGroupBox("Add Range Based Alert")
        rlayout = QVBoxLayout(self._range_group)

        # Row 1: upper_op  value  "jumps and"  lower_op  value
        range_row1 = QHBoxLayout()
        self._upper_op = QComboBox()
        self._upper_op.addItems(["=", "<="])
        self._upper_op.setCurrentIndex(1)
        self._upper_op.currentIndexChanged.connect(self._on_upper_op_changed)
        range_row1.addWidget(self._upper_op)
        self._upper_range = QSpinBox()
        self._upper_range.setRange(0, 50)
        self._upper_range.setValue(3)
        range_row1.addWidget(self._upper_range)
        range_row1.addWidget(QLabel("jumps and"))
        self._lower_op = QComboBox()
        self._lower_op.addItems([">", ">="])
        self._lower_op.setEnabled(False)
        range_row1.addWidget(self._lower_op)
        self._lower_range = QSpinBox()
        self._lower_range.setRange(0, 50)
        self._lower_range.setEnabled(False)
        range_row1.addWidget(self._lower_range)
        range_row1.addWidget(QLabel("from:"))
        rlayout.addLayout(range_row1)

        # Row 2: range type + select system/character
        range_row2 = QHBoxLayout()
        self._range_type = QComboBox()
        self._range_type.addItems(["Home System", "Any Character",
                                   "Any Followed Character",
                                   "Single System", "Single Character"])
        self._range_type.currentIndexChanged.connect(self._on_range_type_changed)
        range_row2.addWidget(self._range_type)

        self._range_system = QComboBox()
        self._range_system.setEditable(True)
        self._range_system.addItems(self._system_names)
        self._range_system.setEnabled(False)
        self._range_system.setVisible(False)
        range_row2.addWidget(self._range_system)

        self._range_character = QComboBox()
        self._range_character.setEnabled(False)
        self._range_character.setVisible(False)
        range_row2.addWidget(self._range_character)

        self._range_na_label = QLabel("N/A")
        self._range_na_label.setEnabled(False)
        range_row2.addWidget(self._range_na_label)
        rlayout.addLayout(range_row2)

        # Row 3: Sound + Add/Save
        range_row3 = QHBoxLayout()
        self._range_play_btn = QPushButton("Play")
        self._range_play_btn.setFixedWidth(40)
        self._range_play_btn.clicked.connect(self._on_play_range_sound)
        range_row3.addWidget(self._range_play_btn)
        self._range_sound = QComboBox()
        self._range_sound.addItems(SOUND_LIST + ["Custom..."])
        self._range_sound.setCurrentIndex(3)
        self._range_sound.currentIndexChanged.connect(self._on_range_sound_changed)
        range_row3.addWidget(self._range_sound)
        self._add_range_btn = QPushButton("Add")
        self._add_range_btn.clicked.connect(self._on_add_range_alert)
        range_row3.addWidget(self._add_range_btn)
        self._save_range_btn = QPushButton("Save")
        self._save_range_btn.setVisible(False)
        self._save_range_btn.clicked.connect(self._on_save_range_alert)
        range_row3.addWidget(self._save_range_btn)
        rlayout.addLayout(range_row3)

        layout.addWidget(self._range_group)

        # --- Add Custom Text Alert ---
        self._custom_group = QGroupBox("Add Custom Text Alert")
        clayout = QVBoxLayout(self._custom_group)

        # Row 1: trigger text + repeat interval
        custom_row1 = QHBoxLayout()
        custom_row1.addWidget(QLabel("Trigger:"))
        self._custom_text = QLineEdit()
        custom_row1.addWidget(self._custom_text)
        custom_row1.addWidget(QLabel("every"))
        self._custom_interval = QSpinBox()
        self._custom_interval.setRange(0, 999)
        self._custom_interval.setValue(0)
        custom_row1.addWidget(self._custom_interval)
        custom_row1.addWidget(QLabel("secs"))
        clayout.addLayout(custom_row1)

        # Row 2: Sound + Add/Save
        custom_row2 = QHBoxLayout()
        self._custom_play_btn = QPushButton("Play")
        self._custom_play_btn.setFixedWidth(40)
        self._custom_play_btn.clicked.connect(self._on_play_custom_sound)
        custom_row2.addWidget(self._custom_play_btn)
        self._custom_sound = QComboBox()
        self._custom_sound.addItems(SOUND_LIST + ["Custom..."])
        self._custom_sound.setCurrentIndex(3)
        self._custom_sound.currentIndexChanged.connect(self._on_custom_sound_changed)
        custom_row2.addWidget(self._custom_sound)
        self._add_custom_btn = QPushButton("Add")
        self._add_custom_btn.clicked.connect(self._on_add_custom_alert)
        custom_row2.addWidget(self._add_custom_btn)
        self._save_custom_btn = QPushButton("Save")
        self._save_custom_btn.setVisible(False)
        self._save_custom_btn.clicked.connect(self._on_save_custom_alert)
        custom_row2.addWidget(self._save_custom_btn)
        clayout.addLayout(custom_row2)

        layout.addWidget(self._custom_group)

        scroll.setWidget(inner)
        self.addTab(scroll, "Alerts")
        self._refresh_alert_list()

    def _init_lists_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Ignore strings
        group = QGroupBox("Ignore Strings")
        glayout = QVBoxLayout(group)
        self._ignore_strings_edit = QTextEdit()
        self._ignore_strings_edit.setPlainText('\n'.join(self._config.ignore_strings))
        self._ignore_strings_edit.setMaximumHeight(100)
        glayout.addWidget(self._ignore_strings_edit)

        save_btn = QPushButton("Save Ignore Strings")
        save_btn.clicked.connect(self._save_ignore_strings)
        glayout.addWidget(save_btn)
        layout.addWidget(group)

        # Ignore systems
        group2 = QGroupBox("Ignore Systems (IDs)")
        glayout2 = QVBoxLayout(group2)
        self._ignore_systems_edit = QTextEdit()
        self._ignore_systems_edit.setPlainText(
            '\n'.join(str(s) for s in self._config.ignore_systems))
        self._ignore_systems_edit.setMaximumHeight(100)
        glayout2.addWidget(self._ignore_systems_edit)

        save_btn2 = QPushButton("Save Ignore Systems")
        save_btn2.clicked.connect(self._save_ignore_systems)
        glayout2.addWidget(save_btn2)
        layout.addWidget(group2)

        layout.addStretch()
        self.addTab(tab, "Lists")

    def _init_landmarks_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Landmark Systems (always-visible labels)")
        glayout = QVBoxLayout(group)

        # Build reverse lookup: system_id -> name
        self._id_to_name: dict[int, str] = {v: k for k, v in self._system_names_dict.items()}

        self._landmark_list = QListWidget()
        for sys_id in self._config.landmark_systems:
            name = self._id_to_name.get(sys_id, f"Unknown ({sys_id})")
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, sys_id)
            self._landmark_list.addItem(item)
        glayout.addWidget(self._landmark_list)

        add_row = QHBoxLayout()
        self._landmark_input = QLineEdit()
        self._landmark_input.setPlaceholderText("Search system name...")
        completer = QCompleter(self._system_names)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._landmark_input.setCompleter(completer)
        add_row.addWidget(self._landmark_input)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._on_add_landmark)
        add_row.addWidget(add_btn)
        glayout.addLayout(add_row)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._on_remove_landmark)
        glayout.addWidget(remove_btn)

        layout.addWidget(group)
        layout.addStretch()
        self.addTab(tab, "Landmarks")

    def _on_add_landmark(self):
        text = self._landmark_input.text().strip()
        if not text:
            return
        # Case-insensitive lookup
        sys_id = -1
        for name, sid in self._system_names_dict.items():
            if name.lower() == text.lower():
                sys_id = sid
                text = name  # use canonical name
                break
        if sys_id < 0:
            QMessageBox.warning(self, "Not Found", f'System "{text}" not found.')
            return
        if sys_id in self._config.landmark_systems:
            QMessageBox.warning(self, "Duplicate", f"{text} is already a landmark.")
            return
        self._config.landmark_systems.append(sys_id)
        self._config.save()
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, sys_id)
        self._landmark_list.addItem(item)
        self._landmark_input.clear()
        self.landmarks_changed.emit(list(self._config.landmark_systems))

    def _on_remove_landmark(self):
        row = self._landmark_list.currentRow()
        if row < 0:
            return
        self._config.landmark_systems.pop(row)
        self._config.save()
        self._landmark_list.takeItem(row)
        self.landmarks_changed.emit(list(self._config.landmark_systems))

    def _init_misc_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Display options
        group = QGroupBox("Display")
        glayout = QVBoxLayout(group)

        # Map mode toggle (prominent placement at top)
        map_mode_row = QHBoxLayout()
        map_mode_row.addWidget(QLabel("Map Mode:"))
        self._map_mode_combo = QComboBox()
        self._map_mode_combo.addItems(["3D Projection", "2D Schematic"])
        self._map_mode_combo.setCurrentIndex(0 if self._config.map_mode == "3d" else 1)
        self._map_mode_combo.currentIndexChanged.connect(self._on_map_mode_changed)
        map_mode_row.addWidget(self._map_mode_combo)
        glayout.addLayout(map_mode_row)

        self._show_alert_age = QCheckBox("Show Alert Age")
        self._show_alert_age.setChecked(self._config.show_alert_age)
        self._show_alert_age.toggled.connect(self._on_config_changed)
        glayout.addWidget(self._show_alert_age)

        self._display_char_names = QCheckBox("Display Character Names")
        self._display_char_names.setChecked(self._config.display_character_names)
        self._display_char_names.toggled.connect(self._on_config_changed)
        glayout.addWidget(self._display_char_names)

        self._show_char_locations = QCheckBox("Show Character Locations")
        self._show_char_locations.setChecked(self._config.show_character_locations)
        self._show_char_locations.toggled.connect(self._on_config_changed)
        glayout.addWidget(self._show_char_locations)

        self._persistent_labels = QCheckBox("Persistent System Labels")
        self._persistent_labels.setChecked(self._config.persistent_system_labels)
        self._persistent_labels.toggled.connect(self._on_persistent_labels_changed)
        glayout.addWidget(self._persistent_labels)

        self._dark_mode = QCheckBox("Dark Mode")
        self._dark_mode.setChecked(self._config.dark_mode)
        self._dark_mode.toggled.connect(self._on_dark_mode_changed)
        glayout.addWidget(self._dark_mode)

        row = QHBoxLayout()
        row.addWidget(QLabel("Map Text Size:"))
        self._map_text_size = QSpinBox()
        self._map_text_size.setRange(4, 24)
        self._map_text_size.setValue(self._config.map_text_size)
        self._map_text_size.valueChanged.connect(self._on_map_text_size_changed)
        row.addWidget(self._map_text_size)
        glayout.addLayout(row)

        layout.addWidget(group)

        # Alert limits
        group2 = QGroupBox("Limits")
        glayout2 = QGridLayout(group2)

        glayout2.addWidget(QLabel("Max Alert Age (min):"), 0, 0)
        self._max_alert_age = QSpinBox()
        self._max_alert_age.setRange(0, 120)
        self._max_alert_age.setValue(self._config.max_alert_age)
        self._max_alert_age.valueChanged.connect(self._on_config_changed)
        glayout2.addWidget(self._max_alert_age, 0, 1)

        glayout2.addWidget(QLabel("Max Alerts:"), 1, 0)
        self._max_alerts = QSpinBox()
        self._max_alerts.setRange(1, 100)
        self._max_alerts.setValue(self._config.max_alerts)
        self._max_alerts.valueChanged.connect(self._on_config_changed)
        glayout2.addWidget(self._max_alerts, 1, 1)

        layout.addWidget(group2)

        # Log path override
        group3 = QGroupBox("Log Path")
        glayout3 = QVBoxLayout(group3)
        self._override_log_path = QCheckBox("Override Log Path")
        self._override_log_path.setChecked(self._config.override_log_path)
        glayout3.addWidget(self._override_log_path)

        override_active = self._config.override_log_path
        display_path = (self._config.log_path
                        if override_active and self._config.log_path
                        else get_default_log_path())

        path_row = QHBoxLayout()
        self._log_path_input = QLineEdit(display_path)
        self._log_path_input.setReadOnly(not override_active)
        path_row.addWidget(self._log_path_input)
        self._browse_btn = QPushButton("Browse")
        self._browse_btn.setEnabled(override_active)
        self._browse_btn.clicked.connect(self._browse_log_path)
        path_row.addWidget(self._browse_btn)
        glayout3.addLayout(path_row)

        self._override_log_path.toggled.connect(self._on_override_toggled)

        layout.addWidget(group3)

        # Profile export/import
        profile_group = QGroupBox("Profile")
        profile_layout = QHBoxLayout(profile_group)
        export_btn = QPushButton("Export Profile...")
        export_btn.clicked.connect(self._on_export_profile)
        profile_layout.addWidget(export_btn)
        import_btn = QPushButton("Import Profile...")
        import_btn.clicked.connect(self._on_import_profile)
        profile_layout.addWidget(import_btn)
        layout.addWidget(profile_group)

        layout.addStretch()
        scroll.setWidget(tab)
        self.addTab(scroll, "Misc")

    def _init_info_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        for text in (
            #Sulten says hi!
            #Need to build out with a better user manual
            "T.A.C.O. Twosday: Python Edition v2.1.0",
            "Code port and additional development by Sulten",
            "Python Port using PyQt6 + PyOpenGL",
            "~~~~~~~~",
            "Enhancements:", 
            "- Updated static 3d map and created 2d map option",
            "- Users can export and import their profiles",
            "- Added user defined landmarks",
            "- Added region names",
            "- And many QOL improvements",
            "I am actively maintaining this project, if you have ideas on how to improve T.A.C.O Twosday please let me know",
            "~~~~~~~~~",

            "If you appreciate this project, I gratefully accept ISK",
            "Enjoy!  ~Sulten",

            "~~~~~~~~",


            "Original C# version by the McNubblet",
            "Python port for cross-platform Linux/Windows support",

            "~~~~~~~~",
            
            "Controls",
            "Right Click on the map opens the primary control menu",
            "Left click to pan map and select star systems",


        ):
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            layout.addWidget(lbl)
        layout.addStretch()
        self.addTab(tab, "Info")

    # --- Handlers ---

    def _on_config_changed(self):
        self._config.monitor_game_log = self._monitor_game_log.isChecked()
        self._config.show_alert_age = self._show_alert_age.isChecked()
        self._config.display_character_names = self._display_char_names.isChecked()
        self._config.show_character_locations = self._show_char_locations.isChecked()
        self._config.max_alert_age = self._max_alert_age.value()
        self._config.max_alerts = self._max_alerts.value()
        self._config.override_log_path = self._override_log_path.isChecked()
        self._config.log_path = self._log_path_input.text()
        self._config.save()
        self.config_changed.emit()

    def _on_add_channel(self):
        name = self._channel_name_input.text().strip()
        prefix = self._channel_prefix_input.text().strip().lower()
        if not name or not prefix:
            QMessageBox.warning(self, "Invalid Input", "Enter both name and prefix.")
            return

        for ch in self._config.custom_channels:
            if ch.get("name") == name:
                QMessageBox.warning(self, "Duplicate", "Channel already exists.")
                return

        short_name = name[:3].lower() if len(name) >= 3 else name.lower()
        channel = {
            "name": name, "prefix": prefix,
            "monitor": True, "alert": True, "short_name": short_name
        }
        self._config.custom_channels.append(channel)
        self._config.save()

        self._channel_list.addItem(f"{name} ({prefix})")
        self._channel_name_input.clear()
        self._channel_prefix_input.clear()
        self.channel_added.emit(name, prefix)

    def _on_remove_channel(self):
        row = self._channel_list.currentRow()
        if row < 0:
            return
        name = self._config.custom_channels[row].get("name", "")
        self._config.custom_channels.pop(row)
        self._config.save()
        self._channel_list.takeItem(row)
        self.channel_removed.emit(name)

    # --- Alert list management ---

    def _refresh_alert_list(self):
        self._loading_alerts = True
        self._alert_list.clear()
        for trigger_dict in self._config.alert_triggers:
            t = AlertTrigger.from_dict(trigger_dict)
            item = QListWidgetItem(str(t))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if t.enabled else Qt.CheckState.Unchecked
            )
            self._alert_list.addItem(item)
        self._loading_alerts = False

    def _write_alert_config(self):
        self._config.save()
        self.alerts_changed.emit()

    def _on_alert_selection_changed(self, row: int):
        has_sel = row >= 0
        self._play_alert_btn.setEnabled(has_sel)
        self._edit_alert_btn.setEnabled(has_sel and self._editing_index < 0)
        self._remove_alert_btn.setEnabled(has_sel and self._editing_index < 0)

    def _on_alert_item_checked(self, item: QListWidgetItem):
        if self._loading_alerts:
            return
        row = self._alert_list.row(item)
        if 0 <= row < len(self._config.alert_triggers):
            checked = item.checkState() == Qt.CheckState.Checked
            self._config.alert_triggers[row]["enabled"] = checked
            self._write_alert_config()

    def _on_move_alert_up(self):
        row = self._alert_list.currentRow()
        if row <= 0:
            return
        lst = self._config.alert_triggers
        lst[row - 1], lst[row] = lst[row], lst[row - 1]
        self._write_alert_config()
        self._refresh_alert_list()
        self._alert_list.setCurrentRow(row - 1)

    def _on_move_alert_down(self):
        row = self._alert_list.currentRow()
        lst = self._config.alert_triggers
        if row < 0 or row >= len(lst) - 1:
            return
        lst[row], lst[row + 1] = lst[row + 1], lst[row]
        self._write_alert_config()
        self._refresh_alert_list()
        self._alert_list.setCurrentRow(row + 1)

    def _on_play_selected_alert(self):
        row = self._alert_list.currentRow()
        if row < 0 or not self._sound_manager:
            return
        t = AlertTrigger.from_dict(self._config.alert_triggers[row])
        if t.sound_id >= 0:
            if not self._sound_manager.play_sound_by_id(t.sound_id):
                self._sound_manager.play_custom_sound(t.sound_path)
        elif t.sound_path:
            self._sound_manager.play_custom_sound(t.sound_path)

    def _on_remove_alert(self):
        row = self._alert_list.currentRow()
        if 0 <= row < len(self._config.alert_triggers):
            self._config.alert_triggers.pop(row)
            self._write_alert_config()
            self._refresh_alert_list()

    # --- Edit mode ---

    def _on_edit_selected_alert(self):
        row = self._alert_list.currentRow()
        if row < 0:
            return
        self._editing_index = row
        t = AlertTrigger.from_dict(self._config.alert_triggers[row])

        # Disable list interaction during edit
        self._alert_list.setEnabled(False)
        self._remove_alert_btn.setEnabled(False)
        self._play_alert_btn.setEnabled(False)
        self._move_up_btn.setEnabled(False)
        self._move_down_btn.setEnabled(False)
        self._edit_alert_btn.setVisible(False)
        self._cancel_edit_btn.setVisible(True)

        if t.type == AlertType.RANGED:
            self._custom_group.setEnabled(False)
            self._add_range_btn.setVisible(False)
            self._save_range_btn.setVisible(True)
            # Populate range fields
            self._upper_op.setCurrentIndex(
                1 if t.upper_limit_operator == RangeAlertOperator.LESS_THAN_OR_EQUAL else 0
            )
            self._upper_range.setValue(t.upper_range)
            if t.upper_limit_operator == RangeAlertOperator.LESS_THAN_OR_EQUAL:
                self._lower_op.setEnabled(True)
                self._lower_range.setEnabled(True)
                lo_idx = 1 if t.lower_limit_operator == RangeAlertOperator.GREATER_THAN_OR_EQUAL else 0
                self._lower_op.setCurrentIndex(lo_idx)
                self._lower_range.setValue(t.lower_range)
            # Range type
            type_map = {
                RangeAlertType.HOME: 0, RangeAlertType.ANY_CHARACTER: 1,
                RangeAlertType.ANY_FOLLOWED_CHARACTER: 2,
                RangeAlertType.SYSTEM: 3, RangeAlertType.CHARACTER: 4,
            }
            idx = type_map.get(t.range_to, 0)
            self._range_type.setCurrentIndex(idx)
            if t.range_to == RangeAlertType.SYSTEM and t.system_name:
                si = self._range_system.findText(t.system_name)
                if si >= 0:
                    self._range_system.setCurrentIndex(si)
                else:
                    self._range_system.setEditText(t.system_name)
            elif t.range_to == RangeAlertType.CHARACTER and t.character_name:
                ci = self._range_character.findText(t.character_name)
                if ci >= 0:
                    self._range_character.setCurrentIndex(ci)
            # Sound
            self._set_sound_combo(self._range_sound, t.sound_id, t.sound_path)
        else:
            self._range_group.setEnabled(False)
            self._add_custom_btn.setVisible(False)
            self._save_custom_btn.setVisible(True)
            self._custom_text.setText(t.text)
            self._custom_interval.setValue(t.repeat_interval)
            self._set_sound_combo(self._custom_sound, t.sound_id, t.sound_path)

    def _on_cancel_edit(self):
        self._editing_index = -1
        self._exit_edit_mode()

    def _exit_edit_mode(self):
        self._alert_list.setEnabled(True)
        self._move_up_btn.setEnabled(True)
        self._move_down_btn.setEnabled(True)
        self._edit_alert_btn.setVisible(True)
        self._cancel_edit_btn.setVisible(False)

        # Range group
        self._range_group.setEnabled(True)
        self._add_range_btn.setVisible(True)
        self._save_range_btn.setVisible(False)
        self._reset_range_fields()

        # Custom group
        self._custom_group.setEnabled(True)
        self._add_custom_btn.setVisible(True)
        self._save_custom_btn.setVisible(False)
        self._reset_custom_fields()

        self._on_alert_selection_changed(self._alert_list.currentRow())

    def _reset_range_fields(self):
        self._upper_op.setCurrentIndex(1)
        self._upper_range.setValue(3)
        self._lower_op.setCurrentIndex(0)
        self._lower_op.setEnabled(False)
        self._lower_range.setValue(0)
        self._lower_range.setEnabled(False)
        self._range_type.setCurrentIndex(0)
        self._range_sound.setCurrentIndex(3)
        # Reset custom entry if present
        last = self._range_sound.count() - 1
        if self._range_sound.itemText(last) != "Custom...":
            self._range_sound.removeItem(last)

    def _reset_custom_fields(self):
        self._custom_text.clear()
        self._custom_interval.setValue(0)
        self._custom_sound.setCurrentIndex(3)
        last = self._custom_sound.count() - 1
        if self._custom_sound.itemText(last) != "Custom...":
            self._custom_sound.removeItem(last)

    # --- Range type / operator helpers ---

    def _on_upper_op_changed(self, index: int):
        # index 0 = "=", index 1 = "<="
        enabled = (index == 1)
        self._lower_op.setEnabled(enabled)
        self._lower_range.setEnabled(enabled)
        if not enabled:
            self._lower_op.setCurrentIndex(0)
            self._lower_range.setValue(0)

    def _on_range_type_changed(self, index: int):
        # 0=Home, 1=Any Char, 2=Any Followed Char, 3=Single System, 4=Single Character
        self._range_system.setVisible(index == 3)
        self._range_system.setEnabled(index == 3)
        self._range_character.setVisible(index == 4)
        self._range_character.setEnabled(index == 4)
        self._range_na_label.setVisible(index < 3)
        if index == 4:
            self._refresh_character_list()

    def _refresh_character_list(self):
        self._range_character.clear()
        if self._char_names_func:
            names = self._char_names_func()
            if names:
                self._range_character.addItems(names)

    # --- Sound combo helpers ---

    def _sound_combo_items(self):
        return SOUND_LIST + ["Custom..."]

    def _set_sound_combo(self, combo: QComboBox, sound_id: int, sound_path: str):
        combo.blockSignals(True)
        if sound_id >= 0 and sound_id < len(SOUND_LIST):
            combo.setCurrentIndex(sound_id)
        elif sound_path:
            # Add custom path as second-to-last item (before "Custom...")
            last = combo.count() - 1
            if combo.itemText(last) == "Custom...":
                combo.insertItem(last, sound_path)
                combo.setCurrentIndex(last)
            else:
                combo.setItemText(last, sound_path)
                combo.setCurrentIndex(last)
        combo.blockSignals(False)

    def _on_range_sound_changed(self, index: int):
        self._handle_custom_sound_pick(self._range_sound, index)

    def _on_custom_sound_changed(self, index: int):
        self._handle_custom_sound_pick(self._custom_sound, index)

    def _handle_custom_sound_pick(self, combo: QComboBox, index: int):
        if combo.itemText(index) != "Custom...":
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Sound File", "", "Sound Files (*.wav *.mp3);;All Files (*)"
        )
        # Block signals while modifying the combo to prevent re-triggering
        # (insertItem shifts "Custom..." to a new index, which fires
        # currentIndexChanged and would reopen the file dialog)
        combo.blockSignals(True)
        if path:
            combo.insertItem(index, path)
            combo.setCurrentIndex(index)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _get_sound_from_combo(self, combo: QComboBox):
        """Return (sound_id, sound_path) from a sound combo box."""
        index = combo.currentIndex()
        text = combo.currentText()
        if text == "Custom...":
            return -1, ""
        if index < len(SOUND_LIST):
            return index, SOUND_LIST[index]
        # Custom file path entry
        return -1, text

    def _on_play_range_sound(self):
        if not self._sound_manager:
            return
        sid, spath = self._get_sound_from_combo(self._range_sound)
        if sid >= 0:
            self._sound_manager.play_sound_by_id(sid)
        elif spath:
            self._sound_manager.play_custom_sound(spath)

    def _on_play_custom_sound(self):
        if not self._sound_manager:
            return
        sid, spath = self._get_sound_from_combo(self._custom_sound)
        if sid >= 0:
            self._sound_manager.play_sound_by_id(sid)
        elif spath:
            self._sound_manager.play_custom_sound(spath)

    # --- Add / Save range alert ---

    def _build_range_trigger(self) -> AlertTrigger | None:
        """Build an AlertTrigger from the range form fields, or None on validation failure."""
        upper_op_idx = self._upper_op.currentIndex()
        upper_op = (RangeAlertOperator.EQUAL if upper_op_idx == 0
                    else RangeAlertOperator.LESS_THAN_OR_EQUAL)
        lower_op = RangeAlertOperator.GREATER_THAN_OR_EQUAL
        lower_val = 0
        if upper_op == RangeAlertOperator.LESS_THAN_OR_EQUAL:
            lower_op = (RangeAlertOperator.GREATER_THAN if self._lower_op.currentIndex() == 0
                        else RangeAlertOperator.GREATER_THAN_OR_EQUAL)
            lower_val = self._lower_range.value()

        type_idx = self._range_type.currentIndex()
        range_to = [RangeAlertType.HOME, RangeAlertType.ANY_CHARACTER,
                    RangeAlertType.ANY_FOLLOWED_CHARACTER,
                    RangeAlertType.SYSTEM, RangeAlertType.CHARACTER][type_idx]

        system_id = -1
        system_name = ""
        character_name = ""

        if range_to == RangeAlertType.SYSTEM:
            sys_text = self._range_system.currentText().strip()
            if not sys_text:
                QMessageBox.warning(self, "Validation", "Select a system.")
                return None
            # Look up system name case-insensitively
            sys_lower = sys_text.lower()
            for n, sid in self._system_names_dict.items():
                if n.lower() == sys_lower:
                    system_name = n
                    system_id = sid
                    break
            else:
                QMessageBox.warning(self, "Validation",
                                    f'System "{sys_text}" not found.')
                return None
        elif range_to == RangeAlertType.CHARACTER:
            character_name = self._range_character.currentText().strip()
            if not character_name:
                QMessageBox.warning(self, "Validation", "Select a character.")
                return None

        sound_id, sound_path = self._get_sound_from_combo(self._range_sound)
        if sound_id < 0 and not sound_path:
            QMessageBox.warning(self, "Validation", "Select a sound.")
            return None

        return AlertTrigger(
            type=AlertType.RANGED,
            upper_limit_operator=upper_op,
            upper_range=self._upper_range.value(),
            lower_limit_operator=lower_op,
            lower_range=lower_val,
            range_to=range_to,
            system_id=system_id,
            system_name=system_name,
            character_name=character_name,
            sound_id=sound_id,
            sound_path=sound_path,
            enabled=True,
        )

    def _on_add_range_alert(self):
        trigger = self._build_range_trigger()
        if trigger is None:
            return
        self._config.alert_triggers.append(trigger.to_dict())
        self._write_alert_config()
        self._refresh_alert_list()
        self._reset_range_fields()

    def _on_save_range_alert(self):
        trigger = self._build_range_trigger()
        if trigger is None:
            return
        row = self._editing_index
        if 0 <= row < len(self._config.alert_triggers):
            # Preserve enabled state from original
            trigger.enabled = self._config.alert_triggers[row].get("enabled", True)
            self._config.alert_triggers[row] = trigger.to_dict()
            self._write_alert_config()
            self._refresh_alert_list()
            self._alert_list.setCurrentRow(row)
        self._editing_index = -1
        self._exit_edit_mode()

    # --- Add / Save custom alert ---

    def _build_custom_trigger(self) -> AlertTrigger | None:
        text = self._custom_text.text().strip()
        if not text:
            QMessageBox.warning(self, "Validation", "Enter trigger text.")
            return None
        sound_id, sound_path = self._get_sound_from_combo(self._custom_sound)
        if sound_id < 0 and not sound_path:
            QMessageBox.warning(self, "Validation", "Select a sound.")
            return None
        return AlertTrigger(
            type=AlertType.CUSTOM,
            text=text,
            repeat_interval=self._custom_interval.value(),
            sound_id=sound_id,
            sound_path=sound_path,
            enabled=True,
        )

    def _on_add_custom_alert(self):
        trigger = self._build_custom_trigger()
        if trigger is None:
            return
        self._config.alert_triggers.append(trigger.to_dict())
        self._write_alert_config()
        self._refresh_alert_list()
        self._reset_custom_fields()

    def _on_save_custom_alert(self):
        trigger = self._build_custom_trigger()
        if trigger is None:
            return
        row = self._editing_index
        if 0 <= row < len(self._config.alert_triggers):
            trigger.enabled = self._config.alert_triggers[row].get("enabled", True)
            self._config.alert_triggers[row] = trigger.to_dict()
            self._write_alert_config()
            self._refresh_alert_list()
            self._alert_list.setCurrentRow(row)
        self._editing_index = -1
        self._exit_edit_mode()

    def _save_ignore_strings(self):
        text = self._ignore_strings_edit.toPlainText()
        self._config.ignore_strings = [s.strip() for s in text.split('\n') if s.strip()]
        self._config.save()

    def _save_ignore_systems(self):
        text = self._ignore_systems_edit.toPlainText()
        systems = []
        for s in text.split('\n'):
            s = s.strip()
            if s.isdigit():
                systems.append(int(s))
        self._config.ignore_systems = systems
        self._config.save()

    def _on_override_toggled(self, checked: bool):
        self._log_path_input.setReadOnly(not checked)
        self._browse_btn.setEnabled(checked)
        if not checked:
            self._log_path_input.setText(get_default_log_path())
        self._on_config_changed()

    def _browse_log_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select EVE Log Directory")
        if path:
            self._log_path_input.setText(path)
            self._on_config_changed()

    def _on_dark_mode_changed(self, checked: bool):
        self._config.dark_mode = checked
        self._config.save()
        self.dark_mode_changed.emit(checked)

    def _on_persistent_labels_changed(self, checked: bool):
        self._config.persistent_system_labels = checked
        self._config.save()
        self.persistent_labels_changed.emit(checked)

    def _on_map_text_size_changed(self, value: int):
        self._config.map_text_size = value
        self._config.save()
        self.map_text_size_changed.emit(value)

    def _on_map_mode_changed(self, index: int):
        mode = "3d" if index == 0 else "2d"
        self._config.map_mode = mode
        self._config.save()
        self.map_mode_changed.emit(mode)

    # --- Profile export / import ---

    def _on_export_profile(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Profile", "taco_profile.json",
            "JSON Files (*.json);;All Files (*)")
        if not path:
            return
        try:
            self._config.export_profile(path)
            QMessageBox.information(self, "Export", "Profile exported successfully.")
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", str(exc))

    def _on_import_profile(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Profile", "",
            "JSON Files (*.json);;All Files (*)")
        if not path:
            return
        old_channels = {ch.get("name", "") for ch in self._config.custom_channels}
        try:
            imported = self._config.import_profile(path)
        except Exception as exc:
            QMessageBox.warning(self, "Import Failed", str(exc))
            return
        self._refresh_widgets()
        self.config_changed.emit()
        self.alerts_changed.emit()
        self.dark_mode_changed.emit(self._config.dark_mode)
        self.persistent_labels_changed.emit(self._config.persistent_system_labels)
        self.map_text_size_changed.emit(self._config.map_text_size)
        self.landmarks_changed.emit(list(self._config.landmark_systems))
        self.map_mode_changed.emit(self._config.map_mode)
        # Sync channel tabs: remove old, add new
        new_channels = {ch.get("name", ""): ch.get("prefix", "")
                        for ch in self._config.custom_channels}
        for name in old_channels - new_channels.keys():
            self.channel_removed.emit(name)
        for name, prefix in new_channels.items():
            if name not in old_channels:
                self.channel_added.emit(name, prefix)
        QMessageBox.information(
            self, "Import", f"Imported {len(imported)} settings successfully.")

    def _refresh_widgets(self):
        """Re-read all widget values from config after an import."""
        cfg = self._config

        # Channels tab
        self._channel_list.clear()
        for ch in cfg.custom_channels:
            self._channel_list.addItem(f"{ch.get('name', '')} ({ch.get('prefix', '')})")
        self._monitor_game_log.setChecked(cfg.monitor_game_log)

        # Alerts tab
        self._refresh_alert_list()

        # Lists tab
        self._ignore_strings_edit.setPlainText('\n'.join(cfg.ignore_strings))
        self._ignore_systems_edit.setPlainText(
            '\n'.join(str(s) for s in cfg.ignore_systems))

        # Landmarks tab
        self._landmark_list.clear()
        for sys_id in cfg.landmark_systems:
            name = next((n for n, sid in self._system_names_dict.items()
                         if sid == sys_id), str(sys_id))
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, sys_id)
            self._landmark_list.addItem(item)

        # Misc tab
        self._show_alert_age.setChecked(cfg.show_alert_age)
        self._display_char_names.setChecked(cfg.display_character_names)
        self._show_char_locations.setChecked(cfg.show_character_locations)
        self._persistent_labels.setChecked(cfg.persistent_system_labels)
        self._dark_mode.setChecked(cfg.dark_mode)
        self._map_text_size.setValue(cfg.map_text_size)
        self._max_alert_age.setValue(cfg.max_alert_age)
        self._max_alerts.setValue(cfg.max_alerts)
        self._map_mode_combo.setCurrentIndex(0 if cfg.map_mode == "3d" else 1)

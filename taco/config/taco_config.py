"""T.A.C.O. configuration manager - JSON config with dataclass defaults, auto-save on change.

Ported from ConfigVer6.cs. Stores user preferences in a platform-appropriate
JSON file and exposes them as typed dataclass fields.
"""
import json
import logging
import os
import platform
import shutil
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# No default presets — users configure their own channels, alerts, and
# ignore strings via the Settings panel or by importing a profile.


@dataclass
class TacoConfig:
    """Application configuration with auto-save support.

    All properties correspond to ConfigVer6.cs fields.  Changes are
    automatically persisted when :meth:`save` is called.  Call
    :meth:`load` at startup to hydrate from disk (or create the file
    with defaults if it does not exist).
    """

    # Window state
    preserve_window_position: bool = True
    preserve_window_size: bool = True
    window_position_x: int = 50
    window_position_y: int = 50
    window_size_x: int = 1253
    window_size_y: int = 815
    preserve_full_screen_status: bool = True
    is_full_screen: bool = False

    # Home system
    preserve_home_system: bool = True
    home_system_id: int = 771

    # Game log
    monitor_game_log: bool = True

    # Camera
    preserve_camera_distance: bool = True
    preserve_look_at: bool = True
    camera_distance: float = 700.0
    look_at_x: float = -1416.0
    look_at_y: float = 3702.0

    # Log path override
    override_log_path: bool = False
    log_path: str = ""

    # Selected systems
    preserve_selected_systems: bool = True
    selected_systems: list[int] = field(default_factory=list)

    # Landmark systems (always-visible labels on map)
    landmark_systems: list[int] = field(default_factory=list)

    # Intel display
    display_new_file_alerts: bool = True
    display_open_file_alerts: bool = True
    display_character_names: bool = True
    show_character_locations: bool = True
    camera_follow_character: bool = False
    centre_on_character: int = -1

    # Map
    map_range_from: int = 0
    map_mode: str = "3d"

    # Anomaly monitor
    anomaly_monitor_sound_id: int = -1
    anomaly_monitor_sound_path: str = ""

    # Alert display
    show_alert_age: bool = True
    show_alert_age_secs: bool = True
    max_alert_age: int = 10
    max_alerts: int = 20

    # Map text
    map_text_size: int = 8

    # Theme
    dark_mode: bool = False

    # Labels
    persistent_system_labels: bool = False

    # Custom channels: list of dicts with keys (name, prefix, monitor, alert, short_name)
    custom_channels: list[dict] = field(default_factory=list)

    # Alert triggers: list of dicts matching AlertTrigger.to_dict() format
    alert_triggers: list[dict] = field(default_factory=list)

    # Ignore strings
    ignore_strings: list[str] = field(default_factory=list)

    # Ignore systems
    ignore_systems: list[int] = field(default_factory=list)

    # Monitored systems (green crosshairs, excluding home)
    monitored_systems: list[int] = field(default_factory=list)

    # Character list
    character_list: list[str] = field(default_factory=list)

    # ---- internal state (not serialised) ----
    _dirty: bool = field(default=False, init=False, repr=False, compare=False)
    _auto_save: bool = field(default=True, init=False, repr=False, compare=False)

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_config_dir() -> Path:
        """Return the platform-appropriate configuration directory.

        Linux / macOS : ``~/.config/taco/``
        Windows       : ``%APPDATA%/taco/``
        """
        system = platform.system()
        if system == "Windows":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base / "taco"

    @staticmethod
    def get_config_path() -> Path:
        """Return the full path to ``taco.json``."""
        return TacoConfig.get_config_dir() / "taco.json"

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def _serialisable_dict(self) -> dict[str, Any]:
        """Return a plain dict of all public fields suitable for JSON."""
        result: dict[str, Any] = {}
        for f in fields(self):
            if f.name.startswith("_"):
                continue
            result[f.name] = getattr(self, f.name)
        return result

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "TacoConfig":
        """Create a TacoConfig from a dict, falling back to defaults for
        missing or invalid keys.

        Uses ``object.__new__`` and ``object.__setattr__`` to bypass the
        auto-save ``__setattr__`` override, which would otherwise call
        ``save()`` before all fields have been initialised.
        """
        from dataclasses import MISSING

        config = object.__new__(cls)
        # Set internal state first so __setattr__ won't auto-save
        object.__setattr__(config, "_dirty", False)
        object.__setattr__(config, "_auto_save", False)

        valid_names = {f.name for f in fields(cls) if not f.name.startswith("_")}
        for f in fields(cls):
            if f.name.startswith("_"):
                continue
            if f.name in data:
                object.__setattr__(config, f.name, data[f.name])
            elif f.default is not MISSING:
                object.__setattr__(config, f.name, f.default)
            elif f.default_factory is not MISSING:
                object.__setattr__(config, f.name, f.default_factory())

        # Re-enable auto-save now that all fields are set
        object.__setattr__(config, "_auto_save", True)
        return config

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist current configuration to disk as formatted JSON."""
        config_path = self.get_config_path()
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as fh:
                json.dump(self._serialisable_dict(), fh, indent=4, ensure_ascii=False)
            self._dirty = False
            logger.info("Configuration saved to %s", config_path)
        except OSError as exc:
            logger.error("Failed to save configuration: %s", exc)

    @classmethod
    def load(cls) -> "TacoConfig":
        """Load configuration from disk.

        If the file or directory does not exist it is created with
        default values.  Any keys present in the file override the
        defaults; missing keys retain their defaults.
        """
        config_path = cls.get_config_path()
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                logger.info("Configuration loaded from %s", config_path)
                config = cls._from_dict(data)
                config._dirty = False
                return config
            except (json.JSONDecodeError, OSError, TypeError) as exc:
                logger.warning(
                    "Failed to read config (%s); using defaults and re-saving.", exc
                )

        # First run or corrupted file -- write defaults
        config = cls()
        config.save()
        return config

    # ------------------------------------------------------------------
    # Profile export / import
    # ------------------------------------------------------------------

    # Keys exported in a profile (gameplay-relevant, not window state)
    _PROFILE_KEYS: tuple[str, ...] = (
        "home_system_id", "monitored_systems", "selected_systems",
        "custom_channels", "alert_triggers", "ignore_strings",
        "ignore_systems", "character_list",
        "show_alert_age", "display_character_names", "show_character_locations",
        "max_alert_age", "max_alerts",
        "map_text_size", "persistent_system_labels", "dark_mode",
        "monitor_game_log", "map_range_from",
        "landmark_systems", "map_mode",
    )

    def export_profile(self, path: str) -> list[str]:
        """Write gameplay-relevant config fields and custom sounds to *path*.

        Custom sound files referenced by alert triggers are copied next to the
        exported JSON so the profile is fully portable.  Returns the list of
        exported key names.
        """
        from taco.audio.sound_manager import SOUND_LIST

        data: dict[str, Any] = {"taco_profile": 1}
        for key in self._PROFILE_KEYS:
            data[key] = getattr(self, key)

        # --- bundle custom sound files ---
        export_dir = Path(path).parent
        bundled: list[str] = []  # filenames placed next to the JSON

        for trigger in data.get("alert_triggers", []):
            sound_path = trigger.get("sound_path", "")
            sound_id = trigger.get("sound_id", -1)
            if sound_id < 0 and sound_path and sound_path not in SOUND_LIST:
                src = Path(sound_path)
                if src.is_file():
                    dest = export_dir / src.name
                    if dest != src:
                        shutil.copy2(str(src), str(dest))
                    bundled.append(src.name)
                    # store just the filename for portability
                    trigger["sound_path"] = src.name

        if bundled:
            data["_bundled_sounds"] = bundled

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=4, ensure_ascii=False)
        logger.info("Profile exported to %s (%d keys, %d sounds)",
                     path, len(self._PROFILE_KEYS), len(bundled))
        return list(self._PROFILE_KEYS)

    def import_profile(self, path: str) -> list[str]:
        """Read a profile JSON from *path*, apply recognised keys, and save.

        Custom sound files bundled next to the JSON are copied into the config
        directory so alert triggers can find them after import.  Returns the
        list of imported key names.
        """
        from taco.audio.sound_manager import SOUND_LIST

        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if "taco_profile" not in data:
            raise ValueError("Not a valid TACO profile (missing taco_profile key)")

        import_dir = Path(path).parent
        sounds_dir = self.get_config_dir() / "sounds"

        # --- restore bundled sound files ---
        bundled = data.get("_bundled_sounds", [])
        if bundled:
            sounds_dir.mkdir(parents=True, exist_ok=True)
        for filename in bundled:
            src = import_dir / filename
            if src.is_file():
                shutil.copy2(str(src), str(sounds_dir / filename))

        # rewrite portable filenames → absolute paths for alert triggers
        for trigger in data.get("alert_triggers", []):
            sound_path = trigger.get("sound_path", "")
            sound_id = trigger.get("sound_id", -1)
            if sound_id < 0 and sound_path and sound_path not in SOUND_LIST:
                # If it's just a filename (no directory), resolve to sounds_dir
                if not os.path.dirname(sound_path):
                    resolved = sounds_dir / sound_path
                    if resolved.is_file():
                        trigger["sound_path"] = str(resolved)

        valid = {k for k in self._PROFILE_KEYS}
        imported: list[str] = []
        self.begin_batch()
        try:
            for key, value in data.items():
                if key in valid:
                    self.set(key, value)
                    imported.append(key)
        finally:
            self.end_batch(save=True)
        logger.info("Profile imported from %s (%d keys)", path, len(imported))
        return imported

    # ------------------------------------------------------------------
    # Auto-save helpers
    # ------------------------------------------------------------------

    def set(self, name: str, value: Any) -> None:
        """Set a config property by name and auto-save if the value changed."""
        if not hasattr(self, name) or name.startswith("_"):
            raise AttributeError(f"TacoConfig has no property '{name}'")
        old = getattr(self, name)
        if old != value:
            object.__setattr__(self, name, value)
            self._dirty = True
            if self._auto_save:
                self.save()

    def __setattr__(self, name: str, value: Any) -> None:
        """Override attribute setting to track changes and auto-save.

        Private/internal attributes (prefixed with ``_``) bypass auto-save
        to avoid infinite recursion during initialisation.
        """
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return

        # During __init__, dataclass sets attrs before _auto_save exists
        try:
            auto = object.__getattribute__(self, "_auto_save")
        except AttributeError:
            object.__setattr__(self, name, value)
            return

        # Detect actual change
        try:
            old = object.__getattribute__(self, name)
        except AttributeError:
            old = _SENTINEL

        object.__setattr__(self, name, value)

        if auto and old is not _SENTINEL and old != value:
            self._dirty = True
            self.save()

    @property
    def dirty(self) -> bool:
        """True when in-memory state differs from the last save."""
        return self._dirty

    def begin_batch(self) -> None:
        """Temporarily disable auto-save so that multiple mutations can be
        applied before a single :meth:`save`."""
        self._auto_save = False

    def end_batch(self, save: bool = True) -> None:
        """Re-enable auto-save and optionally persist changes."""
        self._auto_save = True
        if save and self._dirty:
            self.save()


# Sentinel used internally for change detection
_SENTINEL = object()

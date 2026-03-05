"""Cross-platform EVE Online log path detection.
Ported from LogPathDetector.cs with added Linux support."""
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LogPathInfo:
    path: str = ""
    is_valid: bool = False
    installation_type: str = ""
    recent_chat_log_count: int = 0
    recent_game_log_count: int = 0

    def __str__(self) -> str:
        return (f"{self.installation_type}: {self.path} "
                f"({self.recent_chat_log_count} chat, {self.recent_game_log_count} game logs)")


def get_possible_log_paths() -> list[str]:
    """Get all possible EVE Online log paths for the current system."""
    paths = []
    system = platform.system()

    if system == "Windows":
        _get_windows_paths(paths)
    elif system == "Linux":
        _get_linux_paths(paths)
    elif system == "Darwin":
        _get_macos_paths(paths)

    return list(dict.fromkeys(paths))  # deduplicate preserving order


def _get_windows_paths(paths: list[str]):
    documents = Path.home() / "Documents"

    # Standard installation
    standard = documents / "EVE" / "logs"
    if standard.exists():
        paths.append(str(standard))

    # Alternative
    alt = documents / "EVE Online" / "logs"
    if alt.exists():
        paths.append(str(alt))

    # Multiple EVE account folders
    try:
        for d in documents.iterdir():
            if d.is_dir() and d.name.startswith("EVE"):
                logs = d / "logs"
                if logs.exists():
                    paths.append(str(logs))
    except (PermissionError, OSError):
        pass

    # Steam paths
    steam_locations = [
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
        Path(r"D:\Steam"),
        Path(r"D:\SteamLibrary"),
    ]
    for steam in steam_locations:
        eve_logs = steam / "steamapps" / "compatdata" / "8500" / "pfx" / "drive_c" / "users" / "steamuser" / "My Documents" / "EVE" / "logs"
        if eve_logs.exists():
            paths.append(str(eve_logs))


def _get_linux_paths(paths: list[str]):
    home = Path.home()
    user = home.name

    # Wine default
    wine_path = home / ".wine" / "drive_c" / "users" / user / "My Documents" / "EVE" / "logs"
    if wine_path.exists():
        paths.append(str(wine_path))

    # Also check "Documents" variant
    wine_path2 = home / ".wine" / "drive_c" / "users" / user / "Documents" / "EVE" / "logs"
    if wine_path2.exists():
        paths.append(str(wine_path2))

    # Proton (Steam)
    proton_path = (home / ".local" / "share" / "Steam" / "steamapps" / "compatdata" /
                   "8500" / "pfx" / "drive_c" / "users" / "steamuser" / "My Documents" / "EVE" / "logs")
    if proton_path.exists():
        paths.append(str(proton_path))

    # Flatpak Steam
    flatpak_path = (home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" /
                    "Steam" / "steamapps" / "compatdata" / "8500" / "pfx" / "drive_c" /
                    "users" / "steamuser" / "My Documents" / "EVE" / "logs")
    if flatpak_path.exists():
        paths.append(str(flatpak_path))

    # Lutris
    lutris_path = home / "Games" / "eve-online" / "drive_c" / "users" / user / "My Documents" / "EVE" / "logs"
    if lutris_path.exists():
        paths.append(str(lutris_path))


def _get_macos_paths(paths: list[str]):
    documents = Path.home() / "Documents"
    standard = documents / "EVE" / "logs"
    if standard.exists():
        paths.append(str(standard))


def get_default_log_path() -> str:
    """Get the default EVE log path for the current platform."""
    system = platform.system()
    if system == "Windows":
        return str(Path.home() / "Documents" / "EVE" / "logs")
    elif system == "Linux":
        # Try Proton first
        home = Path.home()
        proton = (home / ".local" / "share" / "Steam" / "steamapps" / "compatdata" /
                  "8500" / "pfx" / "drive_c" / "users" / "steamuser" / "My Documents" / "EVE" / "logs")
        if proton.exists():
            return str(proton)
        # Then Wine
        wine = home / ".wine" / "drive_c" / "users" / home.name / "My Documents" / "EVE" / "logs"
        if wine.exists():
            return str(wine)
        return str(proton)  # Default to Proton path even if not exists
    return str(Path.home() / "Documents" / "EVE" / "logs")


def is_valid_eve_log_path(path: str) -> bool:
    """Check if path is a valid EVE logs directory."""
    if not path or not os.path.isdir(path):
        return False
    chat_logs = os.path.join(path, "Chatlogs")
    game_logs = os.path.join(path, "Gamelogs")
    return os.path.isdir(chat_logs) or os.path.isdir(game_logs)

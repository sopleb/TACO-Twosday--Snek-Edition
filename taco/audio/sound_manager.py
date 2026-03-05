"""Sound playback using PyQt6. Ported from MainForm.cs sound handling.

Built-in WAV sounds use QSoundEffect (low-latency, no decoding overhead).
Custom sounds (MP3, WAV, OGG, etc.) use QMediaPlayer + QAudioOutput which
supports compressed formats.

On Linux, Qt6's pip multimedia backend often can't load (missing ffmpeg
plugin deps), so we fall back to paplay/aplay via subprocess.
"""
import os
import platform
import shutil
import subprocess
import sys
from typing import Optional

from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QSoundEffect, QMediaPlayer, QAudioOutput, QMediaDevices


def _resource_path(relative: str) -> str:
    if getattr(sys, 'frozen', False):
        base = os.path.join(sys._MEIPASS, "taco", "resources")
    else:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources")
    return os.path.normpath(os.path.join(base, relative))


def _linux_audio_cmd() -> Optional[list[str]]:
    """Return a command prefix for playing WAV files on Linux, or None."""
    for cmd in ("paplay", "aplay", "pw-play"):
        if shutil.which(cmd):
            return [cmd]
    return None


# Sound names mapped to their WAV file names (matching C# project)
BUILT_IN_SOUNDS = {
    "1up1": "1up1.wav",
    "Boo2": "Boo2.wav",
    "Coin": "Coin.wav",
    "KamekLaugh": "KamekLaugh.wav",
    "Powerup": "Powerup.wav",
    "RedCoin2": "RedCoin2.wav",
    "RedCoin3": "RedCoin3.wav",
    "StarCoin": "StarCoin.wav",
    "SuitFly": "SuitFly.wav",
    "SuitSpin": "SuitSpin.wav",
    "Whistle": "Whistle.wav",
    "CallInsideHouse": "CallInsideHouse.wav",
    "Hostiles1jump": "Hostiles1jump.wav",
    "Hostiles2jump": "hostiles2jump.wav",
    "Hostiles3jump": "hostiles3jump.wav",
    "Hostiles4jump": "hostiles4jump.wav",
    "HostilesHere": "HostilesHere.wav",
}

# Ordered list matching C# combo box indices
SOUND_LIST = [
    "1up1", "Boo2", "Coin", "KamekLaugh", "Powerup",
    "RedCoin2", "RedCoin3", "StarCoin", "SuitFly", "SuitSpin", "Whistle",
    "CallInsideHouse", "Hostiles1jump", "Hostiles2jump",
    "Hostiles3jump", "Hostiles4jump", "HostilesHere",
]


class SoundManager:
    def __init__(self):
        self._sounds: dict[str, QSoundEffect] = {}
        self._sound_paths: dict[str, str] = {}  # name -> absolute filepath
        self._media_player: Optional[QMediaPlayer] = None
        self._audio_output: Optional[QAudioOutput] = None
        self._muted = False
        # On Linux, detect whether Qt audio works; if not, use subprocess.
        self._use_native_cmd: Optional[list[str]] = None
        if platform.system() == "Linux":
            if not QMediaDevices.audioOutputs():
                self._use_native_cmd = _linux_audio_cmd()

    def load_sounds(self):
        """Register all built-in WAV file paths. QSoundEffect instances are
        created lazily on first play to avoid spawning ~17 audio threads at
        startup."""
        sounds_dir = _resource_path("sounds")
        for name, filename in BUILT_IN_SOUNDS.items():
            filepath = os.path.join(sounds_dir, filename)
            if os.path.exists(filepath):
                self._sound_paths[name] = filepath

    def _play_native(self, filepath: str):
        """Play a WAV file via the system audio command (Linux fallback)."""
        if self._use_native_cmd is None:
            return
        try:
            subprocess.Popen(
                self._use_native_cmd + [filepath],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass

    def _ensure_media_player(self) -> QMediaPlayer:
        """Lazily create the QMediaPlayer used for custom sounds."""
        if self._media_player is None:
            self._media_player = QMediaPlayer()
            self._audio_output = QAudioOutput()
            self._audio_output.setVolume(0.8)
            self._media_player.setAudioOutput(self._audio_output)
        return self._media_player

    def _get_or_create_effect(self, name: str) -> Optional[QSoundEffect]:
        """Return cached QSoundEffect, creating it lazily on first access."""
        if name in self._sounds:
            return self._sounds[name]
        if name in self._sound_paths:
            effect = QSoundEffect()
            effect.setSource(QUrl.fromLocalFile(self._sound_paths[name]))
            effect.setVolume(0.8)
            self._sounds[name] = effect
            return effect
        return None

    def play_sound(self, name: str) -> bool:
        """Play a built-in sound by name. Returns True if sound was found."""
        if self._muted:
            return False
        # Native subprocess path (Linux fallback)
        if self._use_native_cmd is not None:
            if name in self._sound_paths:
                self._play_native(self._sound_paths[name])
                return True
            return False
        effect = self._get_or_create_effect(name)
        if effect is not None:
            if effect.isLoaded():
                effect.play()
                return True
            # Effect still loading — fall back to QMediaPlayer
            if name in self._sound_paths:
                player = self._ensure_media_player()
                player.stop()
                player.setSource(QUrl.fromLocalFile(self._sound_paths[name]))
                player.play()
                return True
        return False

    def play_sound_by_id(self, sound_id: int) -> bool:
        """Play a built-in sound by its index in SOUND_LIST. Returns True if played."""
        if self._muted or sound_id < 0 or sound_id >= len(SOUND_LIST):
            return False
        return self.play_sound(SOUND_LIST[sound_id])

    def play_custom_sound(self, file_path: str):
        """Play a sound by file path, or by built-in name as fallback."""
        if self._muted:
            return
        # Try as built-in sound name first (handles sound_id/sound_path mismatch)
        if self._use_native_cmd is not None:
            if file_path in self._sound_paths:
                self._play_native(self._sound_paths[file_path])
                return
            if os.path.exists(file_path):
                self._play_native(file_path)
            return
        effect = self._get_or_create_effect(file_path)
        if effect is not None:
            effect.play()
            return
        if not os.path.exists(file_path):
            return
        player = self._ensure_media_player()
        player.stop()
        player.setSource(QUrl.fromLocalFile(os.path.abspath(file_path)))
        player.play()

    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, value: bool):
        self._muted = value

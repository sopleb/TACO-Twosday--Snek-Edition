"""Local chat watcher for character location tracking. Ported from LocalWatcher.cs.

All file I/O runs in a background thread to avoid blocking the UI.
"""
import os
import re
import threading
from datetime import datetime, timedelta
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from taco.intel.log_path_detector import get_default_log_path


class LocalInfo:
    def __init__(self):
        self.char_name: str = ""
        self.initial_system: int = -1
        self.current_system: str = ""


class LocalWatcher(QObject):
    system_change = pyqtSignal(str, str)  # system_name, char_name

    # Internal signal for thread-safe delivery of results to main thread
    _results_ready = pyqtSignal(list, object)  # system_changes, initial_local_info

    _SYSTEM_CHANGE_RE = re.compile(
        r'EVE\sSystem\s>\sChannel\schanged\sto\sLocal\s:\s(?P<systemname>.*)'
    )
    _LISTENER_RE = re.compile(r'Listener:\s*(?P<name>.*)')
    _INITIAL_SYSTEM_RE = re.compile(
        r"Channel\sID:\s*\(\('solarsystemid2',\s(?P<initialsystem>[0-9]{8})"
    )

    def __init__(self, log_path: str | None = None, parent=None):
        super().__init__(parent)
        self._root_logs_path = log_path or get_default_log_path()
        self._log_path = os.path.join(self._root_logs_path, "Chatlogs")
        self._encoding = 'utf-16-le'

        self._file_sizes: dict[str, int] = {}
        self._interesting_files: dict[str, _InterestingFile] = {}
        self.initial_local_info: Optional[LocalInfo] = None

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._on_tick)

        self._tick_running = False
        self._stopped = False
        self._results_ready.connect(self._on_results)

    @property
    def is_running(self) -> bool:
        return self._timer.isActive() or self._tick_running

    def start_watch(self) -> bool:
        if self._timer.isActive():
            return True

        if not os.path.isdir(self._log_path):
            return False

        self._interesting_files.clear()
        self._stopped = False
        self._tick_running = True
        threading.Thread(target=self._init_worker, daemon=True).start()
        return True

    def stop_watch(self):
        self._stopped = True
        self._timer.stop()

    def _init_worker(self):
        """Background thread: initial file scan + first tick."""
        try:
            all_files = self._init_log_file_info()
            system_changes = []
            first_info = None

            seen_chars: set[str] = set()
            for log_file in all_files:
                length = self._get_file_length(log_file)
                info = self._init_local(log_file)
                if not info.char_name:
                    continue
                if first_info is None:
                    first_info = info
                self._interesting_files[log_file] = _InterestingFile(
                    log_file, length, datetime.now(), info.char_name
                )
                if info.char_name not in seen_chars:
                    seen_chars.add(info.char_name)
                    system_name = (info.current_system
                                   if info.current_system
                                   else str(info.initial_system))
                    system_changes.append((system_name, info.char_name))

            # First tick
            tick_changes = self._do_tick_work()
            system_changes.extend(tick_changes)
            self._results_ready.emit(system_changes, first_info)
        except Exception:
            self._results_ready.emit([], None)

    def _on_tick(self):
        """Timer callback (main thread): start background tick if not already running."""
        if self._tick_running:
            return
        self._tick_running = True
        self._timer.stop()
        threading.Thread(target=self._tick_thread, daemon=True).start()

    def _tick_thread(self):
        """Background thread: do file I/O tick."""
        try:
            changes = self._do_tick_work()
            self._results_ready.emit(changes, None)
        except Exception:
            self._results_ready.emit([], None)

    def _on_results(self, system_changes, initial_info):
        """Main thread: emit collected results and restart timer."""
        self._tick_running = False
        if self._stopped:
            return
        if initial_info is not None and self.initial_local_info is None:
            self.initial_local_info = initial_info
        for system_name, char_name in system_changes:
            self.system_change.emit(system_name, char_name)
        self._timer.start()

    def _do_tick_work(self):
        """All file I/O — runs in background thread. Returns list of (system_name, char_name)."""
        system_changes = []

        # Process new files
        changed = self._get_changed_log_files()
        for full_path in changed:
            if full_path in self._interesting_files:
                continue
            length = self._get_file_length(full_path)
            info = self._init_local(full_path)
            self._interesting_files[full_path] = _InterestingFile(
                full_path, length, datetime.now(), info.char_name
            )
            system_name = info.current_system if info.current_system else str(info.initial_system)
            system_changes.append((system_name, info.char_name))

        # Remove stale
        stale = [k for k, v in self._interesting_files.items()
                 if v.last_update < datetime.now() - timedelta(minutes=120)]
        for k in stale:
            del self._interesting_files[k]
            self._file_sizes.pop(k, None)

        # Prune _file_sizes entries for files no longer tracked
        tracked = set(self._interesting_files.keys())
        stale_sizes = [k for k in self._file_sizes if k not in tracked]
        for k in stale_sizes:
            del self._file_sizes[k]

        # Read new content - read directly instead of relying on file size
        for fpath, ifile in self._interesting_files.items():
            text, new_len = self._read_log_file(fpath, ifile.last_position)
            if new_len <= ifile.last_position or not text:
                continue

            ifile.last_position = new_len
            ifile.last_update = datetime.now()

            lines = [l.strip() for l in text.split('\n') if l.strip()]
            for line in lines:
                m = self._SYSTEM_CHANGE_RE.search(line)
                if m:
                    system_changes.append((m.group("systemname").strip(), ifile.char_name))

        return system_changes

    # --- File I/O helpers (called from background thread) ---

    def _init_log_file_info(self) -> list[str]:
        try:
            files = []
            for f in os.listdir(self._log_path):
                if not f.lower().startswith("local") or not f.endswith(".txt"):
                    continue
                full = os.path.join(self._log_path, f)
                stat = os.stat(full)
                if datetime.fromtimestamp(stat.st_ctime) > datetime.now() - timedelta(days=1):
                    files.append((full, stat.st_mtime))

            files.sort(key=lambda x: x[1], reverse=True)
            result = []
            for full_path, _ in files:
                length = self._get_file_length(full_path)
                self._file_sizes[full_path] = length
                result.append(full_path)
            return result
        except (OSError, PermissionError):
            return []

    def _init_local(self, file_path: str) -> LocalInfo:
        info = LocalInfo()
        try:
            with open(file_path, 'r', encoding=self._encoding, errors='replace') as f:
                for line in f:
                    line = self._clean_line(line)

                    if info.initial_system == -1:
                        m = self._INITIAL_SYSTEM_RE.search(line)
                        if m:
                            info.initial_system = int(m.group("initialsystem"))
                            continue

                    if not info.char_name:
                        m = self._LISTENER_RE.match(line)
                        if m:
                            name = m.group("name").strip()
                            if len(name) > 4:
                                info.char_name = name
                            continue

                    m = self._SYSTEM_CHANGE_RE.search(line)
                    if m:
                        info.current_system = m.group("systemname").strip()
        except (OSError, UnicodeDecodeError):
            return LocalInfo()
        return info

    def _get_changed_log_files(self) -> list[str]:
        changed = []
        try:
            for f in os.listdir(self._log_path):
                if not f.lower().startswith("local") or not f.endswith(".txt"):
                    continue
                full = os.path.join(self._log_path, f)
                stat = os.stat(full)
                if datetime.fromtimestamp(stat.st_ctime) < datetime.now() - timedelta(days=1):
                    continue

                length = self._get_file_length(full)
                if full in self._file_sizes:
                    if self._file_sizes[full] != length:
                        self._file_sizes[full] = length
                        changed.append(full)
                else:
                    self._file_sizes[full] = length
                    changed.append(full)
        except (OSError, PermissionError):
            pass
        return changed

    def _get_file_length(self, file_path: str) -> int:
        try:
            return os.path.getsize(file_path)
        except OSError:
            return -1

    def _read_log_file(self, file_path: str, start_pos: int) -> tuple[str, int]:
        try:
            with open(file_path, 'rb') as f:
                f.seek(start_pos)
                raw = f.read()
                new_pos = start_pos + len(raw)
                text = raw.decode(self._encoding, errors='replace')
                text = self._clean_line(text)
                return text, new_pos
        except (OSError, UnicodeDecodeError):
            return "", -1

    @staticmethod
    def _clean_line(line: str) -> str:
        return line.replace('\ufeff', '').replace('\ufffe', '').replace('\r', '').strip()


class _InterestingFile:
    def __init__(self, file_name: str, last_position: int, last_update: datetime, char_name: str = ""):
        self.file_name = file_name
        self.last_position = last_position
        self.last_update = last_update
        self.char_name = char_name

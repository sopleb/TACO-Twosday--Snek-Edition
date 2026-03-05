"""QTimer-based file polling for EVE chat/game logs. Ported from LogWatcher.cs.

All file I/O runs in a background thread to avoid blocking the UI.
"""
import os
import re
import threading
from datetime import datetime, timedelta
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from taco.intel.log_entry import LogEntry, LogEntryType, LogFileType, CombatEventType
from taco.intel.log_path_detector import get_default_log_path


class InterestingFile:
    def __init__(self, file_name: str, last_position: int, last_update: datetime, char_name: str = ""):
        self.file_name = file_name
        self.last_position = last_position
        self.last_update = last_update
        self.last_combat = datetime.min
        self.char_name = char_name
        self.timeout_triggered = True
        self.in_combat = False


class LogWatcher(QObject):
    new_log_entry = pyqtSignal(object)        # LogEntry
    combat_event = pyqtSignal(str, str, int)  # filename, charname, CombatEventType

    # Internal signal for thread-safe delivery of results to main thread
    _results_ready = pyqtSignal(list, list)   # entries, combat_events

    _CHAT_LOG_RE = re.compile(
        r'\[\s\d{4}\.\d{2}\.\d{2}\s(?P<time>\d{2}:\d{2}:\d{2})\s\]\s(?P<name>\w.*)\s>\s(?P<content>.*)'
    )
    _GAME_LOG_RE = re.compile(
        r'\[\s\d{4}\.\d{2}\.\d{2}\s(?P<time>\d{2}:\d{2}:\d{2})\s\]\s\(\w.*\)\s(?P<content>.*)'
    )
    _GAME_COMBAT_RE = re.compile(
        r'\[\s\d{4}\.\d{2}\.\d{2}\s\d{2}:\d{2}:\d{2}\s\]\s\(combat\)'
    )
    _LISTENER_RE = re.compile(r'Listener:\s*(?P<name>.*)')

    def __init__(self, channel_prefix: str, log_file_type: LogFileType,
                 log_path: str | None = None, parent=None):
        super().__init__(parent)
        self._channel_prefix = channel_prefix
        self._log_file_type = log_file_type

        self._root_logs_path = log_path or get_default_log_path()

        if self._log_file_type == LogFileType.GAME:
            self._encoding = 'ascii'
            self._log_path = os.path.join(self._root_logs_path, "Gamelogs")
        else:
            self._encoding = 'utf-16-le'
            self._log_path = os.path.join(self._root_logs_path, "Chatlogs")

        self._file_sizes: dict[str, int] = {}
        self._interesting_files: dict[str, InterestingFile] = {}
        self._previous_entries: list[LogEntry] = []

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._on_tick)

        self._tick_running = False
        self._stopped = False
        self._results_ready.connect(self._on_results)

    @property
    def channel_prefix(self) -> str:
        return self._channel_prefix

    @property
    def root_logs_path(self) -> str:
        return self._root_logs_path

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
            init_entries = []

            for log_file in all_files:
                length = self._get_file_length(log_file)
                char_name = self._get_log_listener(log_file)
                self._interesting_files[log_file] = InterestingFile(
                    log_file, length, datetime.now(), char_name)

                entry = LogEntry(
                    file_name=os.path.basename(log_file),
                    entry_type=(LogEntryType.OPEN_GAME_LOG if self._log_file_type == LogFileType.GAME
                                else LogEntryType.OPEN_CHAT_LOG),
                    line_content=str(length),
                    character_name=char_name,
                )
                init_entries.append(entry)

            # First tick
            tick_entries, combat_events = self._do_tick_work()
            init_entries.extend(tick_entries)
            self._results_ready.emit(init_entries, combat_events)
        except Exception:
            self._results_ready.emit([], [])

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
            entries, combat_events = self._do_tick_work()
            self._results_ready.emit(entries, combat_events)
        except Exception:
            self._results_ready.emit([], [])

    def _on_results(self, entries, combat_events):
        """Main thread: emit collected results and restart timer."""
        self._tick_running = False
        if self._stopped:
            return
        for entry in entries:
            self.new_log_entry.emit(entry)
        for fname, cname, etype in combat_events:
            self.combat_event.emit(fname, cname, etype)
        self._timer.start()

    def _do_tick_work(self):
        """All file I/O — runs in background thread. Returns (entries, combat_events)."""
        entries = []
        combat_events = []

        # Clean expired previous entries
        cutoff = datetime.now() - timedelta(seconds=5)
        self._previous_entries = [e for e in self._previous_entries if e.time_added >= cutoff]

        # Process new/changed files
        changed_files = self._get_changed_log_files()
        for full_path in changed_files:
            if full_path in self._interesting_files:
                continue
            char_name = self._get_log_listener(full_path)
            # Start reading from position 0 so the first message isn't skipped.
            # Header lines won't match the chat regex and will be filtered out.
            self._interesting_files[full_path] = InterestingFile(full_path, 0, datetime.now(), char_name)

            entry = LogEntry(
                file_name=os.path.basename(full_path),
                entry_type=(LogEntryType.NEW_GAME_LOG if self._log_file_type == LogFileType.GAME
                            else LogEntryType.NEW_CHAT_LOG),
                line_content=str(self._file_sizes.get(full_path, 0)),
                log_type=self._log_file_type,
                character_name=char_name,
            )
            entries.append(entry)

        # Combat timeout detection
        if self._log_file_type == LogFileType.GAME:
            for ifile in self._interesting_files.values():
                if (ifile.in_combat and not ifile.timeout_triggered and
                        ifile.last_combat < datetime.now() - timedelta(seconds=30)):
                    ifile.timeout_triggered = True
                    ifile.in_combat = False
                    combat_events.append((ifile.file_name, ifile.char_name, int(CombatEventType.STOP)))

        # Remove stale files
        stale_keys = [
            k for k, v in self._interesting_files.items()
            if v.last_update < datetime.now() - timedelta(minutes=120)
        ]
        for k in stale_keys:
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
                entry = LogEntry()
                regex = self._CHAT_LOG_RE if self._log_file_type == LogFileType.CHAT else self._GAME_LOG_RE
                match = regex.match(line)

                entry.raw_line = line
                entry.file_name = os.path.basename(fpath)
                entry.log_prefix = self._channel_prefix
                entry.time_added = datetime.now()
                entry.log_type = self._log_file_type
                entry.character_name = ifile.char_name

                # Combat detection
                if self._log_file_type == LogFileType.GAME and self._GAME_COMBAT_RE.match(line):
                    if not ifile.in_combat:
                        ifile.in_combat = True
                        combat_events.append((ifile.file_name, ifile.char_name, int(CombatEventType.START)))
                    ifile.timeout_triggered = False
                    ifile.last_combat = ifile.last_update

                if match:
                    entry.log_time = match.group("time")
                    entry.line_content = match.group("content")
                    entry.entry_type = LogEntryType.CHAT_EVENT
                    entry.parse_success = True
                    if self._log_file_type == LogFileType.CHAT:
                        entry.player_name = match.group("name")
                else:
                    entry.line_content = line
                    entry.parse_success = False
                    entry.entry_type = (LogEntryType.UNKNOWN_CHAT_LOG
                                        if self._log_file_type == LogFileType.CHAT
                                        else LogEntryType.UNKNOWN_GAME_LOG)

                # Dedup — use player_name + content so different reporters
                # with the same message text are not incorrectly dropped
                dedup_key = (entry.player_name or "") + "\x00" + entry.line_content
                if not any(
                    (prev.player_name or "") + "\x00" + prev.line_content == dedup_key
                    for prev in self._previous_entries
                ):
                    self._previous_entries.append(entry)
                    entries.append(entry)

        return entries, combat_events

    # --- File I/O helpers (called from background thread) ---

    def _init_log_file_info(self) -> list[str]:
        pattern = ("" if self._log_file_type == LogFileType.GAME else self._channel_prefix)
        try:
            files = []
            for f in os.listdir(self._log_path):
                if not f.endswith(".txt"):
                    continue
                if not f.lower().startswith(pattern.lower()):
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

    def _get_changed_log_files(self) -> list[str]:
        pattern = ("" if self._log_file_type == LogFileType.GAME else self._channel_prefix)
        changed = []
        try:
            for f in os.listdir(self._log_path):
                if not f.endswith(".txt"):
                    continue
                if not f.lower().startswith(pattern.lower()):
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

    def _get_log_listener(self, file_path: str) -> str:
        try:
            with open(file_path, 'r', encoding=self._encoding, errors='replace') as f:
                for line in f:
                    line = self._clean_line(line)
                    m = self._LISTENER_RE.match(line)
                    if m:
                        return m.group("name").strip()
        except (OSError, UnicodeDecodeError):
            pass
        return ""

    def _read_log_file(self, file_path: str, start_pos: int) -> tuple[str, int]:
        try:
            with open(file_path, 'rb') as f:
                f.seek(start_pos)
                raw = f.read()
                # Use actual bytes read for new position, not getsize()
                # This avoids skipping data written between read() and getsize()
                new_pos = start_pos + len(raw)
                text = raw.decode(self._encoding, errors='replace')
                text = self._clean_line(text)
                return text, new_pos
        except (OSError, UnicodeDecodeError):
            return "", -1

    @staticmethod
    def _clean_line(line: str) -> str:
        return line.replace('\ufeff', '').replace('\ufffe', '').replace('\r', '').strip()

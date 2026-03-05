"""Log entry dataclass and enums, ported from LogWatcher.cs classes."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum


class CombatEventType(IntEnum):
    START = 0
    STOP = 1


class LogEntryType(IntEnum):
    OPEN_CHAT_LOG = 0
    NEW_CHAT_LOG = 1
    OPEN_GAME_LOG = 2
    NEW_GAME_LOG = 3
    UNKNOWN_CHAT_LOG = 4
    UNKNOWN_GAME_LOG = 5
    EXPIRED_CHAT_LOG = 6
    EXPIRED_GAME_LOG = 7
    CHAT_EVENT = 8


class LogFileType(IntEnum):
    GAME = 0
    CHAT = 1


@dataclass
class LogEntry:
    file_name: str = ""
    log_time: str = ""
    player_name: str = ""
    character_name: str = ""
    line_content: str = ""
    log_prefix: str = ""
    log_type: LogFileType = LogFileType.CHAT
    entry_type: LogEntryType = LogEntryType.CHAT_EVENT
    parse_success: bool = False
    raw_line: str = ""
    matched_ids: set[int] = field(default_factory=set)
    time_added: datetime = field(default_factory=datetime.now)

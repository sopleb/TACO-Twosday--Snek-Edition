from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum


class AlertType(IntEnum):
    RANGED = 0
    CUSTOM = 1


class RangeAlertOperator(IntEnum):
    EQUAL = 0
    LESS_THAN = 1
    GREATER_THAN = 2
    LESS_THAN_OR_EQUAL = 3
    GREATER_THAN_OR_EQUAL = 4


class RangeAlertType(IntEnum):
    HOME = 0
    SYSTEM = 1
    CHARACTER = 2
    ANY_CHARACTER = 3
    NONE = 4
    ANY_FOLLOWED_CHARACTER = 5


@dataclass
class AlertTrigger:
    type: AlertType = AlertType.RANGED
    upper_limit_operator: RangeAlertOperator = RangeAlertOperator.EQUAL
    lower_limit_operator: RangeAlertOperator = RangeAlertOperator.EQUAL
    upper_range: int = 0
    lower_range: int = 0
    range_to: RangeAlertType = RangeAlertType.HOME
    character_name: str = ""
    system_id: int = -1
    sound_id: int = -1
    sound_path: str = ""
    enabled: bool = True
    text: str = ""
    repeat_interval: int = 0
    system_name: str = ""
    trigger_time: datetime = field(default_factory=lambda: datetime.min)

    def __str__(self) -> str:
        parts = []
        if self.type == AlertType.RANGED:
            op = "Range = " if self.upper_limit_operator == RangeAlertOperator.EQUAL else "Range <= "
            parts.append(op)
            parts.append(str(self.upper_range))

            if (self.upper_limit_operator == RangeAlertOperator.EQUAL or
                    (self.lower_range == 0 and self.lower_limit_operator == RangeAlertOperator.GREATER_THAN_OR_EQUAL)):
                parts.append(" jump from: " if self.upper_range == 1 else " jumps from: ")
            else:
                parts.append(" jump and" if self.upper_range == 1 else " jumps and")
                parts.append(" > " if self.lower_limit_operator == RangeAlertOperator.GREATER_THAN else " >= ")
                parts.append(str(self.lower_range))
                parts.append(" jump from: " if self.lower_range == 1 else " jumps from: ")

            if self.range_to in (RangeAlertType.HOME, RangeAlertType.SYSTEM):
                parts.append("Home" if self.system_id == -1 else self.system_name)
            elif self.range_to == RangeAlertType.ANY_FOLLOWED_CHARACTER:
                parts.append("Any Followed Character")
            else:
                parts.append("Any Character" if self.range_to == RangeAlertType.ANY_CHARACTER else self.character_name)

            parts.append(f" (Custom Sound)" if self.sound_id == -1 else f" ({self.sound_path})")

        elif self.type == AlertType.CUSTOM:
            parts.append(f'When "{self.text}" is seen, play (')
            parts.append("Custom Sound" if self.sound_id == -1 else self.sound_path)
            parts.append("). Trigger ")
            if self.repeat_interval == 0:
                parts.append("every detection.")
            else:
                parts.append(f"every {self.repeat_interval}")
                parts.append(" sec." if self.repeat_interval == 1 else " secs.")

        return "".join(parts)

    def to_dict(self) -> dict:
        return {
            "type": int(self.type),
            "upper_limit_operator": int(self.upper_limit_operator),
            "lower_limit_operator": int(self.lower_limit_operator),
            "upper_range": self.upper_range,
            "lower_range": self.lower_range,
            "range_to": int(self.range_to),
            "character_name": self.character_name,
            "system_id": self.system_id,
            "sound_id": self.sound_id,
            "sound_path": self.sound_path,
            "enabled": self.enabled,
            "text": self.text,
            "repeat_interval": self.repeat_interval,
        }

    @staticmethod
    def _safe_enum(enum_cls, value, default):
        try:
            return enum_cls(value)
        except ValueError:
            return default

    @staticmethod
    def from_dict(d: dict) -> "AlertTrigger":
        return AlertTrigger(
            type=AlertTrigger._safe_enum(AlertType, d.get("type", 0), AlertType.RANGED),
            upper_limit_operator=AlertTrigger._safe_enum(RangeAlertOperator, d.get("upper_limit_operator", 0), RangeAlertOperator.EQUAL),
            lower_limit_operator=AlertTrigger._safe_enum(RangeAlertOperator, d.get("lower_limit_operator", 0), RangeAlertOperator.EQUAL),
            upper_range=d.get("upper_range", 0),
            lower_range=d.get("lower_range", 0),
            range_to=AlertTrigger._safe_enum(RangeAlertType, d.get("range_to", 0), RangeAlertType.HOME),
            character_name=d.get("character_name", ""),
            system_id=d.get("system_id", -1),
            sound_id=d.get("sound_id", -1),
            sound_path=d.get("sound_path", ""),
            enabled=d.get("enabled", True),
            text=d.get("text", ""),
            repeat_interval=d.get("repeat_interval", 0),
        )

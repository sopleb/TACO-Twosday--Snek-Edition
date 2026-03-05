from dataclasses import dataclass, field


@dataclass
class PathInfo:
    total_jumps: int = 0
    path_systems: list[int] = field(default_factory=list)
    from_system: int = 0
    to_system: int = 0

    @property
    def path_id(self) -> int:
        return (self.from_system * 10000) + self.to_system

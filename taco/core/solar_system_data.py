from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SolarSystemConnectionData:
    to_system_id: int = 0
    to_system_native_id: int = 0
    is_regional: bool = False


@dataclass
class SolarSystemData:
    id: int = 0
    native_id: int = 0
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    x2d: float = 0.0
    y2d: float = 0.0
    region_id: int = 0
    connected_to: list[SolarSystemConnectionData] = field(default_factory=list)

    @staticmethod
    def from_dict(d: dict) -> "SolarSystemData":
        connections = []
        for c in d.get("connected_to", []) or []:
            connections.append(SolarSystemConnectionData(
                to_system_id=c["to_system_id"],
                to_system_native_id=c["to_system_native_id"],
                is_regional=c.get("is_regional", False),
            ))
        return SolarSystemData(
            id=d["id"],
            native_id=d["native_id"],
            name=d["name"],
            x=d["x"],
            y=d["y"],
            z=d["z"],
            x2d=d.get("x2d", d["x"]),
            y2d=d.get("y2d", d["y"]),
            region_id=d.get("region_id", 0),
            connected_to=connections,
        )


@dataclass
class SolarSystemConnection:
    to_system_id: int = 0
    to_system_native_id: int = 0
    is_regional: bool = False

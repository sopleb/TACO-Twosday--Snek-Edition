"""BFS pathfinding using heapq, ported from SolarSystemPathFinder.cs."""
import heapq
from typing import Optional

from taco.core.path_info import PathInfo
from taco.core.solar_system_data import SolarSystemData


class SolarSystemPathFinder:
    def __init__(self, system_data: list[SolarSystemData]):
        self._size = len(system_data)
        self._is_blocked = [False] * self._size
        self._solar_systems = system_data

    def set_blocked(self, index: int, value: bool = True):
        self._is_blocked[index] = value

    def find_path(self, start: int, end: int) -> PathInfo:
        return self._find_path_reversed(end, start)

    def _find_path_reversed(self, start: int, end: int) -> PathInfo:
        start_sys = self._solar_systems[start]

        # (cost, counter, system_id, parent_chain)
        counter = 0
        open_list: list[tuple[float, int, int, list[int]]] = []
        heapq.heappush(open_list, (0, counter, start, []))

        visited = [False] * self._size
        visited[start] = True

        while open_list:
            cost, _, current_id, parent_chain = heapq.heappop(open_list)

            if current_id == end:
                # Build path
                path = list(parent_chain) + [current_id]
                info = PathInfo()
                info.path_systems = path
                info.total_jumps = len(path) - 1
                info.from_system = start
                info.to_system = end
                return info

            connections = self._solar_systems[current_id].connected_to
            if connections:
                for conn in connections:
                    temp_id = conn.to_system_id
                    if temp_id >= self._size:
                        continue
                    if self._is_blocked[temp_id] or visited[temp_id]:
                        continue
                    visited[temp_id] = True
                    new_cost = cost + 1
                    counter += 1
                    heapq.heappush(
                        open_list,
                        (new_cost, counter, temp_id, parent_chain + [current_id])
                    )

        # No path found — use -1 to distinguish from "0 jumps" (same system)
        return PathInfo(
            total_jumps=-1,
            path_systems=[],
            from_system=start,
            to_system=end,
        )

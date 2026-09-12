"""Q4 D model: origin B/C gate plus conservative co-observation filtering.

The production agent uses only observations exposed by the simulator. B and C
route assets live beside this module, so importing the model does not depend on
any Desktop experiment directory.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
Q3_RUNTIME = HERE.parent / "q3" / "B题模型代码汇总" / "第三问策略对比"
ASSETS = HERE / "assets" / "d_model"

for runtime in (Q3_RUNTIME, HERE):
    if str(runtime) not in sys.path:
        sys.path.insert(0, str(runtime))

from feasible_region import MAX_DIRECTION_R  # noqa: E402
from q4_experiment import Q4TriangularCoverageAgent  # noqa: E402

Point = tuple[float, float]


def point_segment_distance(point: Point, a: Point, b: Point) -> float:
    """Euclidean distance from a point to a closed line segment."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    denominator = dx * dx + dy * dy
    if denominator <= 1e-12:
        return math.dist(point, a)
    t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / denominator
    t = max(0.0, min(1.0, t))
    projection = (a[0] + t * dx, a[1] + t * dy)
    return math.dist(point, projection)


def point_in_convex_polygon(point: Point, polygon: tuple[Point, ...]) -> bool:
    """Return whether point lies inside or on a convex polygon of either winding."""
    signs = []
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        cross = ((b[0] - a[0]) * (point[1] - a[1])
                 - (b[1] - a[1]) * (point[0] - a[0]))
        if abs(cross) > 1e-8:
            signs.append(cross > 0.0)
    return not signs or all(value == signs[0] for value in signs)


class DAgent(Q4TriangularCoverageAgent):
    """Final offline Q4 model frozen after the C+3FB validation.

    Gate:
      * no source discovered at the origin -> certified B route, target 2;
      * at least one discovery -> certified C route, target 3.

    At either route, a co-observation is skipped only when the minimum distance
    from the station to the conservative feasible region exceeds the problem's
    1500 m maximum reception radius.
    """

    discovery_threshold = 0
    b_route_observation_target = 2
    c_route_observation_target = 3
    reach_limit_m = MAX_DIRECTION_R
    _route_cache: dict[str, tuple[Point, ...]] | None = None

    @classmethod
    def _routes(cls) -> dict[str, tuple[Point, ...]]:
        if cls._route_cache is None:
            routes = {}
            for name, filename in (("B", "b_winner_design.json"),
                                   ("C", "c_winner_design.json")):
                payload = json.loads((ASSETS / filename).read_text(encoding="utf-8"))
                sites = [tuple(point) for point in payload["sites"]]
                routes[name] = tuple(sites[index] for index in payload["order"])
            if any(route[0] != (0.0, 0.0) for route in routes.values()):
                raise ValueError("B and C routes must begin at the origin")
            cls._route_cache = routes
        return cls._route_cache

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.coverage_observation_target = self.b_route_observation_target
        self.search_points = list(self._routes()["B"])
        self.origin_discoveries: int | None = None
        self.selected_search_order: str | None = None
        self.pruned_observations = 0
        self.coobservations = 0

    def within_reach(self, point: Point, state) -> bool:
        """Whether a station can be within 1500 m of the conservative region."""
        polygon = self._snapshot(state).polygon
        if not polygon:
            return True
        if point_in_convex_polygon(point, polygon):
            return True
        return any(
            point_segment_distance(point, a, polygon[(index + 1) % len(polygon)])
            <= self.reach_limit_m
            for index, a in enumerate(polygon)
        )

    def _coobserve(self, point: Point, primary_channel: int) -> None:
        if self.selected_search_order not in ("B", "C"):
            return super()._coobserve(point, primary_channel)
        for channel, state in self.state.items():
            if (channel == primary_channel or state.cleared or state.exhausted
                    or not state.discovered
                    or len(state.observations) >= self.coverage_observation_target):
                continue
            if any(math.dist(point, old) <= 1.0 for old in state.probed_points):
                continue
            if not self.within_reach(point, state):
                self.pruned_observations += 1
                continue
            result = self.observe(point, channel)
            if result in ("direction", "near"):
                state.attempts += 1
            self.co_measurements += 1
            self.coobservations += 1

    def search(self) -> None:
        origin = (0.0, 0.0)
        for channel, state in self.state.items():
            if not state.discovered:
                self.observe(origin, channel)
        self._coobserve(origin, -1)
        self.origin_discoveries = sum(state.discovered for state in self.state.values())

        selected = ("B" if self.origin_discoveries <= self.discovery_threshold else "C")
        self.selected_search_order = selected
        self.coverage_observation_target = (
            self.b_route_observation_target if selected == "B"
            else self.c_route_observation_target
        )
        self.search_points = list(self._routes()[selected])

        remaining = list(self.search_points[1:])
        while remaining and sum(state.discovered for state in self.state.values()) < 16:
            point = remaining.pop(0)
            for channel, state in self.state.items():
                if not state.discovered:
                    self.observe(point, channel)
            self._coobserve(point, -1)
            following = remaining[0] if remaining else None
            self._opportunistic_clear(following)
        self.search_end_time_s = self.sim.time_s


CPlus3FBAgent = DAgent


if __name__ == "__main__":
    print({name: len(route) for name, route in DAgent._routes().items()})

"""Q4 historical DO experiment: observation-conditioned route ordering.

Earlier result files use the legacy strategy label ``D1``.  The experiment is
called DO in current documentation so the D production-model name is unique.

The station set and all localisation/clearing behaviour are inherited from the
B model.  Only the order of the unvisited search stations changes.  After each
station, visibility hypotheses inconsistent with the accumulated no-signal
search history are removed and the remaining route is replanned.

The hypothesis model is a routing heuristic, not a stopping rule.  Every
remaining station stays mandatory unless 16 distinct sources have been found.
"""
from __future__ import annotations

import json
import math
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = Path(r"C:\Users\李\Desktop\第四问定向源实验")
MODEL_ROOT = (HERE.parent if (HERE.parent / "B模型").exists()
              else Path(r"C:\Users\李\Desktop\Q4保底基线"))
if str(EXP) not in sys.path:
    sys.path.insert(0, str(EXP))

from baseline_core import dist  # noqa: E402

_B_SPEC = importlib.util.spec_from_file_location(
    "q4_dynamic_baseline_b", MODEL_ROOT / "B模型" / "cert_route_agent.py")
_B_MODULE = importlib.util.module_from_spec(_B_SPEC)
_B_SPEC.loader.exec_module(_B_MODULE)
CertRouteAgent = _B_MODULE.CertRouteAgent


class FullPosteriorRollingAgent(CertRouteAgent):
    """Experimental full rolling planner retained as a negative ablation."""

    area_radius_m = 1800.0
    prior_mean_sources = tuple(range(10, 17))
    hypothesis_radial_bins = 15
    hypothesis_angular_bins = 60
    hypothesis_receive_radii = (1000.0, 1250.0, 1500.0)
    hypothesis_beam_directions = tuple(range(0, 360, 30))
    directional_prior = 0.5
    discovery_action_s = 6.0
    max_relocate_checks = 80
    reorder_margin_s = 0.5

    _pattern_cache = None
    _plan_cache = {}

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.dynamic_order_log = []
        self._site_index = {
            (round(point[0], 7), round(point[1], 7)): i
            for i, point in enumerate(self.search_points)
        }

    @classmethod
    def _visibility_patterns(cls, sites):
        """Aggregate prior hypotheses by their 27-bit station visibility mask."""
        if cls._pattern_cache is not None:
            return cls._pattern_cache
        weights = defaultdict(float)
        omni_weight = 1.0 - cls.directional_prior
        beam_weight = cls.directional_prior / len(cls.hypothesis_beam_directions)
        for ri in range(cls.hypothesis_radial_bins):
            # Equal-area radial strata; angular offset avoids spoke artefacts.
            radius = cls.area_radius_m * math.sqrt(
                (ri + 0.5) / cls.hypothesis_radial_bins)
            offset = (ri * 0.5) % 1.0
            for ai in range(cls.hypothesis_angular_bins):
                theta = 2.0 * math.pi * (ai + offset) / cls.hypothesis_angular_bins
                source = (radius * math.cos(theta), radius * math.sin(theta))
                for receive_radius in cls.hypothesis_receive_radii:
                    in_range = []
                    bearings = []
                    for station in sites:
                        dx, dy = station[0] - source[0], station[1] - source[1]
                        in_range.append(math.hypot(dx, dy) <= receive_radius + 1e-9)
                        bearings.append(math.degrees(math.atan2(dy, dx)) % 360.0)
                    omni_mask = sum((1 << i) for i, ok in enumerate(in_range) if ok)
                    if omni_mask:
                        weights[omni_mask] += omni_weight
                    for beam in cls.hypothesis_beam_directions:
                        mask = 0
                        for i, ok in enumerate(in_range):
                            delta = (bearings[i] - beam + 180.0) % 360.0 - 180.0
                            if ok and abs(delta) <= 90.0 + 1e-9:
                                mask |= 1 << i
                        if mask:
                            weights[mask] += beam_weight
        cls._pattern_cache = tuple(weights.items())
        return cls._pattern_cache

    @classmethod
    def _expected_remaining_sources(cls, discovered):
        possible = cls.prior_mean_sources
        return sum(max(0, total - discovered) for total in possible) / len(possible)

    @staticmethod
    def _travel_distance(position, route, sites):
        total = 0.0
        current = position
        for index in route:
            total += dist(current, sites[index])
            current = sites[index]
        return total

    @classmethod
    def _objective(cls, position, route, sites, survivors, hidden_sources):
        travel_s = cls._travel_distance(position, route, sites) / 5.0
        if not route or not survivors or hidden_sources <= 1e-12:
            return travel_s
        total_weight = sum(weight for _, weight in survivors)
        if total_weight <= 0.0:
            return travel_s
        expected_first = 0.0
        fallback = len(route) + 1
        for pattern, weight in survivors:
            first = fallback
            for rank, site in enumerate(route, 1):
                if pattern & (1 << site):
                    first = rank
                    break
            expected_first += weight * first
        expected_first /= total_weight
        return travel_s + cls.discovery_action_s * hidden_sources * expected_first

    @classmethod
    def _nearest_route(cls, position, remaining, sites):
        route, left, current = [], set(remaining), position
        while left:
            nxt = min(left, key=lambda i: (dist(current, sites[i]), i))
            route.append(nxt)
            left.remove(nxt)
            current = sites[nxt]
        return route

    @classmethod
    def _gain_route(cls, position, remaining, sites, survivors, hidden_sources):
        route, left, current = [], set(remaining), position
        active = list(survivors)
        while left:
            total = sum(weight for _, weight in active) or 1.0
            horizon = max(0, len(left) - 1)
            choices = []
            for site in left:
                visible = sum(weight for mask, weight in active
                              if mask & (1 << site)) / total
                saved_scans_s = (cls.discovery_action_s * hidden_sources
                                 * visible * horizon)
                key = dist(current, sites[site]) / 5.0 - saved_scans_s
                choices.append((key, dist(current, sites[site]), site))
            _, _, nxt = min(choices)
            route.append(nxt)
            left.remove(nxt)
            current = sites[nxt]
            active = [(mask, weight) for mask, weight in active
                      if not (mask & (1 << nxt))]
        return route

    @classmethod
    def _improve_relocate(cls, position, route, sites, survivors, hidden_sources):
        route = list(route)
        best = cls._objective(position, route, sites, survivors, hidden_sources)
        checks = 0
        improved = True
        while improved and checks < cls.max_relocate_checks:
            improved = False
            for old in range(len(route)):
                item = route[old]
                rest = route[:old] + route[old + 1:]
                for new in range(len(route)):
                    if new == old:
                        continue
                    candidate = rest[:new] + [item] + rest[new:]
                    value = cls._objective(
                        position, candidate, sites, survivors, hidden_sources)
                    checks += 1
                    if value < best - cls.reorder_margin_s:
                        route, best, improved = candidate, value, True
                        break
                    if checks >= cls.max_relocate_checks:
                        break
                if improved or checks >= cls.max_relocate_checks:
                    break
        return route, best

    def _plan_remaining(self, remaining, visited_mask):
        discovered = sum(st.discovered for st in self.state.values())
        current_key = (round(self.sim.position[0], 1), round(self.sim.position[1], 1))
        key = (tuple(sorted(remaining)), visited_mask, discovered, current_key)
        cached = self._plan_cache.get(key)
        if cached is not None:
            return list(cached)

        patterns = self._visibility_patterns(self.search_points)
        survivors = [(mask, weight) for mask, weight in patterns
                     if not (mask & visited_mask)]
        hidden = self._expected_remaining_sources(discovered)
        base = list(remaining)
        nearest = self._nearest_route(self.sim.position, remaining, self.search_points)
        gain = self._gain_route(
            self.sim.position, remaining, self.search_points, survivors, hidden)
        seeds = (base, nearest, gain)
        route = min(seeds, key=lambda candidate: self._objective(
            self.sim.position, candidate, self.search_points, survivors, hidden))
        route, score = self._improve_relocate(
            self.sim.position, route, self.search_points, survivors, hidden)
        self._plan_cache[key] = tuple(route)
        self.dynamic_order_log.append({
            "visited": visited_mask.bit_count(),
            "discovered": discovered,
            "surviving_patterns": len(survivors),
            "expected_hidden_sources": hidden,
            "objective_s": score,
            "next_site": route[0] if route else None,
        })
        return route

    def search(self) -> None:
        remaining = list(range(len(self.search_points)))
        visited_mask = 0
        while remaining and sum(st.discovered for st in self.state.values()) < 16:
            route = self._plan_remaining(remaining, visited_mask)
            site = route[0]
            point = self.search_points[site]
            for channel, st in self.state.items():
                if not st.discovered:
                    self.observe(point, channel)
            self._coobserve(point, -1)
            remaining.remove(site)
            visited_mask |= 1 << site

            following = None
            if remaining and sum(st.discovered for st in self.state.values()) < 16:
                following_route = self._plan_remaining(remaining, visited_mask)
                following = self.search_points[following_route[0]]
            self._opportunistic_clear(following)
            self.say(
                f"动态搜索点 {site + 1}/{len(self.search_points)} 完成，"
                f"已发现 {sum(st.discovered for st in self.state.values())} 个源，"
                f"虚拟时间 {self.sim.time_s:.1f}s")
        self.search_end_time_s = self.sim.time_s


class ObservationGatedOrderAgent(CertRouteAgent):
    """Choose B or B+ suffix after the origin scan using observed discoveries.

    A low discovery count at the origin is a direct warning that sources are
    distant, have small receive radii, or point away from the centre.  Those are
    exactly the cases where B's boundary-friendly order is preferable.  The
    gate changes only the order and never changes the stopping condition.
    """

    discovery_threshold = 0
    _bplus_indices = None

    def _bplus_order_indices(self):
        if self.__class__._bplus_indices is not None:
            return list(self.__class__._bplus_indices)
        data = json.loads((MODEL_ROOT / "B+模型" / "winner_design.json").read_text(
            encoding="utf-8"))
        ordered = [tuple(data["sites"][i]) for i in data["order"]]
        lookup = {(round(point[0], 7), round(point[1], 7)): i
                  for i, point in enumerate(self.search_points)}
        indices = [lookup[(round(point[0], 7), round(point[1], 7))]
                   for point in ordered]
        self.__class__._bplus_indices = tuple(indices)
        return indices

    def search(self) -> None:
        origin = self.search_points[0]
        for channel, st in self.state.items():
            if not st.discovered:
                self.observe(origin, channel)
        self._coobserve(origin, -1)
        discovered = sum(st.discovered for st in self.state.values())

        if discovered <= self.discovery_threshold:
            route = list(range(1, len(self.search_points)))
            selected = "B"
        else:
            route = [i for i in self._bplus_order_indices() if i != 0]
            selected = "B+"
        self.selected_search_order = selected
        self.origin_discoveries = discovered

        while route and sum(st.discovered for st in self.state.values()) < 16:
            site = route.pop(0)
            point = self.search_points[site]
            for channel, st in self.state.items():
                if not st.discovered:
                    self.observe(point, channel)
            self._coobserve(point, -1)
            following = self.search_points[route[0]] if route else None
            self._opportunistic_clear(following)
        self.search_end_time_s = self.sim.time_s


class GatedT0Agent(ObservationGatedOrderAgent):
    discovery_threshold = 0
    _bplus_indices = None


class GatedT1Agent(ObservationGatedOrderAgent):
    discovery_threshold = 1
    _bplus_indices = None


class GatedT2Agent(ObservationGatedOrderAgent):
    discovery_threshold = 2
    _bplus_indices = None


class GatedT3Agent(ObservationGatedOrderAgent):
    discovery_threshold = 3
    _bplus_indices = None


class DynamicDiscoveryOrderAgent(GatedT0Agent):
    """Historical DO agent: use B iff the origin scan discovers no source."""

    _bplus_indices = None


if __name__ == "__main__":
    design = json.loads((MODEL_ROOT / "B模型" / "winner_design.json").read_text(
        encoding="utf-8"))
    ordered = [tuple(design["sites"][i]) for i in design["order"]]
    patterns = FullPosteriorRollingAgent._visibility_patterns(ordered)
    print(f"sites={len(ordered)} aggregated_visibility_patterns={len(patterns)}")

"""C+ candidate: choose the B or C certified route after the origin scan."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL_ROOT = HERE / "models"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _load_agent_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_B = _load_agent_module(
    "q4_cplus_baseline_b", MODEL_ROOT / "B模型" / "cert_route_agent.py")
BaseAgent = _B.CertRouteAgent


class CPlusGateAgent(BaseAgent):
    """Use B when origin discoveries <= threshold, otherwise use C."""

    discovery_threshold = 0
    _route_cache = None

    @classmethod
    def _routes(cls):
        if cls._route_cache is not None:
            return cls._route_cache
        routes = {}
        for name, folder in (("B", "B模型"), ("C", "C模型")):
            data = json.loads((MODEL_ROOT / folder / "winner_design.json").read_text(
                encoding="utf-8"))
            sites = [tuple(point) for point in data["sites"]]
            routes[name] = [sites[index] for index in data["order"]]
        if routes["B"][0] != (0.0, 0.0) or routes["C"][0] != (0.0, 0.0):
            raise ValueError("B and C routes must share the origin as their first station")
        cls._route_cache = routes
        return routes

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.search_points = list(self._routes()["B"])
        self.origin_discoveries = None
        self.selected_search_order = None

    def search(self) -> None:
        origin = (0.0, 0.0)
        for channel, state in self.state.items():
            if not state.discovered:
                self.observe(origin, channel)
        self._coobserve(origin, -1)
        self.origin_discoveries = sum(
            state.discovered for state in self.state.values())

        selected = ("B" if self.origin_discoveries <= self.discovery_threshold
                    else "C")
        self.selected_search_order = selected
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
            self.say(
                f"C+ {selected}路线：原点发现{self.origin_discoveries}个，"
                f"当前共发现{sum(s.discovered for s in self.state.values())}个")
        self.search_end_time_s = self.sim.time_s


class CPlusGate0Agent(CPlusGateAgent):
    discovery_threshold = 0
    _route_cache = None


class CPlusGate1Agent(CPlusGateAgent):
    discovery_threshold = 1
    _route_cache = None


class CPlusGate2Agent(CPlusGateAgent):
    discovery_threshold = 2
    _route_cache = None


class CPlusGate3Agent(CPlusGateAgent):
    discovery_threshold = 3
    _route_cache = None


class CPlusAgent(CPlusGate0Agent):
    """Selected C+ model: threshold 0 after the origin scan."""

    _route_cache = None


if __name__ == "__main__":
    for cls in (CPlusGate0Agent, CPlusGate1Agent,
                CPlusGate2Agent, CPlusGate3Agent):
        routes = cls._routes()
        print(cls.__name__, {name: len(route) for name, route in routes.items()})

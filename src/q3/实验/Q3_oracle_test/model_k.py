"""Model K (conservative prototype): coverage-constrained online rolling route.

One scheduler over the union of mandatory coverage stops and source action
nodes.  The second-question four-metric selector, the clear rule and the
co-observation rules are inherited from J+ unchanged; only the order in which
coverage and clearing are executed changes.
"""
from __future__ import annotations

from baseline_core import dist
from model_jplus import JPlusAgent


class KAgent(JPlusAgent):
    max_actions = 500

    @staticmethod
    def _route_first(nodes, start):
        points = [node[1] for node in nodes]
        if len(points) <= 1:
            return nodes[0]
        remaining = set(range(len(points)))
        route = []
        current = start
        while remaining:
            nxt = min(remaining, key=lambda i: dist(current, points[i]))
            route.append(nxt)
            current = points[nxt]
            remaining.remove(nxt)

        def cost(order):
            pts = [start] + [points[i] for i in order]
            return sum(dist(a, b) for a, b in zip(pts, pts[1:]))

        improved = True
        while improved:
            improved = False
            old = cost(route)
            for i in range(len(route) - 1):
                for j in range(i + 2, len(route) + 1):
                    candidate = route[:i] + list(reversed(route[i:j])) + route[j:]
                    if cost(candidate) + 1e-9 < old:
                        route, improved = candidate, True
                        break
                if improved:
                    break
            if improved:
                continue
            old = cost(route)
            n = len(route)
            for seg_len in (1, 2, 3):
                for i in range(n - seg_len + 1):
                    segment = route[i:i + seg_len]
                    rest = route[:i] + route[i + seg_len:]
                    for j in range(len(rest) + 1):
                        for seg in (segment, segment[::-1]):
                            candidate = rest[:j] + seg + rest[j:]
                            if cost(candidate) + 1e-9 < old:
                                route, improved = candidate, True
                                break
                        if improved:
                            break
                    if improved:
                        break
                if improved:
                    break
        return nodes[route[0]]

    def run(self):
        self.sim.enter()
        pending = list(self.search_points)
        coverage_done = False
        actions = 0
        while actions < self.max_actions:
            nodes = [("cover", p, -1) for p in pending]
            for ch, st in self.state.items():
                if st.cleared or st.exhausted or not st.discovered:
                    continue
                center = self._clear_decision(st)
                if center is not None:
                    nodes.append(("clear", center, ch))
                    continue
                if st.attempts >= 10:
                    st.exhausted = True
                    continue
                q = self._next_measurement_point(st)
                if q is None:
                    st.exhausted = True
                    continue
                nodes.append(("measure", q, ch))
            if not nodes:
                break
            kind, point, ch = self._route_first(nodes, self.sim.position)
            if kind == "cover":
                for channel, st in self.state.items():
                    if not st.discovered:
                        self.observe(point, channel)
                self.max_coobservations = max(
                    self.coverage_extra_measure_budget,
                    min(6, sum(st.discovered and not st.cleared
                               for st in self.state.values()) // 3))
                self._coobserve(point, -1)
                pending = [p for p in pending if dist(p, point) > 1e-9]
            elif kind == "clear":
                st = self.state[ch]
                if self._try_clear(point, ch):
                    st.cleared = True
                self._coobserve(point, ch)
            else:
                st = self.state[ch]
                self.observe(point, ch)
                st.attempts += 1
                self._coobserve(point, ch)
            if sum(st.discovered for st in self.state.values()) >= 16:
                pending = []
            if not pending and not coverage_done:
                self.search_end_time_s = self.sim.time_s
                coverage_done = True
            actions += 1
        if not coverage_done:
            self.search_end_time_s = self.sim.time_s
        self.sim.exit()
        return self.summary()

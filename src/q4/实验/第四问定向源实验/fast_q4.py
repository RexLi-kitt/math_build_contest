"""Q4 fast candidates: L1100-family with an inner surround ring.

The L1100 lattice has a detection hole around radius 1000-1100: a source there
may have only the nearest r=1100 site within reach, and a beam pointing away
from it then stays hidden.  A small inner ring at r ~ 500 m seals that hole.
"""
from __future__ import annotations

import math

from baseline_core import AREA_R, add, dist, bearing, wrap, SPEED
from q4_experiment import Q4TriangularCoverageAgent
from feasible_region import predicted_circle


class L1100InnerMixin:
    inner_radius_m = 550.0
    inner_count = 6
    inner_phase_deg = 0.0

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        base = self._triangular_sites(self.lattice_side_m)
        inner = [add((0.0, 0.0), self.inner_radius_m,
                     self.inner_phase_deg + 360.0 * k / self.inner_count)
                 for k in range(self.inner_count)]
        self.search_points = [base[0], *inner, *base[1:]]


class L1100Inner3Agent(L1100InnerMixin, Q4TriangularCoverageAgent):
    lattice_side_m = 1100.0
    coverage_observation_target = 2
    inner_radius_m = 450.0
    inner_count = 3
    inner_phase_deg = 90.0


class L1100Inner6Agent(L1100InnerMixin, Q4TriangularCoverageAgent):
    lattice_side_m = 1100.0
    coverage_observation_target = 2
    inner_radius_m = 550.0
    inner_count = 6
    inner_phase_deg = 0.0


class L1100Inner6R300Agent(L1100InnerMixin, Q4TriangularCoverageAgent):
    lattice_side_m = 1100.0
    coverage_observation_target = 2
    inner_radius_m = 300.0
    inner_count = 6
    inner_phase_deg = 0.0


class L1000Inner3Agent(L1100InnerMixin, Q4TriangularCoverageAgent):
    lattice_side_m = 1000.0
    coverage_observation_target = 2
    inner_radius_m = 450.0
    inner_count = 3
    inner_phase_deg = 90.0


class CertifiedRingAgent(Q4TriangularCoverageAgent):
    """Certified surround sweep: alternating rings, TSP-ordered.

    A fine polar-grid audit must show max uncovered beam gap < 180 deg, so
    every directional source is front-faced at some stop.
    """

    coverage_observation_target = 2
    ring_spec = ((900.0, 8, 0.0), (1400.0, 8, 22.5), (1900.0, 8, 0.0), (2400.0, 8, 22.5))
    _order_cache: dict = {}

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        from certify import ring
        from strong_tsp import solve_tour
        key = self.ring_spec
        order = self._order_cache.get(key)
        if order is None:
            sites = [(0.0, 0.0)]
            for radius, count, offset in self.ring_spec:
                sites.extend(ring(radius, count, offset))
            rest = sites[1:]
            tour, _ = solve_tour(rest, start=(0.0, 0.0), restarts=40)
            order = [rest[i] for i in tour]
            self._order_cache[key] = order
        self.search_points = [(0.0, 0.0), *order]

    def _coverage_order(self, unvisited):
        # The precomputed TSP order is authoritative.
        return list(unvisited)


class H8Agent(CertifiedRingAgent):
    """Certified 31-site design: 6x1000 + 12x1400 + 12x2000, tour ~21.4 km."""

    ring_spec = ((1000.0, 6, 0.0), (1400.0, 12, 15.0), (2000.0, 12, 0.0))


class H7Agent(CertifiedRingAgent):
    """Certified 31-site design: 6x1000 + 6x1300 + 6x1600 + 6x1900 + 6x2200."""

    ring_spec = ((1000.0, 6, 0.0), (1300.0, 6, 30.0), (1600.0, 6, 0.0),
                 (1900.0, 6, 30.0), (2200.0, 6, 0.0))


class OpportunisticBudgetMixin:
    """Raise the on-the-way clearing detour budget during the sweep.

    The inherited rule (250 m) only fires when the enclosing circle is already
    <= 20 m.  A larger budget lets the sweep cash in sources that become
    clearable just as the route passes nearby, instead of paying for a
    dedicated clearing leg later.
    """

    opportunistic_budget_m = 500.0

    def _opportunistic_clear(self, next_point):
        if next_point is None:
            return
        considered = set()
        while True:
            choices = []
            for channel, st in self.state.items():
                if channel in considered or st.cleared or not st.discovered:
                    continue
                center = self._clear_decision(st)
                if center is None:
                    continue
                extra = (dist(self.sim.position, center) + dist(center, next_point)
                         - dist(self.sim.position, next_point))
                if extra <= self.opportunistic_budget_m:
                    choices.append((extra, channel, center))
            if not choices:
                return
            _, channel, center = min(choices)
            considered.add(channel)
            if self._try_clear(center, channel):
                self.state[channel].cleared = True


class H8Clear500Agent(OpportunisticBudgetMixin, H8Agent):
    opportunistic_budget_m = 500.0


class H8Clear900Agent(OpportunisticBudgetMixin, H8Agent):
    opportunistic_budget_m = 900.0


class L1100I3Clear500Agent(OpportunisticBudgetMixin, L1100Inner3Agent):
    opportunistic_budget_m = 500.0


class BeamAwareMixin:
    """Directional-visibility-aware measurement scoring.

    An observation (p, theta) proves the source beam half-plane contains p.  For
    a belief sample x the beam direction b must satisfy
    ``|wrap(bearing(x, p) - b)| <= 90`` for every observed station p, so the
    consistent b form an arc.  A candidate q returns a direction with
    probability equal to the fraction of that arc whose half-plane contains q
    (uniform beam prior).  Multiplying the range-receive probability by this
    visibility probability stops the localizer from spending trips behind the
    beam (the raw analytics showed 54% of post-search measures were no_signal).
    """

    beam_bins = 180
    min_directional_receive = 0.02
    beam_cache_entries = 256
    no_signal_safe_range_m = 900.0
    receive_visibility_floor = 0.0

    def _beam_tables(self, st, snapshot):
        cached = getattr(self, "_beam_table_cache", None)
        if cached is None:
            cached = self._beam_table_cache = {}
        key = id(snapshot)
        entry = cached.get(key)
        observations = tuple(st.observations)
        no_signals = tuple(st.no_signal_points)
        if (entry is not None and entry[0] == observations
                and entry[1] == no_signals):
            return entry[2]
        bins = self.beam_bins
        step = 360.0 / bins
        tables = []
        for x in snapshot.samples:
            dirs = [bearing(x, p) for p, _ in st.observations]
            blocked = [bearing(x, q) for q in no_signals
                       if dist(x, q) <= self.no_signal_safe_range_m]
            consistent = []
            for k in range(bins):
                b = (k + 0.5) * step
                if not all(abs(wrap(d - b)) <= 90.0 + 1e-9 for d in dirs):
                    consistent.append(False)
                    continue
                consistent.append(all(abs(wrap(s - b)) > 90.0 for s in blocked))
            total = sum(consistent)
            if total == 0:
                # Belief sample slightly off axis can make the strict sector
                # constraints empty; fall back to observations only.
                consistent = [all(abs(wrap(d - b)) <= 90.0 + 1e-9 for d in dirs)
                              for b in ((k + 0.5) * step for k in range(bins))]
                total = sum(consistent)
            prefix = [0]
            for k in range(2 * bins):
                prefix.append(prefix[-1] + (1 if consistent[k % bins] else 0))
            tables.append((prefix, total))
        if len(cached) > self.beam_cache_entries:
            cached.clear()
        cached[key] = (observations, no_signals, tables)
        return tables

    def _visibility_probability(self, table, x, q):
        prefix, total = table
        if total <= 0:
            return 0.0
        step = 360.0 / self.beam_bins
        delta = bearing(x, q) % 360.0
        k0 = int(math.floor(((delta - 90.0) % 360.0) / step))
        return (prefix[k0 + self.beam_bins] - prefix[k0]) / total

    def _raw_metrics(self, st, snapshot, candidate):
        samples = list(snapshot.samples)
        if not samples or not st.observations:
            return None
        tables = self._beam_tables(st, snapshot)
        p_rec = 0.0
        total_weight = 0.0
        receive = []
        qualities = []
        for x, weight, bounds, table in zip(samples, snapshot.weights,
                                            snapshot.radius_bounds, tables):
            total_weight += weight
            lower, upper = bounds
            d = dist(candidate, x)
            if d <= lower:
                p_range = 1.0
            elif d >= upper:
                p_range = 0.0
            else:
                p_range = (upper - d) / (upper - lower)
            if p_range > 0.0 and weight > 0.0:
                p_vis = self._visibility_probability(table, x, candidate)
                p_rec += weight * p_range * p_vis
                if p_vis >= self.receive_visibility_floor:
                    receive.append(x)
            candidate_angle = bearing(candidate, x)
            qualities.append(max(
                (math.sin(math.radians(wrap(bearing(station, x) - candidate_angle))) ** 2
                 for station, _ in st.observations), default=0.0))
        if total_weight <= 0.0 or not receive:
            return None
        p_rec /= total_weight
        if p_rec < self.min_directional_receive:
            return None
        circles = [predicted_circle(snapshot, candidate, bearing(candidate, x))
                   for x in receive]
        circles = [circle for circle in circles if math.isfinite(circle.radius_m)]
        if not circles:
            return None
        r_pred = sum(circle.radius_m for circle in circles) / len(circles)
        post_distance = sum(dist(candidate, circle.center) for circle in circles) / len(circles)
        path_distance = dist(self.sim.position, candidate) + post_distance
        direct_distance = dist(self.sim.position, snapshot.circle.center)
        if path_distance - direct_distance > self.max_extra_distance_m:
            return None
        return (sum(qualities) / len(qualities), p_rec,
                path_distance / SPEED + 6.0, r_pred)


class H8BeamAgent(BeamAwareMixin, H8Agent):
    """H8 with directional-visibility-aware localization scoring."""


class BeamChaseMixin(BeamAwareMixin):
    """Beam-aware D-opt measurement selection with a visible chase fallback.

    The inherited fallback selector (``SevenPointAgent._next_measurement_point``)
    picks the highest D-opt information rate and never asks whether the source
    can see the point at all.  Here every candidate's information rate is
    multiplied by its beam-visibility probability, no-signal probes steer the
    beam tables, and points along the last successful bearing are always in the
    candidate pool so a guaranteed-visible move exists after a failed probe.
    """

    min_candidate_visibility = 0.15
    score_visibility_weight = 1.0
    chase_steps_m = (150.0, 300.0, 450.0, 650.0)

    def _candidate_visibility(self, st, snapshot, q):
        if not snapshot.samples:
            return 1.0
        tables = self._beam_tables(st, snapshot)
        total = 0.0
        value = 0.0
        for x, weight, table in zip(snapshot.samples, snapshot.weights, tables):
            if weight <= 0.0:
                continue
            total += weight
            value += weight * self._visibility_probability(table, x, q)
        return value / total if total > 0.0 else 1.0

    def _next_measurement_point(self, st):
        recovery = self._degenerate_recovery_point(st)
        if recovery is not None:
            return recovery
        if len(st.observations) == 1:
            candidates = self._first_observation_candidates(st)
        else:
            estimate = self._least_squares_intersection(st.observations)
            if estimate is None or math.hypot(*estimate) > AREA_R * 1.2:
                candidates = self._first_observation_candidates(st)
            else:
                candidates = [add(estimate, radius, a)
                              for radius in (180.0, 300.0, 450.0)
                              for a in range(0, 360, 30)]
        if st.observations:
            p, theta = st.observations[-1]
            candidates.extend(add(p, step, theta) for step in self.chase_steps_m)
        snapshot = self._snapshot(st)
        best, best_score = None, -float("inf")
        fallback, fallback_vis = None, -1.0
        for q in candidates:
            if math.hypot(*q) > 2600:
                continue
            if any(dist(q, old) <= 1.0 for old in st.probed_points):
                continue
            visibility = self._candidate_visibility(st, snapshot, q)
            if visibility > fallback_vis:
                fallback, fallback_vis = q, visibility
            if visibility < self.min_candidate_visibility:
                continue
            rate = self._information_rate(st, q, dist(self.sim.position, q) / SPEED)
            score = rate if self.score_visibility_weight <= 0.0 else rate * visibility
            if score > best_score:
                best, best_score = q, score
        if best is not None:
            return best
        if fallback is not None:
            return fallback
        return super()._next_measurement_point(st)


class H8ChaseAgent(BeamChaseMixin, H8Agent):
    """H8 with visibility-weighted D-opt selection and bearing chase."""


class H8Filter03Agent(BeamChaseMixin, H8Agent):
    """Hard visibility filter 0.30, no chase, information rate unchanged."""

    min_candidate_visibility = 0.30
    score_visibility_weight = 0.0
    chase_steps_m = ()


class H8Filter05Agent(BeamChaseMixin, H8Agent):
    """Hard visibility filter 0.50, no chase, information rate unchanged."""

    min_candidate_visibility = 0.50
    score_visibility_weight = 0.0
    chase_steps_m = ()


class H8Filter03ChaseAgent(BeamChaseMixin, H8Agent):
    """Hard visibility filter 0.30 with the visible chase candidates kept."""

    min_candidate_visibility = 0.30
    score_visibility_weight = 0.0
    chase_steps_m = (150.0, 300.0, 450.0, 650.0)


class H8ActionRoutingAgent(H8Agent):
    """H8 clearing route anchored at the next action point (H-model style).

    RollingCoverage routes to the least-squares target anchor, which can sit
    behind the beam or far from where the next measurement actually happens.
    Routing to the action point (clear centre when ready, otherwise the next
    measurement point) aligns the tour with what the dog will execute.
    """

    def _route_anchor(self, st):
        center = self._clear_decision(st)
        if center is not None:
            return center
        old_log_size = len(self.selection_log)
        point = self._next_measurement_point(st)
        del self.selection_log[old_log_size:]
        if point is not None:
            return point
        return self._target_anchor(st)


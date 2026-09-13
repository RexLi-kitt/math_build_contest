"""Three agents used in the controlled A/B/C comparison."""
from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import permutations
from typing import Optional

from baseline_core import (AREA_R, ERROR_DEG, MIN_R, SPEED, ChannelState,
                           Point, SevenPointAgent, add, bearing, dist, wrap)
from feasible_region import (RegionSnapshot, build_region, build_region_cached,
                             predicted_circle, reception_probabilities)


@dataclass(frozen=True)
class SelectionDecision:
    position: Point
    score: float
    q_geo: float
    p_rec: float
    travel_s: float
    r_pred_m: float


class FeasibleRegionAgent(SevenPointAgent):
    """Q2 feasible-region localizer with the existing D-opt point selector."""

    clear_margin_m = 0.25

    def _snapshot(self, st: ChannelState) -> RegionSnapshot:
        return build_region_cached(st.observations, st.no_signal_points)

    def _belief_samples(self, st: ChannelState) -> list[Point]:
        samples = list(self._snapshot(st).samples)
        return samples or super()._belief_samples(st)

    def _target_anchor(self, st: ChannelState) -> Point:
        circle = self._snapshot(st).circle
        if math.isfinite(circle.radius_m):
            return circle.center
        return super()._target_anchor(st)

    def _clear_decision(self, st: ChannelState) -> Optional[Point]:
        if len(st.observations) < 2:
            return None
        circle = self._snapshot(st).circle
        if circle.radius_m <= 20.0 - self.clear_margin_m:
            return circle.center
        return None

    def _opportunistic_clear(self, next_point: Optional[Point]) -> None:
        if next_point is None:
            return
        considered: set[int] = set()
        while True:
            choices = []
            for channel, st in self.state.items():
                if channel in considered or st.cleared or not st.discovered:
                    continue
                center = self._clear_decision(st)
                if center is None:
                    continue
                extra = dist(self.sim.position, center) + dist(center, next_point) - dist(self.sim.position, next_point)
                if extra <= 250.0:
                    choices.append((extra, channel, center))
            if not choices:
                return
            _, channel, center = min(choices)
            considered.add(channel)
            if self._try_clear(center, channel):
                self.state[channel].cleared = True

    def localize_and_clear(self, channel: int) -> bool:
        st = self.state[channel]
        if st.cleared or not st.discovered:
            return st.cleared
        for _ in range(10):
            center = self._clear_decision(st)
            if center is not None and self._try_clear(center, channel):
                st.cleared = True
                return True
            q = self._next_measurement_point(st)
            if q is None:
                break
            self.observe(q, channel)
            st.attempts += 1
            if st.cleared:
                return True
        # The conservative region can be slightly enlarged by polygonal circle
        # approximation.  Exhaust without a speculative clear if it stays >20 m.
        st.exhausted = True
        return False


class Q2FourMetricAgent(FeasibleRegionAgent):
    """Q2 four-metric selector using the Q2 candidate generation on online history.

    Candidate generation follows the Q2 solver exactly: a coarse polar grid
    anchored on the first station (distances 200..1800 m, 60-degree steps), the
    top-two scored points refined at distance +-100 m and bearing +-10 degrees,
    and the final min-max normalisation and scoring recomputed on the refined
    set only.  The predicted-radius index is Q2's plain mean.  Only the belief
    samples (weighted online history instead of uniform offline samples) and the
    third metric (completion time from C+) remain online adaptations; both are
    documented.  The R_good band uses the range-based threshold so that it stays
    valid when online scores are negative (Q2's offline scores are positive).
    """

    weights = (0.35, 0.30, 0.15, 0.20)
    good_eta = 0.10
    coarse_distances = (200.0, 600.0, 1000.0, 1400.0, 1800.0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selection_log: list[SelectionDecision] = []

    @staticmethod
    def _normal(values: list[float], value: float) -> float:
        lo, hi = min(values), max(values)
        return 1.0 if hi <= lo else (value - lo) / (hi - lo)

    def _predicted_radius_stat(self, radii: list[float]) -> float:
        """Q2 uses the plain mean over guaranteed-receive samples."""
        return sum(radii) / len(radii)

    def _coarse_candidates(self, st: ChannelState) -> list[Point]:
        station, angle = st.observations[0]
        return [add(station, d, angle + offset)
                for d in self.coarse_distances for offset in range(0, 360, 60)]

    def _refine_candidates(self, st: ChannelState,
                           seeds: list[SelectionDecision]) -> list[Point]:
        station, _ = st.observations[0]
        points, seen = [], set()
        for item in seeds:
            base = bearing(station, item.position)
            d = dist(station, item.position)
            for dd in (max(50.0, d - 100.0), d, min(1800.0, d + 100.0)):
                for da in (-10.0, 0.0, 10.0):
                    q = add(station, dd, base + da)
                    key = (round(q[0], 9), round(q[1], 9))
                    if key not in seen:
                        seen.add(key)
                        points.append(q)
        return points

    def _raw_metrics(self, st: ChannelState, snapshot: RegionSnapshot,
                     candidate: Point) -> tuple[float, float, float, float] | None:
        samples = list(snapshot.samples)
        if not samples:
            return None
        receive = [target for target in samples if dist(candidate, target) <= MIN_R]
        if not receive:
            return None
        qualities, radii = [], []
        for target in samples:
            candidate_angle = bearing(candidate, target)
            quality = max((math.sin(math.radians(wrap(bearing(station, target) - candidate_angle))) ** 2
                           for station, _ in st.observations), default=0.0)
            qualities.append(quality)
        for target in receive:
            c = predicted_circle(snapshot, candidate, bearing(candidate, target))
            if math.isfinite(c.radius_m):
                radii.append(c.radius_m)
        if not radii:
            return None
        return (sum(qualities) / len(qualities), len(receive) / len(samples),
                dist(self.sim.position, candidate) / SPEED,
                self._predicted_radius_stat(radii))

    def _score_pool(self, st: ChannelState, snapshot: RegionSnapshot,
                    pool: list[Point]) -> list[SelectionDecision]:
        rows = []
        for q in pool:
            if math.hypot(*q) > 2600 or any(dist(q, old) <= 1.0 for old in st.probed_points):
                continue
            metrics = self._raw_metrics(st, snapshot, q)
            if metrics is not None:
                rows.append((q, *metrics))
        if not rows:
            return []
        columns = [[row[i] for row in rows] for i in range(1, 5)]
        scored = []
        for q, q_geo, p_rec, travel_s, r_pred in rows:
            normalized = [self._normal(columns[i], value)
                          for i, value in enumerate((q_geo, p_rec, travel_s, r_pred))]
            score = (self.weights[0] * normalized[0] + self.weights[1] * normalized[1]
                     - self.weights[2] * normalized[2] - self.weights[3] * normalized[3])
            scored.append(SelectionDecision(q, score, q_geo, p_rec, travel_s, r_pred))
        return scored

    def _select_from_scored(self, scored: list[SelectionDecision]) -> SelectionDecision:
        peak = max(item.score for item in scored)
        low = min(item.score for item in scored)
        # Range-based R_good band remains valid even when all scores are negative.
        threshold = peak - self.good_eta * (peak - low)
        return min((item for item in scored if item.score >= threshold),
                   key=lambda item: (item.travel_s, item.r_pred_m, -item.score))

    def _next_measurement_point(self, st: ChannelState) -> Optional[Point]:
        recovery = self._degenerate_recovery_point(st)
        if recovery is not None:
            return recovery
        snapshot = self._snapshot(st)
        coarse = self._score_pool(st, snapshot, self._coarse_candidates(st))
        if not coarse:
            return super()._next_measurement_point(st)
        seeds = sorted(coarse, key=lambda item: item.score, reverse=True)[:2]
        scored = self._score_pool(st, snapshot, self._refine_candidates(st, seeds))
        if not scored:
            scored = coarse
        decision = self._select_from_scored(scored)
        self.selection_log.append(decision)
        return decision.position


class CPlusAgent(Q2FourMetricAgent):
    """Paper-friendly C improvement: completion time and co-observation.

    The four-metric structure is unchanged.  Its third metric is the expected
    time from the current position through the candidate measurement to the
    predicted enclosing-circle centre.  At an active measurement stop, up to
    three other unresolved channels are observed when their guaranteed-receive
    probability and crossing geometry make the six-second stationary action
    worthwhile.
    """

    # Small paired training screen (seed 41001) selected this risk-aware setting;
    # it is subsequently evaluated on disjoint validation seeds.
    weights = (0.25, 0.25, 0.35, 0.15)
    max_extra_distance_m = 250.0
    coobserve_threshold = 0.035
    max_coobservations = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.co_measurements = 0

    def _raw_metrics(self, st: ChannelState, snapshot: RegionSnapshot,
                     candidate: Point) -> tuple[float, float, float, float] | None:
        samples = list(snapshot.samples)
        if not samples:
            return None
        receive = [target for target in samples if dist(candidate, target) <= MIN_R]
        if not receive:
            return None
        qualities = []
        for target in samples:
            candidate_angle = bearing(candidate, target)
            qualities.append(max(
                (math.sin(math.radians(wrap(bearing(station, target) - candidate_angle))) ** 2
                 for station, _ in st.observations), default=0.0))
        circles = [predicted_circle(snapshot, candidate, bearing(candidate, target))
                   for target in receive]
        circles = [circle for circle in circles if math.isfinite(circle.radius_m)]
        if not circles:
            return None
        r_pred = self._predicted_radius_stat([circle.radius_m for circle in circles])
        post_measure_distance = sum(dist(candidate, circle.center) for circle in circles) / len(circles)
        path_distance = dist(self.sim.position, candidate) + post_measure_distance
        direct_distance = dist(self.sim.position, snapshot.circle.center)
        if path_distance - direct_distance > self.max_extra_distance_m:
            return None
        finish_time_s = path_distance / SPEED + 6.0
        return (sum(qualities) / len(qualities), len(receive) / len(samples),
                finish_time_s, r_pred)

    def _coobserve(self, point: Point, primary_channel: int) -> None:
        choices = []
        for channel, st in self.state.items():
            if channel == primary_channel or st.cleared or st.exhausted or not st.discovered:
                continue
            if len(st.observations) >= 5 or any(dist(point, old) <= 1.0 for old in st.probed_points):
                continue
            if self._clear_decision(st) is not None:
                continue
            snapshot = self._snapshot(st)
            samples = list(snapshot.samples)
            if not samples:
                continue
            receive = [target for target in samples if dist(point, target) <= MIN_R]
            p_rec = len(receive) / len(samples)
            if p_rec < 0.60:
                continue
            quality = sum(max(
                (math.sin(math.radians(wrap(bearing(station, target) - bearing(point, target)))) ** 2
                 for station, _ in st.observations), default=0.0)
                for target in receive) / len(receive)
            value_per_second = p_rec * quality / 6.0
            if value_per_second >= self.coobserve_threshold:
                choices.append((value_per_second, channel))
        for _, channel in sorted(choices, reverse=True)[:self.max_coobservations]:
            self.observe(point, channel)
            self.state[channel].attempts += 1
            self.co_measurements += 1

    def localize_and_clear(self, channel: int) -> bool:
        st = self.state[channel]
        if st.cleared or not st.discovered:
            return st.cleared
        for _ in range(10):
            center = self._clear_decision(st)
            if center is not None and self._try_clear(center, channel):
                st.cleared = True
                return True
            q = self._next_measurement_point(st)
            if q is None:
                break
            self.observe(q, channel)
            st.attempts += 1
            self._coobserve(q, channel)
            if st.cleared:
                return True
        st.exhausted = True
        return False


class CoverageIntegratedAgent(CPlusAgent):
    """C+ with coverage-order control and low-detour Q2 task insertion.

    All seven coverage sites remain mandatory unless the known upper bound of
    sixteen sources has already been reached.  Q2 only proposes single-source
    measurement sites; this Q3 layer decides when a proposal is cheap enough to
    insert into the remaining coverage route.
    """

    # Risk-aware screen selected 140 m / 8 insertions: the 12-insertion option
    # had a slightly lower training mean but a materially worse CVaR90 tail.
    insertion_budget_m = 140.0
    max_coverage_insertions = 8
    coverage_extra_measure_budget = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.coverage_insertions = 0

    def _coverage_order(self, unvisited: list[Point]) -> list[Point]:
        if len(unvisited) <= 1:
            return list(unvisited)
        anchors = [self._target_anchor(st) for st in self.state.values()
                   if st.discovered and not st.cleared and not st.exhausted]
        best_order, best_cost = None, math.inf
        for order in permutations(unvisited):
            path = [self.sim.position, *order]
            cost = sum(dist(a, b) for a, b in zip(path, path[1:]))
            # Preserve a short coverage route while choosing its finishing side
            # to be useful for the already discovered targets.
            if anchors:
                cost += min(dist(order[-1], anchor) for anchor in anchors)
            if cost < best_cost - 1e-6:
                best_order, best_cost = order, cost
        return list(best_order) if best_order is not None else list(unvisited)

    def _insertion_before(self, next_coverage: Point) -> Optional[tuple[int, Point]]:
        if self.coverage_insertions >= self.max_coverage_insertions:
            return None
        choices = []
        direct = dist(self.sim.position, next_coverage)
        for channel, st in self.state.items():
            if st.cleared or st.exhausted or not st.discovered or st.attempts >= 10:
                continue
            if self._clear_decision(st) is not None:
                continue
            old_log_size = len(self.selection_log)
            point = self._next_measurement_point(st)
            decision = self.selection_log[-1] if len(self.selection_log) > old_log_size else None
            del self.selection_log[old_log_size:]
            if point is None:
                continue
            extra = dist(self.sim.position, point) + dist(point, next_coverage) - direct
            if extra > self.insertion_budget_m:
                continue
            if decision is not None:
                shrink = max(0.0, self._snapshot(st).circle.radius_m - decision.r_pred_m)
                rank = extra / (1.0 + min(shrink, 300.0) / 100.0)
            else:
                rank = extra
            choices.append((rank, extra, channel, point))
        if not choices:
            return None
        _, _, channel, point = min(choices)
        return channel, point

    def _orient_coverage_ring(self) -> None:
        """Hook to rotate/resize the coverage ring after the origin scan."""

    def search(self) -> None:
        # The origin is fixed; the six ring sites remain an explicit coverage set.
        origin = self.search_points[0]
        for channel, st in self.state.items():
            if not st.discovered:
                self.observe(origin, channel)
        self._coobserve(origin, -1)
        self._orient_coverage_ring()
        self.say(f"搜索点 {origin!r} 完成，虚拟时间 {self.sim.time_s:.1f}s")

        unvisited = list(self.search_points[1:])
        while unvisited and sum(st.discovered for st in self.state.values()) < 16:
            next_coverage = self._coverage_order(unvisited)[0]
            insertion = self._insertion_before(next_coverage)
            if insertion is not None:
                channel, point = insertion
                self.observe(point, channel)
                self.state[channel].attempts += 1
                self.coverage_insertions += 1
                self._coobserve(point, channel)
                self._opportunistic_clear(next_coverage)
                continue

            # Unknown channels must be tested at every coverage site.  Already
            # discovered channels compete for a bounded stationary-measurement
            # budget through the inherited C+ co-observation rule.
            for channel, st in self.state.items():
                if not st.discovered:
                    self.observe(next_coverage, channel)
            # More discovered sources make stationary measurements more
            # valuable because they replace many later dedicated trips.
            self.max_coobservations = max(
                self.coverage_extra_measure_budget,
                min(6, sum(st.discovered and not st.cleared for st in self.state.values()) // 3),
            )
            self._coobserve(next_coverage, -1)
            unvisited.remove(next_coverage)
            following = self._coverage_order(unvisited)[0] if unvisited else None
            self._opportunistic_clear(following)
            self.say(f"搜索点 {next_coverage!r} 完成，虚拟时间 {self.sim.time_s:.1f}s")
        self.search_end_time_s = self.sim.time_s


class HybridBeliefRollingAgent(CPlusAgent):
    """Hybrid belief map, active sensing, and risk-constrained rolling plan."""

    min_active_receive_probability = 0.60

    @staticmethod
    def _weighted_quantile(values: list[tuple[float, float]], probability: float) -> float:
        ordered = sorted(values)
        threshold = probability * sum(weight for _, weight in ordered)
        cumulative = 0.0
        for value, weight in ordered:
            cumulative += weight
            if cumulative >= threshold:
                return value
        return ordered[-1][0]

    def _raw_metrics(self, st: ChannelState, snapshot: RegionSnapshot,
                     candidate: Point) -> tuple[float, float, float, float] | None:
        if not snapshot.samples:
            return None
        receive_probabilities = reception_probabilities(snapshot, candidate)
        p_rec = sum(weight * probability for weight, probability
                    in zip(snapshot.weights, receive_probabilities))
        if p_rec < self.min_active_receive_probability:
            return None
        q_geo = 0.0
        predicted = []
        for target, belief_weight, receive_probability in zip(
                snapshot.samples, snapshot.weights, receive_probabilities):
            candidate_angle = bearing(candidate, target)
            quality = max(
                (math.sin(math.radians(wrap(bearing(station, target) - candidate_angle))) ** 2
                 for station, _ in st.observations), default=0.0)
            q_geo += belief_weight * quality
            conditional_weight = belief_weight * receive_probability
            if conditional_weight > 0.0:
                circle = predicted_circle(snapshot, candidate, candidate_angle)
                if math.isfinite(circle.radius_m):
                    predicted.append((circle, conditional_weight))
        if not predicted:
            return None
        weight_sum = sum(weight for _, weight in predicted)
        r90 = self._weighted_quantile(
            [(circle.radius_m, weight) for circle, weight in predicted], .90)
        post_distance = sum(dist(candidate, circle.center) * weight
                            for circle, weight in predicted) / weight_sum
        path_distance = dist(self.sim.position, candidate) + post_distance
        direct_distance = dist(self.sim.position, snapshot.circle.center)
        if path_distance - direct_distance > self.max_extra_distance_m:
            return None
        return q_geo, p_rec, path_distance / SPEED + 6.0, r90

    def _coobserve(self, point: Point, primary_channel: int) -> None:
        choices = []
        for channel, st in self.state.items():
            if channel == primary_channel or st.cleared or st.exhausted or not st.discovered:
                continue
            if len(st.observations) >= 5 or any(dist(point, old) <= 1.0 for old in st.probed_points):
                continue
            if self._clear_decision(st) is not None:
                continue
            snapshot = self._snapshot(st)
            if not snapshot.samples:
                continue
            receive_probabilities = reception_probabilities(snapshot, point)
            p_rec = sum(weight * probability for weight, probability
                        in zip(snapshot.weights, receive_probabilities))
            if p_rec < self.min_active_receive_probability:
                continue
            quality = sum(
                weight * max(
                    (math.sin(math.radians(wrap(bearing(station, target) - bearing(point, target)))) ** 2
                     for station, _ in st.observations), default=0.0)
                for target, weight in zip(snapshot.samples, snapshot.weights))
            value_per_second = p_rec * quality / 6.0
            if value_per_second >= self.coobserve_threshold:
                choices.append((value_per_second, channel))
        for _, channel in sorted(choices, reverse=True)[:self.max_coobservations]:
            self.observe(point, channel)
            self.state[channel].attempts += 1
            self.co_measurements += 1

    def run(self) -> dict:
        """Route-guided receding horizon: execute one action, then re-plan."""
        self.sim.enter()
        self.search()
        for _ in range(240):
            unresolved = [(channel, st) for channel, st in self.state.items()
                          if st.discovered and not st.cleared and not st.exhausted]
            if not unresolved:
                break
            # The open 2-opt/Or-opt route supplies global direction.  Only its
            # first channel executes one clear or measurement action, after
            # which updated beliefs are routed again.
            channel = self._two_opt_route([item[0] for item in unresolved])[0]
            st = self.state[channel]
            center = self._clear_decision(st)
            if center is not None:
                if self._try_clear(center, channel):
                    st.cleared = True
                    self._coobserve(center, channel)
                continue
            if st.attempts >= 10:
                st.exhausted = True
                continue
            point = self._next_measurement_point(st)
            if point is None:
                st.exhausted = True
                continue
            self.observe(point, channel)
            st.attempts += 1
            self._coobserve(point, channel)
        self.sim.exit()
        return self.summary()


class _MarginalInsertionMixin:
    """Replace F's fixed detour/budget caps with a marginal-benefit criterion.

    A proposal is inserted before the next coverage site only when the
    predicted enclosing-circle shrinkage per extra metre travelled clears
    ``benefit_lambda``; the number of insertions is capped dynamically by the
    number of currently unresolved sources instead of a constant.
    """

    max_extra_distance_m = 250.0
    benefit_lambda = 0.30
    max_dynamic_insertions = 14

    def _insertion_before(self, next_coverage: Point) -> Optional[tuple[int, Point]]:
        unresolved = sum(
            st.discovered and not st.cleared and not st.exhausted
            for st in self.state.values())
        cap = min(self.max_dynamic_insertions,
                  self.max_coverage_insertions + unresolved)
        if self.coverage_insertions >= cap:
            return None
        direct = dist(self.sim.position, next_coverage)
        choices = []
        for channel, st in self.state.items():
            if st.cleared or st.exhausted or not st.discovered or st.attempts >= 10:
                continue
            if self._clear_decision(st) is not None:
                continue
            old_log_size = len(self.selection_log)
            point = self._next_measurement_point(st)
            decision = self.selection_log[-1] if len(self.selection_log) > old_log_size else None
            del self.selection_log[old_log_size:]
            if point is None or decision is None:
                continue
            extra = dist(self.sim.position, point) + dist(point, next_coverage) - direct
            if extra > self.max_extra_distance_m:
                continue
            shrink = max(0.0, self._snapshot(st).circle.radius_m - decision.r_pred_m)
            ratio = float("inf") if extra <= 1e-9 else shrink / extra
            if ratio >= self.benefit_lambda:
                choices.append((-ratio, extra, channel, point))
        if not choices:
            return None
        _, _, channel, point = min(choices)
        return channel, point


class RollingCoverageAgent(CoverageIntegratedAgent):
    """Model G: coverage-integrated search with per-action rolling clearing.

    The discovery, insertion and co-observation structure is inherited from F
    unchanged, so both models share an identical search phase
    (``search_end_time_s`` matches).  Only the clearing stage differs: instead
    of localising and clearing one whole source before considering the next,
    this model runs a receding-horizon schedule.  At every step the remaining
    unresolved sources are re-routed with the open nearest-neighbour +
    2-opt/Or-opt planner, only the first target of that route executes a single
    clear or measurement action, and the route is re-planned from the updated
    beliefs.  Any measured gain therefore comes solely from the clearing
    schedule, which keeps the ablation with F clean.
    """

    def run(self) -> dict:
        self.sim.enter()
        self.search()
        for _ in range(240):
            unresolved = [channel for channel, st in self.state.items()
                          if st.discovered and not st.cleared and not st.exhausted]
            if not unresolved:
                break
            # Global direction from the open route, one action of look-ahead.
            channel = self._two_opt_route(unresolved)[0]
            st = self.state[channel]
            center = self._clear_decision(st)
            if center is not None:
                if self._try_clear(center, channel):
                    st.cleared = True
                    self._coobserve(center, channel)
                continue
            if st.attempts >= 10:
                st.exhausted = True
                continue
            point = self._next_measurement_point(st)
            if point is None:
                st.exhausted = True
                continue
            self.observe(point, channel)
            st.attempts += 1
            self._coobserve(point, channel)
        self.sim.exit()
        return self.summary()


class TaskSchedulingAgent(RollingCoverageAgent):
    """Model H: rolling task scheduling over actual action points.

    Two corrections over G, both derived from the same scheduling objective:

    1. Routing nodes are the *next action points* (clear centre when the source
       is clearable, otherwise the Q2 recommended measurement point) instead of
       target anchors.  The 100-case screen showed the anchor/action mismatch
       has P90 = 594 m, so G orders a proxy problem the dog does not execute.
    2. Near-terminal non-preemption: after a measurement leaves a source with
       ``r <= ready_radius_m`` one action away from clearing, that source stays
       first in the schedule until cleared or exhausted.  Pure per-action
       rolling had 38% of sources left and revisited, each revisit paying a
       re-approach leg.
    """

    ready_radius_m = 60.0
    use_action_nodes = True

    def _route_anchor(self, st: ChannelState) -> Point:
        if not self.use_action_nodes:
            return self._target_anchor(st)
        center = self._clear_decision(st)
        if center is not None:
            return center
        old_log_size = len(self.selection_log)
        point = self._next_measurement_point(st)
        del self.selection_log[old_log_size:]
        if point is not None:
            return point
        return self._target_anchor(st)

    def run(self) -> dict:
        self.sim.enter()
        self.search()
        sticky: Optional[int] = None
        for _ in range(240):
            unresolved = [channel for channel, st in self.state.items()
                          if st.discovered and not st.cleared and not st.exhausted]
            if not unresolved:
                break
            if sticky is not None:
                st = self.state.get(sticky)
                if st is None or st.cleared or st.exhausted or not st.discovered:
                    sticky = None
            if sticky is None:
                channel = self._two_opt_route(unresolved)[0]
            else:
                channel = sticky
            st = self.state[channel]
            center = self._clear_decision(st)
            if center is not None:
                if self._try_clear(center, channel):
                    st.cleared = True
                    self._coobserve(center, channel)
                continue
            if st.attempts >= 10:
                st.exhausted = True
                continue
            point = self._next_measurement_point(st)
            if point is None:
                st.exhausted = True
                continue
            self.observe(point, channel)
            st.attempts += 1
            self._coobserve(point, channel)
            # Non-preemption: finishing a near-terminal source costs one action,
            # while switching pays a re-approach leg.
            if (not st.cleared and not st.exhausted
                    and self._snapshot(st).circle.radius_m <= self.ready_radius_m):
                sticky = channel
        self.sim.exit()
        return self.summary()


class MarginalInsertionAgent(_MarginalInsertionMixin, CoverageIntegratedAgent):
    """Ablation: F with the marginal-benefit insertion rule only.

    Kept for the paper's negative ablation: the ratio test replaces F's fixed
    detour/count caps but over-inserts in practice, so it is not adopted.
    """


class MarginalRollingAgent(_MarginalInsertionMixin, RollingCoverageAgent):
    """Ablation: marginal insertion combined with per-action rolling."""


class ActionNodeOnlyAgent(TaskSchedulingAgent):
    """Ablation: action-point routing only, preemption unchanged."""

    ready_radius_m = -1.0


class NonPreemptionOnlyAgent(TaskSchedulingAgent):
    """Ablation: near-terminal non-preemption only, anchor routing kept."""

    use_action_nodes = False


class RingOptimizedAgent(RollingCoverageAgent):
    """Model I: coverage-ring radius reduction with a proven detection guarantee.

    With centre + six ring sites the worst point of the task disk lies on the
    boundary halfway between adjacent ring sites, at distance

        d(R) = sqrt(1800^2 + R^2 - 2 * 1800 * R * cos(30 deg)).

    Detection only requires d(R) <= 1000 m, which holds for R >= 1123 m.  The
    original R = 1250 m gives 951.6 m but a 7500 m ring tour; R = 1150 m gives
    988.5 m and a 6900 m tour, saving 600 m ~ 120 s per episode without any loss
    of coverage.  Bearing-aligned rotation of the ring was tested separately and
    rejected (see the negative ablation below).
    """

    search_ring_r = 1150.0


class JCompactRingAgent(RingOptimizedAgent):
    """Model J: compact seven-point coverage ring at R = 1000 m.

    Only the discovery layer changes relative to I.  With the origin stop plus
    k evenly spaced ring stops of radius R, the worst point of the task disk
    lies on the boundary half-way between adjacent ring stops:

        d_k(R) = sqrt(1800^2 + R^2 - 2 * 1800 * R * cos(pi / k)).

    Detection only requires d_k(R) <= 1000 (every receive radius is >= 1000 m),
    which gives the minimum feasible radius

        R_min(k) = 1800 cos(pi/k) - sqrt(3240000 cos^2(pi/k) - 2240000):

    R_min(6) = 1122.9 m, R_min(7) = 997.2 m, R_min(8) = 938.1 m.  The open
    sweep path is R * (1 + 2(k-1) sin(pi/k)), so k=7 at R=1000 sweeps 6207 m
    instead of 6900 m for I.  Each extra stop costs one more scan of the
    still-undiscovered channels (~60 s per episode): k=6 -> 7 saves 106 s of
    movement and pays ~61 s of scanning, while k=7 -> 8 saves only 49 s and
    still pays ~60 s, so the joint (k, R) optimum is k=7 at R ~= 1000 (worst
    coverage 998.25 m, 1.75 m margin; the centre is covered by the origin
    stop).  Three paired 1000-case seeds: 298.2 s/source vs 306.0 for I, all
    clears 100%.
    """

    search_ring_r = 1000.0
    ring_count = 7

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        step = 360.0 / self.ring_count
        self.search_points = [(0.0, 0.0)] + [
            add((0.0, 0.0), self.search_ring_r, step * k)
            for k in range(self.ring_count)
        ]


class JPlusAgent(JCompactRingAgent):
    """Model J+ (final): J with the measurement-scheduling correction.

    Two changes, both confined to where measurements are taken:

    1. No measurement detours during the coverage sweep: the Q2 recommended
       points are taken later, on the way, inside the rolling clearing route.
       Under the compact ring the sweep is already close to the sources, so a
       mid-sweep detour costs more than it saves; the insertion mechanism came
       from the old R = 1250 geometry, where the trade-off was the opposite.
    2. The Q2 four-metric weights are re-calibrated to equal weights and the
       per-stop co-observation budget is raised from 3 to 5.

    Three paired 1000-case seeds against J: 293.5 vs 298.2 s/source (-4.7,
    95% CI [3.7, 5.8]), P95 367.8 vs 375.3, all clears 100% (3000/3000).
    """

    def _insertion_before(self, next_coverage):
        return None

    weights = (0.25, 0.25, 0.25, 0.25)
    coverage_extra_measure_budget = 5


class AblationRing8Agent(JCompactRingAgent):
    """Negative ablation: eight-point ring at R = 950 m.

    Saves a further 49 s of movement per episode but adds one more full scan
    round of the undiscovered channels (~60 s), so it is slower than k=7.
    """

    search_ring_r = 950.0
    ring_count = 8


class RotatedRingAblationAgent(RollingCoverageAgent):
    """Negative ablation: bearing-aligned ring rotation at the original radius.

    The seven-site covering radius is rotation invariant, so alignment is safe
    in principle, but the 100-case pairing showed it clearly hurts (6/20 wins on
    the screen) because the angular-gap objective ignores the route geometry.
    """

    def _orient_coverage_ring(self) -> None:
        bearings = []
        for st in self.state.values():
            if st.discovered and st.observations:
                station, angle = st.observations[0]
                if dist(station, (0.0, 0.0)) <= 1.0:
                    bearings.append(angle)
        if not bearings:
            return
        best_theta, best_cost = 0.0, math.inf
        for step in range(0, 60, 5):
            theta = float(step)
            cost = 0.0
            for angle in bearings:
                gap = min(abs(wrap(angle - (theta + 60.0 * k))) for k in range(6))
                cost += gap
            if cost < best_cost - 1e-9:
                best_theta, best_cost = theta, cost
        self._set_ring_rotation(best_theta)


STRATEGIES = {
    "A_current_ls_dopt": SevenPointAgent,
    "B_region_dopt": FeasibleRegionAgent,
    "C_region_q2": Q2FourMetricAgent,
    "Cplus_completion_coobserve": CPlusAgent,
    "F_coverage_integrated": CoverageIntegratedAgent,
    "G_rolling_coverage": RollingCoverageAgent,
    "H_task_scheduling": TaskSchedulingAgent,
    "I_ring_optimized": RingOptimizedAgent,
    "J_ring7_1000": JCompactRingAgent,
    "Jplus_final": JPlusAgent,
    "D_hybrid_belief_rolling": HybridBeliefRollingAgent,
    "Ablation_action_nodes_only": ActionNodeOnlyAgent,
    "Ablation_non_preemption_only": NonPreemptionOnlyAgent,
    "Ablation_ring_rotation": RotatedRingAblationAgent,
    "Ablation_ring8_950": AblationRing8Agent,
    "Ablation_marginal_insertion": MarginalInsertionAgent,
    "Ablation_marginal_rolling": MarginalRollingAgent,
}

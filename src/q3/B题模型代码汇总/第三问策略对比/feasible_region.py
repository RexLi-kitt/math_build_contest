"""Fast conservative feasible-region updates for the Q2/Q3 comparison.

The outer polygon always contains every source consistent with the deterministic
parts of the observations.  A no-signal observation creates a non-convex hole;
the hole is therefore applied to belief samples, while the outer polygon remains
conservative for the clear decision.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

Point = tuple[float, float]
AREA_R = 1800.0
MAX_DIRECTION_R = 1500.0
GUARANTEE_R = 1000.0
ERROR_DEG = 1.0


@dataclass(frozen=True)
class EnclosingCircle:
    center: Point
    radius_m: float


@dataclass(frozen=True)
class RegionSnapshot:
    polygon: tuple[Point, ...]
    circle: EnclosingCircle
    samples: tuple[Point, ...]
    weights: tuple[float, ...]
    radius_bounds: tuple[tuple[float, float], ...]


def _clip(poly: list[Point], a: float, b: float, c: float) -> list[Point]:
    if not poly:
        return []
    out: list[Point] = []
    previous = poly[-1]
    previous_value = a * previous[0] + b * previous[1] - c
    for current in poly:
        current_value = a * current[0] + b * current[1] - c
        previous_inside = previous_value <= 1e-8
        current_inside = current_value <= 1e-8
        if previous_inside != current_inside:
            denominator = previous_value - current_value
            t = previous_value / denominator
            out.append((previous[0] + t * (current[0] - previous[0]),
                        previous[1] + t * (current[1] - previous[1])))
        if current_inside:
            out.append(current)
        previous, previous_value = current, current_value
    return out


_TANGENT_CACHE: dict[int, tuple[tuple[float, float], ...]] = {}


def _tangent_dirs(sides: int) -> tuple[tuple[float, float], ...]:
    """Cached outward normal (cos, sin) of every tangent line of a sides-gon."""
    dirs = _TANGENT_CACHE.get(sides)
    if dirs is None:
        dirs = tuple((math.cos(2 * math.pi * k / sides), math.sin(2 * math.pi * k / sides))
                     for k in range(sides))
        _TANGENT_CACHE[sides] = dirs
    return dirs


def _outer_circle_polygon(center: Point, radius: float, sides: int = 72) -> list[Point]:
    vertex_radius = radius / math.cos(math.pi / sides)
    return [(center[0] + vertex_radius * math.cos(2 * math.pi * (k + .5) / sides),
             center[1] + vertex_radius * math.sin(2 * math.pi * (k + .5) / sides))
            for k in range(sides)]


def _clip_outer_circle(poly: list[Point], center: Point, radius: float,
                       sides: int = 72) -> list[Point]:
    if not poly:
        return []
    cx, cy = center
    # If every vertex already lies inside the inscribed disk it is also inside
    # the circumscribed polygon, so the whole 72-side clip is a no-op.
    limit = radius * radius + 1e-9
    inside = True
    for x, y in poly:
        dx, dy = x - cx, y - cy
        if dx * dx + dy * dy > limit:
            inside = False
            break
    if inside:
        return poly
    # Inline the Sutherland-Hodgman half-plane step to avoid one function call
    # per tangent line (the dominant cost when this runs millions of times).
    for a, b in _tangent_dirs(sides):
        c = radius + a * cx + b * cy
        out: list[Point] = []
        previous = poly[-1]
        previous_value = a * previous[0] + b * previous[1] - c
        for current in poly:
            current_value = a * current[0] + b * current[1] - c
            previous_inside = previous_value <= 1e-8
            current_inside = current_value <= 1e-8
            if previous_inside != current_inside:
                denominator = previous_value - current_value
                t = previous_value / denominator
                out.append((previous[0] + t * (current[0] - previous[0]),
                            previous[1] + t * (current[1] - previous[1])))
            if current_inside:
                out.append(current)
            previous, previous_value = current, current_value
        poly = out
        if not poly:
            break
    return poly


def _clip_bearing(poly: list[Point], station: Point, angle_deg: float) -> list[Point]:
    lower = math.radians(angle_deg - ERROR_DEG)
    upper = math.radians(angle_deg + ERROR_DEG)
    for a, b in ((math.sin(lower), -math.cos(lower)),
                 (-math.sin(upper), math.cos(upper))):
        poly = _clip(poly, a, b, a * station[0] + b * station[1])
    return poly


def _circle_two(a: Point, b: Point) -> EnclosingCircle:
    center = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return EnclosingCircle(center, math.dist(center, a))


def _circle_three(a: Point, b: Point, c: Point) -> EnclosingCircle | None:
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-10:
        return None
    aa, bb, cc = a[0] ** 2 + a[1] ** 2, b[0] ** 2 + b[1] ** 2, c[0] ** 2 + c[1] ** 2
    center = ((aa * (b[1] - c[1]) + bb * (c[1] - a[1]) + cc * (a[1] - b[1])) / d,
              (aa * (c[0] - b[0]) + bb * (a[0] - c[0]) + cc * (b[0] - a[0])) / d)
    return EnclosingCircle(center, math.dist(center, a))


_SHUFFLE_CACHE: dict[int, tuple[int, ...]] = {}


def _shuffle_order(n: int) -> tuple[int, ...]:
    """Cached index permutation equivalent to ``random.Random(0).shuffle``."""
    order = _SHUFFLE_CACHE.get(n)
    if order is None:
        indices = list(range(n))
        random.Random(0).shuffle(indices)
        order = tuple(indices)
        _SHUFFLE_CACHE[n] = order
    return order


def minimum_enclosing_circle(points: list[Point]) -> EnclosingCircle:
    """Deterministic randomized incremental minimum enclosing circle."""
    if not points:
        return EnclosingCircle((0.0, 0.0), math.inf)
    pts = [points[i] for i in _shuffle_order(len(points))]
    circle = EnclosingCircle(pts[0], 0.0)
    for i, p in enumerate(pts):
        if math.dist(p, circle.center) <= circle.radius_m + 1e-7:
            continue
        circle = EnclosingCircle(p, 0.0)
        for j, q in enumerate(pts[:i]):
            if math.dist(q, circle.center) <= circle.radius_m + 1e-7:
                continue
            circle = _circle_two(p, q)
            for r in pts[:j]:
                if math.dist(r, circle.center) <= circle.radius_m + 1e-7:
                    continue
                candidate = _circle_three(p, q, r)
                if candidate is not None:
                    circle = candidate
    return circle


def _inside_convex(poly: list[Point], point: Point) -> bool:
    return all((poly[(i + 1) % len(poly)][0] - poly[i][0]) * (point[1] - poly[i][1])
               - (poly[(i + 1) % len(poly)][1] - poly[i][1]) * (point[0] - poly[i][0]) >= -1e-7
               for i in range(len(poly)))


def _belief_samples(poly: list[Point], limit: int = 64) -> list[Point]:
    if not poly:
        return []
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    points: list[Point] = []
    grid = 11
    for i in range(grid):
        for j in range(grid):
            p = (min(xs) + (max(xs) - min(xs)) * (i + .5) / grid,
                 min(ys) + (max(ys) - min(ys)) * (j + .5) / grid)
            if _inside_convex(poly, p):
                points.append(p)
    # Boundary points preserve thin feasible regions that a fixed grid can miss.
    points.extend(poly)
    if len(points) <= limit:
        return points
    step = len(points) / limit
    return [points[min(int(k * step), len(points) - 1)] for k in range(limit)]


def build_region(observations: list[tuple[Point, float]],
                 no_signal_points: list[Point]) -> RegionSnapshot:
    poly = _outer_circle_polygon((0.0, 0.0), AREA_R)
    for station, angle in observations:
        poly = _clip_bearing(poly, station, angle)
        poly = _clip_outer_circle(poly, station, MAX_DIRECTION_R)
        if not poly:
            break
    circle = minimum_enclosing_circle(poly)
    samples, masses, bounds = [], [], []
    for point in _belief_samples(poly):
        lower = max([GUARANTEE_R] + [math.dist(point, station) for station, _ in observations])
        upper = min([MAX_DIRECTION_R] + [math.dist(point, station) for station in no_signal_points])
        mass = max(0.0, upper - lower)
        if mass > 1e-9:
            samples.append(point); masses.append(mass); bounds.append((lower, upper))
    total = sum(masses)
    weights = [mass / total for mass in masses] if total else []
    return RegionSnapshot(tuple(poly), circle, tuple(samples), tuple(weights), tuple(bounds))


_REGION_CACHE: dict = {}


def build_region_cached(observations: list[tuple[Point, float]],
                        no_signal_points: list[Point]) -> RegionSnapshot:
    """Memoised build_region; the belief region only depends on the history."""
    key = (tuple(observations), tuple(no_signal_points))
    snapshot = _REGION_CACHE.get(key)
    if snapshot is None:
        snapshot = build_region(list(observations), list(no_signal_points))
        if len(_REGION_CACHE) >= 16384:
            _REGION_CACHE.clear()
        _REGION_CACHE[key] = snapshot
    return snapshot


def reception_probabilities(snapshot: RegionSnapshot, station: Point) -> list[float]:
    """Conditional receive probabilities for the fixed unknown source radius."""
    probabilities = []
    for target, (lower, upper) in zip(snapshot.samples, snapshot.radius_bounds):
        distance = math.dist(target, station)
        if distance <= lower:
            probabilities.append(1.0)
        elif distance >= upper:
            probabilities.append(0.0)
        else:
            probabilities.append((upper - distance) / (upper - lower))
    return probabilities


def predicted_circle(snapshot: RegionSnapshot, station: Point,
                     predicted_bearing: float) -> EnclosingCircle:
    poly = _clip_bearing(list(snapshot.polygon), station, predicted_bearing)
    poly = _clip_outer_circle(poly, station, MAX_DIRECTION_R)
    return minimum_enclosing_circle(poly)

"""覆盖点开放路径优化；仅使用检测点和在线位置，不读取源真值。"""
import math
from functools import lru_cache

from q4_experiment import Q4TriangularCoverageAgent


def improve(route, distances):
    """固定起点的2-opt与单点Or-opt，严格下降直到局部稳定。"""
    route = list(route)
    for _ in range(100):
        best_delta, move = -1e-7, None
        n = len(route)
        for i in range(1, n - 1):
            a, b = route[i - 1], route[i]
            for j in range(i + 1, n):
                c = route[j]
                delta = distances[a][c] - distances[a][b]
                if j + 1 < n:
                    d = route[j + 1]
                    delta += distances[b][d] - distances[c][d]
                if delta < best_delta:
                    best_delta, move = delta, (i, j)
        if move is not None:
            i, j = move
            route[i:j + 1] = reversed(route[i:j + 1])
            continue
        # 单点搬移包括移至终点；用完整代价校核，点数最多31。
        cost = sum(distances[a][b] for a, b in zip(route, route[1:]))
        candidate_best = None
        for i in range(1, n):
            rest = route[:i] + route[i + 1:]
            for j in range(1, n):
                candidate = rest[:j] + [route[i]] + rest[j:]
                value = sum(distances[a][b] for a, b in zip(candidate, candidate[1:]))
                if value < cost - 1e-7:
                    cost, candidate_best = value, candidate
        if candidate_best is None:
            break
        route = candidate_best
    return route


@lru_cache(maxsize=16)
def initial_route(points):
    distances = [[math.dist(a, b) for b in points] for a in points]
    candidates = []
    for first in range(1, len(points)):
        route = [0, first]
        left = set(range(1, len(points))) - {first}
        while left:
            nxt = min(left, key=lambda i: (distances[route[-1]][i], i))
            route.append(nxt)
            left.remove(nxt)
        route = improve(route, distances)
        candidates.append((sum(distances[a][b] for a, b in zip(route, route[1:])), route))
    return tuple(points[i] for i in min(candidates)[1])


class Route31Agent(Q4TriangularCoverageAgent):
    """保留原31点，预先求多起点开放路线，在线沿路线访问。"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.planned = initial_route(tuple(self.search_points))

    def _coverage_order(self, unvisited):
        remaining = set(unvisited)
        return [p for p in self.planned if p in remaining]


def segment_distance(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, -(a[0] * dx + a[1] * dy) / (dx * dx + dy * dy)))
    return math.hypot(a[0] + t * dx, a[1] + t * dy)


def triangle_intersects_disk(triangle, radius=1800.0):
    crosses = [a[0] * b[1] - a[1] * b[0]
               for a, b in zip(triangle, triangle[1:] + triangle[:1])]
    if min(crosses) >= -1e-8 or max(crosses) <= 1e-8:
        return True
    return min(segment_distance(a, b)
               for a, b in zip(triangle, triangle[1:] + triangle[:1])) <= radius + 1e-7


@lru_cache(maxsize=8)
def clipped_sites(side, offset_x=0.0, offset_y=0.0):
    """保留所有与源圆域相交的三角形顶点；交集判定包含相切。"""
    h = side * math.sqrt(3) / 2
    def vertex(i, j):
        return (side * (i + j / 2) + offset_x, h * j + offset_y)
    points = set()
    for i in range(-8, 9):
        for j in range(-8, 9):
            a, b, c, d = vertex(i, j), vertex(i + 1, j), vertex(i, j + 1), vertex(i + 1, j + 1)
            for triangle in ([a, b, c], [b, d, c]):
                if triangle_intersects_disk(triangle):
                    points.update(triangle)
    return tuple(sorted(points, key=lambda p: (math.hypot(*p), math.atan2(p[1], p[0]))))


class ClippedRouteAgent(Route31Agent):
    @staticmethod
    def _triangular_sites(side):
        return list(clipped_sites(side))


class ShiftedAgent(Route31Agent):
    lattice_side_m = 990.0
    phase = (0.5, 0.0)

    def __init__(self, sim, verbose=False):
        Q4TriangularCoverageAgent.__init__(self, sim, verbose)
        dx, dy = self.phase
        points = clipped_sites(self.lattice_side_m, dx * self.lattice_side_m,
                               dy * self.lattice_side_m * math.sqrt(3) / 2)
        self.search_points = [(0.0, 0.0)] + [p for p in points if math.hypot(*p) > 1e-7]
        self.planned = initial_route(tuple(self.search_points))


class ShiftB(ShiftedAgent):
    phase = (0.0, 0.5)


class ShiftC(ShiftedAgent):
    phase = (0.5, 0.5)


class ShiftD(ShiftedAgent):
    phase = (0.5, 1 / 3)


class ShiftGreedy(ShiftedAgent):
    def _coverage_order(self, unvisited):
        return Q4TriangularCoverageAgent._coverage_order(self, unvisited)


class ShiftBGreedy(ShiftB):
    def _coverage_order(self, unvisited):
        return Q4TriangularCoverageAgent._coverage_order(self, unvisited)


class ShiftBRolling(ShiftB):
    """从实际当前位置对剩余开放路线局部重排。"""
    def _coverage_order(self, unvisited):
        if len(unvisited) < 2:
            return list(unvisited)
        key = (self.sim.position, tuple(unvisited),
               tuple((c, len(s.observations), s.cleared) for c, s in self.state.items()))
        if getattr(self, '_last_key', None) == key:
            return self._last_route
        route = super()._coverage_order(unvisited)
        points = [self.sim.position] + route
        distances = [[math.dist(a, b) for b in points] for a in points]
        indices = improve(list(range(len(points))), distances)
        route = [points[i] for i in indices[1:]]
        self._last_key, self._last_route = key, route
        return route

"""实现Q4最终D模型的原点分支门控与1500米保守共观测距离门。"""
from __future__ import annotations

import math
from collections.abc import Sequence

Point = tuple[float, float]
MAX_RECEPTION_RADIUS_M = 1500.0


def select_route(origin_discoveries: int) -> str:
    """原点零发现走B路线，否则走C路线。"""
    if origin_discoveries < 0:
        raise ValueError("origin_discoveries must be nonnegative")
    return "B" if origin_discoveries == 0 else "C"


def point_segment_distance(point: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    denominator = dx * dx + dy * dy
    if denominator <= 1e-12:
        return math.dist(point, a)
    t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / denominator
    t = max(0.0, min(1.0, t))
    projection = (a[0] + t * dx, a[1] + t * dy)
    return math.dist(point, projection)


def point_in_convex_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    signs: list[bool] = []
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        cross = ((b[0] - a[0]) * (point[1] - a[1])
                 - (b[1] - a[1]) * (point[0] - a[0]))
        if abs(cross) > 1e-8:
            signs.append(cross > 0.0)
    return not signs or all(sign == signs[0] for sign in signs)


def distance_to_feasible_region(station: Point, polygon: Sequence[Point]) -> float:
    """计算测站到保守凸可行域的欧氏最小距离。"""
    if not polygon or point_in_convex_polygon(station, polygon):
        return 0.0
    return min(
        point_segment_distance(station, a, polygon[(i + 1) % len(polygon)])
        for i, a in enumerate(polygon)
    )


def should_coobserve(station: Point, feasible_polygon: Sequence[Point]) -> bool:
    """等号保留；仅剪去距离严格大于1500米的不可能成功测量。"""
    return distance_to_feasible_region(station, feasible_polygon) <= MAX_RECEPTION_RADIUS_M


if __name__ == "__main__":
    square = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
    print({
        "gate": {n: select_route(n) for n in range(4)},
        "1499m": should_coobserve((1500.0, 0.0), square),
        "1500m": should_coobserve((1501.0, 0.0), square),
        "1500.1m": should_coobserve((1501.1, 0.0), square),
    })

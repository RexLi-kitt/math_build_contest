# 功能：以旋转卡壳与全顶点枚举精确求区域直径，并判定以直径 D 为直径的同直径圆能否覆盖区域。
from __future__ import annotations

from fractions import Fraction
from itertools import combinations
import math

Point = tuple[Fraction, Fraction]


def _cross(a: Point, b: Point, c: Point) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _distance2(a: Point, b: Point) -> Fraction:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def convex_hull(points) -> tuple[Point, ...]:
    ordered = sorted({(Fraction(p[0]), Fraction(p[1])) for p in points})
    if len(ordered) <= 1:
        return tuple(ordered)
    lower, upper = [], []
    for part, sequence in ((lower, ordered), (upper, reversed(ordered))):
        for p in sequence:
            while len(part) >= 2 and _cross(part[-2], part[-1], p) <= 0:
                part.pop()
            part.append(p)
    return tuple(lower[:-1] + upper[:-1])


def convex_diameter(vertices, method: str = "calipers"):
    """第三步：区域直径 D = max_{i<j} ||v_i − v_j||，同时返回最远点对。

    任一内部点的凸组合由三角不等式不会超过顶点对距离，故只需检查顶点；
    距离平方保留有理数精确比较，最后才开平方。复杂度：枚举 O(m²)，卡壳 O(m)。
    """
    if method not in ("calipers", "exhaustive"):
        raise ValueError("method 必须为 calipers 或 exhaustive")
    hull = convex_hull(vertices)
    if not hull:
        raise ValueError("空点集没有可用直径")
    best = Fraction(0)
    endpoints = (hull[0], hull[0])

    def consider(a: Point, b: Point) -> None:
        nonlocal best, endpoints
        squared = _distance2(a, b)
        if squared > best:
            best, endpoints = squared, (a, b)

    size = len(hull)
    if method == "exhaustive" or size <= 2:
        for a, b in combinations(hull, 2):
            consider(a, b)
    else:
        j = 1
        for i in range(size):
            nxt = (i + 1) % size

            def area(index: int) -> Fraction:
                return _cross(hull[i], hull[nxt], hull[index % size])

            while area(j + 1) > area(j):
                j = (j + 1) % size
            consider(hull[i], hull[j])
            consider(hull[nxt], hull[j])
            if area(j + 1) == area(j):
                # 相邻对侧顶点面积相等（平行支撑边）时同时检查候选点，避免漏检。
                consider(hull[i], hull[(j + 1) % size])
                consider(hull[nxt], hull[(j + 1) % size])
    return math.sqrt(best), best, endpoints


def diameter_circle_coverage(vertices):
    """第四步：是否存在直径等于区域直径的圆覆盖区域。

    半径 D/2 的圆若要同时包含最远点对 a,b，圆心只能是中点 c=(a+b)/2；
    圆盘为凸集，故只检查 max_i ||v_i − c|| <= D/2 即可，结论精确（不用浮点容差）。
    等边三角形反例中 R_min = D/√3 > D/2，判定为「否」。
    """
    hull = convex_hull(vertices)
    _, squared_diameter, (a, b) = convex_diameter(hull)
    center = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    farthest = max(hull, key=lambda p: _distance2(p, center))
    maximum = _distance2(farthest, center)
    radius2 = squared_diameter / 4
    radius = math.sqrt(radius2)
    covers = maximum <= radius2
    # 正值为最远顶点超出圆边界的量，负值表示仍有余量，仅供显示。
    return center, radius, covers, math.sqrt(maximum) - radius, farthest

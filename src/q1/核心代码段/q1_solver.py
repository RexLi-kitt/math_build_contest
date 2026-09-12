# 功能：把每条 ±1° 示向度误差带转成闭半平面并逐次求交，得到凸定位区域并判定空集、无界与退化。
from __future__ import annotations

from fractions import Fraction
from itertools import combinations
import math
from typing import Iterable, Literal, Sequence

Number = int | float | Fraction
Point = tuple[Fraction, Fraction]
RegionStatus = Literal["empty", "unbounded", "point", "segment", "polygon"]


def _number(value: Number) -> Fraction:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("坐标、角度和系数必须是有限数值")
    return Fraction(value)


def _cross(a: Point, b: Point, c: Point) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _direction_degrees(angle: Fraction) -> Point:
    """按八分圆计算方向，保持轴向/对角向精确以及反向、旋转对称。

    向量不必归一化。普通角度仍受浮点三角函数精度限制；这里不放宽误差界。
    """
    quadrant, remainder = divmod(angle % 360, 90)
    swap = remainder > 45
    reduced = 90 - remainder if swap else remainder
    if reduced == 0:
        x, y = Fraction(1), Fraction(0)
    elif reduced == 45:
        x, y = Fraction(1), Fraction(1)
    else:
        radians = math.radians(float(reduced))
        x, y = _number(math.cos(radians)), _number(math.sin(radians))
    if swap:
        x, y = y, x
    return ((x, y), (-y, x), (-x, -y), (y, -x))[int(quadrant)]


def bearing_halfplanes(
    stations: Iterable[Sequence[Number]],
    bearings_deg: Iterable[Number],
    error_deg: Number = 1.0,
) -> tuple[tuple[Fraction, Fraction, Fraction], ...]:
    """第一步：每条观测的楔形 W_i = {X | cross(u⁻, X−M) ≥ 0 且 cross(u⁺, X−M) ≤ 0}。

    等价于两个闭半平面 a*x + b*y <= c，共 2n 个约束；方位从正东逆时针计量，
    允许负角度或超过 360°；0 < error_deg < 90 保证张角小于 180°。
    """
    points = tuple((_number(x), _number(y)) for x, y in stations)
    angles = tuple(_number(a) for a in bearings_deg)
    epsilon = _number(error_deg)
    if len(points) != len(angles):
        raise ValueError("检测点数量必须与示向度数量相同")
    if not 0 < epsilon < 90:
        raise ValueError("误差半角必须满足 0 < error_deg < 90")
    result = []
    for (x, y), angle in zip(points, angles):
        lower = _direction_degrees(angle - epsilon)
        upper = _direction_degrees(angle + epsilon)
        if lower[0] * upper[1] - lower[1] * upper[0] <= 0:
            raise ValueError("误差半角接近浮点分辨率极限，边界方向无法可靠区分")
        for a, b in (
            (lower[1], -lower[0]),
            (-upper[1], upper[0]),
        ):
            a, b = _number(a), _number(b)
            result.append((a, b, a * x + b * y))
    return tuple(result)


def convex_hull(points: Iterable[Sequence[Number]]) -> tuple[Point, ...]:
    """二维单调链凸包：逆时针、去重、删除共线中间点，不重复首点。"""
    ordered = sorted({(_number(p[0]), _number(p[1])) for p in points})
    if len(ordered) <= 1:
        return tuple(ordered)
    lower, upper = [], []
    for part, sequence in ((lower, ordered), (upper, reversed(ordered))):
        for p in sequence:
            while len(part) >= 2 and _cross(part[-2], part[-1], p) <= 0:
                part.pop()
            part.append(p)
    return tuple(lower[:-1] + upper[:-1])


def intersect_halfplanes(
    halfplanes: Iterable[tuple[Number, Number, Number]],
) -> tuple[RegionStatus, tuple[Point, ...], Point | None, Point | None]:
    """第二步：通用闭半平面交，无人工包围框，支持退化和无界。

    枚举边界交点并按全部约束筛选，O(k³) 次有理数运算，适合少量测向观测。
    返回 (区域状态, 顶点, 可行点, 无界延伸方向)。
    """
    constraints = tuple((_number(a), _number(b), _number(c)) for a, b, c in halfplanes)
    if any(a == b == 0 and c < 0 for a, b, c in constraints):
        return "empty", (), None, None
    constraints = tuple((a, b, c) for a, b, c in constraints if a or b)

    def feasible(p: Point) -> bool:
        return all(a * p[0] + b * p[1] <= c for a, b, c in constraints)

    origin = (Fraction(0), Fraction(0))
    witness = origin if feasible(origin) else None
    # 非空闭凸集距原点最近点必为原点、边界垂足或边界交点之一。
    if witness is None:
        for a, b, c in constraints:
            norm2 = a * a + b * b
            p = (a * c / norm2, b * c / norm2)
            if feasible(p):
                witness = p
                break
    vertices = set()
    for (a1, b1, c1), (a2, b2, c2) in combinations(constraints, 2):
        determinant = a1 * b2 - a2 * b1
        if determinant == 0:
            continue
        p = ((c1 * b2 - c2 * b1) / determinant, (a1 * c2 - a2 * c1) / determinant)
        if feasible(p):
            vertices.add(p)
            witness = p
    if witness is None:
        return "empty", (), None, None

    # 无界等价于存在 d != 0，使全部法向量满足 n·d <= 0；
    # 二维非平凡衰退锥必包含某条约束边界的切向方向。
    directions = [(Fraction(1), Fraction(0))] if not constraints else []
    for a, b, _ in constraints:
        directions.extend(((b, -a), (-b, a)))
    for d in directions:
        if all(a * d[0] + b * d[1] <= 0 for a, b, _ in constraints):
            return "unbounded", (), witness, d
    hull = convex_hull(vertices)
    if not hull:
        raise ArithmeticError("非空有界区域未找到顶点")
    status: RegionStatus = "point" if len(hull) == 1 else "segment" if len(hull) == 2 else "polygon"
    return status, hull, witness, None


def localize(stations, bearings_deg, error_deg: Number = 1.0):
    """串联两步：观测 -> 半平面 -> 定位区域（空集与无界不返回直径）。"""
    region = intersect_halfplanes(bearing_halfplanes(stations, bearings_deg, error_deg))
    return region

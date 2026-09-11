"""Q1：角度约束、半平面交、凸区域直径及同直径圆覆盖。
"""
from dataclasses import dataclass
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


def _point(value: Sequence[Number]) -> Point:
    if len(value) != 2:
        raise ValueError("每个点必须包含两个坐标")
    return _number(value[0]), _number(value[1])


def _cross(a: Point, b: Point, c: Point) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _distance2(a: Point, b: Point) -> Fraction:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


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


@dataclass(frozen=True)
class HalfPlane:
    """闭半平面 a*x + b*y <= c；零法向量也能表达恒真/矛盾约束。"""

    a: Fraction
    b: Fraction
    c: Fraction

    def __post_init__(self) -> None:
        for name in ("a", "b", "c"):
            object.__setattr__(self, name, _number(getattr(self, name)))

    def contains(self, point: Sequence[Number]) -> bool:
        x, y = _point(point)
        return self.a * x + self.b * y <= self.c


@dataclass(frozen=True)
class Region:
    status: RegionStatus
    vertices: tuple[Point, ...]
    feasible_point: Point | None
    # 无界时给出非零可行延伸方向，而不是伪造截断多边形。
    recession_direction: Point | None = None

    def float_vertices(self) -> list[tuple[float, float]]:
        """供显示、绘图使用；后续计算建议保留原始有理数顶点。"""
        return [(float(x), float(y)) for x, y in self.vertices]


@dataclass(frozen=True)
class Diameter:
    distance: float
    squared_distance: Fraction | None
    endpoints: tuple[Point, Point] | None


@dataclass(frozen=True)
class CircleCoverage:
    center: Point
    radius: float
    covers: bool
    # 正值表示最远顶点超出圆边界，负值表示仍有余量，单位为米。
    max_excess: float
    farthest_vertex: Point


@dataclass(frozen=True)
class LocalizationResult:
    halfplanes: tuple[HalfPlane, ...]
    region: Region
    diameter: Diameter | None
    circle: CircleCoverage | None


def bearing_halfplanes(
    stations: Iterable[Sequence[Number]],
    bearings_deg: Iterable[Number],
    error_deg: Number = 1.0,
) -> tuple[HalfPlane, ...]:
    """第一步：同一固定干扰源的观测 -> 每次两个半平面。

    方位从正东逆时针计量，允许负角度或超过 360°。
    0 < error_deg < 90，保证楔形张角小于 180°；默认题设的 1°。
    不要求误差独立；不接受无信号记录。空输入表示没有角度约束。
    """
    points = tuple(_point(p) for p in stations)
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
        if lower[0]*upper[1] - lower[1]*upper[0] <= 0:
            raise ValueError("误差半角接近浮点分辨率极限，边界方向无法可靠区分")
        for a, b in (
            (lower[1], -lower[0]),
            (-upper[1], upper[0]),
        ):
            a, b = _number(a), _number(b)
            result.append(HalfPlane(a, b, a * x + b * y))
    return tuple(result)


def convex_hull(points: Iterable[Sequence[Number]]) -> tuple[Point, ...]:
    """二维单调链凸包：逆时针、去重、删除共线中间点，不重复首点。"""
    points = sorted({_point(p) for p in points})
    if len(points) <= 1:
        return tuple(points)
    lower, upper = [], []
    for part, ordered in ((lower, points), (upper, reversed(points))):
        for p in ordered:
            while len(part) >= 2 and _cross(part[-2], part[-1], p) <= 0:
                part.pop()
            part.append(p)
    return tuple(lower[:-1] + upper[:-1])


def intersect_halfplanes(halfplanes: Iterable[HalfPlane]) -> Region:
    """第二步：通用闭半平面交，无人工包围框，支持退化和无界。

    枚举交点并筛选，O(k³) 次有理数运算，适合少量测向观测。
    实际耗时还取决于有理数位数。
    """
    constraints = tuple(halfplanes)
    if any(h.a == h.b == 0 and h.c < 0 for h in constraints):
        return Region("empty", (), None)
    constraints = tuple(h for h in constraints if h.a or h.b)

    def feasible(p: Point) -> bool:
        return all(h.a * p[0] + h.b * p[1] <= h.c for h in constraints)

    origin = (Fraction(0), Fraction(0))
    witness = origin if feasible(origin) else None
    # 非空闭凸集距原点最近点必为原点、边界垂足或边界交点之一。
    if witness is None:
        for h in constraints:
            norm2 = h.a * h.a + h.b * h.b
            p = (h.a * h.c / norm2, h.b * h.c / norm2)
            if feasible(p):
                witness = p
                break
    vertices = set()
    for h, g in combinations(constraints, 2):
        determinant = h.a * g.b - g.a * h.b
        if determinant == 0:
            continue
        p = ((h.c * g.b - g.c * h.b) / determinant,
             (h.a * g.c - g.a * h.c) / determinant)
        if feasible(p):
            vertices.add(p)
            witness = p
    if witness is None:
        return Region("empty", (), None)

    # 无界等价于存在 d!=0，使全部法向量满足 n·d<=0。
    # 二维非平凡衰退锥必包含某条约束边界的切向方向；无约束另处理。
    directions = [(Fraction(1), Fraction(0))] if not constraints else []
    for h in constraints:
        directions.extend(((h.b, -h.a), (-h.b, h.a)))
    for d in directions:
        if all(h.a * d[0] + h.b * d[1] <= 0 for h in constraints):
            return Region("unbounded", (), witness, d)
    hull = convex_hull(vertices)
    if not hull:
        raise ArithmeticError("非空有界区域未找到顶点")
    status = "point" if len(hull) == 1 else "segment" if len(hull) == 2 else "polygon"
    return Region(status, hull, witness)


def convex_diameter(
    vertices: Iterable[Sequence[Number]],
    method: Literal["calipers", "exhaustive"] = "calipers",
) -> Diameter:
    """第三步：输入顶点/点集的凸包直径，同时返回最远点对。

    自动去重、排序、去除内部点。凸包预处理 O(m log m)；之后
    calipers 为 O(m)，exhaustive 为 O(m²)。空点集抛出 ValueError。
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
                consider(hull[i], hull[(j + 1) % size])
                consider(hull[nxt], hull[(j + 1) % size])
    return Diameter(math.sqrt(best), best, endpoints)


def diameter_circle_coverage(vertices: Iterable[Sequence[Number]]) -> CircleCoverage:
    """第四步：是否存在直径等于区域直径的圆覆盖区域
    自行求最远点对，圆心只能是其中点；精确比较有理数距离平方。
    covers 不使用显示值或浮点容差，max_excess 仅供显示。
    """
    return _circle_coverage(convex_hull(vertices))


def _circle_coverage(vertices: tuple[Point, ...], diameter: Diameter | None = None) -> CircleCoverage:
    diameter = diameter or convex_diameter(vertices)
    a, b = diameter.endpoints
    center = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    farthest = max(vertices, key=lambda p: _distance2(p, center))
    maximum = _distance2(farthest, center)
    radius2 = diameter.squared_distance / 4
    radius = math.sqrt(radius2)
    return CircleCoverage(center, radius, maximum <= radius2,
                          math.sqrt(maximum) - radius, farthest)


def localize(
    stations: Iterable[Sequence[Number]],
    bearings_deg: Iterable[Number],
    error_deg: Number = 1.0,
    method: Literal["calipers", "exhaustive"] = "calipers",
) -> LocalizationResult:
    """串联前四步；空集无直径，无界区域直径为 inf，二者均无覆盖圆。"""
    if method not in ("calipers", "exhaustive"):
        raise ValueError("method 必须为 calipers 或 exhaustive")
    halfplanes = bearing_halfplanes(stations, bearings_deg, error_deg)
    region = intersect_halfplanes(halfplanes)
    if region.status == "empty":
        return LocalizationResult(halfplanes, region, None, None)
    if region.status == "unbounded":
        return LocalizationResult(halfplanes, region, Diameter(math.inf, None, None), None)
    diameter = convex_diameter(region.vertices, method)
    circle = _circle_coverage(region.vertices, diameter)
    return LocalizationResult(halfplanes, region, diameter, circle)

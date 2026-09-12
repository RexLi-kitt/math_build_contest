# 功能：用 ±1° 方位带与距离上界裁剪出保守可行域，并以最小包围圆判定能否前往圆心清除。
from __future__ import annotations

import math

AREA_R = 1800.0           # 任务圆域半径
MAX_DIRECTION_R = 1500.0  # 接收半径上界：超过必然无信号，可作裁剪约束
GUARANTEE_R = 1000.0      # 接收半径下界：环内必然有信号
ERROR_DEG = 1.0           # 示向度误差半角
CLEAR_RADIUS_M = 19.75    # 20 m 光学/清除半径留 0.25 m 数值余量


def clip(poly, a, b, c):
    """Sutherland–Hodgman 裁剪一条半平面 a*x + b*y <= c，返回交点多边形。"""
    if not poly:
        return []
    out, previous = [], poly[-1]
    previous_value = a * previous[0] + b * previous[1] - c
    for current in poly:
        current_value = a * current[0] + b * current[1] - c
        previous_inside = previous_value <= 1e-8
        current_inside = current_value <= 1e-8
        if previous_inside != current_inside:
            t = previous_value / (previous_value - current_value)
            out.append((previous[0] + t * (current[0] - previous[0]),
                        previous[1] + t * (current[1] - previous[1])))
        if current_inside:
            out.append(current)
        previous, previous_value = current, current_value
    return out


def clip_bearing(poly, station, angle_deg):
    """加入一条 ±1° 示向度带（张角 2° 的闭楔形），即两个半平面约束。"""
    lower = math.radians(angle_deg - ERROR_DEG)
    upper = math.radians(angle_deg + ERROR_DEG)
    for a, b in ((math.sin(lower), -math.cos(lower)),
                 (-math.sin(upper), math.cos(upper))):
        poly = clip(poly, a, b, a * station[0] + b * station[1])
    return poly


def task_area_polygon(sides=72):
    """任务圆域的保守表示：外接正 sides 边形（默认 72 边）。"""
    vertex_radius = AREA_R / math.cos(math.pi / sides)
    return [(vertex_radius * math.cos(2 * math.pi * (k + .5) / sides),
             vertex_radius * math.sin(2 * math.pi * (k + .5) / sides)) for k in range(sides)]


def clip_outer_circle(poly, center, radius, sides=72):
    """用外接正 sides 边形保守表示距离上界 d <= radius（72 面切向在实现中预缓存）。"""
    if not poly:
        return []
    cx, cy = center
    limit = radius * radius + 1e-9
    if all((x - cx) ** 2 + (y - cy) ** 2 <= limit for x, y in poly):
        return poly  # 全部顶点已在半径内，整段裁剪可跳过
    for k in range(sides):
        a, b = math.cos(2 * math.pi * k / sides), math.sin(2 * math.pi * k / sides)
        poly = clip(poly, a, b, radius + a * cx + b * cy)
        if not poly:
            break
    return poly


def _circle_two(a, b):
    center = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return center, math.dist(center, a)


def _circle_three(a, b, c):
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-10:
        return None
    aa, bb, cc = a[0] ** 2 + a[1] ** 2, b[0] ** 2 + b[1] ** 2, c[0] ** 2 + c[1] ** 2
    center = ((aa * (b[1] - c[1]) + bb * (c[1] - a[1]) + cc * (a[1] - b[1])) / d,
              (aa * (c[0] - b[0]) + bb * (a[0] - c[0]) + cc * (b[0] - a[0])) / d)
    return center, math.dist(center, a)


def minimum_enclosing_circle(points):
    """随机增量最小包围圆：圆心是 0/1/2/3 个边界点的确定结果，半径即包围圆半径。"""
    if not points:
        return (0.0, 0.0), math.inf
    circle = (points[0], 0.0)
    for i, p in enumerate(points):
        if math.dist(p, circle[0]) <= circle[1] + 1e-7:
            continue
        circle = (p, 0.0)
        for j, q in enumerate(points[:i]):
            if math.dist(q, circle[0]) <= circle[1] + 1e-7:
                continue
            circle = _circle_two(p, q)
            for r in points[:j]:
                if math.dist(r, circle[0]) <= circle[1] + 1e-7:
                    continue
                candidate = _circle_three(p, q, r)
                if candidate is not None:
                    circle = candidate
    return circle


def _inside_convex(poly, point):
    return all((poly[(i + 1) % len(poly)][0] - poly[i][0]) * (point[1] - poly[i][1])
               - (poly[(i + 1) % len(poly)][1] - poly[i][1]) * (point[0] - poly[i][0]) >= -1e-7
               for i in range(len(poly)))


def belief_samples(poly, limit=64):
    """在可行域上取 11×11 网格内点并补边界顶点，薄区域也不会被网格漏掉。"""
    if not poly:
        return []
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    points = [(min(xs) + (max(xs) - min(xs)) * (i + .5) / 11,
               min(ys) + (max(ys) - min(ys)) * (j + .5) / 11)
              for i in range(11) for j in range(11)]
    points = [p for p in points if _inside_convex(poly, p)] + list(poly)
    if len(points) <= limit:
        return points
    step = len(points) / limit
    return [points[min(int(k * step), len(points) - 1)] for k in range(limit)]


def build_region(observations, no_signal_points):
    """信念层主流程：任务圆域外接 72 边形起，逐条观测裁剪方位带与 1500 m 上界。

    返回 (保守多边形, 样本, 接收半径区间)；no_signal 排除圆是非凸孔洞，
    只从样本里删除，保守多边形仍用于清除判定以免误清除。
    """
    poly = task_area_polygon()
    for station, angle in observations:
        poly = clip_bearing(poly, station, angle)
        poly = clip_outer_circle(poly, station, MAX_DIRECTION_R)
        if not poly:
            break
    samples, bounds = [], []
    for point in belief_samples(poly):
        lower = max([GUARANTEE_R] + [math.dist(point, station) for station, _ in observations])
        upper = min([MAX_DIRECTION_R] + [math.dist(point, station) for station in no_signal_points])
        if upper - lower > 1e-9:
            samples.append(point)
            bounds.append((lower, upper))
    return poly, samples, bounds


def minimum_enclosing_circle_of_region(poly):
    return minimum_enclosing_circle(list(poly))


def clear_decision(poly):
    """清除判定：保守外包络的最小包围圆半径不超过 19.75 m 时才前往圆心清除。"""
    center, radius = minimum_enclosing_circle_of_region(poly)
    return center if radius <= CLEAR_RADIUS_M else None


def reception_probabilities(samples, bounds, station):
    """固定未知接收半径下的条件接收概率 p_rec，供四指标 p_rec 项使用。"""
    probabilities = []
    for target, (lower, upper) in zip(samples, bounds):
        distance = math.dist(target, station)
        if distance <= lower:
            probabilities.append(1.0)
        elif distance >= upper:
            probabilities.append(0.0)
        else:
            probabilities.append((upper - distance) / (upper - lower))
    return probabilities


def predicted_circle(poly, station, predicted_bearing):
    """预加入一条假设方位后的包围圆，用于四指标中的 R_pred 项。"""
    updated = clip_bearing(list(poly), station, predicted_bearing)
    updated = clip_outer_circle(updated, station, MAX_DIRECTION_R)
    return minimum_enclosing_circle(updated)

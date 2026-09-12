# 功能：以±1°角度带交集认证清除点，并在认证失败时生成20m覆盖的局部回补网格。
from __future__ import annotations

import math
from typing import Iterable


Point = tuple[float, float]


def _clip_halfplane(polygon: list[Point], origin: Point, direction_deg: float, keep_left: bool) -> list[Point]:
    """Sutherland–Hodgman 半平面裁剪。"""
    vx, vy = math.cos(math.radians(direction_deg)), math.sin(math.radians(direction_deg))

    def signed(point: Point) -> float:
        return vx * (point[1] - origin[1]) - vy * (point[0] - origin[0])

    def inside(point: Point) -> bool:
        return signed(point) >= -1e-9 if keep_left else signed(point) <= 1e-9

    if not polygon:
        return []
    output: list[Point] = []
    previous, previous_inside = polygon[-1], inside(polygon[-1])
    for current in polygon:
        current_inside = inside(current)
        if current_inside != previous_inside:
            sp, sc = signed(previous), signed(current)
            ratio = sp / (sp - sc)
            output.append((previous[0] + ratio * (current[0] - previous[0]),
                           previous[1] + ratio * (current[1] - previous[1])))
        if current_inside:
            output.append(current)
        previous, previous_inside = current, current_inside
    return output


def certified_clear_circle(observations: Iterable[tuple[float, float, float]],
                           error_deg: float = 1.0, extent_m: float = 1800.0) -> tuple[Point, float] | None:
    """计算角度带交集的保守包含圆；半径不超过20m才可安全调用 clear。"""
    polygon: list[Point] = [(-extent_m, -extent_m), (extent_m, -extent_m),
                            (extent_m, extent_m), (-extent_m, extent_m)]
    for x, y, bearing_deg in observations:
        # 测向角带内部位于下边界左侧、上边界右侧。
        polygon = _clip_halfplane(polygon, (x, y), bearing_deg - error_deg, keep_left=True)
        polygon = _clip_halfplane(polygon, (x, y), bearing_deg + error_deg, keep_left=False)
        if not polygon:
            return None
    center = (sum(point[0] for point in polygon) / len(polygon),
              sum(point[1] for point in polygon) / len(polygon))
    radius = max(math.dist(center, point) for point in polygon)
    return center, radius


def local_repair_grid(estimate: Point, half_width_m: float = 56.0, step_m: float = 28.0) -> list[Point]:
    """认证不足或 clear 失败后的局部清除点；28m方格的最近点上界约19.8m。"""
    offsets = [value for value in range(-int(half_width_m), int(half_width_m) + 1, int(step_m))]
    return [(estimate[0] + dx, estimate[1] + dy) for dx in offsets for dy in offsets]


def should_clear(circle: tuple[Point, float] | None, clear_radius_m: float = 20.0) -> bool:
    """只有角度带交集的保守包含圆完全落入20m清除半径时才建议直接清除。"""
    return circle is not None and circle[1] <= clear_radius_m

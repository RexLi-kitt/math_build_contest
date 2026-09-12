# 功能：基于问题二的交会几何、接收保障和移动代价选择第四问的主动第二检测点。
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable


def wrap(angle_deg: float) -> float:
    """将角度折返至 [-180°, 180°)。"""
    return (angle_deg + 180.0) % 360.0 - 180.0


@dataclass(frozen=True)
class Q2Candidate:
    point: tuple[float, float]
    predicted_source: tuple[float, float]
    score: float
    geometry: float
    receive: float
    move_cost: float


def choose_q2_second_point(
    first_point: tuple[float, float], first_bearing_deg: float,
    current_point: tuple[float, float], posterior_positions: Iterable[tuple[float, float]],
    visible_fraction: Callable[[tuple[float, float]], float],
    weights: tuple[float, float, float] = (0.30, 0.20, 0.50),
) -> tuple[Q2Candidate, tuple[float, float]]:
    """在 Q4 方向—位置后验上执行 V13 的 Q2 主动二测，并返回镜像补测点。"""
    x1, y1 = first_point
    ux, uy = math.cos(math.radians(first_bearing_deg)), math.sin(math.radians(first_bearing_deg))
    vx, vy = -uy, ux

    # 首测向后距离通常尚未收敛，故使用经 V13 回归验证的固定距离层，避免过度相信单次观测。
    candidates: list[Q2Candidate] = []
    for source_range in (600.0, 700.0, 800.0, 900.0, 1000.0, 1100.0):
        predicted = (x1 + source_range * ux, y1 + source_range * uy)
        for lateral in (150.0, 250.0, 350.0):
            for sign in (-1.0, 1.0):
                point = (predicted[0] + sign * lateral * vx, predicted[1] + sign * lateral * vy)
                second_bearing = math.degrees(math.atan2(predicted[1] - point[1], predicted[0] - point[0]))
                crossing = min(abs(wrap(first_bearing_deg - second_bearing)),
                               180.0 - abs(wrap(first_bearing_deg - second_bearing)))
                geometry = math.sin(math.radians(crossing)) ** 2     # 交会角接近 90° 时最好
                receive = visible_fraction(point)                     # 定向后验下仍可接收的候选状态比例
                move_cost = min(math.dist(current_point, point) / 1800.0, 1.0)
                score = weights[0] * geometry + weights[1] * receive - weights[2] * move_cost
                candidates.append(Q2Candidate(point, predicted, score, geometry, receive, move_cost))

    if not candidates:
        raise RuntimeError("Q2 候选集为空，无法选择第二检测点")
    best = max(candidates, key=lambda row: row.score)

    # 若最佳二测无信号，沿首测向线镜像一次，快速区分定向盲侧和距离不足。
    longitudinal = (best.point[0] - x1) * ux + (best.point[1] - y1) * uy
    lateral = (best.point[0] - x1) * vx + (best.point[1] - y1) * vy
    mirror = (x1 + longitudinal * ux - lateral * vx, y1 + longitudinal * uy - lateral * vy)
    return best, mirror

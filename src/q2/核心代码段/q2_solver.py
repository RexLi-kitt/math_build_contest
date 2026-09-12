# 功能：以四指标评分完成“全局粗搜索—局部加密—高分区执行点”选择。
from __future__ import annotations

import math
from typing import Callable

S1 = (-750.0, -450.0)
ETA = 0.10


def normalize_and_score(rows: list[dict], weights: tuple[float, float, float, float]) -> list[dict]:
    """对 q_geo、p_rec、travel_s、r_pred_m 分别归一化后计算 J。"""
    valid = [r for r in rows if r["p_rec"] > 0 and math.isfinite(r["r_pred_m"])]
    if not valid:
        raise RuntimeError("没有保证接收的候选点")
    for source, target in (("q_geo", "q_n"), ("p_rec", "p_n"),
                           ("travel_s", "t_n"), ("r_pred_m", "r_n")):
        lo, hi = min(r[source] for r in valid), max(r[source] for r in valid)
        for row in rows:
            row[target] = (row[source] - lo) / (hi - lo) if row in valid and hi > lo else 0.0
    for row in rows:
        if row not in valid:
            row["J"] = -math.inf
        else:
            # +w3+w4 是不改变排序的常数平移，使 J>=0 后可直接采用 90% 阈值。
            row["J"] = (weights[0] * row["q_n"] + weights[1] * row["p_n"]
                        - weights[2] * row["t_n"] - weights[3] * row["r_n"]
                        + weights[2] + weights[3])
    return rows


def polar_point(bearing_deg: float, distance_m: float, offset_deg: float) -> tuple[float, float]:
    angle = math.radians(bearing_deg + offset_deg)
    return S1[0] + distance_m * math.cos(angle), S1[1] + distance_m * math.sin(angle)


def choose_second_point(bearing_deg: float, weights: tuple[float, float, float, float],
                        metric_fn: Callable[[tuple[float, float]], dict]) -> tuple[dict, list[dict]]:
    """metric_fn 必须返回 q_geo、p_rec、travel_s、r_pred_m 四项原始指标。"""
    coarse_points = [polar_point(bearing_deg, d, offset)
                     for d in range(100, 1801, 200) for offset in range(0, 360, 30)]
    coarse = [{"x_m": x, "y_m": y, **metric_fn((x, y))} for x, y in coarse_points]
    normalize_and_score(coarse, weights)
    seeds = sorted(coarse, key=lambda r: r["J"], reverse=True)[:2]

    refined_points: set[tuple[float, float]] = set()
    for seed in seeds:
        distance = math.dist(S1, (seed["x_m"], seed["y_m"]))
        direction = math.degrees(math.atan2(seed["y_m"] - S1[1], seed["x_m"] - S1[0]))
        for d in (max(50.0, distance - 100.0), distance, min(1800.0, distance + 100.0)):
            for offset in (-10.0, 0.0, 10.0):
                refined_points.add(tuple(round(v, 7) for v in polar_point(0.0, d, direction + offset)))
    refined = [{"x_m": x, "y_m": y, **metric_fn((x, y))} for x, y in refined_points]
    normalize_and_score(refined, weights)

    peak = max(refined, key=lambda r: r["J"])
    good = [r for r in refined if r["J"] >= (1.0 - ETA) * peak["J"]]
    # 高分区内优先短移动；若相同，再选预测 MEC 更小的点。
    execute = min(good, key=lambda r: (round(r["travel_s"], 6), r["r_pred_m"], -r["J"]))
    return execute, good

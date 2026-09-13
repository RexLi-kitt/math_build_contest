# 功能：第二问四指标选点内核——粗网格到加密两阶段打分，并在高分区内选出下一测量点。
from __future__ import annotations

import math
from dataclasses import dataclass

COARSE_DISTANCES = (200.0, 600.0, 1000.0, 1400.0, 1800.0)  # 以首次检测站为原点的粗网格距离
COARSE_BEARING_STEP = 60.0
GOOD_ETA = 0.10            # 高分区带宽：峰值的 10%（range-based，在线负分时仍有效）
SPEED = 5.0                # 移动速度 5 m/s
MEASURE_TIME_S = 6.0       # 一次测量动作（切换 1 s + 检测 5 s）
MAX_EXTRA_DISTANCE_M = 250.0  # C+ 限制：绕行测量相对直奔圆心的额外路程上限

WEIGHTS_C = (0.35, 0.30, 0.15, 0.20)      # C：第二问示例权重
WEIGHTS_CPLUS = (0.25, 0.25, 0.35, 0.15)  # C+：第三问在线权重
WEIGHTS_JPLUS = (0.25, 0.25, 0.25, 0.25)  # J+：等权标定（最终模型）


@dataclass(frozen=True)
class SelectionDecision:
    position: tuple[float, float]
    score: float
    q_geo: float
    p_rec: float
    travel_s: float
    r_pred_m: float


def add(point, length, angle_deg):
    angle = math.radians(angle_deg)
    return (point[0] + length * math.cos(angle), point[1] + length * math.sin(angle))


def bearing(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def wrap(angle_deg):
    return (angle_deg + 180.0) % 360.0 - 180.0


def normal(values, value):
    """min-max 归一化；上界等于下界时取 1.0。"""
    lo, hi = min(values), max(values)
    return 1.0 if hi <= lo else (value - lo) / (hi - lo)


def raw_metrics(samples, observations, current_position, candidate, min_receive_r,
                predicted_radius, third="completion"):
    """四项原始指标 q_geo、p_rec、travel_s、r_pred；候选点看不到任何样本时返回 None。

    q_geo：对全部信念样本取「与历史各站交角 sin²」的最大值再平均，衡量交会几何质量；
    p_rec：候选点在保证接收半径内的样本占比；
    third="move"       第三指标为到候选点的移动时间（C 口径）；
    third="completion" 第三指标为完成时间 = (到候选点 + 候选点到预测圆心)/v + 6 s（C+ 起口径）。
    """
    if not samples:
        return None
    receive = [target for target in samples if math.dist(candidate, target) <= min_receive_r]
    if not receive:
        return None
    qualities = []
    for target in samples:
        candidate_angle = bearing(candidate, target)
        qualities.append(max((math.sin(math.radians(wrap(bearing(station, target) - candidate_angle))) ** 2
                              for station, _ in observations), default=0.0))
    radii, centers = [], []
    for target in receive:
        center, radius = predicted_radius(candidate, bearing(candidate, target))
        if math.isfinite(radius):
            radii.append(radius)
            centers.append(center)
    if not radii:
        return None
    q_geo = sum(qualities) / len(qualities)
    p_rec = len(receive) / len(samples)
    r_pred = sum(radii) / len(radii)
    if third == "move":
        return q_geo, p_rec, math.dist(current_position, candidate) / SPEED, r_pred
    post_distance = sum(math.dist(candidate, center) for center in centers) / len(centers)
    path_distance = math.dist(current_position, candidate) + post_distance
    return q_geo, p_rec, path_distance / SPEED + MEASURE_TIME_S, r_pred


def score_pool(pool, weights, metrics_fn):
    """池内四项指标各自 min-max 归一化后加权：J = w1·q_geo + w2·p_rec − w3·travel_s − w4·r_pred。"""
    rows = [(q, *metrics_fn(q)) for q in pool]
    rows = [(q, *m) for q, *m in rows if m[0] is not None]
    if not rows:
        return []
    columns = [[row[i] for row in rows] for i in range(1, 5)]
    scored = []
    for q, q_geo, p_rec, travel_s, r_pred in rows:
        normalized = [normal(columns[i], value)
                      for i, value in enumerate((q_geo, p_rec, travel_s, r_pred))]
        score = (weights[0] * normalized[0] + weights[1] * normalized[1]
                 - weights[2] * normalized[2] - weights[3] * normalized[3])
        scored.append(SelectionDecision(q, score, q_geo, p_rec, travel_s, r_pred))
    return scored


def select_from_scored(scored):
    """高分区（range-based R_good 带）内优先短移动，其次取预测包围圆更小的点。"""
    peak = max(item.score for item in scored)
    low = min(item.score for item in scored)
    threshold = peak - GOOD_ETA * (peak - low)
    return min((item for item in scored if item.score >= threshold),
               key=lambda item: (item.travel_s, item.r_pred_m, -item.score))


def next_measurement_point(station, bearing_deg, weights, metrics_fn):
    """选点主流程：粗网格（5 距离 × 6 方位）取前二 → ±100 m、±10° 邻域加密 → 重算分数。

    加密集上重新归一化与评分（与第二问求解器完全一致），最后选执行点。
    """
    coarse_points = [add(station, d, bearing_deg + offset)
                     for d in COARSE_DISTANCES for offset in range(0, 360, int(COARSE_BEARING_STEP))]
    coarse = score_pool(coarse_points, weights, metrics_fn)
    if not coarse:
        return None
    seeds = sorted(coarse, key=lambda item: item.score, reverse=True)[:2]
    refined_points, seen = [], set()
    for item in seeds:
        distance = math.dist(station, item.position)
        base = bearing(station, item.position)
        for dd in (max(50.0, distance - 100.0), distance, min(1800.0, distance + 100.0)):
            for da in (-10.0, 0.0, 10.0):
                point = add(station, dd, base + da)
                key = (round(point[0], 9), round(point[1], 9))
                if key not in seen:
                    seen.add(key)
                    refined_points.append(point)
    refined = score_pool(refined_points, weights, metrics_fn) or coarse
    return select_from_scored(refined)

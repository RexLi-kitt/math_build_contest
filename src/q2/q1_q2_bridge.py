"""问题1到问题2的可复用接口。

问题2只在离线评估时枚举首次观测后的可能目标位置；运行策略不读取真实源坐标。
每个候选第二点均调用问题1的角度带交集、区域直径和同直径圆覆盖判定。
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "q1"))
from localization import HalfPlane, bearing_halfplanes, convex_diameter, diameter_circle_coverage, intersect_halfplanes  # noqa: E402

RADIUS, SPEED, ERROR = 1800.0, 5.0, 1.0


@dataclass(frozen=True)
class Q1Evaluation:
    status: str
    diameter_m: float
    mec_radius_m: float
    diameter_circle_covers: bool


def _wrap(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


def _bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _disk_halfplanes(sides: int = 64) -> list[HalfPlane]:
    """内接正多边形逼近作业圆，保证评价区域不超出半径1800 m圆盘。"""
    if sides < 12:
        raise ValueError("sides 至少为12")
    apothem = RADIUS * math.cos(math.pi / sides)
    return [HalfPlane(math.cos(2 * math.pi * k / sides), math.sin(2 * math.pi * k / sides), apothem)
            for k in range(sides)]


def _mec_radius(vertices) -> float:
    """小规模凸多边形的最小外接圆半径：枚举两点圆与三点圆。"""
    pts = [(float(x), float(y)) for x, y in vertices]
    if len(pts) <= 1:
        return 0.0
    best = math.inf
    def test(cx, cy, r):
        nonlocal best
        if r < best and all((x-cx)**2+(y-cy)**2 <= r*r + 1e-7 for x,y in pts): best = r
    for i, a in enumerate(pts):
        for b in pts[i+1:]:
            cx,cy=(a[0]+b[0])/2,(a[1]+b[1])/2; test(cx,cy,math.dist(a,b)/2)
    for i,a in enumerate(pts):
        for j,b in enumerate(pts[i+1:],i+1):
            for c in pts[j+1:]:
                d=2*(a[0]*(b[1]-c[1])+b[0]*(c[1]-a[1])+c[0]*(a[1]-b[1]))
                if abs(d)<1e-10: continue
                aa=a[0]**2+a[1]**2; bb=b[0]**2+b[1]**2; cc=c[0]**2+c[1]**2
                cx=(aa*(b[1]-c[1])+bb*(c[1]-a[1])+cc*(a[1]-b[1]))/d
                cy=(aa*(c[0]-b[0])+bb*(a[0]-c[0])+cc*(b[0]-a[0]))/d
                test(cx,cy,math.dist((cx,cy),a))
    return best


def evaluate_with_q1(stations: Iterable[tuple[float, float]], bearings_deg: Iterable[float]) -> Q1Evaluation:
    """调用问题1求解器，返回问题2评分所需的几何不确定性指标。"""
    constraints = list(bearing_halfplanes(stations, bearings_deg, ERROR)) + _disk_halfplanes()
    region = intersect_halfplanes(constraints)
    if region.status in {"empty", "unbounded"}:
        return Q1Evaluation(region.status, math.inf, math.inf, False)
    diameter = convex_diameter(region.vertices)
    coverage = diameter_circle_coverage(region.vertices)
    return Q1Evaluation(region.status, diameter.distance, _mec_radius(region.vertices), coverage.covers)


def initial_targets(s1: tuple[float, float], first_bearing: float, radial_count: int = 3, angle_count: int = 3) -> list[tuple[float, float]]:
    """首次 direction 后的离散可行样本：(5,1500] m 与 ±1° 角度带，而非[1000,1500]。"""
    points = []
    for d in [5.1 + (1500.0 - 5.1) * i / (radial_count - 1) for i in range(radial_count)]:
        for err in [-ERROR + 2 * ERROR * j / (angle_count - 1) for j in range(angle_count)]:
            phi = math.radians(first_bearing + err)
            g = (s1[0] + d * math.cos(phi), s1[1] + d * math.sin(phi))
            if g[0] * g[0] + g[1] * g[1] <= RADIUS * RADIUS:
                points.append(g)
    return points


def score_second_point(s1: tuple[float, float], first_bearing: float, s2: tuple[float, float], weights=(2.2,.8,.004,1.2,.003)) -> dict[str, float]:
    """以问题1输出的中位最小外接圆半径、直径为核心，计算候选第二点评分。"""
    targets = initial_targets(s1, first_bearing)
    if not targets:
        raise ValueError("首次观测可行区为空")
    radii, diameters, geometry, received = [], [], [], []
    for g in targets:
        b2 = _bearing(s2, g)
        q1 = evaluate_with_q1([s1, s2], [first_bearing, b2])
        radii.append(q1.mec_radius_m); diameters.append(q1.diameter_m)
        alpha = abs(_wrap(_bearing(s1, g) - b2)); alpha = min(alpha, 180 - alpha)
        geometry.append(math.sin(math.radians(alpha)) ** 2)
        received.append(float(math.dist(s2, g) <= 1000.0))  # 对未知半径的保守保证
    travel = math.dist(s1, s2) / SPEED
    boundary_risk = max(0.0, 0.20 - (RADIUS - math.hypot(*s2)) / RADIUS)
    r_med = sorted(radii)[len(radii) // 2]
    d_med = sorted(diameters)[len(diameters) // 2]
    q_geo = sum(geometry) / len(geometry); p_rec = sum(received) / len(received)
    # R_mec 越小越好；权重后续可用问题1回放数据校准。
    w1,w2,w3,w4,w5=weights
    score = w1*q_geo + w2*p_rec - w3*travel - w4*boundary_risk - w5*r_med
    return {"score": score, "q_geo": q_geo, "p_rec": p_rec, "travel_s": travel,
            "boundary_risk": boundary_risk, "predicted_diameter_m": d_med,
            "predicted_mec_radius_m": r_med}

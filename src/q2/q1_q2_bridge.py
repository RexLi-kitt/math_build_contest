"""Q2方案卡接口：独立构造 A1/A2，仅复用 Q1 的角度带求交方法。"""
from __future__ import annotations
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "q1"))
from localization import HalfPlane, bearing_halfplanes, convex_diameter, intersect_halfplanes  # noqa: E402

RADIUS, SPEED, ERROR, DISK_SIDES = 1800.0, 5.0, 1.0, 64
MIN_DIRECTION_DISTANCE, MAX_DIRECTION_DISTANCE, GUARANTEE_RADIUS = 5.0, 1500.0, 1000.0

@dataclass(frozen=True)
class RegionEvaluation:
    status: str
    diameter_m: float
    mec_radius_m: float
    vertices: tuple[tuple[float, float], ...]

def bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))

def _wrap(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0

def _circle_halfplanes(center: tuple[float, float], radius: float, sides: int = DISK_SIDES) -> list[HalfPlane]:
    """外接正多边形包络圆盘，保守地保留圆盘内全部真值。"""
    return [HalfPlane(math.cos(2*math.pi*k/sides), math.sin(2*math.pi*k/sides),
                      radius + center[0]*math.cos(2*math.pi*k/sides) + center[1]*math.sin(2*math.pi*k/sides))
            for k in range(sides)]

def _mec_radius(vertices: Iterable[tuple[float, float]]) -> float:
    pts = [(float(x), float(y)) for x, y in vertices]
    if len(pts) <= 1: return 0.0
    best = math.inf
    def accept(cx: float, cy: float, r: float) -> None:
        nonlocal best
        if r < best and all((x-cx)**2 + (y-cy)**2 <= r*r + 1e-7 for x,y in pts): best = r
    for i, a in enumerate(pts):
        for b in pts[i+1:]:
            cx,cy=(a[0]+b[0])/2,(a[1]+b[1])/2; accept(cx,cy,math.dist(a,b)/2)
    for i,a in enumerate(pts):
        for j,b in enumerate(pts[i+1:],i+1):
            for c in pts[j+1:]:
                d=2*(a[0]*(b[1]-c[1])+b[0]*(c[1]-a[1])+c[0]*(a[1]-b[1]))
                if abs(d) < 1e-10: continue
                aa,bb,cc=a[0]**2+a[1]**2,b[0]**2+b[1]**2,c[0]**2+c[1]**2
                cx=(aa*(b[1]-c[1])+bb*(c[1]-a[1])+cc*(a[1]-b[1]))/d
                cy=(aa*(c[0]-b[0])+bb*(a[0]-c[0])+cc*(b[0]-a[0]))/d
                accept(cx,cy,math.dist((cx,cy),a))
    return best

def _evaluate(constraints: list[HalfPlane]) -> RegionEvaluation:
    region = intersect_halfplanes(constraints)
    if region.status in {"empty", "unbounded"}:
        return RegionEvaluation(region.status, math.inf, math.inf, tuple())
    verts = tuple((float(x), float(y)) for x,y in region.vertices)
    return RegionEvaluation(region.status, convex_diameter(verts).distance, _mec_radius(verts), verts)

def a1_constraints(s1: tuple[float,float], first_bearing: float) -> list[HalfPlane]:
    """A1 的凸外壳：角度带∩目标圆∩首测 1500m 上界。

    5m 下界为一个微小的内孔，不能用半平面表示；其严格作用于样本与在线更新，
    而凸外壳含该内孔只会使 MEC 保守，不会导致提前清除。
    """
    return (list(bearing_halfplanes([s1], [first_bearing], ERROR))
            + _circle_halfplanes((0.0, 0.0), RADIUS)
            + _circle_halfplanes(s1, MAX_DIRECTION_DISTANCE))

def evaluate_a1(s1: tuple[float,float], first_bearing: float) -> RegionEvaluation:
    return _evaluate(a1_constraints(s1, first_bearing))

def evaluate_a2(s1: tuple[float,float], first_bearing: float,
                s2: tuple[float,float], second_bearing: float) -> RegionEvaluation:
    """实际/预测二测域 A2=A1∩第二条角度带。"""
    return _evaluate(a1_constraints(s1, first_bearing)
                     + list(bearing_halfplanes([s2], [second_bearing], ERROR)))

def initial_targets(s1: tuple[float,float], first_bearing: float,
                    radial_count: int = 3, angle_count: int = 3) -> list[tuple[float,float]]:
    """对 A1 作近似均匀面积采样；样本严格满足 5m 内孔与全部物理条件。"""
    points: list[tuple[float,float]] = []
    lo2, hi2 = MIN_DIRECTION_DISTANCE**2, MAX_DIRECTION_DISTANCE**2
    for i in range(radial_count):
        d = math.sqrt(lo2 + (hi2-lo2) * (i + 0.5) / radial_count)
        for j in range(angle_count):
            angle = first_bearing - ERROR + 2*ERROR*(j + 0.5)/angle_count
            phi = math.radians(angle); g=(s1[0]+d*math.cos(phi), s1[1]+d*math.sin(phi))
            if g[0]*g[0]+g[1]*g[1] <= RADIUS*RADIUS:
                points.append(g)
    return points

def no_signal_update(targets: Iterable[tuple[float,float]], s2: tuple[float,float]) -> list[tuple[float,float]]:
    """已知全向源下，no_signal 只能确定地排除 1000m 保证接收圆盘。"""
    return [g for g in targets if math.dist(g, s2) > GUARANTEE_RADIUS]

def raw_four_metrics(s1: tuple[float,float], first_bearing: float,
                     s2: tuple[float,float], targets: Iterable[tuple[float,float]]) -> dict[str,float]:
    """方案卡四指标原始值。R_pred 仅在保证接收样本上定义。"""
    targets=list(targets)
    if not targets: raise ValueError("A1 样本为空")
    geo=[]; received=[]; predicted=[]
    for g in targets:
        b2=bearing(s2,g)
        alpha=abs(_wrap(bearing(s1,g)-b2)); alpha=min(alpha,180-alpha)
        geo.append(math.sin(math.radians(alpha))**2)
        if math.dist(g,s2) <= GUARANTEE_RADIUS:
            received.append(1.0)
            predicted.append(evaluate_a2(s1,first_bearing,s2,b2).mec_radius_m)
        else:
            received.append(0.0)
    n_receive=sum(received)
    return {"q_geo":sum(geo)/len(geo), "p_rec":n_receive/len(targets),
            "travel_s":math.dist(s1,s2)/SPEED,
            "r_pred_m":(sum(predicted)/n_receive if n_receive else math.inf),
            "guaranteed_samples":int(n_receive)}

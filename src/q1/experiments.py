"""可复现的 Q1 随机算例与定向边界测试，输出完整 JSON 和 Excel 可读 CSV。

运行：python -m src.q1.experiments --cases 100 --seed 20260911
S 表示真实干扰源，M_i 表示监测点；只模拟同一组内的单一固定干扰源。
"""

import argparse
from collections import Counter
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random

from .localization import (
    HalfPlane, convex_diameter, diameter_circle_coverage, intersect_halfplanes, localize,
)


def bearing(station, source):
    return math.degrees(math.atan2(source[1] - station[1], source[0] - station[0])) % 360


def wrap(angle):
    return (angle + 180) % 360 - 180


def source_in_hull(source, vertices):
    """独立于半平面 contains 的顶点边叉积检查，保留 Fraction 精度。"""
    if not vertices:
        return False
    p = tuple(Fraction(x) for x in source)
    if len(vertices) == 1:
        return p == vertices[0]
    def cross(a, b):
        return (b[0]-a[0])*(p[1]-a[1]) - (b[1]-a[1])*(p[0]-a[0])
    if len(vertices) == 2:
        a, b = vertices
        return cross(a, b) == 0 and all(min(a[i], b[i]) <= p[i] <= max(a[i], b[i]) for i in (0, 1))
    return all(cross(a, b) >= 0 for a, b in zip(vertices, vertices[1:] + vertices[:1]))


def evaluate(case_id, kind, source, stations, measured, note=""):
    observations = []
    for i, (station, angle) in enumerate(zip(stations, measured), 1):
        truth = bearing(station, source)
        observations.append({"case_id": case_id, "monitor": f"M{i}",
                             "x": station[0], "y": station[1],
                             "source_x": source[0], "source_y": source[1],
                             "true_bearing_deg": truth, "error_deg": wrap(angle-truth),
                             "measured_bearing_deg": angle,
                             "distance_to_source_m": math.dist(station, source)})
    record = {"case_id": case_id, "kind": kind, "source": list(source),
              "stations": [list(p) for p in stations], "observations": observations,
              "note": note, "checks": {}, "diameter_m": None, "circle_covers": None,
              "vertices": [], "endpoints": None}
    try:
        result = localize(stations, measured)
        region = result.region
        record["status"] = region.status
        checks = record["checks"]
        checks["input_error_within_bound"] = all(abs(o["error_deg"]) <= 1 + 1e-12 for o in observations)
        checks["truth_satisfies_halfplanes"] = all(h.contains(source) for h in result.halfplanes)
        checks["nonempty"] = region.status != "empty"
        if region.status == "unbounded":
            record["diameter_m"] = "∞"
            d = region.recession_direction
            checks["recession_direction_valid"] = bool(d[0] or d[1]) and all(h.a*d[0] + h.b*d[1] <= 0 for h in result.halfplanes)
            record["recession_direction"] = [str(x) for x in d]
        elif region.status != "empty":
            v = region.vertices
            reference = convex_diameter(v, method="exhaustive")
            checks["truth_inside_polygon"] = source_in_hull(source, v)
            checks["vertices_satisfy_halfplanes"] = all(h.contains(p) for h in result.halfplanes for p in v)
            checks["diameters_match_exactly"] = reference.squared_distance == result.diameter.squared_distance
            record.update(diameter_m=result.diameter.distance,
                          vertices=region.float_vertices(),
                          vertices_exact=[[str(x), str(y)] for x, y in v],
                          endpoints=[[float(x), float(y)] for x, y in result.diameter.endpoints],
                          circle_covers=result.circle.covers,
                          circle_radius_m=result.circle.radius,
                          circle_center=[float(x) for x in result.circle.center],
                          circle_excess_m=result.circle.max_excess)
        record["passed"] = all(checks.values())
    except (ArithmeticError, ValueError, TypeError) as exc:
        # 保留失败输入，继续执行其他组，不通过重抽样隐藏错误。
        record.update(status="error", passed=False, exception=f"{type(exc).__name__}: {exc}")
    return record


def generate_random_cases(count=100, seed=20260911):
    """S 在半径 1800 圆盘内面积均匀；每个 M 在以 S 为心的环域面积均匀。

    监测距离 50~900 米，避开 <=5 米盲区，且小于最小有效接收半径1000米。
    监测点允许位于目标圆域外，未强制好的交会角，也不筛掉无界组。
    """
    if count < 1:
        raise ValueError("随机组数至少为 1")
    rng = random.Random(seed)
    records = []
    for index in range(1, count + 1):
        radius, angle = 1800 * math.sqrt(rng.random()), rng.uniform(0, 2*math.pi)
        source = (radius*math.cos(angle), radius*math.sin(angle))
        stations, measured = [], []
        for _ in range(rng.randint(2, 6)):
            distance = math.sqrt(rng.uniform(50**2, 900**2))
            direction = rng.uniform(0, 2*math.pi)
            point = (source[0] + distance*math.cos(direction), source[1] + distance*math.sin(direction))
            stations.append(point)
            measured.append((bearing(point, source) + rng.uniform(-1, 1)) % 360)
        records.append(evaluate(f"MC{index:03d}", "蒙特卡洛", source, stations, measured))
    return records


def equilateral_case():
    """三组 ±1° 观测的交区域接近边长20米的等边三角形；数值容差1e-8米。"""
    side = 20.0
    height = side * math.sqrt(3)/2
    triangle = [(-side/2, -height/3), (side/2, -height/3), (0, 2*height/3)]
    stations, measured = [], []
    for a, b in zip(triangle, triangle[1:]+triangle[:1]):
        ux, uy = (b[0]-a[0])/side, (b[1]-a[1])/side
        stations.append((a[0]-600*ux, a[1]-600*uy))
        measured.append((math.degrees(math.atan2(uy, ux))+1) % 360)
    record = evaluate("EQ_LAST", "等边三角形反例", (0, 0), stations, measured,
                      "三条楔形交会反例；理论边长20米，最小外接圆半径20/√3米。三角函数产生浮点近似。")
    record["analytic"] = {"side_m": side, "diameter_m": side,
                          "minimum_circle_radius_m": side/math.sqrt(3),
                          "half_diameter_m": side/2, "tolerance_m": 1e-8}
    vertices = record["vertices"]
    record["checks"]["triangle_boundary_matches"] = bool(vertices) and all(min(math.dist(p,q) for q in vertices) < 1e-8 for p in triangle) and all(min(math.dist(p,q) for q in triangle) < 1e-8 for p in vertices)
    record["checks"]["analytic_diameter_matches"] = isinstance(record["diameter_m"], (int,float)) and abs(record["diameter_m"]-side) < 1e-8
    record["checks"]["counterexample_not_covered"] = record["circle_covers"] is False
    record["passed"] = record.get("passed", False) and all(record["checks"].values())
    return record


def boundary_cases():
    """不依赖随机碰撞制造退化。精确点、线段等用有理系数直接测试几何层。"""
    definitions = [
        ("EDGE01", "空集", [HalfPlane(1,0,0), HalfPlane(-1,0,-1)], "empty", None,
         "x≤0 且 x≥1", "返回空集和无有效直径；排查输入，不自动放宽误差。"),
        ("EDGE02", "无界", [HalfPlane(-1,0,0)], "unbounded", None,
         "x≥0", "直径记∞，保留无界状态；增加不同方向观测，不用矩形截断。"),
        ("EDGE03", "单点", [HalfPlane(1,0,2),HalfPlane(-1,0,-2),HalfPlane(0,1,3),HalfPlane(0,-1,-3)], "point", 0,
         "x=2, y=3", "合法退化结果：直径0，覆盖圆半径0。"),
        ("EDGE04", "线段", [HalfPlane(-1,0,0),HalfPlane(1,0,4),HalfPlane(0,1,3),HalfPlane(0,-1,-3)], "segment", 4,
         "0≤x≤4, y=3", "合法退化结果：返回端点，直径4米。"),
        ("EDGE05", "近乎平行的边界", [HalfPlane(-1,0,0),HalfPlane(0,-1,0),HalfPlane(1,Fraction(1,10**8),1)], "polygon", math.hypot(1,1e8),
         "x≥0,y≥0,x+10^-8*y≤1", "保留极狭长区域；有理数判定，不将近乎平行误当平行。此为几何层压力测试。"),
    ]
    rows = []
    for cid, label, constraints, expected, expected_d, specification, handling in definitions:
        region = intersect_halfplanes(constraints)
        diameter = convex_diameter(region.vertices) if region.vertices else None
        passed = region.status == expected
        if expected_d is not None:
            passed = passed and diameter is not None and math.isclose(diameter.distance, expected_d, rel_tol=1e-12, abs_tol=1e-12)
        if region.status == "unbounded":
            d = region.recession_direction
            passed = passed and bool(d[0] or d[1]) and all(h.a*d[0]+h.b*d[1] <= 0 for h in constraints)
        rows.append({"case_id": cid, "case": label, "layer": "半平面几何层", "input": specification,
                     "expected_status": expected, "actual_status": region.status,
                     "diameter_m": diameter.distance if diameter else "∞" if region.status=="unbounded" else None,
                     "expected_diameter_m": expected_d, "passed": passed, "handling": handling})
    for cid, label, source, stations, measured, handling in [
        ("EDGE06", "角度跨0°", (0,0), [(-500,0),(0,-500)], [359.5,90.2],
         "按圆周角度处理；向量半平面无需直接比较角度大小。"),
        ("EDGE07", "小交会角", (0,0), [(-500,-10),(-500,10)], None,
         "保留大的有限直径，提示交会几何较差；后续选择侧向检测点。"),
    ]:
        angles = measured if measured is not None else [bearing(m,source) for m in stations]
        record = evaluate(cid, label, source, stations, angles)
        rows.append({"case_id": cid, "case": label, "layer": "测向完整流程",
                     "input": f"S={source}; M={stations}; 示向度={angles}",
                     "expected_status": "polygon", "actual_status": record["status"],
                     "diameter_m": record["diameter_m"], "expected_diameter_m": None,
                     "passed": record["passed"] and record["status"]=="polygon", "handling": handling,
                     "detail": record})
    # 再覆盖完整角度入口的空集与无界，避免只有几何层检查。
    for cid, label, stations, measured, expected in [
        ("EDGE08", "相背观测导致空集", [(0,0),(100,0)], [180,0], "empty"),
        ("EDGE09", "单次测向无界", [(0,0)], [45], "unbounded"),
    ]:
        result = localize(stations, measured)
        rows.append({"case_id": cid, "case": label, "layer": "测向完整流程",
                     "input": f"M={stations}; 示向度={measured}", "expected_status": expected,
                     "actual_status": result.region.status,
                     "diameter_m": "∞" if expected=="unbounded" else None,
                     "expected_diameter_m": None,
                     "passed": result.region.status==expected and result.circle is None,
                     "handling": "人为异常输入，不指定共同真实S；与有效随机观测分开统计。"})
    return rows


def region_subset(inner, outer_halfplanes):
    """闭凸集 inner 是否包含于给定半平面交；空集视为被任意区域包含。"""
    if inner.status == "empty":
        return True
    if inner.status == "unbounded":
        witness, direction = inner.feasible_point, inner.recession_direction
        return (all(h.contains(witness) for h in outer_halfplanes)
                and all(h.a*direction[0] + h.b*direction[1] <= 0 for h in outer_halfplanes))
    return all(h.contains(vertex) for h in outer_halfplanes for vertex in inner.vertices)


def sensitivity_cases(cases, levels=(0.9, 1.0, 1.1)):
    """固定观测、只改误差半角：区域应随误差界放宽而扩张，非空有界时直径不减。

    模拟误差本身抽样于[-1°,1°]，故 0.9° 档可能把真值排除而出现空集，这是预期
    结果，只记录状态；空集与无界档的直径单调性记为不适用。
    """
    rows = []
    for case in cases:
        stations = case["stations"]
        measured = [o["measured_bearing_deg"] for o in case["observations"]]
        results = {level: localize(stations, measured, level) for level in levels}
        for index, level in enumerate(levels):
            result = results[level]
            region, diameter = result.region, result.diameter
            if index == 0:
                containment = diameter_monotone = None
            else:
                previous = results[levels[index-1]]
                containment = region_subset(previous.region, result.halfplanes)
                finite = (previous.diameter is not None and previous.diameter.squared_distance is not None
                          and diameter is not None and diameter.squared_distance is not None)
                diameter_monotone = (previous.diameter.squared_distance <= diameter.squared_distance) if finite else None
            rows.append({
                "case_id": case["case_id"], "error_deg": level, "status": region.status,
                "diameter_m": "∞" if region.status == "unbounded" else (diameter.distance if diameter else None),
                "containment": containment, "diameter_monotone": diameter_monotone,
                "passed": containment is not False and diameter_monotone is not False,
            })
    return rows


def write_csv(path, headers, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerows(rows)


def run(count, seed, output):
    output.mkdir(parents=True, exist_ok=True)
    random_cases = generate_random_cases(count, seed)
    cases = random_cases + [equilateral_case()]
    edge = boundary_cases()
    sensitivity = sensitivity_cases(random_cases)
    metadata = {
        "seed": seed, "random_case_count": count, "monitor_count": "离散均匀2~6",
        "source_sampling": "半径1800米圆盘内面积均匀",
        "monitor_sampling": "以S为圆心，半径50~900米环域内面积均匀；允许目标圆域外监测",
        "error_sampling": "各不同监测点独立均匀U(-1°,1°)，仅实验假设；误差界固定1°",
        "retention": "不按交会形状/结果筛选或重抽样；无界、失败均保留",
        "sensitivity_levels": "0.9°,1.0°,1.1°；固定同一组观测，只改误差半角",
        "units": "坐标及距离：米；角度：度",
        "source_name": "本表S为真实干扰源，M_i为监测点；旧方案G与此处S同义",
        "rounding": "计算使用完整精度；Excel展示坐标/直径6位、角度9位小数",
        "recalculation": "表格为已运行结果快照；更改数据后需重跑Python，不会在Excel中自动调用定位函数",
        "code_sha256": {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('localization.py')]},
    }
    summary = {"random_status_counts": dict(Counter(c["status"] for c in random_cases)),
               "random_passed": sum(c["passed"] for c in random_cases),
               "random_count": count, "edge_passed": sum(c["passed"] for c in edge),
               "edge_count": len(edge), "counterexample_passed": cases[-1]["passed"],
               "sensitivity_passed": sum(r["passed"] for r in sensitivity),
               "sensitivity_count": len(sensitivity)}
    payload = {"metadata":metadata, "summary":summary, "cases":cases,
               "boundary_cases":edge, "sensitivity":sensitivity}
    (output/'experiment_data.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    headers = ["组号","类型","S_x(m)","S_y(m)","监测点数","区域状态","直径(m)","同直径圆覆盖","检查结果"]
    for i in range(1,7):
        headers += [f"M{i}_x(m)",f"M{i}_y(m)"]
    rows=[]
    for c in cases:
        row=[c['case_id'],c['kind'],*c['source'],len(c['stations']),c['status'],c['diameter_m'],c['circle_covers'],"通过" if c['passed'] else "失败"]
        for i in range(6):
            row += c['stations'][i] if i<len(c['stations']) else [None,None]
        rows.append(row)
    write_csv(output/'定位实验汇总.csv', headers, rows)
    observations=[o for c in cases for o in c['observations']]
    keys=["case_id","monitor","x","y","source_x","source_y","true_bearing_deg","error_deg","measured_bearing_deg","distance_to_source_m"]
    write_csv(output/'观测明细.csv', ["组号","监测点","M_x(m)","M_y(m)","S_x(m)","S_y(m)","真实方位(°)","加入误差(°)","示向度(°)","源点距离(m)"], [[o[k] for k in keys] for o in observations])
    write_csv(output/'边界测试.csv', ["编号","情况","测试层","输入","预期状态","实际状态","直径(m)","检查结果","处理方式"],
              [[c['case_id'],c['case'],c['layer'],c['input'],c['expected_status'],c['actual_status'],c['diameter_m'],"通过" if c['passed'] else "失败",c['handling']] for c in edge])
    write_csv(output/'误差界敏感性.csv', ["组号","误差半角(°)","区域状态","直径(m)","包含检查","直径不减检查","检查结果"],
              [[r['case_id'],r['error_deg'],r['status'],r['diameter_m'],
                "基准" if r['containment'] is None else "通过" if r['containment'] else "失败",
                "不适用" if r['diameter_monotone'] is None else "通过" if r['diameter_monotone'] else "失败",
                "通过" if r['passed'] else "失败"] for r in sensitivity])
    print(json.dumps(summary, ensure_ascii=False))
    if (summary['random_passed'] != count or summary['edge_passed'] != len(edge)
            or not summary['counterexample_passed']
            or summary['sensitivity_passed'] != summary['sensitivity_count']):
        raise SystemExit("存在未通过算例，请检查已保留的输入和检查项。")
    return payload


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=int, default=100)
    parser.add_argument('--seed', type=int, default=20260911)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent/'results')
    args=parser.parse_args()
    run(args.cases, args.seed, args.output)

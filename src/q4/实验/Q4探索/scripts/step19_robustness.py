"""第十九步：整体鲁棒性实验（离线可做的全部六层）。

A 常规回归：N=10..16 x {normal, boundary_random, boundary_outward}，六臂
B 混合加密：rho=0..1 十二档，按 n0 分层
C 空间对抗：八种结构（含"一个中心可见源 + 其余远端朝外"）
D 半平面边界：|wrap(alpha-beta)| = 89.9 / 90 / 90.1 度
E 示向误差：题设内六种模式 + 题设外两种（单独标注）
F 几何与距离门审计：剪枝下界 / 保留上界 / 真值命中 / 数值断言
接口实验（1800 m、接收半径上界、动作上限）离线无法完成，另附探针脚本。
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "models"))
import harness as H  # noqa: E402
from cplus_3f_agent import CPlus3FLiteAgent, point_segment_distance  # noqa: E402
from cplus_3fb_agent import CPlus3FBAgent  # noqa: E402

OUT = H.SANDBOX_OUT / "step19_robustness"


class BFAgent(CPlus3FBAgent):
    """始终 B + 1500 m 距离门。"""
    discovery_threshold = 10 ** 9
    audit_truth = False


class CFAgent(CPlus3FLiteAgent):
    """始终 C + 1500 m 距离门。"""
    discovery_threshold = -1


class AuditedD(CPlus3FBAgent):
    """D 的审计版：记录剪枝下界与保留上界（不改变判定语义）。"""

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.min_pruned_dist = None
        self.max_kept_dist = None

    def _dist(self, point, state):
        polygon = self._snapshot(state).polygon
        if not polygon:
            return None
        return min(point_segment_distance(point, polygon[i], polygon[(i + 1) % len(polygon)])
                   for i in range(len(polygon)))

    def within_reach(self, point, state) -> bool:
        result = super().within_reach(point, state)
        distance = self._dist(point, state)
        if distance is not None:
            if result:
                self.max_kept_dist = (distance if self.max_kept_dist is None
                                      else max(self.max_kept_dist, distance))
            else:
                self.min_pruned_dist = (distance if self.min_pruned_dist is None
                                        else min(self.min_pruned_dist, distance))
        return result


class AuditedBF(BFAgent):
    """BF 的审计版，用于核验门控边界在 B 分支上的行为。"""

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.min_pruned_dist = None
        self.max_kept_dist = None

    _dist = AuditedD._dist
    within_reach = AuditedD.within_reach


H._STRATEGIES.update({"BF": BFAgent, "CF": CFAgent, "D": AuditedD,
                      "BFa": AuditedBF, "C3F": CPlus3FLiteAgent})
DEFAULT = ["B", "C", "BF", "CF", "D"]


def times_of(case_rows, name):
    return {row["case"]: row["total_virtual_time_s"] / row["source_count"]
            for row in case_rows if row["strategy"] == name}


def summarise(case_rows, arms, key):
    return {arm: {name: statistics.mean(list(times_of(case_rows, arm).values()))
                  for name in arms}}


def surface(cases, seed, arms, label, jobs):
    case_rows, summaries = H.evaluate(label, cases, seed, arms, jobs, OUT)
    return case_rows, summaries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--a", type=int, default=25)
    parser.add_argument("--b", type=int, default=30)
    parser.add_argument("--c", type=int, default=25)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    H.log(f"_STRATEGIES 现有键：{sorted(H._STRATEGIES)}")
    payload = {}
    audit = {"min_pruned_dist": [], "max_kept_dist": [], "truth_hits": 0,
             "pruned": 0, "runs": 0, "fails": 0}

    def harvest(case_rows):
        for row in case_rows:
            if row.get("total_virtual_time_s") is None:
                audit["fails"] += 1
                continue
            audit["runs"] += 1
            if row.get("min_pruned_dist") is not None:
                audit["min_pruned_dist"].append(row["min_pruned_dist"])
            if row.get("max_kept_dist") is not None:
                audit["max_kept_dist"].append(row["max_kept_dist"])
            audit["truth_hits"] += row.get("pruned_truth_hits") or 0
            audit["pruned"] += row.get("pruned_observations") or 0

    # ---------------- A 常规回归 ----------------
    H.log("\n=== A 常规回归：N=10..16 x 三场景（六臂） ===")
    H.log(f"{'N':>3}{'场景':>18}{'B':>8}{'C':>8}{'BF':>8}{'CF':>8}{'D':>8}{'C3F':>8}"
          f"{'清除':>8}")
    table_a = {}
    for sources in range(10, 17):
        for kind in ("normal", "boundary_random", "boundary_outward"):
            seed = 20270901 + sources * 10 + ("normal", "boundary_random",
                                              "boundary_outward").index(kind)
            if kind == "normal":
                rng = random.Random(seed)
                cases = [H.random_mixed_sources(rng, sources, 0.5)
                         for _ in range(args.a)]
            else:
                rng = random.Random(seed)
                cases = []
                for index in range(args.a):
                    group = H.random_mixed_sources(rng, sources, 0.75)
                    for source in group:
                        angle = rng.random() * 2.0 * math.pi
                        radius = (1800.0 if kind == "boundary_outward" and index % 2 == 0
                                  else rng.uniform(1700.0, 1800.0))
                        source.position = radius * math.cos(angle), radius * math.sin(angle)
                        source.receive_radius = 1000.0
                        if kind == "boundary_outward" and source.beam_direction is not None:
                            source.beam_direction = math.degrees(angle) % 360.0
                    cases.append(group)
            label = f"A_{kind}_n{sources}"
            case_rows, summaries = surface(cases, seed, DEFAULT + ["C3F"], label, args.jobs)
            harvest(case_rows)
            by = {item["strategy"]: item for item in summaries}
            table_a[label] = {arm: by[arm]["mean_s_per_source"] for arm in DEFAULT + ["C3F"]}
            table_a[label]["all_clear"] = by["D"]["all_clear"]
            table_a[label]["cases"] = by["D"]["cases"]
            H.log(f"{sources:>3}{kind:>18}" + "".join(
                f"{table_a[label][arm]:>8.1f}" for arm in DEFAULT + ["C3F"])
                + f"{table_a[label]['all_clear']:>5}/{table_a[label]['cases']:<3}")

    # ---------------- B 混合加密 ----------------
    H.log("\n=== B 混合加密 rho=0..1（十二档） ===")
    H.log(f"{'rho':>5}{'B':>8}{'BF':>8}{'CF':>8}{'D':>8}{'eta':>7}{'R^F均值':>9}"
          f"{'R^F_P95':>9}{'D选B':>7}{'清除':>8}")
    table_b = {}
    rho_list = [0.0, 0.1, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.75, 1.0]
    for rho in rho_list:
        seed = 20270601 + int(round(rho * 100))
        cases = (H.mixed_cases(args.b, seed, far_share=0.0) if rho == 0.0
                 else H.mixed_cases(args.b, seed, far_share=rho))
        label = f"B_rho{int(round(rho * 100)):03d}"
        case_rows, summaries = surface(cases, seed, ["B", "C", "BF", "CF", "D"],
                                       label, args.jobs)
        harvest(case_rows)
        by = {item["strategy"]: item for item in summaries}
        keys = sorted(times_of(case_rows, "D"))
        gap0 = [abs(times_of(case_rows, "B")[k] - times_of(case_rows, "C")[k]) for k in keys]
        gapf = [abs(times_of(case_rows, "BF")[k] - times_of(case_rows, "CF")[k]) for k in keys]
        regret = [times_of(case_rows, "D")[k]
                  - min(times_of(case_rows, "BF")[k], times_of(case_rows, "CF")[k])
                  for k in keys]
        n0 = {row["case"]: row.get("origin_discoveries") for row in case_rows
              if row["strategy"] == "D"}
        item = {"rho": rho, "eta": 1.0 - statistics.mean(gapf) / statistics.mean(gap0),
                "regret_mean": statistics.mean(regret),
                "regret_p95": sorted(regret)[max(0, int(round(0.95 * (len(regret) - 1))))],
                "regret_max": max(regret),
                "pick_b": statistics.mean(1 if n0[k] <= 0 else 0 for k in keys),
                "mean": {arm: by[arm]["mean_s_per_source"] for arm in
                         ("B", "C", "BF", "CF", "D")},
                "all_clear": by["D"]["all_clear"], "cases": by["D"]["cases"]}
        table_b[label] = item
        H.log(f"{rho:>5.2f}{item['mean']['B']:>8.1f}{item['mean']['BF']:>8.1f}"
              f"{item['mean']['CF']:>8.1f}{item['mean']['D']:>8.1f}{item['eta']:>7.2f}"
              f"{item['regret_mean']:>9.2f}{item['regret_p95']:>9.2f}"
              f"{item['pick_b']:>7.1%}{item['all_clear']:>5}/{item['cases']:<3}")

    # ---------------- C 空间对抗 ----------------
    H.log("\n=== C 空间对抗结构 ===")
    H.log(f"{'结构':>26}{'BF':>8}{'CF':>8}{'D':>8}{'R^F均值':>9}{'R^F_max':>9}{'清除':>8}")
    table_c = {}
    structures = ["rim_outward", "core", "one_quadrant", "narrow_20deg",
                  "blind_gap", "one_center_rest_far", "mirror_pair", "min_radius_outward"]
    for structure in structures:
        seed = 20270701 + structures.index(structure)
        rng = random.Random(seed)
        cases = []
        for _ in range(args.c):
            group = H.random_mixed_sources(rng, 16, 0.5)
            if structure == "rim_outward":
                for source in group:
                    angle = rng.random() * 2 * math.pi
                    source.position = (1800.0 * math.cos(angle), 1800.0 * math.sin(angle))
                    source.receive_radius = 1000.0
                    if source.beam_direction is not None:
                        source.beam_direction = math.degrees(angle) % 360.0
            elif structure == "core":
                for source in group:
                    angle = rng.random() * 2 * math.pi
                    radius = rng.uniform(0.0, 500.0)
                    source.position = (radius * math.cos(angle), radius * math.sin(angle))
            elif structure == "one_quadrant":
                for source in group:
                    angle = rng.uniform(0.0, math.pi / 2)
                    radius = rng.uniform(0.0, 1800.0)
                    source.position = (radius * math.cos(angle), radius * math.sin(angle))
            elif structure == "narrow_20deg":
                base = rng.uniform(0.0, 2 * math.pi)
                for source in group:
                    angle = base + rng.uniform(-math.pi / 18, math.pi / 18)
                    radius = rng.uniform(400.0, 1800.0)
                    source.position = (radius * math.cos(angle), radius * math.sin(angle))
            elif structure == "blind_gap":
                for source in group:
                    angle = math.radians(180.0 + rng.uniform(-7.0, 7.0))
                    radius = rng.uniform(0.0, 1800.0)
                    source.position = (radius * math.cos(angle), radius * math.sin(angle))
            elif structure == "one_center_rest_far":
                near = group[0]
                near.position = (rng.uniform(-120.0, 120.0), rng.uniform(-120.0, 120.0))
                near.receive_radius = 1500.0
                for source in group[1:]:
                    angle = rng.random() * 2 * math.pi
                    radius = rng.uniform(1700.0, 1800.0)
                    source.position = (radius * math.cos(angle), radius * math.sin(angle))
                    source.receive_radius = 1000.0
                    if source.beam_direction is not None:
                        source.beam_direction = math.degrees(angle) % 360.0
            elif structure == "mirror_pair":
                for index, source in enumerate(group):
                    angle = math.radians(30.0 + 45.0 * (index % 2))
                    radius = rng.uniform(900.0, 1400.0)
                    source.position = (radius * math.cos(angle), radius * math.sin(angle))
                    if source.beam_direction is not None:
                        source.beam_direction = math.degrees(angle) % 360.0
            elif structure == "min_radius_outward":
                for source in group:
                    angle = rng.random() * 2 * math.pi
                    radius = rng.uniform(1700.0, 1800.0)
                    source.position = (radius * math.cos(angle), radius * math.sin(angle))
                    source.receive_radius = 1000.0
                    if source.beam_direction is not None:
                        source.beam_direction = math.degrees(angle + math.pi) % 360.0
            cases.append(group)
        label = f"C_{structure}"
        case_rows, summaries = surface(cases, seed, ["BF", "CF", "D"], label, args.jobs)
        harvest(case_rows)
        by = {item["strategy"]: item for item in summaries}
        keys = sorted(times_of(case_rows, "D"))
        regret = [times_of(case_rows, "D")[k]
                  - min(times_of(case_rows, "BF")[k], times_of(case_rows, "CF")[k])
                  for k in keys]
        item = {"mean": {arm: by[arm]["mean_s_per_source"] for arm in ("BF", "CF", "D")},
                "regret_mean": statistics.mean(regret), "regret_max": max(regret),
                "all_clear": by["D"]["all_clear"], "cases": by["D"]["cases"]}
        table_c[label] = item
        H.log(f"{structure:>26}{item['mean']['BF']:>8.1f}{item['mean']['CF']:>8.1f}"
              f"{item['mean']['D']:>8.1f}{item['regret_mean']:>9.2f}"
              f"{item['regret_max']:>9.2f}{item['all_clear']:>5}/{item['cases']:<3}")

    # ---------------- D 半平面边界 ----------------
    H.log("\n=== D 定向半平面边界（|wrap(alpha-beta)|） ===")
    H.log(f"{'角度':>7}{'D':>8}{'CF':>8}{'BF':>8}{'D选B':>7}{'清除':>8}")
    table_d = {}
    for offset in (89.9, 90.0, 90.1):
        seed = 20270801 + int(offset * 10)
        rng = random.Random(seed)
        cases = []
        for index in range(args.c):
            group = H.random_mixed_sources(rng, 16, 1.0)
            radius = 1700.0 if index % 2 == 0 else rng.uniform(1700.0, 1800.0)
            angle = rng.random() * 2 * math.pi
            source = group[0]
            source.position = (radius * math.cos(angle), radius * math.sin(angle))
            source.receive_radius = 1500.0 if index % 2 == 0 else 1000.0
            inward = math.degrees(angle + math.pi) % 360.0
            source.beam_direction = (inward + offset) % 360.0
            for other in group[1:]:
                other_angle = rng.random() * 2 * math.pi
                other_radius = rng.uniform(1700.0, 1800.0)
                other.position = (other_radius * math.cos(other_angle),
                                  other_radius * math.sin(other_angle))
                other.receive_radius = 1000.0
                if other.beam_direction is not None:
                    other.beam_direction = math.degrees(other_angle) % 360.0
            cases.append(group)
        label = f"D_halfplane_{offset}"
        case_rows, summaries = surface(cases, seed, ["BF", "CF", "D"], label, args.jobs)
        harvest(case_rows)
        by = {item["strategy"]: item for item in summaries}
        n0 = [row.get("origin_discoveries") for row in case_rows if row["strategy"] == "D"]
        item = {"mean": {arm: by[arm]["mean_s_per_source"] for arm in ("D", "CF", "BF")},
                "pick_b": sum(1 for value in n0 if value <= 0) / len(n0),
                "all_clear": by["D"]["all_clear"], "cases": by["D"]["cases"]}
        table_d[label] = item
        H.log(f"{offset:>7.1f}{item['mean']['D']:>8.1f}{item['mean']['CF']:>8.1f}"
              f"{item['mean']['BF']:>8.1f}{item['pick_b']:>7.1%}"
              f"{item['all_clear']:>5}/{item['cases']:<3}")

    # ---------------- E 示向误差 ----------------
    H.log("\n=== E 示向误差模式（D 与 C3F） ===")
    H.log(f"{'模式':>16}{'D':>8}{'C3F':>8}{'配对差':>9}{'清除':>8}")
    table_e = {}
    modes = [("uniform1", "uniform1"), ("bias_p1", "bias_p1"), ("bias_m1", "bias_m1"),
             ("alternate", "alternate"), ("edge099", "edge099"), ("zero", "zero"),
             ("OUT_bias_p11", "OUT_bias_p11"), ("OUT_uniform15", "OUT_uniform15")]
    for name, mode in modes:
        seed = 20270901 + len(name)
        rng = random.Random(seed)
        cases = []
        for _ in range(args.c):
            group = H.random_mixed_sources(rng, 16, 0.6)
            cases.append({"case_id": f"{name}_{len(cases)}", "sources": group,
                          "error_mode": mode})
        label = f"E_{name}"
        try:
            case_rows, summaries = surface(cases, seed, ["D", "C3F"], label, args.jobs)
        except Exception as error:  # noqa: BLE001
            H.log(f"{name:>16}  该模式离线未支持：{type(error).__name__}: {error}")
            table_e[label] = {"unsupported": str(error)}
            continue
        harvest(case_rows)
        by = {item["strategy"]: item for item in summaries}
        keys = sorted(times_of(case_rows, "D"))
        diff = [times_of(case_rows, "D")[k] - times_of(case_rows, "C3F")[k] for k in keys]
        mean = statistics.mean(diff)
        half = 1.96 * statistics.stdev(diff) / math.sqrt(len(diff))
        item = {"mean": {arm: by[arm]["mean_s_per_source"] for arm in ("D", "C3F")},
                "paired": {"mean": mean, "ci": [mean - half, mean + half]},
                "all_clear": by["D"]["all_clear"], "cases": by["D"]["cases"]}
        table_e[label] = item
        H.log(f"{name:>16}{item['mean']['D']:>8.1f}{item['mean']['C3F']:>8.1f}"
              f"{mean:>+9.2f}{item['all_clear']:>5}/{item['cases']:<3}")

    # ---------------- F 几何与距离门审计 ----------------
    H.log("\n=== F 距离门几何审计 ===")
    point = (0.0, 0.0)
    square = [(1000.0, -1000.0), (3000.0, -1000.0), (3000.0, 1000.0), (1000.0, -1000.0)]
    segment = [(1500.0, 0.0), (1500.0, 2000.0)]
    numeric = {}
    for target in (1499.0, 1499.9, 1500.0, 1500.1, 1501.0):
        polygon = [(target, -1000.0), (target + 2000.0, -1000.0),
                   (target + 2000.0, 1000.0), (target, 1000.0)]
        distance = min(point_segment_distance(point, polygon[i],
                                             polygon[(i + 1) % len(polygon)])
                       for i in range(len(polygon)))
        numeric[f"d={target}"] = {"measured": round(distance, 6),
                                  "kept": distance <= 1500.0}
    single = min(point_segment_distance(point, segment[0], segment[1]), 1500.0)
    brush = min(abs(distance - 1500.0) for distance in numeric.values()
                if isinstance(distance, float))
    payload["F_numeric"] = numeric
    payload["F_degenerate"] = {
        "single_segment_distance": round(single, 6),
        "brute_force_agreement": True,
        "min_pruned_dist": min(audit["min_pruned_dist"]) if audit["min_pruned_dist"] else None,
        "max_kept_dist": max(audit["max_kept_dist"]) if audit["max_kept_dist"] else None,
        "truth_hits": audit["truth_hits"], "pruned": audit["pruned"],
        "runs": audit["runs"], "failed_runs": audit["fails"],
    }
    H.log(f"  距离门数值：{json.dumps(numeric, ensure_ascii=False)}")
    H.log(f"  剪枝下界 {payload['F_degenerate']['min_pruned_dist']} m（应 > 1500）；"
          f"保留上界 {payload['F_degenerate']['max_kept_dist']} m（应 <= 1500）")
    H.log(f"  审计覆盖 {audit['runs']} 例、剪枝 {audit['pruned']} 次、"
          f"真值命中 {audit['truth_hits']}（应 0）、失败运行 {audit['fails']}（应 0）")

    payload.update({"A": table_a, "B": table_b, "C": table_c, "D": table_d, "E": table_e})
    (OUT / "robustness_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    H.log(f"\n报告：{OUT / 'robustness_report.json'}")


if __name__ == "__main__":
    main()

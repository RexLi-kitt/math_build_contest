"""D 模型鲁棒性实验：仓库内自包含的配对回归、对抗场景和剪枝审计。

结果默认写入 outputs/q4/results/d_robustness。案例数指独立源配置数，模型运行数
指同一案例在不同策略臂上的重复执行数；二者在报告中分开统计。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from d_agent import DAgent, point_in_convex_polygon, point_segment_distance
from q4_experiment import (DirectionalSimulator, DirectionalSource, Q4TriangularCoverageAgent,
                           clone_sources, percentile, random_mixed_sources)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "outputs" / "q4" / "results" / "d_robustness"


class NoFilterAgent(DAgent):
    """保留路线和方位目标，关闭距离门。"""

    def within_reach(self, point, state):
        return True


class BAgent(NoFilterAgent):
    discovery_threshold = 10**9


class CAgent(NoFilterAgent):
    discovery_threshold = -1


class BFAgent(DAgent):
    discovery_threshold = 10**9


class CFAgent(DAgent):
    discovery_threshold = -1


class C3FReference(DAgent):
    """D 的直接前代：C 分支有距离门，B 分支没有。"""

    def _coobserve(self, point, primary_channel):
        if self.selected_search_order == "B":
            return Q4TriangularCoverageAgent._coobserve(self, point, primary_channel)
        return super()._coobserve(point, primary_channel)


def polygon_distance(point, polygon):
    if not polygon:
        return None
    if point_in_convex_polygon(point, tuple(polygon)):
        return 0.0
    return min(point_segment_distance(point, a, polygon[(i + 1) % len(polygon)])
               for i, a in enumerate(polygon))


class AuditedDAgent(DAgent):
    """与正式 D 行为一致，并对 D 两个分支的每次剪枝做模拟器真值核验。"""

    def __init__(self, sim, verbose=False):
        super().__init__(sim, verbose)
        self.audited_pruned = 0
        self.pruned_truth_hits = 0
        self.min_pruned_dist = None
        self.max_kept_dist = None

    def truth_success(self, point, channel):
        source = self.sim.sources.get(channel)
        if source is None or source.cleared:
            return False
        if math.dist(point, source.position) > source.receive_radius + 1e-9:
            return False
        if source.beam_direction is None:
            return True
        angle = math.degrees(math.atan2(point[1] - source.position[1],
                                        point[0] - source.position[0])) % 360.0
        delta = (angle - source.beam_direction + 180.0) % 360.0 - 180.0
        return abs(delta) <= 90.0 + 1e-9

    def _coobserve(self, point, primary_channel):
        if self.selected_search_order not in ("B", "C"):
            return Q4TriangularCoverageAgent._coobserve(self, point, primary_channel)
        for channel, state in self.state.items():
            if (channel == primary_channel or state.cleared or state.exhausted
                    or not state.discovered
                    or len(state.observations) >= self.coverage_observation_target):
                continue
            if any(math.dist(point, old) <= 1.0 for old in state.probed_points):
                continue
            polygon = self._snapshot(state).polygon
            distance = polygon_distance(point, polygon)
            if not self.within_reach(point, state):
                self.pruned_observations += 1
                self.audited_pruned += 1
                if self.truth_success(point, channel):
                    self.pruned_truth_hits += 1
                if distance is not None:
                    self.min_pruned_dist = (distance if self.min_pruned_dist is None
                                            else min(self.min_pruned_dist, distance))
                continue
            if distance is not None:
                self.max_kept_dist = (distance if self.max_kept_dist is None
                                      else max(self.max_kept_dist, distance))
            result = self.observe(point, channel)
            if result in ("direction", "near"):
                state.attempts += 1
            self.co_measurements += 1
            self.coobservations += 1


STRATEGIES = {
    "B": BAgent,
    "C": CAgent,
    "BF": BFAgent,
    "CF": CFAgent,
    "D": AuditedDAgent,
    "C3F": C3FReference,
}


class ErrorModeSimulator(DirectionalSimulator):
    def __init__(self, sources, seed, error_mode="uniform_pm1"):
        super().__init__(sources, seed)
        self.error_mode = error_mode
        self.error_index = 0

    def _sign(self, source, point):
        token = f"{self.seed}|{source.channel}|{point[0]:.3f}|{point[1]:.3f}".encode()
        return 1.0 if hashlib.sha256(token).digest()[0] & 1 else -1.0

    def _location_error(self, source, point):
        mode = self.error_mode
        if mode == "uniform_pm1":
            return super()._location_error(source, point)
        if mode == "bias_p1":
            return 1.0
        if mode == "bias_m1":
            return -1.0
        if mode == "zero":
            return 0.0
        if mode == "edge_099":
            return 0.99 * self._sign(source, point)
        if mode == "alternate":
            self.error_index += 1
            return 1.0 if self.error_index % 2 else -1.0
        if mode == "out_bias_p11":
            return 1.1
        if mode == "out_uniform_15":
            return 1.5 * super()._location_error(source, point)
        raise ValueError(f"未知误差模式：{mode}")


def scenario_normal(rng, count):
    return random_mixed_sources(rng, count, 0.5)


def scenario_boundary(rng, count, outward, case_index=0):
    sources = random_mixed_sources(rng, count, 0.75)
    for source in sources:
        angle = rng.random() * 2.0 * math.pi
        radius = 1800.0 if outward and case_index % 2 == 0 else rng.uniform(1700.0, 1800.0)
        source.position = radius * math.cos(angle), radius * math.sin(angle)
        source.receive_radius = 1000.0
        if outward and source.beam_direction is not None:
            source.beam_direction = math.degrees(angle) % 360.0
    return sources


def scenario_mixed(rng, rho):
    sources = random_mixed_sources(rng, None, 0.5)
    order = list(range(len(sources)))
    rng.shuffle(order)
    far_count = min(len(sources), max(0, round(len(sources) * rho)))
    for index in order[:far_count]:
        source = sources[index]
        angle = rng.random() * 2.0 * math.pi
        radius = rng.uniform(1700.0, 1800.0)
        source.position = radius * math.cos(angle), radius * math.sin(angle)
        source.receive_radius = 1000.0
        if source.beam_direction is not None:
            source.beam_direction = math.degrees(angle) % 360.0
    return sources


def scenario_structure(rng, name):
    sources = random_mixed_sources(rng, 16, 0.5)
    if name == "rim_outward":
        for source in sources:
            angle = rng.random() * 2 * math.pi
            source.position = 1800.0 * math.cos(angle), 1800.0 * math.sin(angle)
            source.receive_radius = 1000.0
            if source.beam_direction is not None:
                source.beam_direction = math.degrees(angle) % 360.0
    elif name == "core":
        for source in sources:
            angle, radius = rng.random() * 2 * math.pi, rng.uniform(0.0, 500.0)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
    elif name == "one_quadrant":
        for source in sources:
            angle, radius = rng.uniform(0, math.pi / 2), rng.uniform(0, 1800)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
    elif name == "narrow_20deg":
        base = rng.random() * 2 * math.pi
        for source in sources:
            angle, radius = base + rng.uniform(-math.pi / 18, math.pi / 18), rng.uniform(400, 1800)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
    elif name == "blind_gap":
        for source in sources:
            angle, radius = math.radians(180 + rng.uniform(-7, 7)), rng.uniform(0, 1800)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
    elif name == "one_center_visible_rest_far":
        near = sources[0]
        near.position = rng.uniform(-120, 120), rng.uniform(-120, 120)
        near.receive_radius = 1500.0
        near.beam_direction = None  # 明确保证原点可见
        for source in sources[1:]:
            angle, radius = rng.random() * 2 * math.pi, rng.uniform(1700, 1800)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
            source.receive_radius = 1000.0
            if source.beam_direction is not None:
                source.beam_direction = math.degrees(angle) % 360.0
    elif name == "mirror_pair":
        for index, source in enumerate(sources):
            angle, radius = math.radians(30 + 45 * (index % 2)), rng.uniform(900, 1400)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
            if source.beam_direction is not None:
                source.beam_direction = math.degrees(angle) % 360.0
    elif name in ("min_radius_outward", "min_radius_inward"):
        for source in sources:
            angle, radius = rng.random() * 2 * math.pi, rng.uniform(1700, 1800)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
            source.receive_radius = 1000.0
            if source.beam_direction is not None:
                source.beam_direction = math.degrees(
                    angle if name.endswith("outward") else angle + math.pi) % 360.0
    else:
        raise ValueError(name)
    return sources


def scenario_halfplane(rng, offset):
    sources = scenario_boundary(rng, 16, True)
    source = sources[0]
    angle, radius = rng.random() * 2 * math.pi, 900.0
    source.position = radius * math.cos(angle), radius * math.sin(angle)
    source.receive_radius = 1500.0
    inward = math.degrees(angle + math.pi) % 360.0
    source.beam_direction = (inward + offset) % 360.0
    return sources


def action_metrics(sim, search_end):
    previous = (0.0, 0.0)
    values = {"movement": 0.0, "search_movement": 0.0, "post_movement": 0.0,
              "detection": 0.0, "switching": 0.0, "clearing": 0.0}
    channel = 1
    for action in sim.actions:
        if action.position is not None:
            move = math.dist(previous, action.position) / 5.0
            values["movement"] += move
            values["search_movement" if action.virtual_time_s <= search_end + 1e-6
                   else "post_movement"] += move
            previous = action.position
        if action.kind == "measure":
            values["detection"] += 5.0
            if action.channel != channel:
                values["switching"] += 1.0
            channel = action.channel
        elif action.kind == "clear":
            values["clearing"] += 5.0 if action.result == "success" else 3.0
    return values


def run_one(item):
    label, case, sources, seed, strategy, error_mode = item
    sim = ErrorModeSimulator(clone_sources(sources), seed * 100000 + case, error_mode)
    agent = STRATEGIES[strategy](sim)
    result = agent.run()
    search_end = getattr(agent, "search_end_time_s", sim.time_s)
    return {
        "label": label, "case": case, "strategy": strategy,
        "source_count": len(sources), **result,
        "all_cleared": int(result["cleared_channels"] == len(sources)),
        "origin_discoveries": getattr(agent, "origin_discoveries", None),
        "selected_route": getattr(agent, "selected_search_order", None),
        "pruned_observations": getattr(agent, "pruned_observations", 0),
        "audited_pruned": getattr(agent, "audited_pruned", 0),
        "pruned_truth_hits": getattr(agent, "pruned_truth_hits", 0),
        "min_pruned_dist": getattr(agent, "min_pruned_dist", None),
        "max_kept_dist": getattr(agent, "max_kept_dist", None),
        **action_metrics(sim, search_end),
    }


def evaluate(label, cases, seed, arms, error_mode, jobs):
    work = [(label, index, sources, seed, arm, error_mode)
            for index, sources in enumerate(cases, 1) for arm in arms]
    if jobs <= 1:
        return [run_one(item) for item in work]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(run_one, work))


def values(rows, strategy):
    return {row["case"]: row["total_virtual_time_s"] / row["source_count"]
            for row in rows if row["strategy"] == strategy}


def summary(rows, strategy):
    group = [row for row in rows if row["strategy"] == strategy]
    per_source = [row["total_virtual_time_s"] / row["source_count"] for row in group]
    return {
        "cases": len(group), "all_clear": sum(row["all_cleared"] for row in group),
        "mean_s_per_source": statistics.mean(per_source),
        "p95_s_per_source": percentile(per_source, 0.95),
        "cvar90_s_per_source": statistics.mean(sorted(per_source)[-max(1, round(.1 * len(group))):]),
    }


def paired(rows, left, right):
    a, b = values(rows, left), values(rows, right)
    keys = sorted(set(a) & set(b))
    diff = [a[k] - b[k] for k in keys]
    mean = statistics.mean(diff)
    half = 1.96 * statistics.stdev(diff) / math.sqrt(len(diff)) if len(diff) > 1 else 0.0
    return {"mean": mean, "ci95": [mean - half, mean + half],
            "win_rate": sum(x < 0 for x in diff) / len(diff)}


def compact(rows, arms):
    return {arm: summary(rows, arm) for arm in arms}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", type=int, default=25)
    parser.add_argument("--b", type=int, default=30)
    parser.add_argument("--c", type=int, default=25)
    parser.add_argument("--e", type=int, default=25)
    parser.add_argument("--jobs", type=int, default=min(12, os.cpu_count() or 1))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"protocol": {"a": args.a, "b": args.b, "c": args.c, "e": args.e}}
    all_rows, independent_cases = [], 0

    report["A"] = {}
    for count in range(10, 17):
        for kind_index, kind in enumerate(("normal", "boundary_random", "boundary_outward")):
            seed = 20270901 + count * 10 + kind_index
            rng = random.Random(seed)
            cases = [(scenario_normal(rng, count) if kind == "normal"
                      else scenario_boundary(rng, count, kind == "boundary_outward", i))
                     for i in range(args.a)]
            label, arms = f"A_{kind}_n{count}", ["B", "C", "BF", "CF", "D", "C3F"]
            rows = evaluate(label, cases, seed, arms, "uniform_pm1", args.jobs)
            all_rows += rows; independent_cases += len(cases)
            report["A"][label] = {"arms": compact(rows, arms),
                                   "D_minus_C3F": paired(rows, "D", "C3F")}
            print(label, report["A"][label]["arms"]["D"]["mean_s_per_source"], flush=True)

    report["B"] = {}
    mixed_rows = []
    rhos = (0, .1, .2, .25, .3, .35, .4, .45, .5, .6, .75, 1)
    for rho in rhos:
        seed = 20270601 + round(100 * rho); rng = random.Random(seed)
        cases = [scenario_mixed(rng, rho) for _ in range(args.b)]
        label, arms = f"B_rho{round(100*rho):03d}", ["B", "C", "BF", "CF", "D"]
        rows = evaluate(label, cases, seed, arms, "uniform_pm1", args.jobs)
        all_rows += rows; mixed_rows += rows; independent_cases += len(cases)
        b, c, bf, cf, d = (values(rows, arm) for arm in arms)
        keys = sorted(d); g0 = [abs(b[k]-c[k]) for k in keys]; gf = [abs(bf[k]-cf[k]) for k in keys]
        regret = [d[k] - min(bf[k], cf[k]) for k in keys]
        report["B"][label] = {
            "rho": rho, "arms": compact(rows, arms),
            "eta": 1 - statistics.mean(gf) / statistics.mean(g0),
            "regret_mean": statistics.mean(regret), "regret_p95": percentile(regret, .95),
            "regret_max": max(regret),
        }
        print(label, report["B"][label]["regret_mean"], flush=True)

    report["B_strata"] = {}
    mixed_by = {arm: values(mixed_rows, arm) for arm in ("BF", "CF", "D")}
    # 不同 rho 的 case 编号会重复，所以分层直接按 (label, case) 建键。
    keyed = {(row["label"], row["case"], row["strategy"]): row for row in mixed_rows}
    d_keys = [(row["label"], row["case"]) for row in mixed_rows if row["strategy"] == "D"]
    for stratum, predicate in (("n0=0", lambda n: n == 0),
                               ("n0=1", lambda n: n == 1),
                               ("n0>=2", lambda n: n >= 2)):
        selected = [key for key in d_keys
                    if predicate(keyed[(key[0], key[1], "D")]["origin_discoveries"])]
        regrets, gaps, best_b = [], [], 0
        for label, case in selected:
            bf = keyed[(label, case, "BF")]["total_virtual_time_s"] / keyed[(label, case, "BF")]["source_count"]
            cf = keyed[(label, case, "CF")]["total_virtual_time_s"] / keyed[(label, case, "CF")]["source_count"]
            d = keyed[(label, case, "D")]["total_virtual_time_s"] / keyed[(label, case, "D")]["source_count"]
            gaps.append(bf - cf); regrets.append(d - min(bf, cf)); best_b += bf < cf
        report["B_strata"][stratum] = {
            "cases": len(selected), "mean_BF_minus_CF": statistics.mean(gaps),
            "best_is_B_rate": best_b / len(selected),
            "regret_mean": statistics.mean(regrets), "regret_p95": percentile(regrets, .95),
            "regret_max": max(regrets),
        }

    report["C"] = {}
    structures = ("rim_outward", "core", "one_quadrant", "narrow_20deg", "blind_gap",
                  "one_center_visible_rest_far", "mirror_pair", "min_radius_outward",
                  "min_radius_inward")
    for index, name in enumerate(structures):
        seed = 20270701 + index; rng = random.Random(seed)
        cases = [scenario_structure(rng, name) for _ in range(args.c)]
        label, arms = f"C_{name}", ["BF", "CF", "D"]
        rows = evaluate(label, cases, seed, arms, "uniform_pm1", args.jobs)
        all_rows += rows; independent_cases += len(cases)
        bf, cf, d = (values(rows, arm) for arm in arms); keys = sorted(d)
        regret = [d[k] - min(bf[k], cf[k]) for k in keys]
        report["C"][label] = {"arms": compact(rows, arms),
                               "regret_mean": statistics.mean(regret), "regret_max": max(regret)}
        print(label, report["C"][label]["regret_mean"], flush=True)

    report["D_halfplane"] = {}
    for offset in (89.9, 90.0, 90.1):
        seed = 20270801 + round(offset * 10); rng = random.Random(seed)
        cases = [scenario_halfplane(rng, offset) for _ in range(args.c)]
        label, arms = f"D_halfplane_{offset}", ["BF", "CF", "D"]
        rows = evaluate(label, cases, seed, arms, "uniform_pm1", args.jobs)
        all_rows += rows; independent_cases += len(cases)
        report["D_halfplane"][label] = compact(rows, arms)
        d_group = [row for row in rows if row["strategy"] == "D"]
        report["D_halfplane"][label]["D_pick_B_rate"] = statistics.mean(
            row["selected_route"] == "B" for row in d_group)
        print(label, report["D_halfplane"][label]["D"]["mean_s_per_source"], flush=True)

    report["E_error"] = {}
    modes = ("uniform_pm1", "bias_p1", "bias_m1", "alternate", "edge_099", "zero",
             "out_bias_p11", "out_uniform_15")
    error_seed = 20271101
    error_rng = random.Random(error_seed)
    error_cases = [scenario_normal(error_rng, 16) for _ in range(args.e)]
    independent_cases += len(error_cases)
    for index, mode in enumerate(modes):
        seed = error_seed
        cases = error_cases
        label, arms = f"E_{mode}", ["D", "C3F"]
        rows = evaluate(label, cases, seed, arms, mode, args.jobs)
        all_rows += rows
        report["E_error"][label] = {"scope": "in_spec" if mode not in
                                    ("out_bias_p11", "out_uniform_15") else "out_of_spec",
                                    "arms": compact(rows, arms),
                                    "D_minus_C3F": paired(rows, "D", "C3F")}
        print(label, report["E_error"][label]["arms"]["D"]["mean_s_per_source"], flush=True)

    audited = [row for row in all_rows if row["strategy"] == "D"]
    pruned_dist = [row["min_pruned_dist"] for row in audited if row["min_pruned_dist"] is not None]
    kept_dist = [row["max_kept_dist"] for row in audited if row["max_kept_dist"] is not None]
    numeric = {}
    for target in (1499.0, 1499.9, 1500.0, 1500.1, 1501.0):
        polygon = ((target, -1000.0), (target + 2000.0, -1000.0),
                   (target + 2000.0, 1000.0), (target, 1000.0))
        distance = polygon_distance((0.0, 0.0), polygon)
        numeric[str(target)] = {"distance": distance, "kept": distance <= 1500.0}
    numeric["inside"] = {"distance": polygon_distance((0, 0),
                              ((-2000, -2000), (2000, -2000), (2000, 2000), (-2000, 2000))),
                         "kept": True}
    report["F_distance"] = numeric
    in_spec_rows = [row for row in all_rows if not row["label"].startswith(
        ("E_out_bias_p11", "E_out_uniform_15"))]
    out_spec_rows = [row for row in all_rows if row not in in_spec_rows]
    report["audit"] = {
        "independent_source_cases": independent_cases,
        "model_runs": len(all_rows),
        "all_cleared_runs": sum(row["all_cleared"] for row in all_rows),
        "in_spec_model_runs": len(in_spec_rows),
        "in_spec_all_cleared_runs": sum(row["all_cleared"] for row in in_spec_rows),
        "out_of_spec_model_runs": len(out_spec_rows),
        "out_of_spec_all_cleared_runs": sum(row["all_cleared"] for row in out_spec_rows),
        "d_runs": len(audited),
        "d_audited_pruned": sum(row["audited_pruned"] for row in audited),
        "d_pruned_truth_hits": sum(row["pruned_truth_hits"] for row in audited),
        "min_d_pruned_distance_m": min(pruned_dist) if pruned_dist else None,
        "max_d_kept_distance_m": max(kept_dist) if kept_dist else None,
    }

    with (args.output / "cases.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_rows[0]))
        writer.writeheader(); writer.writerows(all_rows)
    (args.output / "robustness_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["audit"], ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

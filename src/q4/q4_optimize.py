"""问题4参数筛选：在清除率约束下最小化平均每源时间。"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from q4_experiment import (DirectionalSimulator, Q3DirectAgent,
                           Q4TriangularCoverageAgent, clone_sources,
                           percentile, random_mixed_sources)
from q4_routes import Route31Agent, ClippedRouteAgent, ShiftedAgent, ShiftB, ShiftC, ShiftD, ShiftGreedy
from q4_routes import ShiftBGreedy, ShiftBRolling
from q4_better import Grid26A, Grid26B, Grid26C, Insert28, Insert26, ClearEarly28

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "outputs" / "q4" / "results" / "optimization"


class L1000C2(Q4TriangularCoverageAgent):
    lattice_side_m = 1000.0
    coverage_observation_target = 2


class L1000C3(Q4TriangularCoverageAgent):
    lattice_side_m = 1000.0
    coverage_observation_target = 3


class L1000C4(Q4TriangularCoverageAgent):
    lattice_side_m = 1000.0
    coverage_observation_target = 4


class L1000C5(Q4TriangularCoverageAgent):
    lattice_side_m = 1000.0
    coverage_observation_target = 5


class L950C2(Q4TriangularCoverageAgent):
    lattice_side_m = 950.0
    coverage_observation_target = 2


class L950C1(Q4TriangularCoverageAgent):
    lattice_side_m = 950.0
    coverage_observation_target = 1


class L1000C1(Q4TriangularCoverageAgent):
    lattice_side_m = 1000.0
    coverage_observation_target = 1


class L1050C1(Q4TriangularCoverageAgent):
    lattice_side_m = 1050.0
    coverage_observation_target = 1


class L1050C2(Q4TriangularCoverageAgent):
    lattice_side_m = 1050.0
    coverage_observation_target = 2


class L1100C1(Q4TriangularCoverageAgent):
    lattice_side_m = 1100.0
    coverage_observation_target = 1


class L1100C2(Q4TriangularCoverageAgent):
    lattice_side_m = 1100.0
    coverage_observation_target = 2


class L1100C3(Q4TriangularCoverageAgent):
    lattice_side_m = 1100.0
    coverage_observation_target = 3


class L1100C4(Q4TriangularCoverageAgent):
    lattice_side_m = 1100.0
    coverage_observation_target = 4


class L1200C1(Q4TriangularCoverageAgent):
    lattice_side_m = 1200.0
    coverage_observation_target = 1


class L1200C2(Q4TriangularCoverageAgent):
    lattice_side_m = 1200.0
    coverage_observation_target = 2


class L950C3(Q4TriangularCoverageAgent):
    lattice_side_m = 950.0
    coverage_observation_target = 3


class L950C4(Q4TriangularCoverageAgent):
    lattice_side_m = 950.0
    coverage_observation_target = 4


class L900C3(Q4TriangularCoverageAgent):
    lattice_side_m = 900.0
    coverage_observation_target = 3


class L900C5(Q4TriangularCoverageAgent):
    lattice_side_m = 900.0
    coverage_observation_target = 5


STRATEGIES = {
    "Grid26A": Grid26A,
    "Grid26B": Grid26B,
    "Grid26C": Grid26C,
    "Insert28": Insert28,
    "Insert26": Insert26,
    "ClearEarly28": ClearEarly28,
    "ShiftBGreedy": ShiftBGreedy,
    "ShiftBRolling": ShiftBRolling,
    "ShiftA": ShiftedAgent,
    "ShiftB": ShiftB,
    "ShiftC": ShiftC,
    "ShiftD": ShiftD,
    "ShiftGreedy": ShiftGreedy,
    "Route31": Route31Agent,
    "ClippedRoute": ClippedRouteAgent,
    "Q3_direct": Q3DirectAgent,
    "L950_C1": L950C1,
    "L1000_C2": L1000C2,
    "L1000_C1": L1000C1,
    "L1000_C3": L1000C3,
    "L1000_C4": L1000C4,
    "L1000_C5": L1000C5,
    "L950_C2": L950C2,
    "L950_C3": L950C3,
    "L950_C4": L950C4,
    "L900_C3": L900C3,
    "L900_C5": L900C5,
    "L1050_C1": L1050C1,
    "L1050_C2": L1050C2,
    "L1100_C1": L1100C1,
    "L1100_C2": L1100C2,
    "L1100_C3": L1100C3,
    "L1100_C4": L1100C4,
    "L1200_C1": L1200C1,
    "L1200_C2": L1200C2,
}


def run_case(case_index, sources, seed, name, agent_class):
    sim = DirectionalSimulator(clone_sources(sources), seed * 100000 + case_index)
    started = time.perf_counter()
    agent = agent_class(sim)
    result = agent.run()
    search_end_s = getattr(agent, "search_end_time_s", float("nan"))
    movement_s = 0.0
    search_movement_s = 0.0
    post_search_movement_s = 0.0
    detection_s = 0.0
    switching_s = 0.0
    clearing_s = 0.0
    failed_clear_actions = 0
    previous = (0.0, 0.0)
    current_channel = 1
    for action in sim.actions:
        if action.position is not None:
            move_s = math.dist(previous, action.position) / 5.0
            movement_s += move_s
            if action.virtual_time_s <= search_end_s + 1e-6:
                search_movement_s += move_s
            else:
                post_search_movement_s += move_s
            previous = action.position
        if action.kind == "measure":
            detection_s += 5.0
            if action.channel != current_channel:
                switching_s += 1.0
            current_channel = action.channel
        elif action.kind == "clear":
            if action.result == "success":
                clearing_s += 5.0
            else:
                clearing_s += 3.0
                failed_clear_actions += 1
    return {
        "case": case_index,
        "strategy": name,
        "source_count": len(sources),
        **result,
        "all_cleared": int(result["cleared_channels"] == len(sources)),
        "search_sites": len(agent.search_points),
        "search_end_time_s": search_end_s,
        "movement_time_s": movement_s,
        "search_movement_time_s": search_movement_s,
        "post_search_movement_time_s": post_search_movement_s,
        "detection_time_s": detection_s,
        "switching_time_s": switching_s,
        "clearing_time_s": clearing_s,
        "failed_clear_actions": failed_clear_actions,
        "wall_time_s": time.perf_counter() - started,
    }


def _run_work(item):
    """供Windows多进程安全调用的顶层包装函数。"""
    return run_case(*item)


def main():
    parser = argparse.ArgumentParser(description="问题4成功率约束参数筛选")
    parser.add_argument("--cases", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260913)
    parser.add_argument("--sources", type=int, choices=range(10, 17))
    parser.add_argument("--directional-fraction", type=float, default=0.5)
    parser.add_argument("--min-success", type=float, default=1.0)
    parser.add_argument("--strategies", help="逗号分隔；默认全部")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1),
                        help="并行进程数；默认最多使用8个CPU核心")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    selected = STRATEGIES
    if args.strategies:
        names = [name.strip() for name in args.strategies.split(",") if name.strip()]
        selected = {name: STRATEGIES[name] for name in names}

    rng = random.Random(args.seed)
    cases = [random_mixed_sources(rng, args.sources, args.directional_fraction)
             for _ in range(args.cases)]
    work = [(index, sources, args.seed, name, agent_class)
            for index, sources in enumerate(cases, 1)
            for name, agent_class in selected.items()]
    rows = []
    started = time.perf_counter()
    progress_step = max(1, len(work) // 20)
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            for done, row in enumerate(pool.map(_run_work, work), 1):
                rows.append(row)
                if done % progress_step == 0 or done == len(work):
                    print(f"run {done:04d}/{len(work)} complete", flush=True)
    else:
        for done, item in enumerate(work, 1):
            rows.append(_run_work(item))
            if done % progress_step == 0 or done == len(work):
                print(f"run {done:04d}/{len(work)} complete", flush=True)
    elapsed = time.perf_counter() - started

    summaries = []
    for name in selected:
        group = [row for row in rows if row["strategy"] == name]
        success = sum(row["all_cleared"] for row in group) / len(group)
        per_source = [row["total_virtual_time_s"] / row["source_count"] for row in group]
        summaries.append({
            "strategy": name,
            "search_sites": group[0]["search_sites"],
            "success_rate": success,
            "feasible": success >= args.min_success,
            "mean_time_per_source_s": statistics.mean(per_source),
            "p95_time_per_source_s": percentile(per_source, 0.95),
            "mean_measure_actions": statistics.mean(row["measure_actions"] for row in group),
            "mean_cleared": statistics.mean(row["cleared_channels"] for row in group),
            "mean_movement_per_source_s": statistics.mean(
                row["movement_time_s"] / row["source_count"] for row in group),
            "mean_search_movement_per_source_s": statistics.mean(
                row["search_movement_time_s"] / row["source_count"] for row in group),
            "mean_post_search_movement_per_source_s": statistics.mean(
                row["post_search_movement_time_s"] / row["source_count"] for row in group),
            "mean_detection_per_source_s": statistics.mean(
                row["detection_time_s"] / row["source_count"] for row in group),
            "mean_switching_per_source_s": statistics.mean(
                row["switching_time_s"] / row["source_count"] for row in group),
            "mean_clearing_per_source_s": statistics.mean(
                row["clearing_time_s"] / row["source_count"] for row in group),
            "mean_failed_clear_actions": statistics.mean(
                row["failed_clear_actions"] for row in group),
            "mean_search_phase_per_source_s": statistics.mean(
                row["search_end_time_s"] / row["source_count"] for row in group),
            "mean_post_search_per_source_s": statistics.mean(
                (row["total_virtual_time_s"] - row["search_end_time_s"])
                / row["source_count"] for row in group),
        })
    summaries.sort(key=lambda item: (not item["feasible"], item["mean_time_per_source_s"]))
    feasible = [item for item in summaries if item["feasible"]]
    best = feasible[0]["strategy"] if feasible else None

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "case_results.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    payload = {"config": vars(args), "elapsed_wall_time_s": elapsed,
               "best_feasible": best, "summaries": summaries}
    (output / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

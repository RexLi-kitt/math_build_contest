"""Run paired A/B/C experiments on identical random cases."""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from baseline_core import OfflineSimulator, Source, random_sources
from strategies import STRATEGIES


def clone_sources(sources: list[Source]) -> list[Source]:
    return [Source(s.channel, s.position, s.receive_radius) for s in sources]


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1)]


def run_case(case_index: int, sources: list[Source], seed: int,
             selected_items: list) -> list[dict]:
    """Run every selected strategy on one case; top-level for process pickling."""
    rows = []
    for name, agent_class in selected_items:
        sim = OfflineSimulator(clone_sources(sources), seed * 100000 + case_index)
        wall_start = time.perf_counter()
        agent = agent_class(sim)
        result = agent.run()
        counts = {"direction": 0, "no_signal": 0, "near": 0, "clear_failed": 0}
        movement_s = 0.0
        previous = (0.0, 0.0)
        for action in sim.actions:
            if action.position is not None:
                movement_s += math.dist(previous, action.position) / 5.0
                previous = action.position
            if action.kind == "measure" and action.result in counts:
                counts[action.result] += 1
            if action.kind == "clear" and action.result != "success":
                counts["clear_failed"] += 1
        rows.append({
            "seed": seed, "case": case_index, "strategy": name,
            "source_count": len(sources), **result,
            "all_cleared": int(result["cleared_channels"] == len(sources)),
            "movement_time_s": round(movement_s, 6),
            "active_measurements": sum(st.attempts for st in agent.state.values()),
            "co_measurements": getattr(agent, "co_measurements", 0),
            "coverage_insertions": getattr(agent, "coverage_insertions", 0),
            "search_end_time_s": getattr(agent, "search_end_time_s", float("nan")),
            "no_signal_actions": counts["no_signal"],
            "failed_clear_actions": counts["clear_failed"],
            "decision_wall_time_s": round(time.perf_counter() - wall_start, 6),
        })
    return rows


def _run_work(item: tuple) -> list[dict]:
    """Unpack one work item for ProcessPoolExecutor.map."""
    return run_case(*item)


def main() -> None:
    parser = argparse.ArgumentParser(description="第三问定位与第二检测点策略配对实验")
    parser.add_argument("--cases", type=int, default=30)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--sources", type=int, choices=range(10, 17))
    parser.add_argument("--strategies", help="逗号分隔的策略名；默认运行全部")
    parser.add_argument("--output", default="results/latest")
    parser.add_argument("--jobs", type=int, default=1,
                        help="并行进程数；1 为顺序执行，大样本建议设为 CPU 核数")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    cases = [random_sources(rng, args.sources) for _ in range(args.cases)]
    selected = STRATEGIES
    if args.strategies:
        names = [name.strip() for name in args.strategies.split(",") if name.strip()]
        unknown = [name for name in names if name not in STRATEGIES]
        if unknown:
            raise ValueError(f"未知策略: {unknown}")
        selected = {name: STRATEGIES[name] for name in names}
    selected_items = list(selected.items())
    work = [(case_index, sources, args.seed, selected_items)
            for case_index, sources in enumerate(cases, 1)]
    rows = []
    started = time.perf_counter()
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            for done, case_rows in enumerate(pool.map(_run_work, work), 1):
                rows.extend(case_rows)
                print(f"case {done:04d}/{args.cases} complete", flush=True)
    else:
        for case_index, sources, seed, items in work:
            rows.extend(run_case(case_index, sources, seed, items))
            print(f"case {case_index:04d}/{args.cases} complete", flush=True)
    fields = list(rows[0])
    with (output / "case_results.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    summaries = []
    for name in selected:
        group = [row for row in rows if row["strategy"] == name]
        times = [row["total_virtual_time_s"] for row in group]
        per_source = [row["total_virtual_time_s"] / row["source_count"] for row in group]
        summaries.append({
            "strategy": name,
            "all_cleared_rate": sum(row["all_cleared"] for row in group) / len(group),
            "mean_virtual_time_s": statistics.mean(times),
            "median_virtual_time_s": statistics.median(times),
            "p90_virtual_time_s": percentile(times, .90),
            "p95_virtual_time_s": percentile(times, .95),
            "max_virtual_time_s": max(times),
            "mean_time_per_source_s": statistics.mean(per_source),
            "mean_movement_time_s": statistics.mean(row["movement_time_s"] for row in group),
            "mean_measure_actions": statistics.mean(row["measure_actions"] for row in group),
            "mean_active_measurements": statistics.mean(row["active_measurements"] for row in group),
            "mean_co_measurements": statistics.mean(row["co_measurements"] for row in group),
            "mean_coverage_insertions": statistics.mean(row["coverage_insertions"] for row in group),
            "mean_search_end_time_s": (statistics.mean(
                row["search_end_time_s"] for row in group
                if math.isfinite(row["search_end_time_s"]))
                if any(math.isfinite(row["search_end_time_s"]) for row in group) else None),
            "mean_failed_clear_actions": statistics.mean(row["failed_clear_actions"] for row in group),
            "wall_time_s": sum(row["decision_wall_time_s"] for row in group),
        })
    (output / "summary.json").write_text(json.dumps({
        "config": vars(args), "elapsed_wall_time_s": time.perf_counter() - started,
        "summaries": summaries,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

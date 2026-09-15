"""第三步：拆解 C 在压力场景下多出的时间由哪些动作造成。

输出动作级画像：每个停靠点的测量次数、无信号占比、搜索/搜索后阶段的移动与
清除动作，用来判断该改分类门控还是改几何与定位。
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402

from q4_experiment import DirectionalSimulator, clone_sources  # noqa: E402

OUT = H.SANDBOX_OUT / "step3_profile"
NAMES = ["B", "C"]


def profile_case(item):
    case_index, sources, seed, name = item
    sim = DirectionalSimulator(clone_sources(sources), seed * 100000 + case_index)
    agent = H.strategy_class(name)(sim)
    started = time.perf_counter()
    result = agent.run()
    search_end = getattr(agent, "search_end_time_s", float("nan"))
    counters = Counter()
    stations_search, stations_post = set(), set()
    distance_m = distance_post_m = 0.0
    previous = (0.0, 0.0)
    for action in sim.actions:
        in_search = action.virtual_time_s <= search_end + 1e-6
        if action.position is not None:
            step = math.dist(previous, action.position)
            distance_m += step
            if not in_search:
                distance_post_m += step
            (stations_search if in_search else stations_post).add(
                (round(action.position[0], 3), round(action.position[1], 3)))
            previous = action.position
        phase = "search" if in_search else "post"
        if action.kind == "measure":
            counters[f"measure_{phase}"] += 1
            counters[f"measure_{phase}_{action.result}"] += 1
        elif action.kind == "clear":
            counters[f"clear_{phase}"] += 1
            counters[f"clear_{phase}_{action.result}"] += 1
    return {
        "case": case_index,
        "strategy": name,
        "source_count": len(sources),
        "cleared_channels": result["cleared_channels"],
        "all_cleared": int(result["cleared_channels"] == len(sources)),
        "total_virtual_time_s": result["total_virtual_time_s"],
        "search_end_time_s": search_end,
        "measure_total": counters["measure_search"] + counters["measure_post"],
        "measure_search": counters["measure_search"],
        "measure_post": counters["measure_post"],
        "measure_search_no_signal": counters["measure_search_no_signal"],
        "measure_post_no_signal": counters["measure_post_no_signal"],
        "measure_post_direction": counters["measure_post_direction"],
        "clear_total": counters["clear_search"] + counters["clear_post"],
        "clear_post_success": counters["clear_post_success"],
        "clear_post_fail": counters["clear_post_fail"],
        "stations_search": len(stations_search),
        "stations_post": len(stations_post),
        "distance_m": distance_m,
        "distance_post_m": distance_post_m,
        "wall_time_s": time.perf_counter() - started,
    }


def _worker(item):
    return profile_case(item)


def evaluate(label, cases, seed, names, jobs):
    work = [(index, sources, seed, name)
            for index, sources in enumerate(cases, 1) for name in names]
    rows = []
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for done, row in enumerate(pool.map(_worker, work), 1):
            rows.append(row)
            if done % max(1, len(work) // 10) == 0 or done == len(work):
                print(f"  {label}: {done}/{len(work)}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / f"{label}_cases.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    keys = [key for key in rows[0] if key not in ("case", "strategy", "source_count")]
    table = {}
    for name in names:
        group = [row for row in rows if row["strategy"] == name]
        table[name] = {
            "cases": len(group),
            "all_clear": sum(row["all_cleared"] for row in group),
        }
        for key in keys:
            if key == "all_cleared":
                continue
            if key.startswith("clear_") or key in ("stations_search", "stations_post",
                                                   "measure_total"):
                table[name][key] = statistics.mean(row[key] for row in group)
            else:
                table[name][key] = statistics.mean(
                    row[key] / row["source_count"] for row in group)
    return rows, table


def main() -> None:
    scenarios = [
        ("boundary_outward", H.boundary_cases(200, 20261024, True), 20261024),
        ("mixed", H.mixed_cases(200, 20261025), 20261025),
    ]
    payload = {}
    for label, cases, seed in scenarios:
        rows, table = evaluate(label, cases, seed, NAMES, 16)
        payload[label] = table
        print(f"\n=== {label}：每源时间构成（秒/源） ===")
        metrics = [
            ("total_virtual_time_s", "总时间"),
            ("search_end_time_s", "搜索阶段结束时刻"),
            ("distance_m", "总移动距离(m)"),
            ("distance_post_m", "搜索后移动距离(m)"),
            ("measure_search", "搜索期测量次数"),
            ("measure_post", "搜索后测量次数"),
            ("measure_search_no_signal", "搜索期无信号次数"),
            ("measure_post_no_signal", "搜索后无信号次数"),
            ("measure_post_direction", "搜索后有效示向次数"),
            ("clear_total", "清除动作次数"),
            ("clear_post_fail", "搜索后清除失败次数"),
            ("stations_search", "搜索停靠点数"),
            ("stations_post", "搜索后测量点数"),
        ]
        print(f"{'指标':<24}{'B':>12}{'C':>12}{'差(C-B)':>12}")
        for key, title in metrics:
            b, c = table["B"][key], table["C"][key]
            print(f"{title:<24}{b:>12.2f}{c:>12.2f}{c - b:>+12.2f}")
    (OUT / "profile.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n画像已写入 {OUT / 'profile.json'}")


if __name__ == "__main__":
    main()

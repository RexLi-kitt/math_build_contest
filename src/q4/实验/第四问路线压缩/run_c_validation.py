"""C 模型验证: 正常500(seed 20260925, 新种子) + 压力200(seed 20260924)。

对照: B+ (OrderAreaAgent, 现行出货) / C (AggOrderAgent, 激进设计+覆盖顺序)。
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

EXP = r"C:\Users\李\Desktop\第四问定向源实验"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, EXP)
sys.path.insert(0, str(HERE))

import q4_optimize  # noqa: E402
from q4_optimize import run_case  # noqa: E402
from q4_experiment import random_mixed_sources  # noqa: E402
from cert_order_agents import OrderAreaAgent  # noqa: E402
from cert_joint_agents import AggOrderAgent  # noqa: E402

STRATS = {
    "Bplus": OrderAreaAgent,
    "C": AggOrderAgent,
}


def summarize(rows, output, note):
    summary = []
    for name in STRATS:
        group = [r for r in rows if r["strategy"] == name]
        per = [r["total_virtual_time_s"] / r["source_count"] for r in group]
        summary.append({
            "strategy": name,
            "cases": len(group),
            "all_clear": sum(r["all_cleared"] for r in group),
            "mean_s_per_source": statistics.mean(per),
            "p95_s_per_source": q4_optimize.percentile(per, 0.95),
            "mean_search_movement_s": statistics.mean(
                r["search_movement_time_s"] / r["source_count"] for r in group),
            "mean_post_search_movement_s": statistics.mean(
                r["post_search_movement_time_s"] / r["source_count"] for r in group),
            "mean_detection_s": statistics.mean(
                r["detection_time_s"] / r["source_count"] for r in group),
            "mean_switching_s": statistics.mean(
                r["switching_time_s"] / r["source_count"] for r in group),
            "mean_measure_actions": statistics.mean(
                r["measure_actions"] for r in group),
        })
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(
        json.dumps({"note": note, "summaries": summary,
                    "failures": [(r["case"], r["strategy"])
                                 for r in rows if not r["all_cleared"]]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n== {note} ==", flush=True)
    for s in summary:
        print(f"{s['strategy']:>6}: {s['all_clear']}/{s['cases']} "
              f"mean={s['mean_s_per_source']:7.2f} p95={s['p95_s_per_source']:7.2f} "
              f"search_mv={s['mean_search_movement_s']:6.1f} "
              f"post_mv={s['mean_post_search_movement_s']:6.1f} "
              f"det={s['mean_detection_s']:6.1f} "
              f"sw={s['mean_switching_s']:5.1f}", flush=True)


def stress_work(item):
    index, sources = item
    return [run_case(index, sources, 20260924, name, cls)
            for name, cls in STRATS.items()]


def main():
    jobs = 16
    seed = 20260925
    rng = random.Random(seed)
    cases = [random_mixed_sources(rng, None, 0.5) for _ in range(500)]
    work = [(index, sources, seed, name, cls)
            for index, sources in enumerate(cases, 1)
            for name, cls in STRATS.items()]
    rows = []
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for done, row in enumerate(pool.map(q4_optimize._run_work, work), 1):
            rows.append(row)
            if done % 250 == 0 or done == len(work):
                print(f"normal {done}/{len(work)}", flush=True)
    summarize(rows, HERE / "results" / "c_holdout500",
              f"C validation: normal 500 cases seed={seed}")

    rng = random.Random(20260924)
    stress = []
    for index in range(200):
        sources = random_mixed_sources(rng, 16, 0.75)
        for source in sources:
            angle = rng.random() * 2 * math.pi
            radius = 1800.0 if index % 2 == 0 else rng.uniform(1700, 1800)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
            source.receive_radius = 1000.0
            if source.beam_direction is not None:
                source.beam_direction = math.degrees(angle) % 360
        stress.append((index + 1, sources))
    rows = []
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for done, group in enumerate(pool.map(stress_work, stress), 1):
            rows.extend(group)
            if done % 25 == 0:
                print(f"stress {done}/200", flush=True)
    summarize(rows, HERE / "results" / "c_stress200",
              "C validation: boundary stress 200 cases seed=20260924")


if __name__ == "__main__":
    main()

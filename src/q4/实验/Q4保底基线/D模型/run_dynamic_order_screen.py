"""Paired screen for B, B+ and D1 dynamic discovery ordering."""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

EXP = Path(r"C:\Users\李\Desktop\第四问定向源实验")
MODELS = Path(r"C:\Users\李\Desktop\Q4保底基线")
HERE = Path(__file__).resolve().parent
for path in (EXP, MODELS / "B模型", MODELS / "B+模型", HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import q4_optimize  # noqa: E402
from q4_experiment import random_mixed_sources  # noqa: E402
from dynamic_order_agent import DynamicDiscoveryOrderAgent  # noqa: E402

# Import the two identically named baseline modules without relying on sys.path
# order. Their agent behaviour differs only through winner_design.json.
import importlib.util


def _load_agent(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CertRouteAgent


BAgent = _load_agent("q4_baseline_b", MODELS / "B模型" / "cert_route_agent.py")
BPlusAgent = _load_agent("q4_baseline_bplus", MODELS / "B+模型" / "cert_route_agent.py")
STRATEGIES = {
    "B": BAgent,
    "Bplus": BPlusAgent,
    "D1": DynamicDiscoveryOrderAgent,
}


def _run(item):
    case_index, sources, seed, name = item
    return q4_optimize.run_case(case_index, sources, seed, name, STRATEGIES[name])


def _summary(rows):
    result = []
    for name in STRATEGIES:
        group = [row for row in rows if row["strategy"] == name]
        values = [row["total_virtual_time_s"] / row["source_count"] for row in group]
        result.append({
            "strategy": name,
            "cases": len(group),
            "all_clear": sum(row["all_cleared"] for row in group),
            "mean_s_per_source": statistics.mean(values),
            "p95_s_per_source": q4_optimize.percentile(values, 0.95),
            "mean_search_movement_s": statistics.mean(
                row["search_movement_time_s"] / row["source_count"] for row in group),
            "mean_post_search_movement_s": statistics.mean(
                row["post_search_movement_time_s"] / row["source_count"] for row in group),
            "mean_detection_s": statistics.mean(
                row["detection_time_s"] / row["source_count"] for row in group),
            "mean_program_time_s": statistics.mean(row["wall_time_s"] for row in group),
        })
    return result


def _paired_comparisons(rows):
    by_strategy = {
        name: {row["case"]: row["total_virtual_time_s"] / row["source_count"]
               for row in rows if row["strategy"] == name}
        for name in STRATEGIES
    }
    result = []
    for baseline in ("B", "Bplus"):
        shared = sorted(set(by_strategy[baseline]) & set(by_strategy["D1"]))
        differences = [by_strategy["D1"][case] - by_strategy[baseline][case]
                       for case in shared]
        mean = statistics.mean(differences)
        half_width = (1.96 * statistics.stdev(differences) / math.sqrt(len(differences))
                      if len(differences) > 1 else 0.0)
        result.append({
            "comparison": f"D1-{baseline}",
            "cases": len(differences),
            "mean_paired_difference_s_per_source": mean,
            "normal_approx_95ci": [mean - half_width, mean + half_width],
            "d1_win_rate": sum(value < 0 for value in differences) / len(differences),
        })
    return result


def _stress_cases(count, seed):
    rng = random.Random(seed)
    cases = []
    for index in range(count):
        sources = random_mixed_sources(rng, 16, 0.75)
        for source in sources:
            angle = rng.random() * 2.0 * math.pi
            radius = 1800.0 if index % 2 == 0 else rng.uniform(1700.0, 1800.0)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
            source.receive_radius = 1000.0
            if source.beam_direction is not None:
                source.beam_direction = math.degrees(angle) % 360.0
        cases.append(sources)
    return cases


def _evaluate(label, cases, seed, jobs, output):
    work = [(i, sources, seed, name)
            for i, sources in enumerate(cases, 1) for name in STRATEGIES]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        rows = list(pool.map(_run, work))
    summary = _summary(rows)
    paired = _paired_comparisons(rows)
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{label}.json").write_text(json.dumps(
        {"label": label, "seed": seed, "summaries": summary,
         "paired_comparisons": paired,
         "failures": [(row["case"], row["strategy"])
                      for row in rows if not row["all_cleared"]]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    for item in summary:
        print(f"{label:>8} {item['strategy']:>5}: "
              f"clear={item['all_clear']}/{item['cases']} "
              f"mean={item['mean_s_per_source']:.2f} "
              f"p95={item['p95_s_per_source']:.2f} "
              f"program={item['mean_program_time_s']:.3f}s", flush=True)
    for item in paired:
        lo, hi = item["normal_approx_95ci"]
        print(f"{label:>8} {item['comparison']}: "
              f"diff={item['mean_paired_difference_s_per_source']:+.2f} "
              f"95%CI=[{lo:+.2f},{hi:+.2f}]", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--normal", type=int, default=100)
    parser.add_argument("--stress", type=int, default=100)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20261001)
    parser.add_argument("--output", type=Path,
                        default=HERE / "results" / "dynamic_order_screen")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    normal = [random_mixed_sources(rng, None, 0.5) for _ in range(args.normal)]
    _evaluate("normal", normal, args.seed, args.jobs, args.output)
    stress_seed = args.seed + 1
    _evaluate("stress", _stress_cases(args.stress, stress_seed), stress_seed,
              args.jobs, args.output)


if __name__ == "__main__":
    main()

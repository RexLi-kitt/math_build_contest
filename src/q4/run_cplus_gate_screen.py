"""Screen C/B origin-gate thresholds on four paired scenario families."""
from __future__ import annotations

import argparse
import importlib.util
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
ROOT = HERE.parents[1]
OUTPUT_DIR = ROOT / "outputs" / "q4"
for path in (EXP, HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import q4_optimize  # noqa: E402
from q4_experiment import random_mixed_sources  # noqa: E402
from cplus_gate_agent import (CPlusGate0Agent, CPlusGate1Agent,
                              CPlusGate2Agent, CPlusGate3Agent)  # noqa: E402


def _load_agent(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CertRouteAgent


STRATEGIES = {
    "B": _load_agent("cplus_screen_b", MODELS / "B模型" / "cert_route_agent.py"),
    "C": _load_agent("cplus_screen_c", MODELS / "C模型" / "cert_route_agent.py"),
    "T0": CPlusGate0Agent,
    "T1": CPlusGate1Agent,
    "T2": CPlusGate2Agent,
    "T3": CPlusGate3Agent,
}


def _run(item):
    index, sources, seed, name = item
    return q4_optimize.run_case(index, sources, seed, name, STRATEGIES[name])


def _normal_cases(count, seed):
    rng = random.Random(seed)
    return [random_mixed_sources(rng, None, 0.5) for _ in range(count)]


def _min_radius_cases(count, seed):
    cases = _normal_cases(count, seed)
    for sources in cases:
        for source in sources:
            source.receive_radius = 1000.0
    return cases


def _boundary_cases(count, seed, outward):
    rng = random.Random(seed)
    cases = []
    for index in range(count):
        sources = random_mixed_sources(rng, 16, 0.75)
        for source in sources:
            angle = rng.random() * 2.0 * math.pi
            radius = 1800.0 if outward and index % 2 == 0 else rng.uniform(1700.0, 1800.0)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
            source.receive_radius = 1000.0
            if outward and source.beam_direction is not None:
                source.beam_direction = math.degrees(angle) % 360.0
        cases.append(sources)
    return cases


def _summarize(rows):
    summaries = []
    for name in STRATEGIES:
        group = [row for row in rows if row["strategy"] == name]
        per_source = [row["total_virtual_time_s"] / row["source_count"]
                      for row in group]
        summaries.append({
            "strategy": name,
            "cases": len(group),
            "all_clear": sum(row["all_cleared"] for row in group),
            "mean_s_per_source": statistics.mean(per_source),
            "p95_s_per_source": q4_optimize.percentile(per_source, 0.95),
            "mean_search_movement_s": statistics.mean(
                row["search_movement_time_s"] / row["source_count"] for row in group),
            "mean_post_search_movement_s": statistics.mean(
                row["post_search_movement_time_s"] / row["source_count"] for row in group),
            "mean_detection_s": statistics.mean(
                row["detection_time_s"] / row["source_count"] for row in group),
            "mean_program_time_s": statistics.mean(row["wall_time_s"] for row in group),
        })
    return summaries


def _evaluate(label, cases, seed, jobs, output):
    work = [(index, sources, seed, name)
            for index, sources in enumerate(cases, 1) for name in STRATEGIES]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        rows = list(pool.map(_run, work))
    summaries = _summarize(rows)
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "label": label,
        "seed": seed,
        "summaries": summaries,
        "failures": [(row["case"], row["strategy"])
                     for row in rows if not row["all_cleared"]],
    }
    (output / f"{label}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in summaries:
        print(f"{label:>15} {item['strategy']:>2}: "
              f"clear={item['all_clear']}/{item['cases']} "
              f"mean={item['mean_s_per_source']:.2f} "
              f"p95={item['p95_s_per_source']:.2f} "
              f"program={item['mean_program_time_s']:.3f}s", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=100)
    parser.add_argument("--jobs", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20261011)
    parser.add_argument("--output", type=Path,
                        default=OUTPUT_DIR / "results" / "cplus_gate_screen")
    args = parser.parse_args()
    scenario_builders = (
        ("normal", _normal_cases),
        ("min_radius", _min_radius_cases),
        ("boundary_random", lambda count, seed: _boundary_cases(count, seed, False)),
        ("boundary_outward", lambda count, seed: _boundary_cases(count, seed, True)),
    )
    for offset, (label, builder) in enumerate(scenario_builders):
        seed = args.seed + offset
        _evaluate(label, builder(args.cases, seed), seed, args.jobs, args.output)


if __name__ == "__main__":
    main()

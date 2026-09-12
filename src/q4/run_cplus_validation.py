"""Independent paired validation of the selected C+ threshold-0 model."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
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
from cplus_gate_agent import CPlusAgent  # noqa: E402
from run_cplus_gate_screen import (_boundary_cases, _min_radius_cases,
                                   _normal_cases)  # noqa: E402


def _load_agent(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CertRouteAgent


STRATEGIES = {
    "B": _load_agent("cplus_validation_b", MODELS / "B模型" / "cert_route_agent.py"),
    "C": _load_agent("cplus_validation_c", MODELS / "C模型" / "cert_route_agent.py"),
    "Cplus": CPlusAgent,
}


def _run(item):
    index, sources, seed, name = item
    return q4_optimize.run_case(index, sources, seed, name, STRATEGIES[name])


def _evaluate(label, cases, seed, jobs, output):
    work = [(index, sources, seed, name)
            for index, sources in enumerate(cases, 1) for name in STRATEGIES]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        rows = list(pool.map(_run, work))

    summaries = []
    values = {}
    for name in STRATEGIES:
        group = [row for row in rows if row["strategy"] == name]
        values[name] = {row["case"]: row["total_virtual_time_s"] / row["source_count"]
                        for row in group}
        per = list(values[name].values())
        summaries.append({
            "strategy": name,
            "cases": len(group),
            "all_clear": sum(row["all_cleared"] for row in group),
            "mean_s_per_source": statistics.mean(per),
            "p95_s_per_source": q4_optimize.percentile(per, 0.95),
            "mean_program_time_s": statistics.mean(row["wall_time_s"] for row in group),
        })

    comparisons = []
    for baseline in ("B", "C"):
        diff = [values["Cplus"][case] - values[baseline][case]
                for case in sorted(values["Cplus"])]
        mean = statistics.mean(diff)
        half = 1.96 * statistics.stdev(diff) / math.sqrt(len(diff))
        comparisons.append({
            "comparison": f"Cplus-{baseline}",
            "mean_paired_difference_s_per_source": mean,
            "normal_approx_95ci": [mean - half, mean + half],
            "cplus_win_rate": sum(value < 0 for value in diff) / len(diff),
        })

    payload = {
        "label": label,
        "seed": seed,
        "summaries": summaries,
        "paired_comparisons": comparisons,
        "failures": [(row["case"], row["strategy"])
                     for row in rows if not row["all_cleared"]],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{label}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in summaries:
        print(f"{label:>15} {item['strategy']:>5}: "
              f"clear={item['all_clear']}/{item['cases']} "
              f"mean={item['mean_s_per_source']:.2f} "
              f"p95={item['p95_s_per_source']:.2f}", flush=True)
    for item in comparisons:
        lo, hi = item["normal_approx_95ci"]
        print(f"{label:>15} {item['comparison']}: "
              f"diff={item['mean_paired_difference_s_per_source']:+.2f} "
              f"95%CI=[{lo:+.2f},{hi:+.2f}]", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--normal", type=int, default=500)
    parser.add_argument("--risk", type=int, default=200)
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20261021)
    parser.add_argument("--output", type=Path,
                        default=OUTPUT_DIR / "results" / "cplus_holdout")
    args = parser.parse_args()
    scenarios = (
        ("normal", _normal_cases(args.normal, args.seed), args.seed),
        ("min_radius", _min_radius_cases(args.risk, args.seed + 1), args.seed + 1),
        ("boundary_random", _boundary_cases(args.risk, args.seed + 2, False), args.seed + 2),
        ("boundary_outward", _boundary_cases(args.risk, args.seed + 3, True), args.seed + 3),
    )
    for label, cases, seed in scenarios:
        _evaluate(label, cases, seed, args.jobs, args.output)


if __name__ == "__main__":
    main()

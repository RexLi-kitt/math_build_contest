"""I/J/J+ stress-robustness experiment S0-S6 (frozen models, new seeds).

Implements the stress protocol: 7 scenarios x 3 seeds x 200 cases x 3 models,
with hard-constraint metrics, 16 performance metrics, stratified paired
bootstrap and failure-case capture.  Run with the project venv python:

    .venv\\Scripts\\python.exe src\\q3\\B题模型代码汇总\\第三问策略对比\\diagnostics\\stress_robustness.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from baseline_core import OfflineSimulator, Source, dist, random_sources  # noqa: E402
from strategies import (JCompactRingAgent, JPlusAgent,  # noqa: E402
                        RingOptimizedAgent)
from c_to_cplus_metrics import action_metrics, clone_sources, percentile  # noqa: E402

SCENARIOS = ("S0_baseline", "S1_boundary", "S2_min_radius", "S3_systematic_bias",
             "S4_clustered", "S5_max_load", "S6_compound")
SEEDS = (104729, 130363, 155921)
CASES_PER_SEED = 200
BIAS_SPLIT = 100


class BiasedSimulator(OfflineSimulator):
    """Deterministic common bias on every direction measurement (stress S3/S6)."""

    def __init__(self, sources, seed, bias_deg=0.0):
        super().__init__(sources, seed)
        self.bias_deg = bias_deg

    def _location_error(self, source, point):
        if self.bias_deg:
            return self.bias_deg
        return super()._location_error(source, point)


class _SearchMetricMixin:
    def search(self):
        super().search()
        self.metric_search_end_time_s = self.sim.time_s
        self.metric_search_action_count = len(self.sim.actions)
        previous = (0.0, 0.0)
        distance_m = 0.0
        for action in self.sim.actions[:self.metric_search_action_count]:
            if action.position is not None:
                distance_m += dist(previous, action.position)
                previous = action.position
        self.metric_search_movement_time_s = distance_m / 5.0
        self.metric_unfinished_after_search = sum(
            not state.cleared for state in self.state.values() if state.discovered)
        self.metric_not_clear_ready_after_search = sum(
            (not state.cleared and self._clear_decision(state) is None)
            for state in self.state.values() if state.discovered)


class MetricIAgent(_SearchMetricMixin, RingOptimizedAgent):
    pass


class MetricJAgent(_SearchMetricMixin, JCompactRingAgent):
    pass


class MetricJPlusAgent(_SearchMetricMixin, JPlusAgent):
    pass


MODELS = (("I", MetricIAgent), ("J", MetricJAgent), ("J+", MetricJPlusAgent))
PAIRS = (("I", "J"), ("J", "J+"), ("I", "J+"))


def bias_for(scenario, case):
    if scenario in ("S3_systematic_bias", "S6_compound"):
        return 1.0 if case <= BIAS_SPLIT else -1.0
    return 0.0


def _uniform_point(rng):
    radius = 1800.0 * math.sqrt(rng.random())
    angle = rng.uniform(0.0, 2 * math.pi)
    return (radius * math.cos(angle), radius * math.sin(angle))


def make_sources(scenario, rng, case):
    if scenario in ("S0_baseline", "S3_systematic_bias"):
        return random_sources(rng, None)
    if scenario == "S2_min_radius":
        count = rng.randint(10, 16)
        channels = rng.sample(range(1, 21), count)
        return [Source(ch, _uniform_point(rng), 1000.0) for ch in channels]
    if scenario == "S1_boundary":
        count = rng.randint(10, 16)
        channels = rng.sample(range(1, 21), count)
        candidates = []
        for k in range(7):
            base = 360.0 / 7 * (k + 0.5)
            for delta in (0.0, 0.2, -0.2, 1.0, -1.0):
                for radius in (1799.0, 1800.0):
                    angle = math.radians(base + delta)
                    candidates.append((radius * math.cos(angle), radius * math.sin(angle)))
        points = rng.sample(candidates, count)
        return [Source(ch, p, rng.uniform(1000.0, 1500.0))
                for ch, p in zip(channels, points)]
    if scenario == "S4_clustered":
        count = rng.randint(10, 16)
        channels = rng.sample(range(1, 21), count)
        cluster_count = rng.choice((2, 3))
        centers = []
        for _ in range(2000):
            if len(centers) >= cluster_count:
                break
            candidate = _uniform_point(rng)
            candidate = (candidate[0] * 0.92, candidate[1] * 0.92)
            if all(dist(candidate, c) >= 700.0 for c in centers):
                centers.append(candidate)
        sources = []
        for ch in channels:
            point = None
            for _ in range(500):
                center = centers[rng.randrange(len(centers))]
                radius = 150.0 * math.sqrt(rng.random())
                angle = rng.uniform(0.0, 2 * math.pi)
                trial = (center[0] + radius * math.cos(angle),
                         center[1] + radius * math.sin(angle))
                if math.hypot(*trial) <= 1800.0:
                    point = trial
                    break
            if point is None:
                point = _uniform_point(rng)
            sources.append(Source(ch, point, rng.uniform(1000.0, 1500.0)))
        return sources
    if scenario == "S5_max_load":
        return random_sources(rng, 16)
    if scenario == "S6_compound":
        channels = rng.sample(range(1, 21), 16)
        start = rng.randrange(7)
        width = rng.choice((2, 3))
        sectors = [(start + i) % 7 for i in range(width)]
        sources = []
        for ch in channels:
            k = sectors[rng.randrange(width)]
            base = 360.0 / 7 * (k + 0.5) + rng.uniform(-3.0, 3.0)
            radius = rng.uniform(1750.0, 1800.0)
            angle = math.radians(base)
            sources.append(Source(ch, (radius * math.cos(angle), radius * math.sin(angle)), 1000.0))
        return sources
    raise ValueError(f"unknown scenario {scenario}")


def run_case(item):
    scenario, seed, case, sources, bias = item
    rows = []
    n = len(sources)
    true_channels = {s.channel for s in sources}
    for name, klass in MODELS:
        sim = BiasedSimulator(clone_sources(sources), seed * 100000 + case, bias)
        agent = klass(sim)
        anomaly = 0
        error = ""
        started = time.perf_counter()
        try:
            result = agent.run()
        except Exception as exc:  # noqa: BLE001 - captured as a hard metric
            result = None
            anomaly = 1
            error = repr(exc)
        wall = time.perf_counter() - started
        movement, detect_switch, clear_actions, switches, last_discovery = action_metrics(
            sim, true_channels)
        search_end = getattr(agent, "metric_search_end_time_s", float("nan"))
        first_detection, failed_clears, actions = {}, 0, []
        for action in sim.actions:
            if action.kind == "measure" and action.result in ("direction", "near"):
                first_detection.setdefault(action.channel, action.virtual_time_s)
                actions.append({"k": "m", "c": action.channel, "r": action.result,
                                "p": action.position, "t": action.virtual_time_s})
            elif action.kind == "clear":
                if action.result != "success":
                    failed_clears += 1
                actions.append({"k": "c", "c": action.channel, "r": action.result,
                                "p": action.position, "t": action.virtual_time_s})
        if math.isfinite(search_end):
            undiscovered = sorted(
                c for c in true_channels
                if first_detection.get(c, math.inf) > search_end + 0.01)
        else:
            undiscovered = sorted(true_channels)
        never_detected = sorted(c for c in true_channels if c not in first_detection)
        exhausted = sorted(c for c in true_channels
                           if getattr(agent.state[c], "exhausted", False))
        total = result["total_virtual_time_s"] if result else round(sim.time_s, 6)
        all_cleared = int(result is not None
                          and result["cleared_channels"] == n)
        rows.append({
            "scenario": scenario, "seed": seed, "case": case, "model": name,
            "n": n, "bias_deg": bias, "anomaly": anomaly, "error": error,
            "all_cleared": all_cleared,
            "undiscovered_cases": int(bool(undiscovered)),
            "undiscovered_sources": len(undiscovered),
            "coverage_misses": len(never_detected),
            "exhausted_cases": int(bool(exhausted)),
            "exhausted_sources": len(exhausted),
            "failed_clears": failed_clears,
            "total_per_source": total / n,
            "movement_per_source": movement / n,
            "detect_switch_per_source": detect_switch / n,
            "clear_time_per_source": clear_actions / n,
            "last_discovery_per_source": last_discovery / n,
            "search_end_per_source": search_end / n if math.isfinite(search_end) else float("nan"),
            "search_movement_per_source": getattr(
                agent, "metric_search_movement_time_s", float("nan")) / n,
            "not_ready_rate": getattr(
                agent, "metric_not_clear_ready_after_search", 0) / n,
            "active_measurements_per_source": sum(
                state.attempts for state in agent.state.values()) / n,
            "co_measurements_per_source": getattr(agent, "co_measurements", 0) / n,
            "switches_per_source": switches / n,
            "insertions_per_source": getattr(agent, "coverage_insertions", 0) / n,
            "decision_wall_s": wall,
            "decomposition_error_s": abs(total - movement - detect_switch - clear_actions),
            "hard_fail": int(bool(not all_cleared or undiscovered or never_detected
                                  or exhausted or failed_clears or anomaly)),
            "_sources": [(s.channel, s.position, s.receive_radius) for s in sources]
            if (not all_cleared or undiscovered or never_detected or exhausted
                or failed_clears or anomaly) else None,
            "_actions": actions if (not all_cleared or undiscovered or never_detected
                                    or exhausted or failed_clears or anomaly) else None,
        })
    return rows


def percentile_safe(values, q):
    ordered = sorted(v for v in values if not math.isnan(v))
    if not ordered:
        return float("nan")
    return ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)]


BASE_METRICS = ("total_per_source", "movement_per_source", "detect_switch_per_source",
                "clear_time_per_source", "last_discovery_per_source",
                "search_end_per_source", "search_movement_per_source", "not_ready_rate",
                "active_measurements_per_source", "co_measurements_per_source",
                "switches_per_source", "insertions_per_source", "decision_wall_s",
                "decomposition_error_s")


def summarize(group):
    total = [r["total_per_source"] for r in group]
    values = {
        "cases": len(group),
        "all_cleared_rate": statistics.mean(r["all_cleared"] for r in group),
        "undiscovered_cases": sum(r["undiscovered_cases"] for r in group),
        "undiscovered_sources": sum(r["undiscovered_sources"] for r in group),
        "coverage_misses": sum(r["coverage_misses"] for r in group),
        "exhausted_cases": sum(r["exhausted_cases"] for r in group),
        "exhausted_sources": sum(r["exhausted_sources"] for r in group),
        "failed_clears": sum(r["failed_clears"] for r in group),
        "anomalies": sum(r["anomaly"] for r in group),
        "hard_fail_cases": sum(r["hard_fail"] for r in group),
        "mean_per_source": statistics.mean(total),
        "median_per_source": statistics.median(total),
        "p90_per_source": percentile_safe(total, .90),
        "p95_per_source": percentile_safe(total, .95),
        "max_per_source": max(total),
    }
    for metric in BASE_METRICS:
        values[f"mean_{metric}"] = statistics.mean(r[metric] for r in group)
    return values


def bootstrap_ci(values_by_seed, reps=10000, seed=20260912):
    rng = np.random.default_rng(seed)
    arrays = [np.asarray([v for v in values if not math.isnan(v)]) for values in values_by_seed]
    arrays = [a for a in arrays if len(a)]
    means = np.empty(reps)
    for i in range(reps):
        accumulator = 0.0
        for a in arrays:
            idx = rng.integers(0, len(a), len(a))
            accumulator += a[idx].mean()
        means[i] = accumulator / len(arrays)
    return float(means.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def paired_stats(diffs_by_seed):
    diffs = [d for values in diffs_by_seed.values() for d in values]
    mean, low, high = bootstrap_ci(list(diffs_by_seed.values()))
    seed_means = {str(seed): float(np.mean(values)) for seed, values in diffs_by_seed.items()}
    return {
        "n": len(diffs),
        "mean": mean, "median": statistics.median(diffs),
        "ci_low": low, "ci_high": high,
        "right_wins": sum(d > 1e-9 for d in diffs),
        "left_wins": sum(d < -1e-9 for d in diffs),
        "ties": sum(abs(d) <= 1e-9 for d in diffs),
        "seed_means": seed_means,
        "seed_range": max(seed_means.values()) - min(seed_means.values()),
    }


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="I/J/J+ S0-S6 stress robustness")
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--seeds", default=",".join(str(s) for s in SEEDS))
    parser.add_argument("--cases", type=int, default=CASES_PER_SEED)
    parser.add_argument("--jobs", type=int, default=16)
    parser.add_argument("--output", default="results/stress_robustness")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    if args.quick:
        args.cases = min(args.cases, 5)
        args.seeds = "104729"
    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    output = ROOT / args.output
    started = time.time()
    all_rows = []
    manifest_scenarios = {}
    for scenario in scenarios:
        work = []
        for seed in seeds:
            rng = random.Random(seed)
            for case in range(1, args.cases + 1):
                sources = make_sources(scenario, rng, case)
                work.append((scenario, seed, case, sources, bias_for(scenario, case)))
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            batches = list(pool.map(run_case, work))
        rows = [row for batch in batches for row in batch]
        all_rows.extend(rows)
        for seed in seeds:
            seed_rows = [r for r in rows if r["seed"] == seed]
            scenario_dir = output / scenario / f"seed_{seed}"
            scenario_dir.mkdir(parents=True, exist_ok=True)
            fields = [k for k in seed_rows[0] if not k.startswith("_")]
            write_csv(scenario_dir / "case_results.csv", seed_rows, fields)
            (scenario_dir / "summary.json").write_text(json.dumps(
                {name: summarize([r for r in seed_rows if r["model"] == name])
                 for name, _ in MODELS}, ensure_ascii=False, indent=2), encoding="utf-8")
            failures = [{"seed": r["seed"], "case": r["case"], "model": r["model"],
                         "sources": r["_sources"], "actions": (r["_actions"] or [])[:300],
                         "undiscovered_sources": r["undiscovered_sources"],
                         "coverage_misses": r["coverage_misses"],
                         "exhausted_sources": r["exhausted_sources"],
                         "failed_clears": r["failed_clears"], "anomaly": r["anomaly"],
                         "error": r["error"]}
                        for r in seed_rows if r["hard_fail"]]
            (scenario_dir / "failures.json").write_text(
                json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest_scenarios[scenario] = {
            "cases_per_seed": args.cases, "seeds": seeds,
            "description": SCENARIO_NOTES.get(scenario, ""),
        }
        print(f"[{scenario}] done: {len(rows)} rows", flush=True)

    fields = [k for k in all_rows[0] if not k.startswith("_")]
    write_csv(output / "stress_case_results.csv", all_rows, fields)

    summary_rows = []
    summary_json = {}
    for scenario in scenarios:
        summary_json[scenario] = {}
        for name, _ in MODELS:
            per_seed = {}
            for seed in seeds:
                group = [r for r in all_rows
                         if r["scenario"] == scenario and r["model"] == name
                         and r["seed"] == seed]
                per_seed[str(seed)] = summarize(group)
            pooled_group = [r for r in all_rows
                            if r["scenario"] == scenario and r["model"] == name]
            pooled = summarize(pooled_group)
            mean, low, high = bootstrap_ci(
                [[r["total_per_source"] for r in pooled_group if r["seed"] == seed]
                 for seed in seeds])
            pooled.update({"mean_ci_low": low, "mean_ci_high": high, "bootstrap_mean": mean})
            summary_json[scenario][name] = {"per_seed": per_seed, "pooled": pooled}
            for label, item in [("pooled", pooled)] + [(str(s), per_seed[str(s)]) for s in seeds]:
                row = {"scenario": scenario, "model": name, "seed": label}
                row.update(item)
                summary_rows.append(row)
    summary_fields = list(summary_rows[0])
    write_csv(output / "stress_summary.csv", summary_rows, summary_fields)
    (output / "stress_summary.json").write_text(
        json.dumps(summary_json, ensure_ascii=False, indent=2), encoding="utf-8")

    lookup = {(r["scenario"], r["seed"], r["case"], r["model"]): r for r in all_rows}
    paired = {}
    for scenario in scenarios:
        paired[scenario] = {}
        for left, right in PAIRS:
            diffs_by_seed = {}
            for seed in seeds:
                diffs = []
                for case in range(1, args.cases + 1):
                    a = lookup.get((scenario, seed, case, left))
                    b = lookup.get((scenario, seed, case, right))
                    if a and b:
                        diffs.append(a["total_per_source"] - b["total_per_source"])
                diffs_by_seed[seed] = diffs
            paired[scenario][f"{left}->{right}"] = paired_stats(diffs_by_seed)
    (output / "paired_effects.json").write_text(
        json.dumps(paired, ensure_ascii=False, indent=2), encoding="utf-8")
    paired_rows = []
    for scenario in scenarios:
        for pair, item in paired[scenario].items():
            row = {"scenario": scenario, "pair": pair}
            row.update({k: v for k, v in item.items() if k not in ("seed_means",)})
            row["seed_means"] = json.dumps(item["seed_means"])
            paired_rows.append(row)
    write_csv(output / "paired_effects.csv", paired_rows, list(paired_rows[0]))

    failures = []
    for row in all_rows:
        if row["hard_fail"]:
            failures.append({
                "scenario": row["scenario"], "seed": row["seed"], "case": row["case"],
                "model": row["model"],
                "sources": row["_sources"],
                "undiscovered_sources": row["undiscovered_sources"],
                "coverage_misses": row["coverage_misses"],
                "exhausted_sources": row["exhausted_sources"],
                "failed_clears": row["failed_clears"], "anomaly": row["anomaly"],
                "error": row["error"],
                "actions": (row["_actions"] or [])[:300],
            })
    (output / "failure_cases.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "models": {
            "I": {"class": "RingOptimizedAgent", "search_ring_r": 1150.0,
                  "ring_points": 6},
            "J": {"class": "JCompactRingAgent", "search_ring_r": 1000.0,
                  "ring_points": 7},
            "J+": {"class": "JPlusAgent", "search_ring_r": 1000.0,
                   "ring_points": 7, "weights": [0.25, 0.25, 0.25, 0.25],
                   "coverage_extra_measure_budget": 5, "insertion_budget_m": 0.0},
        },
        "seeds": seeds, "cases_per_seed": args.cases, "scenarios": manifest_scenarios,
        "bias_rule": "S3/S6: cases 1-100 +1 deg, cases 101-200 -1 deg, "
                     "all direction measurements share the same bias (no cancellations)",
        "file_hashes": {
            "strategies.py": file_hash(ROOT / "strategies.py"),
            "baseline_core.py": file_hash(ROOT / "baseline_core.py"),
            "feasible_region.py": file_hash(ROOT / "feasible_region.py"),
            "stress_robustness.py": file_hash(Path(__file__)),
        },
        "python_version": sys.version,
        "started": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started)),
        "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_s": round(time.time() - started, 1),
    }
    (output / "experiment_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({s: {m: round(summary_json[s][m]["pooled"]["mean_per_source"], 2)
                          for m, _ in MODELS} for s in scenarios},
                     ensure_ascii=False, indent=2))


SCENARIO_NOTES = {
    "S0_baseline": "standard generator: uniform area, 10-16 sources, base radius/error",
    "S1_boundary": "sources on r=1799/1800 at worst-sector bisectors with 0/+-0.2/+-1 deg jitter",
    "S2_min_radius": "uniform positions, all receive radii fixed at 1000 m",
    "S3_systematic_bias": "uniform positions, common +1/-1 deg bias per case (100/100 split)",
    "S4_clustered": "2-3 clusters (>=700 m apart), sources within 150 m of centers",
    "S5_max_load": "16 sources per case, base distribution",
    "S6_compound": "16 boundary sources in 2-3 adjacent worst sectors, radius 1000 m, common bias",
}


if __name__ == "__main__":
    main()

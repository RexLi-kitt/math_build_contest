"""Paired mechanism backtest for the C+ -> F transition.

The experiment keeps the source set and simulator noise identical within each
case.  Four F variants separate coverage-site co-measurement, dynamic coverage
ordering, and low-detour Q2 insertion.  Source truth is used only after a run
to identify first-discovery time and the final reliability outcome.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from baseline_core import OfflineSimulator, Source
from strategies import CPlusAgent, CoverageIntegratedAgent
from c_to_cplus_metrics import action_metrics, clone_sources, percentile


class _SearchSnapshotMixin:
    def search(self):
        super().search()
        self.metric_search_end_time_s = self.sim.time_s
        self.metric_unfinished_after_search = sum(
            not state.cleared for state in self.state.values() if state.discovered
        )
        self.metric_not_clear_ready_after_search = sum(
            (not state.cleared and self._clear_decision(state) is None)
            for state in self.state.values() if state.discovered
        )


class MetricCPlusAgent(_SearchSnapshotMixin, CPlusAgent):
    pass


class _FixedCoverageOrderMixin:
    """Use the original stored ring order instead of F's adaptive permutation."""

    def _coverage_order(self, unvisited):
        return list(unvisited)


class MetricFFixedNoInsertionAgent(
        _SearchSnapshotMixin, _FixedCoverageOrderMixin, CoverageIntegratedAgent):
    max_coverage_insertions = 0


class MetricFDynamicNoInsertionAgent(_SearchSnapshotMixin, CoverageIntegratedAgent):
    max_coverage_insertions = 0


class MetricFFixedInsertionAgent(
        _SearchSnapshotMixin, _FixedCoverageOrderMixin, CoverageIntegratedAgent):
    pass


class MetricFFullAgent(_SearchSnapshotMixin, CoverageIntegratedAgent):
    pass


MODELS = (
    ("C+", MetricCPlusAgent),
    ("F_fixed_no_insert", MetricFFixedNoInsertionAgent),
    ("F_dynamic_no_insert", MetricFDynamicNoInsertionAgent),
    ("F_fixed_insert", MetricFFixedInsertionAgent),
    ("F", MetricFFullAgent),
)


def run_agent(name, klass, sources, noise_seed, case, seed):
    sim = OfflineSimulator(clone_sources(sources), noise_seed)
    agent = klass(sim)
    result = agent.run()
    n = len(sources)
    movement, detect_switch, clear_actions, switches, last_discovery = action_metrics(
        sim, {item.channel for item in sources}
    )
    decomposition_error = abs(
        result["total_virtual_time_s"] - movement - detect_switch - clear_actions
    )
    return {
        "seed": seed,
        "case": case,
        "model": name,
        "source_count": n,
        "all_cleared": int(result["cleared_channels"] == n),
        "total_time_per_source_s": result["total_virtual_time_s"] / n,
        "movement_time_per_source_s": movement / n,
        "detection_switch_time_per_source_s": detect_switch / n,
        "clear_action_time_per_source_s": clear_actions / n,
        "measure_actions_per_source": result["measure_actions"] / n,
        "channel_switches_per_source": switches / n,
        "last_discovery_time_per_source_s": last_discovery / n,
        "search_end_time_per_source_s": agent.metric_search_end_time_s / n,
        "unfinished_after_search_rate": agent.metric_unfinished_after_search / n,
        "not_clear_ready_after_search_rate": agent.metric_not_clear_ready_after_search / n,
        "active_measurements_per_source": sum(state.attempts for state in agent.state.values()) / n,
        "co_measurements_per_source": getattr(agent, "co_measurements", 0) / n,
        "coverage_insertions_per_source": getattr(agent, "coverage_insertions", 0) / n,
        "decomposition_error_s": decomposition_error,
    }


def run_case(item):
    seed, case, sources = item
    noise_seed = seed * 100000 + case
    return [run_agent(name, klass, sources, noise_seed, case, seed) for name, klass in MODELS]


METRICS = (
    "total_time_per_source_s",
    "movement_time_per_source_s",
    "detection_switch_time_per_source_s",
    "clear_action_time_per_source_s",
    "measure_actions_per_source",
    "channel_switches_per_source",
    "last_discovery_time_per_source_s",
    "search_end_time_per_source_s",
    "unfinished_after_search_rate",
    "not_clear_ready_after_search_rate",
    "active_measurements_per_source",
    "co_measurements_per_source",
    "coverage_insertions_per_source",
)


def summarize(rows):
    summaries = []
    for name, _ in MODELS:
        subset = [row for row in rows if row["model"] == name]
        item = {"model": name, "cases": len(subset)}
        for metric in METRICS:
            values = [row[metric] for row in subset]
            item[f"mean_{metric}"] = statistics.mean(values)
            if metric == "total_time_per_source_s":
                item[f"p95_{metric}"] = percentile(values, .95)
        item["all_cleared_rate"] = statistics.mean(row["all_cleared"] for row in subset)
        summaries.append(item)

    lookup = {(row["seed"], row["case"], row["model"]): row for row in rows}
    pairs = []
    comparisons = (
        ("C+", "F"),
        ("C+", "F_fixed_no_insert"),
        ("F_fixed_no_insert", "F_dynamic_no_insert"),
        ("F_fixed_no_insert", "F_fixed_insert"),
        ("F_dynamic_no_insert", "F"),
        ("F_fixed_insert", "F"),
    )
    cases = sorted({(row["seed"], row["case"]) for row in rows})
    for left, right in comparisons:
        for metric in METRICS:
            differences = [lookup[(seed, case, left)][metric] - lookup[(seed, case, right)][metric]
                           for seed, case in cases]
            pairs.append({
                "left": left,
                "right": right,
                "metric": metric,
                "mean_left_minus_right": statistics.mean(differences),
                "right_better_cases": sum(value > 1e-9 for value in differences),
                "equal_cases": sum(abs(value) <= 1e-9 for value in differences),
                "left_better_cases": sum(value < -1e-9 for value in differences),
            })
    return summaries, pairs


def main():
    parser = argparse.ArgumentParser(description="C+ 到 F 的统一指标与机制消融回测")
    parser.add_argument("--seeds", default="112358,271828,314159")
    parser.add_argument("--cases-per-seed", type=int, default=200)
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--output", default="diagnostics/results/cplus_to_f_metrics_600")
    args = parser.parse_args()
    seeds = [int(value) for value in args.seeds.split(",")]
    work = []
    for seed in seeds:
        rng = random.Random(seed)
        for case in range(1, args.cases_per_seed + 1):
            # Generate in exactly the same order as the C -> C+ experiment.
            from baseline_core import random_sources
            work.append((seed, case, random_sources(rng, None)))
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            batches = list(pool.map(run_case, work))
    else:
        batches = [run_case(item) for item in work]
    rows = [row for batch in batches for row in batch]
    summaries, pairs = summarize(rows)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "case_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    payload = {"config": vars(args), "summaries": summaries, "paired": pairs}
    (output / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

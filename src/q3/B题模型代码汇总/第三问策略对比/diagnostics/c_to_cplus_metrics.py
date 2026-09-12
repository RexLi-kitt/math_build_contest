"""Paired mechanism backtest for the C -> C+ transition.

Production agents do not read source truth.  Truth is used only after the run
to identify the time at which every real source was first detected.
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

from baseline_core import OfflineSimulator, Source, dist, random_sources
from strategies import CPlusAgent, Q2FourMetricAgent


class _SearchSnapshotMixin:
    def search(self):
        super().search()
        self.metric_search_end_time_s = self.sim.time_s
        self.metric_unfinished_after_search = sum(
            not state.cleared for state in self.state.values()
            if state.discovered
        )
        self.metric_not_clear_ready_after_search = sum(
            (not state.cleared and self._clear_decision(state) is None)
            for state in self.state.values() if state.discovered
        )


class MetricCAgent(_SearchSnapshotMixin, Q2FourMetricAgent):
    pass


class MetricCPlusAgent(_SearchSnapshotMixin, CPlusAgent):
    pass


def clone_sources(sources: list[Source]) -> list[Source]:
    return [Source(item.channel, item.position, item.receive_radius) for item in sources]


def action_metrics(sim: OfflineSimulator, true_channels: set[int]):
    previous = (0.0, 0.0)
    movement_s = 0.0
    measure_actions = 0
    switches = 0
    current_channel = 1
    successful_clears = 0
    failed_clears = 0
    first_discovery = {}
    for action in sim.actions:
        if action.position is not None:
            movement_s += dist(previous, action.position) / 5.0
            previous = action.position
        if action.kind == "measure":
            measure_actions += 1
            if action.channel != current_channel:
                switches += 1
            current_channel = action.channel
            if (action.channel in true_channels and action.channel not in first_discovery
                    and action.result in {"direction", "near"}):
                first_discovery[action.channel] = action.virtual_time_s
        elif action.kind == "clear":
            if action.result == "success":
                successful_clears += 1
            else:
                failed_clears += 1
    detection_switch_s = 5.0 * measure_actions + switches
    clear_action_s = 5.0 * successful_clears + 3.0 * failed_clears
    last_discovery_s = max(first_discovery.values()) if len(first_discovery) == len(true_channels) else math.nan
    return movement_s, detection_switch_s, clear_action_s, switches, last_discovery_s


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
        "decomposition_error_s": decomposition_error,
    }


def run_case(item):
    seed, case, sources = item
    noise_seed = seed * 100000 + case
    return [
        run_agent("C", MetricCAgent, sources, noise_seed, case, seed),
        run_agent("C+", MetricCPlusAgent, sources, noise_seed, case, seed),
    ]


METRICS = [
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
]


def percentile(values, probability):
    values = sorted(values)
    return values[math.ceil(probability * len(values)) - 1]


def summarize(rows):
    summaries = []
    for model in ("C", "C+"):
        subset = [row for row in rows if row["model"] == model]
        item = {"model": model, "cases": len(subset)}
        for metric in METRICS:
            values = [row[metric] for row in subset]
            item[f"mean_{metric}"] = statistics.mean(values)
            if metric == "total_time_per_source_s":
                item[f"p95_{metric}"] = percentile(values, .95)
        item["all_cleared_rate"] = statistics.mean(row["all_cleared"] for row in subset)
        summaries.append(item)
    by_case = {}
    for row in rows:
        by_case[(row["seed"], row["case"], row["model"])] = row
    paired = []
    for metric in METRICS:
        differences = []
        for seed, case in sorted({(row["seed"], row["case"]) for row in rows}):
            differences.append(
                by_case[(seed, case, "C")][metric]
                - by_case[(seed, case, "C+")][metric]
            )
        paired.append({
            "metric": metric,
            "mean_C_minus_Cplus": statistics.mean(differences),
            "Cplus_better_cases": sum(value > 0 for value in differences),
            "equal_cases": sum(abs(value) <= 1e-9 for value in differences),
            "C_better_cases": sum(value < 0 for value in differences),
        })
    return summaries, paired


def main():
    parser = argparse.ArgumentParser(description="C 到 C+ 的统一指标回测")
    parser.add_argument("--seeds", default="112358,271828,314159")
    parser.add_argument("--cases-per-seed", type=int, default=200)
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--output", default="diagnostics/results/c_to_cplus_metrics_600")
    args = parser.parse_args()
    seeds = [int(value) for value in args.seeds.split(",")]
    work = []
    for seed in seeds:
        rng = random.Random(seed)
        for case in range(1, args.cases_per_seed + 1):
            work.append((seed, case, random_sources(rng, None)))
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            batches = list(pool.map(run_case, work))
    else:
        batches = [run_case(item) for item in work]
    rows = [row for batch in batches for row in batch]
    summaries, paired = summarize(rows)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "case_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    payload = {"config": vars(args), "summaries": summaries, "paired": paired}
    (output / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Paired seven-metric backtest for I -> J and J -> J+ (compact ring + measurement schedule)."""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from baseline_core import OfflineSimulator, dist, random_sources
from strategies import (AblationRing8Agent, JCompactRingAgent, JPlusAgent,
                        RingOptimizedAgent)
from c_to_cplus_metrics import action_metrics, clone_sources, percentile


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
            not state.cleared for state in self.state.values() if state.discovered
        )
        self.metric_not_clear_ready_after_search = sum(
            (not state.cleared and self._clear_decision(state) is None)
            for state in self.state.values() if state.discovered
        )


class MetricIAgent(_SearchMetricMixin, RingOptimizedAgent):
    pass


class MetricJAgent(_SearchMetricMixin, JCompactRingAgent):
    pass


class MetricJPlusAgent(_SearchMetricMixin, JPlusAgent):
    pass


class MetricRing8Agent(_SearchMetricMixin, AblationRing8Agent):
    pass


MODELS = (
    ("I", MetricIAgent),
    ("J", MetricJAgent),
    ("Jplus", MetricJPlusAgent),
    ("Ring8", MetricRing8Agent),
)

PAIRS = (("I", "J"), ("J", "Jplus"), ("J", "Ring8"))


def run_agent(name, klass, sources, noise_seed, case, seed):
    sim = OfflineSimulator(clone_sources(sources), noise_seed)
    agent = klass(sim)
    result = agent.run()
    n = len(sources)
    movement, detect_switch, clear_actions, switches, last_discovery = action_metrics(
        sim, {source.channel for source in sources}
    )
    return {
        "seed": seed, "case": case, "model": name, "source_count": n,
        "all_cleared": int(result["cleared_channels"] == n),
        "total_time_per_source_s": result["total_virtual_time_s"] / n,
        "movement_time_per_source_s": movement / n,
        "detection_switch_time_per_source_s": detect_switch / n,
        "clear_action_time_per_source_s": clear_actions / n,
        "measure_actions_per_source": result["measure_actions"] / n,
        "channel_switches_per_source": switches / n,
        "last_discovery_time_per_source_s": last_discovery / n,
        "search_end_time_per_source_s": agent.metric_search_end_time_s / n,
        "search_movement_time_per_source_s": agent.metric_search_movement_time_s / n,
        "unfinished_after_search_rate": agent.metric_unfinished_after_search / n,
        "not_clear_ready_after_search_rate": agent.metric_not_clear_ready_after_search / n,
        "active_measurements_per_source": sum(state.attempts for state in agent.state.values()) / n,
        "co_measurements_per_source": getattr(agent, "co_measurements", 0) / n,
        "coverage_insertions_per_source": getattr(agent, "coverage_insertions", 0) / n,
        "decomposition_error_s": abs(
            result["total_virtual_time_s"] - movement - detect_switch - clear_actions
        ),
    }


def run_case(item):
    seed, case, sources = item
    noise_seed = seed * 100000 + case
    return [run_agent(name, klass, sources, noise_seed, case, seed) for name, klass in MODELS]


METRICS = (
    "total_time_per_source_s", "movement_time_per_source_s",
    "detection_switch_time_per_source_s", "clear_action_time_per_source_s",
    "measure_actions_per_source", "channel_switches_per_source",
    "last_discovery_time_per_source_s", "search_end_time_per_source_s",
    "search_movement_time_per_source_s", "unfinished_after_search_rate",
    "not_clear_ready_after_search_rate", "active_measurements_per_source",
    "co_measurements_per_source", "coverage_insertions_per_source",
)


def summarize(rows):
    summaries = []
    for model, _ in MODELS:
        subset = [row for row in rows if row["model"] == model]
        item = {"model": model, "cases": len(subset)}
        for metric in METRICS:
            values = [row[metric] for row in subset]
            item[f"mean_{metric}"] = statistics.mean(values)
            if metric == "total_time_per_source_s":
                item[f"p95_{metric}"] = percentile(values, .95)
        item["all_cleared_rate"] = statistics.mean(row["all_cleared"] for row in subset)
        summaries.append(item)
    lookup = {(r["seed"], r["case"], r["model"]): r for r in rows}
    cases = sorted({(r["seed"], r["case"]) for r in rows})
    paired = []
    for left, right in PAIRS:
        for metric in METRICS:
            differences = [lookup[(seed, case, left)][metric] - lookup[(seed, case, right)][metric]
                           for seed, case in cases]
            paired.append({
                "left": left, "right": right, "metric": metric,
                "mean_left_minus_right": statistics.mean(differences),
                "right_better_cases": sum(value > 1e-9 for value in differences),
                "equal_cases": sum(abs(value) <= 1e-9 for value in differences),
                "left_better_cases": sum(value < -1e-9 for value in differences),
            })
    return summaries, paired


def main():
    parser = argparse.ArgumentParser(description="I 到 J+ 的覆盖环与测量调度消融")
    parser.add_argument("--seeds", default="112358,271828,314159")
    parser.add_argument("--cases-per-seed", type=int, default=200)
    parser.add_argument("--jobs", type=int, default=16)
    parser.add_argument("--output", default="diagnostics/results/i_to_jplus_metrics_600")
    args = parser.parse_args()
    work = []
    for seed in [int(value) for value in args.seeds.split(",")]:
        rng = random.Random(seed)
        for case in range(1, args.cases_per_seed + 1):
            work.append((seed, case, random_sources(rng, None)))
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            batches = list(pool.map(run_case, work))
    else:
        batches = [run_case(item) for item in work]
    rows = [row for batch in batches for row in batch]
    summaries, paired_rows = summarize(rows)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "case_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    payload = {"config": vars(args), "summaries": summaries, "paired": paired_rows}
    (output / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

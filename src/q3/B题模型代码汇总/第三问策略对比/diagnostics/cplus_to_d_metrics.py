"""Paired seven-metric and 2x2 mechanism backtest for the C+ -> D branch."""
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

from baseline_core import OfflineSimulator, random_sources
from strategies import CPlusAgent, HybridBeliefRollingAgent
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


class _RollingRunMixin:
    """Execute one action and re-plan the unresolved-channel route."""

    def run(self):
        self.sim.enter()
        self.search()
        for _ in range(240):
            unresolved = [
                (channel, state) for channel, state in self.state.items()
                if state.discovered and not state.cleared and not state.exhausted
            ]
            if not unresolved:
                break
            channel = self._two_opt_route([item[0] for item in unresolved])[0]
            state = self.state[channel]
            center = self._clear_decision(state)
            if center is not None:
                if self._try_clear(center, channel):
                    state.cleared = True
                    self._coobserve(center, channel)
                continue
            if state.attempts >= 10:
                state.exhausted = True
                continue
            point = self._next_measurement_point(state)
            if point is None:
                state.exhausted = True
                continue
            self.observe(point, channel)
            state.attempts += 1
            self._coobserve(point, channel)
        self.sim.exit()
        return self.summary()


class MetricCPlusAgent(_SearchSnapshotMixin, CPlusAgent):
    pass


class MetricCPlusRollingAgent(_SearchSnapshotMixin, _RollingRunMixin, CPlusAgent):
    pass


class MetricDBeliefBatchAgent(_SearchSnapshotMixin, HybridBeliefRollingAgent):
    # Retain D's probabilistic/risk-aware selection, but use C+'s batch completion.
    run = CPlusAgent.run


class MetricDFullAgent(_SearchSnapshotMixin, HybridBeliefRollingAgent):
    pass


MODELS = (
    ("C+", MetricCPlusAgent),
    ("Cplus_rolling", MetricCPlusRollingAgent),
    ("D_belief_batch", MetricDBeliefBatchAgent),
    ("D", MetricDFullAgent),
)


def run_agent(name, klass, sources, noise_seed, case, seed):
    sim = OfflineSimulator(clone_sources(sources), noise_seed)
    agent = klass(sim)
    result = agent.run()
    n = len(sources)
    movement, detect_switch, clear_actions, switches, last_discovery = action_metrics(
        sim, {item.channel for item in sources}
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
    "unfinished_after_search_rate", "not_clear_ready_after_search_rate",
    "active_measurements_per_source", "co_measurements_per_source",
)


def summarize(rows):
    result = []
    for model, _ in MODELS:
        subset = [row for row in rows if row["model"] == model]
        item = {"model": model, "cases": len(subset)}
        for metric in METRICS:
            values = [row[metric] for row in subset]
            item[f"mean_{metric}"] = statistics.mean(values)
            if metric == "total_time_per_source_s":
                item[f"p95_{metric}"] = percentile(values, .95)
        item["all_cleared_rate"] = statistics.mean(row["all_cleared"] for row in subset)
        result.append(item)
    lookup = {(row["seed"], row["case"], row["model"]): row for row in rows}
    cases = sorted({(row["seed"], row["case"]) for row in rows})
    paired = []
    for left, right in (
        ("C+", "D"), ("C+", "Cplus_rolling"),
        ("C+", "D_belief_batch"), ("Cplus_rolling", "D"),
        ("D_belief_batch", "D"),
    ):
        for metric in METRICS:
            differences = [lookup[(seed, case, left)][metric] - lookup[(seed, case, right)][metric]
                           for seed, case in cases]
            paired.append({
                "left": left, "right": right, "metric": metric,
                "mean_left_minus_right": statistics.mean(differences),
                "right_better_cases": sum(item > 1e-9 for item in differences),
                "equal_cases": sum(abs(item) <= 1e-9 for item in differences),
                "left_better_cases": sum(item < -1e-9 for item in differences),
            })
    return result, paired


def main():
    parser = argparse.ArgumentParser(description="C+ 到 D 分支的七指标与 2x2 消融")
    parser.add_argument("--seeds", default="112358,271828,314159")
    parser.add_argument("--cases-per-seed", type=int, default=200)
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--output", default="diagnostics/results/cplus_to_d_metrics_600")
    args = parser.parse_args()
    work = []
    for seed in [int(item) for item in args.seeds.split(",")]:
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

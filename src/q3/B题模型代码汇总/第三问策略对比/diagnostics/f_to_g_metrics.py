"""Paired mechanism backtest for F -> G with rolling diagnostics."""
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
from strategies import (CoverageIntegratedAgent, MarginalInsertionAgent,
                        MarginalRollingAgent, RollingCoverageAgent)
from c_to_cplus_metrics import action_metrics, clone_sources, percentile


class _MetricMixin:
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

    def _start_primary_log(self):
        self.metric_primary_sequence = []
        self.metric_preemptions = 0

    def _record_primary(self, channel):
        if self.metric_primary_sequence and self.metric_primary_sequence[-1] != channel:
            previous = self.state[self.metric_primary_sequence[-1]]
            if previous.discovered and not previous.cleared and not previous.exhausted:
                self.metric_preemptions += 1
        self.metric_primary_sequence.append(channel)

    def _finish_primary_log(self):
        blocks = []
        for channel in self.metric_primary_sequence:
            if not blocks or blocks[-1] != channel:
                blocks.append(channel)
        counts = {channel: blocks.count(channel) for channel in set(blocks)}
        self.metric_primary_blocks = len(blocks)
        self.metric_revisited_channels = sum(value > 1 for value in counts.values())


class _BatchRunMixin:
    def run(self):
        self._start_primary_log()
        self.sim.enter()
        self.search()
        while True:
            targets = [channel for channel, state in self.state.items()
                       if state.discovered and not state.cleared and not state.exhausted]
            if not targets:
                break
            channel = self._two_opt_route(targets)[0]
            self._record_primary(channel)
            self.localize_and_clear(channel)
        self.sim.exit()
        self._finish_primary_log()
        return self.summary()


class _RollingRunMixin:
    def run(self):
        self._start_primary_log()
        self.sim.enter()
        self.search()
        for _ in range(240):
            unresolved = [channel for channel, state in self.state.items()
                          if state.discovered and not state.cleared and not state.exhausted]
            if not unresolved:
                break
            channel = self._two_opt_route(unresolved)[0]
            self._record_primary(channel)
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
        self._finish_primary_log()
        return self.summary()


class MetricFAgent(_MetricMixin, _BatchRunMixin, CoverageIntegratedAgent):
    pass


class MetricGAgent(_MetricMixin, _RollingRunMixin, RollingCoverageAgent):
    pass


class MetricMarginalFAgent(_MetricMixin, _BatchRunMixin, MarginalInsertionAgent):
    pass


class MetricMarginalGAgent(_MetricMixin, _RollingRunMixin, MarginalRollingAgent):
    pass


MODELS = (
    ("F", MetricFAgent),
    ("G", MetricGAgent),
    ("F_marginal_insert", MetricMarginalFAgent),
    ("G_marginal_insert", MetricMarginalGAgent),
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
        "unfinished_after_search_rate": agent.metric_unfinished_after_search / n,
        "not_clear_ready_after_search_rate": agent.metric_not_clear_ready_after_search / n,
        "active_measurements_per_source": sum(state.attempts for state in agent.state.values()) / n,
        "co_measurements_per_source": getattr(agent, "co_measurements", 0) / n,
        "coverage_insertions_per_source": getattr(agent, "coverage_insertions", 0) / n,
        "primary_blocks_per_source": agent.metric_primary_blocks / n,
        "revisited_channel_rate": agent.metric_revisited_channels / n,
        "preemptions_per_source": agent.metric_preemptions / n,
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
    "coverage_insertions_per_source", "primary_blocks_per_source",
    "revisited_channel_rate", "preemptions_per_source",
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
    for left, right in (("F", "G"), ("F_marginal_insert", "G_marginal_insert"),
                        ("F", "F_marginal_insert"), ("G", "G_marginal_insert")):
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
    parser = argparse.ArgumentParser(description="F 到 G 的七指标与滚动消融回测")
    parser.add_argument("--seeds", default="112358,271828,314159")
    parser.add_argument("--cases-per-seed", type=int, default=200)
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--output", default="diagnostics/results/f_to_g_metrics_600")
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

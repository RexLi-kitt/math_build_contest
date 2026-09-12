"""Paired, truth-assisted diagnostics for B problem 3 strategies.

All truth access in this module is explicitly restricted to counterfactual
diagnostic groups.  Production strategies in strategies.py remain unchanged.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from array import array
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# The diagnostic lives one directory below the strategy modules so it can be
# executed either from this directory or from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from baseline_core import OfflineSimulator, Source, dist, random_sources
from strategies import (
    CPlusAgent,
    CoverageIntegratedAgent,
    Q2FourMetricAgent,
    RingOptimizedAgent,
)


class CReweightedAgent(Q2FourMetricAgent):
    """C with C+ weights only; isolates the parameter change."""

    weights = CPlusAgent.weights


class CCompletionOnlyAgent(CPlusAgent):
    """C+ completion-time objective with co-observation disabled."""

    max_coobservations = 0


class CCompletionCWeightsAgent(CPlusAgent):
    """Completion-time objective only, retaining C's original weights."""

    weights = Q2FourMetricAgent.weights
    max_coobservations = 0


class CCoobserveOnlyAgent(CPlusAgent):
    """C selection objective plus C+ stationary co-observation."""

    weights = Q2FourMetricAgent.weights
    _raw_metrics = Q2FourMetricAgent._raw_metrics


class CCompletionCoobserveCWeightsAgent(CPlusAgent):
    """Completion-time plus co-observation, retaining C's original weights."""

    weights = Q2FourMetricAgent.weights


class FNoInsertionAgent(CoverageIntegratedAgent):
    """F's adaptive cover tour and stationary measurements, without insertions."""

    max_coverage_insertions = 0


class DiscoveryTruthRingAgent(RingOptimizedAgent):
    """Diagnostic only: a source position is revealed after its first signal.

    It keeps the same noisy search process.  Once a channel has been detected,
    its exact position may be used for the conservative clear decision.  This
    estimates the value of removing post-discovery localization uncertainty.
    """

    def observe(self, point, channel):
        result = super().observe(point, channel)
        if self.state[channel].discovered and not self.state[channel].cleared:
            self.state[channel].oracle_point = self.sim.sources[channel].position
        return result

    def _clear_decision(self, st):
        point = getattr(st, "oracle_point", None)
        return point if point is not None else super()._clear_decision(st)


def clone_sources(sources: list[Source]) -> list[Source]:
    return [Source(s.channel, s.position, s.receive_radius) for s in sources]


def movement_time(actions) -> float:
    previous = (0.0, 0.0)
    distance = 0.0
    for action in actions:
        if action.position is not None:
            distance += dist(previous, action.position)
            previous = action.position
    return distance / 5.0


def open_path_cost(points: list[tuple[float, float]], start=(0.0, 0.0),
                   clearance_radius: float = 0.0) -> float:
    """Exact Held--Karp cost for visiting the supplied points in an open route.

    clearance_radius=0 gives a feasible truth-known direct-clear route through
    source centres.  clearance_radius=20 uses pairwise disk-distance relaxation,
    hence is a lower bound rather than a feasible route in general.
    """
    n = len(points)
    if not n:
        return 0.0
    size = 1 << n
    values = array("d", [math.inf]) * (size * n)
    for j, point in enumerate(points):
        values[(1 << j) * n + j] = max(0.0, dist(start, point) - clearance_radius)
    for mask in range(1, size):
        rest = mask
        while rest:
            bit = rest & -rest
            rest -= bit
            j = bit.bit_length() - 1
            previous = mask ^ bit
            if not previous:
                continue
            best = math.inf
            candidates = previous
            while candidates:
                prior_bit = candidates & -candidates
                candidates -= prior_bit
                k = prior_bit.bit_length() - 1
                gap = max(0.0, dist(points[k], points[j]) - 2.0 * clearance_radius)
                best = min(best, values[previous * n + k] + gap)
            values[mask * n + j] = best
    return min(values[(size - 1) * n:(size - 1) * n + n])


def run_agent(agent_class, sources: list[Source], noise_seed: int):
    sim = OfflineSimulator(clone_sources(sources), noise_seed)
    agent = agent_class(sim)
    result = agent.run()
    return result, agent, sim


def per_source(value: float, count: int) -> float:
    return value / count


def run_case(item):
    case, sources, master_seed = item
    n = len(sources)
    noise_seed = master_seed * 100000 + case
    normal, normal_agent, normal_sim = run_agent(RingOptimizedAgent, sources, noise_seed)
    revealed, revealed_agent, revealed_sim = run_agent(DiscoveryTruthRingAgent, sources, noise_seed)

    # This group runs I's ordinary search.  Only then are remaining positions
    # revealed and cleared along the exact shortest open route through centres.
    post_sim = OfflineSimulator(clone_sources(sources), noise_seed)
    post_agent = RingOptimizedAgent(post_sim)
    post_sim.enter()
    post_agent.search()
    post_search_time = post_sim.time_s
    remaining = [source for source in post_sim.sources.values() if not source.cleared]
    post_oracle_distance = open_path_cost([source.position for source in remaining], post_sim.position)
    post_oracle_total = post_search_time + post_oracle_distance / 5.0 + 5.0 * len(remaining)

    centres = [source.position for source in sources]
    full_truth_direct = open_path_cost(centres) / 5.0 + 5.0 * n
    full_truth_lower = open_path_cost(centres, clearance_radius=20.0) / 5.0 + 5.0 * n

    variants = [
        ("C", Q2FourMetricAgent),
        ("C_reweighted", CReweightedAgent),
        ("C_completion_c_weights", CCompletionCWeightsAgent),
        ("C_completion_only", CCompletionOnlyAgent),
        ("C_coobserve_only", CCoobserveOnlyAgent),
        ("C_completion_coobserve_c_weights", CCompletionCoobserveCWeightsAgent),
        ("Cplus", CPlusAgent),
        ("F_no_insertion", FNoInsertionAgent),
        ("F", CoverageIntegratedAgent),
    ]
    rows = []
    for name, klass in variants:
        result, agent, sim = run_agent(klass, sources, noise_seed)
        rows.append({
            "case": case, "group": name, "source_count": n,
            "total_time_s": result["total_virtual_time_s"],
            "time_per_source_s": per_source(result["total_virtual_time_s"], n),
            "movement_time_s": movement_time(sim.actions),
            "measure_actions": result["measure_actions"],
            "cleared": result["cleared_channels"],
        })

    rows.extend([
        {"case": case, "group": "I_normal", "source_count": n,
         "total_time_s": normal["total_virtual_time_s"],
         "time_per_source_s": per_source(normal["total_virtual_time_s"], n),
         "search_time_s": getattr(normal_agent, "search_end_time_s", math.nan),
         "post_search_time_s": normal["total_virtual_time_s"] - getattr(normal_agent, "search_end_time_s", 0.0),
         "movement_time_s": movement_time(normal_sim.actions), "measure_actions": normal["measure_actions"],
         "cleared": normal["cleared_channels"]},
        {"case": case, "group": "I_discovery_truth", "source_count": n,
         "total_time_s": revealed["total_virtual_time_s"],
         "time_per_source_s": per_source(revealed["total_virtual_time_s"], n),
         "movement_time_s": movement_time(revealed_sim.actions), "measure_actions": revealed["measure_actions"],
         "cleared": revealed["cleared_channels"]},
        {"case": case, "group": "truth_after_search", "source_count": n,
         "total_time_s": post_oracle_total, "time_per_source_s": per_source(post_oracle_total, n),
         "search_time_s": post_search_time, "post_search_time_s": post_oracle_total - post_search_time,
         "cleared": n},
        {"case": case, "group": "truth_direct_centres", "source_count": n,
         "total_time_s": full_truth_direct, "time_per_source_s": per_source(full_truth_direct, n), "cleared": n},
        {"case": case, "group": "truth_disk_lower_bound", "source_count": n,
         "total_time_s": full_truth_lower, "time_per_source_s": per_source(full_truth_lower, n), "cleared": n},
    ])
    return rows


def summary(rows):
    output = []
    groups = sorted({row["group"] for row in rows})
    for group in groups:
        subset = [row for row in rows if row["group"] == group]
        values = [row["time_per_source_s"] for row in subset]
        output.append({
            "group": group, "cases": len(subset),
            "mean_time_per_source_s": statistics.mean(values),
            "median_time_per_source_s": statistics.median(values),
            "p95_time_per_source_s": sorted(values)[math.ceil(.95 * len(values)) - 1],
            "all_cleared_rate": sum(row["cleared"] == row["source_count"] for row in subset) / len(subset),
        })
    return output


def main():
    parser = argparse.ArgumentParser(description="第三问真值辅助与模块消融诊断")
    parser.add_argument("--cases", type=int, default=100)
    parser.add_argument("--seed", type=int, default=982451653)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--output", default="diagnostics/results/diagnostic_seed982451653_100")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    work = [(case, random_sources(rng, None), args.seed) for case in range(1, args.cases + 1)]
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            case_rows = list(pool.map(run_case, work))
    else:
        case_rows = [run_case(item) for item in work]
    rows = [row for group in case_rows for row in group]
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with (out / "case_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    payload = {"config": vars(args), "summaries": summary(rows)}
    (out / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

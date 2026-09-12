"""Screen the two Q3 coverage-insertion parameters on paired cases."""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import time
from pathlib import Path

from baseline_core import OfflineSimulator, Source, random_sources
from strategies import CoverageIntegratedAgent

CONFIGS = [(100.0, 6), (140.0, 8), (180.0, 8), (180.0, 12), (220.0, 10)]


def clone(sources: list[Source]) -> list[Source]:
    return [Source(s.channel, s.position, s.receive_radius) for s in sources]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=20)
    parser.add_argument("--seed", type=int, default=70501)
    parser.add_argument("--output", default="results/coverage_rule_screen.json")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    cases = [random_sources(rng, None) for _ in range(args.cases)]
    records = []
    for budget, maximum in CONFIGS:
        class Trial(CoverageIntegratedAgent):
            pass
        Trial.insertion_budget_m = budget
        Trial.max_coverage_insertions = maximum
        rows = []
        started = time.perf_counter()
        for index, sources in enumerate(cases, 1):
            sim = OfflineSimulator(clone(sources), args.seed * 100000 + index)
            agent = Trial(sim); result = agent.run()
            movement = 0.0; previous = (0.0, 0.0)
            for action in sim.actions:
                if action.position is not None:
                    movement += math.dist(previous, action.position) / 5.0
                    previous = action.position
            rows.append({"success": result["cleared_channels"] == len(sources),
                         "per_source": result["total_virtual_time_s"] / len(sources),
                         "movement": movement, "measure": result["measure_actions"],
                         "insertions": agent.coverage_insertions})
        values = sorted(row["per_source"] for row in rows)
        tail = values[max(0, math.ceil(.9 * len(values)) - 1):]
        record = {"insertion_budget_m": budget, "max_insertions": maximum,
                  "clear_rate": sum(row["success"] for row in rows) / len(rows),
                  "mean_per_source_s": statistics.mean(values),
                  "cvar90_per_source_s": statistics.mean(tail),
                  "mean_movement_s": statistics.mean(row["movement"] for row in rows),
                  "mean_measure_actions": statistics.mean(row["measure"] for row in rows),
                  "mean_insertions": statistics.mean(row["insertions"] for row in rows),
                  "wall_time_s": time.perf_counter() - started}
        record["loss"] = (.7 * record["mean_per_source_s"] + .3 * record["cvar90_per_source_s"]
                          + 100000 * (1 - record["clear_rate"]))
        records.append(record); print(json.dumps(record, ensure_ascii=False), flush=True)
    records.sort(key=lambda row: row["loss"])
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"seed": args.seed, "cases": args.cases, "records": records},
                               ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

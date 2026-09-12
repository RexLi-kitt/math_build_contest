"""Small paired training-screen for C+ weights; validation is run separately."""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import time
from pathlib import Path

from baseline_core import OfflineSimulator, Source, random_sources
from strategies import CPlusAgent

WEIGHTS = [
    (0.35, 0.30, 0.15, 0.20),
    (0.30, 0.30, 0.25, 0.15),
    (0.25, 0.30, 0.30, 0.15),
    (0.25, 0.35, 0.25, 0.15),
    (0.30, 0.25, 0.30, 0.15),
    (0.25, 0.25, 0.35, 0.15),
]


def clone(sources: list[Source]) -> list[Source]:
    return [Source(s.channel, s.position, s.receive_radius) for s in sources]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=20)
    parser.add_argument("--seed", type=int, default=41001)
    parser.add_argument("--output", default="results/weight_screen.json")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    cases = [random_sources(rng, None) for _ in range(args.cases)]
    records = []
    for index, weights in enumerate(WEIGHTS, 1):
        class TrialAgent(CPlusAgent):
            pass
        TrialAgent.weights = weights
        rows = []
        start = time.perf_counter()
        for case_index, sources in enumerate(cases, 1):
            sim = OfflineSimulator(clone(sources), args.seed * 100000 + case_index)
            result = TrialAgent(sim).run()
            rows.append((result["cleared_channels"] == len(sources),
                         result["total_virtual_time_s"] / len(sources)))
        per_source = sorted(row[1] for row in rows)
        tail = per_source[max(0, math.ceil(.9 * len(per_source)) - 1):]
        mean = statistics.mean(per_source)
        cvar90 = statistics.mean(tail)
        success = sum(row[0] for row in rows) / len(rows)
        loss = .7 * mean + .3 * cvar90 + 100000.0 * (1.0 - success)
        record = {"weights": weights, "all_cleared_rate": success,
                  "mean_time_per_source_s": mean, "cvar90_time_per_source_s": cvar90,
                  "loss": loss, "wall_time_s": time.perf_counter() - start}
        records.append(record)
        print(f"{index}/{len(WEIGHTS)} {json.dumps(record, ensure_ascii=False)}", flush=True)
    records.sort(key=lambda row: row["loss"])
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cases": args.cases, "seed": args.seed,
                                "objective": "0.7*mean+0.3*CVaR90+100000*(1-clear_rate)",
                                "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

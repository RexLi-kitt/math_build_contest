"""Reproduce D versus its C+3F predecessor on 10--16 source scenarios."""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from pathlib import Path

from d_agent import DAgent
from q4_experiment import (DirectionalSimulator, Q4TriangularCoverageAgent,
                           clone_sources, random_mixed_sources)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "outputs" / "q4" / "results" / "d_model" / "reproduction.json"


class CPlus3FReference(DAgent):
    """D with the B-branch filter disabled, equivalent to frozen C+3F."""

    def _coobserve(self, point, primary_channel):
        if self.selected_search_order == "B":
            return Q4TriangularCoverageAgent._coobserve(self, point, primary_channel)
        return super()._coobserve(point, primary_channel)


def build_cases(kind: str, count: int, source_count: int, seed: int):
    rng = random.Random(seed)
    cases = []
    for index in range(count):
        sources = random_mixed_sources(rng, source_count, 0.5 if kind == "normal" else 0.75)
        if kind != "normal":
            for source in sources:
                angle = rng.random() * 2.0 * math.pi
                radius = 1800.0 if kind == "boundary_outward" and index % 2 == 0 \
                    else rng.uniform(1700.0, 1800.0)
                source.position = radius * math.cos(angle), radius * math.sin(angle)
                source.receive_radius = 1000.0
                if kind == "boundary_outward" and source.beam_direction is not None:
                    source.beam_direction = math.degrees(angle) % 360.0
        cases.append(sources)
    return cases


def run_agent(agent_class, sources, seed):
    simulator = DirectionalSimulator(clone_sources(sources), seed)
    return agent_class(simulator).run()


def paired_summary(cases, seed):
    old, new, cleared = [], [], 0
    for index, sources in enumerate(cases, 1):
        case_seed = seed * 100000 + index
        before = run_agent(CPlus3FReference, sources, case_seed)
        after = run_agent(DAgent, sources, case_seed)
        old.append(before["total_virtual_time_s"] / len(sources))
        new.append(after["total_virtual_time_s"] / len(sources))
        cleared += after["cleared_channels"] == len(sources)
    differences = [a - b for a, b in zip(new, old)]
    mean = statistics.mean(differences)
    half = (1.96 * statistics.stdev(differences) / math.sqrt(len(differences))
            if len(differences) > 1 else 0.0)
    return {
        "cases": len(cases),
        "all_clear": cleared,
        "cplus3f_mean_s_per_source": statistics.mean(old),
        "d_mean_s_per_source": statistics.mean(new),
        "d_minus_cplus3f": mean,
        "normal_approx_95ci": [mean - half, mean + half],
        "win_rate": sum(value < 0 for value in differences) / len(differences),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=50)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = {}
    for count_index, source_count in enumerate((10, 12, 14, 16)):
        for kind_index, kind in enumerate(("normal", "boundary_random", "boundary_outward")):
            seed = 20270310 + count_index * 10 + kind_index
            label = f"{kind}_n{source_count}"
            cases = build_cases(kind, args.cases, source_count, seed)
            payload[label] = paired_summary(cases, seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()

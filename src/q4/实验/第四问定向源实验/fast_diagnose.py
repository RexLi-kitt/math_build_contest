"""Diagnose a single case for fast_q4 strategies (detection/clearing failure)."""
from __future__ import annotations

import argparse
import random

from q4_experiment import DirectionalSimulator, clone_sources, random_mixed_sources
from fast_compare import STRATEGIES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--case", type=int, required=True)
    parser.add_argument("--strategy", default="L1100I3")
    parser.add_argument("--sources", type=int)
    parser.add_argument("--directional-fraction", type=float, default=0.5)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    sources = None
    for index in range(1, args.case + 1):
        sources = random_mixed_sources(rng, args.sources, args.directional_fraction)
    sim = DirectionalSimulator(clone_sources(sources), args.seed * 100000 + args.case)
    agent = STRATEGIES[args.strategy](sim)
    result = agent.run()
    print(args.strategy, "CASE", args.case, "sources", len(sources), result)
    for source in sources:
        state = agent.state[source.channel]
        if not state.cleared:
            print({
                "channel": source.channel,
                "position": tuple(round(v, 1) for v in source.position),
                "radius": round(source.receive_radius, 1),
                "beam": None if source.beam_direction is None else round(source.beam_direction, 1),
                "discovered": state.discovered,
                "observations": [(tuple(round(v, 1) for v in p), round(a, 2)) for p, a in state.observations],
                "attempts": state.attempts,
                "no_signal": len(state.no_signal_points),
                "failed_clear_points": len(state.failed_clear_points),
                "exhausted": state.exhausted,
            })


if __name__ == "__main__":
    main()

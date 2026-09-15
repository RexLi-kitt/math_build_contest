"""Compare post-search waste between strategies."""
from __future__ import annotations

import random
import sys

sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")

from q4_experiment import DirectionalSimulator, clone_sources, random_mixed_sources
from fast_compare import STRATEGIES


def run(name, cases, seed):
    rng = random.Random(seed)
    post = {"direction": 0, "no_signal": 0, "near": 0}
    total_time = 0.0
    for index in range(1, cases + 1):
        sources = random_mixed_sources(rng, None, 0.5)
        sim = DirectionalSimulator(clone_sources(sources), seed * 100000 + index)
        agent = STRATEGIES[name](sim)
        agent.run()
        search_end = getattr(agent, "search_end_time_s", float("inf"))
        total_time += sim.time_s
        for a in sim.actions:
            if a.kind == "measure" and a.virtual_time_s > search_end + 1e-6:
                post[a.result] += 1
    print(f"{name:>10}: post direction={post['direction']} no_signal={post['no_signal']} "
          f"waste={post['no_signal'] / max(1, post['direction'] + post['no_signal']):.1%} "
          f"time/src={total_time / cases / 13:.1f}")


if __name__ == "__main__":
    cases = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 20260916
    for name in sys.argv[3:]:
        run(name, cases, seed)

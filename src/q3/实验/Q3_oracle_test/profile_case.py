"""Profile one case: agent decision time vs oracle Held-Karp time."""
from __future__ import annotations

import cProfile
import io
import pstats
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oracle_harness import (InstrumentedI, Ring7Compact,  # noqa: E402
                            VARIANTS, extract, held_karp_open, oracle_bounds)

from baseline_core import OfflineSimulator, Source, random_sources  # noqa: E402

seed = 55021
rng = random.Random(seed)
cases = [random_sources(rng, None) for _ in range(5)]

for name in ("I_ring_optimized", "R7_b100_co5_even"):
    agent_cls = VARIANTS[name]
    wall_agent = wall_oracle = 0.0
    for index, sources in enumerate(cases, 1):
        sim = OfflineSimulator([Source(s.channel, s.position, s.receive_radius)
                                for s in sources], seed=seed * 100000 + index)
        agent = agent_cls(sim)
        t0 = time.perf_counter()
        agent.run()
        t1 = time.perf_counter()
        metrics = extract(sim, agent, sources)
        oracle_bounds(sim, agent, sources, metrics)
        t2 = time.perf_counter()
        wall_agent += t1 - t0
        wall_oracle += t2 - t1
    print(f"{name}: agent {wall_agent/5:.3f} s/case, extract+oracle {wall_oracle/5:.3f} s/case")

profile = cProfile.Profile()
sim = OfflineSimulator([Source(s.channel, s.position, s.receive_radius)
                        for s in cases[0]], seed=seed * 100000 + 1)
agent = VARIANTS["R7_b100_co5_even"](sim)
profile.enable()
agent.run()
profile.disable()
stream = io.StringIO()
pstats.Stats(profile, stream=stream).sort_stats("cumulative").print_stats(18)
print(stream.getvalue())

t0 = time.perf_counter()
held_karp_open((0.0, 0.0), [s.position for s in cases[0]])
print(f"held_karp_open n={len(cases[0])}: {time.perf_counter()-t0:.4f} s")

"""顺序变体筛选 v3: 正常100 + 压力100, Base/OrdArea/MixB05/MixB1/MixB2。"""
from __future__ import annotations

import math
import random
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

EXP = r"C:\Users\李\Desktop\第四问定向源实验"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, EXP)
sys.path.insert(0, str(HERE))

import q4_optimize  # noqa: E402
from q4_optimize import run_case  # noqa: E402
from q4_experiment import random_mixed_sources  # noqa: E402
from cert_route_agent import CertRouteAgent  # noqa: E402
from cert_order_agents import (MixB05Agent, MixB1Agent, MixB2Agent,  # noqa: E402
                               OrderAreaAgent)

STRATS = {
    "Base": CertRouteAgent,
    "OrdArea": OrderAreaAgent,
    "MixB05": MixB05Agent,
    "MixB1": MixB1Agent,
    "MixB2": MixB2Agent,
}


def run_stage(cases, seed, label):
    work = [(index, sources, seed, name, cls)
            for index, sources in enumerate(cases, 1)
            for name, cls in STRATS.items()]
    rows = []
    with ProcessPoolExecutor(max_workers=16) as pool:
        for row in pool.map(q4_optimize._run_work, work):
            rows.append(row)
    print(f"\n== {label} ==", flush=True)
    for name in STRATS:
        g = [r for r in rows if r["strategy"] == name]
        per = [r["total_virtual_time_s"] / r["source_count"] for r in g]
        print(f"{name:>8}: {sum(r['all_cleared'] for r in g)}/{len(g)} "
              f"mean={statistics.mean(per):7.2f} "
              f"p95={q4_optimize.percentile(per, 0.95):7.2f} "
              f"det={statistics.mean(r['detection_time_s']/r['source_count'] for r in g):6.1f} "
              f"meas={statistics.mean(r['measure_actions'] for r in g):6.1f}",
              flush=True)


def main():
    rng = random.Random(20260928)
    normal = [random_mixed_sources(rng, None, 0.5) for _ in range(100)]
    run_stage(normal, 20260928, "normal 100 seed=20260928")

    rng = random.Random(20260929)
    stress = []
    for index in range(100):
        sources = random_mixed_sources(rng, 16, 0.75)
        for source in sources:
            angle = rng.random() * 2 * math.pi
            radius = 1800.0 if index % 2 == 0 else rng.uniform(1700, 1800)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
            source.receive_radius = 1000.0
            if source.beam_direction is not None:
                source.beam_direction = math.degrees(angle) % 360
        stress.append(sources)
    run_stage(stress, 20260929, "stress 100 seed=20260929")


if __name__ == "__main__":
    main()

"""风险映射: AggOrder 在"困难但非对抗"场景下的表现。

场景A minR-uniform: 16源均匀分布, 全部 R=1000, 50%定向随机波束
场景B boundary-randbeam: 16源在 r∈[1700,1800], R=1000, 75%定向随机波束
对照 C: 官方标准正常场景 (均匀, R∈[1000,1500], 50%定向)
策略: Bplus / AggOrder。
"""
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
from cert_joint_agents import AggOrderAgent  # noqa: E402

STRATS = {"Bplus": CertRouteAgent, "AggOrder": AggOrderAgent}


def work(item):
    index, sources, seed = item
    return [run_case(index, sources, seed, name, cls)
            for name, cls in STRATS.items()]


def run(cases, seed, label):
    jobs = [(i, s, seed) for i, s in enumerate(cases, 1)]
    rows = []
    with ProcessPoolExecutor(max_workers=16) as pool:
        for group in pool.map(work, jobs):
            rows.extend(group)
    print(f"\n== {label} ==", flush=True)
    for name in STRATS:
        g = [r for r in rows if r["strategy"] == name]
        per = [r["total_virtual_time_s"] / r["source_count"] for r in g]
        print(f"{name:>8}: {sum(r['all_cleared'] for r in g)}/{len(g)} "
              f"mean={statistics.mean(per):7.2f} "
              f"det={statistics.mean(r['detection_time_s']/r['source_count'] for r in g):6.1f}",
              flush=True)


def main():
    n = 100
    # A: 全 R=1000 均匀
    rng = random.Random(20260931)
    cases_a = []
    for _ in range(n):
        sources = random_mixed_sources(rng, 16, 0.5)
        for s in sources:
            s.receive_radius = 1000.0
        cases_a.append(sources)
    run(cases_a, 20260931, "A minR-uniform 16源 R=1000 50%定向")

    # B: 边界带随机波束
    rng = random.Random(20260932)
    cases_b = []
    for _ in range(n):
        sources = random_mixed_sources(rng, 16, 0.75)
        for s in sources:
            angle = rng.random() * 2 * math.pi
            radius = rng.uniform(1700, 1800)
            s.position = radius * math.cos(angle), radius * math.sin(angle)
            s.receive_radius = 1000.0
            if s.beam_direction is not None:
                s.beam_direction = rng.uniform(0.0, 360.0)
        cases_b.append(sources)
    run(cases_b, 20260932, "B boundary-randbeam 16源 75%定向 随机波束")


if __name__ == "__main__":
    main()

"""Fine audit of H8-class designs + randomized search for a shorter certified tour."""
from __future__ import annotations

import math
import random
import sys

sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")
from certify import certify, ring
from strong_tsp import solve_tour


def build(spec):
    sites = [(0.0, 0.0)]
    for radius, count, offset in spec:
        sites.extend(ring(radius, count, offset))
    return sites


def estimated_cost(sites, tour_m, scan_s_per_site=62.0):
    return tour_m / 5.0 + scan_s_per_site * len(sites)


def fine_audit(name, spec):
    sites = build(spec)
    worst, wx = certify(sites, r_step=10.0, t_step=0.5)
    print(f"{name}: n={len(sites)} fine(max_gap)={worst:.2f} worst=({wx[0]:.0f},{wx[1]:.0f})")
    return worst


if __name__ == "__main__":
    h8 = ((1000.0, 6, 0.0), (1400.0, 12, 15.0), (2000.0, 12, 0.0))
    coarse, _ = certify(build(h8), r_step=30.0, t_step=1.0)
    print(f"H8 coarse(30/1) gap={coarse:.2f}")
    print("fine audit H8 ...")
    fine_audit("H8", h8)

    rng = random.Random(20260912)
    best = []
    for trial in range(80):
        k1 = rng.choice((5, 6, 7, 8))
        r1 = rng.uniform(930, 1060)
        k2 = rng.choice((10, 12, 14))
        r2 = rng.uniform(1280, 1520)
        k3 = rng.choice((10, 12, 14))
        r3 = rng.uniform(1850, 2120)
        o1 = rng.uniform(0, 360.0 / k1)
        o2 = rng.uniform(0, 360.0 / k2)
        o3 = rng.uniform(0, 360.0 / k3)
        spec = ((r1, k1, o1), (r2, k2, o2), (r3, k3, o3))
        sites = build(spec)
        gap, _ = certify(sites, r_step=60.0, t_step=4.0)
        if gap > 176.0:
            continue
        _order, tour = solve_tour(sites[1:], restarts=10)
        best.append((estimated_cost(sites, tour), gap, tour, len(sites), spec))
        print(f"trial {trial:>3}: cost={best[-1][0]:7.0f} gap={gap:6.2f} tour={tour:7.0f} "
              f"n={len(sites)} spec=({r1:.0f},{k1},{o1:.0f})/({r2:.0f},{k2},{o2:.0f})/({r3:.0f},{k3},{o3:.0f})")
    best.sort(key=lambda item: item[0])
    print("\nTop candidates by estimated cost:")
    for cost, gap, tour, n, spec in best[:8]:
        print(f"cost={cost:7.0f} gap={gap:6.2f} tour={tour:7.0f}m n={n} spec={spec}")

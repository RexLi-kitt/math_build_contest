"""Fine audit + local refinement of the 28-site certified candidate."""
from __future__ import annotations

import itertools
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


BASE = ((987.565, 5, 30.584), (1291.032, 10, 10.454), (1934.417, 12, 0.829))


def audit(spec, r_step=10.0, t_step=0.5):
    gap, wx = certify(build(spec), r_step=r_step, t_step=t_step)
    return gap, wx


if __name__ == "__main__":
    gap, wx = audit(BASE)
    print(f"BASE fine gap={gap:.2f} worst=({wx[0]:.0f},{wx[1]:.0f})")

    rng = random.Random(7)
    r1, k1, o1 = BASE[0]
    r2, k2, o2 = BASE[1]
    r3, k3, o3 = BASE[2]
    results = []
    for trial in range(120):
        spec = ((r1 + rng.uniform(-30, 30), k1, o1 + rng.uniform(-12, 12)),
                (r2 + rng.uniform(-40, 40), k2, o2 + rng.uniform(-18, 18)),
                (r3 + rng.uniform(-40, 40), k3, o3 + rng.uniform(-15, 15)))
        gap, _ = certify(build(spec), r_step=40.0, t_step=3.0)
        if gap > 173.0:
            continue
        fine, _ = certify(build(spec), r_step=15.0, t_step=0.75)
        if fine > 177.0:
            continue
        _order, tour = solve_tour(build(spec)[1:], restarts=8)
        results.append((tour, fine, spec))
        print(f"trial {trial:>3}: tour={tour:7.0f} fine={fine:6.2f} spec="
              f"({spec[0][0]:.0f},{spec[0][1]},{spec[0][2]:.1f})/"
              f"({spec[1][0]:.0f},{spec[1][1]},{spec[1][2]:.1f})/"
              f"({spec[2][0]:.0f},{spec[2][1]},{spec[2][2]:.1f})")
    results.sort()
    print("\nBest:")
    for tour, fine, spec in results[:6]:
        print(f"tour={tour:7.0f}m ({tour/5:.0f}s) gap={fine:6.2f} spec={spec}")

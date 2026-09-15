"""Optimize certified 4-ring sweep designs: minimize tour subject to the surround gap."""
from __future__ import annotations

import itertools
import sys

sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")
from certify import certify, ring, tour_length


def build(spec):
    sites = [(0.0, 0.0)]
    for radius, count, offset in spec:
        sites.extend(ring(radius, count, offset))
    return sites


def score(spec, margin=175.0):
    sites = build(spec)
    gap, _ = certify(sites, r_step=60.0, t_step=4.0)
    if gap > margin:
        return None
    return gap, tour_length(sites)


if __name__ == "__main__":
    best = []
    radii1 = (850.0, 900.0, 950.0, 1000.0)
    radii2 = (1300.0, 1400.0, 1500.0)
    radii3 = (1800.0, 1900.0, 2000.0)
    radii4 = (2300.0, 2400.0, 2500.0)
    for r1, r2, r3, r4 in itertools.product(radii1, radii2, radii3, radii4):
        spec = ((r1, 8, 0.0), (r2, 8, 22.5), (r3, 8, 0.0), (r4, 8, 22.5))
        result = score(spec)
        if result is None:
            continue
        gap, tour = result
        best.append((tour, gap, spec))
    best.sort()
    print(f"{len(best)} certified designs")
    for tour, gap, spec in best[:12]:
        print(f"tour={tour:7.0f}m ({tour/5:5.0f}s) gap={gap:6.2f} spec={spec}")

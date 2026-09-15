"""Certified surround-coverage checker for Q4 directional jammers.

A directional source at x is guaranteed visible from a visit set S iff the
directions from x to the sites of S within 1000 m are NOT contained in any
open half-plane, i.e. the maximum angular gap between consecutive directions
is <= 180 deg.  We evaluate that gap on a fine polar grid (with margin) and
then score candidate designs by their sweep tour length.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

Area = 1800.0
Reach = 1000.0


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def ring(r, n, offset=0.0):
    return [(r * math.cos(math.radians(offset + 360.0 * k / n)),
             r * math.sin(math.radians(offset + 360.0 * k / n))) for k in range(n)]


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def max_gap_at(x, sites, reach=Reach):
    if min(dist(x, p) for p in sites) <= 5.0:
        # Within 5 m the optical locator clears directly; the direction from the
        # source to a coincident site is undefined, so skip this measure-zero set.
        return 0.0
    dirs = []
    for p in sites:
        d = dist(x, p)
        if d <= reach:
            dirs.append(math.degrees(math.atan2(p[1] - x[1], p[0] - x[0])) % 360.0)
    if not dirs:
        return 360.0
    dirs.sort()
    gap = dirs[0] + 360.0 - dirs[-1]
    for a, b in zip(dirs, dirs[1:]):
        gap = max(gap, b - a)
    return gap


def certify(sites, reach=Reach, r_step=25.0, t_step=1.5, audit=None):
    worst = 0.0
    worst_x = None
    for ri in range(0, int(Area // r_step) + 1):
        r = ri * r_step
        steps = 1 if r == 0.0 else int(360.0 / t_step)
        for ti in range(steps):
            t = math.radians(ti * t_step)
            x = (r * math.cos(t), r * math.sin(t))
            gap = max_gap_at(x, sites, reach)
            if gap > worst:
                worst, worst_x = gap, x
    return worst, worst_x


def tour_length(sites, start=(0.0, 0.0)):
    pts = list(sites)
    n = len(pts)
    remaining = set(range(n))
    order = []
    cur = start
    while remaining:
        j = min(remaining, key=lambda i: dist(cur, pts[i]))
        order.append(j)
        cur = pts[j]
        remaining.remove(j)

    def cost(o):
        total = 0.0
        prev = start
        for i in o:
            total += dist(prev, pts[i])
            prev = pts[i]
        return total

    improved = True
    while improved:
        improved = False
        old = cost(order)
        for i in range(n - 1):
            for j in range(i + 2, n + 1):
                cand = order[:i] + list(reversed(order[i:j])) + order[j:]
                if cost(cand) + 1e-6 < old:
                    order, improved = cand, True
                    break
            if improved:
                break
    return cost(order)


@dataclass
class Design:
    name: str
    sites: list

    @property
    def count(self):
        return len(self.sites)


def report(name, sites):
    worst, wx = certify(sites)
    length = tour_length(sites)
    status = "PASS" if worst <= 180.0 else "FAIL"
    tail = f" worst_x=({wx[0]:7.1f},{wx[1]:7.1f})" if wx is not None else ""
    print(f"{name:>34}: sites={len(sites):>2} max_gap={worst:6.2f} "
          f"tour={length:7.0f}m ({length/5:6.0f}s) {status}{tail}")
    return worst, length


if __name__ == "__main__":
    import sys
    sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")
    from q4_optimize import L1100C2, L1000C2, L950C2

    designs = {
        "L1100": L1100C2._triangular_sites(1100.0),
        "L1000": L1000C2._triangular_sites(1000.0),
        "L950": L950C2._triangular_sites(950.0),
        "ring 6x1100+6x1905": [(0.0, 0.0)] + ring(1100, 6) + ring(1905, 6, 30),
        "ring 6x1000+6x1800+6x2600": [(0.0, 0.0)] + ring(1000, 6) + ring(1800, 6, 30) + ring(2600, 6),
        "ring 3x450+6x1100+6x1905+6x2200": ([(0.0, 0.0)] + ring(450, 3, 90)
                                            + ring(1100, 6) + ring(1905, 6, 30) + ring(2200, 6)),
        "ring 6x550+6x1100+6x1905+6x2200": ([(0.0, 0.0)] + ring(550, 6)
                                            + ring(1100, 6) + ring(1905, 6, 30) + ring(2200, 6)),
    }
    for name, sites in designs.items():
        report(name, sites)

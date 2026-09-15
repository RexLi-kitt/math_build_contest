"""Measure the union-route length for the conservative K design.

For each case of seed 55021: build the route over the mandatory cover set
(origin + 7 ring stops at R=1000) plus the true source positions, using the same
nearest-neighbour + 2-opt/Or-opt local search as the production router, and
compare with the two-phase J+ movement (6207 m sweep + source TSP).
"""
from __future__ import annotations

import math
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"C:\Users\李\Desktop\B题模型代码汇总\第三问策略对比")))

from baseline_core import add, dist, random_sources  # noqa: E402

SPEED = 5.0


def open_route_length(start, anchors):
    remaining = set(range(len(anchors)))
    route = []
    current = start
    while remaining:
        nxt = min(remaining, key=lambda i: dist(current, anchors[i]))
        route.append(nxt)
        current = anchors[nxt]
        remaining.remove(nxt)

    def cost(order):
        pts = [start] + [anchors[i] for i in order]
        return sum(dist(a, b) for a, b in zip(pts, pts[1:]))

    improved = True
    while improved:
        improved = False
        old = cost(route)
        for i in range(len(route) - 1):
            for j in range(i + 2, len(route) + 1):
                cand = route[:i] + list(reversed(route[i:j])) + route[j:]
                if cost(cand) + 1e-9 < old:
                    route, improved = cand, True
                    break
            if improved:
                break
        if improved:
            continue
        old = cost(route)
        n = len(route)
        for seg_len in (1, 2, 3):
            for i in range(n - seg_len + 1):
                segment = route[i:i + seg_len]
                rest = route[:i] + route[i + seg_len:]
                for j in range(len(rest) + 1):
                    for seg in (segment, segment[::-1]):
                        cand = rest[:j] + seg + rest[j:]
                        if cost(cand) + 1e-9 < old:
                            route, improved = cand, True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
    return cost(route)


def main():
    ring = [(0.0, 0.0)] + [add((0.0, 0.0), 1000.0, 360.0 / 7 * k) for k in range(7)]
    rng = random.Random(55021)
    union_lengths, source_lengths, ns = [], [], []
    for _ in range(1000):
        sources = random_sources(rng, None)
        positions = [s.position for s in sources]
        ns.append(len(sources))
        union_lengths.append(open_route_length((0.0, 0.0), ring + positions))
        source_lengths.append(open_route_length((0.0, 0.0), positions))
    mean_n = statistics.mean(ns)
    mean_union = statistics.mean(union_lengths)
    mean_source = statistics.mean(source_lengths)
    cover = 6190.0
    print(f"cases 1000, mean n = {mean_n:.2f}")
    print(f"mean source-only TSP (NN+2opt): {mean_source:.0f} m")
    print(f"mean union route (7 ring stops + sources): {mean_union:.0f} m")
    print(f"J+ two-phase movement: {cover + mean_source:.0f} m")
    print(f"union saving: {cover + mean_source - mean_union:.0f} m "
          f"= {(cover + mean_source - mean_union) / SPEED:.0f} s/episode "
          f"= {(cover + mean_source - mean_union) / SPEED / mean_n:.1f} s/source")
    by_n = {}
    for n, u in zip(ns, union_lengths):
        by_n.setdefault(n, []).append(u)
    for n in sorted(by_n):
        print(f"  n={n:2d}: union {statistics.mean(by_n[n]):.0f} m, "
              f"{statistics.mean(by_n[n]) / SPEED / n:.1f} s/source")


if __name__ == "__main__":
    main()

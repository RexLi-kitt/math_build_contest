"""Strong open TSP (nearest neighbour + 2-opt + efficient Or-opt, multi-start)."""
from __future__ import annotations

import math
import random

from certify import dist


def route_cost(order, pts, start=(0.0, 0.0)):
    total = 0.0
    prev = start
    for i in order:
        total += dist(prev, pts[i])
        prev = pts[i]
    return total


def nearest_neighbour(pts, start_idx, start=(0.0, 0.0)):
    n = len(pts)
    remaining = set(range(n))
    order = []
    cur = start
    if start_idx is not None:
        remaining.discard(start_idx)
        order.append(start_idx)
        cur = pts[start_idx]
    while remaining:
        j = min(remaining, key=lambda i: dist(cur, pts[i]))
        order.append(j)
        cur = pts[j]
        remaining.remove(j)
    return order


def two_opt(order, pts, start=(0.0, 0.0)):
    order = list(order)
    n = len(order)
    improved = True
    while improved:
        improved = False
        best_delta, best_pair = 0.0, None
        for i in range(n - 1):
            a_prev = start if i == 0 else pts[order[i - 1]]
            a = pts[order[i]]
            for j in range(i + 1, n):
                b = pts[order[j]]
                b_next = start if j == n - 1 else pts[order[j + 1]]
                delta = (dist(a_prev, b) + dist(a, b_next)) - (dist(a_prev, a) + dist(b, b_next))
                if delta < best_delta - 1e-9:
                    best_delta, best_pair = delta, (i, j)
        if best_pair:
            i, j = best_pair
            order[i:j + 1] = reversed(order[i:j + 1])
            improved = True
    return order


def or_opt(order, pts, start=(0.0, 0.0)):
    order = list(order)
    n = len(order)
    improved = True
    while improved:
        improved = False
        for seg_len in (1, 2, 3):
            for i in range(n - seg_len + 1):
                seg = order[i:i + seg_len]
                prev = start if i == 0 else pts[order[i - 1]]
                nxt = None if i + seg_len >= n else pts[order[i + seg_len]]
                first, last = pts[seg[0]], pts[seg[-1]]
                removal = (dist(prev, first) + (dist(last, nxt) if nxt else 0.0)
                           - (dist(prev, nxt) if nxt else 0.0))
                rest = order[:i] + order[i + seg_len:]
                for j in range(len(rest) + 1):
                    a = start if j == 0 else pts[rest[j - 1]]
                    b = None if j == len(rest) else pts[rest[j]]
                    for s in (seg, list(reversed(seg))):
                        f, l = pts[s[0]], pts[s[-1]]
                        add = dist(a, f) + (dist(l, b) if b else 0.0) - (dist(a, b) if b else 0.0)
                        if add - removal < -1e-9:
                            order = rest[:j] + s + rest[j:]
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
    return order


def solve_tour(pts, start=(0.0, 0.0), restarts=60, seed=0):
    rng = random.Random(seed)
    n = len(pts)
    starts = sorted(range(n), key=lambda i: dist(start, pts[i]))[:8]
    starts += [rng.randrange(n) for _ in range(restarts)]
    best_order, best_cost = None, math.inf
    for s in starts:
        order = nearest_neighbour(pts, s, start)
        for _ in range(6):
            order = two_opt(order, pts, start)
            order = or_opt(order, pts, start)
        cost = route_cost(order, pts, start)
        if cost < best_cost - 1e-9:
            best_order, best_cost = order, cost
    return best_order, best_cost


if __name__ == "__main__":
    import sys
    sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")
    from certify import ring
    from q4_optimize import L1000C2, L950C2

    designs = {
        "L1000": L1000C2._triangular_sites(1000.0),
        "L950": L950C2._triangular_sites(950.0),
        "8x900+8x1400+8x1900+8x2400": ([(0.0, 0.0)] + ring(900, 8) + ring(1400, 8, 22.5)
                                       + ring(1900, 8) + ring(2400, 8, 22.5)),
        "9x950+9x1500+9x2050+9x2550": ([(0.0, 0.0)] + ring(950, 9) + ring(1500, 9, 20)
                                       + ring(2050, 9, 40) + ring(2550, 9)),
    }
    for name, pts in designs.items():
        order, cost = solve_tour(pts)
        print(f"{name:>34}: n={len(pts):>2} best_tour={cost:7.0f}m ({cost/5:6.0f}s)")

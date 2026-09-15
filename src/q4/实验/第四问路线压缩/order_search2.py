"""顺序搜索 v2: 边界加权覆盖目标, 兼顾正常/压力两个场景。

权重 w(x) = 1 + alpha * (r/1800)^4; alpha=0 退化为纯覆盖, alpha 越大越优先
覆盖边界带(压力场景的源都在 r in [1700,1800] 且朝外, 需要外圈站早到)。
证书与顺序无关, 重排零风险。
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

EXP = r"C:\Users\李\Desktop\第四问定向源实验"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, EXP)

from strong_tsp import route_cost  # noqa: E402

S_EST = 13.0
MEASURE_S = 5.0
GRID_STEP = 50.0

data = json.loads((HERE / "winner_design.json").read_text(encoding="utf-8"))
sites = [tuple(p) for p in data["sites"]]
tsp_order = list(data["order"])

xs = np.arange(-1800.0, 1800.0 + GRID_STEP, GRID_STEP)
X, Y = np.meshgrid(xs, xs)
inside = (X ** 2 + Y ** 2) <= 1800.0 ** 2
cells = np.stack([X[inside], Y[inside]], axis=1)
r_cells = np.hypot(cells[:, 0], cells[:, 1])
n_cells = cells.shape[0]

cover_masks = []
for p in sites:
    d2 = (cells[:, 0] - p[0]) ** 2 + (cells[:, 1] - p[1]) ** 2
    cover_masks.append(d2 <= 1000.0 ** 2)


def make_weights(alpha):
    w = 1.0 + alpha * (r_cells / 1800.0) ** 4
    return w / w.sum()


def tour_of(order):
    pts = [sites[i] for i in order]
    return route_cost(list(range(len(pts))), pts)


def make_objective(weights):
    def objective(order):
        covered = np.zeros(n_cells, dtype=bool)
        total = 0.0
        for i in order:
            covered |= cover_masks[i]
            total += 1.0 - weights[covered].sum()
        return tour_of(order) / 5.0 + MEASURE_S * S_EST * total
    return objective


def two_opt_or_opt(order, objective, max_passes=300):
    order = list(order)
    best = objective(order)
    for _ in range(max_passes):
        improved = False
        n = len(order)
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                cand = order[:i] + list(reversed(order[i:j + 1])) + order[j + 1:]
                val = objective(cand)
                if val < best - 1e-6:
                    order, best, improved = cand, val, True
                    break
            if improved:
                break
        if improved:
            continue
        for i in range(1, n):
            for j in range(1, n):
                if j == i:
                    continue
                rest = order[:i] + order[i + 1:]
                cand = rest[:j] + [order[i]] + rest[j:]
                val = objective(cand)
                if val < best - 1e-6:
                    order, best, improved = cand, val, True
                    break
            if improved:
                break
        if not improved:
            break
    assert sorted(order) == list(range(len(order))), "排列被破坏"
    return order, best


def greedy(weights, max_per_distance=True):
    remaining = set(range(len(sites)))
    order, covered, pos = [], np.zeros(n_cells, dtype=bool), (0.0, 0.0)
    while remaining:
        best, best_key = None, -math.inf
        for i in remaining:
            new = weights[~covered & cover_masks[i]].sum()
            d = max(math.dist(pos, sites[i]), 1.0)
            key = new / d if max_per_distance else new
            if key > best_key:
                best, best_key = i, key
        order.append(best)
        covered |= cover_masks[best]
        pos = sites[best]
        remaining.remove(best)
    return order


out = {}
for alpha in (0.0, 1.0, 3.0):
    weights = make_weights(alpha)
    objective = make_objective(weights)
    seeds = [tsp_order, greedy(weights, True), greedy(weights, False)]
    best_order, best_val = None, math.inf
    for seed in seeds:
        o, v = two_opt_or_opt(seed, objective)
        if v < best_val:
            best_order, best_val = o, v
    name = f"mix_a{alpha:g}"
    out[name] = {"order": best_order, "tour_m": tour_of(best_order),
                 "objective": best_val, "alpha": alpha}
    print(f"{name:>9}: tour={tour_of(best_order):7.0f}m J={best_val:7.0f}")

(HERE / "order_variants2.json").write_text(json.dumps(out, indent=2),
                                           encoding="utf-8")
print("saved order_variants2.json")

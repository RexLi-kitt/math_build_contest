"""站点顺序优化: 最短巡游 vs 覆盖发现延迟 的加权权衡。

检测成本 ∝ 每站未发现频道数, 未发现源越早被发现越省。用 1000m 圆盘覆盖
近似发现过程(全向代理), 目标:
    J = tour/5 + 5 * S_est * sum_k (1 - c_k)
其中 c_k = 前 k 站 1000m 圆盘并集覆盖的圆域面积比例, S_est=13。
证书只依赖站点集合, 与顺序无关, 因此重排零风险。
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
n_cells = cells.shape[0]
print(f"覆盖网格: {n_cells} 格 (步长 {GRID_STEP:.0f}m)")

cover_masks = []
for p in sites:
    d2 = (cells[:, 0] - p[0]) ** 2 + (cells[:, 1] - p[1]) ** 2
    cover_masks.append(d2 <= 1000.0 ** 2)


def uncovered_sum(order):
    covered = np.zeros(n_cells, dtype=bool)
    total = 0.0
    for i in order:
        covered |= cover_masks[i]
        total += 1.0 - covered.mean()
    return total


def tour_of(order):
    pts = [sites[i] for i in order]
    return route_cost(list(range(len(pts))), pts)


def objective(order):
    return tour_of(order) / 5.0 + MEASURE_S * S_EST * uncovered_sum(order)


def two_opt_or_opt(order, max_passes=300):
    """第一改进下降; 每接受一步立即重算, 保证排列合法。"""
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


def greedy(max_per_distance=True):
    remaining = set(range(len(sites)))
    order, covered, pos = [], np.zeros(n_cells, dtype=bool), (0.0, 0.0)
    while remaining:
        best, best_key = None, -math.inf
        for i in remaining:
            new = (~covered & cover_masks[i]).sum()
            d = max(math.dist(pos, sites[i]), 1.0)
            key = new / d if max_per_distance else new
            if key > best_key:
                best, best_key = i, key
        order.append(best)
        covered |= cover_masks[best]
        pos = sites[best]
        remaining.remove(best)
    return order


variants = {}
for name, seed in (("tsp", tsp_order),
                   ("greedy_dens", greedy(True)),
                   ("greedy_area", greedy(False))):
    o, v = two_opt_or_opt(seed)
    variants[name] = (o, v)

print(f"\n{'变体':>12} {'巡游(m)':>9} {'未覆盖和':>9} {'目标J(s)':>9} {'vs TSP':>9}")
base_j = objective(tsp_order)
for name, (o, v) in variants.items():
    t = tour_of(o)
    u = uncovered_sum(o)
    print(f"{name:>12} {t:9.0f} {u:9.2f} {v:9.0f} {v - base_j:+9.0f}")

out = {}
for name, (o, v) in variants.items():
    out[name] = {"order": o, "tour_m": tour_of(o),
                 "uncovered_sum": uncovered_sum(o), "objective": v}
(HERE / "order_variants.json").write_text(json.dumps(out, indent=2),
                                          encoding="utf-8")
print("\nsaved order_variants.json")

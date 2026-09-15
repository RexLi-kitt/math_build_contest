"""设计+顺序联合优化工具: 校准过的端到端代理目标。

目标(单位 s/局):
    J = tour(order)/5 + 60*n + 78*uncovered_sum(order)
校准: B+ (n=27, tour=20850, uncovered=3.61) -> J=6072 s/局, 加后段
(搜索后移动+清除) 8552/12.9=663 s/源 vs 实测 654.85, 误差 1%。
其中 60 = 6s*7空频道 + 18s 共观测/站; 78 = 6s*13源。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")
from strong_tsp import route_cost  # noqa: E402

GRID_STEP = 50.0
S_EST = 13.0
E_EST = 7.0
MEASURE_S = 6.0
COOB_PER_SITE = 18.0

xs = np.arange(-1800.0, 1800.0 + GRID_STEP, GRID_STEP)
_X, _Y = np.meshgrid(xs, xs)
_inside = (_X ** 2 + _Y ** 2) <= 1800.0 ** 2
CELLS = np.stack([_X[_inside], _Y[_inside]], axis=1)
N_CELLS = CELLS.shape[0]
COVER_R2 = 1000.0 ** 2


def make_masks(sites):
    masks = []
    for p in sites:
        d2 = (CELLS[:, 0] - p[0]) ** 2 + (CELLS[:, 1] - p[1]) ** 2
        masks.append(d2 <= COVER_R2)
    return masks


def uncovered_sum(order, masks):
    covered = np.zeros(N_CELLS, dtype=bool)
    total = 0.0
    for i in order:
        covered |= masks[i]
        total += 1.0 - covered.mean()
    return total


def greedy_order(masks, sites):
    remaining = set(range(len(sites)))
    order, covered, pos = [], np.zeros(N_CELLS, dtype=bool), (0.0, 0.0)
    while remaining:
        best, best_key = None, -math.inf
        for i in remaining:
            new = (~covered & masks[i]).sum()
            d = max(math.dist(pos, sites[i]), 1.0)
            key = new / d
            if key > best_key:
                best, best_key = i, key
        order.append(best)
        covered |= masks[best]
        pos = sites[best]
        remaining.remove(best)
    return order


def order_objective(order, masks, tour):
    return tour / 5.0 + MEASURE_S * S_EST * uncovered_sum(order, masks)


def refine_order(order, masks, sites, max_passes=300):
    """对固定设计做顺序局部搜索, 目标 = tour/5 + 78*uncovered_sum。"""
    from strong_tsp import route_cost

    order = list(order)
    best = order_objective(order, masks, route_cost(order, sites))
    for _ in range(max_passes):
        improved = False
        n = len(order)
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                cand = order[:i] + list(reversed(order[i:j + 1])) + order[j + 1:]
                val = order_objective(cand, masks, route_cost(cand, sites))
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
                val = order_objective(cand, masks, route_cost(cand, sites))
                if val < best - 1e-6:
                    order, best, improved = cand, val, True
                    break
            if improved:
                break
        if not improved:
            break
    assert sorted(order) == list(range(len(order))), "排列被破坏"
    return order, best


def joint_J(sites, order, masks):
    from strong_tsp import route_cost

    tour = route_cost(order, sites)
    n = len(sites)
    return (tour / 5.0 + (MEASURE_S * E_EST + COOB_PER_SITE) * n
            + MEASURE_S * S_EST * uncovered_sum(order, masks))


def evaluate_design(sites):
    """快速评估: 贪心覆盖顺序 + 联合目标。返回 (J, tour, uncovered, order)。"""
    from strong_tsp import route_cost

    masks = make_masks(sites)
    order = greedy_order(masks, sites)
    tour = route_cost(order, sites)
    unc = uncovered_sum(order, masks)
    J = tour / 5.0 + (MEASURE_S * E_EST + COOB_PER_SITE) * len(sites) + MEASURE_S * S_EST * unc
    return J, tour, unc, order

"""顺序搜索 v3: 压力感知代理 (外向半平面) + 正常覆盖 的联合目标。

压力场景: 12/16 源在 r∈[1700,1800] 且波束径向朝外。源 x 被站 p 发现需
|p-x|<=1000 且 (p-x)·x_hat >= 0 (站位于 x 的外向半平面)。其余 4/16 全向。
联合目标: J = tour/5 + 5*13*(unc_norm + w_s * unc_stress), 扫描 w_s。
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
STRESS_R = 1700.0
STRESS_DIR_FRACTION = 0.75

data = json.loads((HERE / "winner_design.json").read_text(encoding="utf-8"))
sites = [tuple(p) for p in data["sites"]]
tsp_order = list(data["order"])

xs = np.arange(-1800.0, 1800.0 + GRID_STEP, GRID_STEP)
X, Y = np.meshgrid(xs, xs)
inside = (X ** 2 + Y ** 2) <= 1800.0 ** 2
cells = np.stack([X[inside], Y[inside]], axis=1)
r_cells = np.hypot(cells[:, 0], cells[:, 1])
n_cells = cells.shape[0]
is_stress = r_cells >= STRESS_R
x_hat = cells / np.maximum(r_cells, 1e-9)[:, None]

cover_masks = []
stress_masks = []
for p in sites:
    d2 = (cells[:, 0] - p[0]) ** 2 + (cells[:, 1] - p[1]) ** 2
    omni = d2 <= 1000.0 ** 2
    cover_masks.append(omni)
    outward = ((cells[:, 0] - p[0]) * x_hat[:, 0]
               + (cells[:, 1] - p[1]) * x_hat[:, 1]) >= 0.0
    stress_masks.append(omni & (outward | ~is_stress))

n_norm = (~is_stress).sum()
n_stress = is_stress.sum()
print(f"网格: 内部 {n_norm} 格, 压力带 {n_stress} 格")


def tour_of(order):
    pts = [sites[i] for i in order]
    return route_cost(list(range(len(pts))), pts)


def make_objective(w_s):
    def objective(order):
        cov_n = np.zeros(n_cells, dtype=bool)
        cov_s = np.zeros(n_cells, dtype=bool)
        total_n = total_s = 0.0
        for i in order:
            cov_n |= cover_masks[i]
            cov_s |= stress_masks[i]
            total_n += 1.0 - cov_n[~is_stress].mean()
            total_s += 1.0 - cov_s[is_stress].mean()
        return (tour_of(order) / 5.0
                + MEASURE_S * S_EST * (total_n + w_s * total_s))
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


def greedy(objective_weights):
    """密度贪心: 新覆盖/距离, 覆盖按联合权重计。"""
    def value(i, covered_n, covered_s):
        new_n = (~covered_n & cover_masks[i])[~is_stress].sum() / n_norm
        new_s = (~covered_s & stress_masks[i])[is_stress].sum() / n_stress
        return new_n + objective_weights * new_s

    remaining = set(range(len(sites)))
    order, cn, cs, pos = [], np.zeros(n_cells, dtype=bool), np.zeros(n_cells, dtype=bool), (0.0, 0.0)
    while remaining:
        best, best_key = None, -math.inf
        for i in remaining:
            d = max(math.dist(pos, sites[i]), 1.0)
            key = value(i, cn, cs) / d
            if key > best_key:
                best, best_key = i, key
        order.append(best)
        cn |= cover_masks[best]
        cs |= stress_masks[best]
        pos = sites[best]
        remaining.remove(best)
    return order


out = {}
for w_s in (0.5, 1.0, 2.0):
    objective = make_objective(w_s)
    best_order, best_val = None, math.inf
    for seed in (tsp_order, greedy(w_s)):
        o, v = two_opt_or_opt(seed, objective)
        if v < best_val:
            best_order, best_val = o, v
    name = f"mixb_w{w_s:g}"
    out[name] = {"order": best_order, "tour_m": tour_of(best_order),
                 "objective": best_val, "w_s": w_s}
    print(f"{name:>9}: tour={tour_of(best_order):7.0f}m J={best_val:7.0f}")

(HERE / "order_variants3.json").write_text(json.dumps(out, indent=2),
                                           encoding="utf-8")
print("saved order_variants3.json")

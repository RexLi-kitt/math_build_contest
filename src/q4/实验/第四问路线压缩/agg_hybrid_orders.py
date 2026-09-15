"""激进设计的外圈优先混合顺序: 先扫 k 个外圈站, 再覆盖优先。"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(r"C:\Users\李\Desktop\第四问路线压缩")
sys.path.insert(0, str(HERE))

from joint_tools import (greedy_order, make_masks, joint_J,  # noqa: E402
                         uncovered_sum)
from strong_tsp import route_cost  # noqa: E402

ev = json.loads((HERE / "joint_eval_results.json").read_text(encoding="utf-8"))
by = {r["name"]: r for r in ev}
agg = by["aggressive"]
sites = [tuple(p) for p in agg["sites"]]
masks = make_masks(sites)

outer = sorted([i for i in range(len(sites)) if math.hypot(*sites[i]) >= 1780],
               key=lambda i: math.hypot(*sites[i]))
inner = [i for i in range(len(sites)) if i not in outer]


def nn_seq(pool, start):
    remaining = set(pool)
    order, pos = [], start
    while remaining:
        j = min(remaining, key=lambda i: math.dist(pos, sites[i]))
        order.append(j)
        pos = sites[j]
        remaining.remove(j)
    return order


def hybrid(k):
    first = nn_seq(outer, (0.0, 0.0))[:k]
    rest_pool = [i for i in range(len(sites)) if i not in first]
    pos = sites[first[-1]] if first else (0.0, 0.0)
    rest_masks = masks
    remaining = set(rest_pool)
    covered = np.zeros_like(masks[0])
    for i in first:
        covered |= masks[i]
    order = list(first)
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


import numpy as np  # noqa: E402

out = {}
for k in (4, 8, 15):
    order = hybrid(k)
    assert sorted(order) == list(range(len(sites)))
    tour = route_cost(order, sites)
    unc = uncovered_sum(order, masks)
    J = joint_J(sites, order, masks)
    out[f"agg_h{k}"] = {"order": order, "tour_m": tour, "unc": unc, "J": J}
    print(f"agg_h{k}: tour={tour:7.0f} unc={unc:5.2f} J={J:7.0f}")

# 纯覆盖顺序做对照
order0 = greedy_order(masks, sites)
print(f"greedy : tour={route_cost(order0, sites):7.0f} "
      f"unc={uncovered_sum(order0, masks):5.2f} "
      f"J={joint_J(sites, order0, masks):7.0f}")

(HERE / "order_variants5.json").write_text(json.dumps(out, indent=2),
                                           encoding="utf-8")
print("saved order_variants5.json")

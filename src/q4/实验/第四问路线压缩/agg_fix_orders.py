"""AggOrder 压力修复变体: 把 k 个角向均匀的外圈站挪到顺序最前。"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(r"C:\Users\李\Desktop\第四问路线压缩")
sys.path.insert(0, str(HERE))

from joint_tools import make_masks, uncovered_sum, joint_J  # noqa: E402
from strong_tsp import route_cost  # noqa: E402

ev = json.loads((HERE / "joint_eval_results.json").read_text(encoding="utf-8"))
by = {r["name"]: r for r in ev}
agg = by["aggressive"]
sites = [tuple(p) for p in agg["sites"]]
base_order = list(agg["order"])
masks = make_masks(sites)

outer = [i for i in range(len(sites)) if math.hypot(*sites[i]) >= 1780]
outer_sorted = sorted(outer, key=lambda i: math.atan2(sites[i][1], sites[i][0]))


def pick_spread(k):
    m = len(outer_sorted)
    return [outer_sorted[round(j * m / k) % m] for j in range(k)]


def nn_seq(pool, start):
    remaining = set(pool)
    order, pos = [], start
    while remaining:
        j = min(remaining, key=lambda i: math.dist(pos, sites[i]))
        order.append(j)
        pos = sites[j]
        remaining.remove(j)
    return order


out = {}
for k in (4, 8):
    front = nn_seq(pick_spread(k), (0.0, 0.0))
    order = front + [i for i in base_order if i not in front]
    assert sorted(order) == list(range(len(sites)))
    tour = route_cost(order, sites)
    unc = uncovered_sum(order, masks)
    J = joint_J(sites, order, masks)
    out[f"agg_fix{k}"] = {"order": order, "tour_m": tour, "unc": unc, "J": J}
    print(f"agg_fix{k}: tour={tour:7.0f} unc={unc:5.2f} J={J:7.0f} "
          f"front_r={[round(math.hypot(*sites[i])) for i in front]}")

(HERE / "order_variants6.json").write_text(json.dumps(out, indent=2),
                                           encoding="utf-8")
print("saved order_variants6.json")

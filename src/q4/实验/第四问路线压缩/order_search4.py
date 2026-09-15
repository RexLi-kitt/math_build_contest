"""顺序搜索 v4: 手工构造 外圈优先 / 内外交替, 直接兼顾两个场景。"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

EXP = r"C:\Users\李\Desktop\第四问定向源实验"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, EXP)

from strong_tsp import route_cost  # noqa: E402

data = json.loads((HERE / "winner_design.json").read_text(encoding="utf-8"))
sites = [tuple(p) for p in data["sites"]]
r_sites = [math.hypot(*p) for p in sites]
n = len(sites)

outer = sorted([i for i in range(n) if r_sites[i] >= 1780],
               key=lambda i: -r_sites[i])
inner = [i for i in range(n) if i not in outer]
print(f"外圈站(r>=1780): {len(outer)} 个, 其余 {len(inner)} 个")


def nn_order(pool, start=(0.0, 0.0)):
    remaining = set(pool)
    order, pos = [], start
    while remaining:
        j = min(remaining, key=lambda i: math.dist(pos, sites[i]))
        order.append(j)
        pos = sites[j]
        remaining.remove(j)
    return order


def tour_of(order):
    pts = [sites[i] for i in order]
    return route_cost(list(range(len(pts))), pts)


variants = {}
# 外圈优先: 先按最近邻扫外圈, 再按最近邻扫其余
variants["outer_first"] = nn_order(outer) + nn_order(inner, sites[nn_order(outer)[-1]])
# 内外交替: 轮流取最近的外圈/内圈站
order, remaining_o, remaining_i, pos = [], set(outer), set(inner), (0.0, 0.0)
turn_outer = True
while remaining_o or remaining_i:
    pool = remaining_o if (turn_outer and remaining_o) else (remaining_i or remaining_o)
    j = min(pool, key=lambda i: math.dist(pos, sites[i]))
    order.append(j)
    (remaining_o if j in remaining_o else remaining_i).discard(j)
    pos = sites[j]
    turn_outer = not turn_outer
variants["alternating"] = order

for name, order in variants.items():
    assert sorted(order) == list(range(n))
    print(f"{name:>12}: tour={tour_of(order):7.0f}m")

(HERE / "order_variants4.json").write_text(
    json.dumps({k: {"order": v, "tour_m": tour_of(v)} for k, v in variants.items()},
               indent=2), encoding="utf-8")
print("saved order_variants4.json")

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")
from strong_tsp import solve_tour  # noqa: E402

HERE = Path(r"C:\Users\李\Desktop\第四问路线压缩")
data = json.loads((HERE / "winner_design.json").read_text(encoding="utf-8"))
sites = [tuple(p) for p in data["sites"]]
json_order = list(data["order"])
variants = json.loads((HERE / "order_variants.json").read_text(encoding="utf-8"))


def indep_tour(order):
    prev = (0.0, 0.0)
    total = 0.0
    for i in order:
        total += math.dist(prev, sites[i])
        prev = sites[i]
    return total


print("JSON order 巡游(独立复算):", round(indep_tour(json_order), 1),
      " json tour_m:", round(data["tour_m"], 1))
for name, v in variants.items():
    print(f"{name:>12} 巡游(独立复算): {indep_tour(v['order']):.1f}  "
          f"首站={sites[v['order'][0]]}  末站={sites[v['order'][-1]]}")

order2, cost2 = solve_tour(sites, restarts=200)
print("重新 solve_tour(restarts=200):", round(cost2, 1),
      " 与JSON order 相同?", list(order2) == json_order)
print("JSON order 站点数:", len(json_order), "唯一:", len(set(json_order)))
print("sites 数:", len(sites))

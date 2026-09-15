import json
import math
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")
from strong_tsp import solve_tour, two_opt, or_opt, route_cost  # noqa: E402

HERE = Path(r"C:\Users\李\Desktop\第四问路线压缩")
data = json.loads((HERE / "winner_design.json").read_text(encoding="utf-8"))
sites = [tuple(p) for p in data["sites"]]
variants = json.loads((HERE / "order_variants.json").read_text(encoding="utf-8"))
g = list(variants["greedy_area"]["order"])

print("greedy_area 排列合法:", sorted(g) == list(range(len(sites))))
print("坐标是否含重复:", len(set(sites)) != len(sites))


def legs(order):
    prev = (0.0, 0.0)
    out = []
    for i in order:
        out.append((prev, sites[i], math.dist(prev, sites[i])))
        prev = sites[i]
    return out


ls = legs(g)
big = [l for l in ls if l[2] > 1500]
print(f"greedy_area 中 >1500m 的腿: {len(big)} 条")
for a, b, d in big:
    print(f"  {a} -> {b}: {d:.0f}m")

# 用 strong_tsp 的 2-opt / Or-opt 从该顺序继续优化, 看是否能再降
order = list(range(len(sites)))
pts = [sites[i] for i in g]
o = list(range(len(pts)))
o2 = two_opt(o, pts)
o2 = or_opt(o2, pts)
print("strong 2opt+oropt 后:", round(route_cost(o2, pts), 1))

# 更多 restarts 的 solve_tour
for r in (500, 2000):
    _, c = solve_tour(sites, restarts=r)
    print(f"solve_tour(restarts={r}): {c:.1f}")

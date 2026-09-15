"""检查 B 与 C 的站点集是否有公共子集，判断"共享前缀 + 分叉"是否可行。

若存在公共前缀 S，使得 S∪(B\\S)=B 证书、S∪(C\\S)=C 证书，则可以先走 S 做探测，
再决定走 B 的余下站点还是 C 的余下站点，且两个分支都保持 100% 覆盖证书。
"""
from __future__ import annotations

import json
from pathlib import Path

MODELS = Path(r"C:\Users\李\Desktop\Q4保底基线")


def load(name):
    data = json.loads((MODELS / name / "winner_design.json").read_text(encoding="utf-8"))
    sites = [tuple(point) for point in data["sites"]]
    order = [sites[index] for index in data["order"]]
    return data, sites, order


bdata, bsites, border = load("B模型")
cdata, csites, corder = load("C模型")

key = lambda p: (round(p[0], 3), round(p[1], 3))
bset = {key(p) for p in bsites}
cset = {key(p) for p in csites}
shared = bset & cset

print(f"B: {len(bsites)} 站  tour={bdata.get('tour_m')}  gap={bdata.get('gap_grid_5_025')}")
print(f"C: {len(csites)} 站  tour={cdata.get('tour_m')}  gap={cdata.get('gap_grid_5_025')}")
print(f"公共站点: {len(shared)}")
print(f"B 独有: {len(bset - cset)}   C 独有: {len(cset - bset)}")

print("\nB 路线顺序（标 * 为公共站）:")
for index, point in enumerate(border):
    print(f"  {index:>2} {'*' if key(point) in shared else ' '} ({point[0]:>9.2f},{point[1]:>9.2f})")

print("\nC 路线顺序（标 * 为公共站）:")
for index, point in enumerate(corder):
    print(f"  {index:>2} {'*' if key(point) in shared else ' '} ({point[0]:>9.2f},{point[1]:>9.2f})")

# 公共站在两条路线中的名次分布
brank = {key(p): i for i, p in enumerate(border)}
crank = {key(p): i for i, p in enumerate(corder)}
print("\n公共站在各自路线中的名次:")
for point in sorted(shared, key=lambda p: (brank[p], crank[p])):
    print(f"  ({point[0]:>9.2f},{point[1]:>9.2f})  B#{brank[point]:>2}  C#{crank[point]:>2}")

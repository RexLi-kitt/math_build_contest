"""检查 AggOrder 顺序结构: 外圈站在顺序中的位置。"""
import json
import math
from pathlib import Path

HERE = Path(r"C:\Users\李\Desktop\第四问路线压缩")
ev = json.loads((HERE / "joint_eval_results.json").read_text(encoding="utf-8"))
by = {r["name"]: r for r in ev}

for name in ("aggressive", "B_winner"):
    r = by[name]
    sites = [tuple(p) for p in r["sites"]]
    order = list(r["order"])
    radii = [round(math.hypot(*sites[i])) for i in order]
    outer_pos = [k for k, i in enumerate(order, 1)
                 if math.hypot(*sites[i]) >= 1780]
    print(f"== {name} (n={len(sites)}, tour={r['tour_refined']:.0f}) ==")
    print("  顺序半径:", radii)
    print(f"  外圈站(r>=1780): {len(outer_pos)} 个, 在顺序中的位置: {outer_pos}")

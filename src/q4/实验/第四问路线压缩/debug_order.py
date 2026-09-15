import json
import math
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\李\Desktop\第四问路线压缩")
sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")

import order_search as os

g0 = os.greedy(False)
print("greedy_area 未优化前合法:", sorted(g0) == list(range(len(os.sites))))

o = list(g0)
# 复刻 two_opt_or_opt 的循环, 逐步检查
n = len(o)
best = os.objective(o)
for it in range(3):
    changed = False
    for i in range(1, n - 1):
        for j in range(i + 1, n):
            cand = o[:i] + list(reversed(o[i:j + 1])) + o[j + 1:]
            assert sorted(cand) == list(range(n)), f"2opt broke perm at i={i} j={j}"
            val = os.objective(cand)
            if val < best - 1e-6:
                o, best, changed = cand, val, True
    for i in range(1, n):
        rest = o[:i] + o[i + 1:]
        for j in range(1, n):
            cand = rest[:j] + [o[i]] + rest[j:]
            if sorted(cand) != list(range(n)):
                print(f"Or-opt 破坏排列: i={i} j={j} len(cand)={len(cand)}")
                dup = [x for x in set(cand) if cand.count(x) > 1]
                miss = set(range(n)) - set(cand)
                print("  重复:", dup, "缺失:", miss)
                raise SystemExit(1)
            val = os.objective(cand)
            if val < best - 1e-6:
                o, best, changed = cand, val, True
    print(f"pass {it}: changed={changed} perm_ok={sorted(o) == list(range(n))}")
    if not changed:
        break

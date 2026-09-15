"""迭代 3 配对差分析: 同案例上 Extra450/Extra700 相对 Base 的每源差值。"""
import csv
import statistics
from pathlib import Path

path = Path(r"C:\Users\李\Desktop\第四问路线压缩\results\iter3_screen100\case_results.csv")
rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
by_case = {}
for r in rows:
    by_case.setdefault(r["case"], {})[r["strategy"]] = (
        float(r["total_virtual_time_s"]) / float(r["source_count"]))

for strat in ("Extra450", "Extra700"):
    diffs = [v[strat] - v["Base"] for v in by_case.values() if strat in v]
    n = len(diffs)
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    se = sd / (n ** 0.5)
    wins = sum(d < 0 for d in diffs)
    print(f"{strat} vs Base: n={n} 均值差={mean:+.2f} s/源 "
          f"标准差={sd:.2f} 标准误={se:.2f} "
          f"95%CI=[{mean - 1.96 * se:+.2f}, {mean + 1.96 * se:+.2f}] "
          f"胜率={wins}/{n}")

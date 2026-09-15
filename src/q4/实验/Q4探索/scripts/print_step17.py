"""把源数区间报告打印成紧凑表格。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
path = Path(r"c:\Users\李\.trae-cn\work\6aa56502e5f93f31529a14bc\q4x"
            r"\step17_source_count\source_count_report.json")
data = json.loads(path.read_text(encoding="utf-8"))
print(f"{'源数':>4}{'场景':>18}{'C+3F':>9}{'C+3FB':>9}{'B':>9}"
      f"{'C+3FB总时长':>12}{'配对差':>9}{'95%CI':>18}{'胜率':>8}{'清除':>8}")
for key, item in sorted(data.items(), key=lambda kv: (kv[1]["sources"], kv[1]["kind"])):
    paired = item["paired_3fb_minus_3f"]
    total = item["mean"]["Cplus3FB"] * item["sources"]
    print(f"{item['sources']:>4}{item['kind']:>18}"
          f"{item['mean']['Cplus3F']:>9.1f}{item['mean']['Cplus3FB']:>9.1f}"
          f"{item['mean']['B']:>9.1f}{total:>12.0f}"
          f"{paired['mean']:>+9.2f}"
          f"  [{paired['ci'][0]:+.1f},{paired['ci'][1]:+.1f}]"
          f"{paired['win_rate']:>8.0%}{item['all_clear']:>8}")
print()
print(f"{'源数':>4}{'场景':>18}{'P95(C+3FB)':>12}{'CVaR90(C+3FB)':>15}"
      f"{'P95(C+3F)':>11}{'CVaR90(C+3F)':>14}")
for key, item in sorted(data.items(), key=lambda kv: (kv[1]["sources"], kv[1]["kind"])):
    print(f"{item['sources']:>4}{item['kind']:>18}"
          f"{item['p95']['Cplus3FB']:>12.1f}{item['cvar90']['Cplus3FB']:>15.1f}"
          f"{item['p95']['Cplus3F']:>11.1f}{item['cvar90']['Cplus3F']:>14.1f}")

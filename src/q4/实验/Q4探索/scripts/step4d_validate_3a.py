"""C+3A 正式验证：与 C+、B、C 在同一批案例上配对比较（离线模拟器）。

指标口径与 Q3 一致：全清除率、均值、P95、CVaR90、搜索移动、搜索后移动、检测、程序时间。
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "models"))
import harness as H  # noqa: E402
from cplus_3a_agent import CPlus3AzimuthAgent  # noqa: E402

H._STRATEGIES["Cplus3A"] = CPlus3AzimuthAgent
OUT = H.SANDBOX_OUT / "step4d_validate3a"
NAMES = ["Cplus", "Cplus3A", "B", "C"]

SCENARIOS = [
    ("normal", lambda count: H.normal_cases(count, 20261021), 20261021, 500),
    ("min_radius", lambda count: H.min_radius_cases(count, 20261022), 20261022, 200),
    ("boundary_random", lambda count: H.boundary_cases(count, 20261023, False),
     20261023, 200),
    ("boundary_outward", lambda count: H.boundary_cases(count, 20261024, True),
     20261024, 200),
    ("mixed", lambda count: H.mixed_cases(count, 20261025), 20261025, 200),
]


def paired(by_strategy, a, b, cases):
    diff = [by_strategy[a][case] - by_strategy[b][case] for case in cases]
    mean = statistics.mean(diff)
    half = 1.96 * statistics.stdev(diff) / math.sqrt(len(diff))
    return {"comparison": f"{a}-{b}", "mean_diff_s_per_source": mean,
            "normal_approx_95ci": [mean - half, mean + half],
            "win_rate": sum(1 for value in diff if value < 0) / len(diff)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {}
    for label, builder, seed, count in SCENARIOS:
        cases = builder(count)
        rows, summaries = H.evaluate(label, cases, seed, NAMES, args.jobs, OUT)
        by_strategy = {name: {row["case"]: row["total_virtual_time_s"]
                              / row["source_count"]
                              for row in rows if row["strategy"] == name}
                       for name in NAMES}
        ordered = sorted(by_strategy["Cplus"])
        comparisons = [paired(by_strategy, "Cplus3A", "Cplus", ordered),
                       paired(by_strategy, "Cplus3A", "B", ordered),
                       paired(by_strategy, "Cplus3A", "C", ordered)]
        payload[label] = {"summaries": summaries, "paired": comparisons}
        H.log(f"\n--- {label}（{len(cases)} 例）---")
        H.log(f"{'策略':<9}{'均值':>9}{'P95':>9}{'CVaR90':>9}"
              f"{'搜索移动':>10}{'搜索后':>9}{'检测':>9}{'全清除':>9}")
        for item in summaries:
            H.log(f"{item['strategy']:<9}{item['mean_s_per_source']:>9.2f}"
                  f"{item['p95_s_per_source']:>9.2f}"
                  f"{item['cvar90_s_per_source']:>9.2f}"
                  f"{item['mean_search_movement_s']:>10.2f}"
                  f"{item['mean_post_search_movement_s']:>9.2f}"
                  f"{item['mean_detection_s']:>9.2f}"
                  f"{item['all_clear']:>6}/{item['cases']}")
        for item in comparisons:
            low, high = item["normal_approx_95ci"]
            H.log(f"  {item['comparison']:<14} 配对差="
                  f"{item['mean_diff_s_per_source']:+.2f} "
                  f"95%CI=[{low:+.2f},{high:+.2f}] "
                  f"胜率={item['win_rate']:.1%}")
    (OUT / "cplus3a_validation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    H.log(f"\n验证结果已写入 {OUT / 'cplus3a_validation.json'}")


if __name__ == "__main__":
    main()

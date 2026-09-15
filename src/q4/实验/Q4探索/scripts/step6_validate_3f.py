"""C+3F-lite 正式验证：与 C+3A、C+、B、C 在同一批案例上配对比较。

同时报告剪枝诊断：被跳过的共观测次数、实际执行的共观测次数，
用来核对"可剪枝空间"是否真的被吃掉。
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
from cplus_3f_agent import CPlus3FLiteAgent  # noqa: E402

H._STRATEGIES["Cplus3A"] = CPlus3AzimuthAgent
H._STRATEGIES["Cplus3F"] = CPlus3FLiteAgent
OUT = H.SANDBOX_OUT / "step6_validate3f"
NAMES = ["Cplus", "Cplus3A", "Cplus3F", "B", "C"]

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
    parser.add_argument("--normal", type=int, default=500)
    parser.add_argument("--only", default="", help="逗号分隔的场景名")
    args = parser.parse_args()
    wanted = {name.strip() for name in args.only.split(",") if name.strip()}
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {}
    for label, builder, seed, count in SCENARIOS:
        if wanted and label not in wanted:
            continue
        if label == "normal":
            count = args.normal
        cases = builder(count)
        names = NAMES if label == "normal" else ["Cplus", "Cplus3A", "Cplus3F"]
        rows, summaries = H.evaluate(label, cases, seed, names, args.jobs, OUT)
        by_strategy = {name: {row["case"]: row for row in rows
                              if row["strategy"] == name} for name in names}
        times = {name: {case: row["total_virtual_time_s"] / row["source_count"]
                        for case, row in by_strategy[name].items()}
                 for name in names}
        ordered = sorted(times["Cplus"])
        comparisons = [paired(times, "Cplus3F", base, ordered)
                       for base in ("Cplus", "Cplus3A", "B", "C") if base in times]
        prune_cases = [row for row in rows if row["strategy"] == "Cplus3F"]
        pruned = [row["pruned_observations"] or 0 for row in prune_cases]
        kept = [row["coobservations"] or 0 for row in prune_cases]
        pure_c = [row for row in rows if row["strategy"] == "C"]
        payload[label] = {
            "summaries": summaries, "paired": comparisons,
            "pruned_per_case": statistics.mean(pruned),
            "kept_per_case": statistics.mean(kept),
            "prune_share": (sum(pruned) / (sum(pruned) + sum(kept))
                            if sum(pruned) + sum(kept) else 0.0),
            "cleared_all": sum(row["all_cleared"] for row in prune_cases),
        }
        H.log(f"\n--- {label}（{len(cases)} 例）---")
        H.log(f"{'策略':<10}{'均值':>9}{'P95':>9}{'CVaR90':>9}"
              f"{'搜索移动':>10}{'搜索后':>9}{'检测':>9}{'全清除':>9}")
        for item in summaries:
            H.log(f"{item['strategy']:<10}{item['mean_s_per_source']:>9.2f}"
                  f"{item['p95_s_per_source']:>9.2f}"
                  f"{item['cvar90_s_per_source']:>9.2f}"
                  f"{item['mean_search_movement_s']:>10.2f}"
                  f"{item['mean_post_search_movement_s']:>9.2f}"
                  f"{item['mean_detection_s']:>9.2f}"
                  f"{item['all_clear']:>6}/{item['cases']}")
        for item in comparisons:
            low, high = item["normal_approx_95ci"]
            H.log(f"  {item['comparison']:<16} 配对差="
                  f"{item['mean_diff_s_per_source']:+.2f} "
                  f"95%CI=[{low:+.2f},{high:+.2f}] "
                  f"胜率={item['win_rate']:.1%}")
        H.log(f"  剪枝诊断：跳过 {payload[label]['pruned_per_case']:.1f} 次/例，"
              f"执行 {payload[label]['kept_per_case']:.1f} 次/例，"
              f"剪枝占 {payload[label]['prune_share']:.1%}"
              + (f"；对照纯 C 检测次数 "
                 f"{statistics.mean(row['measure_actions'] for row in pure_c):.1f}"
                 if pure_c else ""))
    (OUT / "cplus3f_validation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    H.log(f"\n验证结果已写入 {OUT / 'cplus3f_validation.json'}")


if __name__ == "__main__":
    main()

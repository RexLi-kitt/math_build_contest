"""C+3F 的架构简化验证：剪枝之后，原点门控是否还必要。

如果 C 分支加上距离门之后在边界场景不再劣于 B，那么门控可以整体去掉，
模型退化为"单一路线 + 选择性共观测"，同时消除 mixed 象限的门控失效风险。
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
from cplus_3f_agent import CPlus3FLiteAgent  # noqa: E402


class C3FDirectAgent(CPlus3FLiteAgent):
    """去掉门控：始终使用 C 的站点集与 3 条方位目标（阈值 -1 使门控恒选 C）。"""

    discovery_threshold = -1


H._STRATEGIES["Cplus3F"] = CPlus3FLiteAgent
H._STRATEGIES["C3FDirect"] = C3FDirectAgent
OUT = H.SANDBOX_OUT / "step6b_nogate"
NAMES = ["Cplus3F", "C3FDirect", "B", "C"]

SCENARIOS = [
    ("boundary_random", lambda count: H.boundary_cases(count, 20261023, False),
     20261023),
    ("boundary_outward", lambda count: H.boundary_cases(count, 20261024, True),
     20261024),
    ("mixed", lambda count: H.mixed_cases(count, 20261025), 20261025),
    ("normal", lambda count: H.normal_cases(count, 20261021), 20261021),
    ("min_radius", lambda count: H.min_radius_cases(count, 20261022), 20261022),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--count", type=int, default=200)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {}
    for label, builder, seed in SCENARIOS:
        cases = builder(args.count)
        rows, summaries = H.evaluate(label, cases, seed, NAMES, args.jobs, OUT)
        by_strategy = {name: {row["case"]: row["total_virtual_time_s"]
                              / row["source_count"]
                              for row in rows if row["strategy"] == name}
                       for name in NAMES}
        ordered = sorted(by_strategy["Cplus3F"])
        diff = [by_strategy["C3FDirect"][case] - by_strategy["Cplus3F"][case]
                for case in ordered]
        mean = statistics.mean(diff)
        half = 1.96 * statistics.stdev(diff) / math.sqrt(len(diff))
        payload[label] = {"summaries": summaries,
                          "direct_minus_gated": mean,
                          "ci": [mean - half, mean + half]}
        H.log(f"\n--- {label}（{len(cases)} 例）---")
        H.log(f"{'策略':<11}{'均值':>9}{'P95':>9}{'CVaR90':>9}"
              f"{'检测':>9}{'全清除':>9}")
        for item in summaries:
            H.log(f"{item['strategy']:<11}{item['mean_s_per_source']:>9.2f}"
                  f"{item['p95_s_per_source']:>9.2f}"
                  f"{item['cvar90_s_per_source']:>9.2f}"
                  f"{item['mean_detection_s']:>9.2f}"
                  f"{item['all_clear']:>6}/{item['cases']}")
        H.log(f"  去掉门控 − 保留门控 = {mean:+.2f} s/源 "
              f"95%CI=[{mean - half:+.2f},{mean + half:+.2f}]")
    (OUT / "nogate_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

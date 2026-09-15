"""第十步：DG2（延迟门控 + 动态连接 B 路线）筛选。

按用户口径修正三点：
1. 切换后仍访问完整 B 站点集，覆盖证书自然保留，只优化访问顺序；
2. 不用 AUC/准确率选阈值，直接用配对总时间（并对"该走 B 却继续 C"的代价给予关注）；
3. 重点看 k=2、k=3，同时保留 k=1、k=5 作对照，并对比 replan 与 fixed 两种衔接方式。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "models"))
import harness as H  # noqa: E402
from cplus_3f_agent import CPlus3FLiteAgent  # noqa: E402
from cplus_3f_dg2_agent import make_variant  # noqa: E402


class C3FDirectAgent(CPlus3FLiteAgent):
    discovery_threshold = -1


H._STRATEGIES["Cplus3F"] = CPlus3FLiteAgent
H._STRATEGIES["C3FDirect"] = C3FDirectAgent
VARIANTS = {"Cplus3F": CPlus3FLiteAgent, "C3FDirect": C3FDirectAgent}
for probe, tau, replan in ((1, 0, True), (2, 0, True), (2, 1, True), (3, 0, True),
                           (3, 1, True), (5, 0, True), (2, 0, False), (3, 0, False)):
    name = f"DG2_k{probe}_t{tau}_{'R' if replan else 'F'}"
    H._STRATEGIES[name] = make_variant(probe, tau, replan)
    VARIANTS[name] = H._STRATEGIES[name]

OUT = H.SANDBOX_OUT / "step10_screen_dg2"
SCENARIOS = [
    ("boundary_random", lambda count: H.boundary_cases(count, 20261031, False),
     20261031),
    ("boundary_outward", lambda count: H.boundary_cases(count, 20261032, True),
     20261032),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--cases", type=int, default=200)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    names = list(VARIANTS)
    table = {}
    for label, builder, seed in SCENARIOS:
        cases = builder(args.cases)
        rows, _ = H.evaluate(label, cases, seed, names, args.jobs, OUT)
        means = {name: statistics.mean(
            row["total_virtual_time_s"] / row["source_count"]
            for row in rows if row["strategy"] == name) for name in names}
        table[label] = means
        H.log(f"\n--- {label}（筛选用种子 {seed}，{len(cases)} 例）---")
        for name in sorted(means, key=means.get):
            decisions = [row["delayed_decision"] for row in rows
                         if row["strategy"] == name]
            share = (sum(1 for value in decisions if value == "B") / len(decisions)
                     if decisions else 0.0)
            conn = [row["connection_m"] for row in rows
                    if row["strategy"] == name and row["connection_m"] is not None]
            extra = (f"  衔接移动均值={statistics.mean(conn):.0f}m" if conn else "")
            H.log(f"  {name:<18}{means[name]:>9.2f}"
                  f"  {'切B比例=' + format(share, '.1%') if decisions and decisions[0] else ''}"
                  f"{extra}")
    H.log("\n=== 两场景等权平均（越低越好；括号内为相对 C+3F 的差） ===")
    base = statistics.mean(table[label]["Cplus3F"] for label, _, _ in SCENARIOS)
    weighted = {name: statistics.mean(table[label][name] for label, _, _ in SCENARIOS)
                for name in names}
    for name in sorted(weighted, key=weighted.get):
        H.log(f"  {name:<18}{weighted[name]:>9.2f}   ({weighted[name] - base:+.2f})")
    (OUT / "dg2_screen.json").write_text(json.dumps(
        {"per_scenario": table, "equal_weight": weighted, "cplus3f_baseline": base},
        ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

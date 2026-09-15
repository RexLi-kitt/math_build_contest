"""第八步：延迟门控 (k, τ) 筛选。

只在两个"原点零发现"的边界场景上有意义（其余场景门控不触发、与 C+3F 同值），
因此筛选只跑这两个场景，用与验证批次不同的筛选用种子。
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
from cplus_3f_dg_agent import CPlus3FDelayedAgent, make_variant  # noqa: E402


class C3FDirectAgent(CPlus3FLiteAgent):
    discovery_threshold = -1  # 始终走 C 分支


H._STRATEGIES["Cplus3F"] = CPlus3FLiteAgent
H._STRATEGIES["C3FDirect"] = C3FDirectAgent
VARIANTS = {"Cplus3F": CPlus3FLiteAgent, "C3FDirect": C3FDirectAgent}
for k, tau in ((1, 0), (2, 0), (3, 0), (3, 1), (5, 2)):
    name = f"DG_k{k}_t{tau}"
    H._STRATEGIES[name] = make_variant(k, tau)
    VARIANTS[name] = H._STRATEGIES[name]

OUT = H.SANDBOX_OUT / "step8_screen_dg"
SCENARIOS = [
    ("boundary_random", False, 20261031),
    ("boundary_outward", True, 20261032),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--cases", type=int, default=200)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    names = list(VARIANTS)
    table = {}
    for label, outward, seed in SCENARIOS:
        cases = H.boundary_cases(args.cases, seed, outward)
        rows, _ = H.evaluate(label, cases, seed, names, args.jobs, OUT)
        means = {name: statistics.mean(
            row["total_virtual_time_s"] / row["source_count"]
            for row in rows if row["strategy"] == name) for name in names}
        table[label] = means
        H.log(f"\n--- {label}（筛选用种子 {seed}，{len(cases)} 例）---")
        for name in names:
            H.log(f"  {name:<12}{means[name]:>9.2f}")
        for name in names:
            if not name.startswith("DG"):
                continue
            decisions = [row["delayed_decision"] for row in rows
                         if row["strategy"] == name]
            share = (sum(1 for value in decisions if value == "B") / len(decisions)
                     if decisions else 0.0)
            H.log(f"  {name} 切到 B 的比例：{share:.1%}")
    H.log("\n=== 两场景等权平均（越低越好） ===")
    H.log(f"{'策略':<12}{'等权均值':>10}{'相对最优的差':>13}")
    weighted = {name: statistics.mean(table[label][name] for label, _, _ in SCENARIOS)
                for name in names}
    best = min(weighted.values())
    for name in sorted(weighted, key=weighted.get):
        H.log(f"{name:<12}{weighted[name]:>10.2f}{weighted[name] - best:>+13.2f}")
    (OUT / "screen_report.json").write_text(json.dumps(
        {"per_scenario": table, "equal_weight": weighted},
        ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

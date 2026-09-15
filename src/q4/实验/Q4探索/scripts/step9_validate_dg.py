"""第九步：延迟门控在全新种子上的验证（筛选用 20261031/32，验证用 20261101/02）。

结论若与筛选一致，说明"延迟门控净损失"不是种子偶然；同时复现各分支的证书状况。
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
from cplus_3f_dg_agent import make_variant  # noqa: E402


class C3FDirectAgent(CPlus3FLiteAgent):
    discovery_threshold = -1


H._STRATEGIES["Cplus3F"] = CPlus3FLiteAgent
H._STRATEGIES["C3FDirect"] = C3FDirectAgent
for k, tau in ((1, 0), (3, 0)):
    name = f"DG_k{k}_t{tau}"
    H._STRATEGIES[name] = make_variant(k, tau)
NAMES = ["Cplus3F", "DG_k1_t0", "DG_k3_t0", "C3FDirect", "B", "C"]
OUT = H.SANDBOX_OUT / "step9_validate_dg"
SCENARIOS = [
    ("boundary_random", False, 20261101),
    ("boundary_outward", True, 20261102),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--cases", type=int, default=200)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {}
    for label, outward, seed in SCENARIOS:
        cases = H.boundary_cases(args.cases, seed, outward)
        rows, summaries = H.evaluate(label, cases, seed, NAMES, args.jobs, OUT)
        times = {name: {row["case"]: row["total_virtual_time_s"] / row["source_count"]
                        for row in rows if row["strategy"] == name}
                 for name in NAMES}
        H.log(f"\n--- {label}（验证种子 {seed}，{len(cases)} 例）---")
        H.log(f"{'策略':<11}{'均值':>9}{'P95':>9}{'CVaR90':>9}{'全清除':>9}")
        for item in summaries:
            H.log(f"{item['strategy']:<11}{item['mean_s_per_source']:>9.2f}"
                  f"{item['p95_s_per_source']:>9.2f}"
                  f"{item['cvar90_s_per_source']:>9.2f}"
                  f"{item['all_clear']:>6}/{item['cases']}")
        ordered = sorted(times["Cplus3F"])
        for base in ("Cplus3F", "B"):
            diff = [times["DG_k1_t0"][case] - times[base][case] for case in ordered]
            mean = statistics.mean(diff)
            half = 1.96 * statistics.stdev(diff) / math.sqrt(len(diff))
            H.log(f"  DG_k1_t0 − {base:<8} = {mean:+.2f} "
                  f"95%CI=[{mean - half:+.2f},{mean + half:+.2f}]")
        for name in ("DG_k1_t0", "DG_k3_t0"):
            decisions = [row["delayed_decision"] for row in rows
                         if row["strategy"] == name]
            share = sum(1 for value in decisions if value == "B") / len(decisions)
            H.log(f"  {name} 切到 B 的比例：{share:.1%}")
        payload[label] = {"seed": seed,
                          "means": {name: statistics.mean(times[name].values())
                                    for name in NAMES}}
    H.log("\n=== 两场景等权平均 ===")
    weighted = {name: statistics.mean(payload[label]["means"][name]
                                      for label, _, _ in SCENARIOS)
                for name in NAMES}
    best = min(weighted.values())
    for name in sorted(weighted, key=weighted.get):
        H.log(f"  {name:<11}{weighted[name]:>9.2f}{weighted[name] - best:>+9.2f}")
    (OUT / "dg_validation.json").write_text(json.dumps(
        {"per_scenario": payload, "equal_weight": weighted},
        ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

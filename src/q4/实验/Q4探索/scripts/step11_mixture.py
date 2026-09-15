"""第十一步：贴边场景的连续过渡（边界随机 → 边界朝外）。

用 outward_share 控制每条定向波束朝外的概率（0=随机朝向，1=全部朝外），
位置/半径/源数在同一随机流下不变，观察各模型在哪里交叉、门控在哪里失效。
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
from cplus_3f_dg_agent import make_variant as make_dg  # noqa: E402
from cplus_3f_dg2_agent import make_variant as make_dg2  # noqa: E402


class C3FDirectAgent(CPlus3FLiteAgent):
    discovery_threshold = -1


H._STRATEGIES["Cplus3F"] = CPlus3FLiteAgent
H._STRATEGIES["C3FDirect"] = C3FDirectAgent
H._STRATEGIES["DG_k1_t0"] = make_dg(1, 0)
H._STRATEGIES["DG2_k3_t1_R"] = make_dg2(3, 1, True)
NAMES = ["Cplus3F", "DG_k1_t0", "DG2_k3_t1_R", "C3FDirect"]
OUT = H.SANDBOX_OUT / "step11_mixture"
LEVELS = [0.0, 0.25, 0.5, 0.75, 1.0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--cases", type=int, default=150)
    parser.add_argument("--seed", type=int, default=20261201)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    table = {}
    H.log(f"{'朝外波束占比':<14}" + "".join(f"{name:>14}" for name in NAMES)
          + f"{'切B比例(k1)':>13}")
    for index, share in enumerate(LEVELS):
        seed = args.seed + index
        cases = H.margin_cases(args.cases, seed, share)
        rows, _ = H.evaluate(f"margin_{int(share * 100):03d}", cases, seed, NAMES,
                             args.jobs, OUT)
        means = {name: statistics.mean(
            row["total_virtual_time_s"] / row["source_count"]
            for row in rows if row["strategy"] == name) for name in NAMES}
        table[share] = means
        decisions = [row["delayed_decision"] for row in rows
                     if row["strategy"] == "DG_k1_t0"]
        switch = sum(1 for value in decisions if value == "B") / len(decisions)
        H.log(f"{share:<14.2f}" + "".join(f"{means[name]:>14.2f}" for name in NAMES)
              + f"{switch:>13.1%}")
    H.log("\n每级的最优策略：")
    for share, means in table.items():
        best = min(means, key=means.get)
        H.log(f"  朝外占比 {share:.2f}: {best}（{means[best]:.2f}）")
    (OUT / "mixture_report.json").write_text(json.dumps(
        {str(share): means for share, means in table.items()},
        ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

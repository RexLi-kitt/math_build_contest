"""第十八步：3F 距离门对分支差异的吸收比例与剩余门控遗憾。

臂定义（与用户口径一致）：
    B  = 始终走 B（27 站 / 目标方位 2，无距离门）
    C  = 始终走 C（29 站 / 目标方位 3，无距离门）
    BF = 始终走 B + 1500 m 距离门
    CF = 始终走 C + 1500 m 距离门
    D  = C+3FB（n0=0 走 BF 分支，n0>=1 走 CF 分支）

指标：
    R^F_i = T_D,i - min(T_BF,i, T_CF,i)        剩余门控遗憾
    G^0_i = |T_B,i - T_C,i|,  G^F_i = |T_BF,i - T_CF,i|
    eta   = 1 - E[G^F] / E[G^0]                 3F 对分支差异的吸收比例
并按 n0 = 0 / 1 / >=2 分层输出。
"""
from __future__ import annotations

import argparse
import inspect
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
from cplus_3fb_agent import CPlus3FBAgent  # noqa: E402

if "B" not in H._STRATEGIES or "C" not in H._STRATEGIES:
    import cplus_gate_agent as G  # noqa: E402
    pool = {name: obj for name, obj in vars(G).items()
            if inspect.isclass(obj) and name.endswith("AzimuthAgent")}
    for prefix, key in (("B", "B"), ("C", "C")):
        match = [name for name in pool if name.startswith(prefix)
                 and name[1:2].isdigit()]
        if match:
            H._STRATEGIES[key] = pool[match[0]]
    H.log(f"从 cplus_gate_agent 取得的路线类：{ {k: v.__name__ for k, v in pool.items()} }")


class BFilterAgent(CPlus3FBAgent):
    """恒走 B 分支，其余同 C+3FB。"""
    discovery_threshold = 10 ** 9


class CFilterAgent(CPlus3FLiteAgent):
    """恒走 C 分支，其余同 C+3F。"""
    discovery_threshold = -1


H._STRATEGIES["BF"] = BFilterAgent
H._STRATEGIES["CF"] = CFilterAgent
H._STRATEGIES["D"] = CPlus3FBAgent
NAMES = ["B", "C", "BF", "CF", "D"]
RHO = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
OUT = H.SANDBOX_OUT / "step18_gate_regret"


def stats(values: list) -> dict:
    ordered = sorted(values)
    return {"mean": statistics.mean(values),
            "p95": ordered[max(0, int(round(0.95 * (len(ordered) - 1))))],
            "max": ordered[-1]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--cases", type=int, default=100)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    per_rho = {}
    H.log(f"{'rho':>5}{'eta':>8}{'R^F均值':>9}{'R^F_P95':>9}{'R^F_max':>9}"
          f"{'D选B比例':>10}{'D均值':>9}{'CF均值':>9}{'BF均值':>9}")
    for rho in RHO:
        seed = 20270501 + int(round(rho * 100))
        cases = H.mixed_cases(args.cases, seed, far_share=rho)
        label = f"mixed_rho{int(round(rho * 100)):02d}"
        case_rows, _ = H.evaluate(label, cases, seed, NAMES, args.jobs, OUT)
        rows.extend(case_rows)
        times = {name: {row["case"]: row["total_virtual_time_s"] / row["source_count"]
                        for row in case_rows if row["strategy"] == name}
                 for name in NAMES}
        n0 = {row["case"]: row.get("origin_discoveries") for row in case_rows
              if row["strategy"] == "D"}
        keys = sorted(times["D"])
        gap0 = [abs(times["B"][k] - times["C"][k]) for k in keys]
        gapf = [abs(times["BF"][k] - times["CF"][k]) for k in keys]
        regret = [times["D"][k] - min(times["BF"][k], times["CF"][k]) for k in keys]
        eta = 1.0 - statistics.mean(gapf) / statistics.mean(gap0)
        picked_b = sum(1 for k in keys if n0[k] is not None and n0[k] <= 0) / len(keys)
        per_rho[label] = {
            "rho": rho, "cases": len(keys), "eta": eta,
            "regret": stats(regret), "gap0_mean": statistics.mean(gap0),
            "gapf_mean": statistics.mean(gapf),
            "d_pick_b_share": picked_b,
            "mean": {name: statistics.mean(list(times[name].values())) for name in NAMES},
            "n0": n0, "times": times,
        }
        item = per_rho[label]
        H.log(f"{rho:>5.2f}{eta:>8.2f}{item['regret']['mean']:>9.2f}"
              f"{item['regret']['p95']:>9.2f}{item['regret']['max']:>9.2f}"
              f"{picked_b:>10.1%}{item['mean']['D']:>9.1f}"
              f"{item['mean']['CF']:>9.1f}{item['mean']['BF']:>9.1f}")

    # 按 n0 分层
    H.log("\n=== 按原点发现数分层（六个 rho 汇总） ===")
    H.log(f"{'n0分层':>8}{'案例数':>7}{'BF-CF':>10}{'D选B':>8}"
          f"{'R^F均值':>9}{'R^F_P95':>9}{'R^F_max':>9}{'最优为B':>9}{'最优为CF':>9}")
    strata = {"n0=0": lambda v: v == 0, "n0=1": lambda v: v == 1,
              "n0>=2": lambda v: v >= 2}
    table = {}
    for name, predicate in strata.items():
        keys, diffs, regrets, picks, opt_b, opt_cf = [], [], [], [], 0, 0
        for label, item in per_rho.items():
            for key, value in item["n0"].items():
                if value is None or not predicate(value):
                    continue
                diff_bf_cf = item["times"]["BF"][key] - item["times"]["CF"][key]
                regret = (item["times"]["D"][key]
                          - min(item["times"]["BF"][key], item["times"]["CF"][key]))
                keys.append((label, key))
                diffs.append(diff_bf_cf)
                regrets.append(regret)
                picks.append(1 if value <= 0 else 0)
                if item["times"]["BF"][key] < item["times"]["CF"][key]:
                    opt_b += 1
                else:
                    opt_cf += 1
        if not keys:
            continue
        table[name] = {"cases": len(keys), "bf_minus_cf": statistics.mean(diffs),
                       "pick_b": statistics.mean(picks),
                       "regret": stats(regrets), "optimal_b_share": opt_b / len(keys),
                       "optimal_cf_share": opt_cf / len(keys)}
        item = table[name]
        H.log(f"{name:>8}{item['cases']:>7}{item['bf_minus_cf']:>10.1f}"
              f"{item['pick_b']:>8.1%}{item['regret']['mean']:>9.2f}"
              f"{item['regret']['p95']:>9.2f}{item['regret']['max']:>9.2f}"
              f"{item['optimal_b_share']:>9.1%}{item['optimal_cf_share']:>9.1%}")

    H.log("\n=== 结论 ===")
    etas = [item["eta"] for item in per_rho.values()]
    regret_means = [item["regret"]["mean"] for item in per_rho.values()]
    regret_max = max(item["regret"]["max"] for item in per_rho.values())
    H.log(f"eta 区间 {min(etas):.2f}—{max(etas):.2f}；R^F 均值区间 "
          f"{min(regret_means):.2f}—{max(regret_means):.2f} s/源；全域最坏 R^F "
          f"{regret_max:.1f} s/源")
    payload = {
        "per_rho": {label: {key: value for key, value in item.items()
                            if key not in ("times", "n0")}
                    for label, item in per_rho.items()},
        "strata": table,
        "summary": {"eta_range": [min(etas), max(etas)],
                    "regret_mean_range": [min(regret_means), max(regret_means)],
                    "regret_max": regret_max},
    }
    (OUT / "gate_regret_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    H.log(f"\n报告：{OUT / 'gate_regret_report.json'}")


if __name__ == "__main__":
    main()

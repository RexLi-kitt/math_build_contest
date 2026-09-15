"""第十七步：按题设源数区间 10—16 重测指标。

此前所有参数化实验固定 16 源，而题设是 10—16 源，每源秒数的分母会变：
路线巡游与原点扫描是固定成本，源数越少摊得越重。这里按 N = 10/12/14/16
重测 C+3FB 的绝对指标，并检查它对 C+3F 的弱支配是否在全区间的成立。
"""
from __future__ import annotations

import argparse
import json
import math
import random
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

H._STRATEGIES["Cplus3F"] = CPlus3FLiteAgent
H._STRATEGIES["Cplus3FB"] = CPlus3FBAgent
NAMES = ["Cplus3F", "Cplus3FB", "B"]
OUT = H.SANDBOX_OUT / "step17_source_count"
COUNTS = [10, 12, 14, 16]
KINDS = ["normal", "boundary_random", "boundary_outward"]


def build(kind: str, cases: int, seed: int, sources: int) -> list:
    rng = random.Random(seed)
    built = []
    for index in range(cases):
        group = H.random_mixed_sources(rng, sources, 0.75)
        if kind != "normal":
            outward = kind == "boundary_outward"
            for source in group:
                angle = rng.random() * 2.0 * math.pi
                radius = 1800.0 if index % 2 == 0 else rng.uniform(1700.0, 1800.0)
                source.position = radius * math.cos(angle), radius * math.sin(angle)
                source.receive_radius = 1000.0
                if source.beam_direction is not None:
                    if outward:
                        source.beam_direction = math.degrees(angle) % 360.0
                    else:
                        source.beam_direction = rng.uniform(0.0, 360.0)
        built.append(group)
    return built


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--cases", type=int, default=50)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    table = {}
    H.log(f"{'源数':>4}{'场景':>18}{'C+3F':>9}{'C+3FB':>9}{'B':>9}"
          f"{'配对差(CI)':>26}{'P95(C+3FB)':>12}{'CVaR(C+3FB)':>13}{'清除':>8}")
    for sources in COUNTS:
        for kind in KINDS:
            seed = 20270301 + sources * 10 + KINDS.index(kind)
            cases = build(kind, args.cases, seed, sources)
            label = f"{kind}_n{sources}"
            case_rows, summaries = H.evaluate(label, cases, seed, NAMES,
                                              args.jobs, OUT)
            rows.extend(case_rows)
            by_name = {item["strategy"]: item for item in summaries}
            times = {name: {row["case"]: row["total_virtual_time_s"] / row["source_count"]
                            for row in case_rows if row["strategy"] == name}
                     for name in NAMES}
            ordered = sorted(times["Cplus3F"])
            diff = [times["Cplus3FB"][case] - times["Cplus3F"][case] for case in ordered]
            mean = statistics.mean(diff)
            half = 1.96 * statistics.stdev(diff) / math.sqrt(len(diff))
            clears = by_name["Cplus3FB"]["all_clear"]
            total = by_name["Cplus3FB"]["cases"]
            table[label] = {
                "sources": sources, "kind": kind,
                "mean": {name: by_name[name]["mean_s_per_source"] for name in NAMES},
                "p95": {name: by_name[name]["p95_s_per_source"] for name in NAMES},
                "cvar90": {name: by_name[name]["cvar90_s_per_source"] for name in NAMES},
                "paired_3fb_minus_3f": {"mean": mean, "ci": [mean - half, mean + half],
                                        "win_rate": sum(1 for v in diff if v < 0) / len(diff)},
                "all_clear": f"{clears}/{total}",
                "identical": all(abs(times["Cplus3FB"][c] - times["Cplus3F"][c]) < 1e-9
                                 for c in ordered),
            }
            item = table[label]
            H.log(f"{sources:>4}{kind:>18}{item['mean']['Cplus3F']:>9.1f}"
                  f"{item['mean']['Cplus3FB']:>9.1f}{item['mean']['B']:>9.1f}"
                  f"{mean:>+12.2f} [{item['paired_3fb_minus_3f']['ci'][0]:+.1f},"
                  f"{item['paired_3fb_minus_3f']['ci'][1]:+.1f}]"
                  f"{item['p95']['Cplus3FB']:>12.1f}"
                  f"{item['cvar90']['Cplus3FB']:>13.1f}{clears:>5}/{total:<3}")
    H.log("\n=== 全区间的弱支配检查（C+3FB 相对 C+3F） ===")
    for label, item in table.items():
        paired = item["paired_3fb_minus_3f"]
        verdict = ("逐案例同值" if item["identical"] else
                   ("显著改善" if paired["ci"][1] < 0 else
                    ("显著退化" if paired["ci"][0] > 0 else "无显著差异")))
        H.log(f"  {label:<24} {paired['mean']:+7.2f}  {verdict}")
    (OUT / "source_count_report.json").write_text(
        json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

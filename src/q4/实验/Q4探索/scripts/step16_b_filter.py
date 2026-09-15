"""第十六步：B 分支搜索期距离门（C+3F-B）验收。

验收标准（用户口径）：
1. B 路线/站点顺序/方位目标 2 不变；
2. 走 C 分支的案例与 C+3F 逐案例完全一致（此处用 normal 场景直接验证）；
3. 边界随机、边界朝外分别配对验证，且 100% 清除；
4. 被剪观测的真值审计：本来能够成功却被剪掉的数量必须为 0；
5. 均值 / P95 / CVaR90 至少一项稳定改善。
同时输出 B、C 路线中超出 1800 m 的测站数与首个越界站序号，用于评估越界风险。
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
from cplus_3fb_agent import CPlus3FBAgent  # noqa: E402

H._STRATEGIES["Cplus3F"] = CPlus3FLiteAgent
H._STRATEGIES["Cplus3FB"] = CPlus3FBAgent
NAMES = ["Cplus3F", "Cplus3FB", "B"]
OUT = H.SANDBOX_OUT / "step16_b_filter"
MEDIAN_LIMIT = 1500.0

SCENARIOS = [
    ("normal", lambda count: H.normal_cases(count, 20270101), 20270101),
    ("boundary_random", lambda count: H.boundary_cases(count, 20270102, False), 20270102),
    ("boundary_outward", lambda count: H.boundary_cases(count, 20270103, True), 20270103),
]


def route_arena_check() -> dict:
    """B/C 路线中超出 1800 m 的测站情况。"""
    report = {}
    for folder in ("B模型", "C模型"):
        data = json.loads((H.MODELS / folder / "winner_design.json").read_text(
            encoding="utf-8"))
        sites = [tuple(point) for point in data["sites"]]
        route = [sites[index] for index in data["order"]]
        radii = [math.hypot(*point) for point in route]
        over = [(index, round(radius, 1)) for index, radius in enumerate(radii)
                if radius > 1800.0 + 1e-9]
        report[folder] = {
            "stations": len(route),
            "over_1800": len(over),
            "max_radius_m": round(max(radii), 1),
            "first_over_index": over[0][0] if over else None,
            "first_over_radius_m": over[0][1] if over else None,
            "over_list": over,
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--cases", type=int, default=150)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"arena": route_arena_check()}
    for folder, item in payload["arena"].items():
        H.log(f"{folder}：{item['stations']} 站，超 1800 m 的有 {item['over_1800']} 站，"
              f"最大半径 {item['max_radius_m']} m，首个越界站序号 "
              f"{item['first_over_index']}（{item['first_over_radius_m']} m）")

    verdict = {}
    for label, builder, seed in SCENARIOS:
        cases = builder(args.cases)
        rows, summaries = H.evaluate(label, cases, seed, NAMES, args.jobs, OUT)
        times = {name: {row["case"]: row["total_virtual_time_s"] / row["source_count"]
                        for row in rows if row["strategy"] == name} for name in NAMES}
        ordered = sorted(times["Cplus3F"])
        H.log(f"\n--- {label}（种子 {seed}，{len(cases)} 例）---")
        for item in summaries:
            H.log(f"  {item['strategy']:<10}均值 {item['mean_s_per_source']:>8.2f}  "
                  f"P95 {item['p95_s_per_source']:>8.2f}  "
                  f"CVaR90 {item['cvar90_s_per_source']:>8.2f}  "
                  f"全清除 {item['all_clear']}/{item['cases']}  "
                  f"剪枝 {item.get('mean_pruned') or 0:.1f}  "
                  f"真值命中 {item.get('mean_truth_hits') or 0:.2f}")
        paired = {}
        for other in ("Cplus3F", "B"):
            diff = [times["Cplus3FB"][case] - times[other][case] for case in ordered]
            mean = statistics.mean(diff)
            half = 1.96 * statistics.stdev(diff) / math.sqrt(len(diff)) if len(diff) > 1 else 0.0
            paired[other] = {"mean": mean, "ci": [mean - half, mean + half],
                             "win_rate": sum(1 for value in diff if value < 0) / len(diff)}
            H.log(f"  C+3F-B − {other:<8} = {mean:+8.2f}  "
                  f"95%CI=[{paired[other]['ci'][0]:+.2f},{paired[other]['ci'][1]:+.2f}]  "
                  f"胜率 {paired[other]['win_rate']:.1%}")
        truths = [row.get("pruned_truth_hits") or 0 for row in rows]
        pruned = [row.get("pruned_observations") or 0 for row in rows]
        identical = all(abs(times["Cplus3FB"][case] - times["Cplus3F"][case]) < 1e-9
                        for case in ordered)
        payload[label] = {
            "summaries": summaries,
            "paired": {key: {"mean": value["mean"], "ci": value["ci"],
                             "win_rate": value["win_rate"]}
                       for key, value in paired.items()},
            "identical_to_cplus3f": identical,
            "pruned_total": sum(pruned),
            "truth_hits_total": sum(truths),
            "samples": [row.get("pruned_samples") for row in rows
                        if row.get("pruned_samples")][:3],
        }
        H.log(f"  与 C+3F 逐案例完全一致：{identical}；"
              f"剪枝总计 {sum(pruned)}，真值命中 {sum(truths)}")

    H.log("\n=== 验收判定 ===")
    for label in ("boundary_random", "boundary_outward"):
        item = payload[label]
        best = {key: min(entry[key] for entry in item["summaries"]
                         if entry["strategy"] != "B") for key in
                ("mean_s_per_source", "p95_s_per_source", "cvar90_s_per_source")}
        new = next(entry for entry in item["summaries"] if entry["strategy"] == "Cplus3FB")
        old = next(entry for entry in item["summaries"] if entry["strategy"] == "Cplus3F")
        improves = sum(1 for key in best if new[key] < old[key] - 1e-9)
        stable = sum(1 for key in best
                     if new[key] < old[key] - 1e-9
                     and item["paired"]["Cplus3F"]["ci"][1] < 0)
        H.log(f"  {label}：全清除 {new['all_clear']}/{new['cases']}，"
              f"均值/P95/CVaR 改善项 {improves}/3，配对显著改善项 {stable}/3，"
              f"真值命中 {item['truth_hits_total']}")
    payload["code_identical_under_c_branch"] = all(
        payload[label]["identical_to_cplus3f"] for label in ("normal",))
    (OUT / "b_filter_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    H.log(f"\n报告：{OUT / 'b_filter_report.json'}")


if __name__ == "__main__":
    main()

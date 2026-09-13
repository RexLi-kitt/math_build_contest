"""把 D 鲁棒性 JSON 汇总为可直接引用的 Markdown 报告。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "outputs" / "q4" / "results" / "d_robustness" / "robustness_report.json"


def f(value, digits=2):
    return f"{value:.{digits}f}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    output = args.output or args.input.with_name("README.md")
    audit = data["audit"]
    lines = [
        "# D 模型鲁棒性实验（修正版）", "",
        "本报告由仓库正式 `src/q4/d_agent.py` 直接运行生成。题设内实验与题设外误差失配",
        "分开统计；案例数指独立源配置，模型运行数包含同一案例的多个对照臂。", "",
        "## 总体结果", "",
        f"- 独立源场景：{audit['independent_source_cases']}；模型运行：{audit['model_runs']}。",
        f"- 题设内运行：{audit['in_spec_all_cleared_runs']}/{audit['in_spec_model_runs']} 全部清除。",
        f"- 题设外误差运行：{audit['out_of_spec_all_cleared_runs']}/{audit['out_of_spec_model_runs']} 全部清除；该项只用于失配探测。",
        f"- D 自身逐次审计剪枝：{audit['d_audited_pruned']} 次；真值本可成功：{audit['d_pruned_truth_hits']} 次。",
        f"- 被剪最小距离 {f(audit['min_d_pruned_distance_m'],3)} m；被保留最大距离 {f(audit['max_d_kept_distance_m'],3)} m。", "",
        "## A. 10—16源常规回归", "",
        "| 源数 | normal D | boundary random D | boundary outward D | D−C3F random（95% CI） | D−C3F outward（95% CI） |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for count in range(10, 17):
        n = data["A"][f"A_normal_n{count}"]
        r = data["A"][f"A_boundary_random_n{count}"]
        o = data["A"][f"A_boundary_outward_n{count}"]
        rd, od = r["D_minus_C3F"], o["D_minus_C3F"]
        lines.append(f"| {count} | {f(n['arms']['D']['mean_s_per_source'],1)} | "
                     f"{f(r['arms']['D']['mean_s_per_source'],1)} | {f(o['arms']['D']['mean_s_per_source'],1)} | "
                     f"{f(rd['mean'])} [{f(rd['ci95'][0])}, {f(rd['ci95'][1])}] | "
                     f"{f(od['mean'])} [{f(od['ci95'][0])}, {f(od['ci95'][1])}] |")
    lines += ["", "负值表示 D 比 C+3F 更快。normal 中 D 与 C+3F 逐案例一致。", "",
              "## B. mixed 门控遗憾分层", "",
              "| 原点发现数 | 案例数 | BF−CF | B实际最优比例 | 遗憾均值 | P95 | 最大值 |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for key, item in data["B_strata"].items():
        lines.append(f"| {key} | {item['cases']} | {f(item['mean_BF_minus_CF'])} | "
                     f"{item['best_is_B_rate']:.1%} | {f(item['regret_mean'])} | "
                     f"{f(item['regret_p95'])} | {f(item['regret_max'])} |")
    lines += ["", "## C. 空间对抗场景", "",
              "| 场景 | BF | CF | D | D相对事后最优遗憾 | 最大遗憾 |",
              "|---|---:|---:|---:|---:|---:|"]
    for label, item in data["C"].items():
        name = label.removeprefix("C_")
        arms = item["arms"]
        lines.append(f"| {name} | {f(arms['BF']['mean_s_per_source'],1)} | "
                     f"{f(arms['CF']['mean_s_per_source'],1)} | {f(arms['D']['mean_s_per_source'],1)} | "
                     f"{f(item['regret_mean'])} | {f(item['regret_max'])} |")
    lines += ["", "`min_radius_outward` 使用波束朝外；原旧实验的高遗憾构造实际为朝内，",
              "现保留为 `min_radius_inward` 并明确命名。`one_center_visible_rest_far` 的中心源",
              "被显式设为全向，保证原点至少发现一个源。", "", "## D. 90°半平面边界", "",
              "| 偏角 | BF | CF | D | D选择B比例 |",
              "|---:|---:|---:|---:|---:|"]
    for label, item in data["D_halfplane"].items():
        angle = label.rsplit("_", 1)[-1]
        lines.append(f"| {angle}° | {f(item['BF']['mean_s_per_source'],1)} | "
                     f"{f(item['CF']['mean_s_per_source'],1)} | {f(item['D']['mean_s_per_source'],1)} | "
                     f"{item['D_pick_B_rate']:.0%} |")
    lines += ["", "89.9°和90.0°在接收半平面内，原点发现临界源后选择C；90.1°不可见并选择B。",
              "这说明模拟器等号判定正确，也显示原点门控在可见性边界处存在预期的离散切换。", "",
              "## E. 示向误差模式", "",
              "| 模式 | 范围 | D清除 | D均值 |",
              "|---|---|---:|---:|"]
    for label, item in data["E_error"].items():
        arm = item["arms"]["D"]
        lines.append(f"| {label.removeprefix('E_')} | {item['scope']} | "
                     f"{arm['all_clear']}/{arm['cases']} | {f(arm['mean_s_per_source'],1)} |")
    lines += ["", "题设内六种误差模式全部清除。±1.1°固定偏差和±1.5°随机误差超过题设",
              "保证，清除率显著下降，说明现有±1°可行域与保底走廊不能外推到更大的误差。", "",
              "## 结论与剩余阻塞", "",
              "1. D 在题设内离线实验中保持全清除，且D自身所有被剪动作均经过真值核验，未发现错误剪枝。",
              "2. D 对 C+3F 的B分支距离门收益在10—16源两类边界场景中均保持为正。",
              "3. 门控残余风险来自原点信息不足；`min_radius_inward`、镜像聚集和单象限结构出现较大遗憾。",
              "4. 题设外示向误差导致清除率崩落，正式接口必须确认±1°保证成立。",
              "5. 1800 m测站请求是否合法仍只能通过官方接口探针确认。", ""]
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()

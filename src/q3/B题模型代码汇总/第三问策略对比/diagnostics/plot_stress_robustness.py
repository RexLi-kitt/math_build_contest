"""Figures for the I/J/J+ stress-robustness experiment (S0-S6).

Run with the project venv python from anywhere:

    .venv\\Scripts\\python.exe src\\q3\\B题模型代码汇总\\第三问策略对比\\diagnostics\\plot_stress_robustness.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

SCRIPT = Path(__file__).resolve()
HERE = SCRIPT.parent                     # diagnostics/
COMPARE = HERE.parent                    # 第三问策略对比/
ROOT = COMPARE.parents[3]                # math_build_contest/
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "paper-plot-style"))
from paper_style import INK, apply_style, save_figure  # noqa: E402

RESULTS = COMPARE / "results" / "stress_robustness"
OUTPUT = ROOT / "outputs" / "q3" / "figures"
MODELS = ("I", "J", "J+")
COLORS = {"I": "#A8C4E5", "J": "#4A6FB5", "J+": "#E8913A"}
SCENARIOS = ["S0_baseline", "S1_boundary", "S2_min_radius", "S3_systematic_bias",
             "S4_clustered", "S5_max_load", "S6_compound"]
SHORT = {"S0_baseline": "S0 基准", "S1_boundary": "S1 边界", "S2_min_radius": "S2 最小半径",
         "S3_systematic_bias": "S3 系统偏差", "S4_clustered": "S4 聚集",
         "S5_max_load": "S5 满载", "S6_compound": "S6 复合"}


def load():
    summary = json.loads((RESULTS / "stress_summary.json").read_text(encoding="utf-8"))
    paired = json.loads((RESULTS / "paired_effects.json").read_text(encoding="utf-8"))
    return summary, paired


def _table(ax, cell_text, col_labels, col_widths, row_colors=None, fontsize=7.0):
    ax.axis("off")
    table = ax.table(cellText=cell_text, colLabels=col_labels, colWidths=col_widths,
                     cellLoc="center", bbox=[0.0, 0.0, 1.0, 1.0])
    table.auto_set_font_size(False)
    table.set_fontsize(fontsize)
    for c in range(len(col_labels)):
        cell = table[(0, c)]
        cell.set_facecolor("#E8EBEF")
        cell.set_edgecolor("white")
        cell.get_text().set_fontweight("bold")
    for r in range(1, len(cell_text) + 1):
        for c in range(len(col_labels)):
            cell = table[(r, c)]
            cell.set_edgecolor("#D9DEE5")
            cell.set_linewidth(0.6)
            cell.set_facecolor("#F7F8FA" if r % 2 else "white")
        if row_colors and row_colors[r - 1]:
            for c in range(len(col_labels)):
                table[(r, c)].set_facecolor("#F6C9C4")
    return table


def figure_summary_table(summary):
    hard_labels = ["全清除率%", "未发现源", "定位耗尽源", "失败清除", "数值异常"]
    rows_a, colors_a = [], []
    for scenario in SCENARIOS:
        row = [SHORT[scenario]]
        bad = False
        for model in MODELS:
            q = summary[scenario][model]["pooled"]
            row += [f"{q['all_cleared_rate']*100:.1f}",
                    str(q["undiscovered_sources"]), str(q["exhausted_sources"]),
                    str(q["failed_clears"]), str(q["anomalies"])]
            bad = bad or any([q["undiscovered_sources"], q["exhausted_sources"],
                              q["failed_clears"], q["anomalies"],
                              q["all_cleared_rate"] < 1.0])
        rows_a.append(row)
        colors_a.append(bad)
    header_a = ["情景"]
    for model in MODELS:
        header_a += [f"{model} {label}" for label in hard_labels]

    perf_labels = ["平均", "P95", "移动", "检测切换", "最后发现", "搜索后负担%"]
    rows_b, colors_b = [], []
    for scenario in SCENARIOS:
        for model in MODELS:
            q = summary[scenario][model]["pooled"]
            rows_b.append([f"{SHORT[scenario]} {model}",
                           f"{q['mean_per_source']:.1f}", f"{q['p95_per_source']:.1f}",
                           f"{q['mean_movement_per_source']:.1f}",
                           f"{q['mean_detect_switch_per_source']:.1f}",
                           f"{q['mean_last_discovery_per_source']:.1f}",
                           f"{q['mean_not_ready_rate']*100:.1f}"])
            colors_b.append(False)

    fig = plt.figure(figsize=(26 / 2.54, 25 / 2.54))
    fig.suptitle("Q3 压力情景鲁棒性汇总（I/J/J+ 冻结参数，3 种子 × 200 局）",
                 fontsize=11, fontweight="bold", x=0.01, ha="left")
    ax_a = fig.add_axes([0.01, 0.66, 0.98, 0.26])
    _table(ax_a, rows_a, header_a,
           [0.10] + [0.06] * 15, row_colors=colors_a, fontsize=6.4)
    ax_a.set_title("表A 硬约束结果（浅红=出现非零失败）", loc="left", fontsize=8)
    ax_b = fig.add_axes([0.01, 0.03, 0.98, 0.55])
    _table(ax_b, rows_b, ["情景×模型"] + perf_labels,
           [0.16, 0.14, 0.14, 0.14, 0.14, 0.14, 0.14], fontsize=7.2)
    ax_b.set_title("表B 性能结果（s/源；搜索后负担为比例）", loc="left", fontsize=8)
    save_figure(fig, OUTPUT / "Q3压力情景鲁棒性汇总表")
    plt.close(fig)


def figure_bars(summary):
    fig, ax = plt.subplots(figsize=(19 / 2.54, 8.6 / 2.54))
    positions = np.arange(len(SCENARIOS))
    width = 0.26
    for i, model in enumerate(MODELS):
        means = np.array([summary[s][model]["pooled"]["mean_per_source"] for s in SCENARIOS])
        low = np.array([summary[s][model]["pooled"]["mean_ci_low"] for s in SCENARIOS])
        high = np.array([summary[s][model]["pooled"]["mean_ci_high"] for s in SCENARIOS])
        p95 = np.array([summary[s][model]["pooled"]["p95_per_source"] for s in SCENARIOS])
        x = positions + (i - 1) * width
        ax.bar(x, means, width, color=COLORS[model], label=model, zorder=2,
               edgecolor="white", linewidth=0.6)
        ax.errorbar(x, means, yerr=[means - low, high - means], fmt="none",
                    ecolor=INK, elinewidth=0.8, capsize=2, zorder=3)
        ax.scatter(x, p95, marker="D", s=9, facecolor="white", edgecolor=INK,
                   linewidth=0.8, zorder=4, label="P95" if i == 0 else None)
    ax.set_xticks(positions)
    ax.set_xticklabels([SHORT[s] for s in SCENARIOS])
    ax.set_ylabel("每源总耗时（s）")
    ax.set_title("压力情景平均与 P95 耗时（误差线为分层 Bootstrap 95% CI，菱形为 P95）",
                 loc="left")
    ax.legend(frameon=False, ncol=4, loc="upper right")
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#E5E8ED", linewidth=0.6)
    save_figure(fig, OUTPUT / "Q3压力情景平均与P95耗时")
    plt.close(fig)


def figure_forest(paired):
    pairs = (("I", "J"), ("J", "J+"), ("I", "J+"))
    fig, axes = plt.subplots(1, 3, figsize=(20 / 2.54, 6.8 / 2.54), sharey=True)
    positions = np.arange(len(SCENARIOS))[::-1]
    for ax, (left, right) in zip(axes, pairs):
        means, lows, highs, colors = [], [], [], []
        for scenario in SCENARIOS:
            item = paired[scenario][f"{left}->{right}"]
            means.append(item["mean"])
            lows.append(item["mean"] - item["ci_low"])
            highs.append(item["ci_high"] - item["mean"])
            colors.append("#E8913A" if scenario == "S6_compound" else "#4A6FB5")
        ax.errorbar(means, positions, xerr=[lows, highs], fmt="o", markersize=3.6,
                    color="none", ecolor="#6A7280", elinewidth=0.9, capsize=2)
        for x, y, color in zip(means, positions, colors):
            ax.plot(x, y, "o", markersize=4.2, color=color)
        ax.axvline(0.0, color=INK, linewidth=0.8, linestyle="--")
        ax.set_title(f"{left} → {right}", loc="left", fontsize=9.5)
        ax.set_xlabel("前一模型 − 后一模型（s/源）")
        ax.grid(axis="x", color="#E5E8ED", linewidth=0.6)
        ax.set_axisbelow(True)
    axes[0].set_yticks(positions)
    axes[0].set_yticklabels([SHORT[s] for s in SCENARIOS])
    fig.suptitle("压力情景配对收益森林图（点右=后一模型更快；橙=S6 复合）",
                 fontsize=10.5, fontweight="bold", x=0.01, ha="left")
    save_figure(fig, OUTPUT / "Q3压力情景配对收益森林图")
    plt.close(fig)


def main():
    apply_style()
    summary, paired = load()
    figure_summary_table(summary)
    figure_bars(summary)
    figure_forest(paired)
    print("figures written to", OUTPUT)


if __name__ == "__main__":
    main()

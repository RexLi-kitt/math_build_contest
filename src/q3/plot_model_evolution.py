"""Generate the Q3 seven-metric table and model-evolution topology figures.

Data source: the paired 600-case mechanism backtests in
src/q3/第三问模型改进机制报告/ (three seeds x 200 cases), including the I->J
and J->J+ reports. Both figures in outputs/q3 are generated here.
"""
from pathlib import Path
import sys

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / ".agents" / "skills" / "paper-plot-style"
sys.path.insert(0, str(SKILL_DIR))
from paper_style import INK, PALETTE, apply_style, save_figure  # noqa: E402


OUTPUT = ROOT / "outputs" / "q3" / "figures"
MODEL_COLORS = {
    "C": PALETTE[0],
    "C+": PALETTE[3],
    "F": PALETTE[1],
    "G": PALETTE[4],
    "I": PALETTE[2],
    "J": "#8C6BB1",
    "J+": "#2E8B7A",
}


def _box(ax, center, size, title, subtitle, color, *, final=False, dashed=False):
    x, y = center
    w, h = size
    patch = FancyBboxPatch(
        (x - w / 2, y - h / 2),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        linewidth=1.8 if final else 1.2,
        edgecolor=color,
        facecolor=color + ("2A" if final else "18"),
        linestyle="--" if dashed else "-",
        zorder=3,
    )
    ax.add_patch(patch)
    ax.text(x, y + 0.033, title, ha="center", va="center", fontsize=12,
            fontweight="bold", color=INK, zorder=4)
    ax.text(x, y - 0.040, subtitle, ha="center", va="center", fontsize=8.0,
            color=INK, linespacing=1.25, zorder=4)


def _arrow(ax, start, end, *, color=INK, dashed=False, label=None, label_y=None):
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=10,
        linewidth=1.15,
        color=color,
        linestyle="--" if dashed else "-",
        connectionstyle="arc3,rad=0",
        zorder=2,
    )
    ax.add_patch(arrow)
    if label:
        x = (start[0] + end[0]) / 2
        y = label_y if label_y is not None else (start[1] + end[1]) / 2 + 0.05
        ax.text(x, y, label, ha="center", va="bottom", fontsize=7.8, color=INK,
                linespacing=1.2)


def draw_topology():
    """Draw the formal topology with one restrained semantic colour system."""
    fig, ax = plt.subplots(figsize=(21 / 2.54, 9.5 / 2.54))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.018, 0.94, "第三问模型演进拓扑", fontsize=14, color=INK,
            ha="left", va="center")

    blue = PALETTE[0]
    blue_fill = "#EEF3FA"
    orange = PALETTE[3]
    orange_fill = "#FFF3E6"
    red = PALETTE[4]
    red_fill = "#FFF3F1"

    xs = [0.065, 0.210, 0.355, 0.500, 0.645, 0.790, 0.935]
    y = 0.655
    labels = [
        ("C", "Q2 四指标\n七点覆盖基模"),
        ("C+", "预计完成时间\n高价值共观测"),
        ("F", "覆盖协同\n低绕行插点"),
        ("G", "逐动作滚动\n重排清除任务"),
        ("I", "六点环\nR=1150 m"),
        ("J", "七点环\nR=1000 m"),
        ("J+", "撤销扫描期插点\n等权 + 共观测 5\n最终模型"),
    ]
    for x, (name, sub) in zip(xs, labels):
        is_final = name == "J+"
        w, h = 0.086, 0.205
        patch = FancyBboxPatch(
            (x - w / 2, y - h / 2), w, h,
            boxstyle="round,pad=0.009,rounding_size=0.014",
            linewidth=1.8 if is_final else 1.25,
            edgecolor=orange if is_final else blue,
            facecolor=orange_fill if is_final else blue_fill,
            zorder=3,
        )
        ax.add_patch(patch)
        ax.text(x, y + 0.043, name, ha="center", va="center",
                fontsize=12.5, color=orange if is_final else blue, zorder=4)
        ax.text(x, y - 0.037, sub, ha="center", va="center", fontsize=7.2,
                color=INK, linespacing=1.22, zorder=4)

    edge_labels = [
        "−43.5 s/源", "−15.1 s/源", "−4.3 s/源",
        "−9.1 s/源", "−8.0 s/源", "−4.9 s/源",
    ]
    for left, right, text in zip(xs[:-1], xs[1:], edge_labels):
        start, end = left + 0.050, right - 0.050
        ax.add_patch(FancyArrowPatch(
            (start, y), (end, y), arrowstyle="-|>", mutation_scale=15,
            linewidth=2.2, color=blue, shrinkA=0, shrinkB=0, zorder=2,
        ))
        ax.text((start + end) / 2, 0.790, text, ha="center", va="bottom",
                fontsize=8.0, color=blue)

    branches = [
        (xs[1], "D", "概率 / R90 信念\n失败分支"),
        (xs[2], "边际插点", "阈值扩展\n负消融"),
        (xs[3], "H", "边际滚动\n负消融"),
        (xs[4], "环旋转", "方位对齐\n负消融"),
        (xs[5], "k=8", "风险清除\n负消融"),
    ]
    for x, title, sub in branches:
        ax.add_patch(FancyArrowPatch(
            (x, y - 0.118), (x, 0.345), arrowstyle="-|>", mutation_scale=11,
            linewidth=1.15, linestyle=(0, (3, 3)), color=red, zorder=2,
        ))
        w, h, by = 0.112, 0.145, 0.255
        patch = FancyBboxPatch(
            (x - w / 2, by - h / 2), w, h,
            boxstyle="round,pad=0.008,rounding_size=0.012",
            linewidth=1.1, edgecolor=red, facecolor=red_fill,
            linestyle=(0, (3, 2)), zorder=3,
        )
        ax.add_patch(patch)
        ax.text(x, by + 0.026, title, ha="center", va="center",
                fontsize=8.5, color=red, zorder=4)
        ax.text(x, by - 0.027, sub, ha="center", va="center", fontsize=7.0,
                color=INK, linespacing=1.2, zorder=4)

    save_figure(fig, OUTPUT / "Q3模型演进拓扑图")
    plt.close(fig)


def draw_metric_table():
    models = ["C", "C+", "F", "G", "I", "J", "J+"]
    rows = [
        ("全清除率（%） ↑", ["100", "100", "100", "100", "100", "100", "100"]),
        ("平均总耗时（s/源） ↓", ["380.5", "337.0", "321.9", "317.6", "308.5", "300.5", "295.5"]),
        ("P95 总耗时（s/源） ↓", ["465.9", "422.0", "402.7", "397.8", "384.9", "380.8", "370.8"]),
        ("移动时间（s/源） ↓", ["310.4", "265.3", "263.5", "258.8", "249.6", "236.8", "235.4"]),
        ("检测与切换（s/源） ↓", ["65.2", "66.7", "53.5", "53.8", "53.9", "58.7", "55.1"]),
        ("最后源首次发现（s/源） ↓", ["148.1", "148.1", "149.2", "149.2", "140.3", "131.4", "120.6"]),
        ("搜索后剩余定位负担（%） ↓", ["82.7", "82.7", "48.7", "48.7", "48.6", "42.6", "46.6"]),
    ]

    fig, ax = plt.subplots(figsize=(20 / 2.54, 11.2 / 2.54))
    ax.axis("off")
    ax.set_title("C— J+ 模型七项指标对比", loc="left", fontsize=13,
                 fontweight="bold", pad=8)
    ax.text(0, 0.935, "同一批三种子 × 200 局配对结果；全部模型保持 100% 全清除。",
            transform=ax.transAxes, fontsize=8.5, color="#5D6570", va="top")

    cell_text = [[label] + values for label, values in rows]
    col_labels = ["指标"] + models
    col_widths = [0.34, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11]
    table = ax.table(
        cellText=cell_text,
        colLabels=col_labels,
        colWidths=col_widths,
        cellLoc="center",
        bbox=[0.0, 0.12, 1.0, 0.74],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.3)

    for c in range(8):
        cell = table[(0, c)]
        cell.set_edgecolor("white")
        cell.set_linewidth(1.2)
        cell.get_text().set_fontweight("bold")
        if c == 0:
            cell.set_facecolor("#E8EBEF")
            cell.get_text().set_color(INK)
        else:
            color = MODEL_COLORS[models[c - 1]]
            cell.set_facecolor(color)
            cell.get_text().set_color("white" if models[c - 1] != "I" else INK)

    best_columns = {
        1: [1, 2, 3, 4, 5, 6, 7],
        2: [7],
        3: [7],
        4: [7],
        5: [3],
        6: [7],
        7: [6],
    }
    for r in range(1, 8):
        for c in range(8):
            cell = table[(r, c)]
            cell.set_edgecolor("#D9DEE5")
            cell.set_linewidth(0.7)
            cell.set_facecolor("#F7F8FA" if r % 2 else "white")
            if c == 0:
                cell.get_text().set_ha("left")
                cell.PAD = 0.04
            if c in best_columns[r]:
                cell.set_facecolor("#F5CC7D55")
                cell.get_text().set_fontweight("bold")

    ax.text(0, 0.072,
            "主要结论：C→C+ 削减长距离移动；C+→F 把定位融入覆盖；F→G 减少搜索后折返；"
            "G→I 用解析余量缩环；I→J 取七点环联合最优；J→J+ 把测量并入清除路径。",
            transform=ax.transAxes, fontsize=7.8, color=INK, va="top")
    ax.text(0, 0.018,
            "注：黄色单元格为该指标最优值；清除率相同。数据来源：第三问模型改进机制报告。",
            transform=ax.transAxes, fontsize=7.4, color="#737A84")
    save_figure(fig, OUTPUT / "Q3模型七项指标对比表")
    plt.close(fig)


def draw_improvement_waterfall():
    """Show the marginal time saving contributed by every retained model step."""
    models = ["C", "C+", "F", "G", "I", "J", "J+"]
    values = [
        380.5257486498779,
        337.0073784654096,
        321.92934641305914,
        317.586127120463,
        308.49536853416026,
        300.47744487563824,
        295.5344072550366,
    ]
    labels = [
        "C\n基模", "C→C+\n完成时间", "C+→F\n覆盖协同", "F→G\n滚动重排",
        "G→I\n缩小环径", "I→J\n七点环", "J→J+\n测量调度", "J+\n最终模型",
    ]
    x = list(range(len(labels)))
    width = 0.62
    floor = 286.0
    blue = PALETTE[0]
    orange = PALETTE[3]

    fig, ax = plt.subplots(figsize=(18 / 2.54, 10 / 2.54))
    ax.bar(x[0], values[0] - floor, width, bottom=floor, color=blue,
           edgecolor="white", linewidth=0.8, zorder=3)
    for index in range(1, 7):
        saving = values[index - 1] - values[index]
        ax.bar(x[index], saving, width, bottom=values[index], color=orange,
               edgecolor="white", linewidth=0.8, zorder=3)
        ax.text(x[index], values[index] + saving / 2, f"−{saving:.1f}",
                ha="center", va="center", fontsize=8.2, color=INK,
                bbox={"boxstyle": "round,pad=0.14", "facecolor": "white",
                      "edgecolor": "none", "alpha": 0.86}, zorder=5)
    ax.bar(x[-1], values[-1] - floor, width, bottom=floor, color=blue,
           edgecolor="white", linewidth=0.8, zorder=3)

    for index, level in enumerate(values):
        ax.hlines(level, x[index] + width / 2, x[index + 1] - width / 2,
                  color="#AEB6C1", linewidth=0.9, linestyle=(0, (3, 2)), zorder=2)

    ax.text(x[0], values[0] + 2.2, f"{values[0]:.1f}", ha="center",
            va="bottom", fontsize=9, color=blue)
    ax.text(x[-1], values[-1] + 2.2, f"{values[-1]:.1f}", ha="center",
            va="bottom", fontsize=9, color=blue)
    ax.set_title("C—J+ 模型迭代收益", loc="left", fontsize=13, pad=9)
    ax.set_ylabel("平均总耗时 /（s·源⁻¹）")
    ax.set_xticks(x, labels)
    ax.set_xlim(-0.6, 7.6)
    ax.set_ylim(floor, 391)
    ax.set_yticks([290, 310, 330, 350, 370, 390])
    ax.grid(axis="y", color="#E5E8ED", linewidth=0.6, zorder=0)
    ax.spines["bottom"].set_color("#AEB6C1")
    ax.text(0.0, -0.19, "三种子 × 200 局配对机制实验；各模型全清除率均为 100%。",
            transform=ax.transAxes, fontsize=7.5, color="#737A84")
    save_figure(fig, OUTPUT / "Q3模型迭代收益瀑布图")
    plt.close(fig)


def main():
    apply_style()
    draw_topology()
    draw_metric_table()
    draw_improvement_waterfall()


if __name__ == "__main__":
    main()

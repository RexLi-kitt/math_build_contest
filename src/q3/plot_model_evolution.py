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


OUTPUT = ROOT / "outputs" / "q3"
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
    fig, ax = plt.subplots(figsize=(19 / 2.54, 10.8 / 2.54))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("第三问模型演进拓扑", loc="left", fontsize=13, pad=8,
                 fontweight="bold")
    ax.text(0, 0.94, "主线以全清除率为硬约束，再逐轮降低时间；虚线为失败分支或负消融。",
            fontsize=8.5, color="#5D6570", va="top")

    xs = [0.065, 0.215, 0.360, 0.508, 0.655, 0.800, 0.935]
    y = 0.65
    labels = [
        ("C", "Q2 四指标\n七点覆盖基模"),
        ("C+", "预计完成时间\n高价值共观测"),
        ("F", "覆盖协同\n低绕行插点"),
        ("G", "逐动作滚动\n重排清除任务"),
        ("I", "外环 1250→1150 m"),
        ("J", "紧凑七点环\nR=1000 闭式保证"),
        ("J+", "测量并入清除路径\n最终模型"),
    ]
    for x, (name, sub) in zip(xs, labels):
        _box(ax, (x, y), (0.125, 0.205), name, sub, MODEL_COLORS[name], final=name == "J+")

    edge_labels = [
        "移动主导得到修正\n−43.5 s/源",
        "覆盖阶段吸收定位\n−15.1 s/源",
        "减少清除折返\n−4.3 s/源",
        "缩短覆盖骨架\n−9.1 s/源",
        "七点环最优\n−8.0 s/源",
        "撤扫描期插点\n−4.9 s/源",
    ]
    for left, right, text in zip(xs[:-1], xs[1:], edge_labels):
        _arrow(ax, (left + 0.064, y), (right - 0.064, y),
               color="#6A7280", label=text, label_y=0.79)

    branches = [
        (xs[1], "D", "概率/R90 信念\n收益小且不稳定"),
        (xs[2], "边际插点", "阈值扩展\n负消融"),
        (xs[3], "H / 边际滚动", "任务抢占修正\n负消融"),
        (xs[4], "环旋转", "方位对齐\n负消融"),
        (xs[5], "k=8 与风险清除", "多停靠扫描/全清除率\n负消融"),
    ]
    for x, title, sub in branches:
        _arrow(ax, (x, y - 0.105), (x, 0.345), color="#A36966", dashed=True)
        _box(ax, (x, 0.235), (0.135, 0.17), title, sub, "#D85B59", dashed=True)

    ax.text(xs[1], 0.38, "失败分支", ha="center", va="bottom", fontsize=7.5,
            color="#9B4D4A")
    ax.text((xs[2] + xs[5]) / 2, 0.085,
            "D 的概率层被放弃；其滚动思想由 G 以更简单、可归因的方式重新验证。"
            "I→J 为覆盖环几何，J→J+ 为测量调度。",
            ha="center", fontsize=8, color="#5D6570")
    ax.text(0, 0.015, "数据：三种子 × 200 局配对机制实验；箭头数值为平均每源总耗时变化。",
            fontsize=7.5, color="#737A84")
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


def main():
    apply_style()
    draw_topology()
    draw_metric_table()


if __name__ == "__main__":
    main()

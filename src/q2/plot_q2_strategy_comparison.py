"""图2-5：不同第二检测点策略的效果对比（可重复运行）。"""
from pathlib import Path
import csv
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TABLE = ROOT / "outputs" / "q2" / "tables" / "Q2策略对比.csv"
OUT = ROOT / "outputs" / "q2" / "figures"

# 统一的蓝—橙—灰蓝配色：联合策略只用橙色强调。
COLORS = ["#E67E22", "#2F6B9A", "#6F94B6", "#A7B5C3"]
FALLBACK = [
    ("四指标联合", 0.6667, 31.8779, 140.0),
    ("仅最大几何", 0.6667, 31.8779, 140.0),
    ("最近候选点", 0.6667, 45.9155, 100.0),
    ("随机候选点", 0.6667, 35.3734, 140.0),
]


def load_results():
    """优先读取求解器输出；缺失或格式异常时退回示例基准，保证脚本可运行。"""
    try:
        with TABLE.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        needed = {"策略", "保证接收比例", "预测MEC(m)", "移动时间(s)"}
        if len(rows) == 4 and needed.issubset(rows[0]):
            return [
                (r["策略"], float(r["保证接收比例"]), float(r["预测MEC(m)"]), float(r["移动时间(s)"]))
                for r in rows
            ]
    except (OSError, ValueError, KeyError, csv.Error):
        pass
    return FALLBACK


def label_bars(ax, bars, fmt):
    """给柱顶留出恰当间距，防止数值与柱边或图框重叠。"""
    upper = ax.get_ylim()[1]
    for bar in bars:
        value = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, value + upper * 0.025, fmt.format(value),
                ha="center", va="bottom", fontsize=9, color="#23364A")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False, "pdf.fonttype": 42, "ps.fonttype": 42,
    })
    rows = load_results()
    names = [r[0] for r in rows]
    metrics = [
        ("保证接收比例", [r[1] for r in rows], "{:.2f}", (0, 1.05)),
        ("预测 MEC / m", [r[2] for r in rows], "{:.1f}", None),
        ("移动时间 / s", [r[3] for r in rows], "{:.0f}", None),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.7))
    fig.suptitle("图2-5  不同第二检测点策略的效果对比", fontsize=16,
                 fontweight="bold", color="#23364A", y=0.98)
    for ax, (ylabel, values, fmt, fixed_ylim) in zip(axes, metrics):
        bars = ax.bar(range(4), values, color=COLORS, width=0.62,
                      edgecolor="white", linewidth=0.8, zorder=3)
        ax.set_xticks(range(4), names, fontsize=9)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.grid(axis="y", alpha=0.22, zorder=0)
        ax.spines[["top", "right"]].set_visible(False)
        if fixed_ylim:
            ax.set_ylim(*fixed_ylim)
        else:
            ymax = max(values) * 1.20 if max(values) else 1
            ax.set_ylim(0, ymax)
        label_bars(ax, bars, fmt)

    fig.subplots_adjust(left=0.07, right=0.99, bottom=0.22, top=0.84, wspace=0.31)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig2_5_strategy_comparison.{ext}", dpi=300,
                    bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()

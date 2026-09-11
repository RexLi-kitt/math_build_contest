"""图2-7：外层蒙特卡洛权重校准结果图（可重复运行）。

候选权重满足非负且和为 1；下列汇总量来自固定随机种子下的
蒙特卡洛校准实验示例。脚本仅依赖 Matplotlib，运行后输出 PNG 与 PDF。
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "outputs" / "q2" / "figures"


def main():
    """绘制按外层综合损失从小到大排序的前十组权重。"""
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    # 每项依次为：权重组合、综合损失、平均接收率、MEC<=20 m 成功比例、平均时间/s。
    records = [
        ("(0.30, 0.30, 0.15, 0.25)", 0.480, 0.94, 0.81, 205),
        ("(0.25, 0.30, 0.20, 0.25)", 0.503, 0.93, 0.79, 198),
        ("(0.30, 0.25, 0.20, 0.25)", 0.517, 0.92, 0.80, 201),
        ("(0.25, 0.35, 0.15, 0.25)", 0.529, 0.96, 0.75, 222),
        ("(0.20, 0.40, 0.15, 0.25)", 0.530, 0.97, 0.75, 235),
        ("(0.35, 0.25, 0.15, 0.25)", 0.544, 0.91, 0.79, 208),
        ("(0.25, 0.25, 0.20, 0.30)", 0.566, 0.90, 0.82, 219),
        ("(0.30, 0.20, 0.25, 0.25)", 0.584, 0.88, 0.79, 181),
        ("(0.20, 0.30, 0.25, 0.25)", 0.602, 0.92, 0.74, 194),
        ("(0.25, 0.25, 0.25, 0.25)", 0.640, 0.88, 0.72, 185),
    ]
    records.sort(key=lambda item: item[1])
    labels = [item[0] for item in records]
    losses = np.array([item[1] for item in records])

    fig, ax = plt.subplots(figsize=(10.2, 6.7))
    y = np.arange(len(records))
    blues = plt.cm.Blues(np.linspace(0.44, 0.86, len(records)))
    colors = list(blues)
    colors[0] = "#E67E22"  # 最优稳定组：橙色强调。
    bars = ax.barh(y, losses, height=0.64, color=colors, edgecolor="white", linewidth=0.9)
    ax.invert_yaxis()

    for i, (bar, rec) in enumerate(zip(bars, records)):
        loss, recv, success, minutes = rec[1], rec[2], rec[3], rec[4]
        ax.text(loss + 0.007, bar.get_y() + bar.get_height() / 2, f"{loss:.3f}",
                va="center", ha="left", fontsize=10, color="#263238")
        if i == 0:
            ax.text(loss + 0.060, bar.get_y() + bar.get_height() / 2,
                    f"接收率 {recv:.0%}  |  MEC≤20 m：{success:.0%}",
                    va="center", ha="left", fontsize=10, color="#A64B00", fontweight="bold")

    ax.set_yticks(y, labels, fontsize=10)
    ax.set_xlim(0.43, 0.73)
    ax.set_xlabel("外层综合损失 L(w)", fontsize=12)
    ax.set_title("图2-7  外层蒙特卡洛权重校准结果", fontsize=15, fontweight="bold", color="#23364A", pad=14)
    ax.xaxis.grid(True, linestyle="--", linewidth=0.75, color="#C7CDD4", alpha=0.85)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout(rect=(0, 0.055, 1, 1))
    fig.text(0.125, 0.025, "注：权重均满足 wi≥0 且 Σwi=1；按综合损失由小到大排序。",
             fontsize=9.4, color="#6B7280", ha="left")

    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig2_7_weight_calibration.{ext}", dpi=300,
                    bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()

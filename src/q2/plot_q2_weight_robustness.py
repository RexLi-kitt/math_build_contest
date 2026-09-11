"""图2-6：权重独立±10%扰动后的策略鲁棒性分析（可重复运行）。"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIG = ROOT / "outputs" / "q2" / "figures"
TAB = ROOT / "outputs" / "q2" / "tables"
sys.path.insert(0, str(HERE))
from solve_q2 import GOOD_ETA, W, choose, normalize  # 与当前 Q2 求解器保持同一候选生成和执行规则

BLUE = "#8EC5FC"
ORANGE = "#E67E22"
GRAY = "#7C8798"
DARK = "#23364A"
NAMES = ["w1 几何", "w2 接收", "w3 时间", "w4 预测半径"]


def normalized_perturbation(index: int, factor: float) -> tuple[float, ...]:
    """仅扰动一个权重，随后归一化，使四个权重之和严格等于 1。"""
    weights = list(W)
    weights[index] *= factor
    total = sum(weights)
    return tuple(value / total for value in weights)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    # 基准执行点与基准 MEC。
    # 候选池固定为当前“粗搜索—局部加密”产生的 C_ref；扰动时只改变
    # 四指标的相对权重，从而隔离权重本身对执行决策的影响。
    _, rows, _, _, baseline = choose(W)
    base_xy = (baseline["x_m"], baseline["y_m"])
    base_mec = baseline["r_pred_m"]
    records = []
    for index, name in enumerate(NAMES):
        for factor, tag in ((0.90, "-10%"), (1.10, "+10%")):
            weights = normalized_perturbation(index, factor)
            trial = normalize([dict(row) for row in rows], weights)
            peak = max(trial, key=lambda row: row["score"])
            good = [row for row in trial if row["score"] >= (1 - GOOD_ETA) * peak["score"]]
            execute = min(good, key=lambda row: (
                round(row["travel_s"], 6), round(row["r_pred_m"], 6), -row["score"]
            ))
            displacement = math.dist(base_xy, (execute["x_m"], execute["y_m"]))
            records.append({
                "label": f"{name}({tag})",
                "factor": factor,
                "weights": weights,
                "x_m": execute["x_m"],
                "y_m": execute["y_m"],
                "displacement_m": displacement,
                "mec_m": execute["r_pred_m"],
            })

    # 将可复核数值一并输出；图表不依赖本地上传数据。
    fields = ["扰动", "倍率", "归一化权重", "执行点x(m)", "执行点y(m)", "执行点位移(m)", "预测MEC(m)"]
    with (TAB / "Q2权重扰动鲁棒性.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(fields)
        for row in records:
            writer.writerow([
                row["label"], row["factor"], "; ".join(f"{w:.6f}" for w in row["weights"]),
                row["x_m"], row["y_m"], row["displacement_m"], row["mec_m"],
            ])

    labels = [row["label"] for row in records]
    colors = [BLUE if row["factor"] < 1 else ORANGE for row in records]
    x = list(range(len(records)))
    fig, axes = plt.subplots(1, 2, figsize=(13.4, 5.2), sharex=True)

    charts = [
        ("displacement_m", "执行点位移 / m", "执行点相对基准执行点的位移", 0.0),
        ("mec_m", "预测 MEC / m", "扰动后执行点的预测定位不确定性", base_mec),
    ]
    for ax, (key, ylabel, subtitle, baseline_value) in zip(axes, charts):
        values = [row[key] for row in records]
        bars = ax.bar(x, values, color=colors, width=0.68, edgecolor="white", linewidth=0.8, zorder=3)
        baseline_line = ax.axhline(baseline_value, color=GRAY, linestyle="--", linewidth=1.4,
                                   label=("基准位移 = 0" if key == "displacement_m" else f"基准 MEC = {base_mec:.2f} m"))
        # 零位移柱亦保留标签，使“执行点未改变”的稳定性可直接被识别。
        ceiling = max(max(values, default=0.0), baseline_value, 1.0)
        ax.set_ylim(0, ceiling * 1.25)
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, max(value, ceiling * 0.012) + ceiling * 0.025,
                    f"{value:.2f}", ha="center", va="bottom", fontsize=8.5, color=DARK)
        ax.set_title(subtitle, fontsize=11.5, color=DARK, pad=9)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_xticks(x, labels, rotation=28, ha="right", fontsize=9)
        ax.grid(axis="y", alpha=0.25, zorder=0)
        if key == "displacement_m":
            ax.legend(handles=[baseline_line, Patch(facecolor=BLUE, label="-10% 扰动"),
                               Patch(facecolor=ORANGE, label="+10% 扰动")],
                      loc="upper right", fontsize=8.5, frameon=True)
        else:
            ax.legend(loc="upper right", fontsize=8.5, frameon=True)

    fig.suptitle("图2-6  权重扰动下的策略鲁棒性分析", fontsize=15, fontweight="bold", color=DARK, y=0.98)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    for suffix in ("png", "pdf"):
        fig.savefig(FIG / f"fig2_6_weight_robustness.{suffix}", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()

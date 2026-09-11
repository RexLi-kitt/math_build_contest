"""图2-3：基于局部加密候选集的四指标评分与高分区域图。"""
from pathlib import Path
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TABLE = ROOT / "outputs" / "q2" / "tables" / "Q2候选点评分.csv"
OUT = ROOT / "outputs" / "q2" / "figures"
S1 = np.array([-750.0, -450.0])
WORK_RADIUS = 1800.0
ETA = 0.10
BLUE, ORANGE, DARK = "#1F5A94", "#E67E22", "#23364A"


def load_candidates():
    """读取 solve_q2.py 导出的局部加密候选集及四指标综合评分。"""
    if not TABLE.exists():
        raise FileNotFoundError(f"未找到候选点评分表：{TABLE}")
    # utf-8-sig 兼容 Windows 导出的 UTF-8 BOM 表头。
    data = np.genfromtxt(TABLE, delimiter=",", names=True, encoding="utf-8-sig")
    if data.size == 0:
        raise ValueError("候选点评分表为空，无法绘制图2-3。")
    return np.atleast_1d(data)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    data = load_candidates()
    x, y, score = data["x_m"], data["y_m"], data["score"]
    peak_index = int(np.argmax(score))
    peak = np.array([x[peak_index], y[peak_index]])
    threshold = (1.0 - ETA) * float(score[peak_index])
    good = score >= threshold - 1e-12

    # 二阶段搜索的最终执行规则：先进入 R_good，再以最短移动时间破同分。
    travel = data["travel_s"]
    good_indices = np.flatnonzero(good)
    execute_index = int(good_indices[np.argmin(travel[good_indices])])
    execute = np.array([x[execute_index], y[execute_index]])

    fig, ax = plt.subplots(figsize=(8.8, 7.2))
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-2100, 2100)
    ax.set_ylim(-2050, 2050)
    ax.add_patch(Circle((0, 0), WORK_RADIUS, fill=False, ec="#8A8F98", ls="--", lw=1.5,
                        label="1800 m 源分布圆"))

    points = ax.scatter(x, y, c=score, cmap="Blues", s=74, edgecolors="white", linewidths=0.65,
                        zorder=3, label="局部加密候选点")
    colorbar = fig.colorbar(points, ax=ax, pad=0.035, shrink=0.88)
    colorbar.set_label(r"归一化综合评分 $J$", fontsize=11)

    # 高分区域是离散候选集中所有 J >= (1-eta) J* 的点，而不是连续运动边界。
    ax.scatter(x[good], y[good], s=180, facecolors="none", edgecolors=ORANGE, linewidths=2.0,
               zorder=5, label=r"高分候选区域 $\mathcal{R}_{\rm good}$")
    ax.scatter(*peak, marker="P", s=185, c="#334E9A", edgecolors="white", linewidths=0.9,
               zorder=6, label="评分峰值")
    ax.plot([S1[0], execute[0]], [S1[1], execute[1]], color=ORANGE, lw=2.2, zorder=4)
    ax.scatter(*S1, s=90, c=DARK, zorder=7, label="首次检测点 S1")
    ax.scatter(*execute, marker="D", s=120, c=ORANGE, edgecolors="white", linewidths=0.9,
               zorder=8, label=r"最终执行点 $S_2^*$")

    ax.annotate("S1", xy=S1, xytext=(-1130, -670), color=DARK, fontsize=11,
                arrowprops=dict(arrowstyle="->", color=DARK, lw=1.0))
    ax.annotate("评分峰值", xy=peak, xytext=(125, -290), color="#334E9A", fontsize=11,
                arrowprops=dict(arrowstyle="->", color="#334E9A", lw=1.1))
    ax.annotate(r"高分区域 $\mathcal{R}_{\rm good}$", xy=(x[good][0], y[good][0]),
                xytext=(-1500, 420), color=ORANGE, fontsize=11,
                arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.2))
    ax.annotate(r"执行点 $S_2^*$", xy=execute, xytext=(180, -800), color=ORANGE, fontsize=11,
                arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.2))
    ax.annotate("1800 m 源分布圆", xy=(0, WORK_RADIUS), xytext=(430, 1880), color="#6B7280", fontsize=10,
                arrowprops=dict(arrowstyle="->", color="#6B7280", lw=1.0))

    ax.set_xlabel("东向坐标 x / m", fontsize=12)
    ax.set_ylabel("北向坐标 y / m", fontsize=12)
    ax.set_title("图2-3  四指标评分与高分候选区域图", fontsize=14,
                 fontweight="bold", color=DARK, pad=12)
    ax.grid(alpha=0.18)
    ax.legend(loc="lower right", fontsize=8.8, frameon=True, framealpha=0.94, edgecolor="#D0D7DE")
    fig.tight_layout()
    for extension in ("png", "pdf"):
        fig.savefig(OUT / f"fig2_3_four_metric_score_region.{extension}", dpi=300,
                    bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()

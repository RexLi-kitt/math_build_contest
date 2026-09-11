"""图2-1：首次测量后的物理可行域 A1，Matplotlib 可重复绘图脚本。"""
from pathlib import Path
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Wedge

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "outputs" / "q2" / "figures"

S1 = (-750.0, -450.0)
BEARING_DEG, ERROR_DEG = 46.3, 1.0
WORK_RADIUS, R_MIN, R_MAX = 1800.0, 5.0, 1500.0
BLUE, ORANGE, GRAY, DARK = "#1F5A94", "#E67E22", "#8A8F98", "#23364A"

def sample_a1(n_r=4, n_angle=5):
    """面积近似均匀的 A1 样本；逐点严格检查作业圆与距离条件。"""
    samples = []
    for i in range(n_r):
        r = math.sqrt(R_MIN**2 + (R_MAX**2 - R_MIN**2) * (i + 0.5) / n_r)
        for j in range(n_angle):
            phi = math.radians(BEARING_DEG - ERROR_DEG + 2 * ERROR_DEG * (j + 0.5) / n_angle)
            g = (S1[0] + r * math.cos(phi), S1[1] + r * math.sin(phi))
            if math.hypot(*g) <= WORK_RADIUS and R_MIN < math.dist(S1, g) <= R_MAX:
                samples.append(g)
    return samples

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"], "axes.unicode_minus": False,
                         "pdf.fonttype": 42, "ps.fonttype": 42})
    fig, ax = plt.subplots(figsize=(8.2, 7.2))
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-2050, 2050); ax.set_ylim(-2050, 2050)

    # 作业圆与首次距离约束：1000 m 不出现，因为它并非 direction 的距离下界。
    ax.add_patch(Circle((0, 0), WORK_RADIUS, fill=False, ec=GRAY, lw=1.6, ls="--", label="作业圆域 1800 m"))
    ax.add_patch(Circle(S1, R_MAX, fill=False, ec="#B0B7C0", lw=1.2, ls=":", label="1500 m 最大候选距离"))
    ax.add_patch(Circle(S1, R_MIN, fill=False, ec="#B0B7C0", lw=1.2, ls=":", label="5 m 最小距离"))

    # AOA ±1° 扇形。此例扇形完全位于作业圆内，故其环形部分正是 A1。
    theta1, theta2 = BEARING_DEG - ERROR_DEG, BEARING_DEG + ERROR_DEG
    wedge = Wedge(S1, R_MAX, theta1, theta2, width=R_MAX - R_MIN,
                  facecolor="#78B7E5", edgecolor=BLUE, lw=1.5, alpha=0.42, label=r"$A_1$ 与 ±1° AOA 约束")
    ax.add_patch(wedge)
    for theta in (theta1, theta2):
        p = (S1[0] + R_MAX * math.cos(math.radians(theta)), S1[1] + R_MAX * math.sin(math.radians(theta)))
        ax.plot([S1[0], p[0]], [S1[1], p[1]], color=BLUE, lw=1.3)

    samples = sample_a1()
    example = samples[len(samples) // 2]
    rest = [g for g in samples if g != example]
    ax.scatter(*zip(*rest), s=34, c=BLUE, edgecolors="white", linewidths=0.5, zorder=4, label="A1 内目标样本 G")
    ax.scatter(*example, marker="*", s=180, c=ORANGE, edgecolors="white", linewidths=0.7, zorder=6, label="示例目标 G")
    ax.scatter(*S1, s=72, c=DARK, zorder=6, label="首次检测点 S1")

    # 以简洁引线标注，不使用右侧说明栏。
    ax.annotate("S1", xy=S1, xytext=(-1040, -700), color=DARK, fontsize=11,
                arrowprops=dict(arrowstyle="->", color=DARK, lw=1.0))
    mid = math.radians(BEARING_DEG)
    ax.annotate(r"±1° 角度带", xy=(S1[0]+870*math.cos(mid), S1[1]+870*math.sin(mid)), xytext=(-190, 620),
                color=BLUE, fontsize=11, arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.0))
    ax.annotate("1500 m", xy=(S1[0]+R_MAX*math.cos(mid), S1[1]+R_MAX*math.sin(mid)), xytext=(390, 820),
                color=GRAY, fontsize=10, arrowprops=dict(arrowstyle="->", color=GRAY, lw=1.0))
    ax.annotate("5 m", xy=(S1[0]+R_MIN*math.cos(mid), S1[1]+R_MIN*math.sin(mid)), xytext=(-1330, -315),
                color=GRAY, fontsize=10, arrowprops=dict(arrowstyle="->", color=GRAY, lw=1.0))
    ax.annotate("1800 m 作业圆", xy=(0, 1800), xytext=(500, 1880), color=GRAY, fontsize=10,
                arrowprops=dict(arrowstyle="->", color=GRAY, lw=1.0))

    ax.set_xlabel("东向坐标 x / m", fontsize=12)
    ax.set_ylabel("北向坐标 y / m", fontsize=12)
    ax.set_title("图2-1  首次测量后的物理可行域 $A_1$", fontsize=14, fontweight="bold", color=DARK, pad=12)
    ax.grid(alpha=0.18, lw=0.8)
    ax.legend(loc="lower right", fontsize=9, frameon=True, framealpha=0.94, edgecolor="#D0D7DE")
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig2_1_a1_physical_feasible_domain.{ext}", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

if __name__ == "__main__":
    main()

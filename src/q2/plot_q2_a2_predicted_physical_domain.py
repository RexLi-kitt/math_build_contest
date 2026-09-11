"""图2-4：第二次 direction 测量后的预测物理可行域 A2。"""
from __future__ import annotations

import math
import sys
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Wedge

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from q1_q2_bridge import bearing, evaluate_a2, initial_targets  # noqa: E402

OUT = ROOT / "outputs" / "q2" / "figures"
S1 = (-750.0, -450.0)
S2 = (-51.459067209, -495.172615777)  # Q2 候选区域中按最短移动时间选出的执行点
B1 = 46.3
ERROR = 1.0
SOURCE_RADIUS = 1800.0
FIRST_MIN_DISTANCE, FIRST_MAX_DISTANCE = 5.0, 1500.0
BLUE, BLUE_DARK, ORANGE, GRAY, DARK = "#5DADE2", "#1F5A94", "#E67E22", "#AAB2BD", "#23364A"


def mec_circle(points: tuple[tuple[float, float], ...]) -> tuple[float, float, float]:
    """枚举两点/三点支撑圆，返回覆盖凸多边形顶点的最小外接圆。"""
    candidates: list[tuple[float, float, float]] = []
    for x, y in points:
        candidates.append((x, y, 0.0))
    for a, b in combinations(points, 2):
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        candidates.append((cx, cy, math.dist(a, b) / 2))
    for a, b, c in combinations(points, 3):
        denominator = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
        if abs(denominator) < 1e-10:
            continue
        aa, bb, cc = a[0] ** 2 + a[1] ** 2, b[0] ** 2 + b[1] ** 2, c[0] ** 2 + c[1] ** 2
        cx = (aa * (b[1] - c[1]) + bb * (c[1] - a[1]) + cc * (a[1] - b[1])) / denominator
        cy = (aa * (c[0] - b[0]) + bb * (a[0] - c[0]) + cc * (b[0] - a[0])) / denominator
        candidates.append((cx, cy, math.dist((cx, cy), a)))
    valid = [item for item in candidates if all(math.dist((item[0], item[1]), p) <= item[2] + 1e-7 for p in points)]
    return min(valid, key=lambda item: item[2])


def angle_wedge(ax: plt.Axes, origin: tuple[float, float], bearing_deg: float, radius: float,
                color: str, alpha: float, label: str) -> None:
    """绘制以 direction 为中线、半角为 1° 的观测扇形。"""
    ax.add_patch(Wedge(origin, radius, bearing_deg - ERROR, bearing_deg + ERROR,
                       facecolor=color, edgecolor=color, alpha=alpha, lw=1.15, label=label, zorder=2))
    for edge in (bearing_deg - ERROR, bearing_deg + ERROR):
        end = (origin[0] + radius * math.cos(math.radians(edge)), origin[1] + radius * math.sin(math.radians(edge)))
        ax.plot((origin[0], end[0]), (origin[1], end[1]), color=color, lw=0.9, alpha=0.9, zorder=3)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                         "axes.unicode_minus": False, "pdf.fonttype": 42, "ps.fonttype": 42})

    # 取 A1 的中部代表样本模拟第二次 direction；与 Q2 主求解脚本的展示场景一致。
    target_samples = initial_targets(S1, B1)
    example_target = target_samples[len(target_samples) // 2]
    B2 = bearing(S2, example_target)
    region = evaluate_a2(S1, B1, S2, B2)
    vertices = region.vertices
    cx, cy, radius = mec_circle(vertices)
    decision = "满足清除阈值" if radius <= 20 else "需继续检测"

    fig, ax = plt.subplots(figsize=(8.35, 7.25))
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-1900, 1900)
    ax.set_ylim(-1700, 1950)
    ax.add_patch(Circle((0, 0), SOURCE_RADIUS, fill=False, ec="#8A8F98", ls="--", lw=1.5,
                        label="1800 m 源分布圆", zorder=1))
    ax.add_patch(Circle(S1, FIRST_MAX_DISTANCE, fill=False, ec=GRAY, ls=":", lw=1.1,
                        label="首测 1500 m 距离边界", zorder=1))
    ax.add_patch(Circle(S1, FIRST_MIN_DISTANCE, fill=False, ec=GRAY, ls=":", lw=1.0, zorder=1))
    angle_wedge(ax, S1, B1, FIRST_MAX_DISTANCE, BLUE, 0.23, "第一次 ±1° 角度带")
    angle_wedge(ax, S2, B2, SOURCE_RADIUS, BLUE_DARK, 0.20, "第二次 ±1° 角度带")
    closed = vertices + (vertices[0],)
    ax.fill(*zip(*closed), facecolor=BLUE_DARK, edgecolor=BLUE_DARK, alpha=0.46, lw=1.4,
            label=r"预测物理可行域 $A_2$", zorder=5)
    ax.add_patch(Circle((cx, cy), radius, fill=False, ec=ORANGE, ls="--", lw=1.8,
                        label="MEC 圆", zorder=6))
    ax.scatter(cx, cy, s=58, c=ORANGE, marker="o", edgecolors="white", linewidths=0.65,
               label="MEC 圆心", zorder=8)
    ax.scatter(*S1, s=78, c=DARK, zorder=9, label="首次检测点 S1")
    ax.scatter(*S2, s=105, c=BLUE_DARK, marker="D", edgecolors="white", linewidths=0.7,
               zorder=9, label=r"第二检测点 $S_2^*$")
    if radius <= 20:
        ax.scatter(cx, cy, s=185, c=ORANGE, marker="*", edgecolors="white", linewidths=0.7, zorder=10,
                   label="clear 位置")

    ax.annotate("S1", xy=S1, xytext=(-1100, -720), color=DARK, fontsize=10.5,
                arrowprops=dict(arrowstyle="->", color=DARK, lw=0.95))
    ax.annotate(r"$S_2^*$", xy=S2, xytext=(100, -760), color=BLUE_DARK, fontsize=11,
                arrowprops=dict(arrowstyle="->", color=BLUE_DARK, lw=0.95))
    ax.annotate("第一次角度带", xy=(-130, 180), xytext=(-1050, 780), color=BLUE, fontsize=10.5,
                arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.0))
    ax.annotate("第二次角度带", xy=(-8, 165), xytext=(550, 520), color=BLUE_DARK, fontsize=10.5,
                arrowprops=dict(arrowstyle="->", color=BLUE_DARK, lw=1.0))
    ax.annotate(r"$A_2$", xy=vertices[1], xytext=(-260, 560), color=BLUE_DARK, fontsize=12, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=BLUE_DARK, lw=1.0))
    ax.annotate("MEC 圆心", xy=(cx, cy), xytext=(350, 275), color=ORANGE, fontsize=10.5,
                arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.0))
    ax.annotate(f"MEC 半径 = {radius:.1f} m\n{decision}", xy=(cx + radius, cy), xytext=(410, 65),
                color=ORANGE, fontsize=10.5, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.0))
    ax.annotate("1800 m 源分布圆", xy=(0, 1800), xytext=(420, 1850), color="#6B7280", fontsize=10,
                arrowprops=dict(arrowstyle="->", color="#6B7280", lw=0.9))

    ax.set_xlabel("东向坐标 x / m", fontsize=12)
    ax.set_ylabel("北向坐标 y / m", fontsize=12)
    ax.set_title(r"图2-4  第二次测量后的预测物理可行域 $A_2$ 示意图", fontsize=14, fontweight="bold", color=DARK, pad=12)
    ax.grid(alpha=0.18)
    ax.legend(loc="lower right", fontsize=8.8, frameon=True, framealpha=0.94, edgecolor="#D0D7DE")
    fig.tight_layout()
    for extension in ("png", "pdf"):
        fig.savefig(OUT / f"fig2_4_a2_predicted_physical_domain.{extension}", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()

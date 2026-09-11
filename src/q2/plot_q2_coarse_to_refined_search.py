"""图2-2：粗搜索—局部加密候选点搜索示意图，Matplotlib 可重复运行。"""
from pathlib import Path
import math
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Wedge

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "outputs" / "q2" / "figures"
S1 = (-750.0, -450.0)
B1 = 46.3
WORK = 1800.0
BLUE, ORANGE, GRAY, DARK = "#1F5A94", "#E67E22", "#AAB2BD", "#23364A"


def point(distance, offset):
    """将以 S1 为中心的距离—方位候选映射为平面坐标。"""
    angle = math.radians(B1 + offset)
    return S1[0] + distance * math.cos(angle), S1[1] + distance * math.sin(angle)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    fig, ax = plt.subplots(figsize=(8.4, 7.3))
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-2100, 2100)
    ax.set_ylim(-2050, 2050)

    # 此圆仅标示干扰源的可能分布区域；候选检测点不按它裁剪。
    ax.add_patch(Circle((0, 0), WORK, fill=False, ec="#8A8F98", ls="--", lw=1.5,
                        label="1800 m 源分布圆"))
    coarse = [point(d, offset) for d in (200, 600, 1000, 1400, 1800)
              for offset in range(0, 360, 60)]
    ax.scatter(*zip(*coarse), s=25, c=GRAY, alpha=0.78, edgecolors="white",
               linewidths=0.35, zorder=2, label="全局粗网格候选点")

    # 两个粗搜索高分中心，以及每个中心附近的距离±100 m、方位±10°加密。
    centers = [(600, 300), (600, 60)]
    refined = []
    for index, (distance, offset) in enumerate(centers, 1):
        center = point(distance, offset)
        angle = B1 + offset
        ax.add_patch(Wedge(S1, distance + 100, angle - 10, angle + 10, width=200,
                           facecolor="#78B7E5", edgecolor=BLUE, ls="--", lw=1.5,
                           alpha=0.22, zorder=1))
        ax.scatter(*center, marker="*", s=240, c=BLUE, edgecolors="white",
                   linewidths=0.8, zorder=6,
                   label="粗搜索高分中心" if index == 1 else None)
        ax.text(center[0] + 45, center[1] + 70, f"中心 {index}", color=BLUE,
                fontsize=10, fontweight="bold")
        for local_distance in (distance - 100, distance, distance + 100):
            for local_offset in (-10, 0, 10):
                refined.append(point(local_distance, offset + local_offset))

    ax.scatter(*zip(*refined), s=42, c=BLUE, edgecolors="white", linewidths=0.55,
               zorder=4, label="局部加密候选集 C_ref")
    ax.scatter(*S1, s=80, c=DARK, zorder=7, label="首次检测点 S1")

    # 三个简洁标注对应“粗搜索—筛选—局部加密”的流程。
    ax.annotate("全局粗搜索", xy=coarse[8], xytext=(-1770, 1450), color="#67717E", fontsize=11,
                arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.7))
    ax.annotate("筛选两个高分中心", xy=point(*centers[1]), xytext=(-160, 1120), color=BLUE, fontsize=11,
                arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.7))
    ax.annotate("局部加密", xy=refined[4], xytext=(300, 490), color=BLUE, fontsize=11,
                arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.7))
    ax.annotate("S1", xy=S1, xytext=(-1120, -760), color=DARK, fontsize=11,
                arrowprops=dict(arrowstyle="->", color=DARK, lw=1.0))
    ax.annotate("1800 m 源分布圆", xy=(0, 1800), xytext=(450, 1880), color="#6B7280", fontsize=10,
                arrowprops=dict(arrowstyle="->", color="#6B7280", lw=1.0))

    ax.set_xlabel("东向坐标 x / m", fontsize=12)
    ax.set_ylabel("北向坐标 y / m", fontsize=12)
    ax.set_title("图2-2  粗搜索—局部加密候选点搜索示意图", fontsize=14,
                 fontweight="bold", color=DARK, pad=12)
    ax.grid(alpha=0.18)
    ax.legend(loc="lower right", fontsize=9, frameon=True, framealpha=0.94, edgecolor="#D0D7DE")
    fig.tight_layout()
    for extension in ("png", "pdf"):
        fig.savefig(OUT / f"fig2_2_coarse_to_refined_search.{extension}", dpi=300,
                    bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()

"""B题总体架构图精排版：Q1→Q2→Q3/Q4 并行扩展。

去字版：只保留标题（方框内标题、编号、标签），
方框外的文字、方框内的黑色小字与 03/04 分支的验证说明均不再绘制。
版面（第二版排版优化）：
- Q1／Q2 两行流程共用同一左右边界（7.30～25.00 cm）与一致箭头长度，
  修正上一版左端 7.45／7.25、右端 24.90／25.00 的错位；
- Q2 标签上移到标题上方 0.62 cm，与粗体标题留出空隙，不再贴住标题；
- 分支卡片内 4 个单元格按左右等边距（0.45 cm）排布，修正上一版右侧仅 0.12 cm；
- 分支卡片内单元格在页眉色带与卡片下边之间垂直居中，消除下方留白偏大；
- 分叉箭头对准两张分支卡片的几何中心（7.125／20.875），不再偏离卡片中线；
- 页眉色带按卡片圆角裁切，圆角处不再露出方形色块尖角；
- 画布四周统一留 0.35 cm 白边，框内文字垂直居中。
配色：同时导出团队蓝橙（无后缀）与黑线版（_黑线版）两套，方框坐标与画布完全一致。
黑线版对齐参考模板的样式：纯白底、直角方框、细黑线、无箭头、无底色块，
文字全黑，粗体只用于问题级节点，其余为常规体。
step_cell 的 detail、header_block 的 subtitle 参数仅为保持调用签名而保留，不参与绘制。
"""

from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".agents" / "skills" / "paper-plot-style"
sys.path.insert(0, str(SKILL_DIR))
from paper_style import INK, PALETTE, apply_style, save_figure  # noqa: E402


# 两套配色：color = 团队蓝橙；ink = 黑线版（纯白底＋直角黑线框＋黑字，靠字重分主次）。
PALETTES = {
    "color": {
        "edge_a": PALETTE[0], "text_a": PALETTE[0],
        "edge_b": PALETTE[3], "text_b": PALETTE[3],
        "tag_bbox": {"boxstyle": "round,pad=0.22", "facecolor": PALETTE[3], "edgecolor": "none"},
        "tag_text": "white",
        "band_fill": "#F1F5FB",
        "draw_band": True,
        "rule": "#DDE3EB",
        "label": PALETTE[1],
        "body": INK,
        "cell_weight": "bold",
        "round_corners": True,
        "arrowhead": True,
        "lw": {"box": 1.1, "focus": 1.65, "card": 1.25, "cell": 0.8, "link": 0.9, "big": 1.1},
    },
    "ink": {
        "edge_a": "#000000", "text_a": "#000000",
        "edge_b": "#000000", "text_b": "#000000",
        "tag_bbox": {"boxstyle": "square,pad=0.28", "facecolor": "white",
                     "edgecolor": "#000000", "linewidth": 0.7},
        "tag_text": "#000000",
        "band_fill": "white",
        "draw_band": False,
        "rule": "#000000",
        "label": "#000000",
        "body": "#000000",
        "cell_weight": "normal",
        "round_corners": False,
        "arrowhead": False,
        "lw": {"box": 1.0, "focus": 1.0, "card": 1.0, "cell": 0.8, "link": 0.9, "big": 1.0},
    },
}

EDGE_A = TEXT_A = EDGE_B = TEXT_B = ""
TAG_BBOX, TAG_TEXT = {}, ""
BAND_FILL = RULE = LABEL = BODY = ""
CELL_WEIGHT = "bold"
ROUND_CORNERS = ARROW_HEAD = DRAW_BAND = True
LW_BOX = LW_FOCUS = LW_CARD = LW_CELL = LW_LINK = LW_BIG = 1.0

# ---- 版面栅格（单位 cm，1 数据单位 = 1 cm）----
PANEL_X, PANEL_W = 1.0, 26.0          # Q1／Q2 大框左右边界
Q1_Y, Q1_H = 9.77, 1.88               # Q1 基础层
Q2_Y, Q2_H = 6.53, 2.55               # Q2 枢纽层
FLOW_L, FLOW_R = 7.30, 25.00          # Q1／Q2 两行流程共用的左右边界
FLOW_GAP_A, FLOW_GAP_B = 0.90, 0.80   # Q1（4 格）／Q2（5 格）箭头长度
TAG_GAP = 0.62                        # Q2 标签相对标题基线上移量
CARD_Y, CARD_W, CARD_H = 2.10, 12.25, 3.05
BAND_H = 0.92                         # 分支卡片页眉色带高度
HEADER_PAD = 0.55                     # 卡片标题／编号距卡片左边距
CELL_H, CELL_PAD, CELL_GAP = 0.92, 0.45, 0.45
CANVAS_PAD = 0.35                     # 画布四周留白
CONTENT_X = (PANEL_X, PANEL_X + PANEL_W)
CONTENT_Y = (CARD_Y, Q1_Y + Q1_H)     # Q1 大框上沿为内容最高点
CARD_GAP = 1.50                       # 03／04 两张卡片之间的中缝
SPLIT_X = 14.0                        # 画布中轴（Q1→Q2 主干与分叉主干）


def use_palette(name):
    """切换配色；方框坐标、字号与箭头几何与配色无关。"""
    global EDGE_A, TEXT_A, EDGE_B, TEXT_B, TAG_BBOX, TAG_TEXT
    global BAND_FILL, RULE, LABEL, BODY, CELL_WEIGHT, ROUND_CORNERS, ARROW_HEAD, DRAW_BAND
    global LW_BOX, LW_FOCUS, LW_CARD, LW_CELL, LW_LINK, LW_BIG
    p = PALETTES[name]
    EDGE_A, TEXT_A = p["edge_a"], p["text_a"]
    EDGE_B, TEXT_B = p["edge_b"], p["text_b"]
    TAG_BBOX, TAG_TEXT = p["tag_bbox"], p["tag_text"]
    BAND_FILL, RULE = p["band_fill"], p["rule"]
    LABEL, BODY = p["label"], p["body"]
    CELL_WEIGHT = p["cell_weight"]
    ROUND_CORNERS, ARROW_HEAD, DRAW_BAND = p["round_corners"], p["arrowhead"], p["draw_band"]
    lw = p["lw"]
    LW_BOX, LW_FOCUS, LW_CARD = lw["box"], lw["focus"], lw["card"]
    LW_CELL, LW_LINK, LW_BIG = lw["cell"], lw["link"], lw["big"]


def card(ax, x, y, w, h, *, edge=None, face="white", lw=None, radius=0.09):
    edge = EDGE_A if edge is None else edge
    lw = LW_BOX if lw is None else lw
    if ROUND_CORNERS:
        p = FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0.016,rounding_size={radius}",
            linewidth=lw, edgecolor=edge, facecolor=face, zorder=2,
        )
    else:
        p = Rectangle((x, y), w, h, linewidth=lw, edgecolor=edge, facecolor=face, zorder=2)
    ax.add_patch(p)
    return p


def arrow(ax, start, end, *, color=None, scale=9, lw=None):
    color = EDGE_A if color is None else color
    lw = LW_BIG if lw is None else lw
    if ARROW_HEAD:
        ax.add_patch(FancyArrowPatch(
            start, end, arrowstyle="-|>", mutation_scale=scale,
            linewidth=lw, color=color, shrinkA=0, shrinkB=0, zorder=4,
        ))
    else:
        ax.plot([start[0], end[0]], [start[1], end[1]], color=color, linewidth=lw,
                zorder=4, solid_capstyle="butt")


def step_cell(
    ax,
    x,
    y,
    w,
    h,
    title,
    detail,
    *,
    edge=None,
    text=None,
    weight=None,
    title_size=8.0,
    detail_size=6.8,
):
    edge = EDGE_A if edge is None else edge
    text = TEXT_A if text is None else text
    weight = CELL_WEIGHT if weight is None else weight
    card(ax, x, y, w, h, edge=edge, face="white", lw=LW_CELL, radius=0.055)
    ax.text(x + w / 2, y + h / 2, title, ha="center", va="center",
            fontsize=title_size, color=text, fontweight=weight, zorder=5)


def header_block(ax, x, y, number, title, subtitle, *, text=None, tag=None):
    text = TEXT_A if text is None else text
    ax.text(x, y, f"0{number}", ha="left", va="center", fontsize=8.0,
            color=text, fontweight="bold")
    ax.text(x + 0.78, y, title, ha="left", va="center", fontsize=11.4,
            color=text, fontweight="bold")
    if tag:
        ax.text(x + 0.78, y + TAG_GAP, tag, ha="left", va="center", fontsize=6.4,
                color=TAG_TEXT, bbox=TAG_BBOX)


def branch_card(ax, x, title, subtitle, cells, validation):
    y, w, h = CARD_Y, CARD_W, CARD_H
    box = card(ax, x, y, w, h, edge=EDGE_A, face="white", lw=LW_CARD, radius=0.10)
    if DRAW_BAND:
        band = Rectangle((x, y + h - BAND_H), w, BAND_H, facecolor=BAND_FILL,
                         edgecolor="none", zorder=2.1)
        ax.add_patch(band)
        band.set_clip_path(box)  # 圆角卡片：色带不露出方形尖角
    ax.text(x + HEADER_PAD, y + h - BAND_H / 2, title, ha="left", va="center",
            fontsize=10.5, color=TEXT_A, fontweight="bold", zorder=5)

    # 单元格在色带下沿与卡片下边之间垂直居中，并保持左右等边距。
    cell_h = CELL_H
    cell_w = (w - 2 * CELL_PAD - 3 * CELL_GAP) / 4
    cell_y = y + (h - BAND_H - cell_h) / 2
    starts = [x + CELL_PAD + i * (cell_w + CELL_GAP) for i in range(4)]
    for sx, (head, detail) in zip(starts, cells):
        step_cell(
            ax,
            sx,
            cell_y,
            cell_w,
            cell_h,
            head,
            detail,
            edge=EDGE_A,
            text=TEXT_A,
            title_size=6.8,
            detail_size=5.9,
        )
    for left, right in zip(starts[:-1], starts[1:]):
        arrow(ax, (left + cell_w, cell_y + cell_h / 2),
              (right, cell_y + cell_h / 2), color=EDGE_A, scale=7, lw=LW_LINK)

    # 去字版：原「验证」行（分隔线＋说明）不再绘制；validation 参数仅为保持调用签名。


def build_figure():
    # 画布＝内容外沿＋四周等量白边（1 数据单位 = 1 cm），字号与框体尺寸保持不变。
    x_min, x_max = CONTENT_X[0] - CANVAS_PAD, CONTENT_X[1] + CANVAS_PAD
    y_min, y_max = CONTENT_Y[0] - CANVAS_PAD, CONTENT_Y[1] + CANVAS_PAD
    fig = plt.figure(
        figsize=((x_max - x_min) / 2.54, (y_max - y_min) / 2.54),
        facecolor="white",
        layout="none",
    )
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.axis("off")

    # 去字版：原来的「统一问题设定」约束条（底框＋文字＋分隔点）整条不再绘制。

    # Q1 基础层
    q1_y, q1_h = Q1_Y, Q1_H
    card(ax, PANEL_X, q1_y, PANEL_W, q1_h, edge=EDGE_A, face=BAND_FILL,
         lw=LW_BOX, radius=0.10)
    header_block(ax, PANEL_X + HEADER_PAD, q1_y + q1_h / 2, 1,
                 "确定性几何定位模型", "形成可复用的可行域表征与判定依据")
    q1_cells = [
        ("角度带半平面化", "±1° 示向度→2n 约束"),
        ("状态判别与构形", "空／无界／退化／凸多边形"),
        ("区域直径双重求解", "旋转卡壳＋全顶点对复核"),
        ("同直径圆直接判定", "最远点中点＋顶点检验"),
    ]
    # 与 Q2 共用流程区左右边界；4 格均分，箭头长度与 Q2 一致。
    q1_w = (FLOW_R - FLOW_L - 3 * FLOW_GAP_A) / 4
    q1_starts = [FLOW_L + i * (q1_w + FLOW_GAP_A) for i in range(4)]
    for x, (head, detail) in zip(q1_starts, q1_cells):
        step_cell(ax, x, q1_y + (q1_h - 0.92) / 2, q1_w, 0.92, head, detail)
    for left, right in zip(q1_starts[:-1], q1_starts[1:]):
        arrow(ax, (left + q1_w, q1_y + q1_h / 2), (right, q1_y + q1_h / 2),
              scale=7, lw=LW_LINK)

    arrow(ax, (SPLIT_X, q1_y), (SPLIT_X, Q2_Y + Q2_H), color=EDGE_B, scale=9, lw=LW_BIG)

    # Q2 枢纽层：白底、橙色描边与小标签，避免大面积橙色压迫。
    q2_y, q2_h = Q2_Y, Q2_H
    q2_cell_y, q2_cell_h = q2_y + 0.66, 0.98
    card(ax, PANEL_X, q2_y, PANEL_W, q2_h, edge=EDGE_B, face="white",
         lw=LW_FOCUS, radius=0.10)
    # 标题与流程单元同一水平中轴，标签独立上移，不与标题相碰。
    header_block(ax, PANEL_X + HEADER_PAD, q2_cell_y + q2_cell_h / 2, 2,
                 "多目标主动观测优化模型",
                 "联合权衡定位精度、保证接收率与任务耗时", text=TEXT_B,
                 tag="Q3 / Q4 共同决策内核")
    q2_cells = [
        ("首测域 P1 构造", "角度带＋任务圆＋距离"),
        ("候选空间两阶段搜索", "108 粗搜→双中心加密"),
        ("内层多指标评价", "Qgeo／Prec／T／Rpred"),
        ("外层权重校准", "蒙特卡洛—网格搜索"),
        ("实际二测闭环", "P2→MEC≤20 m 清除"),
    ]
    q2_w = (FLOW_R - FLOW_L - 4 * FLOW_GAP_B) / 5
    q2_starts = [FLOW_L + i * (q2_w + FLOW_GAP_B) for i in range(5)]
    for x, (head, detail) in zip(q2_starts, q2_cells):
        step_cell(ax, x, q2_cell_y, q2_w, q2_cell_h, head, detail,
                  edge=EDGE_B, text=TEXT_B, title_size=7.0, detail_size=6.0)
    for left, right in zip(q2_starts[:-1], q2_starts[1:]):
        arrow(ax, (left + q2_w, q2_cell_y + q2_cell_h / 2),
              (right, q2_cell_y + q2_cell_h / 2),
              color=EDGE_B, scale=7, lw=LW_LINK)

    # 对称分叉：主干为直线（避免 T 形接头出现箭头），两条支线落在卡片几何中心。
    trunk_y = 5.83
    card_top = CARD_Y + CARD_H
    br_x = (PANEL_X + CARD_W / 2, PANEL_X + CARD_W + CARD_GAP + CARD_W / 2)
    ax.plot([SPLIT_X, SPLIT_X], [q2_y, trunk_y], color=EDGE_B,
            linewidth=LW_BIG, zorder=3, solid_capstyle="butt")
    ax.plot([br_x[0], br_x[1]], [trunk_y, trunk_y], color=EDGE_B,
            linewidth=LW_BIG, zorder=3, solid_capstyle="butt")
    for bx in br_x:
        arrow(ax, (bx, trunk_y), (bx, card_top), color=EDGE_B, scale=8, lw=LW_BIG)

    branch_card(
        ax, PANEL_X,
        "03  第三问｜全向多源协同搜索与调度优化",
        "继承 Q2 单源内核；以全清除率为硬约束，词典序优化平均／P95 耗时",
        [
            ("频道状态与保守域", "Ph 递推＋MEC 清除判据"),
            ("覆盖结构联合优化", "中心＋7 外环点，Rcov=1000 m"),
            ("协同观测与路径优化", "高价值共观测＋开放路径"),
            ("逐动作滚动清除", "重规划与在线选点 J+"),
        ],
        "解析覆盖证书 · 多种子配对 · 压力情景与消融实验",
    )
    branch_card(
        ax, PANEL_X + CARD_W + CARD_GAP,
        "04  第四问｜混合源认证覆盖与稳健决策优化",
        "继承 Q2 主动定位闭环；在认证覆盖约束下最小化平均每源任务时间",
        [
            ("定向接收与耗时模型", "距离＋前向半平面约束"),
            ("原点扫描认证门控", "零发现→B；否则→C"),
            ("保守域递推与剪枝", "d(q,Fk)>1500 m 安全跳过"),
            ("滚动清除与走廊兜底", "交错点阵覆盖误差走廊"),
        ],
        "源数分层 · 边界随机 · 边界朝外 · 独立留出验证",
    )

    return fig


def main():
    apply_style()
    plt.rcParams["figure.constrained_layout.use"] = False
    out_dir = ROOT / "outputs" / "overall" / "figures"
    for palette, suffix in (("color", ""), ("ink", "_黑线版")):
        use_palette(palette)
        fig = build_figure()
        base = out_dir / f"B题总体模型架构图_精排版{suffix}"
        save_figure(fig, base)
        fig.savefig(base.with_suffix(".svg"), facecolor="white", bbox_inches=None)
        plt.close(fig)


if __name__ == "__main__":
    main()

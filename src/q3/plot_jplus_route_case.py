"""Reproduce and plot one real J+ offline-simulation route."""
from __future__ import annotations

import csv
import json
import math
import random
import sys
from dataclasses import asdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, FancyArrowPatch


ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "src" / "q3" / "B题模型代码汇总" / "第三问策略对比"
SKILL_DIR = ROOT / ".agents" / "skills" / "paper-plot-style"
sys.path.insert(0, str(MODEL_DIR))
sys.path.insert(0, str(SKILL_DIR))

from baseline_core import OfflineSimulator, random_sources  # noqa: E402
from paper_style import INK, PALETTE, apply_style, save_figure  # noqa: E402
from strategies import JPlusAgent  # noqa: E402


SEED = 24119
CASE = 231
FIGURE_OUTPUT = ROOT / "outputs" / "q3" / "figures"
DATA_OUTPUT = ROOT / "outputs" / "q3" / "data"
RESULT_CSV = MODEL_DIR / "results" / "robustness_jplus" / "seed_24119" / "case_results.csv"


def _compress(points):
    result = []
    for point in points:
        if not result or point != result[-1]:
            result.append(point)
    return result


def _add_direction_arrows(ax, points, color, count):
    segments = [(a, b) for a, b in zip(points, points[1:]) if a != b]
    if not segments:
        return
    picks = sorted(set(round(i * (len(segments) - 1) / max(1, count - 1))
                       for i in range(count)))
    for index in picks:
        a, b = segments[index]
        start = (a[0] + 0.52 * (b[0] - a[0]), a[1] + 0.52 * (b[1] - a[1]))
        end = (a[0] + 0.72 * (b[0] - a[0]), a[1] + 0.72 * (b[1] - a[1]))
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>",
                                    mutation_scale=9, linewidth=1.0,
                                    color=color, zorder=4))


def _shortest_open_route(points):
    """Exact Held--Karp path from the origin through every point, no return."""
    n = len(points)
    origin = (0.0, 0.0)
    dp = {}
    parent = {}
    for j in range(n):
        dp[(1 << j, j)] = math.dist(origin, points[j])
        parent[(1 << j, j)] = None
    for mask in range(1, 1 << n):
        for j in range(n):
            state = (mask, j)
            if not (mask & (1 << j)) or state not in dp:
                continue
            remaining = ((1 << n) - 1) ^ mask
            k = 0
            while remaining:
                if remaining & 1:
                    next_mask = mask | (1 << k)
                    candidate = dp[state] + math.dist(points[j], points[k])
                    next_state = (next_mask, k)
                    if candidate < dp.get(next_state, math.inf):
                        dp[next_state] = candidate
                        parent[next_state] = state
                remaining >>= 1
                k += 1
    full = (1 << n) - 1
    state = min(((full, j) for j in range(n)), key=lambda item: dp[item])
    distance = dp[state]
    order = []
    while state is not None:
        order.append(state[1])
        state = parent[state]
    return list(reversed(order)), distance


def reproduce_case():
    rng = random.Random(SEED)
    sources = None
    for _ in range(CASE):
        sources = random_sources(rng, None)
    assert sources is not None
    truth = [{"channel": source.channel,
              "position": list(source.position),
              "receive_radius": source.receive_radius}
             for source in sources]
    sim = OfflineSimulator(sources, SEED * 100000 + CASE)
    agent = JPlusAgent(sim)
    result = agent.run()

    with RESULT_CSV.open(encoding="utf-8-sig", newline="") as file:
        expected = next(row for row in csv.DictReader(file)
                        if int(row["case"]) == CASE and row["strategy"] == "Jplus_final")
    if abs(result["total_virtual_time_s"] - float(expected["total_virtual_time_s"])) > 1e-3:
        raise RuntimeError("复现结果与已保存实验结果不一致")
    return truth, sim.actions, agent.search_end_time_s, result


def draw_route():
    truth, actions, search_end, result = reproduce_case()
    positioned = [action for action in actions if action.position is not None]
    search_positions = [(0.0, 0.0)] + [action.position for action in positioned
                                       if action.virtual_time_s <= search_end]
    search_positions = _compress(search_positions)
    last_search = search_positions[-1]
    clearing_positions = [last_search] + [action.position for action in positioned
                                          if action.virtual_time_s > search_end]
    clearing_positions = _compress(clearing_positions)

    measure_positions = [action.position for action in positioned if action.kind == "measure"]
    fig, ax = plt.subplots(figsize=(15 / 2.54, 13 / 2.54))
    ax.add_patch(Circle((0, 0), 1800, facecolor="#F8FAFC", edgecolor="#AEB6C1",
                        linewidth=1.0, linestyle=(0, (5, 4)), zorder=0))

    sx, sy = zip(*search_positions)
    cx, cy = zip(*clearing_positions)
    ax.plot(sx, sy, color=PALETTE[0], linewidth=2.1, zorder=2)
    ax.plot(cx, cy, color=PALETTE[3], linewidth=1.45, alpha=0.92, zorder=2)
    _add_direction_arrows(ax, search_positions, PALETTE[0], 7)
    _add_direction_arrows(ax, clearing_positions, PALETTE[3], 10)

    if measure_positions:
        mx, my = zip(*measure_positions)
        ax.scatter(mx, my, s=14, facecolors="white", edgecolors=PALETTE[1],
                   linewidths=0.7, alpha=0.8, zorder=3)
    for source_index, source in enumerate(truth, 1):
        x, y = source["position"]
        ax.scatter([x], [y], s=58, marker="*", facecolors=PALETTE[4],
                   edgecolors="white", linewidths=0.55, zorder=6)
        ax.annotate(str(source_index), (x, y), xytext=(4, 4),
                    textcoords="offset points", fontsize=7.2, color=PALETTE[4])
    ax.scatter([0], [0], marker="s", s=32, facecolors=INK, edgecolors="white",
               linewidths=0.6, zorder=7)

    all_points = [item["position"] for item in truth] + [list(action.position)
                 for action in positioned]
    extent = max(1950, max(max(abs(x), abs(y)) for x, y in all_points) + 170)
    ax.set_xlim(-extent, extent)
    ax.set_ylim(-extent, extent)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x / m")
    ax.set_ylabel("y / m")
    ax.set_title(f"J+ 模型单局真实路线（seed={SEED}，case={CASE}）", loc="left")
    ax.grid(True, color="#E5E8ED", linewidth=0.55, zorder=-1)
    ax.legend(handles=[
        Line2D([0], [0], marker="o", color="none", markerfacecolor="white",
               markeredgecolor=PALETTE[1], markeredgewidth=1.0,
               markersize=5.5, label="测量位置"),
        Line2D([0], [0], marker="*", color="none", markerfacecolor=PALETTE[4],
               markeredgecolor="white", markeredgewidth=0.5,
               markersize=9, label="真实源点"),
    ], loc="upper right", handletextpad=0.55, labelspacing=0.55)

    ax.text(0.02, 0.02,
            f"源点 {len(truth)} 个，清除 {result['cleared_channels']}/{len(truth)}；"
            f"总耗时 {result['total_virtual_time_s']:.1f} s，搜索结束 {search_end:.1f} s",
            transform=ax.transAxes, fontsize=7.6, color=INK,
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white",
                  "edgecolor": "#D9DEE5", "alpha": 0.92})

    basename = FIGURE_OUTPUT / f"J+真实路线案例_seed{SEED}_case{CASE}"
    save_figure(fig, basename)
    plt.close(fig)
    data_path = DATA_OUTPUT / f"J+真实路线案例_seed{SEED}_case{CASE}.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps({
        "seed": SEED, "case": CASE, "strategy": "Jplus_final",
        "selection": "在 seed=24119 的全清除案例中，选择每源耗时最接近中位数且源点不超过12个的案例",
        "search_end_time_s": search_end, "result": result,
        "sources": truth, "actions": [asdict(action) for action in actions],
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def draw_omniscient_route():
    truth, _, _, jplus_result = reproduce_case()
    points = [tuple(source["position"]) for source in truth]
    order, distance_m = _shortest_open_route(points)
    route = [(0.0, 0.0)] + [points[index] for index in order]
    travel_time_s = distance_m / 5.0
    clear_time_s = 5.0 * len(points)

    fig, ax = plt.subplots(figsize=(15 / 2.54, 13 / 2.54))
    ax.add_patch(Circle((0, 0), 1800, facecolor="#F8FAFC", edgecolor="#AEB6C1",
                        linewidth=1.0, linestyle=(0, (5, 4)), zorder=0))
    rx, ry = zip(*route)
    ax.plot(rx, ry, color=PALETTE[0], linewidth=2.0, zorder=2)
    _add_direction_arrows(ax, route, PALETTE[0], len(points))

    for source_index, source in enumerate(truth, 1):
        x, y = source["position"]
        ax.scatter([x], [y], s=62, marker="*", facecolors=PALETTE[4],
                   edgecolors="white", linewidths=0.55, zorder=5)
        ax.annotate(str(source_index), (x, y), xytext=(4, 4),
                    textcoords="offset points", fontsize=7.2, color=PALETTE[4])
    ax.scatter([0], [0], marker="s", s=32, facecolors=INK, edgecolors="white",
               linewidths=0.6, zorder=6)

    extent = 1950
    ax.set_xlim(-extent, extent)
    ax.set_ylim(-extent, extent)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x / m")
    ax.set_ylabel("y / m")
    ax.set_title(f"全知条件下的最快走线（seed={SEED}，case={CASE}）", loc="left")
    ax.grid(True, color="#E5E8ED", linewidth=0.55, zorder=-1)
    ax.legend(handles=[
        Line2D([0], [0], marker="*", color="none", markerfacecolor=PALETTE[4],
               markeredgecolor="white", markeredgewidth=0.5,
               markersize=9, label="真实源点"),
    ], loc="upper right", handletextpad=0.55)
    ax.text(0.02, 0.02,
            f"最短路程 {distance_m:.1f} m；移动 {travel_time_s:.1f} s，"
            f"清除 {clear_time_s:.1f} s；全知耗时 {travel_time_s + clear_time_s:.1f} s，"
            f"J+ 算法耗时 {jplus_result['total_virtual_time_s']:.1f} s",
            transform=ax.transAxes, fontsize=7.6, color=INK,
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white",
                  "edgecolor": "#D9DEE5", "alpha": 0.92})

    basename = FIGURE_OUTPUT / f"全知条件最快走线_seed{SEED}_case{CASE}"
    save_figure(fig, basename)
    plt.close(fig)
    data_path = DATA_OUTPUT / f"全知条件最快走线_seed{SEED}_case{CASE}.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps({
        "seed": SEED, "case": CASE,
        "assumption": "已知全部真实源坐标；从原点出发；必须清除全部源；终点无需返回原点",
        "method": "Held-Karp exact shortest open Hamiltonian path",
        "source_order": [index + 1 for index in order],
        "distance_m": distance_m,
        "movement_time_s": travel_time_s,
        "clear_time_s": clear_time_s,
        "total_time_lower_bound_s": travel_time_s + clear_time_s,
        "sources": truth,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    apply_style()
    draw_route()
    draw_omniscient_route()

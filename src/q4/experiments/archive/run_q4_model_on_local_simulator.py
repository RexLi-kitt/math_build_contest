"""用本地协议模拟器执行 Q4 风险回补模型的动作级闭环测试，不读取隐藏源真值。"""
from __future__ import annotations

import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from engine.q4_local_simulator import LocalQ4Simulator

ROOT = HERE.parents[2]
OUT, FIG, TAB, LOG = ROOT / "outputs" / "q4", ROOT / "outputs" / "q4" / "figures", ROOT / "outputs" / "q4" / "tables", ROOT / "outputs" / "q4" / "logs" / "model_runs"
BLUE, ORANGE, GRAY, DARK = "#1F5A94", "#E67E22", "#8A8F98", "#23364A"


def survey_stations() -> list[tuple[float, float]]:
    """双环十二方位风险覆盖；no_signal 只降低风险，不作为频道不存在证明。"""
    points = [(0.0, 0.0)]
    for radius in (900.0, 1500.0):
        points += [(radius * math.cos(2 * math.pi * k / 12), radius * math.sin(2 * math.pi * k / 12)) for k in range(12)]
    return points


def intersect_bearings(observations: list[tuple[float, float, float]]) -> tuple[float, float] | None:
    """以最小二乘求多条示向度直线交点；不足两条或退化时返回 None。"""
    if len(observations) < 2:
        return None
    a00 = a01 = a11 = b0 = b1 = 0.0
    for x, y, bearing_deg in observations:
        theta = math.radians(bearing_deg)
        # 方向向量的法向量 n，最小化 n·(g-s) 的平方。
        nx, ny = -math.sin(theta), math.cos(theta)
        a00 += nx * nx; a01 += nx * ny; a11 += ny * ny
        projection = nx * x + ny * y
        b0 += nx * projection; b1 += ny * projection
    determinant = a00 * a11 - a01 * a01
    if abs(determinant) < 1e-8:
        return None
    return ((a11 * b0 - a01 * b1) / determinant,
            (a00 * b1 - a01 * b0) / determinant)


def main() -> None:
    for directory in (OUT, FIG, TAB, LOG):
        directory.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"], "axes.unicode_minus": False})
    sim = LocalQ4Simulator(seed=20260915, source_count=12, directional_ratio=.5)
    observed: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
    first_positive_time: dict[int, float] = {}
    clear_time: dict[int, float] = {}
    cleared, action_id, trace = set(), 0, [(0.0, 0.0)]

    def request_id(prefix: str) -> str:
        nonlocal action_id
        action_id += 1
        return f"{prefix}-{action_id}"

    sim.enter(request_id("enter"))
    for station in survey_stations():
        # 仅扫描尚未清除频道；no_signal 不从候选集合中删除频道。
        for channel in range(1, 21):
            if channel in cleared:
                continue
            response = sim.measure(station, channel, request_id("measure"))
            trace.append(station)
            if response["measure_result"] == "direction":
                observed[channel].append((station[0], station[1], response["svd_deg"]))
                first_positive_time.setdefault(channel, response["virtual_time_s"])
            elif response["measure_result"] == "near":
                first_positive_time.setdefault(channel, response["virtual_time_s"])
                result = sim.clear(station, channel, request_id("clear"))
                trace.append(station)
                if result["clear_result"] == "success":
                    cleared.add(channel)
                    clear_time[channel] = result["virtual_time_s"]
        # 事件触发：每到一个新方位，只对已有至少两条正观测的频道尝试定位清除。
        for channel, history in list(observed.items()):
            if channel in cleared:
                continue
            estimate = intersect_bearings(history)
            if estimate is None:
                continue
            result = sim.clear(estimate, channel, request_id("clear"))
            trace.append(estimate)
            if result["clear_result"] == "success":
                cleared.add(channel)
                clear_time[channel] = result["virtual_time_s"]

    exit_response = sim.exit(request_id("exit"))
    sim.export_log(LOG / "q4_local_model_run_seed20260915.json")
    summary = exit_response["summary"]
    source_rows = [{"频道": channel, "首次正观测虚拟时间(s)": first_positive_time[channel],
                    "清除成功虚拟时间(s)": clear_time[channel],
                    "定位清除耗时(s)": clear_time[channel] - first_positive_time[channel]}
                   for channel in sorted(clear_time)]
    durations = [row["定位清除耗时(s)"] for row in source_rows]
    row = {"随机种子": 20260915, "源总数": summary["source_count"], "已清除数": summary["cleared_count"],
           "清除比例": summary["clear_rate"], "虚拟时间(s)": summary["virtual_time_s"],
           "检测次数": sum(event["action"] == "measure" for event in sim.log),
           "清除尝试次数": sum(event["action"] == "clear" for event in sim.log),
           "已获正观测频道数": len(observed), "最快单源定位清除时间(s)": min(durations),
           "平均单源定位清除时间(s)": sum(durations) / len(durations),
           "最慢单源全流程时间(s)": max(durations)}
    with (TAB / "Q4本地模拟器闭环测试.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, list(row)); writer.writeheader(); writer.writerow(row)
    with (TAB / "Q4本地模拟器单源时间明细.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, list(source_rows[0])); writer.writeheader(); writer.writerows(source_rows)

    fig, ax = plt.subplots(figsize=(7.2, 7.0))
    ax.add_patch(plt.Circle((0, 0), 1800, fill=False, ec=GRAY, ls="--", lw=1.4, label="1800 m 源分布圆"))
    stations = survey_stations(); ax.scatter(*zip(*stations), c=GRAY, s=24, label="风险覆盖检测点")
    ax.plot(*zip(*trace), color=BLUE, lw=.9, alpha=.72, label="动作轨迹")
    ax.scatter(0, 0, c=DARK, s=62, zorder=4, label="起点")
    ax.set(aspect="equal", xlabel="东向坐标 x / m", ylabel="北向坐标 y / m", title="Q4 本地模拟器中的风险回补闭环测试")
    ax.grid(alpha=.2); ax.legend(fontsize=8); fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(FIG / f"q4_local_model_run_seed20260915.{suffix}", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(row)


if __name__ == "__main__":
    main()

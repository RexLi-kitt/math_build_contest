"""从完整环形发现站中筛选满足数值定向覆盖判据的最小冗余子集。"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np


# 本脚本位于 src/q4/experiments/analysis/；输出必须归入“已完成/outputs”，
# 不能在 src 下再生成伪输出目录。
ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs" / "q4" / "archive" / "strict_coverage" / "tables"
RADIUS_M, GUARANTEED_RANGE_M, GRID_STEP_M = 1800.0, 1000.0, 20.0


def full_ring_stations() -> list[tuple[float, float]]:
    """与主程序 full 布局一致的 37 个发现站。"""
    stations = [(0.0, 0.0)]
    for radius, shift in ((900.0, 0.0), (1500.0, 15.0), (1800.0, 0.0)):
        stations.extend((radius * math.cos(math.radians(shift + 30 * k)),
                         radius * math.sin(math.radians(shift + 30 * k))) for k in range(12))
    return stations


def validation_points() -> np.ndarray:
    values = np.arange(-RADIUS_M, RADIUS_M + 1e-9, GRID_STEP_M)
    xx, yy = np.meshgrid(values, values)
    return np.column_stack((xx.ravel(), yy.ravel()))[(xx.ravel() ** 2 + yy.ravel() ** 2) <= RADIUS_M ** 2]


def coverage_margin(points: np.ndarray, stations: np.ndarray, chosen: list[int]) -> tuple[float, int]:
    """返回最小角度裕量与失覆盖点数。

    对任一验证位置，取 1000m 内站点的方位；最大相邻方位间隙不超过 π，
    等价于任意半张角 90° 的发射扇区至少覆盖一个站点。正裕量越大越稳健。
    """
    selected = stations[chosen]
    min_margin, failures = float("inf"), 0
    for point in points:
        offsets = selected - point
        distances = np.hypot(offsets[:, 0], offsets[:, 1])
        offsets = offsets[distances <= GUARANTEED_RANGE_M + 1e-9]
        if len(offsets) < 2:
            failures += 1
            min_margin = min(min_margin, -math.pi)
            continue
        angles = np.sort(np.arctan2(offsets[:, 1], offsets[:, 0]))
        gaps = np.diff(np.concatenate((angles, [angles[0] + 2 * math.pi])))
        margin = math.pi - float(np.max(gaps))
        min_margin = min(min_margin, margin)
        if margin < -1e-9:
            failures += 1
    return min_margin, failures


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    stations = np.array(full_ring_stations(), dtype=float)
    points = validation_points()
    chosen = list(range(len(stations)))
    history: list[dict[str, float | int]] = []
    # 后向删除：每轮只删除一个仍可保持数值覆盖、且剩余最小角度裕量最大的站点。
    while True:
        candidates: list[tuple[float, int]] = []
        for station_id in chosen:
            proposal = [item for item in chosen if item != station_id]
            margin, failures = coverage_margin(points, stations, proposal)
            if failures == 0:
                candidates.append((margin, station_id))
        if not candidates:
            break
        margin, removed = max(candidates, key=lambda item: (item[0], -item[1]))
        chosen.remove(removed)
        history.append({"删除站点编号": removed, "剩余站点数": len(chosen), "最小角度裕量(度)": math.degrees(margin)})

    final_margin, final_failures = coverage_margin(points, stations, chosen)
    payload = {
        "grid_step_m": GRID_STEP_M,
        "validation_points": int(len(points)),
        "full_station_count": int(len(stations)),
        "selected_station_count": int(len(chosen)),
        "selected_station_ids": chosen,
        "selected_stations_m": [[round(float(x), 6), round(float(y), 6)] for x, y in stations[chosen]],
        "minimum_angular_margin_deg": round(math.degrees(final_margin), 6),
        "uncovered_validation_points": int(final_failures),
        "warning": "这是 20m 网格上的数值覆盖核验；正式数学证明仍需对连续圆域补充几何论证。",
    }
    (OUT / "Q4发现层覆盖子集.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "Q4发现层覆盖删除过程.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["删除站点编号", "剩余站点数", "最小角度裕量(度)"])
        writer.writeheader(); writer.writerows(history)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



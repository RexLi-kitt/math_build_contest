"""校验 DG2 的 B 路线动态连接：路径长度与耗时。

对比三种衔接方式（从 C 前缀末站出发访问完整 B 站点集）：
1. 直接跳到 B1 后按 B 原顺序（旧 DG 的做法）；
2. 最近邻 + 2-opt 重排（DG2 的做法）；
并给出耗时（官方测试对程序时间有要求）。
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "models"))
import harness as H  # noqa: E402
from cplus_3f_dg2_agent import nearest_neighbour_two_opt, open_path_length  # noqa: E402


def load_route(folder):
    data = json.loads((H.MODELS / folder / "winner_design.json").read_text(
        encoding="utf-8"))
    sites = [tuple(point) for point in data["sites"]]
    return [sites[index] for index in data["order"]]


def main() -> None:
    b_route = load_route("B模型")
    c_route = load_route("C模型")
    b_stations = b_route[1:]
    H.log(f"B 原顺序从原点出发的开放路径：{open_path_length((0.0, 0.0), b_stations) / 1000:.2f} km")
    H.log(f"\n{'起点':<18}{'旧做法(跳B1+原顺序)':>20}{'DG2(最近邻+2opt)':>18}"
          f"{'节省':>10}{'耗时ms':>9}")
    for k in (1, 2, 3, 5):
        start = c_route[k]
        fixed = math.dist(start, b_stations[0]) + open_path_length(b_stations[0], b_stations[1:])
        began = time.perf_counter()
        order = nearest_neighbour_two_opt(start, b_stations)
        elapsed = (time.perf_counter() - began) * 1000
        planned = open_path_length(start, order)
        H.log(f"C{k} ({start[0]:.0f},{start[1]:.0f})"
              f"{fixed / 1000:>17.2f}km{planned / 1000:>15.2f}km"
              f"{(fixed - planned) / 1000:>8.2f}km{elapsed:>9.1f}")


if __name__ == "__main__":
    main()

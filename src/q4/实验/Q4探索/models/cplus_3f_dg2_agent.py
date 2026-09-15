"""C+3F-DG2 模型：延迟门控 + 切换后从当前位置重新优化 B 路线顺序。

与 DG 版的区别（针对上一版的主要失分点）：
1. 判定切 B 后，站点集仍是**完整的 B 站点集**（原点 + 26 站），因此覆盖证书
   是 B 证书的超集、自然保留，不需要重新证明；只把访问顺序按当前位置重新优化，
   因为覆盖证书取决于站点集合而不取决于顺序。
2. 顺序用与出厂设计相同的开放路径优化器（多起点最近邻 + 2-opt + Or-opt，
   起点固定为当前位置），从而压低"C 前缀 → B 路线"的衔接成本。

门控流程（只在原点零发现时启用，其余情况与 C+3F 逐条同值）：
1. 原点扫描；
2. 原点有发现 -> 完整 C+3F（C 路线 + 选择性共观测）；
3. 原点零发现 -> 先走 C 的前 k 站作为探针：
   - 探针新增发现数 > τ -> 继续走 C 的剩余站点（完整 C+3F 行为）；
   - 否则 -> 切到 B 的完整站点集，并按当前位置重新优化访问顺序。

接入：
    from cplus_3f_dg2_agent import CPlus3FDG2Agent
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from cplus_3f_agent import CPlus3FLiteAgent  # noqa: E402


def nearest_neighbour_two_opt(start, stations) -> list:
    """从 start 出发的开放路径：最近邻构造 + 2-opt 下降（起点固定）。

    出厂设计用的是"多起点最近邻 + 2-opt + Or-opt"，单案例要数秒 CPU；这里改为
    单起点最近邻 + 2-opt，距离矩阵只算一次、毫秒级可在线调用，
    仍然直接压掉"前缀 → B 路线"的衔接成本。
    """
    points = [start] + list(stations)
    count = len(points)
    distances = [[math.dist(a, b) for b in points] for a in points]
    remaining = set(range(1, count))
    order = [0]
    while remaining:
        last = order[-1]
        nxt = min(remaining, key=lambda k: (distances[last][k], k))
        order.append(nxt)
        remaining.remove(nxt)
    improved, passes = True, 0
    while improved and passes < 50:
        improved, passes = False, passes + 1
        for i in range(1, count - 1):
            for j in range(i + 1, count):
                delta = distances[order[i - 1]][order[j]] - distances[order[i - 1]][order[i]]
                if j + 1 < count:
                    delta += distances[order[i]][order[j + 1]] - distances[order[j]][order[j + 1]]
                if delta < -1e-9:
                    order[i:j + 1] = reversed(order[i:j + 1])
                    improved = True
    return [points[k] for k in order[1:]]


def open_path_length(start, order) -> float:
    return sum(math.dist(a, b) for a, b in zip([start] + list(order), order))


class CPlus3FDG2Agent(CPlus3FLiteAgent):
    """延迟门控 + 切换后动态连接 B 路线。"""

    probe_stations = 2
    switch_threshold = 0
    replan_b_route = True
    b_route_observation_target = 2

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.probe_new = None
        self.delayed_decision = None
        self.connection_m = None
        self.b_order_m = None

    # ------------------------------------------------------------- 工具

    def _discovered(self) -> int:
        return sum(state.discovered for state in self.state.values())

    def _b_station_order(self, start) -> list:
        """从 start 出发访问完整 B 站点集的顺序（站点集不变，只优化顺序）。"""
        stations = list(self._routes()["B"][1:])
        if not self.replan_b_route:
            return stations
        return nearest_neighbour_two_opt(start, stations)

    def _walk(self, stations) -> list:
        visited = []
        for index, point in enumerate(stations):
            if self._discovered() >= 16:
                break
            for channel, state in self.state.items():
                if not state.discovered:
                    self.observe(point, channel)
            self._coobserve(point, -1)
            visited.append(point)
            following = stations[index + 1] if index + 1 < len(stations) else None
            self._opportunistic_clear(following)
            self.say(f"{self.selected_search_order} 路线：{point!r} 完成，"
                     f"共发现 {self._discovered()} 个")
        return visited

    # ------------------------------------------------------------- 搜索

    def search(self) -> None:
        origin = (0.0, 0.0)
        for channel, state in self.state.items():
            if not state.discovered:
                self.observe(origin, channel)
        self._coobserve(origin, -1)
        self.origin_discoveries = self._discovered()
        routes = self._routes()

        if self.origin_discoveries == 0 and self.probe_stations > 0:
            self.selected_search_order = "C"
            self.coverage_observation_target = self.c_route_observation_target
            self.search_points = list(routes["C"])
            probes = list(self.search_points[1:1 + self.probe_stations])
            visited = self._walk(probes)
            self.probe_new = self._discovered() - self.origin_discoveries
            if self.probe_new <= self.switch_threshold:
                self.selected_search_order = "B"
                self.delayed_decision = "B"
                self.coverage_observation_target = self.b_route_observation_target
                self.search_points = list(routes["B"])
                start = visited[-1] if visited else origin
                order = [point for point in self._b_station_order(start)
                         if point not in visited]
                if order:
                    self.connection_m = math.dist(start, order[0])
                    self.b_order_m = sum(
                        math.dist(a, b) for a, b in zip([start] + order, order))
                self._walk(order)
            else:
                self.delayed_decision = "C"
                self._walk(list(routes["C"][1 + self.probe_stations:]))
        else:
            self.selected_search_order = "C"
            self.delayed_decision = "C"
            self.coverage_observation_target = self.c_route_observation_target
            self.search_points = list(routes["C"])
            self._walk(self.search_points[1:])
        self.search_end_time_s = self.sim.time_s


def make_variant(probe_stations: int, switch_threshold: int,
                 replan_b_route: bool = True):
    class _Variant(CPlus3FDG2Agent):
        pass

    _Variant.probe_stations = probe_stations
    _Variant.switch_threshold = switch_threshold
    _Variant.replan_b_route = replan_b_route
    _Variant.__name__ = (f"CPlus3FDG2_k{probe_stations}_t{switch_threshold}"
                         f"_{'replan' if replan_b_route else 'fixed'}")
    return _Variant


if __name__ == "__main__":
    print("C+3F-DG2 默认：探针", CPlus3FDG2Agent.probe_stations,
          "站，阈值", CPlus3FDG2Agent.switch_threshold,
          "，重排 B 路线", CPlus3FDG2Agent.replan_b_route)

"""C+3F-DG 模型：证书重审 + 延迟门控。

思路（离线可分性证据）：原点零发现的场景里，"原点发现数"完全零信息
（边界随机与边界朝外都是零发现，AUC 0.500），但走过 C 路线的前 k 个测站后，
"累计新增发现数"立刻有分辨力（k=3 时 AUC 0.918、准确率 85%，k=5 时 0.987/96%）。

门控流程（只在原点零发现时启用）：
1. 原点扫描（与 C+ 完全一致）；
2. 原点有发现 -> 直接走 C 路线 + 选择性共观测（与 C+3F 逐条同值）；
3. 原点零发现 -> 先走 C 的前 k 个测站作为探针：
   - 探针新增发现数 > τ -> 判定为"可发现型边界场景"，继续走 C 的剩余站点；
   - 否则 -> 判定为"全朝外型场景"，切换到 B 的站点集（B 分支保持其原始行为：
     方位目标 2、不加距离门），因此该分支与 B 的已验证表现一致。

证书：实际行走的站点集为 {原点} ∪ {C 的前 k 站} ∪ {B 的 26 站}，包含 B 的完整
认证集合；角隙对站点集单调（加站只会减小角隙），故发现覆盖保证不弱于 B，
已在 `step7_certificate.py` 中实测确认。

接入：
    from cplus_3f_dg_agent import CPlus3FDelayedAgent
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from cplus_3f_agent import CPlus3FLiteAgent  # noqa: E402


class CPlus3FDelayedAgent(CPlus3FLiteAgent):
    """延迟门控版本：原点零发现时先探针 k 站，再决定 C 或 B。"""

    probe_stations = 3
    switch_threshold = 0
    b_route_observation_target = 2

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.probe_new = None
        self.delayed_decision = None

    # ------------------------------------------------------------- 工具

    def _discovered(self) -> int:
        return sum(state.discovered for state in self.state.values())

    def _walk(self, stations) -> list:
        """按顺序走站点，返回实际访问过的站点列表。"""
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
                rest = [point for point in self.search_points[1:]
                        if point not in visited]
            else:
                self.delayed_decision = "C"
                rest = list(routes["C"][1 + self.probe_stations:])
            self._walk(rest)
        else:
            self.selected_search_order = "C"
            self.delayed_decision = "C"
            self.coverage_observation_target = self.c_route_observation_target
            self.search_points = list(routes["C"])
            self._walk(self.search_points[1:])
        self.search_end_time_s = self.sim.time_s


def make_variant(probe_stations: int, switch_threshold: int):
    """生成指定 (k, τ) 的变体类，便于筛选。"""

    class _Variant(CPlus3FDelayedAgent):
        pass

    _Variant.probe_stations = probe_stations
    _Variant.switch_threshold = switch_threshold
    _Variant.__name__ = f"CPlus3FDG_k{probe_stations}_t{switch_threshold}"
    return _Variant


if __name__ == "__main__":
    print("C+3F-DG 默认探针站数", CPlus3FDelayedAgent.probe_stations,
          "切换阈值", CPlus3FDelayedAgent.switch_threshold)

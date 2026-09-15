"""B 模型迭代 1: 扫描途中边际插入定位测量点 (Q4 长路线版)。

背景: 基线的 JPlusAgent 在七点环上关闭了插入(负收益); 但 B 模型的 27 站
长路线搜索后移动仍有 181.6 s/源, 插入机会完全不同。本模块在 CertRouteAgent
基础上实现预算可调的 _insertion_before, 并在扫描循环中生效:

  每个覆盖站之前, 若某个已发现未清除频道的下一个 D-opt 测量点顺路
  (额外绕行 <= budget), 就先去做这次测量并顺带共观测, 再继续覆盖站。
"""
from __future__ import annotations

from baseline_core import dist
from cert_route_agent import CertRouteAgent


class CertRouteInsertAgent(CertRouteAgent):
    """带边际插入的 B 模型变体; 预算与上限由类属性控制。"""

    insertion_budget_m = 300.0
    max_insertions = 10

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.coverage_insertions = 0

    def _insertion_before(self, next_coverage):
        if self.coverage_insertions >= self.max_insertions:
            return None
        direct = dist(self.sim.position, next_coverage)
        choices = []
        for channel, st in self.state.items():
            if st.cleared or st.exhausted or not st.discovered or st.attempts >= 10:
                continue
            if self._clear_decision(st) is not None:
                continue
            old_log_size = len(self.selection_log)
            point = self._next_measurement_point(st)
            del self.selection_log[old_log_size:]
            if point is None:
                continue
            extra = (dist(self.sim.position, point)
                     + dist(point, next_coverage) - direct)
            if extra > self.insertion_budget_m:
                continue
            choices.append((extra, channel, point))
        if not choices:
            return None
        _, channel, point = min(choices)
        return channel, point


class Insert200Agent(CertRouteInsertAgent):
    insertion_budget_m = 200.0


class Insert350Agent(CertRouteInsertAgent):
    insertion_budget_m = 350.0


class Insert500Agent(CertRouteInsertAgent):
    insertion_budget_m = 500.0


class Insert800Agent(CertRouteInsertAgent):
    insertion_budget_m = 800.0


class Insert500x16Agent(CertRouteInsertAgent):
    insertion_budget_m = 500.0
    max_insertions = 16


if __name__ == "__main__":
    print("insertion agents:", Insert200Agent.insertion_budget_m,
          Insert350Agent.insertion_budget_m, Insert500Agent.insertion_budget_m,
          Insert800Agent.insertion_budget_m, Insert500x16Agent.max_insertions)

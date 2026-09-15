"""B 模型迭代 2: 搜索后动作点路由 + 近终端粘滞。

迭代 1(扫描中插入)已证负收益。本模块针对搜索后 76% 的测量行程:
- ActionNodeAgent: 调度锚点从"估计源位置"改为实际下一个动作点
  (可清=清除圆心; 否则=D-opt 测量点)。Q3 TaskSchedulingAgent 记录过
  锚点/动作点错配 P90=594m, 该修正从未接到 Q4。
- StickyActionAgent: 再叠加近终端粘滞: 测量后若包围圆 <= 60m,
  继续处理该频道直到清除/耗尽, 避免回访重进场。
"""
from __future__ import annotations

from cert_route_agent import CertRouteAgent


class ActionNodeAgent(CertRouteAgent):
    """搜索后路由锚点 = 实际动作点。"""

    def _route_anchor(self, st):
        center = self._clear_decision(st)
        if center is not None:
            return center
        old_log_size = len(self.selection_log)
        point = self._next_measurement_point(st)
        del self.selection_log[old_log_size:]
        if point is not None:
            return point
        return self._target_anchor(st)


class StickyActionAgent(ActionNodeAgent):
    """动作点路由 + 近终端粘滞(半径 60m)。"""

    ready_radius_m = 60.0

    def run(self) -> dict:
        self.sim.enter()
        self.search()
        sticky = None
        for _ in range(600):
            unresolved = [channel for channel, st in self.state.items()
                          if st.discovered and not st.cleared and not st.exhausted]
            if not unresolved:
                break
            if sticky is not None:
                st = self.state.get(sticky)
                if st is None or st.cleared or st.exhausted or not st.discovered:
                    sticky = None
            if sticky is None:
                channel = self._two_opt_route(unresolved)[0]
            else:
                channel = sticky
            st = self.state[channel]
            center = self._clear_decision(st)
            if center is not None:
                if self._try_clear(center, channel):
                    st.cleared = True
                    self._coobserve(center, channel)
                continue
            if st.attempts >= 30:
                if not self._corridor_clear(channel, st):
                    st.exhausted = True
                continue
            point = self._next_measurement_point(st)
            if point is None:
                if not self._corridor_clear(channel, st):
                    st.exhausted = True
                continue
            self.observe(point, channel)
            st.attempts += 1
            self._coobserve(point, channel)
            if (not st.cleared and not st.exhausted
                    and self._snapshot(st).circle.radius_m <= self.ready_radius_m):
                sticky = channel
        self.sim.exit()
        return self.summary()


class StickyOnlyAgent(CertRouteAgent):
    """仅粘滞(锚点保持目标位置), 用于消融。"""

    ready_radius_m = 60.0

    def run(self) -> dict:
        return StickyActionAgent.run(self)


if __name__ == "__main__":
    print("iter2 agents ready")

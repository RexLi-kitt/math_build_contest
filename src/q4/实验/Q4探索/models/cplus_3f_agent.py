"""C+3F-lite 模型：选择性共观测（只在该测站可能收到信号时才补测）。

机制与依据（离线动作画像）：
- C+3A 的收益全部来自 11%—17% 的有效方位，而 83%—89% 的补测是盲区观测；
- 盲区观测平均距离 2.0—2.1 km，远超接收半径上界 1500 m；
- `feasible_region.build_region_cached` 给出的凸多边形**必然包含真实源**
  （方位角带 ∩ 各观测站 1500 m 圆域），且题设保证接收半径 R ≤ 1500 m。
  因此"候选测站到该可行域的最小距离 > 1500 m"⟹ 该测站不可能收到该频道信号，
  跳过它不会丢失任何可能成功的观测，属于零漏检风险剪枝。

实现要点：
- 只在门控选中 C 路线时启用（B 分支保持原行为，边界场景与 C+ 逐案例同值）；
- 距离用凸多边形的顶点与边计算，避免最小距离落在边中段时被高估；
- 被剪掉的观测若换成真实测量，平均要花 5 秒检测（还可能加 1 秒切换），
  所以剪枝只省虚拟时间，不消耗额外动作。

接入：
    from cplus_3f_agent import CPlus3FLiteAgent
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from cplus_3a_agent import CPlus3AzimuthAgent  # noqa: E402
from feasible_region import MAX_DIRECTION_R  # noqa: E402


def point_segment_distance(point, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    denominator = dx * dx + dy * dy
    if denominator <= 1e-12:
        return math.dist(point, a)
    t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / denominator
    t = max(0.0, min(1.0, t))
    return math.hypot(point[0] - (a[0] + t * dx), point[1] - (a[1] + t * dy))


class CPlus3FLiteAgent(CPlus3AzimuthAgent):
    """C+3A 的门控与方位目标不变，只在证明不可能收到信号时跳过共观测。"""

    reach_limit_m = MAX_DIRECTION_R  # 题设接收半径上界，1500 m

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.pruned_observations = 0
        self.coobservations = 0

    # ------------------------------------------------------------------ 距离门

    def within_reach(self, point, state) -> bool:
        """候选测站到该频道保守可行域的最小距离是否不超过接收半径上界。"""
        polygon = self._snapshot(state).polygon
        if not polygon:
            return True
        limit = self.reach_limit_m
        count = len(polygon)
        for index, a in enumerate(polygon):
            b = polygon[(index + 1) % count]
            if point_segment_distance(point, a, b) <= limit:
                return True
        return False

    # --------------------------------------------------------------- 共观测

    def _coobserve(self, point, primary_channel: int) -> None:
        # B 分支保持原行为；原点扫描阶段（尚未选定路线）也走原实现。
        if self.selected_search_order != "C":
            return super()._coobserve(point, primary_channel)
        # 以下与 Q4TriangularCoverageAgent._coobserve 逐行一致，仅插入距离门。
        for channel, state in self.state.items():
            if (channel == primary_channel or state.cleared or state.exhausted
                    or not state.discovered
                    or len(state.observations) >= self.coverage_observation_target):
                continue
            if any(math.dist(point, old) <= 1.0 for old in state.probed_points):
                continue
            if not self.within_reach(point, state):
                self.pruned_observations += 1
                continue
            result = self.observe(point, channel)
            # 背面无信号是正常的方位筛查，不占用后续主动定位的10次预算。
            if result in ("direction", "near"):
                state.attempts += 1
            self.co_measurements += 1
            self.coobservations += 1


if __name__ == "__main__":
    print("C+3F-lite: 距离上界", CPlus3FLiteAgent.reach_limit_m,
          "m；C 分支方位目标",
          CPlus3FLiteAgent.c_route_observation_target)

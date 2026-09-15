"""C+3F-B：给 B 分支的搜索期共观测加上同一个 1500 m 距离门。

设计约束（用户口径）：
1. B 路线、站点顺序、方位目标 2 **全部不变**，站点集不变 → 覆盖证书天然保留；
2. 只对 B 分支的 `_coobserve` 增加与 C 分支相同的保守可行域判断；
3. 走 C 分支的案例（normal / min-radius / mixed）应与 C+3F **逐案例完全一致**；
4. 被剪观测需可用模拟器真值审计："本来能够成功却被剪掉"必须为 0。

距离门依据：题设接收半径下界为 1000 m，而可行性判据用的是**上界** 1500 m，
因此通过该判据的点只是在"最坏情况"下才可能收到；在 B 分支参与的边界场景里
接收半径恰为 1000 m，剪枝在该场景下不可能漏掉任何能成功的观测。

接入：
    from cplus_3fb_agent import CPlus3FBAgent
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from cplus_3f_agent import CPlus3FLiteAgent, point_segment_distance  # noqa: E402


class CPlus3FBAgent(CPlus3FLiteAgent):
    """在 C+3F 基础上把距离门扩展到 B 分支（B 分支其余行为不变）。"""

    filter_b_route = True
    audit_truth = True

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.pruned_truth_hits = 0
        self.pruned_samples = []

    # ------------------------------------------------------------------ 真值

    def truth_success(self, point, channel) -> bool:
        """模拟器真值：该点此刻对这个频道是否本来能够收到信号。"""
        for source in getattr(self.sim, "sources", []):
            if getattr(source, "channel", None) != channel:
                continue
            if getattr(source, "cleared", False):
                continue
            if math.dist(point, source.position) > source.receive_radius + 1e-9:
                continue
            beam = getattr(source, "beam_direction", None)
            if beam is None:
                return True
            bearing = math.degrees(math.atan2(point[1] - source.position[1],
                                              point[0] - source.position[0])) % 360.0
            if abs((bearing - beam + 180.0) % 360.0 - 180.0) <= 90.0 + 1e-9:
                return True
        return False

    # --------------------------------------------------------------- 共观测

    def _coobserve(self, point, primary_channel: int) -> None:
        # selected_search_order 在原点扫描阶段为 None、门控选定后才是 "B"/"C"，
        # 所以这里用 == "B" 精确框定"B 分支（搜索期）"：
        #   C 分支与原点扫描阶段 -> 完全交给 C+3F（逐行一致）；
        #   B 分支 -> 在原有行为上追加同一个距离门。
        if self.selected_search_order != "B" or not self.filter_b_route:
            return super()._coobserve(point, primary_channel)
        for channel, state in self.state.items():
            if (channel == primary_channel or state.cleared or state.exhausted
                    or not state.discovered
                    or len(state.observations) >= self.coverage_observation_target):
                continue
            if any(math.dist(point, old) <= 1.0 for old in state.probed_points):
                continue
            if not self.within_reach(point, state):
                self.pruned_observations += 1
                if self.audit_truth:
                    polygon = self._snapshot(state).polygon
                    nearest = (min(point_segment_distance(point, polygon[i],
                                                          polygon[(i + 1) % len(polygon)])
                                   for i in range(len(polygon)))
                               if polygon else None)
                    hit = self.truth_success(point, channel)
                    if hit:
                        self.pruned_truth_hits += 1
                    if len(self.pruned_samples) < 3:
                        self.pruned_samples.append({
                            "channel": channel,
                            "point": [round(point[0], 1), round(point[1], 1)],
                            "min_dist_m": round(nearest, 1) if nearest is not None else None,
                            "truth_success": hit,
                        })
                continue
            result = self.observe(point, channel)
            if result in ("direction", "near"):
                state.attempts += 1
            self.co_measurements += 1
            self.coobservations += 1


if __name__ == "__main__":
    print("C+3F-B：距离门", CPlus3FBAgent.reach_limit_m,
          "m；B 分支过滤", CPlus3FBAgent.filter_b_route)

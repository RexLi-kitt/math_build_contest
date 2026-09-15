"""C+3A 模型：C+ 门控不变，仅在门控选中 C 路线时把搜索期目标方位数从 2 提到 3。

动机（离线动作画像）：
- C 在压力场景的额外时间几乎全在搜索后定位阶段：搜索后测量点数是 B 的 1.8 倍、
  搜索后移动是 1.5 倍，说明搜索期攒下的方位几何质量不足；
- 把搜索期每条已发现频道的目标方位数从 2 提到 3，正常场景 300 例配对
  617.45 → 605.46 s/源（−11.98，95% CI [−16.00, −7.97]），P95 与 CVaR90 同步改善；
  混合象限 717.31 → 711.33（−5.98，CI [−11.85, −0.11]）；
- 代价：全部源取最小接收半径的场景反向 613.30 → 621.54（+8.24，CI [+3.47, +13.01]）。

因此本模型只在门控已经决定走 C 路线时提高方位数；走 B 路线时保持 B 的原始行为
（方位数 2），以免改动 B 已验证多年的边界性能。站点集与几何证书完全不变。

接入：
    from cplus_3a_agent import CPlus3AzimuthAgent
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FALLBACK_ROOT = Path(r"C:\Users\李\Desktop\Q4保底基线")
MODEL_ROOT = next((candidate for candidate in (HERE / "C+模型", HERE.parent / "C+模型")
                   if (candidate / "cplus_gate_agent.py").exists()), None)
MODEL_ROOT = MODEL_ROOT.parent if MODEL_ROOT else FALLBACK_ROOT

CPLUS_DIR = MODEL_ROOT / "C+模型"
if str(CPLUS_DIR) not in sys.path:
    sys.path.insert(0, str(CPLUS_DIR))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CPlus = _load("q4_cplus_for_3a", CPLUS_DIR / "cplus_gate_agent.py")


class CPlus3AzimuthAgent(_CPlus.CPlusGateAgent):
    """门控与 C+ 相同；C 分支搜索期目标方位数 3，B 分支保持 2。"""

    discovery_threshold = 0
    c_route_observation_target = 3
    b_route_observation_target = 2
    _route_cache = None

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.coverage_observation_target = self.b_route_observation_target

    def search(self) -> None:
        # 与 C+BaseAgent.search 逐行一致，只在选定路线后调整方位目标。
        origin = (0.0, 0.0)
        for channel, state in self.state.items():
            if not state.discovered:
                self.observe(origin, channel)
        self._coobserve(origin, -1)
        self.origin_discoveries = sum(
            state.discovered for state in self.state.values())

        selected = ("B" if self.origin_discoveries <= self.discovery_threshold
                    else "C")
        self.selected_search_order = selected
        self.search_points = list(self._routes()[selected])
        self.coverage_observation_target = (
            self.c_route_observation_target if selected == "C"
            else self.b_route_observation_target)

        remaining = list(self.search_points[1:])
        while remaining and sum(state.discovered for state in self.state.values()) < 16:
            point = remaining.pop(0)
            for channel, state in self.state.items():
                if not state.discovered:
                    self.observe(point, channel)
            self._coobserve(point, -1)
            following = remaining[0] if remaining else None
            self._opportunistic_clear(following)
            self.say(
                f"C+3A {selected}路线：原点发现{self.origin_discoveries}个，"
                f"当前共发现{sum(s.discovered for s in self.state.values())}个")
        self.search_end_time_s = self.sim.time_s


if __name__ == "__main__":
    routes = CPlus3AzimuthAgent._routes()
    print({name: len(route) for name, route in routes.items()})
    print("C 分支方位数:", CPlus3AzimuthAgent.c_route_observation_target,
          " B 分支方位数:", CPlus3AzimuthAgent.b_route_observation_target)

"""出货代理: 读取认证设计 JSON, 按 TSP 顺序停靠。

search() 直接遍历 self.search_points, 因此把设计站点按 order 排好即可。
设计文件默认 best_design.json(激进版) / safe_design.json(保守版)。
"""
from __future__ import annotations

import json
from pathlib import Path

from q4_experiment import Q4TriangularCoverageAgent

HERE = Path(__file__).resolve().parent


class CertRouteAgent(Q4TriangularCoverageAgent):
    """出货冠军: 27 站 / 20.4 km / 管道云 gap 162.5 度。

    验证: 正常500局 667.36 s/源(100%), 边界压力200局 572.67 s/源(100%);
    对比 ShiftB 756.10 / 702.78, H8 713.42 / 638.58。
    """

    coverage_observation_target = 2
    design_file = HERE / "winner_design.json"
    _design = None

    @classmethod
    def _load(cls):
        if cls._design is None:
            data = json.loads(cls.design_file.read_text(encoding="utf-8"))
            sites = [tuple(p) for p in data["sites"]]
            order = list(data["order"])
            cls._design = ([sites[i] for i in order], data)
        return cls._design

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.search_points = list(self._load()[0])

    def _coverage_order(self, unvisited):
        return list(unvisited)


class CertRouteAggressiveAgent(CertRouteAgent):
    """激进版: 29 站 / 18.1 km / 管道云 gap 173.9 度(正常 672.84, 压力 708.02)。"""

    design_file = HERE / "aggressive_design.json"
    _design = None


CertRouteSafeAgent = CertRouteAgent  # 兼容旧名


if __name__ == "__main__":
    for cls in (CertRouteAgent, CertRouteAggressiveAgent):
        pts, data = cls._load()
        print(f"{cls.__name__}: n={len(pts)} tour={data.get('tour_m', 0):.0f}m "
              f"gap_tube={data.get('gap_tube', 0):.2f} file={cls.design_file.name}")

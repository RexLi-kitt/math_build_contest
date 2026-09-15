"""B+ 模型出货代理: 认证环路线 + 覆盖优先访问顺序 (Certified Route, coverage-first)。

- `CertRouteAgent`            B+ 冠军: 27 站 / 20.85 km / 证书 gap 162.2°
                              正常500局 654.85 s/源(100%), 压力200局 589.34 s/源(100%)
- `CertRouteAggressiveAgent`  备选: 29 站 / 18.1 km / 证书 gap 173.9°

B+ 与 B 的唯一区别是访问顺序: 同一站点集合下, 用"尽早覆盖"的顺序
(未覆盖面积和 3.61 vs TSP 5.50), 检测成本降 ~14 s/源, 正常场景净收益 -1.9%;
代价是边界对抗场景 +2.9%(仍 100% 清除)。证书只依赖站点集合, 顺序改动零风险。

依赖基线模块 `q4_experiment`; 若官方 runner 未将其目录加入 sys.path,
本模块会自动把 `C:\\Users\\李\\Desktop\\第四问定向源实验` 追加进去。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

try:
    from q4_experiment import Q4TriangularCoverageAgent
except ImportError:  # 官方 runner 环境兜底
    _BASE = Path(r"C:\Users\李\Desktop\第四问定向源实验")
    if _BASE.exists():
        sys.path.insert(0, str(_BASE))
    from q4_experiment import Q4TriangularCoverageAgent


class CertRouteAgent(Q4TriangularCoverageAgent):
    """B+ 冠军: 27 站认证路线 + 覆盖优先顺序。"""

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
        # search() 直接按 search_points 列表顺序停靠, 此方法仅作语义兜底。
        return list(unvisited)


class CertRouteAggressiveAgent(CertRouteAgent):
    """B+ 备选(更短但证书余量更小): 29 站。"""

    design_file = HERE / "aggressive_design.json"
    _design = None  # 显式声明, 避免继承父类已加载的缓存


if __name__ == "__main__":
    for cls in (CertRouteAgent, CertRouteAggressiveAgent):
        pts, data = cls._load()
        print(f"{cls.__name__}: n={len(pts)} tour={data.get('tour_m', 0):.0f}m "
              f"gap_certify={data.get('gap_grid_5_025', 0):.2f} "
              f"gap_tube={data.get('gap_tube', 0):.2f}")

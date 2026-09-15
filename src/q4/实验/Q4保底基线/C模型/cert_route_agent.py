"""C 模型出货代理: 认证环路线 + 激进设计(29站) + 覆盖优先顺序。

- `CertRouteAgent`              C 冠军: 29 站 / 18.3 km / 证书 gap 173.9°
                                正常500局 625.0/628.0 s/源(两独立种子, 100%),
                                全R=1000均匀场景 437.4 s/源(比 B+ 快 13%)
- `CertRouteConservativeAgent`  B+ 退路: 27 站 / 20.9 km / 证书 gap 162.2°,
                                对抗边界场景更稳(589 vs 774), 正常慢 ~5%

官方生成器(均匀位置, R∈[1000,1500], 随机波束)的所有已验证场景中 C 大赢或
打平; C 的已知弱点仅是"全贴边+波束全朝外"人造对抗角落(仍 100% 清除)。
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
    """C 冠军: 29 站认证路线 + 覆盖优先顺序。"""

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


class CertRouteConservativeAgent(CertRouteAgent):
    """B+ 退路(对抗边界场景更稳, 正常慢约 5%)。"""

    design_file = HERE / "conservative_design.json"
    _design = None  # 显式声明, 避免继承父类已加载的缓存


if __name__ == "__main__":
    for cls in (CertRouteAgent, CertRouteConservativeAgent):
        pts, data = cls._load()
        print(f"{cls.__name__}: n={len(pts)} tour={data.get('tour_m', 0):.0f}m "
              f"gap_certify={data.get('gap_grid_5_025', 0):.2f} "
              f"gap_tube={data.get('gap_tube', 0):.2f}")

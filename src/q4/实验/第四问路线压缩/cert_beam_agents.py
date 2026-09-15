"""迭代 4: 波束感知选点 (BeamAware/BeamChase) 接到 B 模型。

诊断: 搜索后测量行程 20% 是背面白跑(no_signal 1.27 次/源)。基线已有
BeamAwareMixin(按波束可见概率加权 D-opt 评分)与 BeamChaseMixin(+可见性
候选池与示向追踪), 此前只接过 H8, 未接过 27 站认证路线。
"""
from __future__ import annotations

from cert_route_agent import CertRouteAgent
from fast_q4 import BeamAwareMixin, BeamChaseMixin


class CertBeamAgent(BeamAwareMixin, CertRouteAgent):
    """波束感知 D-opt 评分。"""


class CertChaseAgent(BeamChaseMixin, CertRouteAgent):
    """波束感知 + 可见性候选池 + 示向追踪。"""


if __name__ == "__main__":
    print("beam agents ready")

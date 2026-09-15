"""顺序变体代理: 证书不变, 只换访问顺序。

order_variants.json  : 纯覆盖目标 (greedy_dens / greedy_area / tsp)
order_variants2.json : 边界加权覆盖目标 (mix_a0 / mix_a1 / mix_a3)
"""
from __future__ import annotations

import json
from pathlib import Path

from cert_route_agent import CertRouteAgent

HERE = Path(__file__).resolve().parent
_VARIANTS = json.loads((HERE / "order_variants.json").read_text(encoding="utf-8"))
_VARIANTS2 = json.loads((HERE / "order_variants2.json").read_text(encoding="utf-8"))
_VARIANTS3 = json.loads((HERE / "order_variants3.json").read_text(encoding="utf-8"))


class _OrderAgent(CertRouteAgent):
    variant = None
    variant_source = None
    _order_cache = None

    @classmethod
    def _load(cls):
        if cls._order_cache is None:
            data = json.loads(cls.design_file.read_text(encoding="utf-8"))
            sites = [tuple(p) for p in data["sites"]]
            order = cls.variant_source[cls.variant]["order"]
            cls._order_cache = ([sites[i] for i in order], data)
        return cls._order_cache


class OrderDensAgent(_OrderAgent):
    variant = "greedy_dens"
    variant_source = _VARIANTS
    _order_cache = None


class OrderAreaAgent(_OrderAgent):
    variant = "greedy_area"
    variant_source = _VARIANTS
    _order_cache = None


class OrderTspReoptAgent(_OrderAgent):
    variant = "tsp"
    variant_source = _VARIANTS
    _order_cache = None


class MixA0Agent(_OrderAgent):
    variant = "mix_a0"
    variant_source = _VARIANTS2
    _order_cache = None


class MixA1Agent(_OrderAgent):
    variant = "mix_a1"
    variant_source = _VARIANTS2
    _order_cache = None


class MixA3Agent(_OrderAgent):
    variant = "mix_a3"
    variant_source = _VARIANTS2
    _order_cache = None


class MixB05Agent(_OrderAgent):
    variant = "mixb_w0.5"
    variant_source = _VARIANTS3
    _order_cache = None


class MixB1Agent(_OrderAgent):
    variant = "mixb_w1"
    variant_source = _VARIANTS3
    _order_cache = None


class MixB2Agent(_OrderAgent):
    variant = "mixb_w2"
    variant_source = _VARIANTS3
    _order_cache = None


if __name__ == "__main__":
    for cls in (OrderDensAgent, OrderAreaAgent, MixA0Agent, MixA1Agent, MixA3Agent):
        pts, _ = cls._load()
        print(cls.__name__, len(pts), "sites")

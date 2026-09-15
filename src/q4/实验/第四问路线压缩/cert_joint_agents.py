"""联合优化候选代理: 从 joint_eval_results.json 读站点+顺序。"""
from __future__ import annotations

import json
from pathlib import Path

from cert_route_agent import CertRouteAgent

HERE = Path(__file__).resolve().parent
_EVAL = json.loads((HERE / "joint_eval_results.json").read_text(encoding="utf-8"))
_BY_NAME = {r["name"]: r for r in _EVAL}


class _JointAgent(CertRouteAgent):
    variant = None
    _cache = None

    @classmethod
    def _load(cls):
        if cls._cache is None:
            r = _BY_NAME[cls.variant]
            sites = [tuple(p) for p in r["sites"]]
            order = list(r["order"])
            cls._cache = ([sites[i] for i in order],
                          {"tour_m": r["tour_refined"], "n_sites": r["n"]})
        return cls._cache


class AggOrderAgent(_JointAgent):
    variant = "aggressive"
    _cache = None


class BNewOrderAgent(_JointAgent):
    variant = "B_winner"
    _cache = None


if __name__ == "__main__":
    for cls in (AggOrderAgent, BNewOrderAgent):
        pts, d = cls._load()
        print(cls.__name__, len(pts), "sites, tour", round(d["tour_m"]))

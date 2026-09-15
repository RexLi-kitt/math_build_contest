"""精炼设计代理: 读取 refined_design.json (模拟器在环精炼结果)。"""
from __future__ import annotations

from pathlib import Path

from cert_route_agent import CertRouteAgent

HERE = Path(__file__).resolve().parent


class RefinedAgent(CertRouteAgent):
    design_file = HERE / "refined_design.json"
    _design = None


if __name__ == "__main__":
    pts, d = RefinedAgent._load()
    print("RefinedAgent:", len(pts), "sites, tour", round(d.get("tour_m", 0)))

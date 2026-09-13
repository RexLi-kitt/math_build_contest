"""核对Q4最终D模型的B/C路线资产与距离门边界不变量。"""
from __future__ import annotations

import json
import math
from pathlib import Path

from q4_solver import select_route, should_coobserve

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets" / "d_model"


def load_route(filename: str) -> list[tuple[float, float]]:
    payload = json.loads((ASSETS / filename).read_text(encoding="utf-8"))
    sites = [tuple(map(float, point)) for point in payload["sites"]]
    return [sites[index] for index in payload["order"]]


def verify() -> dict[str, object]:
    routes = {
        "B": load_route("b_winner_design.json"),
        "C": load_route("c_winner_design.json"),
    }
    assert len(routes["B"]) == 27 and len(routes["C"]) == 29
    assert all(route[0] == (0.0, 0.0) for route in routes.values())
    assert all(len(set(route)) == len(route) for route in routes.values())
    assert select_route(0) == "B" and all(select_route(n) == "C" for n in (1, 2, 3))

    region = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
    assert should_coobserve((1501.0, 0.0), region)
    assert not should_coobserve((1501.1, 0.0), region)

    return {
        name: {
            "stations": len(route),
            "max_radius_m": round(max(math.hypot(*point) for point in route), 3),
        }
        for name, route in routes.items()
    }


if __name__ == "__main__":
    print(verify())

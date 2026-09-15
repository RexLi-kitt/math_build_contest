"""第二步续三：在 C 的认证站点集**不变**的前提下，只改访问顺序。

站点集不变意味着证书（发现覆盖保证）完全不变，是零风险改动。压力场景里 C 的
检测代价爆炸，根因是外圈源要等到外圈测站才被发现；把外圈测站提前即可验证。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402
from q4_experiment import Q4TriangularCoverageAgent  # noqa: E402

OUT = H.SANDBOX_OUT / "step2d_order"
C_DIR = H.MODELS / "C模型"

_C_DESIGN = json.loads((C_DIR / "winner_design.json").read_text(encoding="utf-8"))
_C_SITES = [tuple(point) for point in _C_DESIGN["sites"]]
_C_ORDER = [_C_SITES[index] for index in _C_DESIGN["order"]]
_C_BASE = H._load("q4x_c_base", C_DIR / "cert_route_agent.py").CertRouteAgent


def radius(point):
    return math.hypot(point[0], point[1])


def rim_first(threshold: float):
    origin = _C_ORDER[0]
    rest = _C_ORDER[1:]
    outer = [p for p in rest if radius(p) >= threshold]
    inner = [p for p in rest if radius(p) < threshold]
    return [origin] + outer + inner


def nn_from_origin(points):
    remaining = list(points)
    route = []
    current = (0.0, 0.0)
    while remaining:
        nxt = min(remaining, key=lambda p: math.dist(current, p))
        remaining.remove(nxt)
        route.append(nxt)
        current = nxt
    return route


def rim_first_nn(threshold: float):
    origin = _C_ORDER[0]
    rest = _C_ORDER[1:]
    outer = [p for p in rest if radius(p) >= threshold]
    inner = [p for p in rest if radius(p) < threshold]
    return [origin] + nn_from_origin(outer) + nn_from_origin(inner)


def make_agent(order):
    class _OrderedC(_C_BASE):
        _design = ([tuple(p) for p in order], _C_DESIGN)

    _OrderedC.__name__ = "OrderedC"
    return _OrderedC


VARIANTS = {
    "C": _C_BASE,
    "Crim1500": make_agent(rim_first(1500.0)),
    "Crim1700": make_agent(rim_first(1700.0)),
    "CrimNN": make_agent(rim_first_nn(1500.0)),
}
for name, cls in VARIANTS.items():
    H._STRATEGIES[name] = cls


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--normal", type=int, default=300)
    args = parser.parse_args()

    for label, order in (("Crim1500", rim_first(1500.0)),
                         ("Crim1700", rim_first(1700.0)),
                         ("CrimNN", rim_first_nn(1500.0))):
        tour = sum(math.dist(a, b) for a, b in zip([(0.0, 0.0)] + order, order))
        outer = sum(1 for p in order[1:] if radius(p) >= 1500)
        H.log(f"{label}: 站点 {len(order)}，外圈站 {outer}，"
              f"巡游长度 {tour / 1000:.2f} km（C 原顺序 "
              f"{sum(math.dist(a, b) for a, b in zip([(0.0, 0.0)] + _C_ORDER, _C_ORDER)) / 1000:.2f} km）")

    scenarios = [
        ("normal", H.normal_cases(args.normal, 20261021), 20261021),
        ("min_radius", H.min_radius_cases(200, 20261022), 20261022),
        ("boundary_random", H.boundary_cases(200, 20261023, False), 20261023),
        ("boundary_outward", H.boundary_cases(200, 20261024, True), 20261024),
        ("mixed", H.mixed_cases(200, 20261025), 20261025),
    ]
    names = list(VARIANTS)
    summary = {}
    for label, cases, seed in scenarios:
        rows, summaries = H.evaluate(label, cases, seed, names, args.jobs, OUT)
        summary[label] = {item["strategy"]: item for item in summaries}
        H.log(f"\n--- {label}（{len(cases)} 例）---")
        H.log(f"{'策略':<10}{'均值':>9}{'P95':>9}{'CVaR90':>9}"
              f"{'搜索移动':>10}{'搜索后移动':>11}{'检测':>9}{'全清除':>8}")
        for item in summaries:
            H.log(f"{item['strategy']:<10}{item['mean_s_per_source']:>9.2f}"
                  f"{item['p95_s_per_source']:>9.2f}"
                  f"{item['cvar90_s_per_source']:>9.2f}"
                  f"{item['mean_search_movement_s']:>10.2f}"
                  f"{item['mean_post_search_movement_s']:>11.2f}"
                  f"{item['mean_detection_s']:>9.2f}"
                  f"{item['all_clear']:>5}/{item['cases']}")
    (OUT / "order_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

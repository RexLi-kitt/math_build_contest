"""第四步：针对定位阶段瓶颈，检验 C 的搜索期方位条数（coverage_observation_target）。

动作画像显示 C 在压力场景的额外时间集中在搜索后定位：搜索后测量点数是 B 的 1.8 倍、
搜索后移动是 1.5 倍。若根因是搜索期攒下的方位几何质量不足，提高搜索期每条已发现
频道的目标方位数应当直接减少后续补测。站点集与证书均不变。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402

OUT = H.SANDBOX_OUT / "step4_azimuth"
_C_BASE = H._load("q4x_c_base2", H.MODELS / "C模型" / "cert_route_agent.py").CertRouteAgent


def make_variant(target):
    class _AzimuthC(_C_BASE):
        coverage_observation_target = target

    _AzimuthC.__name__ = f"CAz{target}"
    return _AzimuthC


VARIANTS = {
    "C": _C_BASE,
    "CAz3": make_variant(3),
    "CAz4": make_variant(4),
}
for name, cls in VARIANTS.items():
    H._STRATEGIES[name] = cls


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--normal", type=int, default=300)
    args = parser.parse_args()

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
        H.log(f"{'策略':<8}{'均值':>9}{'P95':>9}{'CVaR90':>9}"
              f"{'搜索移动':>10}{'搜索后移动':>11}{'检测':>9}{'全清除':>9}")
        for item in summaries:
            H.log(f"{item['strategy']:<8}{item['mean_s_per_source']:>9.2f}"
                  f"{item['p95_s_per_source']:>9.2f}"
                  f"{item['cvar90_s_per_source']:>9.2f}"
                  f"{item['mean_search_movement_s']:>10.2f}"
                  f"{item['mean_post_search_movement_s']:>11.2f}"
                  f"{item['mean_detection_s']:>9.2f}"
                  f"{item['all_clear']:>6}/{item['cases']}")
    (OUT / "azimuth_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

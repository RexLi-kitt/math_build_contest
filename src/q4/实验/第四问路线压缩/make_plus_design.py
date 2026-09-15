"""合并 B+ 设计: 冠军站点 + OrdArea(覆盖优先)顺序 + B+ 验证数字。"""
import json
from pathlib import Path

HERE = Path(r"C:\Users\李\Desktop\第四问路线压缩")
design = json.loads((HERE / "winner_design.json").read_text(encoding="utf-8"))
variants = json.loads((HERE / "order_variants.json").read_text(encoding="utf-8"))
order = list(variants["greedy_area"]["order"])
sites = [tuple(p) for p in design["sites"]]
assert sorted(order) == list(range(len(sites)))

plus = {
    "name": "B+ (Certified Route, coverage-first order)",
    "sites": [list(p) for p in sites],
    "order": order,
    "tour_m": variants["greedy_area"]["tour_m"],
    "base_order_tour_m": design["tour_m"],
    "n_sites": len(sites),
    "gap_10_05": design["gap_10_05"],
    "gap_grid_5_025": design["gap_grid_5_025"],
    "gap_tube": design["gap_tube"],
    "worst_x": design["worst_x"],
    "tag": design["tag"],
    "ship": True,
    "validation": {
        "normal_500_seed20260923_s_per_source": 654.85,
        "normal_500_p95": 861.62,
        "normal_500_detection_s": 126.8,
        "normal_500_measure_actions": 315.4,
        "stress_200_seed20260924_s_per_source": 589.34,
        "stress_200_p95": 692.67,
        "baseline_B_normal": 667.36,
        "baseline_B_stress": 572.67,
        "baseline_shiftb_normal": 756.10,
        "baseline_shiftb_stress": 702.78,
        "baseline_h8_normal": 713.42,
        "baseline_h8_stress": 638.58,
    },
}
(HERE / "winner_design_plus.json").write_text(
    json.dumps(plus, indent=2), encoding="utf-8")
print("winner_design_plus.json written:")
print("  n:", plus["n_sites"], " tour:", plus["tour_m"],
      " gap_tube:", round(plus["gap_tube"], 2))
print("  order[0:5]:", order[:5])

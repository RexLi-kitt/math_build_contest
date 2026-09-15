"""合并 C 模型设计: 激进站点 + 覆盖优先顺序 + 全部验证数字。"""
import json
from pathlib import Path

HERE = Path(r"C:\Users\李\Desktop\第四问路线压缩")
agg = json.loads((HERE / "aggressive_design.json").read_text(encoding="utf-8"))
ev = json.loads((HERE / "joint_eval_results.json").read_text(encoding="utf-8"))
by = {r["name"]: r for r in ev}
r = by["aggressive"]
sites = [tuple(p) for p in r["sites"]]
order = list(r["order"])
assert sorted(order) == list(range(len(sites)))

design = {
    "name": "C (Certified Route, aggressive design + coverage-first order)",
    "sites": [list(p) for p in sites],
    "order": order,
    "tour_m": r["tour_refined"],
    "n_sites": len(sites),
    "gap_10_05": agg["gap_10_05"],
    "gap_grid_5_025": agg["gap_grid_5_025"],
    "gap_tube": agg["gap_tube"],
    "worst_x": agg["worst_x"],
    "tag": "C",
    "ship": True,
    "validation": {
        "normal_500_seed20260923_s_per_source": 625.00,
        "normal_500_seed20260923_p95": 815.89,
        "normal_500_seed20260925_s_per_source": 627.95,
        "normal_500_seed20260925_p95": 820.07,
        "stress_200_seed20260924_s_per_source": 774.20,
        "stress_200_seed20260924_p95": 974.53,
        "risk_map_minR_uniform_seed20260931": 437.35,
        "risk_map_boundary_randbeam_seed20260932": 575.97,
        "baseline_Bplus_normal_20260923": 654.85,
        "baseline_Bplus_normal_20260925": 661.49,
        "baseline_Bplus_stress_20260924": 589.34,
        "baseline_Bplus_minR_uniform": 502.85,
        "baseline_Bplus_boundary_randbeam": 572.72,
    },
}
(HERE / "c_design.json").write_text(json.dumps(design, indent=2),
                                    encoding="utf-8")
print("c_design.json written: n=", design["n_sites"],
      " tour=", round(design["tour_m"]), " gap_tube=", round(design["gap_tube"], 2))

"""把 Cref 精炼版合并进 C 设计 (保留证书/验证元数据)。"""
import json
import sys
from pathlib import Path

HERE = Path(r"C:\Users\李\Desktop\第四问路线压缩")
sys.path.insert(0, HERE)
sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")
from strong_tsp import route_cost  # noqa: E402

c = json.loads((HERE / "c_design.json").read_text(encoding="utf-8"))
ref = json.loads((HERE / "refined_design.json").read_text(encoding="utf-8"))
print("order 相同:", c["order"] == ref["order"])
sites = [tuple(p) for p in ref["sites"]]
order = list(ref["order"])
pts = [sites[i] for i in order]
tour = route_cost(list(range(len(pts))), pts)
print("Cref tour (按访问顺序):", round(tour, 1))

merged = dict(c)
merged["sites"] = ref["sites"]
merged["order"] = ref["order"]
merged["tour_m"] = tour
merged["name"] = "C (refined: simulator-in-the-loop station tuning)"
merged["refinement"] = {
    "method": "simulator-in-the-loop local search",
    "screen_seed": ref["screen_seed"],
    "screen_cases": ref["screen_cases"],
    "screen_mean_before": 620.31,
    "screen_mean_after": ref["screen_mean"],
}
merged["validation"].update({
    "normal_500_seed20260934_Cref": 625.65,
    "normal_500_seed20260934_C": 631.25,
    "normal_500_seed20260925_Cref": 625.67,
    "normal_500_seed20260925_C": 627.95,
    "stress_200_seed20260924_Cref": 774.08,
})
(HERE / "c_design_refined.json").write_text(json.dumps(merged, indent=2),
                                            encoding="utf-8")
Path(r"C:\Users\李\Desktop\Q4保底基线\C模型\winner_design.json").write_text(
    json.dumps(merged, indent=2), encoding="utf-8")
print("merged -> c_design_refined.json + C模型/winner_design.json")

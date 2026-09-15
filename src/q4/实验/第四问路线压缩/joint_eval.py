"""对现有设计池做联合目标复评: finalists.json + B + 激进 + 冒烟版。"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from joint_tools import evaluate_design, refine_order, joint_J, make_masks  # noqa: E402
from strong_tsp import route_cost  # noqa: E402


def work(item):
    name, sites = item
    J0, tour0, unc0, order0 = evaluate_design(sites)
    masks = make_masks(sites)
    order1, _ = refine_order(order0, masks, sites, max_passes=120)
    tour1 = route_cost(order1, sites)
    J1 = joint_J(sites, order1, masks)
    return {
        "name": name,
        "n": len(sites),
        "J_greedy": J0, "tour_greedy": tour0, "unc_greedy": unc0,
        "J_refined": J1, "tour_refined": tour1,
        "order": order1, "sites": [list(p) for p in sites],
    }


def main():
    items = []
    fin = json.loads((HERE / "finalists.json").read_text(encoding="utf-8"))
    for i, d in enumerate(fin):
        if d.get("ship"):
            items.append((f"fin_{d['tag']}_{i}", [tuple(p) for p in d["sites"]]))
    for fname, tag in (("winner_design.json", "B_winner"),
                       ("aggressive_design.json", "aggressive")):
        d = json.loads((HERE / fname).read_text(encoding="utf-8"))
        items.append((tag, [tuple(p) for p in d["sites"]]))

    results = []
    with ProcessPoolExecutor(max_workers=16) as pool:
        for res in pool.map(work, items):
            results.append(res)
    results.sort(key=lambda r: r["J_refined"])
    print(f"{'design':>22} {'n':>3} {'tour':>7} {'unc':>6} {'J(s/局)':>8}")
    for r in results:
        print(f"{r['name']:>22} {r['n']:>3} {r['tour_refined']:7.0f} "
              f"{r['unc_greedy']:6.2f} {r['J_refined']:8.0f}")
    (HERE / "joint_eval_results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    print("saved joint_eval_results.json")


if __name__ == "__main__":
    main()

"""Build the 3-seed x 1000-case pooled table for C..J+ from existing result dirs."""
from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ("C_region_q2", "Cplus_completion_coobserve", "F_coverage_integrated",
          "G_rolling_coverage", "I_ring_optimized", "J_ring7_1000", "Jplus_final")
SHORT = {"C_region_q2": "C", "Cplus_completion_coobserve": "C+",
         "F_coverage_integrated": "F", "G_rolling_coverage": "G",
         "I_ring_optimized": "I", "J_ring7_1000": "J", "Jplus_final": "J+"}
SEED_DIRS = {
    55021: ["results/robustness_jplus/seed_55021"],
    24119: ["results/robustness_jplus/seed_24119"],
    90317: ["results/robustness/seed_90317", "results/jplus_seed90317"],
}
PAIRS = (("I_ring_optimized", "J_ring7_1000"),
         ("J_ring7_1000", "Jplus_final"),
         ("I_ring_optimized", "Jplus_final"))


def percentile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)]


def load():
    rows = []
    for seed, dirs in SEED_DIRS.items():
        for directory in dirs:
            path = ROOT / directory / "case_results.csv"
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    row["seed"] = int(row["seed"])
                    row["case"] = int(row["case"])
                    rows.append(row)
    return rows


def stats(rows):
    total = [float(r["total_virtual_time_s"]) for r in rows]
    n = [int(r["source_count"]) for r in rows]
    per = [t / k for t, k in zip(total, n)]
    movement = [float(r["movement_time_s"]) / k for r in rows for k in [int(r["source_count"])]]
    detect = [(float(r["total_virtual_time_s"]) - float(r["movement_time_s"])
               - 5.0 * int(r["source_count"])) / int(r["source_count"]) for r in rows]
    return {
        "cases": len(rows),
        "all_cleared_rate": statistics.mean(int(r["all_cleared"]) for r in rows),
        "failed_clears": statistics.mean(int(r["failed_clear_actions"]) for r in rows),
        "mean_per_source_s": statistics.mean(per),
        "median_per_source_s": statistics.median(per),
        "p95_per_source_s": percentile(per, .95),
        "max_per_source_s": max(per),
        "var_per_source": statistics.variance(per),
        "mean_movement_s": statistics.mean(movement),
        "mean_detect_switch_s": statistics.mean(detect),
    }


def main():
    rows = load()
    payload = {"seeds": {}, "pooled": {}, "paired": {}}
    for seed in SEED_DIRS:
        payload["seeds"][str(seed)] = {
            SHORT[m]: stats([r for r in rows if r["seed"] == seed and r["strategy"] == m])
            for m in MODELS if any(r["seed"] == seed and r["strategy"] == m for r in rows)
        }
    for model in MODELS:
        payload["pooled"][SHORT[model]] = stats([r for r in rows if r["strategy"] == model])
    lookup = {(r["seed"], r["case"], r["strategy"]): r for r in rows}
    for left, right in PAIRS:
        diffs, wins, losses = [], 0, 0
        for seed in SEED_DIRS:
            cases = sorted({r["case"] for r in rows if r["seed"] == seed
                            and r["strategy"] in (left, right)})
            for case in cases:
                a, b = lookup.get((seed, case, left)), lookup.get((seed, case, right))
                if not a or not b:
                    continue
                delta = (float(a["total_virtual_time_s"]) / int(a["source_count"])
                         - float(b["total_virtual_time_s"]) / int(b["source_count"]))
                diffs.append(delta)
                wins += delta > 1e-9
                losses += delta < -1e-9
        se = statistics.pstdev(diffs) / math.sqrt(len(diffs))
        payload["paired"][f"{SHORT[left]} vs {SHORT[right]}"] = {
            "n": len(diffs), "right_wins": wins, "left_wins": losses,
            "mean_delta_left_minus_right_s": statistics.mean(diffs),
            "ci95": [statistics.mean(diffs) - 1.96 * se,
                     statistics.mean(diffs) + 1.96 * se],
        }
    output = ROOT / "diagnostics/results/jplus_robustness_table.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, item in payload["pooled"].items():
        print(f"{name:>3} mean {item['mean_per_source_s']:7.2f} p95 {item['p95_per_source_s']:7.2f} "
              f"med {item['median_per_source_s']:7.2f} max {item['max_per_source_s']:7.2f} "
              f"var {item['var_per_source']:7.1f} move {item['mean_movement_s']:7.2f} "
              f"det {item['mean_detect_switch_s']:6.2f} clear {item['all_cleared_rate']:.3f} "
              f"fail {item['failed_clears']:.2f}")
    for name, item in payload["paired"].items():
        print(f"{name}: n={item['n']} right_wins={item['right_wins']} "
              f"mean_delta={item['mean_delta_left_minus_right_s']:+.2f} "
              f"ci95=[{item['ci95'][0]:.2f},{item['ci95'][1]:.2f}]")


if __name__ == "__main__":
    main()

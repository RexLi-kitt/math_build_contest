"""第二步续二：比较"原点发现数"与"原点可见比例"等门控特征的判别力。

只用 C+ 代理补跑一遍以取得原点频道号（用于德军坦克估计源总数），
B/C 的逐案例时间直接复用已有结果，保证配对一致。
"""
from __future__ import annotations

import json
import statistics
import sys
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402
from oracle_gap import auc  # noqa: E402

OUT = H.SANDBOX_OUT / "step2c"
STEP1 = H.SANDBOX_OUT / "step1_oracle"
STEP2 = H.SANDBOX_OUT / "step2_probe"

SCENARIOS = [
    ("normal", lambda: H.normal_cases(500, 20261021), 20261021,
     STEP1 / "normal_rows.json", "B", "C"),
    ("min_radius", lambda: H.min_radius_cases(200, 20261022), 20261022,
     STEP1 / "min_radius_rows.json", "B", "C"),
    ("boundary_random", lambda: H.boundary_cases(200, 20261023, False), 20261023,
     STEP1 / "boundary_random_rows.json", "B", "C"),
    ("boundary_outward", lambda: H.boundary_cases(200, 20261024, True), 20261024,
     STEP1 / "boundary_outward_rows.json", "B", "C"),
    ("mixed", lambda: H.mixed_cases(200, 20261025), 20261025,
     STEP2 / "mixed_rows.json", "BLog", "CLog"),
]

FEATURES = [("origin_discoveries", "le"), ("total_hat", "le"),
            ("visible_fraction", "le"), ("max_gap_deg", "ge")]


def load_reference(path, b_name, c_name):
    rows = json.loads(path.read_text(encoding="utf-8"))
    by_name = {}
    for row in rows:
        by_name.setdefault(row["strategy"], {})[row["case"]] = row
    result = {}
    for case, row in by_name[b_name].items():
        c = by_name[c_name][case]
        n = row["source_count"]
        result[case] = {"t_b": row["total_virtual_time_s"] / n,
                        "t_c": c["total_virtual_time_s"] / n}
    return result


def loss_of(t_b, t_c, oracle, picks):
    return statistics.mean((b if p else c) - o
                           for b, c, o, p in zip(t_b, t_c, oracle, picks))


def threshold_table(values, t_b, t_c, oracle, direction):
    grid = sorted(set(values))
    best = (float("inf"), None)
    table = []
    for threshold in grid:
        picks = [(v <= threshold) if direction == "le" else (v >= threshold)
                 for v in values]
        loss = loss_of(t_b, t_c, oracle, picks)
        table.append((threshold, loss))
        if loss < best[0]:
            best = (loss, threshold)
    return best, table


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    joined = {}
    for label, builder, seed, reference, b_name, c_name in SCENARIOS:
        cases = builder()
        rows = H.load_rows(OUT, label)
        if rows is None or len(rows) != len(cases):
            rows, _ = H.evaluate(label, cases, seed, ["CplusLog"], 12, OUT)
        ref = load_reference(reference, b_name, c_name)
        entries = []
        for row in rows:
            case = row["case"]
            if case not in ref:
                continue
            features = row["origin_features"] or {}
            entries.append({
                "case": case,
                "t_b": ref[case]["t_b"],
                "t_c": ref[case]["t_c"],
                "oracle": min(ref[case]["t_b"], ref[case]["t_c"]),
                "origin_discoveries": row["origin_discoveries"],
                "total_hat": features.get("total_hat", 16.0),
                "visible_fraction": features.get("visible_fraction", 0.0),
                "max_gap_deg": features.get("max_gap_deg", 360.0),
            })
        joined[label] = entries
        H.log(f"{label}: 配对 {len(entries)} 例")

    H.log("\n=== 特征判别力（AUC 预测应选 B，即 T_C 更差）===")
    H.log(f"{'场景':<18}{'n_origin':>10}{'total_hat':>11}"
          f"{'可见比例':>10}{'角隙':>9}")
    feature_names = ["origin_discoveries", "total_hat", "visible_fraction",
                     "max_gap_deg"]
    for label, entries in joined.items():
        label_b = [1 if e["t_c"] > e["t_b"] else 0 for e in entries]
        values = {name: [e[name] for e in entries] for name in feature_names}
        line = f"{label:<18}"
        for name in feature_names:
            score = auc([-v for v in values[name]], label_b)
            line += f"{score:>10.3f}"
        H.log(line)
        for name in ("origin_discoveries", "visible_fraction"):
            H.log(f"    范围 {name}: min={min(values[name]):.2f} "
                  f"max={max(values[name]):.2f} "
                  f"mean={statistics.mean(values[name]):.2f}")

    H.log("\n=== 单特征规则在各场景的损失（s/源，相对 oracle）===")
    for name, direction in FEATURES:
        H.log(f"--- 特征: {name} ({direction}) ---")
        H.log(f"{'场景':<18}{'最优阈值':>10}{'最优损失':>10}"
              f"{'现规则损失':>12}{'改善':>9}")
        per_scenario_best = []
        for label, entries in joined.items():
            t_b = [e["t_b"] for e in entries]
            t_c = [e["t_c"] for e in entries]
            oracle = [e["oracle"] for e in entries]
            values = [e[name] for e in entries]
            current = loss_of(t_b, t_c, oracle,
                              [e["origin_discoveries"] <= 0 for e in entries])
            best, _ = threshold_table(values, t_b, t_c, oracle, direction)
            per_scenario_best.append((label, best[0]))
            H.log(f"{label:<18}{best[1]:>10.2f}{best[0]:>10.2f}"
                  f"{current:>12.2f}{current - best[0]:>+9.2f}")
        H.log("     等权平均: 最优损失={:.2f}".format(
            statistics.mean(v for _, v in per_scenario_best)))

    H.log("\n=== 两特征规则：原点发现数 <= θ 或 可见比例 <= φ 时选 B ===")
    labels = list(joined)
    grids = {
        "origin_discoveries": sorted({e["origin_discoveries"]
                                      for entries in joined.values() for e in entries}),
        "visible_fraction": [0.0, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6],
    }
    best_rule = None
    for theta, phi in product(grids["origin_discoveries"], grids["visible_fraction"]):
        per_scenario = []
        for label, entries in joined.items():
            t_b = [e["t_b"] for e in entries]
            t_c = [e["t_c"] for e in entries]
            oracle = [e["oracle"] for e in entries]
            picks = [e["origin_discoveries"] <= theta or e["visible_fraction"] <= phi
                     for e in entries]
            per_scenario.append(loss_of(t_b, t_c, oracle, picks))
        average = statistics.mean(per_scenario)
        if best_rule is None or average < best_rule[0]:
            best_rule = (average, theta, phi, per_scenario)
    H.log(f"最优规则: θ={best_rule[1]}, φ={best_rule[2]}, "
          f"等权平均损失={best_rule[0]:.2f} s/源")
    H.log(f"各场景损失: "
          f"{dict(zip(labels, [round(v, 2) for v in best_rule[3]]))}")
    (OUT / "feature_report.json").write_text(json.dumps(
        {"joined_keys": labels,
         "best_two_feature_rule": {"theta": best_rule[1], "phi": best_rule[2],
                                   "mean_loss": best_rule[0],
                                   "per_scenario": best_rule[3]}},
        ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

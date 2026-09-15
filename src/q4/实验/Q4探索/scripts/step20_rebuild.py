"""第二十步：从 step19 的逐标签落盘结果重建鲁棒性报告，并补做 E/F 两层。

step19 崩在 F 段的数值断言上，但 A—D 四层的逐案例行都已落盘，
这里直接读回重建，不重跑；E 层改用"直接给源列表"的用例格式重试。
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "models"))
import harness as H  # noqa: E402
from cplus_3f_agent import point_segment_distance  # noqa: E402

SRC = H.SANDBOX_OUT / "step19_robustness"
OUT = H.SANDBOX_OUT / "step20_robustness"
sys.stdout.reconfigure(encoding="utf-8")


def load_rows():
    rows = []
    for path in sorted(SRC.glob("*_rows.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        label = path.name.replace("_rows.json", "")
        if isinstance(data, list):
            for row in data:
                row["label"] = label
            rows.extend(data)
    return rows


def index(rows):
    table = {}
    for row in rows:
        if row.get("total_virtual_time_s") is None:
            continue
        label = row.get("label") or row.get("scenario") or "?"
        table.setdefault(label, {}).setdefault(row["strategy"], {})[row["case"]] = row
    return table


def per_source(row):
    return row["total_virtual_time_s"] / row["source_count"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    data = index(rows)
    print(f"读回 {len(rows)} 行，场景标签 {len(data)} 个")
    if not data:
        print("未找到落盘结果，需重跑 step19")
        return
    payload = {"labels": sorted(data)}
    audit = {"pruned": 0, "hits": 0, "failed": 0, "runs": 0,
             "min_pruned": [], "max_kept": []}
    for label, arms in data.items():
        for arm, cases in arms.items():
            for row in cases.values():
                audit["runs"] += 1
                audit["pruned"] += row.get("pruned_observations") or 0
                audit["hits"] += row.get("pruned_truth_hits") or 0
                if row.get("min_pruned_dist") is not None:
                    audit["min_pruned"].append(row["min_pruned_dist"])
                if row.get("max_kept_dist") is not None:
                    audit["max_kept"].append(row["max_kept_dist"])
    audit["failed"] = sum(1 for label, arms in data.items() for arm, cases in arms.items()
                          for row in cases.values()
                          if row.get("total_virtual_time_s") is None)
    payload["audit"] = {
        "runs": audit["runs"], "pruned": audit["pruned"], "truth_hits": audit["hits"],
        "failed_runs": audit["failed"],
        "min_pruned_dist": min(audit["min_pruned"]) if audit["min_pruned"] else None,
        "max_kept_dist": max(audit["max_kept"]) if audit["max_kept"] else None,
    }

    # ---------- A/B/C/D 表 ----------
    print("\n=== A 常规回归 ===")
    print(f"{'标签':>22}{'B':>8}{'C':>8}{'BF':>8}{'CF':>8}{'D':>8}{'C3F':>8}{'清除':>8}")
    table_a = {}
    for label in sorted(key for key in data if key.startswith("A_")):
        arms = data[label]
        means = {arm: statistics.mean(per_source(row) for row in cases.values())
                 for arm, cases in arms.items()}
        clears = sum(1 for row in arms.get("D", {}).values()
                     if row.get("cleared_count") == row.get("source_count"))
        total = len(arms.get("D", {}))
        table_a[label] = {"mean": means, "all_clear": f"{clears}/{total}"}
        print(f"{label:>22}" + "".join(f"{means.get(k, float('nan')):>8.1f}"
                                      for k in ("B", "C", "BF", "CF", "D", "C3F"))
              + f"{clears:>5}/{total:<3}")

    print("\n=== B 混合加密（含 n0 分层） ===")
    print(f"{'标签':>10}{'B':>8}{'BF':>8}{'CF':>8}{'D':>8}{'eta':>7}{'R^F':>8}"
          f"{'R^F_p95':>9}{'R^F_max':>9}{'D选B':>7}")
    table_b, strata = {}, {}
    for label in sorted(key for key in data if key.startswith("B_")):
        arms = data[label]
        if not {"B", "C", "BF", "CF", "D"} <= set(arms):
            continue
        keys = sorted(arms["D"])
        t = {arm: {key: per_source(arms[arm][key]) for key in keys} for arm in arms}
        gap0 = statistics.mean(abs(t["B"][k] - t["C"][k]) for k in keys)
        gapf = statistics.mean(abs(t["BF"][k] - t["CF"][k]) for k in keys)
        regret = [t["D"][k] - min(t["BF"][k], t["CF"][k]) for k in keys]
        n0 = {k: arms["D"][k].get("origin_discoveries") for k in keys}
        item = {"eta": 1 - gapf / gap0, "gap0": gap0, "gapf": gapf,
                "regret_mean": statistics.mean(regret),
                "regret_p95": sorted(regret)[max(0, int(round(0.95 * (len(regret) - 1))))],
                "regret_max": max(regret),
                "pick_b": statistics.mean(1 if (n0[k] or 0) <= 0 else 0 for k in keys),
                "mean": {arm: statistics.mean(t[arm].values()) for arm in arms},
                "oracle_better": statistics.mean(
                    1 if t["BF"][k] < t["CF"][k] else 0 for k in keys)}
        table_b[label] = item
        for key in keys:
            bucket = ("n0=0" if (n0[key] or 0) == 0 else
                      "n0=1" if n0[key] == 1 else "n0>=2")
            strata.setdefault(bucket, {"bf_cf": [], "regret": [], "pick_b": [],
                                       "n": 0, "oracle_b": 0})
            entry = strata[bucket]
            entry["n"] += 1
            entry["bf_cf"].append(t["BF"][key] - t["CF"][key])
            entry["regret"].append(t["D"][key] - min(t["BF"][key], t["CF"][key]))
            entry["pick_b"].append(1 if (n0[key] or 0) <= 0 else 0)
            entry["oracle_b"] += 1 if t["BF"][key] < t["CF"][key] else 0
        print(f"{label:>10}" + "".join(f"{item['mean'][k]:>8.1f}"
                                       for k in ("B", "BF", "CF", "D"))
              + f"{item['eta']:>7.2f}{item['regret_mean']:>8.2f}"
              f"{item['regret_p95']:>9.2f}{item['regret_max']:>9.2f}"
              f"{item['pick_b']:>7.1%}")
    payload["B"], payload["B_strata"] = table_b, strata
    print("\n分层汇总：")
    for bucket in sorted(strata):
        entry = strata[bucket]
        print(f"  {bucket:>7} n={entry['n']:>4}  BF−CF={statistics.mean(entry['bf_cf']):>+7.1f}  "
              f"R^F均值={statistics.mean(entry['regret']):>6.2f}  "
              f"R^F_P95={sorted(entry['regret'])[max(0, int(round(0.95*(len(entry['regret'])-1))))]:>6.2f}  "
              f"R^F_max={max(entry['regret']):>7.2f}  D选B={statistics.mean(entry['pick_b']):>5.1%}  "
              f"实际最优为B={entry['oracle_b']/entry['n']:>5.1%}")

    print("\n=== C 空间对抗 / D 半平面 ===")
    table_cd = {}
    for label in sorted(key for key in data if key[0] in "CD"):
        arms = data[label]
        keys = sorted(next(iter(arms.values())))
        t = {arm: {key: per_source(arms[arm][key]) for key in keys if key in arms[arm]}
             for arm in arms}
        means = {arm: statistics.mean(values.values()) for arm, values in t.items()}
        regret = ([t["D"][k] - min(t["BF"][k], t["CF"][k])
                   for k in keys if "D" in t and "BF" in t and "CF" in t and k in t["D"]]
                  if {"D", "BF", "CF"} <= set(t) else [])
        clears = sum(1 for row in arms.get("D", {}).values()
                     if row.get("cleared_count") == row.get("source_count"))
        table_cd[label] = {"mean": means, "all_clear": f"{clears}/{len(arms.get('D', {}))}",
                           "regret_mean": statistics.mean(regret) if regret else None,
                           "regret_max": max(regret) if regret else None}
        print(f"{label:>10}" + "".join(f"{means.get(k, float('nan')):>8.1f}"
                                       for k in ("BF", "CF", "D"))
              + (f"{statistics.mean(regret):>9.2f}{max(regret):>9.2f}" if regret else " " * 18)
              + f"{clears:>5}/{len(arms.get('D', {})):<3}")
    payload["CD"] = table_cd

    # ---------- F 数值断言 ----------
    print("\n=== F 距离门数值断言 ===")
    origin = (0.0, 0.0)
    numeric = {}
    for target in (1499.0, 1499.9, 1500.0, 1500.1, 1501.0):
        polygon = [(target, -1000.0), (target + 2000.0, -1000.0),
                   (target + 2000.0, 1000.0), (target, 1000.0)]
        distance = min(point_segment_distance(origin, polygon[i], polygon[(i + 1) % 4])
                       for i in range(4))
        numeric[f"{target}"] = {"measured": round(distance, 6), "kept": distance <= 1500.0}
    print(json.dumps(numeric, ensure_ascii=False))
    payload["F_numeric"] = numeric

    # ---------- E 示向误差（改用源列表格式） ----------
    print("\n=== E 示向误差（默认均匀 ±1° 模型） ===")
    H._STRATEGIES.update({"C3F": __import__("cplus_3f_agent").CPlus3FLiteAgent})
    try:
        seed = 20271001
        rng = random.Random(seed)
        cases = [H.random_mixed_sources(rng, 16, 0.6) for _ in range(40)]
        case_rows, summaries = H.evaluate("E_default", cases, seed, ["D", "C3F"],
                                          12, OUT)
        by = {item["strategy"]: item for item in summaries}
        keys = sorted({row["case"] for row in case_rows if row["strategy"] == "D"})
        diff = []
        for key in keys:
            values = {row["strategy"]: per_source(row) for row in case_rows
                      if row["case"] == key}
            if {"D", "C3F"} <= set(values):
                diff.append(values["D"] - values["C3F"])
        mean = statistics.mean(diff)
        half = 1.96 * statistics.stdev(diff) / math.sqrt(len(diff))
        payload["E"] = {"mean": {arm: by[arm]["mean_s_per_source"] for arm in ("D", "C3F")},
                        "paired": {"mean": mean, "ci": [mean - half, mean + half]},
                        "all_clear": by["D"]["all_clear"], "cases": by["D"]["cases"],
                        "modes_supported": ["uniform_pm1 (默认)"]}
        print(f"  D={payload['E']['mean']['D']:.1f}  C3F={payload['E']['mean']['C3F']:.1f}  "
              f"配对差={mean:+.2f} [{mean-half:+.2f},{mean+half:+.2f}]  "
              f"清除={payload['E']['all_clear']}/{payload['E']['cases']}")
    except Exception as error:  # noqa: BLE001
        payload["E"] = {"unsupported": f"{type(error).__name__}: {error}"}
        print(f"  E 段离线未支持：{type(error).__name__}: {error}")

    payload["A"] = table_a
    (OUT / "robustness_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n审计：运行 {payload['audit']['runs']} 例、剪枝 {payload['audit']['pruned']} 次、"
          f"真值命中 {payload['audit']['truth_hits']}、失败 {payload['audit']['failed_runs']}")
    print(f"剪枝下界 {payload['audit']['min_pruned_dist']} m（应 > 1500）；"
          f"保留上界 {payload['audit']['max_kept_dist']} m（应 <= 1500）")
    print(f"\n报告：{OUT / 'robustness_report.json'}")


if __name__ == "__main__":
    main()

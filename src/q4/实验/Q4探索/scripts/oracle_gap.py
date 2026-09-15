"""第一步：B/C 理想选择器（oracle）上限分析。

oracle = 事后知道结果、总能在 B 与 C 中挑更快的那个。
把 C+ 与 oracle 的差距拆成两部分：
  (1) 分类空间：用更强的原点特征能把差距追回多少；
  (2) 剩余空间：即使分类完美也追不回的部分，只能靠几何/定位改进。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402

NAMES = ["CplusLog", "B", "C"]
OUT = H.SANDBOX_OUT / "step1_oracle"

SCENARIOS = [
    ("normal", lambda: H.normal_cases(500, 20261021), 20261021),
    ("min_radius", lambda: H.min_radius_cases(200, 20261022), 20261022),
    ("boundary_random", lambda: H.boundary_cases(200, 20261023, False), 20261023),
    ("boundary_outward", lambda: H.boundary_cases(200, 20261024, True), 20261024),
    ("mixed", lambda: H.mixed_cases(200, 20261025), 20261025),
]


def auc(scores: list[float], labels: list[int]) -> float:
    """正类（oracle 选 B）的 AUC；分数越大越倾向正类。"""
    pairs = sorted(zip(scores, labels))
    ranks = [0.0] * len(pairs)
    index = 0
    while index < len(pairs):
        end = index
        while end + 1 < len(pairs) and pairs[end + 1][0] == pairs[index][0]:
            end += 1
        average = (index + end) / 2.0 + 1.0
        for position in range(index, end + 1):
            ranks[position] = average
        index = end + 1
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return float("nan")
    rank_sum = sum(rank for rank, (_, label) in zip(ranks, pairs) if label == 1)
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def rule_loss(t_b: list[float], t_c: list[float], oracle: list[float],
              picks_b: list[bool]) -> float:
    """给定逐案例选择，返回平均每源损失（相对 oracle）。"""
    total = 0.0
    for b, c, best, pick_b in zip(t_b, t_c, oracle, picks_b):
        total += (b if pick_b else c) - best
    return total / len(oracle)


def best_threshold(feature: list[float], t_b, t_c, oracle, direction: str):
    """在观测值上穷举单特征阈值，返回 (最优损失, 阈值)。"""
    values = sorted(set(feature))
    grid = [min(values) - 1e-6] + [value + 1e-6 for value in values]
    best = (float("inf"), None)
    for threshold in grid:
        if direction == "le":
            picks = [value <= threshold for value in feature]
        else:
            picks = [value >= threshold for value in feature]
        loss = rule_loss(t_b, t_c, oracle, picks)
        if loss < best[0]:
            best = (loss, threshold)
    return best


def evaluate(label, rows, names):
    t = {}
    for name in names:
        block = [row for row in rows if row["strategy"] == name]
        t[name] = {row["case"]: row["total_virtual_time_s"] / row["source_count"]
                   for row in block}
    ordered = sorted(t["B"])
    t_b = [t["B"][case] for case in ordered]
    t_c = [t["C"][case] for case in ordered]
    oracle = [min(b, c) for b, c in zip(t_b, t_c)]
    cplus = [t["CplusLog"][case] for case in ordered]

    origin = {row["case"]: row for row in rows if row["strategy"] == "CplusLog"}
    ndisc = [origin[case]["origin_discoveries"] for case in ordered]
    max_gap = [origin[case]["origin_features"]["max_gap_deg"] for case in ordered]
    probe_new = []
    for case in ordered:
        series = origin[case]["search_trace"] or [(None, 0.0, origin[case]["origin_discoveries"])]
        probe_new.append(series[0][2] - origin[case]["origin_discoveries"])

    mean = {name: statistics.mean(t[name].values()) for name in t}
    mean["oracle"] = statistics.mean(oracle)
    mean["CplusLog"] = statistics.mean(cplus)
    oracle_win_b = [1 if b < c else 0 for b, c in zip(t_b, t_c)]
    picks_b_gate = [value == 0 for value in ndisc]

    loss_gate = rule_loss(t_b, t_c, oracle, picks_b_gate)
    loss_ndisc = best_threshold(ndisc, t_b, t_c, oracle, "le")
    loss_gap = best_threshold(max_gap, t_b, t_c, oracle, "ge")
    loss_probe = best_threshold(probe_new, t_b, t_c, oracle, "le")

    grid_loss, grid_rule = float("inf"), None
    for nb, gap in product(sorted(set(ndisc)),
                           [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]):
        picks = [n <= nb or g >= gap for n, g in zip(ndisc, max_gap)]
        loss = rule_loss(t_b, t_c, oracle, picks)
        if loss < grid_loss:
            grid_loss, grid_rule = loss, (nb, gap)

    hit = sum(1 for a, b in zip(picks_b_gate, oracle_win_b) if int(a) == b)
    report = {
        "label": label,
        "cases": len(ordered),
        "mean_s_per_source": mean,
        "gap_s_per_source": statistics.mean(cplus) - mean["oracle"],
        "gap_percent": (statistics.mean(cplus) - mean["oracle"]) / mean["oracle"] * 100.0,
        "gain_b_over_c_percent": (mean["B"] - mean["C"]) / mean["C"] * 100.0,
        "oracle_picks_B": sum(oracle_win_b),
        "oracle_picks_B_share": sum(oracle_win_b) / len(ordered),
        "gate_accuracy": hit / len(ordered),
        "loss_gate_s": loss_gate,
        "loss_best_ndisc_s": loss_ndisc[0],
        "loss_best_ndisc_threshold": loss_ndisc[1],
        "loss_best_max_gap_s": loss_gap[0],
        "loss_best_max_gap_threshold": loss_gap[1],
        "loss_best_probe_new_s": loss_probe[0],
        "loss_best_probe_new_threshold": loss_probe[1],
        "loss_best_two_feature_s": grid_loss,
        "loss_best_two_feature_rule": grid_rule,
        "auc_ndisc": auc([-v for v in ndisc], oracle_win_b),
        "auc_max_gap": auc(max_gap, oracle_win_b),
        "auc_probe_new": auc([-v for v in probe_new], oracle_win_b),
    }
    report["classification_space_s"] = loss_gate - report["loss_best_two_feature_s"]
    report["irreducible_space_s"] = report["loss_best_two_feature_s"]
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=16)
    parser.add_argument("--only", default="", help="逗号分隔的场景名")
    args = parser.parse_args()
    wanted = {name.strip() for name in args.only.split(",") if name.strip()}
    OUT.mkdir(parents=True, exist_ok=True)
    reports = []
    for label, builder, seed in SCENARIOS:
        if wanted and label not in wanted:
            continue
        cases = builder()
        rows = H.load_rows(OUT, label)
        if rows is None or len(rows) != len(cases) * len(NAMES):
            rows, _ = H.evaluate(label, cases, seed, NAMES, args.jobs, OUT)
        else:
            H.log(f"{label}: 复用已有 {len(rows)} 行结果")
        report = evaluate(label, rows, NAMES)
        reports.append(report)
        H.log(f"\n=== {label} （{report['cases']} 例） ===")
        H.log(f"B={report['mean_s_per_source']['B']:.2f}  "
              f"C={report['mean_s_per_source']['C']:.2f}  "
              f"C+={report['mean_s_per_source']['CplusLog']:.2f}  "
              f"oracle={report['mean_s_per_source']['oracle']:.2f} s/源")
        H.log(f"C+ 与 oracle 差距: {report['gap_s_per_source']:+.2f} s/源 "
              f"({report['gap_percent']:.3f}%)")
        H.log(f"oracle 选 B 的案例占比: {report['oracle_picks_B_share']:.1%}；"
              f"当前门控命中率: {report['gate_accuracy']:.1%}")
        H.log(f"损失分解(相对 oracle，s/源): 当前门控={report['loss_gate_s']:.2f} | "
              f"最优发现数阈值={report['loss_best_ndisc_s']:.2f} | "
              f"最优角隙阈值={report['loss_best_max_gap_s']:.2f} | "
              f"最优两特征={report['loss_best_two_feature_s']:.2f}")
        H.log(f"→ 分类空间={report['classification_space_s']:.2f} s/源，"
              f"不可约空间={report['irreducible_space_s']:.2f} s/源")
        H.log(f"AUC: 原点发现数={report['auc_ndisc']:.3f} "
              f"角隙={report['auc_max_gap']:.3f} "
              f"首站新增={report['auc_probe_new']:.3f}")
    (OUT / "oracle_report.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    H.log(f"\n报告已写入 {OUT / 'oracle_report.json'}")


if __name__ == "__main__":
    main()

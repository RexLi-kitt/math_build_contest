"""第二步：探测信息量分析。

两阶段方案的前提是"走过对方/自己路线的前若干个站之后，能看出该走哪条路线"。
先看信号是否真的有预测力，再决定要不要实现混合代理。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402
from oracle_gap import auc  # noqa: E402

OUT = H.SANDBOX_OUT / "step2_probe"
NAMES = ["BLog", "CLog", "CplusLog"]

SCENARIOS = [
    ("boundary_random", lambda: H.boundary_cases(200, 20261023, False), 20261023),
    ("mixed", lambda: H.mixed_cases(200, 20261025), 20261025),
    ("boundary_outward", lambda: H.boundary_cases(200, 20261024, True), 20261024),
]


def probe_series(row, max_index=8):
    """返回 [(累计发现数, 累计耗时, 本站新增, 观测次数)]，下标 0 为原点。"""
    trace = row.get("obs_trace") or []
    series = []
    for entry in trace[:max_index]:
        series.append((entry[2], entry[1], entry[4], entry[3]))
    return series


def analyse(label, rows):
    by_name = {name: {row["case"]: row for row in rows if row["strategy"] == name}
               for name in NAMES}
    cases = sorted(by_name["BLog"])
    time = {name: {case: by_name[name][case]["total_virtual_time_s"]
                   / by_name[name][case]["source_count"] for case in cases}
            for name in NAMES}
    per_case = {name: {case: by_name[name][case]["total_virtual_time_s"]
                       for case in cases} for name in NAMES}

    t_b = [time["BLog"][case] for case in cases]
    t_c = [time["CLog"][case] for case in cases]
    t_gate = [time["CplusLog"][case] for case in cases]
    oracle = [min(b, c) for b, c in zip(t_b, t_c)]
    switch_label = [1 if c > b else 0 for b, c in zip(t_b, t_c)]

    # C+ 在该场景实际选了哪条路线
    picks = [by_name["CplusLog"][case]["selected_route"] for case in cases]

    series_c = {case: probe_series(by_name["CLog"][case]) for case in cases}
    series_b = {case: probe_series(by_name["BLog"][case]) for case in cases}
    origin_disc = {case: (series_c[case][0][0] if series_c[case] else 0)
                   for case in cases}

    report = {
        "label": label,
        "cases": len(cases),
        "mean_s_per_source": {
            "B": statistics.mean(t_b), "C": statistics.mean(t_c),
            "Cplus": statistics.mean(t_gate), "oracle": statistics.mean(oracle)},
        "gate_choice_share": {
            "B": sum(pick == "B" for pick in picks) / len(picks),
            "C": sum(pick == "C" for pick in picks) / len(picks)},
        "switch_share": sum(switch_label) / len(switch_label),
        "mean_abs_b_minus_c_s": statistics.mean(
            abs(b - c) for b, c in zip(t_b, t_c)),
        "phase_gap_s_per_source": {},
        "probe": {},
    }
    for key in ("search_movement_time_s", "post_search_movement_time_s",
                "detection_time_s"):
        gap = statistics.mean(
            (by_name["CLog"][case][key] - by_name["BLog"][case][key])
            / by_name["CLog"][case]["source_count"] for case in cases)
        report["phase_gap_s_per_source"][key] = gap

    for index in range(1, 7):
        for route, series in (("C", series_c), ("B", series_b)):
            cumulative, per_station, elapsed = [], [], []
            for case in cases:
                entries = series[case]
                if len(entries) > index:
                    cumulative.append(entries[index][0] - origin_disc[case])
                    per_station.append(entries[index][2])
                    elapsed.append(entries[index][1])
                else:
                    cumulative.append(0)
                    per_station.append(0)
                    elapsed.append(float("nan"))
            key = f"{route}#{index}"
            report["probe"][key] = {
                "mean_cumulative_new": statistics.mean(cumulative),
                "mean_per_station_new": statistics.mean(per_station),
                "auc_cumulative": auc([-v for v in cumulative], switch_label),
                "auc_per_station": auc([-v for v in per_station], switch_label),
                "mean_elapsed_s": statistics.mean(
                    value for value in elapsed if value == value) if any(
                    value == value for value in elapsed) else float("nan"),
            }
    return report, (t_b, t_c, oracle, series_c, series_b, origin_disc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    wanted = {name.strip() for name in args.only.split(",") if name.strip()}
    OUT.mkdir(parents=True, exist_ok=True)
    reports = []
    detail = {}
    for label, builder, seed in SCENARIOS:
        if wanted and label not in wanted:
            continue
        cases = builder()
        rows = H.load_rows(OUT, label)
        if rows is None or len(rows) != len(cases) * len(NAMES):
            rows, _ = H.evaluate(label, cases, seed, NAMES, args.jobs, OUT)
        else:
            H.log(f"{label}: 复用已有 {len(rows)} 行结果")
        report, payload = analyse(label, rows)
        reports.append(report)
        detail[label] = payload
        means = report["mean_s_per_source"]
        H.log(f"\n=== {label}（{report['cases']} 例）===")
        H.log(f"B={means['B']:.2f} C={means['C']:.2f} C+={means['Cplus']:.2f} "
              f"oracle={means['oracle']:.2f} s/源；"
              f"C+ 选 B 占比={report['gate_choice_share']['B']:.1%}；"
              f"oracle 应换路线占比={report['switch_share']:.1%}")
        H.log(f"|T_B-T_C| 均值（每例总时间）= {report['mean_abs_b_minus_c_s']:.1f} s")
        for key, value in report["phase_gap_s_per_source"].items():
            H.log(f"C-B 差 {key}: {value:+.2f} s/源")
        H.log("探测信号 AUC（预测应当换到 B 的案例）:")
        for key, value in report["probe"].items():
            H.log(f"  {key}: 累计新增={value['mean_cumulative_new']:.2f} "
                  f"本站新增={value['mean_per_station_new']:.2f} "
                  f"AUC累计={value['auc_cumulative']:.3f} "
                  f"AUC本站={value['auc_per_station']:.3f} "
                  f"耗时={value['mean_elapsed_s']:.0f}s")
    (OUT / "probe_report.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    H.log(f"\n报告已写入 {OUT / 'probe_report.json'}")


if __name__ == "__main__":
    main()

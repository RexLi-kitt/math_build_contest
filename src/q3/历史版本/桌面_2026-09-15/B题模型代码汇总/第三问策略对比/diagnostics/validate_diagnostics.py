"""Independent consistency checks for the third-question diagnostic report."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FACT = ROOT / "diagnostics" / "results" / "diagnostic_factorial_seed982451653_100"
ROBUST = ROOT / "results" / "robustness" / "robustness_summary.json"
REPORT = ROOT / "diagnostics" / "第三问模型证据报告.md"
C_METRICS = ROOT / "diagnostics" / "results" / "c_to_cplus_metrics_600" / "case_results.csv"
C_REPORT = ROOT / "diagnostics" / "C到C加机制回测报告.md"
F_METRICS = ROOT / "diagnostics" / "results" / "cplus_to_f_metrics_600" / "case_results.csv"
F_REPORT = ROOT / "diagnostics" / "C加到F机制回测报告.md"
D_METRICS = ROOT / "diagnostics" / "results" / "cplus_to_d_metrics_600" / "case_results.csv"
D_REPORT = ROOT / "diagnostics" / "C加到D失败分支机制报告.md"
G_METRICS = ROOT / "diagnostics" / "results" / "f_to_g_metrics_600" / "case_results.csv"
G_REPORT = ROOT / "diagnostics" / "F到G机制回测报告.md"
I_METRICS = ROOT / "diagnostics" / "results" / "g_to_i_metrics_600" / "case_results.csv"
I_REPORT = ROOT / "diagnostics" / "G到I机制回测报告.md"


def main():
    with (FACT / "case_results.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    groups = defaultdict(list)
    for row in rows:
        groups[row["group"]].append(row)
    assert len(groups) == 14, f"expected 14 groups, got {len(groups)}"
    assert all(len(items) == 100 for items in groups.values())
    assert all(int(row["cleared"]) == int(row["source_count"]) for row in groups["I_normal"])
    for case in range(1, 101):
        sample = {row["group"]: row for row in rows if int(row["case"]) == case}
        assert float(sample["truth_disk_lower_bound"]["total_time_s"]) <= float(sample["truth_direct_centres"]["total_time_s"]) + 1e-8
        assert float(sample["truth_direct_centres"]["total_time_s"]) <= float(sample["I_normal"]["total_time_s"]) + 1e-8
    robust = json.loads(ROBUST.read_text(encoding="utf-8"))["cross_seed"]
    ranking = sorted(robust, key=lambda name: robust[name]["mean"])
    assert ranking == ["I_ring_optimized", "G_rolling_coverage", "F_coverage_integrated", "Cplus_completion_coobserve", "C_region_q2"]
    report = REPORT.read_text(encoding="utf-8")
    for section in ("模型改动对照表", "真值辅助诊断", "逐项假设证据表"):
        assert section in report
    with C_METRICS.open(encoding="utf-8-sig", newline="") as handle:
        metric_rows = list(csv.DictReader(handle))
    assert len(metric_rows) == 1200
    metric_cases = defaultdict(dict)
    for row in metric_rows:
        metric_cases[(row["seed"], row["case"])][row["model"]] = row
        assert float(row["decomposition_error_s"]) < 0.0011
    assert len(metric_cases) == 600
    for models in metric_cases.values():
        assert float(models["C+"]["total_time_per_source_s"]) < float(models["C"]["total_time_per_source_s"])
        for field in ("last_discovery_time_per_source_s", "search_end_time_per_source_s",
                      "unfinished_after_search_rate", "not_clear_ready_after_search_rate"):
            assert abs(float(models["C"][field]) - float(models["C+"][field])) < 1e-9
    c_report = C_REPORT.read_text(encoding="utf-8")
    for section in ("评价指标及解释方向", "C 的主要不足", "单模块消融"):
        assert section in c_report
    with F_METRICS.open(encoding="utf-8-sig", newline="") as handle:
        f_rows = list(csv.DictReader(handle))
    assert len(f_rows) == 3000
    f_cases = defaultdict(dict)
    expected_models = {
        "C+", "F_fixed_no_insert", "F_dynamic_no_insert", "F_fixed_insert", "F"
    }
    for row in f_rows:
        f_cases[(row["seed"], row["case"])][row["model"]] = row
        assert float(row["decomposition_error_s"]) < 0.0011
        assert int(row["all_cleared"]) == 1
    assert len(f_cases) == 600
    assert all(set(models) == expected_models for models in f_cases.values())
    cp_mean = sum(float(models["C+"]["total_time_per_source_s"])
                  for models in f_cases.values()) / len(f_cases)
    f_mean = sum(float(models["F"]["total_time_per_source_s"])
                 for models in f_cases.values()) / len(f_cases)
    assert f_mean < cp_mean
    assert all(float(models["F_fixed_no_insert"]["coverage_insertions_per_source"]) == 0
               and float(models["F_dynamic_no_insert"]["coverage_insertions_per_source"]) == 0
               for models in f_cases.values())
    f_report = F_REPORT.read_text(encoding="utf-8")
    for section in ("为什么会从 C+ 继续设计 F", "这么做的合理性", "七项指标",
                    "模型改动、指标路径与证据状态", "2×2 消融",
                    "为什么保留 F", "版本建议"):
        assert section in f_report
    with D_METRICS.open(encoding="utf-8-sig", newline="") as handle:
        d_rows = list(csv.DictReader(handle))
    assert len(d_rows) == 2400
    d_cases = defaultdict(dict)
    d_models = {"C+", "Cplus_rolling", "D_belief_batch", "D"}
    search_fields = ("last_discovery_time_per_source_s", "search_end_time_per_source_s",
                     "unfinished_after_search_rate", "not_clear_ready_after_search_rate")
    for row in d_rows:
        d_cases[(row["seed"], row["case"])][row["model"]] = row
        assert float(row["decomposition_error_s"]) < 0.0011
        assert int(row["all_cleared"]) == 1
    assert len(d_cases) == 600
    for models in d_cases.values():
        assert set(models) == d_models
        for field in search_fields:
            reference = float(models["C+"][field])
            assert all(abs(float(models[name][field]) - reference) < 1e-9 for name in d_models)
    d_means = {
        name: sum(float(models[name]["total_time_per_source_s"])
                  for models in d_cases.values()) / len(d_cases)
        for name in d_models
    }
    assert d_means["Cplus_rolling"] < d_means["D"] < d_means["C+"] < d_means["D_belief_batch"]
    d_report = D_REPORT.read_text(encoding="utf-8")
    for section in ("为什么当时会做 D", "这么做的合理性", "2×2 消融",
                    "逐项假设证据表", "为什么最终放弃 D"):
        assert section in d_report
    with G_METRICS.open(encoding="utf-8-sig", newline="") as handle:
        g_rows = list(csv.DictReader(handle))
    assert len(g_rows) == 2400
    g_cases = defaultdict(dict)
    g_models = {"F", "G", "F_marginal_insert", "G_marginal_insert"}
    for row in g_rows:
        g_cases[(row["seed"], row["case"])][row["model"]] = row
        assert float(row["decomposition_error_s"]) < 0.0011
        assert int(row["all_cleared"]) == 1
    assert len(g_cases) == 600
    for models in g_cases.values():
        assert set(models) == g_models
        for left, right in (("F", "G"), ("F_marginal_insert", "G_marginal_insert")):
            for field in search_fields:
                assert abs(float(models[left][field]) - float(models[right][field])) < 1e-9
    g_means = {
        name: sum(float(models[name]["total_time_per_source_s"])
                  for models in g_cases.values()) / len(g_cases)
        for name in g_models
    }
    assert g_means["G"] < g_means["F"]
    assert g_means["G_marginal_insert"] < g_means["F_marginal_insert"]
    assert g_means["F"] < g_means["F_marginal_insert"]
    assert g_means["G"] < g_means["G_marginal_insert"]
    g_report = G_REPORT.read_text(encoding="utf-8")
    for section in ("为什么会从 F 继续设计 G", "这么做的合理性", "七项指标",
                    "逐项证据表", "2×2 消融", "抢占与重访诊断",
                    "为什么保留 G"):
        assert section in g_report
    with I_METRICS.open(encoding="utf-8-sig", newline="") as handle:
        i_rows = list(csv.DictReader(handle))
    assert len(i_rows) == 2400
    i_cases = defaultdict(dict)
    i_models = {"G", "G_rotated", "I", "I_rotated"}
    for row in i_rows:
        i_cases[(row["seed"], row["case"])][row["model"]] = row
        assert float(row["decomposition_error_s"]) < 0.0011
        assert int(row["all_cleared"]) == 1
    assert len(i_cases) == 600
    assert all(set(models) == i_models for models in i_cases.values())
    i_means = {
        name: sum(float(models[name]["total_time_per_source_s"])
                  for models in i_cases.values()) / len(i_cases)
        for name in i_models
    }
    assert i_means["I"] < i_means["G"]
    assert i_means["I_rotated"] < i_means["G_rotated"]
    assert i_means["G"] < i_means["G_rotated"]
    assert i_means["I"] < i_means["I_rotated"]
    import math
    worst_distance = math.sqrt(1800.0**2 + 1150.0**2
                               - 2*1800.0*1150.0*math.cos(math.pi/6))
    assert worst_distance < 1000.0
    i_report = I_REPORT.read_text(encoding="utf-8")
    for section in ("为什么会从 G 继续设计 I", "为什么1150 m仍能保证覆盖",
                    "七项指标", "逐项证据表", "2×2消融",
                    "为什么保留 I"):
        assert section in i_report
    print("Validation passed: all main-chain and D-branch paired mechanism experiments are internally consistent.")


if __name__ == "__main__":
    main()

"""延迟门控的可分性：用"走过 C 的前 k 个测站后的新增发现数"区分两类零发现场景。

边界随机（门控不该切 B）与边界朝外（门控必须切 B）在原点都是零发现，
但内圈测站能否发现源不同。这里直接用已有轨迹数据算 AUC 与最优阈值。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402
from oracle_gap import auc  # noqa: E402

STEP2 = H.SANDBOX_OUT / "step2_probe"


def load(label):
    rows = json.loads((STEP2 / f"{label}_rows.json").read_text(encoding="utf-8"))
    result = {}
    for row in rows:
        if row["strategy"] != "CLog":
            continue
        trace = row["obs_trace"] or []
        origin = trace[0][2] if trace else 0
        series = []
        for entry in trace:
            series.append(entry[2] - origin)
        result[row["case"]] = series
    return result


def main() -> None:
    random_cases = load("boundary_random")
    outward_cases = load("boundary_outward")
    H.log("标签：1 = 边界朝外（应当走 B），0 = 边界随机（应当走 C）")
    H.log(f"{'k':>3}{'随机均值':>10}{'朝外均值':>10}{'AUC':>8}"
          f"{'最优阈值':>10}{'准确率':>9}{'误判(该B判C)':>14}{'误判(该C判B)':>14}")
    for k in range(1, 8):
        random_values = [series[k] if len(series) > k else 0
                         for series in random_cases.values()]
        outward_values = [series[k] if len(series) > k else 0
                          for series in outward_cases.values()]
        scores = [-value for value in random_values + outward_values]
        labels = [0] * len(random_values) + [1] * len(outward_values)
        score = auc(scores, labels)
        best = (0.0, None)
        grid = sorted(set(random_values + outward_values))
        for threshold in [value - 0.5 for value in grid] + [max(grid) + 0.5]:
            correct = sum(1 for value in outward_values if value <= threshold)
            correct += sum(1 for value in random_values if value > threshold)
            accuracy = correct / (len(random_values) + len(outward_values))
            if accuracy > best[0]:
                best = (accuracy, threshold)
        missed_outward = sum(1 for value in outward_values if value > best[1])
        missed_random = sum(1 for value in random_values if value <= best[1])
        H.log(f"{k:>3}{statistics.mean(random_values):>10.2f}"
              f"{statistics.mean(outward_values):>10.2f}{score:>8.3f}"
              f"{best[1]:>10.1f}{best[0]:>9.1%}"
              f"{missed_outward:>9}/{len(outward_values):<4}"
              f"{missed_random:>9}/{len(random_values):<4}")


if __name__ == "__main__":
    main()

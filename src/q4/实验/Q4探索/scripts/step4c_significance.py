"""配对显著性检验：CAz3（搜索期 3 条方位）与 C（2 条方位）逐案例对比。"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402

STEP4 = H.SANDBOX_OUT / "step4_azimuth"
LABELS = ["normal", "min_radius", "boundary_random", "boundary_outward", "mixed"]


def load(label, strategy):
    rows = json.loads((STEP4 / f"{label}_rows.json").read_text(encoding="utf-8"))
    return {row["case"]: row["total_virtual_time_s"] / row["source_count"]
            for row in rows if row["strategy"] == strategy}


def main() -> None:
    H.log(f"{'场景':<18}{'C':>9}{'CAz3':>9}{'配对差':>10}{'95%CI下':>10}"
          f"{'95%CI上':>10}{'胜率':>8}{'显著':>7}")
    for label in LABELS:
        path = STEP4 / f"{label}_rows.json"
        if not path.exists():
            continue
        c = load(label, "C")
        a = load(label, "CAz3")
        cases = sorted(set(c) & set(a))
        diff = [a[case] - c[case] for case in cases]
        mean = statistics.mean(diff)
        half = 1.96 * statistics.stdev(diff) / math.sqrt(len(diff))
        win = sum(1 for value in diff if value < 0) / len(diff)
        significant = "是" if (mean - half) * (mean + half) > 0 else "否"
        H.log(f"{label:<18}{statistics.mean(c[case] for case in cases):>9.2f}"
              f"{statistics.mean(a[case] for case in cases):>9.2f}"
              f"{mean:>+10.2f}{mean - half:>+10.2f}{mean + half:>+10.2f}"
              f"{win:>8.1%}{significant:>7}")


if __name__ == "__main__":
    main()

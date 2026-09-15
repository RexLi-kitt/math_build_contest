"""冒烟测试：确认 OriginLogAgent 与出货 C+ 逐条同值，并校准单案例耗时。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402

SEED = 20261021
CASES = 20


def main() -> None:
    started = time.perf_counter()
    rows, _ = H.evaluate(
        "smoke20", H.normal_cases(CASES, SEED), SEED,
        ["Cplus", "CplusLog", "B", "C"], 8, H.WORK / "results", dump_rows=False)
    elapsed = time.perf_counter() - started

    def per_source(name):
        return {row["case"]: row["total_virtual_time_s"] / row["source_count"]
                for row in rows if row["strategy"] == name}

    ref, log = per_source("Cplus"), per_source("CplusLog")
    worst = max(abs(ref[case] - log[case]) for case in ref)
    print(f"[identity] max |Cplus - CplusLog| = {worst:.6f} s/源 "
          f"({'一致' if worst < 1e-9 else '不一致，需要检查'})")

    for name in ("Cplus", "B", "C"):
        values = per_source(name)
        print(f"[参考] {name:>7}: mean={sum(values.values()) / len(values):.2f} s/源")
    print(f"[耗时] {len(rows)} 次运行共 {elapsed:.1f}s")


if __name__ == "__main__":
    main()

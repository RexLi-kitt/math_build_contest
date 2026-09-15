"""Cref 第二种子确认: 正常500(seed 20260925) C vs Cref。"""
from __future__ import annotations

import json
import random
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

EXP = r"C:\Users\李\Desktop\第四问定向源实验"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, EXP)
sys.path.insert(0, str(HERE))

import q4_optimize  # noqa: E402
from q4_experiment import random_mixed_sources  # noqa: E402
from cert_joint_agents import AggOrderAgent  # noqa: E402
from cert_refined_agent import RefinedAgent  # noqa: E402

STRATS = {"C": AggOrderAgent, "Cref": RefinedAgent}


def main():
    seed = 20260925
    rng = random.Random(seed)
    cases = [random_mixed_sources(rng, None, 0.5) for _ in range(500)]
    work = [(index, sources, seed, name, cls)
            for index, sources in enumerate(cases, 1)
            for name, cls in STRATS.items()]
    rows = []
    with ProcessPoolExecutor(max_workers=16) as pool:
        for done, row in enumerate(pool.map(q4_optimize._run_work, work), 1):
            rows.append(row)
            if done % 250 == 0:
                print(f"normal {done}/{len(work)}", flush=True)
    out = {}
    for name in STRATS:
        g = [r for r in rows if r["strategy"] == name]
        per = [r["total_virtual_time_s"] / r["source_count"] for r in g]
        out[name] = {
            "all_clear": sum(r["all_cleared"] for r in g),
            "cases": len(g),
            "mean": statistics.mean(per),
            "p95": q4_optimize.percentile(per, 0.95),
        }
        print(f"{name:>5}: {out[name]['all_clear']}/{out[name]['cases']} "
              f"mean={out[name]['mean']:.2f} p95={out[name]['p95']:.2f}", flush=True)
    (HERE / "results" / "refined_confirm_20260925.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

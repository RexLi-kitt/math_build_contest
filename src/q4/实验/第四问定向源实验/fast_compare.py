"""Run named Q4 fast strategies on paired random cases and print compact stats."""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from q4_experiment import random_mixed_sources
from q4_optimize import L1000C2, L1100C2, L950C2, L1200C2, run_case
from fast_q4 import (CertifiedRingAgent, H7Agent, H8ActionRoutingAgent, H8Agent,
                     H8BeamAgent, H8ChaseAgent, H8Clear500Agent,
                     H8Clear900Agent, H8Filter03Agent, H8Filter03ChaseAgent,
                     H8Filter05Agent, L1000Inner3Agent, L1100I3Clear500Agent,
                     L1100Inner3Agent, L1100Inner6Agent, L1100Inner6R300Agent)

STRATEGIES = {
    "L1100_C2": L1100C2,
    "L1200_C2": L1200C2,
    "L1000_C2": L1000C2,
    "L950_C2": L950C2,
    "L1100I3": L1100Inner3Agent,
    "L1100I6": L1100Inner6Agent,
    "L1100I6R300": L1100Inner6R300Agent,
    "L1000I3": L1000Inner3Agent,
    "CertRing33": CertifiedRingAgent,
    "H7": H7Agent,
    "H8": H8Agent,
    "H8Beam": H8BeamAgent,
    "H8Chase": H8ChaseAgent,
    "H8Route": H8ActionRoutingAgent,
    "H8F03": H8Filter03Agent,
    "H8F05": H8Filter05Agent,
    "H8F03C": H8Filter03ChaseAgent,
    "H8C500": H8Clear500Agent,
    "H8C900": H8Clear900Agent,
    "L1100I3C500": L1100I3Clear500Agent,
}


def _work(item):
    return run_case(*item)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20260916)
    parser.add_argument("--strategies", default="L1100_C2,L1100I3,L1100I6")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--sources", type=int, choices=range(10, 17))
    parser.add_argument("--directional-fraction", type=float, default=0.5)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    names = [n.strip() for n in args.strategies.split(",") if n.strip()]
    selected = {n: STRATEGIES[n] for n in names}
    rng = random.Random(args.seed)
    if args.sources:
        cases = [random_mixed_sources(rng, args.sources, args.directional_fraction)
                 for _ in range(args.cases)]
    else:
        cases = [random_mixed_sources(rng, None, args.directional_fraction)
                 for _ in range(args.cases)]
    work = [(i, sources, args.seed, name, cls)
            for i, sources in enumerate(cases, 1) for name, cls in selected.items()]
    rows = []
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for done, row in enumerate(pool.map(_work, work), 1):
            rows.append(row)
            if done % max(1, len(work) // 10) == 0 or done == len(work):
                print(f"{done}/{len(work)}", flush=True)
    print(f"wall {time.perf_counter()-started:.0f}s")
    header = (f"{'strategy':>12} {'sites':>5} {'succ':>6} {'s/src':>7} {'p95src':>7} "
              f"{'search':>7} {'post':>6} {'move':>7} {'det':>6} {'sw':>5} {'clr':>5} {'fail':>5}")
    print(header)
    out = {}
    for name in selected:
        group = [r for r in rows if r["strategy"] == name]
        per = [r["total_virtual_time_s"] / r["source_count"] for r in group]
        s = {
            "success": sum(r["all_cleared"] for r in group) / len(group),
            "per_source": statistics.mean(per),
            "p95": sorted(per)[min(len(per) - 1, int(0.95 * len(per)) - 1)],
            "search": statistics.mean(r["search_end_time_s"] / r["source_count"] for r in group),
            "post": statistics.mean((r["total_virtual_time_s"] - r["search_end_time_s"]) / r["source_count"] for r in group),
            "move": statistics.mean(r["movement_time_s"] / r["source_count"] for r in group),
            "det": statistics.mean(r["detection_time_s"] / r["source_count"] for r in group),
            "sw": statistics.mean(r["switching_time_s"] / r["source_count"] for r in group),
            "clr": statistics.mean(r["clearing_time_s"] / r["source_count"] for r in group),
            "fail": statistics.mean(r["failed_clear_actions"] for r in group),
            "sites": group[0]["search_sites"],
        }
        out[name] = s
        print(f"{name:>12} {s['sites']:>5} {s['success']:>6.3f} {s['per_source']:>7.1f} "
              f"{s['p95']:>7.1f} {s['search']:>7.1f} {s['post']:>6.1f} {s['move']:>7.1f} "
              f"{s['det']:>6.1f} {s['sw']:>5.1f} {s['clr']:>5.1f} {s['fail']:>5.2f}")
    failures = [(r["case"], r["strategy"], r["detected_channels"], r["cleared_channels"])
                for r in rows if not r["all_cleared"]]
    print("failures:", failures if failures else "none")
    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        import csv as _csv
        with (out_dir / "case_results.csv").open("w", newline="", encoding="utf-8-sig") as f:
            writer = _csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (out_dir / "summary.json").write_text(
            json.dumps({"config": vars(args), "summaries": out,
                        "failures": failures}, ensure_ascii=False, indent=2),
            encoding="utf-8")


if __name__ == "__main__":
    main()

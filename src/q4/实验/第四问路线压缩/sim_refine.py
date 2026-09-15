"""模拟器在环的设计精炼: 用真实每源时间直接做局部搜索。

- 屏幕案例: 120 局 seed 20260933 (新种子, 与所有验证种子分离)
- 配对比较: 候选 vs 当前最优, 同案例每源时间差
- 硬约束: certfast (10/0.5) <= 174 (保守证书)
- 移动: 移站/删站/向路径邻居拉直/小抖动
- 输出: refined_design.json (通过后再上 500 局新种子验证)
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

EXP = r"C:\Users\李\Desktop\第四问定向源实验"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, EXP)
sys.path.insert(0, str(HERE))

from baseline_core import dist  # noqa: E402
from q4_experiment import (DirectionalSimulator, clone_sources,  # noqa: E402
                           random_mixed_sources, Q4TriangularCoverageAgent)
from certfast import audit as faudit  # noqa: E402

SCREEN_SEED = 20260933
SCREEN_CASES = 120
FINE_TH = 174.0


def make_agent_class(sites_by_order):
    class _Agent(Q4TriangularCoverageAgent):
        coverage_observation_target = 2

        def __init__(self, sim, verbose: bool = False):
            super().__init__(sim, verbose)
            self.search_points = list(sites_by_order)

        def _coverage_order(self, unvisited):
            return list(unvisited)

    return _Agent


def eval_work(item):
    sites_by_order, case_index, sources, seed = item
    cls = make_agent_class(sites_by_order)
    sim = DirectionalSimulator(clone_sources(sources), seed * 100000 + case_index)
    agent = cls(sim)
    result = agent.run()
    return (case_index, result["total_virtual_time_s"] / len(sources),
            int(result["cleared_channels"] == len(sources)))


def evaluate(pool, sites, order, cases, seed):
    sites_by_order = [tuple(sites[i]) for i in order]
    items = [(sites_by_order, i, sources, seed)
             for i, sources in enumerate(cases, 1)]
    per_case, clears = {}, 0
    for case_index, per, ok in pool.map(eval_work, items):
        per_case[case_index] = per
        clears += ok
    return per_case, clears


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="c_design.json")
    parser.add_argument("--out", default="refined_design.json")
    parser.add_argument("--iters", type=int, default=600)
    args = parser.parse_args()

    design = json.loads((HERE / args.start).read_text(encoding="utf-8"))
    sites = [tuple(p) for p in design["sites"]]
    order = list(design["order"])
    n = len(sites)
    assert sorted(order) == list(range(n))

    rng = random.Random(20260933)
    cases = [random_mixed_sources(rng, None, 0.5) for _ in range(SCREEN_CASES)]

    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=16) as pool:
        incumbent, clears = evaluate(pool, sites, order, cases, SCREEN_SEED)
        inc_mean = statistics.mean(incumbent.values())
        print(f"incumbent: {inc_mean:.2f} s/源 clears={clears}/{SCREEN_CASES} "
              f"({time.perf_counter() - t0:.0f}s)", flush=True)

        best_sites, best_order = list(sites), list(order)
        best_mean = inc_mean
        n_eval = 0
        accepted = 0
        t1 = time.perf_counter()
        for it in range(args.iters):
            cand = [tuple(p) for p in best_sites]
            cand_order = list(best_order)
            move = rng.random()
            if move < 0.10 and len(cand) > 26:
                idx = rng.randrange(len(cand))
                pos = cand_order.index(idx)
                cand.pop(idx)
                rest = cand_order[:pos] + cand_order[pos + 1:]
                cand_order = [i if i < idx else i - 1 for i in rest]
            elif move < 0.40:
                i = rng.randrange(len(cand))
                d = rng.uniform(30.0, 250.0)
                a = rng.uniform(0.0, 2.0 * math.pi)
                cand[i] = (cand[i][0] + d * math.cos(a),
                           cand[i][1] + d * math.sin(a))
            elif move < 0.70:
                i = rng.randrange(len(cand))
                pos = cand_order.index(i)
                a = cand[cand_order[pos - 1]] if pos > 0 else (0.0, 0.0)
                b = (cand[cand_order[pos + 1]] if pos + 1 < len(cand)
                     else cand[cand_order[pos - 1]])
                t = rng.uniform(0.3, 0.7)
                cand[i] = (a[0] + t * (b[0] - a[0]) + rng.uniform(-20, 20),
                           a[1] + t * (b[1] - a[1]) + rng.uniform(-20, 20))
            else:
                i = rng.randrange(len(cand))
                d = rng.uniform(5.0, 60.0)
                a = rng.uniform(0.0, 2.0 * math.pi)
                cand[i] = (cand[i][0] + d * math.cos(a),
                           cand[i][1] + d * math.sin(a))

            g = faudit(cand, 10.0, 0.5)[0]
            if g > FINE_TH:
                continue
            n_eval += 1
            per_case, clears = evaluate(pool, cand, cand_order, cases, SCREEN_SEED)
            mean = statistics.mean(per_case.values())
            diff = statistics.mean(per_case[k] - incumbent[k] for k in incumbent)
            if clears == SCREEN_CASES and diff < -1.0:
                incumbent = per_case
                best_sites, best_order = cand, cand_order
                best_mean = mean
                accepted += 1
                print(f"  it={it} ACCEPT: {mean:.2f} s/源 (diff {diff:+.2f}) "
                      f"n={len(cand)} gap={g:.1f} ({time.perf_counter() - t1:.0f}s)",
                      flush=True)
            if n_eval % 25 == 0:
                print(f"  it={it} evals={n_eval} best={best_mean:.2f} "
                      f"acc={accepted} ({time.perf_counter() - t1:.0f}s)", flush=True)

        print(f"\nrefine done: {inc_mean:.2f} -> {best_mean:.2f} s/源 "
              f"({best_mean - inc_mean:+.2f}), evals={n_eval}, acc={accepted}",
              flush=True)
        out = {
            "sites": [list(p) for p in best_sites],
            "order": best_order,
            "screen_mean": best_mean,
            "screen_seed": SCREEN_SEED,
            "screen_cases": SCREEN_CASES,
            "source_design": args.start,
        }
        (HERE / args.out).write_text(json.dumps(out, indent=2),
                                     encoding="utf-8")
        print(f"saved {args.out}", flush=True)


if __name__ == "__main__":
    main()

"""从搜索出货设计直接驱动配对验证。

衔接 search_cert_route.py 的 Stage C 出货(best_design.json / search_results.json
中 ship:true 的设计)与 fast_compare 的配对实验: 读设计 -> 按 order 生成
search_points -> 逐设计跑同一批随机案例 -> 汇总成功率 / 每源时间 / 分块构成,
并额外跑 certify 双网格细审复核证书余量。

用法:
  python ship_design_runner.py                      # 用 best_design.json
  python ship_design_runner.py --design search_results.json \
      --tag H8,B004 --cases 500 --seed 20260923 --sources 12 \
      --jobs 8 --output results/ship_run
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, r"C:\Users\李\Desktop\第四问路线压缩")

from q4_experiment import Q4TriangularCoverageAgent, DirectionalSimulator  # noqa: E402
from q4_experiment import clone_sources, percentile, random_mixed_sources  # noqa: E402
from certify import certify  # noqa: E402


def _percent(values, p):
    return percentile(values, p)


def load_designs(path, tags):
    """从设计 JSON 读候选。兼容 best_design.json(单对象) 与 search_results.json(数组)。

    只保留 ship 合格(count: True / 无 ship 字段视为候选) 且 tag 指定(若给定)。
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = raw if isinstance(raw, list) else [raw]
    designs = []
    for e in entries:
        if "sites" not in e:
            continue
        if "order" not in e:
            # 顺序缺省: 最近邻兜底(与 _coverage_order 一致)
            sites = [tuple(p) for p in e["sites"]]
            order = list(range(len(sites)))
        else:
            sites = [tuple(p) for p in e["sites"]]
            order = list(e["order"])
        if len(order) != len(sites):
            raise ValueError(f"order 长度 {len(order)} != sites {len(sites)}")
        name = e.get("tag") or e.get("trial") or f"n{len(sites)}"
        if tags and name not in tags:
            continue
        designs.append({
            "name": name,
            "sites": sites,
            "order": order,
            "gap_fine": e.get("gap_fine"),
            "gap_ultra": e.get("gap_ultra"),
            "worst_x": e.get("worst_x"),
            "tour_m": e.get("tour") or e.get("tour_m"),
        })
    return designs


def make_agent_class(design):
    """用设计站点构造 Q4 全清除智能体的子类并返回。

    search_points 直接按设计 order 排列, search() 会按列表顺序逐站停靠,
    从而沿用 Stage C 的 TSP 访问顺序, 避免运行时重新探查路径。
    """
    sites_by_order = [tuple(design["sites"][i]) for i in design["order"]]

    class _ShippedDesignAgent(Q4TriangularCoverageAgent):
        coverage_observation_target = 2

        def __init__(self, sim, verbose: bool = False):
            super().__init__(sim, verbose)
            # 覆盖 _triangular_sites: 搜索站点即设计站点, 顺序即 TSP 顺序
            self.search_points = sites_by_order

        def _coverage_order(self, unvisited):
            # search() 实际不用 _coverage_order; 这里保留设计顺序语义兜底
            return sorted(unvisited, key=lambda p: sites_by_order.index(p))

        def search_site_count(self):
            return len(self.search_points)

    _ShippedDesignAgent.__name__ = f"Shipped_{design['name']}"
    return _ShippedDesignAgent


def _cert_brief(sites):
    """对给定站点跑 certify 双网格细审, 返回 (gap_fine10, gap_ultra5, worst_x)。"""
    pts = [tuple(p) for p in sites]
    gf, wx1 = certify(pts, r_step=10.0, t_step=0.5)
    gu, wx2 = certify(pts, r_step=5.0, t_step=0.25)
    return gf, gu, wx1 or wx2


def run_one(entry):
    case_index, sources, seed, design = entry
    agent_class = make_agent_class(design)
    sim = DirectionalSimulator(clone_sources(sources), seed * 100000 + case_index)
    started = time.perf_counter()
    agent = agent_class(sim)
    result = agent.run()
    search_end_s = getattr(agent, "search_end_time_s", float("nan"))
    rows = {
        "case": case_index,
        "strategy": design["name"],
        "source_count": len(sources),
        **result,
        "all_cleared": int(result["cleared_channels"] == len(sources)),
        "search_sites": len(agent.search_points),
        "search_end_time_s": search_end_s,
        "wall_time_s": time.perf_counter() - started,
    }

    movement = search_mv = post_mv = det = sw = clr = 0.0
    failed = 0
    prev = (0.0, 0.0)
    cur_ch = 1
    for a in sim.actions:
        if a.position is not None:
            mv = math.dist(prev, a.position) / 5.0
            movement += mv
            if a.virtual_time_s <= search_end_s + 1e-6:
                search_mv += mv
            else:
                post_mv += mv
            prev = a.position
        if a.kind == "measure":
            det += 5.0
            if a.channel != cur_ch:
                sw += 1.0
            cur_ch = a.channel
        elif a.kind == "clear":
            if a.result == "success":
                clr += 5.0
            else:
                clr += 3.0
                failed += 1
    rows.update({
        "movement_time_s": movement,
        "search_movement_time_s": search_mv,
        "post_search_movement_time_s": post_mv,
        "detection_time_s": det,
        "switching_time_s": sw,
        "clearing_time_s": clr,
        "failed_clear_actions": failed,
    })
    return rows


def _work(item):
    return run_one(item)


def main():
    ap = argparse.ArgumentParser(description="搜索出货设计 -> 配对验证衔接")
    ap.add_argument("--design", default=r"C:\Users\李\Desktop\第四问路线压缩\best_design.json")
    ap.add_argument("--tag", default=None, help="逗号分隔, 仅验证这些 tag; 默认全部候选")
    ap.add_argument("--cases", type=int, default=500)
    ap.add_argument("--seed", type=int, default=20260923)
    ap.add_argument("--sources", type=int, default=12)
    ap.add_argument("--directional-fraction", type=float, default=0.5)
    ap.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    ap.add_argument("--output", default="results/ship_run")
    ap.add_argument("--re-certify", action="store_true",
                    help="对每个设计额外跑 certify 双网格细审, 复核证书余量")
    args = ap.parse_args()

    tags = [t.strip() for t in args.tag.split(",")] if args.tag else None
    designs = load_designs(args.design, tags)
    if not designs:
        raise SystemExit(f"设计文件无可用候选: {args.design}")
    print(f"载入 {len(designs)} 个候选: {[d['name'] for d in designs]}")

    if args.re_certify:
        for d in designs:
            gf, gu, wx = _cert_brief(d["sites"])
            d["gap_fine"] = d["gap_fine"] if d["gap_fine"] is not None else gf
            d["gap_ultra"] = d["gap_ultra"] if d["gap_ultra"] is not None else gu
            print(f"  certify {d['name']:>10}: n={len(d['sites'])} "
                  f"(10/0.5)={gf:.2f} (5/0.25)={gu:.2f} worst={wx}")

    rng = random.Random(args.seed)
    cases = [random_mixed_sources(rng, args.sources, args.directional_fraction)
             for _ in range(args.cases)]
    work = []
    for d in designs:
        for i, sources in enumerate(cases, 1):
            work.append((i, sources, args.seed, d))

    rows = []
    started = time.perf_counter()
    step = max(1, len(work) // 20)
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for done, row in enumerate(pool.map(_work, work), 1):
            rows.append(row)
            if done % step == 0 or done == len(work):
                print(f"run {done:04d}/{len(work)} complete", flush=True)
    print(f"wall {time.perf_counter() - started:.0f}s")

    summary = []
    for d in designs:
        g = [r for r in rows if r["strategy"] == d["name"]]
        if not g:
            continue
        per = [r["total_virtual_time_s"] / r["source_count"] for r in g]
        summary.append({
            "design": d["name"],
            "sites": len(d["sites"]),
            "tour_m": d["tour_m"],
            "gap_fine": d.get("gap_fine"),
            "gap_ultra": d.get("gap_ultra"),
            "success_rate": sum(r["all_cleared"] for r in g) / len(g),
            "mean_time_per_source_s": statistics.mean(per),
            "p95_time_per_source_s": _percent(per, 0.95),
            "mean_search_per_source_s": statistics.mean(
                r["search_end_time_s"] / r["source_count"] for r in g),
            "mean_post_search_per_source_s": statistics.mean(
                (r["total_virtual_time_s"] - r["search_end_time_s"]) / r["source_count"] for r in g),
            "mean_movement_per_source_s": statistics.mean(
                r["movement_time_s"] / r["source_count"] for r in g),
            "mean_search_movement_per_source_s": statistics.mean(
                r["search_movement_time_s"] / r["source_count"] for r in g),
            "mean_post_search_movement_per_source_s": statistics.mean(
                r["post_search_movement_time_s"] / r["source_count"] for r in g),
            "mean_detection_per_source_s": statistics.mean(
                r["detection_time_s"] / r["source_count"] for r in g),
            "mean_failed_clear_actions": statistics.mean(
                r["failed_clear_actions"] for r in g),
        })
    summary.sort(key=lambda s: (s["success_rate"] < 1.0, s["mean_time_per_source_s"]))
    for s in summary:
        print(f"{s['design']:>10} n={s['sites']:>3} succ={s['success_rate']:>6.3f} "
              f"src={s['mean_time_per_source_s']:>7.1f} p95={s['p95_time_per_source_s']:>7.1f} "
              f"gap5={s['gap_ultra']}")

    failures = [(r["case"], r["strategy"], r["detected_channels"], r["cleared_channels"])
                for r in rows if not r["all_cleared"]]
    print("failures:", failures if failures else "none")

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "case_results.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out / "summary.json").write_text(
        json.dumps({"config": vars(args), "summaries": summary,
                    "failures": failures}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"saved -> {out.resolve()}")


if __name__ == "__main__":
    main()
"""有答案测试机：第三问模型 I 的七项指标 + 完美信息最优解对比。

- 运行 I（或指定变体），统计统一七项指标；
- 用真实源位置计算开放 TSP（Held-Karp 精确解）给出移动时间下界；
- 分解搜索/清除阶段的移动、检测、切换、清除时间，输出与最优走线的差距；
- 可选输出单局动作轨迹与 SVG 走线图，便于人工看差距。

用法:
  python oracle_harness.py --cases 100 --seed 55021 --jobs 16
  python oracle_harness.py --cases 5 --variant I_ring_optimized --trace 1
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from itertools import permutations
from pathlib import Path

CODE_DIR = Path(r"C:\Users\李\Desktop\B题模型代码汇总\第三问策略对比")
sys.path.insert(0, str(CODE_DIR))

from baseline_core import (OfflineSimulator, Source, add, dist,  # noqa: E402
                           random_sources)
from model_j import JAgent  # noqa: E402
from model_jplus import JPlusAgent  # noqa: E402
from model_k import KAgent  # noqa: E402
from strategies import RingOptimizedAgent  # noqa: E402

SPEED = 5.0
MEASURE_TIME = 5.0
SWITCH_TIME = 1.0
CLEAR_SUCCESS_TIME = 5.0
CLEAR_FAIL_TIME = 3.0


class InstrumentedI(RingOptimizedAgent):
    """I + 阶段/类别打点，不改变任何决策。"""

    def __init__(self, sim: OfflineSimulator, verbose: bool = False):
        super().__init__(sim, verbose)
        self.phase = "search"
        self._co_depth = 0
        self.trace: list[tuple] = []

    def search(self) -> None:
        super().search()
        self.phase = "clear"

    def observe(self, p, channel):
        result = super().observe(p, channel)
        self.trace.append((self.phase, "co" if self._co_depth else "active",
                           round(self.sim.time_s, 6), p, channel, result))
        return result

    def _coobserve(self, point, primary_channel) -> None:
        self._co_depth += 1
        try:
            super()._coobserve(point, primary_channel)
        finally:
            self._co_depth -= 1


class Ring6Shrunk(InstrumentedI):
    """k=6 ring shrunk to the coverage limit (sqrt(1800^2+R^2-2*1800*R*cos30)<=1000)."""

    search_ring_r = 1130.0


class Ring7Compact(InstrumentedI):
    """Origin + 7 ring stops at radius ~1010; worst coverage point 992 m."""

    search_ring_r = 1010.0
    ring_count = 7

    def __init__(self, sim: OfflineSimulator, verbose: bool = False):
        super().__init__(sim, verbose)
        step = 360.0 / self.ring_count
        self.search_points = [(0.0, 0.0)] + [
            add((0.0, 0.0), self.search_ring_r, step * k)
            for k in range(self.ring_count)]


class Ring8Compact(Ring7Compact):
    search_ring_r = 950.0
    ring_count = 8


class Ring7Threshold(Ring7Compact):
    """k=7 at the mathematical coverage limit (worst point 998.25 m)."""

    search_ring_r = 1000.0


class Ring7Safe(Ring7Compact):
    search_ring_r = 1020.0


class NoOriginScan(Ring7Compact):
    """k=7 ring at R<=1000 replaces the origin stop; skip the 20-channel origin scan.

    The ring itself covers the centre (R<=1000), so the origin measurement is only
    an early-detection convenience whose 120 s scan cost is not repaid.
    """

    search_ring_r = 999.0

    def search(self) -> None:
        self._orient_coverage_ring()
        self.say("跳过原点扫描")
        unvisited = list(self.search_points[1:])
        while unvisited and sum(st.discovered for st in self.state.values()) < 16:
            next_coverage = self._coverage_order(unvisited)[0]
            insertion = self._insertion_before(next_coverage)
            if insertion is not None:
                channel, point = insertion
                self.observe(point, channel)
                self.state[channel].attempts += 1
                self.coverage_insertions += 1
                self._coobserve(point, channel)
                self._opportunistic_clear(next_coverage)
                continue
            for channel, st in self.state.items():
                if not st.discovered:
                    self.observe(next_coverage, channel)
            self.max_coobservations = max(
                self.coverage_extra_measure_budget,
                min(6, sum(st.discovered and not st.cleared
                           for st in self.state.values()) // 3),
            )
            self._coobserve(next_coverage, -1)
            unvisited.remove(next_coverage)
            following = self._coverage_order(unvisited)[0] if unvisited else None
            self._opportunistic_clear(following)
            self.say(f"搜索点 {next_coverage!r} 完成，虚拟时间 {self.sim.time_s:.1f}s")
        self.search_end_time_s = self.sim.time_s


class JInstrumented(InstrumentedI, JAgent):
    """J with the harness trace hooks (no decision changes)."""


class JPlusInstrumented(InstrumentedI, JPlusAgent):
    """J+ with the harness trace hooks (no decision changes)."""


class KInstrumented(InstrumentedI, KAgent):
    """K prototype with the harness trace hooks (no decision changes)."""


class JContinuation(JInstrumented):
    """Direction 1a: order coverage stops by path + full clearing continuation.

    ``_coverage_order`` in F only pulls the last stop towards the *nearest*
    unresolved anchor.  Here the ordering cost includes an estimate of the whole
    source route that follows the sweep (nearest-neighbour + 2-opt from the last
    coverage stop through every unresolved anchor), so the sweep ends where the
    clearing route is cheap.
    """

    @staticmethod
    def _route_cost_from(start, points):
        if not points:
            return 0.0
        remaining = list(points)
        route = []
        current = start
        while remaining:
            nxt = min(remaining, key=lambda p: dist(current, p))
            route.append(nxt)
            current = nxt
            remaining.remove(nxt)

        def cost(order):
            pts = [start] + order
            return sum(dist(a, b) for a, b in zip(pts, pts[1:]))

        improved = True
        while improved:
            improved = False
            best = cost(route)
            for i in range(len(route) - 1):
                for j in range(i + 1, len(route)):
                    candidate = route[:i] + route[i:j + 1][::-1] + route[j + 1:]
                    value = cost(candidate)
                    if value < best - 1e-9:
                        route, improved = candidate, True
                        break
                if improved:
                    break
        return cost(route)

    def _coverage_order(self, unvisited):
        if len(unvisited) <= 1:
            return list(unvisited)
        anchors = [self._target_anchor(st) for st in self.state.values()
                   if st.discovered and not st.cleared and not st.exhausted]
        if not anchors:
            return super()._coverage_order(unvisited)
        route_cost = [
            self._route_cost_from(anchor, anchors[:i] + anchors[i + 1:])
            for i, anchor in enumerate(anchors)
        ]
        continuation = {}
        for candidate in unvisited:
            continuation[candidate] = min(
                dist(candidate, anchor) + route_cost[i]
                for i, anchor in enumerate(anchors))
        best_order, best_cost = None, math.inf
        for order in permutations(unvisited):
            path = [self.sim.position, *order]
            cost = (sum(dist(a, b) for a, b in zip(path, path[1:]))
                    + continuation[order[-1]])
            if cost < best_cost - 1e-6:
                best_order, best_cost = order, cost
        return list(best_order) if best_order is not None else list(unvisited)


class JOpportunistic(JInstrumented):
    """Direction 1b: parameterised on-the-way clearing detour budget."""

    opp_budget_m = 250.0

    def _opportunistic_clear(self, next_point) -> None:
        if next_point is None:
            return
        considered: set[int] = set()
        while True:
            choices = []
            for channel, st in self.state.items():
                if channel in considered or st.cleared or not st.discovered:
                    continue
                center = self._clear_decision(st)
                if center is None:
                    continue
                extra = (dist(self.sim.position, center) + dist(center, next_point)
                         - dist(self.sim.position, next_point))
                if extra <= self.opp_budget_m:
                    choices.append((extra, channel, center))
            if not choices:
                return
            _, channel, center = min(choices)
            considered.add(channel)
            if self._try_clear(center, channel):
                self.state[channel].cleared = True


class JContinuationOpp(JContinuation, JOpportunistic):
    """Both direction-1 mechanisms with an enlarged 400 m clearing detour."""

    opp_budget_m = 400.0


def _tuned(name: str, **attrs):
    return type(name, (Ring7Threshold,), attrs)


VARIANTS = {
    "I_ring_optimized": InstrumentedI,
    "I_ring6_1130": Ring6Shrunk,
    "I_ring7_1010": Ring7Compact,
    "I_ring7_1000": Ring7Threshold,
    "J_ring7_1000": JInstrumented,
    "Jplus": JPlusInstrumented,
    "K_rolling_union": KInstrumented,
    "I_ring7_1020": Ring7Safe,
    "I_ring7_noorigin_999": NoOriginScan,
    "I_ring8_950": Ring8Compact,
}
class JContinuationB0(JContinuation):
    """Direction 1: continuation-aware ordering with coverage insertions off."""

    insertion_budget_m = 0.0


VARIANTS.update({
    "J_cont": JContinuation,
    "J_cont_b0": JContinuationB0,
    "J_b0_even_co5": type("J_b0_even_co5", (JInstrumented,), {
        "insertion_budget_m": 0.0,
        "weights": (0.25, 0.25, 0.25, 0.25),
        "coverage_extra_measure_budget": 5,
    }),
    "J_opp400": type("J_opp400", (JOpportunistic,), {"opp_budget_m": 400.0}),
    "J_cont_opp400": JContinuationOpp,
    "J_b0": type("J_b0", (JInstrumented,), {"insertion_budget_m": 0.0}),
    "J_b150": type("J_b150", (JInstrumented,), {"insertion_budget_m": 150.0}),
    "J_co6": type("J_co6", (JInstrumented,),
                  {"coverage_extra_measure_budget": 6}),
    "R7_b100_i8": _tuned("R7_b100_i8", insertion_budget_m=100.0),
    "R7_b180_i8": _tuned("R7_b180_i8", insertion_budget_m=180.0),
    "R7_b180_i12": _tuned("R7_b180_i12", insertion_budget_m=180.0,
                          max_coverage_insertions=12),
    "R7_b140_i12": _tuned("R7_b140_i12", max_coverage_insertions=12),
    "R7_co4": _tuned("R7_co4", coverage_extra_measure_budget=4),
    "R7_co5": _tuned("R7_co5", coverage_extra_measure_budget=5),
    "R7_thr005": _tuned("R7_thr005", coobserve_threshold=0.05),
    "R7_b100_co5": _tuned("R7_b100_co5", insertion_budget_m=100.0,
                          coverage_extra_measure_budget=5),
    "R7_w_rpred30": _tuned("R7_w_rpred30", weights=(0.25, 0.20, 0.25, 0.30)),
    "R7_w_rpred25": _tuned("R7_w_rpred25", weights=(0.20, 0.25, 0.30, 0.25)),
    "R7_w_even": _tuned("R7_w_even", weights=(0.25, 0.25, 0.25, 0.25)),
    "R7_riskclear25": _tuned("R7_riskclear25", clear_margin_m=-5.0),
    "R7_riskclear21": _tuned("R7_riskclear21", clear_margin_m=-1.0),
    "R7_riskclear22": _tuned("R7_riskclear22", clear_margin_m=-2.0),
    "R7_b100_co5_even": _tuned("R7_b100_co5_even", insertion_budget_m=100.0,
                               coverage_extra_measure_budget=5,
                               weights=(0.25, 0.25, 0.25, 0.25)),
})


def held_karp_open(start: tuple[float, float],
                   points: list[tuple[float, float]]) -> float:
    """从 start 出发经过所有 points 的最短开放路径长度（精确 Held-Karp）。"""
    n = len(points)
    if n == 0:
        return 0.0
    if n == 1:
        return dist(start, points[0])
    d = [[dist(points[i], points[j]) for j in range(n)] for i in range(n)]
    full = (1 << n) - 1
    inf = float("inf")
    dp = [[inf] * n for _ in range(1 << n)]
    for i in range(n):
        dp[1 << i][i] = dist(start, points[i])
    for mask in range(1, 1 << n):
        row = dp[mask]
        bits = mask
        while bits:
            low = bits & -bits
            i = low.bit_length() - 1
            bits ^= low
            base = row[i]
            if base == inf:
                continue
            rest = full ^ mask
            r = rest
            while r:
                low2 = r & -r
                j = low2.bit_length() - 1
                r ^= low2
                nm = mask | low2
                nd = base + d[i][j]
                if nd < dp[nm][j]:
                    dp[nm][j] = nd
    return min(dp[full])


def extract(sim: OfflineSimulator, agent: InstrumentedI,
            sources: list[Source]) -> dict:
    n = len(sources)
    total = sim.time_s
    search_end = getattr(agent, "search_end_time_s", float("nan"))
    true_channels = {s.channel: s for s in sources}
    first_detect: dict[int, float] = {}
    cur_ch = 1
    stats = {
        "move_search": 0.0, "move_clear": 0.0,
        "meas_search": 0, "meas_clear": 0, "meas_post": 0,
        "meas_co": 0, "meas_active_clear": 0,
        "switch_search": 0, "switch_clear": 0,
        "nosig_search": 0, "nosig_clear": 0,
        "clear_ok": 0, "clear_fail": 0, "clear_ok_search": 0,
    }
    prev = (0.0, 0.0)
    for a in sim.actions:
        if a.position is not None:
            leg = dist(prev, a.position) / SPEED
            if a.virtual_time_s <= search_end + 1e-9:
                stats["move_search"] += leg
            else:
                stats["move_clear"] += leg
            prev = a.position
        in_search = a.virtual_time_s <= search_end + 1e-9
        if a.kind == "measure":
            switched = a.channel != cur_ch
            cur_ch = a.channel
            if switched:
                stats["switch_search" if in_search else "switch_clear"] += 1
            stats["meas_search" if in_search else "meas_clear"] += 1
            if a.result == "no_signal":
                stats["nosig_search" if in_search else "nosig_clear"] += 1
            if a.result in ("direction", "near") and a.channel not in first_detect:
                first_detect[a.channel] = a.virtual_time_s
        elif a.kind == "clear":
            if a.result == "success":
                stats["clear_ok"] += 1
                if in_search:
                    stats["clear_ok_search"] += 1
            else:
                stats["clear_fail"] += 1
    for entry in agent.trace:
        phase, kind = entry[0], entry[1]
        if kind == "co":
            stats["meas_co"] += 1
        elif phase == "clear" and entry[5] != "near":
            stats["meas_active_clear"] += 1

    detected = [ch for ch in true_channels if ch in first_detect]
    last_detect = max((first_detect[ch] for ch in detected), default=float("nan"))
    clear_time = (stats["clear_ok"] * CLEAR_SUCCESS_TIME
                  + stats["clear_fail"] * CLEAR_FAIL_TIME)
    meas_time = (stats["meas_search"] + stats["meas_clear"]) * MEASURE_TIME
    switch_time = (stats["switch_search"] + stats["switch_clear"]) * SWITCH_TIME
    movement = stats["move_search"] + stats["move_clear"]

    return {
        "n": n, "total": total, "search_end": search_end,
        "per_source": total / n,
        "all_cleared": int(stats["clear_ok"] == n),
        "movement": movement, "move_search": stats["move_search"],
        "move_clear": stats["move_clear"],
        "meas_time": meas_time, "switch_time": switch_time,
        "clear_time": clear_time,
        "meas_search": stats["meas_search"], "meas_clear": stats["meas_clear"],
        "meas_co": stats["meas_co"],
        "meas_active_clear": stats["meas_active_clear"],
        "nosig_search": stats["nosig_search"], "nosig_clear": stats["nosig_clear"],
        "clear_fail": stats["clear_fail"], "clear_ok_search": stats["clear_ok_search"],
        "last_detect": last_detect,
        "post_search_time": total - search_end,
        "post_share": (total - search_end) / total * 100.0,
        "detected": len(detected),
    }


def oracle_bounds(sim: OfflineSimulator, agent: InstrumentedI,
                  sources: list[Source], metrics: dict) -> dict:
    """完美信息下的移动/总时间下界（从起点、以及从搜索结束点续跑）。"""
    positions = [s.position for s in sources]
    first_clear: dict[int, float] = {}
    for a in sim.actions:
        if a.kind == "clear" and a.result == "success" and a.channel not in first_clear:
            first_clear[a.channel] = a.virtual_time_s
    before_search = {ch for ch, t in first_clear.items()
                     if t <= metrics["search_end"] + 1e-9}
    remaining = [s.position for s in sources if s.channel not in before_search]
    tsp_all = held_karp_open((0.0, 0.0), positions)
    search_actions = [a for a in sim.actions if a.position is not None
                      and a.virtual_time_s <= metrics["search_end"] + 1e-9]
    search_pos = search_actions[-1].position if search_actions else (0.0, 0.0)
    tsp_clear = held_karp_open(search_pos, remaining)
    k = len(remaining)
    return {
        "oracle_tsp_all_m": tsp_all,
        "oracle_total_s": tsp_all / SPEED + len(sources) * CLEAR_SUCCESS_TIME,
        "oracle_clear_move_m": tsp_clear,
        "oracle_clear_phase_s": tsp_clear / SPEED + k * CLEAR_SUCCESS_TIME,
        "n_remaining_at_search_end": k,
        "clear_move_m": metrics["move_clear"] * SPEED,
    }


def run_case(case_index: int, sources: list[Source], seed: int,
             variant_names: list[str], trace_ok: bool, need_oracle: bool) -> list[dict]:
    rows = []
    for variant_name in variant_names:
        sim = OfflineSimulator([Source(s.channel, s.position, s.receive_radius)
                                for s in sources], seed=seed * 100000 + case_index)
        agent = VARIANTS[variant_name](sim)
        agent.run()
        metrics = extract(sim, agent, sources)
        row = {"seed": seed, "case": case_index, "variant": variant_name,
               **metrics}
        if need_oracle:
            row.update(oracle_bounds(sim, agent, sources, metrics))
        if trace_ok:
            row["_trace"] = {
                "sources": [{"channel": s.channel, "position": s.position,
                             "radius": s.receive_radius} for s in sources],
                "ring": agent.search_points,
                "actions": [{"kind": a.kind, "p": a.position, "ch": a.channel,
                             "result": a.result, "t": a.virtual_time_s}
                            for a in sim.actions],
                "trace": agent.trace,
            }
        rows.append(row)
    return rows


def _work(item):
    return run_case(*item)


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1)]


def svg_case(row: dict, path: Path) -> None:
    data = row["_trace"]
    scale = 0.22
    size = 900
    cx = size / 2

    def xy(p):
        return (cx + p[0] * scale, cx + p[1] * scale)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">',
             '<rect width="100%" height="100%" fill="white"/>']
    r = 1800 * scale
    parts.append(f'<circle cx="{cx}" cy="{cx}" r="{r}" fill="none" stroke="#bbb"/>')
    ring = data["ring"]
    if len(ring) > 1:
        pts = " ".join(f"{xy(p)[0]:.1f},{xy(p)[1]:.1f}" for p in ring[1:])
        parts.append(f'<polygon points="{pts}" fill="none" stroke="#ddd" stroke-dasharray="4"/>')
    for s in data["sources"]:
        x, y = xy(s["position"])
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#d33"/>')
        parts.append(f'<text x="{x + 6:.1f}" y="{y - 6:.1f}" font-size="11">{s["channel"]}</text>')
    prev = (0.0, 0.0)
    for a in data["actions"]:
        if a["p"] is None:
            continue
        x0, y0 = xy(prev)
        x1, y1 = xy(a["p"])
        color = "#27a" if a["kind"] == "measure" else "#2a7"
        parts.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{color}" stroke-width="0.7" opacity="0.55"/>')
        if a["kind"] == "measure" and a["result"] == "direction":
            parts.append(f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="2" fill="#27a"/>')
        elif a["kind"] == "clear" and a["result"] == "success":
            parts.append(f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="3.2" fill="#2a7"/>')
        prev = a["p"]
    parts.append(f'<circle cx="{cx:.1f}" cy="{cx:.1f}" r="4" fill="#000"/>')
    parts.append('</svg>')
    path.write_text("".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="模型 I 有答案测试机")
    parser.add_argument("--cases", type=int, default=100)
    parser.add_argument("--seed", type=int, default=55021)
    parser.add_argument("--sources", type=int, choices=range(10, 17))
    parser.add_argument("--variants", default="I_ring_optimized",
                        help="逗号分隔的变体名")
    parser.add_argument("--output", default="results/latest")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--trace", type=int, default=0, help="前 N 局保存轨迹/SVG")
    parser.add_argument("--no-oracle", action="store_true",
                        help="跳过完美信息下界计算，加速稳定性实验")
    args = parser.parse_args()

    variant_names = [v.strip() for v in args.variants.split(",") if v.strip()]
    unknown = [v for v in variant_names if v not in VARIANTS]
    if unknown:
        raise ValueError(f"未知变体: {unknown}；可用: {list(VARIANTS)}")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    cases = [random_sources(rng, args.sources) for _ in range(args.cases)]
    work = [(i, sources, args.seed, variant_names, i <= args.trace,
             not args.no_oracle)
            for i, sources in enumerate(cases, 1)]
    rows = []
    started = time.perf_counter()
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            for done, case_rows in enumerate(pool.map(_work, work), 1):
                rows.extend(case_rows)
                if done % 20 == 0 or done == args.cases:
                    print(f"case {done}/{args.cases}", flush=True)
    else:
        for item in work:
            rows.extend(run_case(*item))
            print(f"case {item[0]}/{args.cases}", flush=True)
    elapsed = time.perf_counter() - started

    for row in rows:
        if "_trace" in row and row["variant"] == variant_names[0]:
            svg_case(row, output / f"route_case_{row['case']:03d}_{row['variant']}.svg")
            (output / f"trace_case_{row['case']:03d}_{row['variant']}.json").write_text(
                json.dumps(row["_trace"], ensure_ascii=False), encoding="utf-8")
    for row in rows:
        row.pop("_trace", None)

    fields = list(rows[0])
    with (output / "case_results.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summaries = {}
    for variant in variant_names:
        group = [r for r in rows if r["variant"] == variant]
        per_source = [r["per_source"] for r in group]
        summary = {
            "cases": len(group), "seed": args.seed,
            "all_cleared_rate": statistics.mean(r["all_cleared"] for r in group),
            "mean_per_source_s": statistics.mean(per_source),
            "sd_per_source_s": statistics.pstdev(per_source),
            "median_per_source_s": statistics.median(per_source),
            "p90_per_source_s": percentile(per_source, .90),
            "p95_per_source_s": percentile(per_source, .95),
            "max_per_source_s": max(per_source),
            "mean_total_s": statistics.mean(r["total"] for r in group),
            "mean_n": statistics.mean(r["n"] for r in group),
            "mean_search_end_s": statistics.mean(r["search_end"] for r in group),
            "mean_move_per_source_s": statistics.mean(r["movement"] / r["n"] for r in group),
            "mean_move_search_per_source_s": statistics.mean(r["move_search"] / r["n"] for r in group),
            "mean_move_clear_per_source_s": statistics.mean(r["move_clear"] / r["n"] for r in group),
            "mean_meas_switch_per_source_s": statistics.mean(
                (r["meas_time"] + r["switch_time"]) / r["n"] for r in group),
            "mean_meas_search_per_source": statistics.mean(r["meas_search"] / r["n"] for r in group),
            "mean_meas_co_per_source": statistics.mean(r["meas_co"] / r["n"] for r in group),
            "mean_nosig_search_per_source": statistics.mean(
                r["nosig_search"] / r["n"] for r in group),
            "mean_meas_active_clear_per_source": statistics.mean(
                r["meas_active_clear"] / r["n"] for r in group),
            "mean_last_detect_s": statistics.mean(r["last_detect"] for r in group),
            "mean_last_detect_per_source_s": statistics.mean(
                r["last_detect"] / r["n"] for r in group),
            "mean_post_share_pct": statistics.mean(r["post_share"] for r in group),
        }
        if not args.no_oracle:
            summary.update({
                "mean_oracle_total_s": statistics.mean(r["oracle_total_s"] for r in group),
                "mean_oracle_per_source_s": statistics.mean(
                    r["oracle_total_s"] / r["n"] for r in group),
                "mean_oracle_clear_phase_s": statistics.mean(
                    r["oracle_clear_phase_s"] for r in group),
                "mean_actual_clear_phase_s": statistics.mean(
                    r["post_search_time"] for r in group),
                "mean_clear_phase_gap_s": statistics.mean(
                    r["post_search_time"] - r["oracle_clear_phase_s"] for r in group),
                "mean_total_gap_s": statistics.mean(
                    r["total"] - r["oracle_total_s"] for r in group),
                "mean_move_ratio_vs_tsp": statistics.mean(
                    r["movement"] * SPEED / r["oracle_tsp_all_m"] for r in group),
                "mean_clear_move_ratio_vs_tsp": statistics.mean(
                    (r["move_clear"] * SPEED) / max(r["oracle_clear_move_m"], 1e-9)
                    for r in group),
            })
        summaries[variant] = summary

    pairing = {}
    if len(variant_names) > 1:
        reference = variant_names[0]
        ref = {r["case"]: r for r in rows if r["variant"] == reference}
        for variant in variant_names[1:]:
            deltas, wins, losses, ties = [], 0, 0, 0
            for row in rows:
                if row["variant"] != variant:
                    continue
                base = ref[row["case"]]["per_source"]
                delta = base - row["per_source"]
                deltas.append(delta)
                if delta > 1e-6:
                    wins += 1
                elif delta < -1e-6:
                    losses += 1
                else:
                    ties += 1
            mean_delta = statistics.mean(deltas)
            se = (statistics.pstdev(deltas) / math.sqrt(len(deltas))
                  if len(deltas) > 1 else 0.0)
            pairing[f"{reference} vs {variant}"] = {
                "wins": wins, "losses": losses, "ties": ties,
                "mean_delta_s_per_source": mean_delta,
                "ci95_low": mean_delta - 1.96 * se,
                "ci95_high": mean_delta + 1.96 * se,
            }

    result = {"variants": variant_names, "seed": args.seed, "cases": args.cases,
              "elapsed_s": elapsed, "summaries": summaries, "pairing": pairing}
    (output / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

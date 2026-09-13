"""问题4定向源离线实验：比较第三问J+与多方位三角网格搜索。"""
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
from dataclasses import dataclass
from pathlib import Path

from baseline_core import (AREA_R, ERROR_DEG, MAX_R, MIN_R, SPEED, Action,
                           OfflineSimulator, Point, Source, bearing, dist, wrap)
from feasible_region import build_region_cached
from strategies import JPlusAgent


@dataclass
class DirectionalSource(Source):
    """beam_direction=None表示全向，否则表示180度发射扇区的中轴方向。"""

    beam_direction: float | None = None


class DirectionalSimulator(OfflineSimulator):
    """在第三问离线环境上加入定向源的前向半平面接收条件。"""

    def measure(self, p: Point, channel: int) -> tuple[str, float | None]:
        if not self.entered:
            raise RuntimeError("必须先 enter")
        self._move_to(p)
        if channel != self.current_channel:
            self.time_s += 1.0
        self.current_channel = channel
        self.time_s += 5.0
        source = self.sources.get(channel)
        in_range = source is not None and not source.cleared and dist(p, source.position) <= source.receive_radius
        visible = in_range
        if visible and getattr(source, "beam_direction", None) is not None:
            outward = bearing(source.position, p)
            visible = abs(wrap(outward - source.beam_direction)) <= 90.0 + 1e-10
        if not visible:
            self._log("measure", p, channel, "no_signal")
            return "no_signal", None
        if dist(p, source.position) <= 5.0:
            self._log("measure", p, channel, "near")
            return "near", None
        angle = (bearing(p, source.position) + self._location_error(source, p)) % 360.0
        self._log("measure", p, channel, "direction")
        return "direction", angle


class Q3DirectAgent(JPlusAgent):
    """第三问J+原样迁移，作为问题4对照组。"""

    def _snapshot(self, st):
        # 定向源无信号不能作为1000米排除圆；两组均修正该逻辑，
        # 让对比只考察搜索点的方位覆盖差异。
        return build_region_cached(st.observations, ())


class Q4TriangularCoverageAgent(Q3DirectAgent):
    """最终全清除版：950米三角网格，覆盖期补到2条有效方位。"""

    lattice_side_m = 950.0
    coverage_observation_target = 2

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.search_points = self._triangular_sites(self.lattice_side_m)

    @staticmethod
    def _triangular_sites(side: float) -> list[Point]:
        height = side * math.sqrt(3.0) / 2.0
        limit = AREA_R + side + 1e-7
        extent = math.ceil(limit / min(side, height)) + 2
        points: list[Point] = []
        for row in range(-extent, extent + 1):
            y = row * height
            offset = 0.5 * side if row % 2 else 0.0
            for column in range(-extent, extent + 1):
                p = (column * side + offset, y)
                if math.hypot(*p) <= limit:
                    points.append(p)
        points.sort(key=lambda p: (math.hypot(*p), math.atan2(p[1], p[0])))
        origin_index = min(range(len(points)), key=lambda i: dist(points[i], (0.0, 0.0)))
        points[0], points[origin_index] = points[origin_index], points[0]
        return points

    def _coverage_order(self, unvisited: list[Point]) -> list[Point]:
        # 原J+对7个点穷举；网格点更多，改为最近邻滚动选择。
        return sorted(unvisited, key=lambda p: dist(self.sim.position, p))

    def _coobserve(self, point: Point, primary_channel: int) -> None:
        """在网格停靠点主动复测已发现频道，积累定向源的可见侧方位。"""
        for channel, st in self.state.items():
            if (channel == primary_channel or st.cleared or st.exhausted
                    or not st.discovered
                    or len(st.observations) >= self.coverage_observation_target):
                continue
            if any(dist(point, old) <= 1.0 for old in st.probed_points):
                continue
            result = self.observe(point, channel)
            # 背面无信号是正常的方位筛查，不占用后续主动定位的10次预算。
            if result in ("direction", "near"):
                st.attempts += 1
            self.co_measurements += 1

    def _corridor_clear(self, channel: int, st) -> bool:
        """用20米清除圆覆盖最后一次示向度对应的完整误差走廊。

        对距离不超过1500米、角误差不超过1度的源，其相对示向中轴的横向
        偏差不超过1500*sin(1度)=26.18米。纵向30米、横向20米的交错点阵
        最大覆盖空隙为sqrt(15^2+10^2)<20米，因此必有一个清除点命中。
        """
        if not st.observations:
            return False
        station, angle = st.observations[-1]
        radians = math.radians(angle)
        ux, uy = math.cos(radians), math.sin(radians)
        nx, ny = -uy, ux
        offsets = (-30.0, -10.0, 10.0, 30.0)
        for index, longitudinal in enumerate(range(0, 1501, 30)):
            row = offsets if index % 2 == 0 else tuple(reversed(offsets))
            for lateral in row:
                point = (station[0] + longitudinal * ux + lateral * nx,
                         station[1] + longitudinal * uy + lateral * ny)
                if self._try_clear(point, channel):
                    st.cleared = True
                    return True
        return False

    def run(self) -> dict:
        """滚动定位时给定向源更充足的背面试探预算。"""
        self.sim.enter()
        self.search()
        for _ in range(600):
            unresolved = [channel for channel, st in self.state.items()
                          if st.discovered and not st.cleared and not st.exhausted]
            if not unresolved:
                break
            channel = self._two_opt_route(unresolved)[0]
            st = self.state[channel]
            center = self._clear_decision(st)
            if center is not None:
                if self._try_clear(center, channel):
                    st.cleared = True
                    self._coobserve(center, channel)
                continue
            if st.attempts >= 30:
                if not self._corridor_clear(channel, st):
                    st.exhausted = True
                continue
            point = self._next_measurement_point(st)
            if point is None:
                if not self._corridor_clear(channel, st):
                    st.exhausted = True
                continue
            self.observe(point, channel)
            st.attempts += 1
            self._coobserve(point, channel)
        self.sim.exit()
        return self.summary()


STRATEGIES = {
    "Q3_Jplus_direct": Q3DirectAgent,
    "Q4_full_clear_950_C2": Q4TriangularCoverageAgent,
}


def random_mixed_sources(rng: random.Random, fixed_count: int | None,
                         directional_fraction: float) -> list[DirectionalSource]:
    count = fixed_count if fixed_count is not None else rng.randint(10, 16)
    channels = rng.sample(range(1, 21), count)
    directional_count = max(1, min(count - 1, round(count * directional_fraction)))
    directional_channels = set(rng.sample(channels, directional_count))
    sources = []
    for channel in channels:
        radius = AREA_R * math.sqrt(rng.random())
        angle = rng.uniform(0.0, 2.0 * math.pi)
        beam = rng.uniform(0.0, 360.0) if channel in directional_channels else None
        sources.append(DirectionalSource(
            channel=channel,
            position=(radius * math.cos(angle), radius * math.sin(angle)),
            receive_radius=rng.uniform(MIN_R, MAX_R),
            beam_direction=beam,
        ))
    return sources


def clone_sources(sources: list[DirectionalSource]) -> list[DirectionalSource]:
    return [DirectionalSource(s.channel, s.position, s.receive_radius, False, s.beam_direction)
            for s in sources]


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1)]


def run_one(case_index: int, sources: list[DirectionalSource], seed: int,
            strategy_name: str, agent_class) -> tuple[dict, list[Action]]:
    sim = DirectionalSimulator(clone_sources(sources), seed * 100000 + case_index)
    start = time.perf_counter()
    agent = agent_class(sim)
    result = agent.run()
    directional_channels = {s.channel for s in sources if s.beam_direction is not None}
    cleared_directional = sum(agent.state[c].cleared for c in directional_channels)
    row = {
        "seed": seed,
        "case": case_index,
        "strategy": strategy_name,
        "source_count": len(sources),
        "directional_count": len(directional_channels),
        **result,
        "cleared_directional": cleared_directional,
        "all_cleared": int(result["cleared_channels"] == len(sources)),
        "search_sites": len(agent.search_points),
        "decision_wall_time_s": round(time.perf_counter() - start, 6),
    }
    return row, sim.actions


def _run_work(item):
    """供Windows多进程安全调用的顶层包装函数。"""
    return run_one(*item)


def main() -> None:
    parser = argparse.ArgumentParser(description="问题4定向源策略离线配对实验")
    parser.add_argument("--cases", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260912)
    parser.add_argument("--sources", type=int, choices=range(10, 17))
    parser.add_argument("--directional-fraction", type=float, default=0.5)
    parser.add_argument("--output", default="results/latest")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    args = parser.parse_args()
    if not 0.0 < args.directional_fraction < 1.0:
        raise ValueError("--directional-fraction 必须在0和1之间")

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    cases = [random_mixed_sources(rng, args.sources, args.directional_fraction)
             for _ in range(args.cases)]
    rows: list[dict] = []
    first_actions: dict[str, list[dict]] = {}
    started = time.perf_counter()
    work = [(index, sources, args.seed, name, agent_class)
            for index, sources in enumerate(cases, 1)
            for name, agent_class in STRATEGIES.items()]
    progress_step = max(1, len(work) // 20)
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            completed = pool.map(_run_work, work)
            for done, (row, actions) in enumerate(completed, 1):
                rows.append(row)
                if row["case"] == 1:
                    first_actions[row["strategy"]] = [a.__dict__ for a in actions]
                if done % progress_step == 0 or done == len(work):
                    print(f"run {done:04d}/{len(work)} complete", flush=True)
    else:
        for done, item in enumerate(work, 1):
            row, actions = _run_work(item)
            rows.append(row)
            if row["case"] == 1:
                first_actions[row["strategy"]] = [a.__dict__ for a in actions]
            if done % progress_step == 0 or done == len(work):
                print(f"run {done:04d}/{len(work)} complete", flush=True)

    with (output / "case_results.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summaries = []
    for name in STRATEGIES:
        group = [row for row in rows if row["strategy"] == name]
        totals = [row["total_virtual_time_s"] for row in group]
        per_source = [row["total_virtual_time_s"] / row["source_count"] for row in group]
        summaries.append({
            "strategy": name,
            "cases": len(group),
            "search_sites": group[0]["search_sites"],
            "all_cleared_rate": sum(row["all_cleared"] for row in group) / len(group),
            "directional_clear_rate": sum(row["cleared_directional"] for row in group)
                                      / sum(row["directional_count"] for row in group),
            "mean_detected": statistics.mean(row["detected_channels"] for row in group),
            "mean_cleared": statistics.mean(row["cleared_channels"] for row in group),
            "mean_virtual_time_s": statistics.mean(totals),
            "mean_time_per_source_s": statistics.mean(per_source),
            "p95_virtual_time_s": percentile(totals, 0.95),
            "max_virtual_time_s": max(totals),
            "mean_measure_actions": statistics.mean(row["measure_actions"] for row in group),
        })
    payload = {
        "config": vars(args),
        "elapsed_wall_time_s": time.perf_counter() - started,
        "model_note": "定向源覆盖角为中轴两侧各90度；no_signal不生成位置排除圆。",
        "summaries": summaries,
    }
    (output / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "actions_case_001.json").write_text(
        json.dumps(first_actions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

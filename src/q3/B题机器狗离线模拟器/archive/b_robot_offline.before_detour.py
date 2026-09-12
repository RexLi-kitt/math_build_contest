"""B题全向干扰源离线演练。

只使用标准库。策略层不访问环境中保存的真实源位置；真实值仅用于环境响应和测试统计。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

AREA_R = 1800.0
MIN_R, MAX_R = 1000.0, 1500.0
SPEED = 5.0
ERROR_DEG = 1.0
# 七点搜索环半径:环点加原点对目标区域的最坏覆盖距离 951.6 m
# (圆域边界上相邻环点之间的中点),小于 1000 m 的有效接收半径下界。
SEARCH_RING_R = 1250.0

Point = tuple[float, float]


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def bearing(a: Point, b: Point) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360.0


def wrap(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def add(p: Point, length: float, angle_deg: float) -> Point:
    r = math.radians(angle_deg)
    return (p[0] + length * math.cos(r), p[1] + length * math.sin(r))


@dataclass
class Source:
    channel: int
    position: Point
    receive_radius: float
    cleared: bool = False


@dataclass
class Action:
    kind: str
    position: Optional[Point]
    channel: Optional[int]
    result: str
    virtual_time_s: float


class OfflineSimulator:
    """按题意实现 /enter、/measure、/clear、/exit 的核心行为。"""

    def __init__(self, sources: list[Source], seed: int):
        self.sources = {s.channel: s for s in sources}
        self.seed = seed
        self.position: Point = (0.0, 0.0)
        self.current_channel = 1
        self.time_s = 0.0
        self.actions: list[Action] = []
        self.entered = False

    def enter(self) -> None:
        self.entered = True
        self._log("enter", None, None, "accepted")

    def _move_to(self, p: Point) -> float:
        step = dist(self.position, p) / SPEED
        self.time_s += step
        self.position = p
        return step

    def _location_error(self, source: Source, p: Point) -> float:
        # 同一地点对同一频道重复测量保持同一误差；不同地点呈统计波动。
        token = f"{self.seed}|{source.channel}|{p[0]:.3f}|{p[1]:.3f}".encode()
        value = int.from_bytes(hashlib.sha256(token).digest()[:8], "big")
        return (value / (2**64 - 1)) * 2 * ERROR_DEG - ERROR_DEG

    def _log(self, kind: str, p: Optional[Point], channel: Optional[int], result: str) -> None:
        self.actions.append(Action(kind, p, channel, result, round(self.time_s, 6)))

    def measure(self, p: Point, channel: int) -> tuple[str, Optional[float]]:
        if not self.entered:
            raise RuntimeError("必须先 enter")
        self._move_to(p)
        if channel != self.current_channel:
            self.time_s += 1.0
        self.current_channel = channel
        self.time_s += 5.0
        source = self.sources.get(channel)
        if source is None or source.cleared or dist(p, source.position) > source.receive_radius:
            self._log("measure", p, channel, "no_signal")
            return "no_signal", None
        if dist(p, source.position) <= 5.0:
            self._log("measure", p, channel, "near")
            return "near", None
        angle = (bearing(p, source.position) + self._location_error(source, p)) % 360.0
        self._log("measure", p, channel, "direction")
        return "direction", angle

    def clear(self, p: Point, channel: int) -> bool:
        self._move_to(p)
        source = self.sources.get(channel)
        if source is not None and not source.cleared and dist(p, source.position) <= 20.0:
            source.cleared = True
            self.time_s += 5.0
            self._log("clear", p, channel, "success")
            return True
        self.time_s += 3.0
        self._log("clear", p, channel, "no_target_in_range")
        return False

    def exit(self) -> None:
        self._log("exit", None, None, "user_exit")


@dataclass
class ChannelState:
    observations: list[tuple[Point, float]] = field(default_factory=list)
    probed_points: list[Point] = field(default_factory=list)
    no_signal_points: list[Point] = field(default_factory=list)
    discovered: bool = False
    cleared: bool = False
    exhausted: bool = False
    attempts: int = 0


class SevenPointAgent:
    """七点覆盖搜索 + 停靠点补测 + 两方位交会清除 + 顺路清除的基线策略。

    注意:主动选点评分并非项目的问题2正式模型,只用于使本离线环境可独立调试。
    """

    def __init__(self, sim: OfflineSimulator, verbose: bool = False):
        self.sim = sim
        self.verbose = verbose
        self.state = {c: ChannelState() for c in range(1, 21)}
        self.search_points = [(0.0, 0.0)] + [
            add((0.0, 0.0), SEARCH_RING_R, 60.0 * k) for k in range(6)
        ]

    def say(self, message: str) -> None:
        if self.verbose:
            print(message)

    def observe(self, p: Point, channel: int) -> str:
        result, angle = self.sim.measure(p, channel)
        st = self.state[channel]
        st.probed_points.append(p)
        if result == "direction":
            st.discovered = True
            st.observations.append((p, angle if angle is not None else 0.0))
        elif result == "near":
            st.discovered = True
            st.cleared = self.sim.clear(p, channel)
        elif result == "no_signal":
            st.no_signal_points.append(p)
        return result

    @staticmethod
    def _logdet2(a11: float, a12: float, a22: float) -> float:
        determinant = a11 * a22 - a12 * a12
        return math.log(max(determinant, 1e-30))

    def _belief_samples(self, st: ChannelState) -> list[Point]:
        """不读取真值的离散信念样本，用于预计下一观测的信息增益。"""
        if len(st.observations) == 1:
            p, angle = st.observations[0]
            samples = [add(p, radius, angle + delta)
                       for radius in (100.0, 250.0, 400.0, 550.0, 700.0, 850.0, 1000.0, 1150.0, 1300.0, 1450.0)
                       for delta in (-ERROR_DEG, 0.0, ERROR_DEG)]
            filtered = [g for g in samples if all(dist(g, q) > MIN_R for q in st.no_signal_points)]
            return filtered or samples
        estimate = self._least_squares_intersection(st.observations)
        # 两条近乎平行或反向平行方位线会把最小二乘交点推到区域之外；
        # 此时不能围绕伪交点生成候选，而要退回首次方位的保守候选集。
        if estimate is None or math.hypot(*estimate) > AREA_R * 1.2:
            return self._belief_samples(ChannelState(observations=[st.observations[0]]))
        # 多站交会后，在估计位置周边保留有限不确定性样本。
        return [add(estimate, radius, angle) for radius in (0.0, 20.0, 50.0, 90.0)
                for angle in (0.0,) if radius == 0.0] + [
                add(estimate, radius, angle)
                for radius in (20.0, 50.0, 90.0) for angle in range(0, 360, 45)
        ]

    def _degenerate_recovery_point(self, st: ChannelState) -> Optional[Point]:
        """近平行方位线的确定性恢复。

        首测成功后，沿示向度前进 300 m，再横向移动 600 m，均保持在
        1000–1500 m 接收半径约束下的保守可接收范围内；其作用是主动制造
        足够基线，而不是围绕错误的远处交点反复试探。
        """
        if len(st.observations) < 2:
            return None
        directions = [angle for _, angle in st.observations]
        max_sine = max(abs(math.sin(math.radians(wrap(a - b)))) for a in directions for b in directions)
        if max_sine >= math.sin(math.radians(15.0)):
            return None
        p0, angle0 = st.observations[0]
        forward = add(p0, 300.0, angle0)
        lateral = add(forward, 600.0, angle0 + 90.0)
        for point in (forward, lateral):
            if all(dist(point, old) > 1.0 for old in st.probed_points):
                return point
        return None

    def _fim(self, stations: list[Point], target: Point) -> tuple[float, float, float]:
        """方位观测的 Fisher 信息矩阵，加入极弱先验以处理单方位奇异性。"""
        prior = 1.0 / (AREA_R * AREA_R)
        a11, a12, a22 = prior, 0.0, prior
        for p in stations:
            r = max(dist(p, target), 1.0)
            phi = math.radians(bearing(p, target))
            nx, ny = -math.sin(phi) / r, math.cos(phi) / r
            a11 += nx * nx
            a12 += nx * ny
            a22 += ny * ny
        return a11, a12, a22

    def _information_rate(self, st: ChannelState, candidate: Point, move_time_s: float) -> float:
        """D-opt 信息增益 / 预计动作时间。

        对每个信念样本，若候选点在 1000 m 保守接收圈内，计算加入该方位后
        log det(FIM) 的增加量；否则该样本的增益为零。分母包含移动、检测和
        可能的频道切换时间，因而可与“继续赶路”直接比较。
        """
        samples = self._belief_samples(st)
        stations = [p for p, _ in st.observations]
        gain = 0.0
        for target in samples:
            before = self._fim(stations, target)
            before_logdet = self._logdet2(*before)
            if dist(candidate, target) <= MIN_R:
                after_logdet = self._logdet2(*self._fim(stations + [candidate], target))
                gain += max(0.0, after_logdet - before_logdet)
        # 当前频道未知时以 1 秒保守计入；停靠点额外观测也保留该成本。
        return (gain / len(samples)) / max(move_time_s + 6.0, 1e-9)

    def search(self) -> None:
        # 未发现频道完整扫描以维持覆盖保证；已发现频道只要方位不足 3 条
        # 就在当前停靠点补测：停车补一条只花 6 秒，留到清除阶段专程补测
        # 要花上百秒移动。
        for point in self.search_points:
            for channel, st in self.state.items():
                if st.cleared:
                    continue
                if not st.discovered or len(st.observations) < 3:
                    self.observe(point, channel)
            self._opportunistic_clear()
            self.say(f"搜索点 {point!r} 完成，虚拟时间 {self.sim.time_s:.1f}s")

            # 题设总数最多为 16；已发现 16 个不同频道后，剩余频道不可能再有源。
            if sum(st.discovered for st in self.state.values()) >= 16:
                break

    @staticmethod
    def _least_squares_intersection(observations: list[tuple[Point, float]]) -> Optional[Point]:
        if len(observations) < 2:
            return None
        # 方位线的法向式：(-sin θ, cos θ) · x = (-sin θ, cos θ) · p
        a11 = a12 = a22 = b1 = b2 = 0.0
        for p, angle in observations:
            r = math.radians(angle)
            nx, ny = -math.sin(r), math.cos(r)
            rhs = nx * p[0] + ny * p[1]
            a11 += nx * nx
            a12 += nx * ny
            a22 += ny * ny
            b1 += nx * rhs
            b2 += ny * rhs
        det = a11 * a22 - a12 * a12
        if abs(det) < 1e-8:
            return None
        return ((b1 * a22 - a12 * b2) / det, (a11 * b2 - a12 * b1) / det)

    def _first_observation_candidates(self, st: ChannelState) -> list[Point]:
        """根据首次方位生成候选点；最终选择由 D-opt 信息率完成。"""
        p, angle = st.observations[0]
        samples = [add(p, r, angle + delta) for r in (200, 500, 800, 1100, 1400)
                   for delta in (-1.0, 0.0, 1.0)]
        candidates: list[Point] = []
        # 首次观测可能位于有效接收圆边缘，先把“朝测得方向小步推进”
        # 作为候选，避免只追求 90° 基线而一下走出接收范围。
        for move in (150.0, 300.0, 500.0, 750.0):
            for offset in (0.0, -45.0, 45.0, -90.0, 90.0):
                q = add(p, move, angle + offset)
                if math.hypot(*q) > 2600:
                    continue
                candidates.append(q)
        return candidates

    def _next_measurement_point(self, st: ChannelState) -> Optional[Point]:
        recovery = self._degenerate_recovery_point(st)
        if recovery is not None:
            return recovery
        if len(st.observations) == 1:
            candidates = self._first_observation_candidates(st)
        else:
            estimate = self._least_squares_intersection(st.observations)
            if estimate is None or math.hypot(*estimate) > AREA_R * 1.2:
                candidates = self._first_observation_candidates(st)
            else:
                candidates = [add(estimate, radius, a) for radius in (180.0, 300.0, 450.0)
                              for a in range(0, 360, 30)]
        best, best_score = None, -float("inf")
        for q in candidates:
            if math.hypot(*q) > 2600:
                continue
            if any(dist(q, old) <= 1.0 for old in st.probed_points):
                continue
            score = self._information_rate(st, q, dist(self.sim.position, q) / SPEED)
            if score > best_score:
                best, best_score = q, score
        return best

    def _clear_neighborhood(self, estimate: Point, channel: int,
                            include_center: bool = True) -> bool:
        # 小型十字兜底替代旧版 3×3 网格；include_center=False 用于中心点
        # 刚清除失败后的重试，省去一次必败的重复调用。
        offsets = ([(0.0, 0.0)] if include_center else []) + [
            (15.0, 0.0), (-15.0, 0.0), (0.0, 15.0), (0.0, -15.0)]
        for dx, dy in offsets:
            if self.sim.clear((estimate[0] + dx, estimate[1] + dy), channel):
                return True
        return False

    @staticmethod
    def _good_crossing_angle(observations: list[tuple[Point, float]]) -> bool:
        """任意两条方位线的夹角（取锐角）是否不小于约 30°。"""
        angles = [a for _, a in observations]
        return any(
            abs(math.sin(math.radians(angles[i] - angles[j]))) >= 0.5
            for i in range(len(angles)) for j in range(i + 1, len(angles))
        )

    def _opportunistic_clear(self) -> None:
        """搜索途中顺路清除已交会且离当前搜索点足够近的目标。

        只处理已有两条良好交角方位、估计点在 500 m 内的频道；失败不标记
        状态，下一个搜索点会带着新补测的方位以更准的估计重试。
        """
        for channel, st in self.state.items():
            if st.cleared or not st.discovered:
                continue
            if len(st.observations) < 2 or not self._good_crossing_angle(st.observations):
                continue
            estimate = self._least_squares_intersection(st.observations)
            if estimate is None or math.hypot(*estimate) > AREA_R * 1.2:
                continue
            if dist(self.sim.position, estimate) > 500.0:
                continue
            if (self.sim.clear(estimate, channel)
                    or self._clear_neighborhood(estimate, channel, include_center=False)):
                st.cleared = True

    def localize_and_clear(self, channel: int) -> bool:
        st = self.state[channel]
        if st.cleared or not st.discovered:
            return st.cleared
        # 搜索阶段收集到的方位优先用于直接清除；两条交角不小于 30° 的方位
        # 线交会误差约 20-35 m，配合十字兜底与 20 m 光学定位半径通常够用，
        # 清除失败仅损失 3 秒，却经常省掉第三条方位的专程绕路。
        # 主动补测的上限用于防止循环失控。
        for _ in range(10):
            estimate = self._least_squares_intersection(st.observations)
            ready = len(st.observations) >= 3 or (
                len(st.observations) == 2 and self._good_crossing_angle(st.observations))
            if ready and estimate is not None and math.hypot(*estimate) <= AREA_R * 1.2:
                if (self.sim.clear(estimate, channel)
                        or self._clear_neighborhood(estimate, channel, include_center=False)):
                    st.cleared = True
                    return True
                # 清除失败说明估计偏差超过 20 m；继续补方位比扩大网格更有效。
            q = self._next_measurement_point(st)
            if q is None:
                break
            result = self.observe(q, channel)
            st.attempts += 1
            if st.cleared:
                return True
            # 已有两条线而本次无信号时，下一轮仍以历史交会估计重新选点。
            if result == "near":
                return st.cleared
        estimate = self._least_squares_intersection(st.observations)
        if estimate is not None:
            st.cleared = self._clear_neighborhood(estimate, channel)
        if not st.cleared:
            st.exhausted = True
        return st.cleared

    def _target_anchor(self, st: ChannelState) -> Point:
        """目标调度用的保守代表位置；仅作访问顺序估计，不作为清除位置。"""
        estimate = self._least_squares_intersection(st.observations)
        if estimate is not None and math.hypot(*estimate) <= AREA_R * 1.2:
            return estimate
        p, angle = st.observations[0]
        # 单方位时取射线中部，避免按频道编号造成跨区域折返。
        candidate = add(p, 850.0, angle)
        radius = math.hypot(*candidate)
        return candidate if radius <= AREA_R else (candidate[0] * AREA_R / radius, candidate[1] * AREA_R / radius)

    def _two_opt_route(self, channels: list[int]) -> list[int]:
        """从当前位置出发的开放路径：最近邻初解，再用 2-opt 与 Or-opt 交替局部优化。

        2-opt 只会反转连续段，表达不了"把被甩到路线末尾的点搬回其所在簇"这类
        纯插入移动；Or-opt 补足该邻域：把长度 1-3 的段正向或反向插入其他位置。
        """
        if len(channels) < 3:
            return channels
        anchors = {c: self._target_anchor(self.state[c]) for c in channels}
        remaining = set(channels)
        route: list[int] = []
        current = self.sim.position
        while remaining:
            nxt = min(remaining, key=lambda c: dist(current, anchors[c]))
            route.append(nxt)
            current = anchors[nxt]
            remaining.remove(nxt)

        start = self.sim.position

        def route_cost(order: list[int]) -> float:
            points = [start] + [anchors[c] for c in order]
            return sum(dist(a, b) for a, b in zip(points, points[1:]))

        improved = True
        while improved:
            improved = False
            # 2-opt：反转 route[i:j]。
            old_cost = route_cost(route)
            for i in range(len(route) - 1):
                for j in range(i + 2, len(route) + 1):
                    candidate = route[:i] + list(reversed(route[i:j])) + route[j:]
                    if route_cost(candidate) + 1e-6 < old_cost:
                        route = candidate
                        improved = True
                        break
                if improved:
                    break
            if improved:
                continue
            # Or-opt：把长度 1-3 的段（正向或反向）搬到其余部分的任意位置。
            old_cost = route_cost(route)
            n = len(route)
            for seg_len in (1, 2, 3):
                for i in range(n - seg_len + 1):
                    segment = route[i:i + seg_len]
                    rest = route[:i] + route[i + seg_len:]
                    for j in range(len(rest) + 1):
                        for seg in (segment, segment[::-1]):
                            candidate = rest[:j] + seg + rest[j:]
                            if route_cost(candidate) + 1e-6 < old_cost:
                                route = candidate
                                improved = True
                                break
                        if improved:
                            break
                    if improved:
                        break
                if improved:
                    break
        return route

    def run(self) -> dict:
        self.sim.enter()
        self.search()
        # 每完成一个目标，用 2-opt/Or-opt 重排剩余目标的访问顺序，避免按
        # 频道编号顺序或交叉折返在目标圆域两端反复移动。
        while True:
            targets = [c for c, st in self.state.items() if st.discovered and not st.cleared and not st.exhausted]
            if not targets:
                break
            channel = self._two_opt_route(targets)[0]
            self.localize_and_clear(channel)
        self.sim.exit()
        return self.summary()

    def summary(self) -> dict:
        cleared = sum(s.cleared for s in self.state.values())
        detected = sum(s.discovered for s in self.state.values())
        counts = {k: 0 for k in ("measure", "clear")}
        for a in self.sim.actions:
            if a.kind in counts:
                counts[a.kind] += 1
        return {
            "detected_channels": detected,
            "cleared_channels": cleared,
            "total_virtual_time_s": round(self.sim.time_s, 3),
            "measure_actions": counts["measure"],
            "clear_actions": counts["clear"],
        }


def random_sources(rng: random.Random, fixed_count: Optional[int]) -> list[Source]:
    count = fixed_count if fixed_count is not None else rng.randint(10, 16)
    channels = rng.sample(range(1, 21), count)
    result = []
    for channel in channels:
        # 面积均匀：半径取 AREA_R * sqrt(U)，而不是半径均匀。
        radius = AREA_R * math.sqrt(rng.random())
        angle = rng.uniform(0.0, 2 * math.pi)
        result.append(Source(channel, (radius * math.cos(angle), radius * math.sin(angle)),
                             rng.uniform(MIN_R, MAX_R)))
    return result


def write_outputs(out: Path, rows: list[dict], actions: list[Action]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "case_results.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    totals = [r["total_virtual_time_s"] for r in rows]
    summary = {
        "cases": len(rows),
        "all_cleared_rate": sum(r["cleared_channels"] == r["source_count"] for r in rows) / len(rows),
        "mean_virtual_time_s": statistics.mean(totals),
        "median_virtual_time_s": statistics.median(totals),
        "max_virtual_time_s": max(totals),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "actions_case_001.json").write_text(
        json.dumps([asdict(a) for a in actions], ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="B题全向干扰源离线演练")
    parser.add_argument("--cases", type=int, default=10, help="随机案例数")
    parser.add_argument("--seed", type=int, default=2026, help="随机种子")
    parser.add_argument("--sources", type=int, choices=range(10, 17), help="固定干扰源数")
    parser.add_argument("--output", default="results", help="结果目录")
    parser.add_argument("--verbose", action="store_true", help="打印搜索过程")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    rows, first_actions = [], []
    for i in range(1, args.cases + 1):
        sources = random_sources(rng, args.sources)
        sim = OfflineSimulator(sources, seed=args.seed * 100000 + i)
        summary = SevenPointAgent(sim, verbose=args.verbose and i == 1).run()
        row = {"case": i, "source_count": len(sources), **summary}
        rows.append(row)
        if i == 1:
            first_actions = sim.actions
        print(f"案例 {i:03d}: 清除 {summary['cleared_channels']}/{len(sources)}，"
              f"虚拟时间 {summary['total_virtual_time_s']:.1f}s")
    out = Path(args.output)
    write_outputs(out, rows, first_actions)
    rate = sum(r["cleared_channels"] == r["source_count"] for r in rows) / len(rows)
    print(f"\n全清除率: {rate:.1%}；结果已写入: {out.resolve()}")


if __name__ == "__main__":
    main()

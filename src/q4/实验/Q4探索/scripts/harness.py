"""Q4 门控探索：统一离线评测外壳。

原则：
- 只复用离线模拟器与既有 B / B+ / C / C+ / D1 代理，不修改任何原模型文件；
- 所有策略在同一批案例上配对运行，案例生成器与 C+ 出货验证批次保持一致；
- 指标口径对齐 Q3 报告（全清除率、均值、P95、CVaR90、搜索移动、搜索后移动、
  检测、清除、切换、程序时间）。
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True  # 不向只读模型目录写 __pycache__

EXP = Path(r"C:\Users\李\Desktop\第四问定向源实验")
MODELS = Path(r"C:\Users\李\Desktop\Q4保底基线")
CPLUS_DIR = MODELS / "C+模型"
for _p in (EXP, CPLUS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from q4_experiment import (DirectionalSimulator, clone_sources,  # noqa: E402
                           percentile, random_mixed_sources)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CPlusAgent = _load("q4x_cplus_base", CPLUS_DIR / "cplus_gate_agent.py").CPlusAgent


class OriginLogAgent(_CPlusAgent):
    """与 C+ 逐条同构，只额外记录原点门控特征与停靠点轨迹。"""

    def search(self) -> None:
        origin = (0.0, 0.0)
        for channel, state in self.state.items():
            if not state.discovered:
                self.observe(origin, channel)
        self._coobserve(origin, -1)
        self.origin_discoveries = sum(state.discovered for state in self.state.values())
        self.origin_features = self._origin_features()
        self.search_trace = []

        selected = ("B" if self.origin_discoveries <= self.discovery_threshold
                    else "C")
        self.selected_search_order = selected
        self.search_points = list(self._routes()[selected])

        remaining = list(self.search_points[1:])
        while remaining and sum(state.discovered for state in self.state.values()) < 16:
            point = remaining.pop(0)
            for channel, state in self.state.items():
                if not state.discovered:
                    self.observe(point, channel)
            self._coobserve(point, -1)
            self.search_trace.append(
                (point, round(self.sim.time_s, 3),
                 sum(s.discovered for s in self.state.values())))
            following = remaining[0] if remaining else None
            self._opportunistic_clear(following)
            self.say(f"C+ {selected}路线：原点发现{self.origin_discoveries}个，"
                     f"当前共发现{sum(s.discovered for s in self.state.values())}个")
        self.search_end_time_s = self.sim.time_s

    def _origin_features(self) -> dict:
        bearings = []
        channels = []
        for channel, state in self.state.items():
            if not state.discovered:
                continue
            for point, angle in state.observations:
                if math.hypot(*point) <= 1e-9:
                    bearings.append(angle % 360.0)
                    channels.append(channel)
        bearings.sort()
        channels = sorted(set(channels))
        gaps = [b - a for a, b in zip(bearings, bearings[1:])]
        if len(bearings) >= 2:
            gaps.append(bearings[0] + 360.0 - bearings[-1])
        # 频道号与源位置无关，因此原点已发现集合是真实源集合的均匀随机子集，
        # 可用德军坦克估计量推出源总数上界，进而得到"原点可见比例"。
        total_hat = 16.0
        if channels:
            count = len(channels)
            total_hat = min(16.0, max(10.0, channels[-1] * (count + 1) / count - 1.0))
        return {
            "n_bearings": len(bearings),
            "max_gap_deg": round(max(gaps), 2) if gaps else 360.0,
            "bearings": [round(b, 2) for b in bearings],
            "channels": channels,
            "total_hat": round(total_hat, 2),
            "visible_fraction": round(len(channels) / total_hat, 4) if channels else 0.0,
        }


_STRATEGIES: dict[str, type] = {}


def _make_trace_agent(base):
    """包装原代理，只记录观测轨迹；行为逐条保持一致。"""

    class _Logged(base):
        def __init__(self, sim, verbose: bool = False):
            super().__init__(sim, verbose)
            self.trace = []

        def observe(self, p, channel):
            before = sum(state.discovered for state in self.state.values())
            result = super().observe(p, channel)
            after = sum(state.discovered for state in self.state.values())
            self.trace.append((round(p[0], 3), round(p[1], 3), channel, result,
                               round(self.sim.time_s, 3), before, after))
            return result

    _Logged.__name__ = f"Logged{base.__name__}"
    return _Logged


def _compress_trace(agent, search_end_s):
    """把观测轨迹压缩成"每停靠点一行"，控制体积。"""
    trace = getattr(agent, "trace", None)
    if not trace:
        return None
    sites = {(round(p[0], 3), round(p[1], 3)) for p in agent.search_points}
    grouped: list = []
    for x, y, _channel, _result, time_s, before, after in trace:
        if time_s > search_end_s + 1e-6 or (x, y) not in sites:
            continue
        if grouped and grouped[-1][0] == (x, y):
            previous = grouped[-1]
            grouped[-1] = ((x, y), time_s, max(previous[2], after),
                           previous[3] + 1, previous[4] + (after - before))
        else:
            grouped.append(((x, y), time_s, after, 1, after - before))
    return [[list(key), time_s, discoveries, observations, new]
            for key, time_s, discoveries, observations, new in grouped]


def strategy_class(name: str) -> type:
    if name in _STRATEGIES:
        return _STRATEGIES[name]
    if name == "B":
        cls = _load("q4x_b", MODELS / "B模型" / "cert_route_agent.py").CertRouteAgent
    elif name == "Bplus":
        cls = _load("q4x_bplus", MODELS / "B+模型" / "cert_route_agent.py").CertRouteAgent
    elif name == "C":
        cls = _load("q4x_c", MODELS / "C模型" / "cert_route_agent.py").CertRouteAgent
    elif name == "D1":
        cls = _load("q4x_d1", MODELS / "D模型" / "dynamic_order_agent.py").DynamicDiscoveryOrderAgent
    elif name == "Cplus":
        cls = _CPlusAgent
    elif name == "CplusLog":
        cls = OriginLogAgent
    elif name == "BLog":
        _STRATEGIES["BLog"] = _make_trace_agent(_load(
            "q4x_b", MODELS / "B模型" / "cert_route_agent.py").CertRouteAgent)
        return _STRATEGIES["BLog"]
    elif name == "CLog":
        _STRATEGIES["CLog"] = _make_trace_agent(_load(
            "q4x_c", MODELS / "C模型" / "cert_route_agent.py").CertRouteAgent)
        return _STRATEGIES["CLog"]
    else:
        raise KeyError(f"未知策略 {name}")
    _STRATEGIES[name] = cls
    return cls


# ---------------------------------------------------------------- 案例生成器


def normal_cases(count: int, seed: int) -> list:
    rng = random.Random(seed)
    return [random_mixed_sources(rng, None, 0.5) for _ in range(count)]


def min_radius_cases(count: int, seed: int) -> list:
    cases = normal_cases(count, seed)
    for sources in cases:
        for source in sources:
            source.receive_radius = 1000.0
    return cases


def boundary_cases(count: int, seed: int, outward: bool) -> list:
    rng = random.Random(seed)
    cases = []
    for index in range(count):
        sources = random_mixed_sources(rng, 16, 0.75)
        for source in sources:
            angle = rng.random() * 2.0 * math.pi
            radius = 1800.0 if outward and index % 2 == 0 else rng.uniform(1700.0, 1800.0)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
            source.receive_radius = 1000.0
            if outward and source.beam_direction is not None:
                source.beam_direction = math.degrees(angle) % 360.0
        cases.append(sources)
    return cases


def mixed_cases(count: int, seed: int, far_share: float = 0.5) -> list:
    """未覆盖象限：一部分源仍在标准随机位置（原点能发现），另一部分贴边朝外。

    这是"原点有发现但整体很难"的真实组合，官方生成器也可能产生：位置均匀分布
    时会自然出现远处源，随机波束下约一半定向源朝外。
    """
    rng = random.Random(seed)
    cases = []
    for _ in range(count):
        sources = random_mixed_sources(rng, None, 0.5)
        order = list(range(len(sources)))
        rng.shuffle(order)
        far_count = max(1, int(round(len(sources) * far_share)))
        for index in order[:far_count]:
            source = sources[index]
            angle = rng.random() * 2.0 * math.pi
            radius = rng.uniform(1700.0, 1800.0)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
            source.receive_radius = 1000.0
            if source.beam_direction is not None:
                source.beam_direction = math.degrees(angle) % 360.0
        cases.append(sources)
    return cases


def margin_cases(count: int, seed: int, outward_share: float) -> list:
    """贴边场景的连续过渡：每条定向波束以 outward_share 概率中轴朝外，否则随机朝向。

    outward_share=0 等价于 boundary_random，=1 等价于 boundary_outward；
    位置、半径与源数在同一随机流下保持不变，只有波束朝向按概率插值。
    """
    rng = random.Random(seed)
    cases = []
    for index in range(count):
        sources = random_mixed_sources(rng, 16, 0.75)
        for source in sources:
            angle = rng.random() * 2.0 * math.pi
            radius = 1800.0 if index % 2 == 0 else rng.uniform(1700.0, 1800.0)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
            source.receive_radius = 1000.0
            if source.beam_direction is not None:
                if rng.random() < outward_share:
                    source.beam_direction = math.degrees(angle) % 360.0
                else:
                    source.beam_direction = rng.uniform(0.0, 360.0)
        cases.append(sources)
    return cases


# ---------------------------------------------------------------- 单案例运行


def run_case_ext(item):
    case_index, sources, seed, name = item
    sim = DirectionalSimulator(clone_sources(sources), seed * 100000 + case_index)
    started = time.perf_counter()
    agent = strategy_class(name)(sim)
    result = agent.run()
    search_end_s = getattr(agent, "search_end_time_s", float("nan"))

    movement_s = search_movement_s = post_search_movement_s = 0.0
    detection_s = switching_s = clearing_s = 0.0
    failed_clear_actions = 0
    previous = (0.0, 0.0)
    current_channel = 1
    for action in sim.actions:
        if action.position is not None:
            move_s = math.dist(previous, action.position) / 5.0
            movement_s += move_s
            if action.virtual_time_s <= search_end_s + 1e-6:
                search_movement_s += move_s
            else:
                post_search_movement_s += move_s
            previous = action.position
        if action.kind == "measure":
            detection_s += 5.0
            if action.channel != current_channel:
                switching_s += 1.0
            current_channel = action.channel
        elif action.kind == "clear":
            if action.result == "success":
                clearing_s += 5.0
            else:
                clearing_s += 3.0
                failed_clear_actions += 1

    return {
        "case": case_index,
        "strategy": name,
        "source_count": len(sources),
        **result,
        "all_cleared": int(result["cleared_channels"] == len(sources)),
        "search_sites": len(agent.search_points),
        "search_end_time_s": search_end_s,
        "movement_time_s": movement_s,
        "search_movement_time_s": search_movement_s,
        "post_search_movement_time_s": post_search_movement_s,
        "detection_time_s": detection_s,
        "switching_time_s": switching_s,
        "clearing_time_s": clearing_s,
        "failed_clear_actions": failed_clear_actions,
        "origin_discoveries": getattr(agent, "origin_discoveries", None),
        "selected_route": getattr(agent, "selected_search_order", None),
        "pruned_observations": getattr(agent, "pruned_observations", None),
        "coobservations": getattr(agent, "coobservations", None),
        "pruned_truth_hits": getattr(agent, "pruned_truth_hits", None),
        "pruned_samples": getattr(agent, "pruned_samples", None),
        "min_pruned_dist": getattr(agent, "min_pruned_dist", None),
        "max_kept_dist": getattr(agent, "max_kept_dist", None),
        "delayed_decision": getattr(agent, "delayed_decision", None),
        "probe_new": getattr(agent, "probe_new", None),
        "connection_m": getattr(agent, "connection_m", None),
        "b_order_m": getattr(agent, "b_order_m", None),
        "origin_features": getattr(agent, "origin_features", None),
        "search_trace": getattr(agent, "search_trace", None),
        "obs_trace": _compress_trace(agent, search_end_s),
        "wall_time_s": time.perf_counter() - started,
    }


def _worker(item):
    return run_case_ext(item)


# ---------------------------------------------------------------- 汇总


def cvar(values: list[float], alpha: float = 0.90) -> float:
    """CVaR：最差 (1-alpha) 尾部的均值，口径与 Q3 一致。"""
    ordered = sorted(values)
    tail = max(1, int(round(len(ordered) * (1.0 - alpha))))
    return statistics.mean(ordered[-tail:])


def summarize(rows: list[dict], name: str) -> dict:
    group = [row for row in rows if row["strategy"] == name]
    per_source = [row["total_virtual_time_s"] / row["source_count"] for row in group]
    def m(key):
        return statistics.mean(row[key] / row["source_count"] for row in group)
    return {
        "strategy": name,
        "cases": len(group),
        "all_clear": sum(row["all_cleared"] for row in group),
        "mean_s_per_source": statistics.mean(per_source),
        "p95_s_per_source": percentile(per_source, 0.95),
        "cvar90_s_per_source": cvar(per_source, 0.90),
        "mean_search_movement_s": m("search_movement_time_s"),
        "mean_post_search_movement_s": m("post_search_movement_time_s"),
        "mean_detection_s": m("detection_time_s"),
        "mean_switching_s": m("switching_time_s"),
        "mean_clearing_s": m("clearing_time_s"),
        "mean_search_phase_s": statistics.mean(
            row["search_end_time_s"] / row["source_count"] for row in group),
        "mean_post_search_phase_s": statistics.mean(
            (row["total_virtual_time_s"] - row["search_end_time_s"]) / row["source_count"]
            for row in group),
        "mean_failed_clear_actions": statistics.mean(
            row["failed_clear_actions"] for row in group),
        "mean_program_time_s": statistics.mean(row["wall_time_s"] for row in group),
    }


def evaluate(label, cases, seed, names, jobs, output: Path, dump_rows: bool = True):
    work = [(index, sources, seed, name)
            for index, sources in enumerate(cases, 1) for name in names]
    rows: list[dict] = []
    step = max(1, len(work) // 10)
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for done, row in enumerate(pool.map(_worker, work), 1):
                rows.append(row)
                if done % step == 0 or done == len(work):
                    log(f"  {label}: {done}/{len(work)}")
    else:
        for done, item in enumerate(work, 1):
            rows.append(_worker(item))

    summaries = [summarize(rows, name) for name in names]
    output.mkdir(parents=True, exist_ok=True)
    if dump_rows:
        with (output / f"{label}_cases.csv").open(
                "w", newline="", encoding="utf-8-sig") as handle:
            fields = [key for key in rows[0] if key not in
                      ("origin_features", "search_trace", "obs_trace")]
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        with (output / f"{label}_rows.json").open("w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False)
    payload = {
        "label": label,
        "seed": seed,
        "summaries": summaries,
        "failures": [(row["case"], row["strategy"]) for row in rows
                     if not row["all_cleared"]],
    }
    (output / f"{label}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in summaries:
        log(f"{label:>15} {item['strategy']:>7}: "
            f"clear={item['all_clear']}/{item['cases']} "
            f"mean={item['mean_s_per_source']:.2f} "
            f"p95={item['p95_s_per_source']:.2f} "
            f"cvar90={item['cvar90_s_per_source']:.2f}")
    return rows, summaries


WORK = Path(r"C:\Users\李\Desktop\Q4探索")
SANDBOX_OUT = Path(r"c:\Users\李\.trae-cn\work\6aa56502e5f93f31529a14bc\q4x")
LOG_PATH = SANDBOX_OUT / "run.log"


def log(message: str) -> None:
    """同时打印并追加到日志文件；避免依赖 shell 管道。"""
    print(message, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def rows_path(output: Path, label: str) -> Path:
    return output / f"{label}_rows.json"


def load_rows(output: Path, label: str):
    path = rows_path(output, label)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


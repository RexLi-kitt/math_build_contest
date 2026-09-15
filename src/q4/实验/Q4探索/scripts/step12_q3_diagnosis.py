"""第十二步：Q3 正式日志的机制复现。

日志特征：
- 搜索 = 原点 + 7 点环 r=1000（6207 m），结束于 1911.9 s；
- 清除非序循环只有约 17 个"有动作"的迭代就退出了，退出时 ch15/ch16 已发现但未清除，
  且两者在清除阶段**一次动作都没有**（没有测量、也没有失败清除）；
- 该循环 = G/H/J+ 家族：for _ in range(240)，attempts>=10 或 point is None 直接
  exhausted，没有走廊兜底。

这里用离线模拟器复现：统计"给出 next_measurement_point 为 None 而直接放弃"的
发生频率与几何特征，以及整轮以未清除源收尾的比例。
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness as H  # noqa: E402

Q3_STRATEGY_DIR = (H.WORK.parent / "math_build_contest" / "math_build_contest" / "src" /
                   "q3" / "B题模型代码汇总" / "第三问策略对比")
sys.path.insert(0, str(Q3_STRATEGY_DIR))
from baseline_core import OfflineSimulator, random_sources  # noqa: E402
from strategies import JPlusAgent  # noqa: E402

OUT = H.SANDBOX_OUT / "step12_q3_diagnosis"


class DiagnosedJPlus(JPlusAgent):
    """记录放弃原因：正常路径与 J+ 完全一致。"""

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.diag = {"none_point": 0, "none_clear": 0, "attempt_cap": 0,
                     "none_events": [], "iterations": 0}

    def _next_measurement_point(self, st):
        point = super()._next_measurement_point(st)
        if point is None:
            circle = self._snapshot(st).circle
            self.diag["none_point"] += 1
            self.diag["none_events"].append({
                "observations": len(st.observations),
                "attempts": st.attempts,
                "region_radius_m": round(circle.radius_m, 1),
                "region_center_r_m": round(math.hypot(*circle.center), 1),
            })
        return point

    def _two_opt_route(self, targets):
        if getattr(self, "search_end_time_s", None) is not None:
            self.diag["iterations"] += 1
        return super()._two_opt_route(targets)


def build_case(seed, rim_heavy):
    import random
    rng = random.Random(seed)
    sources = random_sources(rng, None)
    if rim_heavy:
        for source in sources:
            angle = rng.random() * 2.0 * math.pi
            radius = 1800.0 if rng.random() < 0.5 else rng.uniform(1700.0, 1800.0)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
            source.receive_radius = 1000.0
    return sources


def run_case(item):
    index, seed, rim_heavy = item
    sources = build_case(seed, rim_heavy)
    sim = OfflineSimulator([type(s)(**vars(s)) for s in sources],
                           seed * 100000 + index)
    agent = DiagnosedJPlus(sim)
    summary = agent.run()
    state = agent.state
    unresolved = [channel for channel, st in state.items()
                  if st.discovered and not st.cleared]
    exhausted = [channel for channel, st in state.items()
                 if st.discovered and st.exhausted and not st.cleared]
    return {
        "case": index,
        "sources": len(sources),
        "discovered": summary["detected_channels"],
        "cleared": summary["cleared_channels"],
        "unresolved": len(unresolved),
        "exhausted": len(exhausted),
        "exhausted_radius": [round(math.hypot(*state[c].observations[-1][0]), 0)
                             for c in exhausted if state[c].observations],
        "none_point": agent.diag["none_point"],
        "none_events": agent.diag["none_events"][:6],
        "iterations": agent.diag["iterations"],
        "virtual_time_s": summary["total_virtual_time_s"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--cases", type=int, default=100)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    work = ([(index, 31000 + index, False) for index in range(1, args.cases + 1)]
            + [(index, 41000 + index, True) for index in range(1, args.cases + 1)])
    rows = []
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for done, row in enumerate(pool.map(run_case, work), 1):
            rows.append(row)
            if done % max(1, len(work) // 5) == 0 or done == len(work):
                H.log(f"  {done}/{len(work)}")
    payload = {}
    # 按批次拆分（前半正常分布、后半贴边重压）
    normal = rows[:args.cases]
    rim = rows[args.cases:]
    for label, group in (("正常分布", normal), ("贴边重压", rim)):
        item = {
            "cases": len(group),
            "mean_sources": statistics.mean(row["sources"] for row in group),
            "clear_rate": statistics.mean(row["cleared"] / row["sources"]
                                          for row in group),
            "cases_with_unresolved": sum(1 for row in group if row["unresolved"] > 0),
            "mean_unresolved": statistics.mean(row["unresolved"] for row in group),
            "mean_exhausted": statistics.mean(row["exhausted"] for row in group),
            "mean_none_point": statistics.mean(row["none_point"] for row in group),
            "mean_iterations": statistics.mean(row["iterations"] for row in group),
            "max_iterations": max(row["iterations"] for row in group),
            "mean_virtual_time_s": statistics.mean(row["virtual_time_s"]
                                                   for row in group),
        }
        payload[label] = item
        H.log(f"\n=== {label}（{len(group)} 例）===")
        H.log(f"  平均源数 {item['mean_sources']:.1f}，平均清除率 "
              f"{item['clear_rate']:.1%}")
        H.log(f"  以未清除源收尾的案例：{item['cases_with_unresolved']}/{len(group)}"
              f"（平均遗留 {item['mean_unresolved']:.2f} 个）")
        H.log(f"  被放弃(exhausted)的源均值 {item['mean_exhausted']:.2f}，"
              f"其中 next_measurement_point=None 次数 {item['mean_none_point']:.2f}")
        H.log(f"  消除循环迭代数：均值 {item['mean_iterations']:.1f}，"
              f"最大 {item['max_iterations']}（上限 240）")
        H.log(f"  平均虚拟时间 {item['mean_virtual_time_s']:.0f} s")
    events = [event for row in rows for event in row["none_events"]]
    if events:
        H.log(f"\n放弃事件共 {len(events)} 次；可行域半径中位数 "
              f"{statistics.median(e['region_radius_m'] for e in events):.1f} m，"
              f"可行域中心半径均值 "
              f"{statistics.mean(e['region_center_r_m'] for e in events):.1f} m，"
              f"已有方位数分布 "
              f"{sorted(set(e['observations'] for e in events))[:8]}")
    (OUT / "q3_diagnosis.json").write_text(json.dumps(
        {"summary": payload, "events_sample": events[:40]},
        ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

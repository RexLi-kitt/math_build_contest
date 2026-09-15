"""第十四步：严格场地约束下的 Q3 复现。

官方客户端 official_baseline_runner._post 的行为：请求若未被接受 → 重试 2 次 →
抛 RuntimeError("... 请求失败") → runner 捕获异常 → finally 调用 /exit →
官方日志表现为"正常退出"但留有未清除源。

离线模拟器不校验请求点是否在 1800 m 场地内，因此需要显式加上这条约束来复现。
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness as H  # noqa: E402

Q3_DIR = (H.WORK.parent / "math_build_contest" / "math_build_contest" / "src" / "q3" /
          "B题模型代码汇总" / "第三问策略对比")
sys.path.insert(0, str(Q3_DIR))
from baseline_core import OfflineSimulator, random_sources  # noqa: E402
from strategies import STRATEGIES  # noqa: E402

OUT = H.SANDBOX_OUT / "step14_q3_strict"
ARENA_R = 1800.0


class StrictSimulator(OfflineSimulator):
    """把"请求点必须落在 1800 m 场地内"作为硬约束；越界即视为被官方拒绝。"""

    def __init__(self, sources, seed, enforce: bool):
        super().__init__(sources, seed)
        self.enforce = enforce
        self.rejected: list = []

    def _check(self, p) -> None:
        radius = math.hypot(p[0], p[1])
        if self.enforce and radius > ARENA_R + 1e-9:
            self.rejected.append((round(p[0], 2), round(p[1], 2), round(radius, 2)))
            raise RuntimeError(f"位置越界被拒绝：{self.rejected[-1]}")

    def measure(self, p, channel):
        self._check(p)
        return super().measure(p, channel)

    def clear(self, p, channel):
        self._check(p)
        return super().clear(p, channel)


def build_sources(seed: int, rim_heavy: bool):
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
    index, seed, rim_heavy, enforce = item
    sources = build_sources(seed, rim_heavy)
    sim = StrictSimulator([type(s)(**vars(s)) for s in sources],
                          seed * 100000 + index, enforce)
    agent = STRATEGIES["Jplus_final"](sim)
    error = None
    try:
        summary = agent.run()
        cleared = summary["cleared_channels"]
        total = len(sources)
    except RuntimeError as exc:
        error = str(exc)[:80]
        cleared = sum(state.cleared for state in agent.state.values())
        total = len(sources)
    return {
        "case": index, "sources": total, "cleared": cleared,
        "aborted": error is not None, "error": error,
        "rejected": sim.rejected[:1], "virtual_time_s": sim.time_s,
        "unresolved_at_end": total - cleared,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--cases", type=int, default=100)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for enforce in (False, True):
        work = ([(index, 51000 + index, False, enforce)
                 for index in range(1, args.cases + 1)]
                + [(index, 61000 + index, True, enforce)
                   for index in range(1, args.cases + 1)])
        rows = []
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            for done, row in enumerate(pool.map(run_case, work), 1):
                rows.append(row)
        normal, rim = rows[:args.cases], rows[args.cases:]
        payload = {}
        H.log(f"\n=== 场地约束 {'开启（复现官方）' if enforce else '关闭（原离线口径）'} ===")
        for label, group in (("正常分布", normal), ("贴边重压", rim)):
            aborts = [row for row in group if row["aborted"]]
            item = {
                "cases": len(group),
                "abort_rate": len(aborts) / len(group),
                "clear_rate": statistics.mean(row["cleared"] / row["sources"]
                                              for row in group),
                "clear_rate_among_aborts": (statistics.mean(
                    row["cleared"] / row["sources"] for row in aborts)
                    if aborts else None),
                "mean_leftover": statistics.mean(row["unresolved_at_end"]
                                                 for row in group),
                "first_rejected": aborts[0]["rejected"] if aborts else None,
            }
            payload[label] = item
            H.log(f"  {label}：中断率 {item['abort_rate']:.1%}，"
                  f"平均清除率 {item['clear_rate']:.1%}，"
                  f"中断案例的清除率 "
                  f"{(item['clear_rate_among_aborts'] or 0):.1%}，"
                  f"首个越界请求 {item['first_rejected']}")
        (OUT / f"strict_{'on' if enforce else 'off'}.json").write_text(
            json.dumps({"summary": payload, "cases": rows},
                       ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

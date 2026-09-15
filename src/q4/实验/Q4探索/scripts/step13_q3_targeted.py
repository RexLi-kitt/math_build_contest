"""第十三步：按正式日志反推的几何做定点复现。

从官方日志的三条示向度可反推出两个未清除源的位置：
- ch16: 由 (623.49,-781.83) 32.51°、(1000,0) 329.43° 交会 → 约 (1442,-260)，r=1465
        （原点 1465 m 处不可见，故 R < 1465；在 513 m 处可见，故 R ≥ 1000）
- ch15: 由 (1000,0) 75.73°、(623.49,781.83) 22.06° 交会 → 约 (1264,1041)，r=1637
        （原点不可见 → R < 1637；1073 m 处可见 → R ≥ 1073）

用离线模拟器 + 同一个 J+ 代理检验：这种几何会不会触发"算不出下一测点"的放弃路径。
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness as H  # noqa: E402

Q3_DIR = (H.WORK.parent / "math_build_contest" / "math_build_contest" / "src" / "q3" /
          "B题模型代码汇总" / "第三问策略对比")
sys.path.insert(0, str(Q3_DIR))
from baseline_core import OfflineSimulator, Source  # noqa: E402
from strategies import STRATEGIES  # noqa: E402

OUT = H.SANDBOX_OUT / "step13_q3_targeted"
JPlus = STRATEGIES["Jplus_final"]


class DiagnosedJPlus(JPlus):
    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        self.diag = {"none_point": 0, "none_clear": 0, "events": []}

    def _next_measurement_point(self, st):
        point = super()._next_measurement_point(st)
        if point is None:
            circle = self._snapshot(st).circle
            self.diag["none_point"] += 1
            self.diag["events"].append({
                "channel": None, "observations": len(st.observations),
                "attempts": st.attempts,
                "region_radius_m": round(circle.radius_m, 1),
                "region_center_r_m": round(math.hypot(*circle.center), 1),
            })
        return point

    def _clear_decision(self, st):
        center = super()._clear_decision(st)
        if center is None:
            self.diag["none_clear"] += 1
        return center


def run(name, spec):
    sources = [Source(channel, position, radius)
               for channel, position, radius in spec]
    sim = OfflineSimulator(sources, 20260913)
    agent = DiagnosedJPlus(sim)
    summary = agent.run()
    leftovers = [(channel, round(math.hypot(*state.observations[0][0]), 0),
                  len(state.observations), state.attempts, state.exhausted)
                 for channel, state in agent.state.items()
                 if state.discovered and not state.cleared]
    H.log(f"\n=== {name} ===")
    H.log(f"  源数 {len(sources)}，发现 {summary['detected_channels']}，"
          f"清除 {summary['cleared_channels']}，虚拟时间 {summary['total_virtual_time_s']:.1f} s")
    H.log(f"  未清除：{leftovers}")
    H.log(f"  无下一测点事件 {agent.diag['none_point']} 次，"
          f"无清除中心事件 {agent.diag['none_clear']} 次")
    for event in agent.diag["events"][:5]:
        H.log(f"    {event}")
    return {"name": name, "sources": len(sources),
            "detected": summary["detected_channels"],
            "cleared": summary["cleared_channels"],
            "virtual_time_s": summary["total_virtual_time_s"],
            "leftovers": leftovers, "none_point": agent.diag["none_point"],
            "none_clear": agent.diag["none_clear"],
            "events": agent.diag["events"][:10]}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = [
        ("仅 ch16 (1442,-260) R=1000", [(16, (1442.0, -260.0), 1000.0)]),
        ("仅 ch16 R=1400", [(16, (1442.0, -260.0), 1400.0)]),
        ("仅 ch15 (1264,1041) R=1100", [(15, (1264.0, 1041.0), 1100.0)]),
        ("仅 ch15 R=1600", [(15, (1264.0, 1041.0), 1600.0)]),
        ("ch15+ch16", [(15, (1264.0, 1041.0), 1100.0), (16, (1442.0, -260.0), 1000.0)]),
        ("ch15+ch16+中心源", [(15, (1264.0, 1041.0), 1100.0),
                              (16, (1442.0, -260.0), 1000.0),
                              (1, (300.0, 200.0), 1200.0),
                              (2, (-400.0, -300.0), 1300.0)]),
    ]
    results = [run(name, spec) for name, spec in cases]
    (OUT / "targeted_report.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = [item for item in results if item["cleared"] < item["sources"]]
    H.log(f"\n结论：{len(failures)}/{len(results)} 个定点案例未完成全清除"
          f"{'，已复现放弃路径' if failures else '，定点几何下 J+ 仍能全清除'}")


if __name__ == "__main__":
    main()

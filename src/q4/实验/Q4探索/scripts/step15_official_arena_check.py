"""核查官方接口对"请求点是否必须在 1800 m 场地内"的约束。

方法：解析团队自己那轮成功的官方演练日志（14/14、3749.393 s），统计所有请求点的
半径分布。若成功运行里出现过 >1800 m 的请求点，说明官方允许越界，越界拒绝假设不成立；
若全部 ≤1800 m，则该约束与成功运行相容。
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

LOGS = [
    H.WORK.parent / "math_build_contest" / "math_build_contest" / "src" / "q3" /
    "B题模型代码汇总" / "模拟器与官方接口" / "official_logs" /
    "Jplus_final_virtual_14of14_3749.393s_20260913.json",
    H.WORK.parent / "math_build_contest" / "math_build_contest" / "src" / "q3" /
    "B题模型代码汇总" / "模拟器与官方接口" / "official_logs" /
    "Jplus_final_actions.json",
    H.WORK.parent / "math_build_contest" / "math_build_contest" / "src" / "q3" /
    "B题模型代码汇总" / "模拟器与官方接口" / "official_logs" /
    "I_ring_optimized_actions.json",
    H.WORK.parent / "math_build_contest" / "math_build_contest" / "src" / "q3" /
    "B题机器狗离线模拟器" / "official_logs" / "baseline_actions.json",
]


def analyse(path: Path) -> dict:
    records = json.loads(path.read_text(encoding="utf-8"))
    radii, kinds, cleared, measured = [], {}, set(), set()
    rejects = []
    for record in records:
        kind = record.get("kind")
        kinds[kind] = kinds.get(kind, 0) + 1
        position = record.get("position")
        if position:
            radii.append(math.hypot(position[0], position[1]))
        response = record.get("response") or {}
        if response.get("accepted") is False:
            rejects.append(record.get("request_id"))
        if kind == "clear" and record.get("result") == "success":
            cleared.add(record.get("channel"))
        if kind == "measure" and record.get("result") == "direction":
            measured.add(record.get("channel"))
        if kind == "enter":
            enter_meta = {key: response.get(key) for key in
                          ("max_virtual_duration_s", "max_real_duration_s")}
        else:
            enter_meta = locals().get("enter_meta", {})
    return {
        "file": path.name,
        "actions": len(records),
        "kinds": kinds,
        "max_radius_m": round(max(radii), 1) if radii else None,
        "positions_over_1800": sum(1 for r in radii if r > 1800.0 + 1e-9),
        "positions_over_1805": sum(1 for r in radii if r > 1805.0),
        "positions_over_1900": sum(1 for r in radii if r > 1900.0),
        "mean_radius_m": round(statistics.mean(radii), 1) if radii else None,
        "rejected_requests": rejects,
        "measured_channels": sorted(measured),
        "cleared_channels": sorted(cleared),
        "enter_meta": enter_meta if radii or True else {},
        "final_time_s": records[-1].get("virtual_time_s"),
    }


def main() -> None:
    for path in LOGS:
        if not path.exists():
            H.log(f"缺少 {path.name}")
            continue
        item = analyse(path)
        H.log(f"\n=== {item['file']} ===")
        H.log(f"  动作 {item['actions']}，构成 {item['kinds']}，"
              f"结束虚拟时间 {item['final_time_s']}")
        H.log(f"  请求点半径：最大 {item['max_radius_m']} m，均值 "
              f"{item['mean_radius_m']} m")
        H.log(f"  越界请求点：>1800 有 {item['positions_over_1800']} 个，"
              f">1805 有 {item['positions_over_1805']} 个，"
              f">1900 有 {item['positions_over_1900']} 个")
        H.log(f"  被拒绝的请求：{item['rejected_requests']}")
        H.log(f"  发现频道 {item['measured_channels']}")
        H.log(f"  清除频道 {item['cleared_channels']}")
        H.log(f"  进入响应元数据 {item['enter_meta']}")


if __name__ == "__main__":
    main()

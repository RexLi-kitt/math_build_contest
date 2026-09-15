"""第五步（评估）：C+3F 的可优化空间上限与第三次观测的浪费画像。

两部分：
1) 事后精确重建"逐案例在方位2/方位3之间选更优"的 oracle，给出任何按案例选择规则的
   收益上限；同时看方位3的亏损是集中还是分散。
2) 诊断第三次观测的机制：记录每次"已积累2条方位后再测一次"的结果与到真实源的距离，
   量化盲区观测的比例，用于设计选择性补测的判据。
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402
from baseline_core import bearing, dist, wrap  # noqa: E402
from q4_experiment import DirectionalSimulator, clone_sources  # noqa: E402

OUT = H.SANDBOX_OUT / "step5_probe3"
STEP2C = H.SANDBOX_OUT / "step2c"
STEP4 = H.SANDBOX_OUT / "step4_azimuth"

_C_BASE = H._load("q4x_c_base3", H.MODELS / "C模型" / "cert_route_agent.py").CertRouteAgent


class Az3ProbeAgent(_C_BASE):
    """C 的方位3臂，额外记录"第3条方位尝试"的几何与结果。"""

    coverage_observation_target = 3

    def observe(self, p, channel):
        state = self.state[channel]
        bearings_before = len(state.observations)
        result = super().observe(p, channel)
        if bearings_before == 2:
            source = PROBE.get("by_channel", {}).get(channel)
            record = PROBE.setdefault("events", [])
            if source is None:
                record.append({"k": 3, "result": result, "dist": None,
                               "too_far": None, "wrong_beam": None})
            else:
                distance = dist(p, source.position)
                beam_ok = True
                if source.beam_direction is not None:
                    beam_ok = abs(wrap(bearing(source.position, p)
                                       - source.beam_direction)) <= 90.0 + 1e-10
                record.append({
                    "k": 3, "result": result, "dist": round(distance, 2),
                    "too_far": distance > source.receive_radius + 1e-9,
                    "wrong_beam": not beam_ok,
                })
        return result


PROBE: dict = {}


def probe_worker(item):
    index, sources, seed, name = item
    PROBE.clear()
    PROBE["by_channel"] = {source.channel: source for source in sources}
    sim = DirectionalSimulator(clone_sources(sources), seed * 100000 + index)
    agent = Az3ProbeAgent(sim)
    result = agent.run()
    events = PROBE.get("events", [])
    third = [event for event in events if event["k"] == 3]
    blind = [event for event in third if event["result"] == "no_signal"]
    too_far = [event for event in third if event["too_far"]]
    wrong_beam = [event for event in third if event["wrong_beam"]]
    both = [event for event in third if event["too_far"] and event["wrong_beam"]]
    return {
        "case": index,
        "source_count": len(sources),
        "cleared": result["cleared_channels"],
        "total_virtual_time_s": result["total_virtual_time_s"],
        "third_attempts": len(third),
        "third_blind": len(blind),
        "third_impossible": len([e for e in third
                                 if e["too_far"] or e["wrong_beam"]]),
        "third_too_far": len(too_far),
        "third_wrong_beam": len(wrong_beam),
        "third_both": len(both),
        "third_blind_dist_mean": (statistics.mean(e["dist"] for e in blind)
                                  if blind else None),
        "third_success_dist_mean": (statistics.mean(e["dist"] for e in third
                                                    if e["result"] != "no_signal")
                                    if any(e["result"] != "no_signal" for e in third)
                                    else None),
    }


def load_arm(label, strategy):
    rows = json.loads((STEP4 / f"{label}_rows.json").read_text(encoding="utf-8"))
    return {row["case"]: row["total_virtual_time_s"] / row["source_count"]
            for row in rows if row["strategy"] == strategy}


def load_features(label):
    rows = json.loads((STEP2C / f"{label}_rows.json").read_text(encoding="utf-8"))
    return {row["case"]: row["origin_features"] for row in rows
            if row["strategy"] == "CplusLog"}


def part_one() -> None:
    H.log("=== 一、方位2/方位3 的事后选择上限（s/源） ===")
    H.log(f"{'场景':<18}{'方位2':>9}{'方位3':>9}{'逐案例最优':>11}"
          f"{'方位3胜率':>10}{'亏损案例均值':>13}{'获利案例均值':>13}")
    for label in ("normal", "min_radius", "boundary_random", "boundary_outward",
                  "mixed"):
        path = STEP4 / f"{label}_rows.json"
        if not path.exists():
            continue
        two = load_arm(label, "C")
        three = load_arm(label, "CAz3")
        cases = sorted(set(two) & set(three))
        deltas = [three[case] - two[case] for case in cases]
        oracle = [min(two[case], three[case]) for case in cases]
        losers = [value for value in deltas if value > 0]
        winners = [value for value in deltas if value < 0]
        H.log(f"{label:<18}{statistics.mean(two[c] for c in cases):>9.2f}"
              f"{statistics.mean(three[c] for c in cases):>9.2f}"
              f"{statistics.mean(oracle):>11.2f}"
              f"{len(winners) / len(deltas):>10.1%}"
              f"{(statistics.mean(losers) if losers else 0):>+13.2f}"
              f"{(statistics.mean(winners) if winners else 0):>+13.2f}")


def part_two(jobs: int) -> None:
    H.log("\n=== 二、第三次方位尝试的浪费画像 ===")
    H.log(f"{'场景':<14}{'尝试/例':>9}{'盲区':>8}{'太远':>8}{'波束背向':>10}"
          f"{'两者兼有':>9}{'盲区距离(m)':>12}{'成功距离(m)':>12}")
    scenarios = [
        ("normal", H.normal_cases(300, 20261021), 20261021),
        ("min_radius", H.min_radius_cases(200, 20261022), 20261022),
        ("mixed", H.mixed_cases(200, 20261025), 20261025),
    ]
    payload = {}
    OUT.mkdir(parents=True, exist_ok=True)
    for label, cases, seed in scenarios:
        work = [(index, sources, seed, "Az3Probe")
                for index, sources in enumerate(cases, 1)]
        rows = []
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for done, row in enumerate(pool.map(probe_worker, work), 1):
                rows.append(row)
                if done % max(1, len(work) // 5) == 0 or done == len(work):
                    H.log(f"  {label}: {done}/{len(work)}")
        total = sum(row["third_attempts"] for row in rows)
        blind_dist = [row["third_blind_dist_mean"] for row in rows
                      if row["third_blind_dist_mean"] is not None]
        success_dist = [row["third_success_dist_mean"] for row in rows
                        if row["third_success_dist_mean"] is not None]
        payload[label] = {
            "cases": len(rows),
            "third_attempts_per_case": total / len(rows),
            "total_attempts": total,
            "blind": sum(row["third_blind"] for row in rows),
            "too_far": sum(row["third_too_far"] for row in rows),
            "wrong_beam": sum(row["third_wrong_beam"] for row in rows),
            "both": sum(row["third_both"] for row in rows),
            "blind_dist_mean": statistics.mean(blind_dist) if blind_dist else None,
            "success_dist_mean": (statistics.mean(success_dist)
                                  if success_dist else None),
        }
        item = payload[label]
        H.log(f"{label:<14}{item['third_attempts_per_case']:>9.2f}"
              f"{item['blind'] / total:>8.1%}"
              f"{item['too_far'] / total:>8.1%}"
              f"{item['wrong_beam'] / total:>10.1%}"
              f"{item['both'] / total:>9.1%}"
              f"{(item['blind_dist_mean'] or 0):>12.1f}"
              f"{(item['success_dist_mean'] or 0):>12.1f}")
    (OUT / "probe3_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=12)
    args = parser.parse_args()
    part_one()
    part_two(args.jobs)


if __name__ == "__main__":
    main()

"""核对 step17 的 normal 场景与 harness 标准 normal 场景是否同一定义。"""
from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness as H  # noqa: E402
sys.path.insert(0, str(HERE.parent / "models"))
from step17_source_count import build  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def profile(groups):
    counts = [len(group) for group in groups]
    radii = [source.receive_radius for group in groups for source in group]
    beams = [source.beam_direction is not None for group in groups for source in group]
    return (statistics.mean(counts), min(radii), max(radii), statistics.mean(radii),
            sum(beams) / len(beams))


standard = H.normal_cases(5, 20270101)
mine = build("normal", 5, 20270101, 16)
print("harness.normal_cases :", profile(standard))
print("step17 build(normal) :", profile(mine))

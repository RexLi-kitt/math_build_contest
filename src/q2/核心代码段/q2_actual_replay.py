# 功能：按真实接收半径和第二次角度误差回放检测结果，并以实际 MEC 判断能否清除。
from __future__ import annotations

import math
import sys
from pathlib import Path

Q2_DIR = Path(__file__).resolve().parents[1] / "q2"
sys.path.insert(0, str(Q2_DIR))
from q1_q2_bridge import bearing, evaluate_a2  # noqa: E402

S1 = (-750.0, -450.0)
FAILURE_MEC = 250.0


def wrap(angle_deg: float) -> float:
    return (angle_deg + 180.0) % 360.0 - 180.0


def replay_second_measurement(g_true: tuple[float, float], receive_radius_m: float,
                              first_bearing_deg: float, second_error_deg: float,
                              s2: tuple[float, float]) -> dict:
    """未接收时不能假装定位成功；接收时才以 A2 的实际 MEC 评价清除条件。"""
    distance = math.dist(s2, g_true)
    if distance > receive_radius_m:
        return {"return_type": "no_signal", "received": False, "mec_m": FAILURE_MEC,
                "can_clear": False}
    if distance <= 5.0:
        return {"return_type": "near", "received": True, "mec_m": 0.0, "can_clear": True}
    second_bearing = wrap(bearing(s2, g_true) + second_error_deg)
    region = evaluate_a2(S1, first_bearing_deg, s2, second_bearing)
    mec = region.mec_radius_m
    return {"return_type": "direction", "received": True, "mec_m": mec,
            "can_clear": math.isfinite(mec) and mec <= 20.0}

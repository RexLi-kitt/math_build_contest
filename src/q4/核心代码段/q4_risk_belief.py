# 功能：按定向源物理规则用 direction 与 no_signal 更新位置—方向联合候选状态。
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


def wrap(angle_deg: float) -> float:
    return (angle_deg + 180.0) % 360.0 - 180.0


@dataclass(frozen=True)
class State:
    x_m: float
    y_m: float
    direction_deg: float | None  # None 表示全向源；其余表示定向源发射中心方向


def is_visible(state: State, sensor: tuple[float, float]) -> bool:
    """定向源半张角为 90°；全向源始终可见。"""
    if state.direction_deg is None:
        return True
    angle = math.degrees(math.atan2(sensor[1] - state.y_m, sensor[0] - state.x_m))
    return abs(wrap(angle - state.direction_deg)) <= 90.0


def update_belief(states: Iterable[State], sensor: tuple[float, float], result: str,
                  bearing_deg: float | None = None, error_deg: float = 1.0) -> list[State]:
    """返回更新后的状态；关键是 no_signal 只排除“1000m 内且本应可见”的状态。"""
    updated: list[State] = []
    for state in states:
        distance = math.dist(sensor, (state.x_m, state.y_m))
        visible = is_visible(state, sensor)
        if result == "direction":
            if bearing_deg is None:
                raise ValueError("direction 返回必须提供示向度")
            predicted = math.degrees(math.atan2(state.y_m - sensor[1], state.x_m - sensor[0]))
            # 正测向需同时满足角度带、题设最大接收距离和该发射方向的可见性。
            if abs(wrap(predicted - bearing_deg)) <= error_deg and distance <= 1500.0 and visible:
                updated.append(state)
        elif result == "near":
            # near 只表明存在近场源，后续直接尝试清除；这里保留 5m 内状态作认证。
            if distance <= 5.0 and visible:
                updated.append(state)
        elif result == "no_signal":
            # 1000m 内保证接收：若本应可见却无信号，该状态可被排除。
            # 1000–1500m 或盲侧无信号均不能作为硬排除条件。
            if not (distance <= 1000.0 and visible):
                updated.append(state)
        else:
            raise ValueError(f"未知测量返回：{result}")
    return updated

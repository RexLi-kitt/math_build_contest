"""问题4本地协议模拟器：复刻官方 /enter、/measure、/clear、/exit 的动作与虚拟计时规则。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Literal

RADIUS, SPEED, N_CHANNELS = 1800.0, 5.0, 20
SWITCH_TIME, MEASURE_TIME, LOCATE_TIME, CLEAR_TIME = 1.0, 5.0, 3.0, 2.0
MAX_COORDINATE, MAX_VIRTUAL_DURATION = 2_000_000.0, 360_000.0


def wrap(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def bearing(origin: tuple[float, float], target: tuple[float, float]) -> float:
    return math.degrees(math.atan2(target[1] - origin[1], target[0] - origin[0])) % 360.0


@dataclass
class Source:
    channel: int
    x_m: float
    y_m: float
    receive_radius_m: float
    kind: Literal["omnidirectional", "directional"]
    facing_deg: float | None = None
    cleared: bool = False


class LocalQ4Simulator:
    """本地动作级替身；不复制官方隐藏案例生成器或 HTTP/联网生命周期。"""

    def __init__(self, seed: int = 20260914, source_count: int = 12,
                 directional_ratio: float = 0.5) -> None:
        if not 10 <= source_count <= 16:
            raise ValueError("source_count 必须满足题设的 10--16。")
        self.seed, self.rng = seed, random.Random(seed)
        self.position, self.channel = (0.0, 0.0), 1
        self.virtual_time_s, self.entered = 0.0, False
        self._measure_error_cache: dict[tuple[int, float, float], float] = {}
        self._requests: dict[str, tuple[str, dict, dict]] = {}
        self.sources = self._generate_sources(source_count, directional_ratio)
        self.log: list[dict] = []

    def _generate_sources(self, count: int, directional_ratio: float) -> list[Source]:
        channels = self.rng.sample(range(1, N_CHANNELS + 1), count)
        directional_count = round(count * directional_ratio)
        result = []
        for index, channel in enumerate(channels):
            rho, theta = RADIUS * math.sqrt(self.rng.random()), self.rng.uniform(0.0, 2 * math.pi)
            directional = index < directional_count
            result.append(Source(channel, rho * math.cos(theta), rho * math.sin(theta),
                                 self.rng.uniform(1000.0, 1500.0),
                                 "directional" if directional else "omnidirectional",
                                 self.rng.uniform(0.0, 360.0) if directional else None))
        return result

    def _source_for(self, channel: int) -> Source | None:
        return next((s for s in self.sources if s.channel == channel and not s.cleared), None)

    def _fixed_error(self, channel: int, point: tuple[float, float]) -> float:
        key = (channel, round(point[0], 6), round(point[1], 6))
        if key not in self._measure_error_cache:
            raw = int(hashlib.sha256(f"{self.seed}|{key}".encode()).hexdigest()[:12], 16)
            self._measure_error_cache[key] = 2.0 * raw / (16**12 - 1) - 1.0
        return self._measure_error_cache[key]

    def _visible(self, point: tuple[float, float], source: Source) -> bool:
        if source.kind == "omnidirectional":
            return True
        return abs(wrap(bearing((source.x_m, source.y_m), point) - float(source.facing_deg))) <= 90.0

    def _record(self, action: str, **payload: object) -> dict:
        event = {"action": action, "virtual_time_s": round(self.virtual_time_s, 6),
                 "x_m": self.position[0], "y_m": self.position[1], "channel": self.channel, **payload}
        self.log.append(event)
        return event

    def _move_to(self, point: tuple[float, float]) -> float:
        if not all(math.isfinite(v) and abs(v) <= MAX_COORDINATE for v in point):
            raise ValueError("坐标必须为有限数且绝对值不超过 2000000。")
        distance = math.dist(self.position, point)
        self.virtual_time_s += distance / SPEED
        self.position = (float(point[0]), float(point[1]))
        return distance

    def _accepted_false(self, action: str, reason: str) -> dict:
        # 官方 accepted=false 的 virtual_time_s 固定为 0，不能当作当前时刻。
        return self._record(action, accepted=False, virtual_time_s=0, reason=reason)

    def _deduplicate(self, action: str, request_id: str | None, payload: dict) -> dict | None:
        if request_id is None:
            return None
        old = self._requests.get(request_id)
        if old is None:
            return None
        if old[0] == action and old[1] == payload:
            return dict(old[2])
        return {"accepted": False, "http_status": 409, "virtual_time_s": 0,
                "reason": "同一 request_id 的请求体不一致"}

    def _save_request(self, action: str, request_id: str | None, payload: dict, response: dict) -> dict:
        if request_id is not None and response.get("accepted") is True:
            self._requests[request_id] = (action, dict(payload), dict(response))
        return response

    def enter(self, request_id: str | None = None) -> dict:
        repeated = self._deduplicate("enter", request_id, {})
        if repeated is not None:
            return repeated
        if self.entered:
            return self._accepted_false("enter", "重复 enter")
        self.entered = True
        response = self._record("enter", accepted=True, max_virtual_duration_s=MAX_VIRTUAL_DURATION,
                                max_real_duration_s=1200, remaining_real_duration_s=1200)
        return self._save_request("enter", request_id, {}, response)

    def measure(self, position: tuple[float, float], channel: int, request_id: str | None = None) -> dict:
        payload = {"position": tuple(position), "channel": channel}
        repeated = self._deduplicate("measure", request_id, payload)
        if repeated is not None:
            return repeated
        if not self.entered:
            return self._accepted_false("measure", "尚未 enter")
        if not isinstance(channel, int) or not 1 <= channel <= N_CHANNELS:
            return self._accepted_false("measure", "频道必须为 1--20 的整数")
        distance = self._move_to(position)
        switched = channel != self.channel
        if switched:
            self.virtual_time_s += SWITCH_TIME
            self.channel = channel
        self.virtual_time_s += MEASURE_TIME
        source = self._source_for(channel)
        if source is None or math.dist(self.position, (source.x_m, source.y_m)) > source.receive_radius_m or not self._visible(self.position, source):
            response = self._record("measure", accepted=True, distance_m=distance, switched=switched, measure_result="no_signal")
        elif math.dist(self.position, (source.x_m, source.y_m)) <= 5.0:
            response = self._record("measure", accepted=True, distance_m=distance, switched=switched, measure_result="near")
        else:
            svd = round((bearing(self.position, (source.x_m, source.y_m)) + self._fixed_error(channel, self.position)) % 360.0, 2)
            response = self._record("measure", accepted=True, distance_m=distance, switched=switched,
                                    measure_result="direction", svd_deg=svd)
        return self._save_request("measure", request_id, payload, response)

    def clear(self, position: tuple[float, float], channel: int, request_id: str | None = None) -> dict:
        payload = {"position": tuple(position), "channel": channel}
        repeated = self._deduplicate("clear", request_id, payload)
        if repeated is not None:
            return repeated
        if not self.entered:
            return self._accepted_false("clear", "尚未 enter")
        if not isinstance(channel, int) or not 1 <= channel <= N_CHANNELS:
            return self._accepted_false("clear", "频道必须为 1--20 的整数")
        distance = self._move_to(position)
        source = self._source_for(channel)
        success = source is not None and math.dist(self.position, (source.x_m, source.y_m)) <= 20.0
        self.virtual_time_s += LOCATE_TIME + (CLEAR_TIME if success else 0.0)
        if success:
            source.cleared = True
        response = self._record("clear", accepted=True, target_channel=channel, distance_m=distance,
                                clear_result="success" if success else "no_target_in_range")
        return self._save_request("clear", request_id, payload, response)

    def exit(self, request_id: str | None = None) -> dict:
        repeated = self._deduplicate("exit", request_id, {})
        if repeated is not None:
            return repeated
        if not self.entered:
            return self._accepted_false("exit", "尚未 enter")
        self.entered = False
        response = self._record("exit", accepted=True, exit_reason="user_exit", summary=self.summary())
        return self._save_request("exit", request_id, {}, response)

    def summary(self) -> dict:
        cleared = sum(source.cleared for source in self.sources)
        return {"source_count": len(self.sources), "cleared_count": cleared,
                "clear_rate": cleared / len(self.sources), "virtual_time_s": round(self.virtual_time_s, 6)}

    def export_log(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.log, ensure_ascii=False, indent=2), encoding="utf-8")

    def export_hidden_scenario_for_debug_only(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps([asdict(s) for s in self.sources], ensure_ascii=False, indent=2), encoding="utf-8")

"""将当前第三问离线基线策略接到官方“问题3演练测试”接口。

重要：本程序使用 b_robot_offline.py 内的临时主动选点启发式，不是问题2正式模型。
只用于官方演练测试，绝不能用于正式测试调试。
参赛队号必须通过 --robot-id 在运行时提供，源码不保存任何队号。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from b_robot_offline import Action, SevenPointAgent


class OfficialSimulatorClient:
    """以与离线环境相同的最小方法集封装官方 HTTP 接口。"""

    def __init__(self, base_url: str, robot_id: str, log_path: Path,
                 arena_id: str = "default"):
        self.base_url = base_url.rstrip("/")
        self.robot_id = robot_id
        self.arena_id = arena_id
        self.log_path = log_path
        self.position = (0.0, 0.0)
        self.current_channel = 1
        self.time_s = 0.0
        self.actions: list[Action] = []
        self.records: list[dict] = []
        self.log_error: str | None = None
        self._request_no = 0
        self.entered = False
        self.real_deadline = 0.0

    def _next_id(self, prefix: str) -> str:
        self._request_no += 1
        return f"baseline-{prefix}-{self._request_no}"

    def _base(self, request_id: str) -> dict:
        return {"arena_id": self.arena_id, "robot_id": self.robot_id, "request_id": request_id}

    @classmethod
    def _mask(cls, value):
        # 提交材料需隐去参赛队号，落盘前把 robot_id 替换为占位符。
        if isinstance(value, dict):
            return {k: ("TEAM_ID" if k == "robot_id" else cls._mask(v))
                    for k, v in value.items()}
        if isinstance(value, list):
            return [cls._mask(v) for v in value]
        return value

    def _post(self, path: str, payload: dict) -> dict:
        # 网络短暂中断时，保持 request_id 和请求体不变进行一次重试，符合官方幂等规则。
        last_error: Exception | None = None
        for _ in range(2):
            try:
                request = Request(
                    self.base_url + path,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=5) as response:
                    body = json.loads(response.read().decode("utf-8"))
                    if response.status != 200 or body.get("accepted") is not True:
                        raise RuntimeError(f"{path} 未被接受：{body}")
                    return body
            except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
                last_error = exc
        raise RuntimeError(f"{path} 请求失败：{last_error}")

    def _record(self, request_id: str, kind: str, position, channel,
                result: str, response: dict) -> None:
        self.time_s = float(response["virtual_time_s"])
        self.actions.append(Action(kind, position, channel, result, self.time_s))
        # 自记完整指令序列与响应信息；robot_id 已脱敏为占位符。
        self.records.append({
            "kind": kind,
            "request_id": request_id,
            "position": list(position) if position is not None else None,
            "channel": channel,
            "result": result,
            "virtual_time_s": self.time_s,
            "response": self._mask(response),
        })
        # A local log failure must never abandon an already-running official
        # test.  Keep recording in memory and report the issue once; /exit and
        # the remaining strategy actions can still be sent normally.
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.write_text(
                json.dumps(self.records, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            if self.log_error is None:
                self.log_error = str(exc)
                print(f"警告：动作日志暂时无法写入（测试将继续）：{exc}", file=sys.stderr)

    def _ensure_time(self) -> None:
        # 为主动 /exit 留出余量；届时由外层记录为未完成，不假装任务已完成。
        if self.real_deadline and time.monotonic() >= self.real_deadline:
            raise TimeoutError("现实运行预算即将耗尽")

    def enter(self) -> None:
        request_id = self._next_id("enter")
        response = self._post("/enter", self._base(request_id))
        self.entered = True
        remaining = float(response["remaining_real_duration_s"])
        self.real_deadline = time.monotonic() + max(0.0, remaining - 8.0)
        self._record(request_id, "enter", None, None, "accepted", response)
        print(f"已进入测试，现实剩余时间 {remaining:.0f} 秒")

    def measure(self, position, channel: int):
        self._ensure_time()
        request_id = self._next_id("measure")
        payload = self._base(request_id)
        payload["position"] = {"x": position[0], "y": position[1]}
        payload["channel"] = channel
        response = self._post("/measure", payload)
        self.position = (float(position[0]), float(position[1]))
        self.current_channel = channel
        result = response["measure_result"]
        self._record(request_id, "measure", self.position, channel, result, response)
        return result, response.get("svd_deg")

    def clear(self, position, channel: int) -> bool:
        self._ensure_time()
        request_id = self._next_id("clear")
        payload = self._base(request_id)
        payload["position"] = {"x": position[0], "y": position[1]}
        payload["channel"] = channel
        response = self._post("/clear", payload)
        self.position = (float(position[0]), float(position[1]))
        result = response["clear_result"]
        self._record(request_id, "clear", self.position, channel, result, response)
        return result == "success"

    def exit(self) -> None:
        if not self.entered:
            return
        try:
            request_id = self._next_id("exit")
            response = self._post("/exit", self._base(request_id))
            self._record(request_id, "exit", None, None, response["exit_reason"], response)
            print("已主动退出测试。")
        finally:
            self.entered = False


def main() -> int:
    parser = argparse.ArgumentParser(description="B题官方问题3演练基准运行器")
    parser.add_argument("--robot-id", required=True, help="当前登录模拟器的参赛队号")
    parser.add_argument("--base-url", default="http://127.0.0.1:2026", help="官方模拟器接口地址")
    parser.add_argument("--arena-id", default="default", help="接口 arena_id，正式测试如不同在此覆盖")
    parser.add_argument("--log", default="official_logs/baseline_actions.json", help="本程序动作日志位置")
    parser.add_argument("--verbose", action="store_true", help="打印骨架搜索进度")
    args = parser.parse_args()

    sim = OfficialSimulatorClient(args.base_url, args.robot_id, Path(args.log), args.arena_id)
    agent = SevenPointAgent(sim, verbose=args.verbose)
    try:
        summary = agent.run()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"本程序日志：{Path(args.log).resolve()}")
        return 0
    except Exception as exc:
        print(f"演练提前结束：{exc}", file=sys.stderr)
        print(f"已执行动作日志：{Path(args.log).resolve()}", file=sys.stderr)
        return 1
    finally:
        # 只要接口仍开放，尽量主动结束；超时后接口关闭时不会伪造成功。
        if sim.entered:
            try:
                sim.exit()
            except Exception as exc:
                print(f"无法调用 /exit：{exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())

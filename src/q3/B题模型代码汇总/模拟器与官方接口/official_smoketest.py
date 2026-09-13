"""官方 B 题模拟器的最小接口通路测试。

仅在模拟器已登录、已启动“问题3演练测试”、且界面提示接口就绪时运行。
队号必须通过 --robot-id 提供，程序中不保存队号。
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def post(base_url: str, path: str, payload: dict) -> dict:
    request = Request(
        base_url + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def base(robot_id: str, request_id: str, arena_id: str) -> dict:
    return {"arena_id": arena_id, "robot_id": robot_id, "request_id": request_id}


def action(robot_id: str, request_id: str, x: float, y: float, channel: int,
           arena_id: str) -> dict:
    payload = base(robot_id, request_id, arena_id)
    payload["position"] = {"x": x, "y": y}
    payload["channel"] = channel
    return payload


def require_accepted(response: dict, label: str) -> None:
    print(f"{label}: {json.dumps(response, ensure_ascii=False)}")
    if response.get("accepted") is not True:
        raise RuntimeError(f"{label} 未被模拟器接受；请检查登录队号、测试状态和接口开放状态。")


def main() -> int:
    parser = argparse.ArgumentParser(description="B题官方模拟器接口通路测试")
    parser.add_argument("--robot-id", required=True, help="当前登录模拟器的参赛队号")
    parser.add_argument("--base-url", default="http://127.0.0.1:2026", help="模拟器接口地址")
    parser.add_argument("--arena-id", default="default", help="接口 arena_id，如不同在此覆盖")
    parser.add_argument("--channel", type=int, default=1, choices=range(1, 21), help="测试检测频道")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    try:
        entered = post(base_url, "/enter", base(args.robot_id, "smoke-enter-1", args.arena_id))
        require_accepted(entered, "enter")
        print("本局现实剩余时间:", entered["remaining_real_duration_s"], "秒")

        measured = post(base_url, "/measure", action(
            args.robot_id, "smoke-measure-1", 0, 0, args.channel, args.arena_id))
        require_accepted(measured, "measure")
        print("检测结果:", measured["measure_result"])
        if measured["measure_result"] == "direction":
            print("示向度:", measured["svd_deg"], "度")

        exited = post(base_url, "/exit", base(args.robot_id, "smoke-exit-1", args.arena_id))
        require_accepted(exited, "exit")
        return 0
    except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
        print(f"接口测试失败: {exc}", file=sys.stderr)
        print("请确认：模拟器已登录；演练测试倒计时已结束；界面显示接口已就绪；队号与当前登录队号完全一致。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""把问题四 DAgent 接到官方模拟器 HTTP 接口。

仅在官方“问题4演练测试”倒计时结束、接口就绪后运行。队号只从命令行传入，
动作日志落盘前会自动脱敏。正式测试前必须先运行 official_q4_probe.py。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from d_agent import DAgent
from baseline_core import Action

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_DIR = ROOT / "outputs" / "q4" / "official_runs"


class RejectedAction(RuntimeError):
    pass


class OfficialQ4Client:
    """DAgent 所需的最小模拟器接口，并完整记录接受、拒绝和传输错误。"""

    def __init__(self, base_url, robot_id, log_path, arena_id="default"):
        self.base_url = base_url.rstrip("/")
        self.robot_id = robot_id
        self.arena_id = arena_id
        self.log_path = Path(log_path)
        self.position = (0.0, 0.0)
        self.current_channel = 1
        self.time_s = 0.0
        self.records = []
        self.actions = []
        self.final = None
        self.entered = False
        self.real_deadline = 0.0
        self.request_no = 0
        self.run_id = f"q4d-{int(time.time())}"

    def _next_id(self, kind):
        self.request_no += 1
        return f"{self.run_id}-{kind}-{self.request_no}"

    def _base(self, request_id):
        return {"arena_id": self.arena_id, "robot_id": self.robot_id,
                "request_id": request_id}

    @classmethod
    def _mask(cls, value):
        if isinstance(value, dict):
            return {key: ("TEAM_ID" if key == "robot_id" else cls._mask(item))
                    for key, item in value.items()}
        if isinstance(value, list):
            return [cls._mask(item) for item in value]
        return value

    def _save(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(json.dumps({
            "run_id": self.run_id,
            "base_url": self.base_url,
            "arena_id": self.arena_id,
            "records": self.records,
            "final": self.final,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def _record(self, path, request_id, payload, response=None, error=None):
        if isinstance(response, dict) and response.get("virtual_time_s") is not None:
            self.time_s = float(response["virtual_time_s"])
        self.records.append({
            "path": path,
            "request_id": request_id,
            "payload": self._mask(payload),
            "accepted": response.get("accepted") if isinstance(response, dict) else None,
            "response": self._mask(response),
            "error": error,
            "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        if isinstance(response, dict):
            kind = path.lstrip("/")
            raw_position = payload.get("position")
            position = ((float(raw_position["x"]), float(raw_position["y"]))
                        if raw_position is not None else None)
            channel = payload.get("channel")
            if kind == "measure":
                result = response.get("measure_result", "rejected")
            elif kind == "clear":
                result = response.get("clear_result", "rejected")
            elif kind == "exit":
                result = response.get("exit_reason", "accepted")
            else:
                result = "accepted" if response.get("accepted") else "rejected"
            self.actions.append(Action(kind, position, channel, result, self.time_s))
        try:
            self._save()
        except OSError as exc:
            print(f"警告：动作日志暂时无法落盘，内存记录仍保留：{exc}", file=sys.stderr)

    def _post(self, path, payload):
        last_error = None
        for attempt in range(2):
            try:
                request = Request(self.base_url + path,
                                  data=json.dumps(payload).encode("utf-8"),
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
                with urlopen(request, timeout=5) as response:
                    body = json.loads(response.read().decode("utf-8"))
                    if response.status != 200:
                        raise RuntimeError(f"HTTP {response.status}: {body}")
                    return body
            except HTTPError as exc:
                try:
                    detail = exc.read().decode("utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    detail = str(exc)
                last_error = f"HTTPError {exc.code}: {detail}"
                break  # 已收到明确 HTTP 响应，不重发动作
            except (URLError, TimeoutError, OSError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt == 0:
                    continue  # 仅对结果未知的传输失败使用相同 request_id 重试
        raise RuntimeError(last_error or f"{path} 请求失败")

    def request(self, path, payload, require_accepted=True):
        request_id = payload["request_id"]
        try:
            response = self._post(path, payload)
        except Exception as exc:
            self._record(path, request_id, payload, error=str(exc))
            raise
        self._record(path, request_id, payload, response=response)
        if require_accepted and response.get("accepted") is not True:
            raise RejectedAction(f"{path} 未被接受：{response}")
        return response

    def _ensure_time(self):
        if self.real_deadline and time.monotonic() >= self.real_deadline:
            raise TimeoutError("现实运行预算即将耗尽，停止新动作并尝试退出")

    def enter(self):
        request_id = self._next_id("enter")
        response = self.request("/enter", self._base(request_id))
        self.entered = True
        remaining = float(response["remaining_real_duration_s"])
        self.real_deadline = time.monotonic() + max(0.0, remaining - 10.0)
        print(f"已进入问题4测试；现实剩余 {remaining:.0f} 秒", flush=True)

    def measure(self, position, channel):
        self._ensure_time()
        request_id = self._next_id("measure")
        payload = self._base(request_id)
        payload.update({"position": {"x": float(position[0]), "y": float(position[1])},
                        "channel": int(channel)})
        response = self.request("/measure", payload)
        self.position = float(position[0]), float(position[1])
        self.current_channel = int(channel)
        return response["measure_result"], response.get("svd_deg")

    def probe_measure(self, position, channel):
        """探针专用：保留 accepted=false 响应，不把它转换为异常。"""
        request_id = self._next_id("probe")
        payload = self._base(request_id)
        payload.update({"position": {"x": float(position[0]), "y": float(position[1])},
                        "channel": int(channel)})
        response = self.request("/measure", payload, require_accepted=False)
        if response.get("accepted") is True:
            self.position = float(position[0]), float(position[1])
            self.current_channel = int(channel)
        return response

    def clear(self, position, channel):
        self._ensure_time()
        request_id = self._next_id("clear")
        payload = self._base(request_id)
        payload.update({"position": {"x": float(position[0]), "y": float(position[1])},
                        "channel": int(channel)})
        response = self.request("/clear", payload)
        self.position = float(position[0]), float(position[1])
        self.current_channel = int(channel)
        return response["clear_result"] == "success"

    def exit(self):
        if not self.entered:
            return
        try:
            request_id = self._next_id("exit")
            response = self.request("/exit", self._base(request_id))
            print(f"已退出：{response.get('exit_reason', 'accepted')}", flush=True)
        finally:
            self.entered = False


def default_log_path():
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return DEFAULT_LOG_DIR / f"D_official_{stamp}.json"


def main():
    parser = argparse.ArgumentParser(description="问题4官方演练：D模型运行器")
    parser.add_argument("--robot-id", required=True, help="当前登录官方模拟器的参赛队号")
    parser.add_argument("--base-url", default="http://127.0.0.1:2026")
    parser.add_argument("--arena-id", default="default")
    parser.add_argument("--log", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    log_path = (args.log or default_log_path()).resolve()
    client = OfficialQ4Client(args.base_url, args.robot_id, log_path, args.arena_id)
    agent = DAgent(client, verbose=args.verbose)
    try:
        summary = agent.run()
        client.final = {
            "status": "completed",
            "summary": summary,
            "origin_discoveries": agent.origin_discoveries,
            "selected_route": agent.selected_search_order,
            "pruned_observations": agent.pruned_observations,
            "coobservations": agent.coobservations,
        }
        client._save()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"动作日志：{log_path}")
        return 0
    except Exception as exc:  # noqa: BLE001
        client.final = {"status": "failed", "error_type": type(exc).__name__,
                        "error": str(exc)}
        try:
            client._save()
        except OSError:
            pass
        print(f"问题4演练提前结束：{type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"已执行动作日志：{log_path}", file=sys.stderr)
        return 1
    finally:
        if client.entered:
            try:
                client.exit()
            except Exception as exc:  # noqa: BLE001
                print(f"无法调用 /exit：{exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())

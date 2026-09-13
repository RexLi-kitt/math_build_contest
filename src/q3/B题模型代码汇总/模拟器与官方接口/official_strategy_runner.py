"""将第三问正式模型（A–I）接入官方“问题3演练测试”HTTP 接口。

运行前：官方模拟器已登录，已启动“问题3演练测试”，倒计时结束且接口就绪。
参赛队号只通过 --robot-id 传入，源码不保存队号。

用法（在“模拟器与官方接口”目录中）：

    python official_strategy_runner.py --robot-id "你的参赛队号" --strategy I_ring_optimized --verbose

日志默认写入 official_logs/<策略名>_actions.json。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from official_baseline_runner import OfficialSimulatorClient

STRATEGY_DIR = Path(__file__).resolve().parent.parent / "第三问策略对比"
sys.path.insert(0, str(STRATEGY_DIR))

from strategies import STRATEGIES  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="B题官方问题3演练：正式策略运行器")
    parser.add_argument("--robot-id", required=True, help="当前登录模拟器的参赛队号")
    parser.add_argument("--strategy", default="Jplus_final", choices=sorted(STRATEGIES),
                        help="第三问模型注册名，默认 I_ring_optimized")
    parser.add_argument("--base-url", default="http://127.0.0.1:2026",
                        help="官方模拟器接口地址")
    parser.add_argument("--arena-id", default="default",
                        help="接口 arena_id，正式测试如不同在此覆盖")
    parser.add_argument("--log", default=None,
                        help="动作日志路径，默认 official_logs/<策略名>_actions.json")
    parser.add_argument("--verbose", action="store_true", help="打印搜索进度")
    args = parser.parse_args()

    # Keep the default log location independent of the shell's working directory.
    # This also avoids a relative path being interpreted differently by a launcher.
    log_path = (Path(args.log).expanduser() if args.log else
                Path(__file__).resolve().parent / "official_logs" /
                f"{args.strategy}_actions.json").resolve()
    client = OfficialSimulatorClient(args.base_url, args.robot_id, log_path, args.arena_id)
    agent = STRATEGIES[args.strategy](client, verbose=args.verbose)
    try:
        summary = agent.run()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"策略：{args.strategy}")
        print(f"本程序日志：{log_path.resolve()}")
        return 0
    except Exception as exc:
        print(f"演练提前结束：{exc}", file=sys.stderr)
        print(f"已执行动作日志：{log_path.resolve()}", file=sys.stderr)
        return 1
    finally:
        # 只要接口仍开放就主动结束；正常跑完时 entered 已为 False，不会重复请求。
        if client.entered:
            try:
                client.exit()
            except Exception as exc:
                print(f"无法调用 /exit：{exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())

"""问题四官方接口探针：验证通路及半径超过1800 m的测量请求是否被接受。"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from official_d_runner import DEFAULT_LOG_DIR, OfficialQ4Client


def main():
    parser = argparse.ArgumentParser(description="问题4官方接口与1800米边界探针")
    parser.add_argument("--robot-id", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:2026")
    parser.add_argument("--arena-id", default="default")
    parser.add_argument("--channel", type=int, default=1, choices=range(1, 21))
    parser.add_argument("--radii", default="1799,1800,1801,1885,1966",
                        help="沿x轴依次探测的半径，逗号分隔；通路测试可传0")
    parser.add_argument("--log", type=Path, default=None)
    args = parser.parse_args()
    radii = [float(item.strip()) for item in args.radii.split(",") if item.strip()]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = (args.log or DEFAULT_LOG_DIR / f"Q4_probe_{stamp}.json").resolve()
    client = OfficialQ4Client(args.base_url, args.robot_id, log_path, args.arena_id)
    results = []
    try:
        client.enter()
        for radius in radii:
            response = client.probe_measure((radius, 0.0), args.channel)
            item = {"radius_m": radius, "accepted": response.get("accepted"),
                    "measure_result": response.get("measure_result"),
                    "virtual_time_s": response.get("virtual_time_s"),
                    "response": OfficialQ4Client._mask(response)}
            results.append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)
        client.final = {"status": "completed", "probe_results": results}
        client._save()
        return 0 if all(item["accepted"] is True for item in results) else 2
    except Exception as exc:  # noqa: BLE001
        client.final = {"status": "failed", "error_type": type(exc).__name__,
                        "error": str(exc), "probe_results": results}
        try:
            client._save()
        except OSError:
            pass
        print(f"探针失败：{type(exc).__name__}: {exc}")
        return 1
    finally:
        if client.entered:
            try:
                client.exit()
            except Exception as exc:  # noqa: BLE001
                print(f"无法调用 /exit：{exc}")
        print(f"探针日志：{log_path}")


if __name__ == "__main__":
    raise SystemExit(main())

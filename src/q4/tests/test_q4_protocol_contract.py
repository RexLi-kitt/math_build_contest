"""官方附件计时契约测试：复核 /measure、/clear、频道状态和 request_id 幂等语义。"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from engine.q4_local_simulator import LocalQ4Simulator


def main() -> None:
    sim = LocalQ4Simulator(seed=20260914, source_count=12, directional_ratio=.5)
    assert sim.enter("enter-1")["virtual_time_s"] == 0
    # 附件示例：500m移动+检测=105；原地换频道检测=111。
    assert sim.measure((300.0, 400.0), 1, "measure-1")["virtual_time_s"] == 105.0
    assert sim.measure((300.0, 400.0), 2, "measure-2")["virtual_time_s"] == 111.0
    # /clear 不切换测向频道；失败时为80s移动+3s精确定位，累计194。
    assert sim.clear((300.0, 0.0), 3, "clear-1")["virtual_time_s"] == 194.0
    assert sim.channel == 2
    assert sim.measure((300.0, 0.0), 2, "measure-3")["virtual_time_s"] == 199.0
    # 完全相同 request_id 重试不能推进虚拟时钟。
    duplicate = sim.measure((300.0, 0.0), 2, "measure-3")
    assert duplicate["virtual_time_s"] == 199.0
    assert sim.exit("exit-1")["exit_reason"] == "user_exit"
    print("Q4 本地协议计时与幂等契约测试通过：199 s")


if __name__ == "__main__":
    main()

"""问题4本地模拟器冒烟测试：验证时间、固定误差和三类测量返回均可记录。"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
Q4_SRC = HERE.parent
sys.path.insert(0, str(Q4_SRC))
from engine.q4_local_simulator import LocalQ4Simulator

OUT = HERE.parents[2] / "outputs" / "q4" / "tests" / "smoke"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sim = LocalQ4Simulator(seed=20260914, source_count=12, directional_ratio=.5)
    sim.enter("enter-1")
    # 不读取真值：扫描三个频道，演示 /measure 接口及虚拟时间累计。
    for index, channel in enumerate((1, 2, 3), 1):
        sim.measure((0.0, 0.0), channel, f"measure-{index}")
    sim.exit("exit-1")
    sim.export_log(OUT / "q4_local_smoke_log.json")
    print(sim.summary())


if __name__ == "__main__":
    main()


"""Q2 实验兼容入口。

所有候选点评分、基线对比、鲁棒性和图表生成统一由 solve_q2.main 实现，
避免实验入口和主程序使用不同的物理域或指标口径。
"""
from solve_q2 import main


if __name__ == "__main__":
    main()

# B 题模型代码汇总

本文件夹汇总 B 题三问的模型代码、离线实验与报告，供查看、复现与论文写作使用。

## 文件夹结构

```
B题模型代码汇总/
├── 模型架构与改进_A到I.md      # 三层架构、A–I 演进、关键公式、负消融、性能总表
├── 第二问/                     # Q1/Q2 求解、边界测试与输出
│   ├── src/q1/localization.py
│   ├── src/q2/{solve_q2.py, q1_q2_bridge.py, boundary_tests.py, README.md}
│   └── outputs/q2/tables/
├── 第三问策略对比/             # 第三问 A–I 模型、离线模拟器与配对实验
│   ├── baseline_core.py        # 离线模拟器 + A 模型 + 路由基础设施
│   ├── feasible_region.py      # 第二问可行域/最小包围圆的在线复用
│   ├── strategies.py           # B–I 模型与消融类
│   ├── run_compare.py          # 同一随机案例下的配对对比入口
│   ├── tune_cplus_weights.py   # 四指标权重筛选
│   ├── tune_coverage_rules.py  # 覆盖协同参数筛选
│   ├── reports/                # 各轮实验报告
│   └── results/                # 逐局结果与 summary.json
└── 模拟器与官方接口/           # 独立离线模拟器与官方 HTTP 演练脚本
    ├── b_robot_offline.py
    ├── official_smoketest.py
    ├── official_baseline_runner.py
    └── README.md
```

## 模型主线

第三问按 A–I 演进，完整说明见 `模型架构与改进_A到I.md`：

- A：最小二乘交点 + D-opt；B：第二问可行域 + 最小包围圆；C：四指标选点；
- C+：预计完成时间 + 顺便测量；D：混合信念 + 风险约束滚动；F：覆盖协同；
- G：逐动作滚动；I：覆盖环半径优化（当前最优，306.2 s/源，1000 局统一口径验证）。

C 到 I 的选点内核统一为第二问正式口径（粗搜→前二加密→只在加密集重评分，预测半径取均值），详见 `第三问策略对比/reports/第八轮第二问口径统一.md`。H（动作点路由 + 近终态不抢占）与覆盖环旋转、边际插入均为负消融，保留在代码中供论文引用。

## 运行

第三问（在 `第三问策略对比/` 中）：

```powershell
# 整条链，1000 局并行
python run_compare.py --cases 1000 --seed 55021 --strategies C_region_q2,Cplus_completion_coobserve,F_coverage_integrated,G_rolling_coverage,I_ring_optimized --output results/faithful_chain_1000 --jobs 16

# 单模型大样本
python run_compare.py --cases 1000 --seed 55021 --strategies I_ring_optimized --output results/i_1000 --jobs 16
```

第二问（在本文件夹根目录）：

```powershell
python 第二问\src\q2\solve_q2.py
python 第二问\src\q2\boundary_tests.py
```

`solve_q2.py` 需要 `matplotlib`；第三问离线对比只使用 Python 标准库。

官方接口与离线模拟：见 `模拟器与官方接口/README.md`。参赛队号只通过命令行参数传入，代码中未写死。

## 说明

- 第三问策略层不读取模拟器中的真实源位置；真值仅用于环境响应与统计。
- 可行域用外接 72 边形保守表示，清除判定使用保守最小包围圆（半径 ≤ 19.75 m）；几何内核已做缓存与内联加速，数值不变而决策耗时约降 5 倍。
- 全部第三问结果来自离线模拟器，不能替代官方演练；正式测试前须通过官方 HTTP 接口复核并保留回退策略。

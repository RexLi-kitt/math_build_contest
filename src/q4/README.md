# Q4：定向源风险回补与本地动作级验证

正式模型为 **V13：Q2 主动感知驱动的定向风险闭环清除模型**。Q2 的“首次正测向—主动选择第二测点—交会定位”是定位主链，Q4 仅增加定向可见性风险、多频道调度和定位失败回补。

## 1. 源码结构

```text
src/q4/
├─ README.md                 # 总入口、边界与复现说明
├─ docs/                     # 方案、模型、协议、时间账本、交接和文献说明
├─ engine/                   # 不读取源真值的本地动作级模拟器
├─ experiments/
│  ├─ run_q4_risk_belief_closed_loop.py  # V13 主程序
│  ├─ analysis/              # 发现层覆盖子集分析
│  └─ archive/               # 已停用的历史回放程序
├─ tests/                    # 动作冒烟测试与协议/计时契约测试
├─ versions/                 # V1–V13 迭代台账与唯一选型报告
├─ 核心代码段/               # 供论文附录和答辩展示的可读代码片段
└─ archive/                  # 旧版 RAHPS 兼容入口及历史字节码
```

各模块职责：

- `docs/`：论文与交接材料的唯一入口。文档包括方案卡、材料融合、风险信念策略、协议一致性、时间账本、模型交接和文献引用说明。
- `engine/`：实现 `enter / move / measure / clear / exit`，统一虚拟时间与动作返回；策略不得访问 `LocalQ4Simulator.sources`。
- `experiments/`：只放可运行实验。当前正式入口是 V13 主程序；覆盖分析和历史回放分别位于 `analysis/`、`archive/`。
- `tests/`：放最小回归测试，不承担正式结果生成。
- `versions/`：模型演化和正式选型的唯一依据。
- `核心代码段/`：从主程序提取的 Q2 主动二测、风险信念和保守清除认证片段。
- `archive/`：只用于追溯，不作为当前运行链路或正式结论。

## 2. 输出结构

```text
outputs/q4/
├─ README.md
├─ v13/                      # 当前唯一正式版本
│  ├─ figures/               # 8 组场景轨迹图（PNG、PDF）
│  ├─ tables/                # 闭环摘要、单源明细、稳定性验证
│  └─ logs/risk_belief_runs/ # 动作级 JSON 日志
├─ tests/smoke/              # 冒烟测试日志
├─ ablation/                 # 不进入正式结论的消融结果
└─ archive/                  # legacy、strict_coverage、旧 runner 结果
```

主程序通过 `Q4_OUTPUT_TAG` 控制一级目录；默认标签为 `v13`。新实验必须使用独立标签，不得覆盖 `v13/` 证据。

## 3. 复现命令

在项目根目录执行：

```powershell
python 已完成/src/q4/tests/smoke_test_local_simulator.py
python 已完成/src/q4/tests/test_q4_protocol_contract.py
python 已完成/src/q4/experiments/run_q4_risk_belief_closed_loop.py
```

前两项检查动作规则和附件计时契约；最后一项运行 V13 主策略。固定场景 `20260915` 的本地结果为 12/12 清除、虚拟时间 10124.851122 s、371 次检测、12 次清除尝试，平均单源定位清除时间 463.923133 s。`outputs/q4/v13/tables/Q4_Q2早触发稳定性验证.csv` 记录 8 组场景 96/96 清除，平均单源定位清除时间 537.583597 s。

以上均为本地规则模拟器结果，不是官方成绩，也不能替代官方演练或更大规模统计。

## 4. 阅读与修改顺序

1. `docs/Q4_方案卡.md`：题目约束和正式方法总览。
2. `versions/Q4_最优版本选型报告.md`：为什么只采用 V13。
3. `docs/Q4_模型交接.md`：当前边界、文件入口和复现命令。
4. `versions/Q4_版本迭代台账.md`：每个版本改了什么、结果如何、为何采用或拒绝。
5. `docs/Q4_风险信念策略说明.md` 与 `docs/Q4_时间账本与稳健优化分析.md`：论文表述、时间拆分和消融依据。

任何策略改动都必须新增版本记录、保留 CSV/JSON 证据，并明确是否成为正式主方案。旧版归档和消融结果不得覆盖 V13。

## 5. 共享旧模块说明

项目根目录中的 `rahps_core.py`、`validation_suite.py` 与 `output/validation/` 属于早期 RAHPS-B 的 **Q2/Q3/Q4 共享兼容材料**。它们不属于当前 V13，也不能仅因包含定向源逻辑而移动到 Q4 目录；若未来统一重构，应迁入独立的 `src/common/`，并同步修改 Q2、Q3 的导入路径。

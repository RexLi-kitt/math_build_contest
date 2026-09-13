# 压力情景鲁棒性实验结果目录

对应报告：`src/q3/第三问模型改进机制报告/07_压力情景鲁棒性报告.md`
图件：`outputs/q3/figures/Q3压力情景*`（png+pdf）

## 规模

7 情景（S0–S6）× 3 新种子（104729、130363、155921）× 每个种子 200 局 × 3 模型（I/J/J+）
= 12600 次运行，模型参数在实验前冻结。

## 文件

| 文件 | 内容 |
|---|---|
| `S0_baseline/` … `S6_compound/` | 每个情景下每个种子的 `case_results.csv`、`summary.json`、`failures.json` |
| `stress_case_results.csv` | 全部逐局逐模型结果（含硬约束与 16 项性能指标） |
| `stress_summary.csv` / `.json` | 情景 × 模型 × 种子/池化的汇总与分层 Bootstrap CI |
| `paired_effects.csv` / `.json` | I→J、J→J+、I→J+ 的配对收益、CI、胜负与分种子均值 |
| `failure_cases.json` | 硬约束失败案例（本次修正度量容差后为空） |
| `experiment_manifest.json` | 模型参数、种子、场景规则、代码哈希、Python 版本与起止时间 |

## 复现

```powershell
# 运行实验（项目 venv）
.venv\Scripts\python.exe src\q3\B题模型代码汇总\第三问策略对比\diagnostics\stress_robustness.py

# 重画图件
.venv\Scripts\python.exe src\q3\B题模型代码汇总\第三问策略对比\diagnostics\plot_stress_robustness.py
```

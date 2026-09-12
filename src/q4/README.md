# 问题四代码

本目录保存定向干扰源的离线实验、路线优化和 C+ 门控策略代码。

- `cplus_gate_agent.py`：当前推荐的 `CPlusAgent`；
- `run_cplus_gate_screen.py`：C/B 原点门控阈值筛选；
- `run_cplus_validation.py`：C+ 独立配对验证；
- `dynamic_order_agent.py` 与 `run_dynamic_order_screen.py`：D1 动态顺序的保留消融；
- 其余 `q4_*.py`、`run_route28.py`、`validate_routes.py`：原始离线实验与路线优化工具。

脚本默认将新结果写入 `outputs/q4/results/`。模型结论和使用说明见 `docs/q4/`。

# 问题四代码

本目录保存定向干扰源的离线实验、路线优化和当前 D 模型代码。

- `d_agent.py`：当前推荐的 `DAgent`，即冻结后的 C+3FB；
- `assets/d_model/`：D 使用的 B/C 认证站点与访问顺序，仓库可独立加载；
- `cplus_gate_agent.py`：历史 C+ 门控模型；
- `run_cplus_gate_screen.py`：C/B 原点门控阈值筛选；
- `run_cplus_validation.py`：C+ 独立配对验证；
- `run_d_robustness.py`：D 的10—16源回归、mixed分层、空间对抗、90°边界、
  多模式示向误差与逐次剪枝真值审计；
- `summarize_d_robustness.py`：把鲁棒性 JSON 汇总为可引用的 Markdown 报告；
- `dynamic_order_agent.py` 与 `run_dynamic_order_screen.py`：历史 DO 动态顺序消融；旧结果键 `D1` 仅作兼容；
- 其余 `q4_*.py`、`run_route28.py`、`validate_routes.py`：原始离线实验与路线优化工具。

脚本默认将新结果写入 `outputs/q4/results/`。模型结论和使用说明见 `docs/q4/`。

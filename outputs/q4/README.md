# 问题四输出

`results/` 保存第四问的离线筛选、压力测试和独立验证结果。

- `D模型数学公式.md`：D 模型的门控、可行域更新、距离剪枝、零漏检证明、覆盖证书、耗时目标与验收统计公式；
- `results/d_model/`：当前 D 模型从 C+3A、C+3F 到 C+3FB 的冻结证据和负消融；
- `cplus_gate_screen/` 与 `cplus_gate_screen100/`：C+ 阈值 0—3 的筛选结果；
- `cplus_holdout/`：C+ 的全新种子独立验证；
- `dynamic_*`：DO 动态顺序实验的筛选、回归和消融结果；文件内旧策略键为 `D1`。

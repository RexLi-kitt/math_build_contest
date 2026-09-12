# Q4 输出目录索引

## 1. 正式结果：`v13/`

- `v13/figures/`：V13 的 8 组随机场景轨迹图（PNG、PDF）；
- `v13/tables/`：V13 闭环摘要、单源时间明细和 8 场景稳定性验证；
- `v13/logs/risk_belief_runs/`：与三张结果表对应的动作级 JSON 日志。

V13 是当前唯一可用于论文主体的本地回归版本：8 组混合场景清除 96/96，平均单源定位清除时间为 537.583597 s。该结果不是官方模拟器成绩。

## 2. 测试与消融

- `tests/smoke/`：本地动作规则冒烟日志；
- `ablation/`：V12 不确定性分级等消融结果，不作为默认方案或正式结论。

## 3. 历史归档：`archive/`

- `archive/legacy/`：早期闭环失败案例、定向源回放、旧图表和旧日志；
- `archive/strict_coverage/`：严格三角覆盖兜底的图与日志，仅用于停止证书对照；
- `archive/legacy_runner/`：旧 RAHPS 验证结果。

归档材料不得作为 V13 正式结论引用。

## 4. 写入规则

主程序默认写入 `v13/`。新实验必须设置独立 `Q4_OUTPUT_TAG`，以下结构自动落到 `outputs/q4/<标签>/`：

```text
<标签>/
├─ figures/
├─ tables/
└─ logs/risk_belief_runs/
```

禁止用新实验覆盖 `v13/` 的图、表或日志。

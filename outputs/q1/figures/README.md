# Q1 等边三角形反例图

源数据：`src/q1/results/experiment_data.json`，算例 `EQ_LAST`。
绘图脚本：`src/q1/plot_equilateral.py`。
风格与字体：`.agents/skills/paper-plot-style`，调用 `apply_style()` 和 `save_figure()`。

| 文件前缀 | 内容 | 画布 |
|---|---|---|
| `equilateral_counterexample` | 实际定位三角形、同直径圆及理论最小外接圆，说明圆覆盖反例 | 15 × 14 cm |
| `equilateral_bearing_overview` | 三个实际监测点、示向方向与 ±1°边界、真实源点和定位区域位置 | 15 × 13 cm |

两张图均导出 PNG（300 dpi）与 PDF，保持坐标轴等比例，不自动裁边。

绘图不重新运行定位模型，顶点、最远点对对应的圆心、直径、监测点和示向度均读取已有结果。最小外接圆采用已有解析结果：本例理论等边三角形外心与 S=(0,0) 重合，半径20/√3米。实际浮点输出与理论顶点误差小于已约定的1e-8米，图中尺寸按合理精度标注。

总览图中，每条射线仅绘制900米长度以限制可视范围，不代表接收半径或新的定位约束。橙色框用于指出局部位置，不参与求解。坐标标签显示两位小数，绘图坐标未舍入。

复现：在仓库根目录运行 `.venv/Scripts/python.exe -m src.q1.plot_equilateral`。环境依赖与绘图技能的 `requirements.txt` 一致，不需重跑随机实验。

# 第三问输出索引

## 正式图件

- `figures/Q3模型演进拓扑图.png|pdf`：C—J+ 模型主线及负消融拓扑。
- `figures/Q3模型七项指标对比表.png|pdf`：各代模型七项回测指标。
- `figures/Q3模型迭代收益瀑布图.png|pdf`：C—J+ 每一步的边际耗时收益及累计降幅。
- `figures/J+真实路线案例_seed24119_case231.png|pdf`：J+ 在代表性单局中的实际搜索、定位与清除路线。
- `figures/全知条件最快走线_seed24119_case231.png|pdf`：同一案例在全知条件下的最短开放访问路线。

## 数据证据

- `data/J+真实路线案例_seed24119_case231.json`：真实源坐标、动作日志与单局结果。
- `data/全知条件最快走线_seed24119_case231.json`：全知路线顺序、距离与耗时分解。

## 说明文档

- `J+模型公式以及架构.md`：J+ 的公式、结构与实现口径。

图件由 `src/q3/plot_model_evolution.py` 和 `src/q3/plot_jplus_route_case.py` 生成。

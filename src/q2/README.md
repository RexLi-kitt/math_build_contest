# Q2：四指标主动第二检测点选择模型

本实现以 `Q2_方案卡.md` 为唯一口径。Q1 仅复用角度误差带的半平面构造方法；Q2 独立建立物理可行域：

\[
A_1=\{G:|\operatorname{wrap}(\theta(G,S_1)-\hat\theta_1)|\le1^\circ,\ \|G\|\le1800,\ 5<\|G-S_1\|\le1500\}.
\]

对候选点，代码仅在 \(\|G_j-S_2\|\le1000\) 的保证接收样本上计算预测 MEC 半径；保证接收样本为零的候选点直接淘汰。几何质量、保证接收比例、移动时间、预测 MEC 分别作 min-max 归一化后，以四指标加权目标选点。候选集先作全方位粗搜索，再对前两名作距离与方位局部加密。

粗网格只承担全局寻优：先以较大距离、方位步长找到前两处高分中心；随后仅在这些中心的距离、方位邻域内生成局部加密集 \(\mathcal C_{\rm ref}\)。最终必须在 \(\mathcal C_{\rm ref}\) 上重新作 min-max 归一化和评分，不能把粗网格点混入最终候选区域。

不将候选区域简化为单一点。令 \(J^*=\max_{s\in\mathcal C_{\rm ref}}J(s)\)，以 \(\eta=0.10\) 定义

\[
\mathcal R_{\rm good}=\{s\in\mathcal C_{\rm ref}:J(s)\ge(1-\eta)J^*\}.
\]

`Q2候选区域.csv` 给出区域内全部离散点；实际执行时在其中选择移动时间最短的点。这样既保留高质量观测构型的备选空间，也避免为极小评分差付出不必要的移动代价。

二测 `direction` 时按 \(A_2=A_1\cap B_2\) 更新；MEC 不超过20m时才前往圆心附近清除。`near` 直接清除；`no_signal` 只从样本域排除以当前点为圆心、半径1000m内的区域，绝不把1000--1500m的无信号解释为硬约束。

## 权重的外层校准

内层选点目标为

\[
J=w_1\widetilde Q_{\rm geo}+w_2\widetilde P_{\rm rec}
-w_3\widetilde T_{\rm move}-w_4\widetilde R_{\rm pred},
\qquad w_i\ge0,\quad\sum_{i=1}^{4}w_i=1.
\]

其中四项均在同一候选集中作 min-max 归一化，因此权重可解释为四项任务目标的相对重要度，而不是米、秒等不同量纲的补偿系数。当前 `W=(0.35,0.30,0.15,0.20)` 只是离线示例权重，不能在论文中写成主观指定。

论文正式实验采用“外层蒙特卡洛—网格搜索”确定权重：每轮随机生成真源位置、接收半径 \(r\in[1000,1500]\) m 与两次测向误差；内层以候选权重选择 \(S_2\)，记录二测后的 MEC、接收结果和总时间。对每个满足单纯形约束的权重组，以

\[
L(\mathbf w)=0.40\frac{\overline R_{\rm mec}}{20}
+0.35(1-\overline P_{\rm recv})
+0.25\frac{\overline T_{\rm total}}{T_0}
\]

评价；选取 \(L\) 最小且在各权重 ±10% 后重新归一化仍稳定的权重组。这里 \(T_0\) 使用最近点基线的平均任务时间，故外层损失的三项可公平比较。

运行：

```text
python src/q2/solve_q2.py
python src/q2/boundary_tests.py
node src/q2/build_q2_workbook.mjs
```

输出：`outputs/q2/figures/` 含 A1、四指标评分和 A2 图；`outputs/q2/tables/` 含候选分解、敏感性、闭环检验、边界测试及 Excel 汇总。

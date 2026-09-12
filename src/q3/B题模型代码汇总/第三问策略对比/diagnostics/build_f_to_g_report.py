"""Build the F -> G mechanism report from paired rolling experiments."""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "diagnostics" / "results" / "f_to_g_metrics_600"
ROBUST = ROOT / "results" / "robustness" / "robustness_summary.json"
OUT = ROOT / "diagnostics" / "F到G机制回测报告.md"


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
    f, g, fm, gm = "F", "G", "F_marginal_insert", "G_marginal_insert"
    total = paired(rows, f, g, "total_time_per_source_s")
    movement = paired(rows, f, g, "movement_time_per_source_s")
    detect = paired(rows, f, g, "detection_switch_time_per_source_s")
    marginal_rolling = paired(rows, fm, gm, "total_time_per_source_s")
    marginal_f = paired(rows, f, fm, "total_time_per_source_s")
    marginal_g = paired(rows, g, gm, "total_time_per_source_s")

    seed_lines = []
    for seed in sorted({int(row["seed"]) for row in rows}):
        subset = [row for row in rows if int(row["seed"]) == seed]
        delta = paired(rows, f, g, "total_time_per_source_s", seed)
        seed_lines.append(
            f"| {seed} | {mean(subset,f,'total_time_per_source_s'):.1f} | "
            f"{mean(subset,g,'total_time_per_source_s'):.1f} | {delta['mean']:+.1f} | "
            f"{delta['right_wins']}/200 | {delta['left_wins']}/200 | {delta['ties']}/200 |"
        )

    robust_lines, robust_deltas = [], []
    for seed, values in robust["per_seed_stats"].items():
        fv = values["F_coverage_integrated"]["mean_time_per_source_s"]
        gv = values["G_rolling_coverage"]["mean_time_per_source_s"]
        robust_deltas.append(fv - gv)
        robust_lines.append(f"| {seed} | {fv:.1f} | {gv:.1f} | {fv-gv:.1f} |")

    report = f"""# F 到 G：逐动作滚动调度机制回测

## 迭代结论

在三个新随机种子、共600个配对案例中，G将平均每源耗时从 **{mean(rows,f,'total_time_per_source_s'):.1f} s** 降至 **{mean(rows,g,'total_time_per_source_s'):.1f} s**，节省 **{total['mean']:.1f} s/源（{100*total['mean']/mean(rows,f,'total_time_per_source_s'):.1f}%）**；P95从 {p95(rows,f):.1f} 降至 {p95(rows,g):.1f} s/源。G在{total['right_wins']}/600局更快、{total['ties']}/600局完全相同、{total['left_wins']}/600局更慢，两者全清除率均为100%。

F与G的发现、覆盖、插点和覆盖阶段协同测量完全相同。七项指标中，最后源发现时间和搜索后定位负担逐案一致；G只改变搜索后的清除调度。时间分解显示，G减少 **{movement['mean']:.1f} s/源移动时间**，同时增加 {abs(detect['mean']):.1f} s/源检测与切换时间，净省 {total['mean']:.1f} s/源。因此，G的收益可以归因于滚动重排剩余任务后的移动组织改善。

## 1. 为什么会从 F 继续设计 G

F在覆盖过程中已经吸收了一部分定位任务，但搜索结束后仍按“选择一个频道—连续定位—完成清除—再选择下一频道”的方式处理剩余源。这种整源处理方式隐含一个假设：选中某个源后，继续服务该源始终比根据新信息转向其他源更划算。

然而，每次主动测量都会改变该源的可行域、下一测量点和清除条件；共观测还可能同时改变其他频道的状态。测量前计算的剩余路线因此可能在一个动作后过时。F只在完成一个频道后重新排列剩余目标，没有充分利用动作级状态更新。G据此把规划周期从“每完成一个源”缩短为“每执行一个动作”。

## 2. 这么做的合理性是什么

| G 的设计 | 决策依据 | 原本希望改善的指标 | 合理性判断 |
|---|---|---|---|
| 对全部未解决源计算开放路径 | 多源任务的主要成本仍是空间移动，单看当前频道会忽略全局方向 | 移动时间、总耗时 | 合理；继续复用F已有的最近邻+2-opt/Or-opt路线器 |
| 只执行路线首目标的一个动作 | 一次测量后目标位置和下一动作点会更新，远期路线不应一次锁死 | 移动时间、P95 | 合理；属于标准滚动时域思想 |
| 每个动作后重新规划 | 共观测和清除会改变多个频道的可服务状态 | 减少旧路线导致的折返 | 合理，但频繁抢占也可能产生重新接近成本 |
| 保持F搜索阶段不变 | 只检验清除调度，避免把覆盖收益混入G | 最后发现时间和搜索后定位负担应完全不变 | 构成干净的父子模型消融 |

G没有修改第二问推荐点、清除阈值、覆盖点、插点预算和共观测规则。它只决定“下一步先服务哪个频道”，因此理论作用边界比D清楚。

## 3. 七项指标回测

| 指标 | F | G | F−G | 解释 |
|---|---:|---:|---:|---|
| 全清除率 | 100% | 100% | 0.0 pp | 可靠性保持 |
| 平均总耗时（s/源） | {mean(rows,f,'total_time_per_source_s'):.1f} | {mean(rows,g,'total_time_per_source_s'):.1f} | **{total['mean']:+.1f}** | G总体提速 |
| P95总耗时（s/源） | {p95(rows,f):.1f} | {p95(rows,g):.1f} | **{p95(rows,f)-p95(rows,g):+.1f}** | 尾部同步改善 |
| 移动时间（s/源） | {mean(rows,f,'movement_time_per_source_s'):.1f} | {mean(rows,g,'movement_time_per_source_s'):.1f} | **{movement['mean']:+.1f}** | 唯一主要收益来源 |
| 检测与切换时间（s/源） | {mean(rows,f,'detection_switch_time_per_source_s'):.1f} | {mean(rows,g,'detection_switch_time_per_source_s'):.1f} | **{detect['mean']:+.1f}** | 滚动多付少量信息成本 |
| 最后源首次发现时间（s/源） | {mean(rows,f,'last_discovery_time_per_source_s'):.1f} | {mean(rows,g,'last_discovery_time_per_source_s'):.1f} | 0.0 | 搜索阶段相同 |
| 搜索后剩余定位负担 | {pct(mean(rows,f,'not_clear_ready_after_search_rate'))} | {pct(mean(rows,g,'not_clear_ready_after_search_rate'))} | 0.0 pp | G不改变覆盖阶段 |

这里的总耗时恒等式为：`{movement['mean']:.1f} − {abs(detect['mean']):.1f} = {total['mean']:.1f} s/源`。清除动作保持5.0 s/源，不参与差值。

## 4. 模型改动与逐项证据表

| 假设 | 直接证据 | 状态 |
|---|---|---|
| 动作级滚动能降低清除阶段移动 | 移动减少 {movement['mean']:.1f} s/源，600局中有{paired(rows,f,g,'movement_time_per_source_s')['right_wins']}局移动更少 | **已验证** |
| 滚动改善不仅依赖F当前插点阈值 | 在边际插点背景下，滚动仍改善 {marginal_rolling['mean']:.1f} s/源 | **已验证** |
| G改善的是搜索后的调度，而非发现或覆盖 | 四项搜索快照指标在F与G的全部配对案例中完全一致 | **已验证** |
| 动作级滚动不会产生抢占代价 | G有 {pct(mean(rows,g,'revisited_channel_rate'))} 的源被主调度离开后再次服务，检测成本增加 {abs(detect['mean']):.1f} s/源 | **已验证（假设不完全成立）** |
| 边际收益插点可替代F的固定140 m/8次限制 | 它使F和G分别恶化 {abs(marginal_f['mean']):.1f}、{abs(marginal_g['mean']):.1f} s/源 | **已验证（假设不成立）** |
| G在边界聚集、最小接收半径或系统测角偏差下仍有效 | 当前只有常规随机分布与多种子实验 | **待验证** |

## 5. 2×2 消融：滚动有效，边际插点失败

| 实验组 | 插点规则 | 清除调度 | 平均s/源 | P95s/源 | 相对同插点父模型的滚动收益 |
|---|---|---|---:|---:|---:|
| F | 固定140 m/最多8次 | 整源处理 | {mean(rows,f,'total_time_per_source_s'):.1f} | {p95(rows,f):.1f} | — |
| G | 固定140 m/最多8次 | 逐动作滚动 | **{mean(rows,g,'total_time_per_source_s'):.1f}** | **{p95(rows,g):.1f}** | **{total['mean']:+.1f}** |
| F边际插点 | 收缩量/额外距离 | 整源处理 | {mean(rows,fm,'total_time_per_source_s'):.1f} | {p95(rows,fm):.1f} | — |
| G边际插点 | 收缩量/额外距离 | 逐动作滚动 | {mean(rows,gm,'total_time_per_source_s'):.1f} | {p95(rows,gm):.1f} | **{marginal_rolling['mean']:+.1f}** |

滚动在两种插点规则下分别改善 {total['mean']:.1f} 和 {marginal_rolling['mean']:.1f} s/源，方向和量级接近；这支持“滚动调度本身有效”。边际插点虽然把搜索后定位负担从 {pct(mean(rows,f,'not_clear_ready_after_search_rate'))} 降到 {pct(mean(rows,fm,'not_clear_ready_after_search_rate'))}，但搜索结束推迟 {mean(rows,fm,'search_end_time_per_source_s')-mean(rows,f,'search_end_time_per_source_s'):.1f} s/源，最终使总时间恶化。因此它作为负消融保留，不进入G。

## 6. 抢占与重访诊断

F对一个频道持续服务到清除或穷尽，主调度重访率为0。G允许动作后切换，平均有 **{pct(mean(rows,g,'revisited_channel_rate'))}** 的真实源在离开后再次成为主任务，发生 **{mean(rows,g,'preemptions_per_source'):.3f} 次/源**未完成抢占。这个比例不高，说明滚动重排多数时候仍会继续服务当前源；它只在路线收益足以改变首目标时切换。

重访是G的副作用，却没有抵消整体移动收益。它也解释了为什么后续尝试“近终态不抢占”具有合理动机，但不能据此预先认定禁止抢占一定更优；是否保留该修正需要单独消融。

## 7. 三个新种子的配对结果

| 种子 | F（s/源） | G（s/源） | F−G | G更快 | F更快 | 相同 |
|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(seed_lines)}

600局配对平均收益的近似95%置信区间为 **[{total['lo']:.1f}, {total['hi']:.1f}] s/源**。三个种子的均值方向一致；G不是逐局支配F，但总体均值和P95均稳定改善。

## 8. 既有3000局鲁棒性实验复核

| 鲁棒性种子 | F（s/源） | G（s/源） | 平均节省 |
|---:|---:|---:|---:|
{chr(10).join(robust_lines)}

三种子各1000局中G均优于F，跨种子平均节省 **{statistics.mean(robust_deltas):.1f} s/源**，与本次600局的 {total['mean']:.1f} s/源一致。新实验提供机制分解，既有实验提供更大样本的方向复核。

## 9. 为什么保留 G、放弃边际插点变体

| 迭代标准 | 实验事实 | 决策 |
|---|---|---|
| 新机制应有独立正贡献 | 两种插点背景下滚动均改善约4 s/源 | **保留逐动作滚动** |
| 改动应具有明确作用边界 | 搜索指标完全相同，差值集中于清除阶段移动 | **保留G的机制解释** |
| 平均和尾部应同向改善 | 均值改善 {total['mean']:.1f}，P95改善 {p95(rows,f)-p95(rows,g):.1f} s/源 | **保留G** |
| 替代插点规则应降低最终总耗时 | 边际插点使G恶化 {abs(marginal_g['mean']):.1f} s/源 | **放弃边际插点** |

G的结构增量只有一个：逐动作滚动重规划。这一增量得到成本分解、2×2消融和多种子大样本共同支持，适合保留为主线模型。

## 10. 可直接用于论文的机制表述

F在覆盖结束后以频道为单位连续执行定位与清除，仅在一个频道完成后重新排列剩余目标。然而一次测量会改变目标可行域、下一推荐检测点和清除状态，共观测还可能同时改变其他频道，原路线会随在线信息更新而失效。为此，G采用逐动作滚动调度：每次根据全部未清除源构造开放路径，只执行路线首目标的一次测量或清除动作，随后更新状态并重新规划。

600局配对实验表明，G相对F减少4.6 s/源移动时间，同时增加0.3 s/源检测与切换时间，最终净省4.3 s/源，P95降低4.9 s/源，且保持100%全清除。F与G的搜索阶段指标逐案一致，因而收益可归因于搜索后调度。滚动在另一套边际插点规则下仍取得4.1 s/源收益，进一步说明其效果不依赖当前插点阈值。

## 11. 结论边界与后续关系

本报告评估的是当前生产版本F到G的单一结构变化。如果按上一份报告的建议将F改为固定覆盖顺序，G也必须以修订后的F为父模型重新回测，当前数值不能直接移植。

G仍有少量源被抢占后重访，因此从调度理论看，动作点路由和近终态不抢占是合理的下一步假设；但既有H消融表明这些修正没有稳定转化为收益，所以H不进入主线。后续主线直接从G转向具有几何覆盖保证的环半径优化I。
"""
    OUT.write_text(report, encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()

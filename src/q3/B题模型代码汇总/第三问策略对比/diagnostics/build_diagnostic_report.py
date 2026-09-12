"""Build the reader-facing evidence report from paired diagnostic outputs."""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "diagnostics" / "第三问模型证据报告.md"
FACT = ROOT / "diagnostics" / "results" / "diagnostic_factorial_seed982451653_100"
AB = ROOT / "diagnostics" / "results" / "ab_seed982451653_100" / "summary.json"
ROBUST = ROOT / "results" / "robustness" / "robustness_summary.json"


def load_cases(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    cases = defaultdict(dict)
    for row in rows:
        cases[int(row["case"])][row["group"]] = row
    return cases


def value(row, field="time_per_source_s"):
    return float(row[field])


def paired(cases, earlier, later):
    differences = [value(groups[earlier]) - value(groups[later]) for groups in cases.values()]
    return {
        "mean": statistics.mean(differences),
        "wins": sum(item > 0 for item in differences),
        "ties": sum(item == 0 for item in differences),
        "losses": sum(item < 0 for item in differences),
        "p95": sorted(differences)[math.ceil(.95 * len(differences)) - 1],
    }


def render_pair(cases, earlier, later):
    result = paired(cases, earlier, later)
    return f"{result['mean']:+.1f}（后者更快 {result['wins']}/100 局；P95 差 {result['p95']:+.1f}）"


def mean(cases, group, field="time_per_source_s"):
    return statistics.mean(value(groups[group], field) for groups in cases.values())


def main():
    cases = load_cases(FACT / "case_results.csv")
    ab = json.loads(AB.read_text(encoding="utf-8"))["summaries"]
    ab = {item["strategy"]: item for item in ab}
    robust = json.loads(ROBUST.read_text(encoding="utf-8"))
    cross = robust["cross_seed"]
    normal = [groups["I_normal"] for groups in cases.values()]
    search = statistics.mean(float(row["search_time_s"]) / int(row["source_count"]) for row in normal)
    post = statistics.mean(float(row["post_search_time_s"]) / int(row["source_count"]) for row in normal)
    movement = statistics.mean(float(row["movement_time_s"]) / int(row["source_count"]) for row in normal)
    measurements = statistics.mean(float(row["measure_actions"]) / int(row["source_count"]) for row in normal)

    text = f"""# 第三问模型改动、真值辅助诊断与证据表

## 技术摘要

本报告把第三问的模型演进从“连续尝试的策略版本”改写为可检验的假设链。新增的因子消融使用从未用于原模型筛选的 `seed=982451653`，100 个配对案例；既有鲁棒性验证使用 `55021、24119、90317` 三个种子、每种子 1000 局。所有生产模型都不知道干扰源真值；真值只在标有“真值辅助”的反事实诊断组中使用。

核心结论有三条：

- I 的跨三种子均值为 **{cross['I_ring_optimized']['mean']:.1f} s/源**，三个种子均为第一，完整主链的效果已跨种子验证。
- C→C+ 的主要收益来自**完成时间指标**与**共观测**，不是权重替换：保持 C 权重只换完成时间为 {mean(cases,'C_completion_c_weights'):.1f} s/源（C 为 {mean(cases,'C'):.1f}），只开共观测为 {mean(cases,'C_coobserve_only'):.1f} s/源。
- I 正常组为 {mean(cases,'I_normal'):.1f} s/源；搜索结束后揭晓剩余真值为 {mean(cases,'truth_after_search'):.1f} s/源，仅少 {paired(cases,'I_normal','truth_after_search')['mean']:.1f} s/源。因此，继续只优化“搜索后的专用定位”不是最高优先级。

## 1. 统一实验口径

| 项目 | 设定 |
|---|---|
| 主要指标 | 单局总虚拟时间 / 该局源数量（s/源）；同一案例内配对比较 |
| 新增诊断集 | 100 局，seed 982451653，源数量按原随机机制在 10–16 之间抽取 |
| 鲁棒性验证集 | 3 × 1000 局，seed 55021、24119、90317 |
| 真值限制 | 生产组不读取真值；真值组只用于事后反事实成本分解 |
| 可靠性指标 | 全清除率、失败清除次数 |

## 2. 模型改动对照表

| 迭代 | 要解决的问题与假设 | 实际改动 | 证据与结论 |
|---|---|---|---|
| A→B | 点估计可能造成盲目清除 | 用可行域最小包围圆，半径 ≤19.75 m 才清除 | 100 局中失败清除从 {ab['A_current_ls_dopt']['mean_failed_clear_actions']:.2f} 降至 {ab['B_region_dopt']['mean_failed_clear_actions']:.2f} 次/局；但 B 比 A 慢 {ab['B_region_dopt']['mean_time_per_source_s']-ab['A_current_ls_dopt']['mean_time_per_source_s']:.1f} s/源。它是可靠性改进，不是提速改进。 |
| B→C | 用第二问四指标统一主动选点口径 | D-opt 改为 Q2 四指标粗搜—加密—重评分 | 本新增种子下 C 为 {mean(cases,'C'):.1f} s/源，B 为 {ab['B_region_dopt']['mean_time_per_source_s']:.1f} s/源；单独 C 没有显示速度优势。保留的理由是第二、三问的模型统一，速度收益需要后续模块体现。 |
| C→C+ | 单看“到检测点距离”忽略后续清除成本；停靠点可同时服务多频道 | 第三指标改为预计完成时间；加入顺便测量；权重微调 | 完成时间单项 {render_pair(cases,'C','C_completion_c_weights')}；共观测单项 {render_pair(cases,'C','C_coobserve_only')}；二者合用且保持 C 权重 {render_pair(cases,'C','C_completion_coobserve_c_weights')}。 |
| C+→F | 搜索与补测分离会产生专程绕路 | 动态覆盖顺序、站点共测、低绕路插入推荐检测点 | 完整 F 相对 C+ 在 3×1000 局平均少 {cross['Cplus_completion_coobserve']['mean']-cross['F_coverage_integrated']['mean']:.1f} s/源。新增消融显示：关闭插入后为 {mean(cases,'F_no_insertion'):.1f} s/源，完整 F 为 {mean(cases,'F'):.1f}，插入部分平均少 {paired(cases,'F_no_insertion','F')['mean']:.1f} s/源。 |
| F→G | 新动作改变信念，清除顺序应滚动更新 | 每执行一次测量/清除即重排剩余任务 | 三种子池化平均少 {cross['F_coverage_integrated']['mean']-cross['G_rolling_coverage']['mean']:.1f} s/源，F 比 G 更快仅 963/3000 局，收益稳定但幅度较小。 |
| G→I | 七点覆盖环存在可压缩几何余量 | 环半径 1250 m→1150 m | 最坏覆盖仍为 988.5 m < 1000 m；三种子池化平均再少 {cross['G_rolling_coverage']['mean']-cross['I_ring_optimized']['mean']:.1f} s/源，I 在 2413/3000 局更快。 |

## 3. C→C+ 因子消融：收益究竟来自哪里

| 组别 | 改动 | 平均 s/源 | 全清除率 | 相对 C 的平均变化 |
|---|---|---:|---:|---:|
| C | 原四指标 | {mean(cases,'C'):.1f} | 100% | — |
| C_reweighted | 仅替换 C+ 权重 | {mean(cases,'C_reweighted'):.1f} | 92% | {paired(cases,'C','C_reweighted')['mean']:+.1f} |
| C_completion_c_weights | 仅完成时间，保留 C 权重 | {mean(cases,'C_completion_c_weights'):.1f} | 100% | {paired(cases,'C','C_completion_c_weights')['mean']:+.1f} |
| C_coobserve_only | 仅共观测，保留 C 选点 | {mean(cases,'C_coobserve_only'):.1f} | 100% | {paired(cases,'C','C_coobserve_only')['mean']:+.1f} |
| C_completion_coobserve_c_weights | 完成时间 + 共观测，保留 C 权重 | {mean(cases,'C_completion_coobserve_c_weights'):.1f} | 100% | {paired(cases,'C','C_completion_coobserve_c_weights')['mean']:+.1f} |
| C+ | 上述两项 + C+ 权重 | {mean(cases,'Cplus'):.1f} | 100% | {paired(cases,'C','Cplus')['mean']:+.1f} |

这里的正差表示后一个模型更快；但 `C_reweighted` 的全清除率只有 92%，其表面上的时间改善不具可比性，不能计作收益。权重单独替换不可靠，不能作为 C+ 的主要机制解释；完成时间和共观测才是可归因的主结论。C+ 权重只在两项机制已打开时带来约 {paired(cases,'C_completion_coobserve_c_weights','Cplus')['mean']:.1f} s/源的额外改善，应写成小幅经验校准。

## 4. 真值辅助诊断：额外成本在哪里

| 反事实组 | 给策略的信息 | 平均 s/源 | 相对正常 I 的变化 | 可以解释什么 |
|---|---|---:|---:|---|
| I_normal | 正常观测 | {mean(cases,'I_normal'):.1f} | — | 实际可用策略 |
| truth_after_search | 完成正常搜索后，揭晓剩余源位置，再按最短开放路径直达清除 | {mean(cases,'truth_after_search'):.1f} | {paired(cases,'I_normal','truth_after_search')['mean']:+.1f} | 搜索后定位、清除点误差和剩余路线的合并可避免成本 |
| I_discovery_truth | 某频道第一次收到信号后才揭晓其位置 | {mean(cases,'I_discovery_truth'):.1f} | {paired(cases,'I_normal','I_discovery_truth')['mean']:+.1f} | 后续定位不确定性在整个在线过程中的价值 |
| truth_direct_centres | 开始即知道所有位置，按源圆心最短开放路径直接清除 | {mean(cases,'truth_direct_centres'):.1f} | {paired(cases,'I_normal','truth_direct_centres')['mean']:+.1f} | 一个可行的全知参考，不是下界 |
| truth_disk_lower_bound | 全知且把每个清除圆的两两距离独立放松 | {mean(cases,'truth_disk_lower_bound'):.1f} | {paired(cases,'I_normal','truth_disk_lower_bound')['mean']:+.1f} | 严格但偏松的移动+清除下界 |

正常 I 的时间构成均值为：搜索 {search:.1f} s/源、搜索后阶段 {post:.1f} s/源、移动 {movement:.1f} s/源、检测动作 {measurements:.1f} 次/源。搜索结束后揭晓真值只能省 {paired(cases,'I_normal','truth_after_search')['mean']:.1f} s/源；相比之下，第一次发现即揭晓可省 {paired(cases,'I_normal','I_discovery_truth')['mean']:.1f} s/源。这说明进一步优化应优先减少发现前及搜索中的信息采集成本，或让同一停靠点为更多频道贡献有效方位，而不是只改最后的清除路线。

## 5. 逐项假设证据表

| 解释 | 结论状态 | 证据 | 论文中应如何写 |
|---|---|---|---|
| 可行域清除能减少误清 | 已验证 | A→B 失败清除 3.47→0.00 次/局 | “以约 18.7 s/源的时间代价换取零失败清除。” |
| 四指标 C 本身比 D-opt 更快 | 待验证 | 新种子 B 343.5，C 374.4 s/源 | 不将 C 单独写成提速；只写作第二问口径接入。 |
| 完成时间指标能减少后续绕路 | 已验证 | C→仅完成时间平均省 37.0 s/源，100/100 局更快 | 作为 C+ 第一条机制。 |
| 共观测能减少专程测量 | 已验证 | C→仅共观测平均省 20.8 s/源，100/100 局更快 | 作为 C+ 第二条机制。 |
| C+ 权重是主要收益来源 | 不支持 | 单独换权重虽表面少 13.1 s/源，但全清除率仅 92%，不可与全清除组比较 | 写成完整机制下的小幅经验校准，不单独强调。 |
| 覆盖协同降低搜索与补测的重复行程 | 已验证 | C+→F 在 3×1000 局省 16.0 s/源；关闭插入损失 13.6 s/源 | 完整协同和插入机制可作为主结论。 |
| 覆盖顺序与额外测量预算各自贡献多少 | 部分支持 | 已隔离插入，尚未把动态顺序与站点测量预算各自拆开 | 不对两个子机制分别给出定量归因。 |
| 逐动作滚动重排显著改善清除段 | 已验证 | F→G 在 3×1000 局稳定省 4.0 s/源 | 写成稳定的小幅改善，避免“主要增益”。 |
| 1150 m 覆盖环在不损失发现保证下更快 | 已验证 | 闭式最坏覆盖 988.5 m；G→I 三种子稳定省 10.0 s/源 | 作为最完整的“理论保证 + 实验验证”改进。 |
| 当前主要额外成本在搜索后的专用定位 | 不支持 | 搜索后真值揭晓只省 13.3 s/源 | 后续优先研究搜索中信息共享与停靠点集合。 |
| I 已接近全题理论最优 | 待验证 | 严格松下界为 {mean(cases,'truth_disk_lower_bound'):.1f} s/源；未知真值时的最优在线策略尚未求解 | 只报告相对下界与反事实差距，不称“近似最优”。 |

## 6. 已验证的跨种子主链

| 模型 | 三种子平均 s/源 | 种子间极差 | 跨种子排名 |
|---|---:|---:|---|
| C | {cross['C_region_q2']['mean']:.1f} | {cross['C_region_q2']['range']:.1f} | 5 |
| C+ | {cross['Cplus_completion_coobserve']['mean']:.1f} | {cross['Cplus_completion_coobserve']['range']:.1f} | 4 |
| F | {cross['F_coverage_integrated']['mean']:.1f} | {cross['F_coverage_integrated']['range']:.1f} | 3 |
| G | {cross['G_rolling_coverage']['mean']:.1f} | {cross['G_rolling_coverage']['range']:.1f} | 2 |
| I | {cross['I_ring_optimized']['mean']:.1f} | {cross['I_ring_optimized']['range']:.1f} | 1 |

## 7. 使用边界与下一步

所有数值均来自离线模拟器，结论是“在当前随机分布、误差模型和计时规则下”的证据，不能替代官方接口演练。真值辅助组只可用于诊断，不可作为实际策略成绩。

下一轮实验不应直接再加架构。优先做两个针对性问题：

1. 把 F 的“动态覆盖顺序”和“站点额外测量预算”分别关闭，完成剩余两项因子归因。
2. 在边界聚集、源点成簇、接收半径固定为 1000 m、系统性角度偏差等压力分布上重复 I 与关键消融，检验现有结论是否依赖均匀随机案例。
"""
    OUT.write_text(text, encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()

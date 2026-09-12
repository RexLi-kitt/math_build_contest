"""多种子鲁棒性验证：同一策略链在多个随机种子下的配对对比与汇总表。

每个种子调用 run_compare.py 跑同一条策略链（或用 --reuse 复用已有结果目录），
池化全部局后生成：
1. 每种子性能总表（平均/中位/P95/最大/方差/失败清除/全清除率）；
2. 跨种子稳定性表（各种子平均/源、跨种子均值/标准差/极差）；
3. 排名稳定性表；
4. 池化配对胜负表（胜率、平均差、最差局、符号检验 p、各种子分解）。

输出：results/robustness/robustness_summary.json 与 reports/多种子鲁棒性表.md。

用法（在 第三问策略对比/ 中）：

    python run_seed_robustness.py --seeds 55021,24119,90317 --cases 1000 --jobs 16 \
        --reuse 55021=results/faithful_chain_1000

不带 --reuse 时所有种子都新跑；目标目录已有同配置结果时自动跳过（--force 强制重跑）。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import subprocess
import sys
import time
from itertools import combinations
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from strategies import STRATEGIES  # noqa: E402

DEFAULT_STRATEGIES = (
    "C_region_q2,Cplus_completion_coobserve,F_coverage_integrated,"
    "G_rolling_coverage,I_ring_optimized"
)

FRIENDLY_NAMES = {
    "C_region_q2": "C 四指标",
    "Cplus_completion_coobserve": "C+ 完成时间+共观测",
    "F_coverage_integrated": "F 覆盖协同",
    "G_rolling_coverage": "G 滚动覆盖",
    "I_ring_optimized": "I 环半径优化",
}


def friendly(name: str) -> str:
    return FRIENDLY_NAMES.get(name, name)


def resolve_path(text: str) -> Path:
    path = Path(text)
    return path if path.is_absolute() else SCRIPT_DIR / path


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)]


def fmt_p(p: float) -> str:
    return "<1e-300" if p <= 0.0 else f"{p:.1e}"


def sign_test_p_value(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    z = (wins - n / 2.0) / math.sqrt(n / 4.0)
    return math.erfc(abs(z) / math.sqrt(2.0))


def parse_reuse_args(items: list[str]) -> dict[int, Path]:
    mapping: dict[int, Path] = {}
    for item in items:
        seed_text, sep, path_text = item.partition("=")
        if not sep or not seed_text.strip().isdigit():
            raise SystemExit(f"--reuse 需要 seed=结果目录 形式，收到：{item!r}")
        mapping[int(seed_text.strip())] = Path(path_text.strip())
    return mapping


def result_dir_valid(path: Path, cases: int, seed: int,
                     strategies: list[str], sources) -> bool:
    if not (path / "case_results.csv").is_file() or not (path / "summary.json").is_file():
        return False
    try:
        config = json.loads((path / "summary.json").read_text(encoding="utf-8"))["config"]
    except (json.JSONDecodeError, KeyError, OSError):
        return False
    existing = [s.strip() for s in str(config.get("strategies", "")).split(",") if s.strip()]
    return (config.get("seed") == seed
            and config.get("cases") == cases
            and set(existing) == set(strategies)
            and config.get("sources") == sources)


def run_seed_fresh(seed: int, cases: int, strategies: list[str],
                   sources, jobs: int, out_dir: Path) -> float:
    cmd = [sys.executable, str(SCRIPT_DIR / "run_compare.py"),
           "--cases", str(cases), "--seed", str(seed),
           "--strategies", ",".join(strategies),
           "--output", str(out_dir), "--jobs", str(jobs)]
    if sources is not None:
        cmd += ["--sources", str(sources)]
    print(f"[seed {seed}] 新跑 {cases} 局 -> {out_dir}", flush=True)
    started = time.perf_counter()
    try:
        subprocess.run(cmd, check=True, cwd=SCRIPT_DIR)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"run_compare.py 在 seed {seed} 上失败（退出码 {exc.returncode}）") from exc
    return time.perf_counter() - started


def load_rows(path: Path) -> list[dict]:
    with (path / "case_results.csv").open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    for row in rows:
        row["seed"] = int(row["seed"])
        row["case"] = int(row["case"])
        row["source_count"] = int(row["source_count"])
        row["all_cleared"] = int(row["all_cleared"])
        row["failed_clear_actions"] = int(row["failed_clear_actions"])
        row["total_virtual_time_s"] = float(row["total_virtual_time_s"])
        row["per_source_s"] = row["total_virtual_time_s"] / row["source_count"]
    return rows


def strategy_stats(rows: list[dict]) -> dict:
    per = [row["per_source_s"] for row in rows]
    return {
        "n_cases": len(rows),
        "all_cleared_rate": sum(row["all_cleared"] for row in rows) / len(rows),
        "mean_time_per_source_s": statistics.mean(per),
        "median_time_per_source_s": statistics.median(per),
        "p95_time_per_source_s": percentile(per, 0.95),
        "max_time_per_source_s": max(per),
        "var_time_per_source_s": statistics.variance(per) if len(per) > 1 else 0.0,
        "mean_total_time_s": statistics.mean(row["total_virtual_time_s"] for row in rows),
        "mean_failed_clear_actions": statistics.mean(
            row["failed_clear_actions"] for row in rows),
    }


def paired_comparisons(all_rows: list[dict], strategies: list[str],
                       seeds: list[int]) -> list[dict]:
    per_seed: dict[int, dict[int, dict[str, float]]] = {seed: {} for seed in seeds}
    for row in all_rows:
        if row["seed"] in per_seed:
            per_seed[row["seed"]].setdefault(row["case"], {})[row["strategy"]] = row["per_source_s"]
    results = []
    for x, y in combinations(strategies, 2):
        diffs: list[float] = []
        wins_by_seed = {seed: 0 for seed in seeds}
        n_by_seed = {seed: 0 for seed in seeds}
        for seed in seeds:
            for case_map in per_seed[seed].values():
                if x not in case_map or y not in case_map:
                    continue
                diff = case_map[x] - case_map[y]
                diffs.append(diff)
                n_by_seed[seed] += 1
                if diff < 0:
                    wins_by_seed[seed] += 1
        wins = sum(1 for d in diffs if d < 0)
        ties = sum(1 for d in diffs if d == 0)
        results.append({
            "x": x,
            "y": y,
            "n_cases": len(diffs),
            "wins": wins,
            "ties": ties,
            "losses": len(diffs) - wins - ties,
            "win_rate": wins / len(diffs) if diffs else 0.0,
            "mean_diff_per_source_s": statistics.mean(diffs) if diffs else 0.0,
            "median_diff_per_source_s": statistics.median(diffs) if diffs else 0.0,
            "worst_diff_per_source_s": max(diffs) if diffs else 0.0,
            "p95_diff_per_source_s": percentile(diffs, 0.95) if diffs else 0.0,
            "sign_test_p": sign_test_p_value(wins, len(diffs) - wins - ties),
            "wins_by_seed": {str(seed): wins_by_seed[seed] for seed in seeds},
            "n_by_seed": {str(seed): n_by_seed[seed] for seed in seeds},
        })
    return results


def per_seed_table(strategies: list[str], stats: dict) -> str:
    lines = ["| 模型 | 平均/源(s) | 中位数 | P95/源 | 最大/源 | 方差 | 失败清除/局 | 全清除率 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name in strategies:
        s = stats[name]
        lines.append(
            "| {} | {:.1f} | {:.1f} | {:.1f} | {:.1f} | {:.0f} | {:.2f} | {:.1%} |".format(
                friendly(name),
                s["mean_time_per_source_s"],
                s["median_time_per_source_s"],
                s["p95_time_per_source_s"],
                s["max_time_per_source_s"],
                s["var_time_per_source_s"],
                s["mean_failed_clear_actions"],
                s["all_cleared_rate"]))
    return "\n".join(lines)


def cross_seed_table(seeds: list[int], strategies: list[str], cross: dict) -> str:
    header = "| 模型 | " + " | ".join(f"seed {seed}" for seed in seeds) \
        + " | 跨种子均值 | 标准差 | 极差 |"
    sep = "|---|" + "---:|" * (len(seeds) + 3)
    lines = [header, sep]
    for name in strategies:
        c = cross[name]
        cells = [f"{c['means_by_seed'][str(seed)]:.1f}" for seed in seeds]
        cells += [f"{c['mean']:.1f}", f"{c['stdev']:.1f}", f"{c['range']:.1f}"]
        lines.append(f"| {friendly(name)} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def ranks_table(seeds: list[int], strategies: list[str], ranks_by_seed: dict) -> str:
    header = "| 模型 | " + " | ".join(f"seed {seed}" for seed in seeds) + " |"
    sep = "|---|" + "---:|" * len(seeds)
    lines = [header, sep]
    for name in strategies:
        cells = [str(ranks_by_seed[str(seed)][name]) for seed in seeds]
        lines.append(f"| {friendly(name)} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def paired_table(seeds: list[int], paired: list[dict]) -> str:
    if not paired:
        return "（只有单个策略，无配对）"
    lines = ["| 配对 | X 胜/总局 | 胜率 | 平均差/源(s) | 最差差/源(s) | 符号检验 p | 各种子 X 胜 |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for item in paired:
        per_seed = "；".join(
            f"{item['wins_by_seed'][str(seed)]}/{item['n_by_seed'][str(seed)]}"
            for seed in seeds)
        lines.append(
            "| {} vs {} | {}/{} | {:.1%} | {:+.1f} | {:+.1f} | {} | {} |".format(
                friendly(item["x"]), friendly(item["y"]),
                item["wins"], item["n_cases"],
                item["win_rate"],
                item["mean_diff_per_source_s"],
                item["worst_diff_per_source_s"],
                fmt_p(item["sign_test_p"]),
                per_seed))
    return "\n".join(lines)


def build_conclusions(seeds: list[int], strategies: list[str], stats_by_seed: dict,
                      cross: dict, paired: list[dict]) -> list[str]:
    lines: list[str] = []
    best = {seed: min(strategies, key=lambda n: stats_by_seed[seed][n]["mean_time_per_source_s"])
            for seed in seeds}
    if len(set(best.values())) == 1:
        lines.append(f"- {friendly(next(iter(best.values())))} 在全部 {len(seeds)} 个种子下平均/源均为第一。")
    else:
        lines.append("- 各种子最优模型："
                     + "；".join(f"seed {seed}：{friendly(name)}" for seed, name in best.items()))
    orders = [sorted(strategies, key=lambda n: stats_by_seed[seed][n]["mean_time_per_source_s"])
              for seed in seeds]
    if all(order == orders[0] for order in orders):
        lines.append("- 各种子下完整排名一致（最优→最差）："
                     + " > ".join(friendly(name) for name in orders[0]) + "。")
    else:
        lines.append("- 各种子下完整排名存在差异，详见排名稳定性表。")
    worst_name = max(strategies, key=lambda n: cross[n]["range"])
    lines.append(f"- 跨种子平均/源极差最大为 {cross[worst_name]['range']:.1f} s"
                 f"（{friendly(worst_name)}），占其跨种子均值的"
                 f" {cross[worst_name]['range'] / cross[worst_name]['mean'] * 100:.1f}%。")
    bad = [(seed, name) for seed in seeds for name in strategies
           if stats_by_seed[seed][name]["all_cleared_rate"] < 1.0]
    if bad:
        lines.append(f"- 存在未全清除的组合：{bad}。")
    else:
        lines.append(f"- 全部 {len(seeds)} 个种子 × {len(strategies)} 个模型的全清除率均为 100%。")
    max_failed = max((stats_by_seed[seed][name]["mean_failed_clear_actions"]
                      for seed in seeds for name in strategies), default=0.0)
    lines.append(f"- 失败清除动作每局均值最大为 {max_failed:.2f} 次。")
    if paired:
        max_p = max(item["sign_test_p"] for item in paired)
        if max_p < 1e-4:
            lines.append(f"- 全部 {len(paired)} 组配对的符号检验 p 均小于 1e-4（最大 {fmt_p(max_p)}），"
                         "排序结论对种子选择稳健。")
        else:
            lines.append(f"- 配对符号检验最大 p 为 {fmt_p(max_p)}，注意存在不显著的配对。")
    if "I_ring_optimized" in strategies:
        value = cross["I_ring_optimized"]["mean"]
        lines.append(f"- I 的跨种子平均/源均值为 {value:.1f} s，"
                     f"距 300 s/源目标 {abs(value - 300.0) / 300.0 * 100:.1f}%。")
    return lines


def build_report(args, reuse_map: dict[int, Path], seeds: list[int], strategies: list[str],
                 seed_info: dict, stats_by_seed: dict, cross: dict,
                 ranks_by_seed: dict, paired: list[dict]) -> str:
    parts: list[str] = []
    parts.append("# 多种子鲁棒性验证（统一第二问口径）\n")
    parts.append(f"- 策略链：{', '.join(friendly(name) for name in strategies)}（`{args.strategies}`）")
    parts.append(f"- 每种子局数：{args.cases}；种子：{', '.join(str(seed) for seed in seeds)}；"
                 "配对方式：同种子同局同源，池化全部局比较")
    fixed = f"；固定每局源数：{args.sources}" if args.sources is not None else ""
    parts.append(f"- 并行进程数：{args.jobs}{fixed}")
    for seed in seeds:
        info = seed_info[str(seed)]
        note = "复用已有结果" if info["reused"] else f"新跑，墙钟 {info['wall_time_s']} s"
        parts.append(f"- seed {seed}：`{info['dir']}`（{note}）")
    total_wall = sum(info["wall_time_s"] or 0.0 for info in seed_info.values())
    if total_wall:
        parts.append(f"- 新跑总墙钟：{total_wall:.1f} s")
    parts.append(f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    parts.append("## 1. 每种子性能总表\n")
    for seed in seeds:
        parts.append(f"### seed {seed}（`{seed_info[str(seed)]['dir']}`）\n")
        parts.append(per_seed_table(strategies, stats_by_seed[seed]) + "\n")

    parts.append("## 2. 跨种子稳定性（平均/源，单位 s）\n")
    parts.append(cross_seed_table(seeds, strategies, cross) + "\n")

    parts.append("## 3. 排名稳定性（按平均/源升序的名次）\n")
    parts.append(ranks_table(seeds, strategies, ranks_by_seed) + "\n")

    parts.append("## 4. 池化配对胜负\n")
    parts.append("差值 = X − Y（每局的每源平均时间差），负值表示 X 更快；"
                 "最差差为 X 相对 Y 最慢一局的差。符号检验为双侧，平局不计入。\n")
    parts.append(paired_table(seeds, paired) + "\n")

    parts.append("## 5. 结论\n")
    for line in build_conclusions(seeds, strategies, stats_by_seed, cross, paired):
        parts.append(line)
    parts.append("")

    parts.append("## 6. 复现\n")
    cmd_parts = [f"python {Path(__file__).name}",
                 f"--seeds {args.seeds}",
                 f"--cases {args.cases}",
                 f"--jobs {args.jobs}"]
    if args.sources is not None:
        cmd_parts.append(f"--sources {args.sources}")
    for seed, path in reuse_map.items():
        cmd_parts.append(f"--reuse {seed}={path}")
    parts.append("```powershell\n" + " ".join(cmd_parts) + "\n```\n")

    parts.append("## 7. 边界\n")
    parts.append("- 全部结果来自离线模拟器（策略层不读取真值），不能替代官方演练；"
                 "正式测试前须通过官方 HTTP 接口复核并保留回退策略。")
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="第三问多种子鲁棒性验证与汇总表生成")
    parser.add_argument("--seeds", default="55021,24119,90317", help="逗号分隔的随机种子列表")
    parser.add_argument("--cases", type=int, default=1000, help="每个种子的局数")
    parser.add_argument("--strategies", default=DEFAULT_STRATEGIES, help="逗号分隔的策略链")
    parser.add_argument("--sources", type=int, choices=range(10, 17),
                        help="固定每局源数；默认随机 10-16")
    parser.add_argument("--jobs", type=int, default=min(16, os.cpu_count() or 1),
                        help="并行进程数")
    parser.add_argument("--output-root", default="results/robustness")
    parser.add_argument("--report", default="reports/多种子鲁棒性表.md")
    parser.add_argument("--reuse", action="append", default=[], metavar="SEED=DIR",
                        help="复用已有结果目录替代新跑，可重复给出")
    parser.add_argument("--force", action="store_true", help="忽略已有同配置结果，强制重跑")
    args = parser.parse_args()

    seeds: list[int] = []
    for text in args.seeds.split(","):
        text = text.strip()
        if text:
            value = int(text)
            if value not in seeds:
                seeds.append(value)
    if not seeds:
        raise SystemExit("--seeds 不能为空")

    strategies = [text.strip() for text in args.strategies.split(",") if text.strip()]
    unknown = [name for name in strategies if name not in STRATEGIES]
    if unknown:
        raise SystemExit(f"未知策略: {unknown}")
    if len(set(strategies)) != len(strategies):
        raise SystemExit("--strategies 存在重复项")

    reuse_map = parse_reuse_args(args.reuse)
    for seed, path in reuse_map.items():
        if seed not in seeds:
            raise SystemExit(f"--reuse 中的种子 {seed} 不在 --seeds 列表内")
        if not result_dir_valid(path, args.cases, seed, strategies, args.sources):
            raise SystemExit(
                f"复用目录 {path} 与当前配置不符（种子/局数/策略链/源数需完全一致）；"
                "如需新跑请去掉该项 --reuse")

    output_root = resolve_path(args.output_root)
    report_path = resolve_path(args.report)

    seed_dirs: dict[int, Path] = {}
    seed_info: dict[str, dict] = {}
    for seed in seeds:
        if seed in reuse_map:
            seed_dirs[seed] = resolve_path(reuse_map[seed])
            seed_info[str(seed)] = {"dir": str(seed_dirs[seed]), "reused": True, "wall_time_s": None}
            print(f"[seed {seed}] 复用已有结果：{seed_dirs[seed]}")
            continue
        out_dir = output_root / f"seed_{seed}"
        if not args.force and result_dir_valid(out_dir, args.cases, seed, strategies, args.sources):
            seed_dirs[seed] = out_dir
            seed_info[str(seed)] = {"dir": str(out_dir), "reused": True, "wall_time_s": None}
            print(f"[seed {seed}] 目标目录已有同配置结果，跳过：{out_dir}")
            continue
        elapsed = run_seed_fresh(seed, args.cases, strategies, args.sources, args.jobs, out_dir)
        seed_dirs[seed] = out_dir
        seed_info[str(seed)] = {"dir": str(out_dir), "reused": False,
                                "wall_time_s": round(elapsed, 1)}

    rows_by_seed = {seed: load_rows(seed_dirs[seed]) for seed in seeds}
    for seed, rows in rows_by_seed.items():
        if not rows:
            raise SystemExit(f"seed {seed} 的结果为空：{seed_dirs[seed]}")

    stats_by_seed = {
        seed: {name: strategy_stats([r for r in rows if r["strategy"] == name])
               for name in strategies}
        for seed, rows in rows_by_seed.items()}
    cross = {}
    for name in strategies:
        means = [stats_by_seed[seed][name]["mean_time_per_source_s"] for seed in seeds]
        cross[name] = {
            "means_by_seed": {str(seed): stats_by_seed[seed][name]["mean_time_per_source_s"]
                              for seed in seeds},
            "mean": statistics.mean(means),
            "stdev": statistics.stdev(means) if len(means) > 1 else 0.0,
            "min": min(means),
            "max": max(means),
            "range": max(means) - min(means),
        }
    ranks_by_seed = {}
    for seed in seeds:
        order = sorted(strategies,
                       key=lambda n: stats_by_seed[seed][n]["mean_time_per_source_s"])
        ranks_by_seed[str(seed)] = {name: rank for rank, name in enumerate(order, 1)}

    all_rows = [row for rows in rows_by_seed.values() for row in rows]
    paired = paired_comparisons(all_rows, strategies, seeds)

    payload = {
        "config": vars(args),
        "strategy_order": strategies,
        "seed_sources": seed_info,
        "per_seed_stats": {str(seed): stats_by_seed[seed] for seed in seeds},
        "cross_seed": cross,
        "ranks_by_seed": ranks_by_seed,
        "paired": paired,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "robustness_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = build_report(args, reuse_map, seeds, strategies, seed_info,
                          stats_by_seed, cross, ranks_by_seed, paired)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    print("\n跨种子稳定性（平均/源，s）：")
    print(cross_seed_table(seeds, strategies, cross))
    print("\n池化配对胜负：")
    print(paired_table(seeds, paired))
    print(f"\n汇总 JSON：{(output_root / 'robustness_summary.json').resolve()}")
    print(f"鲁棒性表：{report_path.resolve()}")


if __name__ == "__main__":
    main()

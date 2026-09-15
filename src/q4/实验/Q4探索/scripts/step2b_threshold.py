"""第二步续：门控阈值在所有场景（含未覆盖的 mixed 象限）上的重评估。

原 C+ 阈值筛选只在 normal / min_radius / boundary_random / boundary_outward 上做，
而后两个场景的源全部贴边，原点发现数恒为 0，阈值在那里没有分辨力。加入 mixed
象限后重新比较阈值 0..6。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402

STEP1 = H.SANDBOX_OUT / "step1_oracle"
STEP2 = H.SANDBOX_OUT / "step2_probe"

SOURCES = [
    ("normal", STEP1 / "normal_rows.json", "B", "C"),
    ("min_radius", STEP1 / "min_radius_rows.json", "B", "C"),
    ("boundary_random", STEP1 / "boundary_random_rows.json", "B", "C"),
    ("boundary_outward", STEP1 / "boundary_outward_rows.json", "B", "C"),
    ("mixed", STEP2 / "mixed_rows.json", "BLog", "CLog"),
]

THRESHOLDS = list(range(0, 7))


def load_scenario(label, path, b_name, c_name):
    rows = json.loads(path.read_text(encoding="utf-8"))
    by_name = {}
    for row in rows:
        by_name.setdefault(row["strategy"], {})[row["case"]] = row
    cases = sorted(by_name[b_name])
    data = []
    for case in cases:
        b = by_name[b_name][case]
        c = by_name[c_name][case]
        gate = by_name["CplusLog"][case]
        n = len(b["source_count"]) if isinstance(b["source_count"], list) else b["source_count"]
        data.append({
            "case": case,
            "n_sources": n,
            "t_b": b["total_virtual_time_s"] / n,
            "t_c": c["total_virtual_time_s"] / n,
            "origin": gate["origin_discoveries"],
        })
    return data


def main() -> None:
    scenarios = {}
    for label, path, b_name, c_name in SOURCES:
        if not path.exists():
            H.log(f"缺少 {path}，跳过 {label}")
            continue
        scenarios[label] = load_scenario(label, path, b_name, c_name)

    H.log("=== 各场景 oracle 与 C+ 现状 ===")
    H.log(f"{'场景':<18}{'n':>5}{'n_origin均值':>13}"
          f"{'B':>9}{'C':>9}{'C+':>9}{'oracle':>9}{'差距%':>9}{'n_origin=0占比':>15}")
    for label, data in scenarios.items():
        t_b = [d["t_b"] for d in data]
        t_c = [d["t_c"] for d in data]
        oracle = [min(b, c) for b, c in zip(t_b, t_c)]
        n_origin = [d["origin"] for d in data]
        gate = [(b if n == 0 else c) for b, c, n in zip(t_b, t_c, n_origin)]
        gap = (statistics.mean(gate) - statistics.mean(oracle)) / statistics.mean(oracle)
        zero = sum(1 for n in n_origin if n == 0) / len(n_origin)
        H.log(f"{label:<18}{len(data):>5}{statistics.mean(n_origin):>13.2f}"
              f"{statistics.mean(t_b):>9.2f}{statistics.mean(t_c):>9.2f}"
              f"{statistics.mean(gate):>9.2f}{statistics.mean(oracle):>9.2f}"
              f"{gap * 100:>8.2f}%{zero:>14.1%}")

    H.log("\n=== 阈值规则（原点发现数 <= θ 选 B，否则选 C）===")
    H.log(f"{'场景':<18}" + "".join(f"{'θ=' + str(t):>12}" for t in THRESHOLDS))
    best_rows = {}
    for label, data in scenarios.items():
        t_b = [d["t_b"] for d in data]
        t_c = [d["t_c"] for d in data]
        oracle = [min(b, c) for b, c in zip(t_b, t_c)]
        n_origin = [d["origin"] for d in data]
        line = f"{label:<18}"
        losses = []
        for threshold in THRESHOLDS:
            picks = [n <= threshold for n in n_origin]
            mean = statistics.mean(b if p else c for b, c, p in zip(t_b, t_c, picks))
            loss = mean - statistics.mean(oracle)
            losses.append(loss)
            line += f"{loss:>+12.2f}"
        best_rows[label] = losses
        H.log(line + "   （数值=相对 oracle 的损失 s/源）")

    H.log("\n=== 逐场景最优阈值 ===")
    for label, losses in best_rows.items():
        best = min(range(len(losses)), key=lambda i: losses[i])
        H.log(f"{label:<18} 最优 θ={THRESHOLDS[best]} "
              f"(损失 {losses[best]:+.2f})，θ=0 损失 {losses[0]:+.2f}，"
              f"改善 {losses[0] - losses[best]:+.2f} s/源")

    H.log("\n=== 跨场景汇总（等权平均损失，s/源）===")
    for index, threshold in enumerate(THRESHOLDS):
        per_scenario = [losses[index] for losses in best_rows.values()]
        pooled = statistics.mean(per_scenario)
        H.log(f"θ={threshold}: 等权平均损失={pooled:+.2f}  "
              f"最差场景损失={max(per_scenario):+.2f}  "
              f"明细={[round(v, 2) for v in per_scenario]}")

    out = {"scenarios": list(scenarios), "losses": best_rows,
           "thresholds": THRESHOLDS}
    (H.SANDBOX_OUT / "step2_threshold.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

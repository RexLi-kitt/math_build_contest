"""第四步续：精确评估自适应方位条数（以及三臂门控）。

两条臂（C 方位 2 / CAz3 方位 3）的原点扫描完全相同，因此"按原点发现数选择方位
条数"的混合策略可以逐案例精确重建，不需要再跑模拟：某案例选哪条臂，就直接取该臂
在该案例上已有的时间。

同时评估三臂门控 {B, C, CAz3}，比较它与三臂 oracle 的差距。
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
STEP4 = H.SANDBOX_OUT / "step4_azimuth"

SCENARIOS = [
    ("normal", STEP1 / "normal_rows.json", "B", "C"),
    ("min_radius", STEP1 / "min_radius_rows.json", "B", "C"),
    ("boundary_random", STEP1 / "boundary_random_rows.json", "B", "C"),
    ("boundary_outward", STEP1 / "boundary_outward_rows.json", "B", "C"),
    ("mixed", STEP2 / "mixed_rows.json", "BLog", "CLog"),
]


def load(path, strategy):
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {row["case"]: row["total_virtual_time_s"] / row["source_count"]
            for row in rows if row["strategy"] == strategy}


def main() -> None:
    data = {}
    for label, reference, b_name, c_name in SCENARIOS:
        arm_path = STEP4 / f"{label}_rows.json"
        if not arm_path.exists():
            H.log(f"缺少 {arm_path}")
            continue
        b = load(reference, b_name)
        c = load(reference, c_name)
        c2 = load(arm_path, "C")
        c3 = load(arm_path, "CAz3")
        n_disc = load_n(STEP1 if label != "mixed" else STEP2,
                        f"{label}_rows.json", "CplusLog")
        cases = sorted(set(b) & set(c) & set(c3) & set(n_disc))
        data[label] = {"cases": cases, "B": b, "C": c, "CAz3": c3,
                       "CAz2": c2, "n": n_disc}
        H.log(f"{label}: 可用配对 {len(cases)} 例")

    H.log("\n=== 各臂均值（s/源） ===")
    H.log(f"{'场景':<18}{'B':>9}{'C(方位2)':>11}{'CAz3':>9}{'最优':>9}")
    for label, block in data.items():
        cases = block["cases"]
        means = {name: statistics.mean(block[name][case] for case in cases)
                 for name in ("B", "C", "CAz3")}
        best = min(means, key=means.get)
        H.log(f"{label:<18}{means['B']:>9.2f}{means['C']:>11.2f}"
              f"{means['CAz3']:>9.2f}{best:>9}")

    H.log("\n=== 自适应方位条数：原点发现数 > θ 用方位3，否则方位2 ===")
    H.log(f"{'场景':<18}" + "".join(f"{'θ=' + str(t):>10}" for t in range(0, 5)))
    for label, block in data.items():
        cases = block["cases"]
        line = f"{label:<18}"
        for threshold in range(0, 5):
            values = [(block["CAz3"][case] if block["n"][case] > threshold
                       else block["C"][case]) for case in cases]
            line += f"{statistics.mean(values):>10.2f}"
        H.log(line)

    H.log("\n=== 三臂规则：0 发现→B；1..θ→C(方位2)；>θ→CAz3 ===")
    H.log(f"{'场景':<18}" + "".join(f"{'θ=' + str(t):>10}" for t in range(0, 5)))
    for label, block in data.items():
        cases = block["cases"]
        line = f"{label:<18}"
        for threshold in range(0, 5):
            values = []
            for case in cases:
                n = block["n"][case]
                if n == 0:
                    values.append(block["B"][case])
                elif n <= threshold:
                    values.append(block["C"][case])
                else:
                    values.append(block["CAz3"][case])
            line += f"{statistics.mean(values):>10.2f}"
        H.log(line)

    H.log("\n=== 现状 C+（0 发现→B，否则 C 方位2）与三臂 oracle 对照 ===")
    H.log(f"{'场景':<18}{'C+现状':>10}{'oracle三臂':>11}{'差距':>9}{'差距%':>8}")
    for label, block in data.items():
        cases = block["cases"]
        gate = [block["B"][case] if block["n"][case] == 0 else block["C"][case]
                for case in cases]
        oracle = [min(block["B"][case], block["C"][case], block["CAz3"][case])
                  for case in cases]
        gap = statistics.mean(gate) - statistics.mean(oracle)
        H.log(f"{label:<18}{statistics.mean(gate):>10.2f}"
              f"{statistics.mean(oracle):>11.2f}{gap:>+9.2f}"
              f"{gap / statistics.mean(oracle) * 100:>7.2f}%")


def load_n(directory: Path, filename: str, strategy: str):
    rows = json.loads((directory / filename).read_text(encoding="utf-8"))
    return {row["case"]: row["origin_discoveries"] for row in rows
            if row["strategy"] == strategy}


if __name__ == "__main__":
    main()

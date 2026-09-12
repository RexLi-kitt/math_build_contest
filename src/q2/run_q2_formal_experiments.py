"""Q2 正式离线实验：权重校准、独立测试、实际二测回放与鲁棒性。

本脚本不访问模拟器；所有结论仅对应题设约束下的合成回放。内层先全局粗搜、
再局部加密，外层用未参与调参的场景报告真实二测 MEC 与接收结果。
"""
from __future__ import annotations

import csv
import itertools
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT, FIG, TAB = ROOT / "outputs" / "q2", ROOT / "outputs" / "q2" / "figures", ROOT / "outputs" / "q2" / "tables"
sys.path.insert(0, str(HERE))
from q1_q2_bridge import ERROR, RADIUS, SPEED, bearing, evaluate_a2, initial_targets  # noqa: E402

S1 = (-750.0, -450.0)
ETA, EPS, FAILURE_MEC = 0.10, math.radians(ERROR), 250.0
BLUE, ORANGE, GRAY, DARK = "#1F5A94", "#E67E22", "#8A8F98", "#23364A"


@dataclass(frozen=True)
class Scenario:
    g: tuple[float, float]
    radius: float
    b1: float
    e2: float


def wrap(x: float) -> float:
    return (x + 180.0) % 360.0 - 180.0


def normalize_weights(w: tuple[float, ...]) -> tuple[float, ...]:
    total = sum(w)
    return tuple(value / total for value in w)


def simplex_grid(step: float = 0.25) -> list[tuple[float, ...]]:
    """四维单纯形网格；step=0.25 时共有 35 组权重。"""
    n = round(1 / step)
    return [(a / n, b / n, c / n, (n - a - b - c) / n)
            for a in range(n + 1) for b in range(n - a + 1)
            for c in range(n - a - b + 1)]


def sample_scenario(rng: random.Random) -> Scenario:
    """按“已在 S1 收到 direction”条件生成真源、半径与两次固定误差。"""
    radius = rng.uniform(1000.0, 1500.0)
    while True:
        rho = RADIUS * math.sqrt(rng.random())
        phi = 2 * math.pi * rng.random()
        g = (rho * math.cos(phi), rho * math.sin(phi))
        d1 = math.dist(S1, g)
        if 5.0 < d1 <= radius:
            break
    return Scenario(g, radius, wrap(bearing(S1, g) + rng.uniform(-ERROR, ERROR)), rng.uniform(-ERROR, ERROR))


def point(b1: float, distance: float, offset: float) -> tuple[float, float]:
    angle = math.radians(b1 + offset)
    return S1[0] + distance * math.cos(angle), S1[1] + distance * math.sin(angle)


def proxy_metrics(s2: tuple[float, float], b1: float, samples: list[tuple[float, float]]) -> dict[str, float]:
    """快速内层预测：GDOP 型角度误差代理，仅用来筛选候选点。

    外层损失始终以 `evaluate_a2` 得到的实际二测 MEC 计量，故代理不承担结论。
    """
    geom, receive, radii = [], 0, []
    for g in samples:
        alpha = abs(wrap(bearing(S1, g) - bearing(s2, g)))
        alpha = min(alpha, 180.0 - alpha)
        sine = max(math.sin(math.radians(alpha)), 0.03)
        geom.append(sine * sine)
        if math.dist(g, s2) <= 1000.0:
            receive += 1
            # 小角度传播的量级代理：交会角越小、距离越远则定位越不稳定。
            radii.append(min(FAILURE_MEC, EPS * (math.dist(S1, g) + math.dist(s2, g)) / sine))
    return {"q": sum(geom) / len(geom), "p": receive / len(samples),
            "t": math.dist(S1, s2) / SPEED,
            "r": sum(radii) / len(radii) if radii else math.inf}


def score_rows(rows: list[dict], weights: tuple[float, ...]) -> list[dict]:
    valid = [row for row in rows if math.isfinite(row["r"]) and row["p"] > 0]
    if not valid:
        return rows
    for key in ("q", "p", "t", "r"):
        lo, hi = min(row[key] for row in valid), max(row[key] for row in valid)
        for row in rows:
            row[f"n_{key}"] = (row[key] - lo) / (hi - lo) if row in valid and hi > lo else (1.0 if row in valid else 0.0)
    for row in rows:
        # 加 w3+w4 仅是常数平移，不改变任何候选点排序；它保证 J 非负，
        # 从而高分区可按方案卡的 J >= (1-eta)J* 定义而不会在负分时为空。
        row["j"] = (weights[0] * row["n_q"] + weights[1] * row["n_p"]
                    - weights[2] * row["n_t"] - weights[3] * row["n_r"]
                    + weights[2] + weights[3]) if row in valid else -math.inf
    return rows


def select_point(scenario: Scenario, weights: tuple[float, ...], rng: random.Random,
                 mode: str = "four") -> tuple[tuple[float, float], dict]:
    """一次完整的粗搜—双中心局部加密；权重每变一次均从粗搜重新开始。"""
    samples = initial_targets(S1, scenario.b1, radial_count=4, angle_count=6)
    coarse_points = [point(scenario.b1, d, off) for d in range(100, 1801, 200) for off in range(0, 360, 30)]
    coarse = [{"pnt": p, **proxy_metrics(p, scenario.b1, samples)} for p in coarse_points]
    score_rows(coarse, weights)
    if mode == "geometry":
        seeds = sorted(coarse, key=lambda row: row["q"], reverse=True)[:2]
    elif mode == "nearest":
        seeds = sorted(coarse, key=lambda row: row["t"])[:2]
    elif mode == "random":
        seeds = rng.sample(coarse, 2)
    else:
        seeds = sorted(coarse, key=lambda row: row["j"], reverse=True)[:2]

    refined = []
    for seed in seeds:
        d = math.dist(S1, seed["pnt"])
        direction = math.degrees(math.atan2(seed["pnt"][1] - S1[1], seed["pnt"][0] - S1[0]))
        for dd in (max(50.0, d - 100.0), d, min(1800.0, d + 100.0)):
            for da in (-10.0, 0.0, 10.0):
                refined.append(point(0.0, dd, direction + da))
    unique = list({(round(p[0], 7), round(p[1], 7)) for p in refined})
    rows = [{"pnt": p, **proxy_metrics(p, scenario.b1, samples)} for p in unique]
    score_rows(rows, weights)
    if mode == "geometry":
        chosen = max(rows, key=lambda row: row["q"])
    elif mode == "nearest":
        chosen = min(rows, key=lambda row: row["t"])
    elif mode == "random":
        chosen = rng.choice(rows)
    else:
        peak = max(rows, key=lambda row: row["j"])
        good = [row for row in rows if row["j"] >= (1 - ETA) * peak["j"]]
        chosen = min(good, key=lambda row: (round(row["t"], 6), row["r"], -row["j"]))
    return chosen["pnt"], chosen


def replay(scenario: Scenario, s2: tuple[float, float]) -> dict[str, float]:
    """按真实半径及真实二测误差回放；无接收时 MEC 以失败上限编码。"""
    d2 = math.dist(s2, scenario.g)
    received = d2 <= scenario.radius
    if not received:
        mec = FAILURE_MEC
    elif d2 <= 5.0:
        mec = 0.0
    else:
        b2 = wrap(bearing(s2, scenario.g) + scenario.e2)
        mec = evaluate_a2(S1, scenario.b1, s2, b2).mec_radius_m
        if not math.isfinite(mec):
            mec = FAILURE_MEC
    return {"received": float(received), "mec": mec, "success20": float(received and mec <= 20.0),
            "time_s": math.dist(S1, s2) / SPEED + 5.0}


def evaluate(weights: tuple[float, ...], scenarios: list[Scenario], seed: int, mode: str = "four") -> list[dict]:
    rng = random.Random(seed)
    records = []
    for index, scenario in enumerate(scenarios):
        s2, _ = select_point(scenario, weights, rng, mode)
        records.append({"case": index, "x_m": s2[0], "y_m": s2[1], **replay(scenario, s2)})
    return records


def summary(records: list[dict]) -> dict[str, float]:
    values = lambda key: sorted(row[key] for row in records)
    mec, times = values("mec"), values("time_s")
    return {"接收率": sum(row["received"] for row in records) / len(records),
            "MEC均值(m)": sum(mec) / len(mec), "MEC中位数(m)": mec[len(mec)//2],
            "MEC_P90(m)": mec[math.ceil(.9*len(mec))-1], "≤20m成功率": sum(row["success20"] for row in records) / len(records),
            "总时间均值(s)": sum(times) / len(times), "总时间P90(s)": times[math.ceil(.9*len(times))-1]}


def write_csv(name: str, fields: list[str], rows: list[dict]) -> None:
    with (TAB / name).open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fields); writer.writeheader(); writer.writerows(rows)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True); TAB.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"], "axes.unicode_minus": False})
    train_rng, test_rng = random.Random(20260911), random.Random(20260912)
    # 本轮为可在本地复现的小规模离线校准；正式提交前扩展为每组至少 30 个训练案例。
    train = [sample_scenario(train_rng) for _ in range(20)]
    test = [sample_scenario(test_rng) for _ in range(40)]
    baseline = evaluate((.25, .25, .25, .25), train, 11, "nearest")
    t0 = summary(baseline)["总时间均值(s)"]

    calibration = []
    for index, weights in enumerate(simplex_grid()):
        records = evaluate(weights, train, 1000 + index)
        result = summary(records)
        loss = .40 * result["MEC均值(m)"] / 20 + .35 * (1 - result["接收率"]) + .25 * result["总时间均值(s)"] / t0
        calibration.append({"权重w1几何": weights[0], "权重w2接收": weights[1], "权重w3时间": weights[2], "权重w4预测": weights[3], "外层损失L": loss, **result})
    calibration.sort(key=lambda row: row["外层损失L"])
    best = tuple(calibration[0][key] for key in ("权重w1几何", "权重w2接收", "权重w3时间", "权重w4预测"))
    write_csv("Q2正式权重网格校准.csv", list(calibration[0]), calibration)

    strategy_rows = []
    for label, mode in (("四指标联合", "four"), ("仅几何", "geometry"), ("最近点", "nearest"), ("随机点", "random")):
        result = summary(evaluate(best, test, 3000, mode))
        strategy_rows.append({"策略": label, **result})
    write_csv("Q2正式独立测试策略对比.csv", list(strategy_rows[0]), strategy_rows)

    robustness = []
    base_summary = summary(evaluate(best, test, 4000))
    for i, name in enumerate(("w1几何", "w2接收", "w3时间", "w4预测")):
        for factor in (.9, 1.1):
            perturb = list(best); perturb[i] *= factor; perturb = normalize_weights(tuple(perturb))
            result = summary(evaluate(perturb, test, 4100 + 10*i + int(10*factor)))
            robustness.append({"扰动": name, "倍率": factor, "归一化权重": ";".join(f"{x:.3f}" for x in perturb),
                               "接收率变化": result["接收率"]-base_summary["接收率"],
                               "成功率变化": result["≤20m成功率"]-base_summary["≤20m成功率"],
                               "MEC均值变化(m)": result["MEC均值(m)"]-base_summary["MEC均值(m)"],
                               "时间均值变化(s)": result["总时间均值(s)"]-base_summary["总时间均值(s)"]})
    write_csv("Q2正式权重鲁棒性.csv", list(robustness[0]), robustness)

    # 两张论文级汇总图：权重损失前十名、独立测试策略表现。
    top = calibration[:10]
    fig, ax = plt.subplots(figsize=(9.0, 4.8))
    ax.bar(range(len(top)), [row["外层损失L"] for row in top], color=BLUE, edgecolor="white")
    ax.set_xticks(range(len(top)), [f"{i+1}" for i in range(len(top))]); ax.set_xlabel("损失排序"); ax.set_ylabel("外层损失 L")
    ax.set_title("图2-4  蒙特卡洛—权重网格校准的前十组方案", color=DARK, fontweight="bold"); ax.grid(axis="y", alpha=.25)
    fig.tight_layout(); fig.savefig(FIG / "fig2_4_weight_calibration.png", dpi=300); fig.savefig(FIG / "fig2_4_weight_calibration.pdf"); plt.close(fig)
    fig, ax = plt.subplots(figsize=(9.2, 4.8)); x = range(len(strategy_rows)); width = .32
    ax.bar([v-width/2 for v in x], [r["接收率"] for r in strategy_rows], width, color=BLUE, label="二测接收率")
    ax.bar([v+width/2 for v in x], [r["≤20m成功率"] for r in strategy_rows], width, color=ORANGE, label="MEC≤20 m 成功率")
    ax.set_xticks(list(x), [r["策略"] for r in strategy_rows]); ax.set_ylim(0, 1.05); ax.set_ylabel("比例"); ax.set_title("图2-5  独立场景中的实际二测回放对比", color=DARK, fontweight="bold"); ax.legend(); ax.grid(axis="y", alpha=.25)
    fig.tight_layout(); fig.savefig(FIG / "fig2_5_independent_replay.png", dpi=300); fig.savefig(FIG / "fig2_5_independent_replay.pdf"); plt.close(fig)
    print("正式校准最优权重", best); print("独立测试", strategy_rows[0])


if __name__ == "__main__":
    main()

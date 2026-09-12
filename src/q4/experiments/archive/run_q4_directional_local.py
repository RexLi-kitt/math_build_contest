"""Q4 局部验证：以 Q2 粗搜—加密为骨架，加入定向可见性与多方位风险回补。"""
from __future__ import annotations

import csv
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
Q2 = ROOT / "src" / "q2"
sys.path.insert(0, str(Q2))
from q1_q2_bridge import ERROR, RADIUS, SPEED, bearing, initial_targets  # noqa: E402

OUT, FIG, TAB = ROOT / "outputs" / "q4", ROOT / "outputs" / "q4" / "figures", ROOT / "outputs" / "q4" / "tables"
S1 = (-750.0, -450.0)
EPS = math.radians(ERROR)
BLUE, ORANGE, GRAY, DARK = "#1F5A94", "#E67E22", "#8A8F98", "#23364A"


def wrap(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def station_visible(s: tuple[float, float], g: tuple[float, float], source_phi: float) -> bool:
    """定向源半张角为90°：机器狗位于发射前方半平面才可见。"""
    station_angle = math.degrees(math.atan2(s[1] - g[1], s[0] - g[0]))
    return abs(wrap(station_angle - source_phi)) <= 90.0


@dataclass(frozen=True)
class Scenario:
    g: tuple[float, float]
    radius: float
    phi: float
    b1: float


def make_scenario(rng: random.Random) -> Scenario:
    """条件于 S1 已成功 direction，符合“由 Q2 接管局部定位”的前提。"""
    while True:
        radius = rng.uniform(1000.0, 1500.0)
        rho, a = RADIUS * math.sqrt(rng.random()), rng.uniform(0.0, 2 * math.pi)
        g = (rho * math.cos(a), rho * math.sin(a))
        phi = rng.uniform(0.0, 360.0)
        if 5.0 < math.dist(S1, g) <= radius and station_visible(S1, g, phi):
            return Scenario(g, radius, phi, wrap(bearing(S1, g) + rng.uniform(-ERROR, ERROR)))


def polar(b1: float, distance: float, offset: float) -> tuple[float, float]:
    a = math.radians(b1 + offset)
    return S1[0] + distance * math.cos(a), S1[1] + distance * math.sin(a)


def normalized_score(rows: list[dict], directional: bool) -> None:
    """Q2 四指标保留，Q4 额外加入方向可见性与未覆盖风险。"""
    for key in ("geo", "prec", "time", "rpred", "pvis", "risk"):
        lo, hi = min(r[key] for r in rows), max(r[key] for r in rows)
        for r in rows:
            r[f"n_{key}"] = (r[key] - lo) / (hi - lo) if hi > lo else 0.0
    for r in rows:
        # Q2：几何、保守接收、时间、预测不确定性；Q4：可见性和漏检风险。
        if directional:
            r["J"] = (.20*r["n_geo"] + .20*r["n_prec"] + .25*r["n_pvis"]
                      - .10*r["n_time"] - .15*r["n_rpred"] - .10*r["n_risk"] + .35)
        else:
            r["J"] = .35*r["n_geo"] + .30*r["n_prec"] - .15*r["n_time"] - .20*r["n_rpred"] + .35


def candidate_metrics(s2: tuple[float, float], b1: float, samples: list[tuple[float, float]],
                      history: list[tuple[float, float]], directional: bool) -> dict:
    geo, rec, visible, proxy = [], 0, 0, []
    # 方向状态是可解释的离散世界模型，而非读取真实 phi。
    phis = range(0, 360, 30)
    for g in samples:
        alpha = min(abs(wrap(bearing(S1, g) - bearing(s2, g))), 180.0 - abs(wrap(bearing(S1, g) - bearing(s2, g))))
        sine = max(math.sin(math.radians(alpha)), .03)
        geo.append(sine*sine)
        if math.dist(s2, g) <= 1000.0:
            rec += 1
            proxy.append(min(250.0, EPS*(math.dist(S1, g) + math.dist(s2, g))/sine))
        if directional:
            # 首次 direction 是正证据：仅保留“从全部历史检测位置均可见”的发射朝向。
            compatible = [phi for phi in phis if all(station_visible(h, g, phi) for h in history)]
            visible += (sum(station_visible(s2, g, phi) for phi in compatible) / len(compatible)
                        if compatible and math.dist(s2, g) <= 1000.0 else 0.0)
    station_angle = math.degrees(math.atan2(s2[1] - S1[1], s2[0] - S1[0]))
    diversity = min(abs(wrap(station_angle-a)) for a in [0.0]) / 180.0
    pvis = visible/len(samples) if directional else rec/len(samples)
    return {"geo":sum(geo)/len(geo), "prec":rec/len(samples), "time":math.dist(S1,s2)/SPEED,
            "rpred":sum(proxy)/len(proxy) if proxy else 250.0,
            "pvis":pvis, "risk":1.0-pvis}


def choose_q4(scenario: Scenario, history: list[tuple[float, float]], directional: bool) -> tuple[dict, list[dict]]:
    """严格保留 Q2 的“两级搜索 + 高分区内最短路”决策结构。"""
    samples = initial_targets(S1, scenario.b1, radial_count=4, angle_count=6)
    coarse = [{"p":p, **candidate_metrics(p,scenario.b1,samples,history,directional)}
              for p in [polar(scenario.b1,d,o) for d in range(100,1801,200) for o in range(0,360,30)]]
    normalized_score(coarse,directional)
    seeds = sorted(coarse,key=lambda r:r["J"],reverse=True)[:2]
    pts=set()
    for seed in seeds:
        d=math.dist(S1,seed["p"]); a=math.degrees(math.atan2(seed["p"][1]-S1[1],seed["p"][0]-S1[0]))
        for dd in (max(50,d-100),d,min(1800,d+100)):
            for da in (-10,0,10): pts.add(tuple(round(v,7) for v in polar(0,dd,a+da)))
    refined=[{"p":p,**candidate_metrics(p,scenario.b1,samples,history,directional)} for p in pts]
    normalized_score(refined,directional)
    peak=max(refined,key=lambda r:r["J"]); good=[r for r in refined if r["J"]>=.9*peak["J"]]
    return min(good,key=lambda r:(round(r["time"],6),r["rpred"],-r["J"])), refined


def observed(s2: tuple[float,float], scenario: Scenario) -> bool:
    return math.dist(s2,scenario.g)<=scenario.radius and station_visible(s2,scenario.g,scenario.phi)


def main() -> None:
    OUT.mkdir(parents=True,exist_ok=True); FIG.mkdir(parents=True,exist_ok=True); TAB.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({"font.sans-serif":["Microsoft YaHei","SimHei","DejaVu Sans"],"axes.unicode_minus":False})
    rng=random.Random(20260913); rows=[]
    for case in range(80):
        scenario=make_scenario(rng); history=[S1]
        for label,flag in (("Q2基线（忽略朝向）",False),("Q4方向风险回补",True)):
            choice,_=choose_q4(scenario,history,flag); s2=choice["p"]; got=observed(s2,scenario)
            rows.append({"案例":case,"策略":label,"二测接收":int(got),"移动时间(s)":choice["time"],"保证接收比例":choice["prec"],"方向可见性评分":choice["pvis"],"漏检风险":choice["risk"],"S2_x(m)":s2[0],"S2_y(m)":s2[1]})
    fields=list(rows[0]);
    with (TAB/"Q4定向源二测配对回放.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
    summary=[]
    for label in ("Q2基线（忽略朝向）","Q4方向风险回补"):
        group=[r for r in rows if r["策略"]==label]
        summary.append({"策略":label,"二测接收率":sum(r["二测接收"] for r in group)/len(group),"平均移动时间(s)":sum(r["移动时间(s)"] for r in group)/len(group),"平均漏检风险":sum(r["漏检风险"] for r in group)/len(group)})
    with (TAB/"Q4定向源策略汇总.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,list(summary[0]));w.writeheader();w.writerows(summary)
    fig,ax=plt.subplots(figsize=(7.6,4.8)); names=[r["策略"] for r in summary]; vals=[r["二测接收率"] for r in summary]
    bars=ax.bar(names,vals,color=[GRAY,BLUE],edgecolor="white");ax.set_ylim(0,1.05);ax.set_ylabel("实际二测接收率");ax.set_title("第四问：定向可见性风险回补的配对回放",color=DARK,fontweight="bold");ax.grid(axis="y",alpha=.25)
    for bar,v in zip(bars,vals):ax.text(bar.get_x()+bar.get_width()/2,v+.025,f"{v:.1%}",ha="center",color=DARK)
    fig.tight_layout();fig.savefig(FIG/"q4_directional_replay.png",dpi=300);fig.savefig(FIG/"q4_directional_replay.pdf");plt.close(fig)
    print(summary)


if __name__=="__main__": main()

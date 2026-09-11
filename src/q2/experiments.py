"""Q2正式交付：调用Q1几何接口完成第二检测点选择、基线对比与敏感性检验。"""
from __future__ import annotations
import csv, math, random, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]; OUT=ROOT/"outputs"/"q2"; FIG=OUT/"figures"; TAB=OUT/"tables"
sys.path.insert(0,str(HERE))
from q1_q2_bridge import RADIUS, ERROR, evaluate_with_q1, score_second_point

S1=(-750.0,-450.0); B1=46.3
W=(2.2,.8,.004,1.2,.003)

def bearing(a,b): return math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))
def inside(p): return math.hypot(*p)<=RADIUS
def candidates():
    ans=[]
    for d in (400,600,800,1000,1200):
        for off in (-120,-90,-60,60,90,120):
            a=math.radians(B1+off); p=(S1[0]+d*math.cos(a),S1[1]+d*math.sin(a))
            if inside(p): ans.append(p)
    return ans
def q1_actual(s2,g):
    # 离线回放专用：g从首次可行域代表点产生，不作为在线策略输入。
    return evaluate_with_q1([S1,s2],[B1,bearing(s2,g)])
def choose(ps,weights=W):
    rows=[]
    for p in ps:
        x=score_second_point(S1,B1,p,weights)
        rows.append({"x_m":p[0],"y_m":p[1],**x})
    return rows, max(rows,key=lambda x:x["score"])
def choose_from_rows(rows, weights):
    w1,w2,w3,w4,w5=weights
    def value(r): return w1*r["q_geo"]+w2*r["p_rec"]-w3*r["travel_s"]-w4*r["boundary_risk"]-w5*r["predicted_mec_radius_m"]
    return max(rows,key=value) | {"score": value(max(rows,key=value))}
def baseline_points(ps,best):
    near=min(ps,key=lambda p:math.dist(S1,p))
    geo=min(ps,key=lambda p:abs(abs(((bearing(S1,p)-B1+180)%360)-180)-90))
    random.seed(2026); rand=random.choice(ps)
    return {"联合评分":(best["x_m"],best["y_m"]),"最近点":near,"固定90度点":geo,"随机点":rand}
def evaluate_strategy(name,p,g):
    got=math.dist(p,g)<=1000.0
    if not got: return [name,p[0],p[1],0,math.inf,math.inf,math.dist(S1,p)/5]
    r=q1_actual(p,g)
    return [name,p[0],p[1],1,r.diameter_m,r.mec_radius_m,math.dist(S1,p)/5]
def make_figure(rows,best):
    plt.rcParams.update({"font.sans-serif":["Microsoft YaHei","SimHei","DejaVu Sans"],"axes.unicode_minus":False})
    fig,ax=plt.subplots(figsize=(8,7)); ax.add_patch(plt.Circle((0,0),RADIUS,fill=False,ec="#8A8F98",ls="--",lw=1.5))
    x=np.array([r["x_m"] for r in rows]); y=np.array([r["y_m"] for r in rows]); c=np.array([r["score"] for r in rows])
    sc=ax.scatter(x,y,c=c,cmap="Blues",s=55,label="候选第二点"); fig.colorbar(sc,ax=ax,label="Q1接口联合评分")
    ax.scatter(*S1,c="#1F5A94",s=90,label="首次检测点 S1",zorder=3); ax.scatter(best["x_m"],best["y_m"],c="#E67E22",marker="D",s=100,label="最优第二点 S2*",zorder=4)
    ax.plot([S1[0],best["x_m"]],[S1[1],best["y_m"]],c="#E67E22",lw=2)
    ax.set(aspect="equal",xlim=(-1900,1900),ylim=(-1900,1900),xlabel="东向坐标 x / m",ylabel="北向坐标 y / m",title="问题2 候选第二检测点的Q1接口联合评分")
    ax.legend(); ax.grid(alpha=.25); fig.tight_layout()
    for ext in ("png","pdf"): fig.savefig(FIG/f"q2_q1_interface_score.{ext}",dpi=300,bbox_inches="tight")
    plt.close(fig)
def main():
    FIG.mkdir(parents=True,exist_ok=True); TAB.mkdir(parents=True,exist_ok=True)
    ps=candidates(); rows,best=choose(ps)
    with open(TAB/"Q2候选点评分.csv","w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(sorted(rows,key=lambda x:x["score"],reverse=True))
    # 选取初始可行带中心线上的代表目标，仅用于统一的离线策略比较。
    g=(S1[0]+800*math.cos(math.radians(B1)),S1[1]+800*math.sin(math.radians(B1)))
    result=[evaluate_strategy(k,p,g) for k,p in baseline_points(ps,best).items()]
    with open(TAB/"Q2策略对比.csv","w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["策略","S2_x(m)","S2_y(m)","保守二次接收","预测区域直径(m)","预测最小外接圆半径(m)","移动时间(s)"]); w.writerows(result)
    # 权重±10%：报告最优点是否改变以及预测MEC变化。
    sens=[]
    for i,label in enumerate(["w1几何","w2接收","w3时间","w4边界","w5MEC"]):
        for fac in (.9,1.1):
            ww=list(W); ww[i]*=fac; b=choose_from_rows(rows,tuple(ww)); sens.append([label,fac,b["x_m"],b["y_m"],b["score"],b["predicted_mec_radius_m"]])
    with open(TAB/"Q2权重敏感性.csv","w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["扰动参数","倍率","最优S2_x(m)","最优S2_y(m)","评分","预测MEC半径(m)"]); w.writerows(sens)
    # 圆域逼近：64边形与128边形的边界内缩误差上界。
    with open(TAB/"Q2圆域逼近检验.csv","w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["边数","最大内缩误差(m)"]); [w.writerow([n,RADIUS*(1-math.cos(math.pi/n))]) for n in (64,128,256)]
    make_figure(rows,best)
    with open(OUT/"README.md","w",encoding="utf-8") as f:
        f.write("# Q2 正式成果\n\n本目录的候选点评分由 `src/q2/q1_q2_bridge.py` 调用Q1角度带、区域直径和最小外接圆接口生成。策略比较中的代表目标仅用于离线回放；在线决策不读取真实源坐标。\n\n若二次观测后最小外接圆半径不超过20 m，且圆心可达，则进入清除；否则继续主动检测。\n")
    print("最优点",best)
if __name__=="__main__": main()

"""按 Q2 方案卡求解：A1/A2、四指标归一化、粗搜—局部加密与离线检验。"""
from __future__ import annotations
import csv, math, random, shutil, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]; OUT=ROOT/"outputs"/"q2"; FIG=OUT/"figures"; TAB=OUT/"tables"; RESULT=HERE/"results"
sys.path.insert(0,str(HERE))
from q1_q2_bridge import (ERROR, GUARANTEE_RADIUS, MAX_DIRECTION_DISTANCE, MIN_DIRECTION_DISTANCE, RADIUS, SPEED,
                           bearing, evaluate_a1, evaluate_a2, initial_targets, no_signal_update, raw_four_metrics)

# 仅用于当前离线示例；正式论文由“蒙特卡洛—网格搜索”外层校准并做±10%稳定性检验。
S1=(-750.0,-450.0); B1=46.3; W=(0.35,0.30,0.15,0.20); GOOD_ETA=0.10

def candidates(distances=(200,600,1000,1400,1800), offsets=range(0,360,60)):
    return [(S1[0]+d*math.cos(math.radians(B1+off)),S1[1]+d*math.sin(math.radians(B1+off))) for d in distances for off in offsets]

def normalize(rows, weights=W):
    valid=[r for r in rows if r["guaranteed_samples"]>0 and math.isfinite(r["r_pred_m"])]
    if not valid: raise RuntimeError("所有候选点均无1000m保证接收样本")
    for key, outkey in (("q_geo","q_geo_norm"),("p_rec","p_rec_norm"),("travel_s","travel_norm"),("r_pred_m","r_pred_norm")):
        lo,hi=min(r[key] for r in valid),max(r[key] for r in valid)
        for r in rows: r[outkey]=((r[key]-lo)/(hi-lo) if r in valid and hi>lo else (0.0 if r not in valid else 1.0))
    for r in rows:
        r["score"]=-math.inf if r not in valid else (weights[0]*r["q_geo_norm"]+weights[1]*r["p_rec_norm"]-weights[2]*r["travel_norm"]-weights[3]*r["r_pred_norm"])
    return rows

def evaluate_points(points, targets):
    return [{"x_m":p[0],"y_m":p[1],**raw_four_metrics(S1,B1,p,targets)} for p in points]

def choose(weights=W):
    targets=initial_targets(S1,B1)
    coarse_raw=evaluate_points(candidates(),targets)
    coarse=normalize([dict(r) for r in coarse_raw],weights)
    seeds=sorted([r for r in coarse if math.isfinite(r["score"])],key=lambda r:r["score"],reverse=True)[:2]
    # 对粗搜优胜点在距离±100m、方位±10°的邻域加密，降低离散误差。
    refined=[]
    for r in seeds:
        d=math.dist(S1,(r["x_m"],r["y_m"])); base=math.degrees(math.atan2(r["y_m"]-S1[1],r["x_m"]-S1[0]))
        refined += [(S1[0]+dd*math.cos(math.radians(base+da)),S1[1]+dd*math.sin(math.radians(base+da)))
                    for dd in (max(50,d-100),d,min(1800,d+100)) for da in (-10,0,10)]
    # 粗网格仅用于定位加密中心；最终评分、候选区域和执行点只来自局部加密集。
    refined_points=list({(round(p[0],9),round(p[1],9)) for p in refined})
    rows=normalize(evaluate_points(refined_points,targets),weights)
    peak=max(rows,key=lambda r:r["score"])
    threshold=(1-GOOD_ETA)*peak["score"]
    good=[r for r in rows if r["score"]>=threshold]
    # 同一移动时间（数值误差按微秒量级视为相同）时，依次选更小预测MEC、更高评分。
    execute=min(good,key=lambda r:(round(r["travel_s"],6),round(r["r_pred_m"],6),-r["score"]))
    return targets, rows, peak, good, execute

def style(): plt.rcParams.update({"font.sans-serif":["Microsoft YaHei","SimHei","DejaVu Sans"],"axes.unicode_minus":False})
def plot_a1(targets):
    style(); reg=evaluate_a1(S1,B1); fig,ax=plt.subplots(figsize=(7,7));
    ax.add_patch(plt.Circle((0,0),RADIUS,fill=False,ec="#7C8798",ls="--",label="干扰源可能区域 1800m"))
    ax.add_patch(plt.Circle(S1,MAX_DIRECTION_DISTANCE,fill=False,ec="#3C8DAD",ls=":",label="首测上界 1500m")); ax.add_patch(plt.Circle(S1,MIN_DIRECTION_DISTANCE,fill=False,ec="#E67E22",ls=":",label="首测内孔 5m"))
    if reg.vertices: ax.fill(*zip(*(reg.vertices+(reg.vertices[0],))),color="#8EC5FC",alpha=.35,label="A1 凸外壳")
    ax.scatter(*zip(*targets),c="#1F5A94",s=28,label="A1 代表样本"); ax.scatter(*S1,c="#D35400",s=70,label="S1")
    ax.set(aspect="equal",xlabel="东向坐标 x / m",ylabel="北向坐标 y / m",title="问题2 首测物理可行域 A1 与代表样本"); ax.legend(fontsize=8); ax.grid(alpha=.25); fig.tight_layout(); fig.savefig(FIG/"q2_a1_domain.png",dpi=300); plt.close(fig)
def plot_score(rows,peak,good,execute):
    style(); fig,ax=plt.subplots(figsize=(8,7)); x=[r["x_m"] for r in rows]; y=[r["y_m"] for r in rows]; c=[r["score"] for r in rows]
    ax.add_patch(plt.Circle((0,0),RADIUS,fill=False,ec="#8A8F98",ls="--",lw=1.5,label="源分布圆")); sc=ax.scatter(x,y,c=c,cmap="Blues",s=48,label="局部加密候选点"); fig.colorbar(sc,ax=ax,label="归一化联合评分 J")
    ax.scatter([r["x_m"] for r in good],[r["y_m"] for r in good],facecolors="none",edgecolors="#E67E22",s=125,lw=2,label="候选区域 R_good")
    ax.scatter(*S1,c="#1F5A94",s=90,label="首次检测点 S1"); ax.scatter(peak["x_m"],peak["y_m"],c="#7E57C2",marker="P",s=105,label="评分峰值"); ax.scatter(execute["x_m"],execute["y_m"],c="#E67E22",marker="D",s=100,label="执行点 S2*"); ax.plot([S1[0],execute["x_m"]],[S1[1],execute["y_m"]],c="#E67E22",lw=2)
    ax.set(aspect="equal",xlabel="东向坐标 x / m",ylabel="北向坐标 y / m",title="问题2 四指标归一化后的第二检测点评分"); ax.legend(); ax.grid(alpha=.25); fig.tight_layout(); fig.savefig(FIG/"q2_four_metric_score.png",dpi=300); plt.close(fig)
def plot_a2(best, targets):
    g=targets[len(targets)//2]; reg=evaluate_a2(S1,B1,(best["x_m"],best["y_m"]),bearing((best["x_m"],best["y_m"]),g)); style(); fig,ax=plt.subplots(figsize=(7,7))
    if reg.vertices: ax.fill(*zip(*(reg.vertices+(reg.vertices[0],))),color="#A8E6CF",alpha=.55,label="预测 A2 凸外壳")
    ax.scatter(*S1,c="#1F5A94",label="S1"); ax.scatter(best["x_m"],best["y_m"],c="#E67E22",marker="D",label="S2*"); ax.scatter(*g,c="#C0392B",marker="*",s=120,label="离线真值样本")
    ax.set(aspect="equal",xlabel="东向坐标 x / m",ylabel="北向坐标 y / m",title=f"二次测量预测域 A2，MEC={reg.mec_radius_m:.2f} m"); ax.legend(); ax.grid(alpha=.25); fig.tight_layout(); fig.savefig(FIG/"q2_a2_prediction.png",dpi=300); plt.close(fig)
def plot_strategy(baselines):
    style(); names=list(baselines); vals=list(baselines.values()); fig,axs=plt.subplots(1,3,figsize=(11,3.6))
    for ax,key,title,unit,color in zip(axs,["p_rec","r_pred_m","travel_s"],["保证接收比例","预测 MEC","移动时间"],["比例","m","s"],["#3C8DAD","#E67E22","#7C8798"]):
        ax.bar(names,[r[key] for r in vals],color=color); ax.set_title(title); ax.set_ylabel(unit); ax.tick_params(axis="x",rotation=28); ax.grid(axis="y",alpha=.25)
    fig.suptitle("问题2 多策略样本回放对比",y=1.03); fig.tight_layout(); fig.savefig(FIG/"q2_strategy_compare.png",dpi=300,bbox_inches="tight"); plt.close(fig)

def main():
    FIG.mkdir(parents=True,exist_ok=True); TAB.mkdir(parents=True,exist_ok=True); RESULT.mkdir(parents=True,exist_ok=True)
    targets,rows,peak,good,best=choose(); plot_a1(targets); plot_score(rows,peak,good,best); plot_a2(best,targets)
    keys=["x_m","y_m","q_geo","p_rec","travel_s","r_pred_m","guaranteed_samples","q_geo_norm","p_rec_norm","travel_norm","r_pred_norm","score"]
    with (TAB/"Q2候选点评分.csv").open("w",newline="",encoding="utf-8-sig") as f: w=csv.DictWriter(f,keys); w.writeheader(); w.writerows(sorted(rows,key=lambda r:r["score"],reverse=True))
    with (TAB/"Q2候选区域.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["eta","评分阈值","x(m)","y(m)","评分","移动时间(s)","是否执行点"])
        w.writerows([[GOOD_ETA,(1-GOOD_ETA)*peak["score"],r["x_m"],r["y_m"],r["score"],r["travel_s"],"是" if r is best else "否"] for r in sorted(good,key=lambda r:r["travel_s"])])
    # 与仅几何、最近点、随机点在同一候选池上做样本回放比较。
    valid=[r for r in rows if math.isfinite(r["score"])]
    random.seed(2026)
    baselines={"四指标联合":best,"仅最大几何":max(valid,key=lambda r:r["q_geo"]),"最近候选点":min(valid,key=lambda r:r["travel_s"]),"随机候选点":random.choice(valid)}
    plot_strategy(baselines)
    with (TAB/"Q2策略对比.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["策略","S2_x(m)","S2_y(m)","保证接收比例","预测MEC(m)","移动时间(s)","综合评分"])
        w.writerows([[n,r["x_m"],r["y_m"],r["p_rec"],r["r_pred_m"],r["travel_s"],r["score"]] for n,r in baselines.items()])
    # 四权重独立±10%检验。每轮均重新归一化并重选点。
    sens=[]
    for i,label in enumerate(["w1几何","w2接收","w3时间","w4预测半径"]):
        for fac in (.9,1.1):
            # 在同一粗搜—局部加密候选池上重算归一化目标，隔离“权重变化”的影响。
            ww=list(W); ww[i]*=fac; trial=normalize([dict(r) for r in rows],tuple(ww)); trial_peak=max(trial,key=lambda r:r["score"])
            b=min([r for r in trial if r["score"] >= (1-GOOD_ETA)*trial_peak["score"]],key=lambda r:(round(r["travel_s"],6),round(r["r_pred_m"],6),-r["score"]))
            sens.append([label,fac,b["x_m"],b["y_m"],b["score"],b["p_rec"],b["r_pred_m"]])
    with (TAB/"Q2权重敏感性.csv").open("w",newline="",encoding="utf-8-sig") as f: w=csv.writer(f); w.writerow(["扰动参数","倍率","最优S2_x(m)","最优S2_y(m)","评分","保证接收比例","预测MEC(m)"]); w.writerows(sens)
    # no_signal 只删除保证接收圆内的样本；验证未把1000—1500m区间硬删除。
    remain=no_signal_update(targets,(best["x_m"],best["y_m"]));
    with (TAB/"Q2闭环检验.csv").open("w",newline="",encoding="utf-8-sig") as f: w=csv.writer(f); w.writerow(["项目","数值"]); w.writerows([["A1样本数",len(targets)],["no_signal后保留样本数",len(remain)],["1000m内被排除数",len(targets)-len(remain)],["最优点预测MEC(m)",best["r_pred_m"]],["最优点移动时间(s)",best["travel_s"]]])
    # 接收半径蒙特卡洛：1000m内必收；1000--1500m的no_signal不允许作硬删除。
    rng=random.Random(2026); radii=[rng.uniform(1000,1500) for _ in range(2000)]
    receipt=[]
    for d in (900,1200,1600):
        received=sum(d<=r for r in radii)/len(radii)
        receipt.append([d,received,1-received,"确定排除" if d<=1000 else "不得硬删除"])
    with (TAB/"Q2接收逻辑检验.csv").open("w",newline="",encoding="utf-8-sig") as f: w=csv.writer(f); w.writerow(["测试距离(m)","接收率","no_signal率","no_signal约束解释"]); w.writerows(receipt)
    for name in ("Q2候选点评分.csv","Q2候选区域.csv","Q2策略对比.csv","Q2权重敏感性.csv","Q2闭环检验.csv","Q2接收逻辑检验.csv"): shutil.copy2(TAB/name,RESULT/name)
    shutil.copy2(HERE / "README.md", OUT / "README.md")
    print("最优点",best)
if __name__=="__main__": main()

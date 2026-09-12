"""问题4：混合定向/全向源的 RAHPS-B 全链路本地验证。

位置×方向联合后验把无信号作为负证据；多环方位覆盖补足定向源的可见性盲区。
策略层只接触接口观测，不读取或使用隐藏源位置、方向、接收半径。
"""
from __future__ import annotations
from pathlib import Path
import json
import argparse
import matplotlib.pyplot as plt
from rahps_core import RADIUS, RAHPSPolicy, SyntheticAdapter
from simulator_adapter import HttpSimulatorAdapter

ROOT=Path(__file__).resolve().parent; OUT=ROOT/"output"/"q4"; OUT.mkdir(parents=True,exist_ok=True)
def one(seed:int, draw:bool=False)->dict:
    api=SyntheticAdapter(seed,mixed=True); policy=RAHPSPolicy(api,mixed=True); result=policy.run(); result["seed"]=seed
    if draw:
        plt.rcParams["font.sans-serif"]=["Microsoft YaHei","SimHei","DejaVu Sans"];plt.rcParams["axes.unicode_minus"]=False
        p=[e for e in policy.events if "x_m" in e];xs=[e["x_m"] for e in p];ys=[e["y_m"] for e in p]
        fig,ax=plt.subplots(figsize=(8,8));ax.add_patch(plt.Circle((0,0),RADIUS,fill=False,ec="#34495e"));ax.plot(xs,ys,c="#8e44ad",lw=1,label="风险补盲观测轨迹")
        ax.set(aspect="equal",xlabel="x / m",ylabel="y / m",title="问题4：可见性信念更新与补盲规划（本地验证）");ax.grid(alpha=.25);ax.legend();fig.tight_layout();fig.savefig(OUT/"q4_route.png",dpi=220);plt.close(fig)
    return result
def main():
    try:
        parser=argparse.ArgumentParser();parser.add_argument("--official",action="store_true");parser.add_argument("--robot-id");parser.add_argument("--base-url",default="http://127.0.0.1:2026");args=parser.parse_args()
        if args.official:
            api=HttpSimulatorAdapter(args.robot_id,args.base_url);api.enter()
            try: result=RAHPSPolicy(api,mixed=True).run()
            finally: api.exit();api.export_log(OUT/"official_q4_command_log.json")
            print(result)
        else:
            results=[one(s,draw=s==202611) for s in (202611,202612,202613)]
            (OUT/"q4_local_validation.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8");[print(x) for x in results]
    except Exception as exc: print(f"问题4求解失败：{exc}")
if __name__=="__main__":main()

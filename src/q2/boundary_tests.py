"""问题2边界测试：交会退化、圆域边界与清除阈值分支。"""
from q1_q2_bridge import evaluate_with_q1, RADIUS
import csv, math
from pathlib import Path
OUT=Path(__file__).resolve().parent/'results'/'Q2边界测试.csv'
def b(a,c): return math.degrees(math.atan2(c[1]-a[1],c[0]-a[0]))
cases=[('近似平行交会',(0.,0.),(100.,0.),(1200.,10.)),('圆域近边界',(1500.,0.),(900.,700.),(1700.,100.)),('可清除阈值示例',(0.,0.),(800.,0.),(400.,400.)),('需继续检测示例',(0.,0.),(600.,0.),(1200.,700.))]
rows=[]
for name,s1,s2,g in cases:
 r=evaluate_with_q1([s1,s2],[b(s1,g),b(s2,g)])
 rows.append([name,r.status,r.diameter_m,r.mec_radius_m,'清除' if r.mec_radius_m<=20 else '继续检测'])
OUT.parent.mkdir(exist_ok=True)
with open(OUT,'w',newline='',encoding='utf-8-sig') as f:
 w=csv.writer(f); w.writerow(['测试情况','区域状态','区域直径(m)','最小外接圆半径(m)','决策分支']); w.writerows(rows)
print(OUT)

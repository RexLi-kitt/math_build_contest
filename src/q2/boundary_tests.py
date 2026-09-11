"""问题2方案卡边界测试：交会退化、物理域与清除阈值。"""
from q1_q2_bridge import evaluate_a2, bearing
import csv, math
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RESULT_OUT=HERE/'results'/'Q2边界测试.csv'
DELIVERY_OUT=ROOT/'outputs'/'q2'/'tables'/'Q2边界测试.csv'
def b(a,c): return math.degrees(math.atan2(c[1]-a[1],c[0]-a[0]))
cases=[('近似平行交会',(0.,0.),(100.,0.),(1200.,10.)),('圆域近边界',(1500.,0.),(900.,700.),(1700.,100.)),('可清除阈值示例',(0.,0.),(800.,0.),(400.,400.)),('需继续检测示例',(0.,0.),(600.,0.),(1200.,700.))]
rows=[]
for name,s1,s2,g in cases:
 r=evaluate_a2(s1,bearing(s1,g),s2,bearing(s2,g))
 rows.append([name,r.status,r.diameter_m,r.mec_radius_m,'清除' if r.mec_radius_m<=20 else '继续检测'])
for out in (RESULT_OUT, DELIVERY_OUT):
 out.parent.mkdir(parents=True,exist_ok=True)
 with open(out,'w',newline='',encoding='utf-8-sig') as f:
  w=csv.writer(f); w.writerow(['测试情况','区域状态','区域直径(m)','物理候选域MEC半径(m)','决策分支']); w.writerows(rows)
print(RESULT_OUT)
print(DELIVERY_OUT)

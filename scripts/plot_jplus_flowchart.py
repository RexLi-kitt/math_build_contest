"""J+ 流程图。依据用户论文节选及 outputs/q3/J+模型公式以及架构.md；不运行求解。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents/skills/paper-plot-style'))
from paper_style import apply_style, save_figure
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, FancyArrowPatch

apply_style()
matplotlib.rcParams['figure.constrained_layout.use'] = False
fig = plt.figure(figsize=(15/2.54, 23/2.54), layout='none')
ax = fig.add_axes([0, 0, 1, 1])
ax.set(xlim=(0, 15), ylim=(0, 23))
ax.axis('off')
BLUE, ORANGE, INK = '#5271AE', '#FFA660', '#303640'

def box(y, title, detail='', warm=False, h=1.38):
    color = ORANGE if warm else BLUE
    ax.add_patch(FancyBboxPatch((3.0, y-h/2), 9.0, h,
        boxstyle='round,pad=0.02,rounding_size=0.12', linewidth=1.0,
        edgecolor=color, facecolor='#FFF4E9' if warm else '#F0F5FB'))
    ax.text(7.5, y+(0.46 if '\n' in detail else 0.25 if detail else 0), title, ha='center', va='center', fontsize=10)
    if detail:
        ax.text(7.5, y-0.29, detail, ha='center', va='center', fontsize=8.5, linespacing=1.5)

def decision(y, text):
    ax.add_patch(Polygon([(7.5,y+.64),(10.3,y),(7.5,y-.64),(4.7,y)],
                         closed=True, facecolor='#FFF6DF', edgecolor=ORANGE, lw=1.0))
    ax.text(7.5,y,text,ha='center',va='center',fontsize=9)

def arrow(points, color=BLUE):
    for a,b in zip(points[:-2], points[1:-1]):
        ax.plot([a[0],b[0]],[a[1],b[1]],color=color,lw=1.05)
    ax.add_patch(FancyArrowPatch(points[-2],points[-1],arrowstyle='-|>',
                                mutation_scale=9,lw=1.05,color=color,shrinkA=0,shrinkB=0))

ax.text(7.5,22.3,'J+ 模型决策流程',ha='center',va='center',fontsize=12,color=BLUE)
box(20.95,'① 初始化与原点扫描','初始化 20 个频道状态，在原点完成首轮扫描')
box(18.85,'② 动态覆盖与未知频道检测','动态选择并访问下一个外环点，逐一检测未知频道')
box(16.75,'③ 停靠点观测与顺路清除','执行预算内共观测和低绕行顺路清除\n每次响应后更新可行域与清除状态',h=1.6)
decision(14.8,'七个外环点覆盖完成？')
box(12.65,'④ 构造开放路径与滚动调度','以未清除频道的最小覆盖圆圆心构造开放路径',warm=True)
box(10.55,'仅执行首频道的一个动作','满足清除条件 → 清除；否则 → 在线选点观测',warm=True)
box(8.45,'⑤ 响应反馈与状态更新','更新可行域、清除状态和任务顺序',warm=True)
decision(6.4,'全部信号源可靠清除？')
box(4.4,'结束',h=.8)

arrow([(7.5,20.24),(7.5,19.56)])
arrow([(7.5,18.14),(7.5,17.57)])
arrow([(7.5,15.93),(7.5,15.44)])
arrow([(7.5,14.16),(7.5,13.36)])
ax.text(7.75,13.83,'是',fontsize=8.5,va='center')
arrow([(4.7,14.8),(1.6,14.8),(1.6,18.85),(2.98,18.85)])
ax.text(3.7,15.03,'否',fontsize=8.5,ha='center')
ax.text(1.28,16.65,'继续覆盖',rotation=90,fontsize=8.5,ha='center',va='center',color=BLUE)
arrow([(7.5,11.94),(7.5,11.26)],ORANGE)
arrow([(7.5,9.84),(7.5,9.16)],ORANGE)
arrow([(7.5,7.74),(7.5,7.04)],ORANGE)
arrow([(10.3,6.4),(13.4,6.4),(13.4,12.65),(12.02,12.65)],ORANGE)
ax.text(11.2,6.65,'否',fontsize=8.5,ha='center')
ax.text(13.75,9.5,'重新规划 · 逐动作执行',rotation=90,fontsize=8.5,ha='center',va='center',color='#A85E27')
arrow([(7.5,5.76),(7.5,4.82)])
ax.text(7.75,5.35,'是',fontsize=8.5,va='center')
ax.plot([2,13],[2.95,2.95],color='#E5E8ED',lw=.8)
ax.text(7.5,2.2,'保证发现 → 保守定位 → 在线选点 → 滚动调度 → 可靠清除',
        ha='center',va='center',fontsize=8.8,color=BLUE)
save_figure(fig, ROOT / 'outputs/q3/figures/J+模型流程图')
plt.close(fig)

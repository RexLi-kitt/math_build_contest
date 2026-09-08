"""运行 python preview.py 生成评审样图。全部数据为合成演示数据。"""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from paper_style import apply_style, save_figure, PALETTE, CMAP, INK

apply_style()
fig = plt.figure(figsize=(21/2.54, 23/2.54), layout='constrained')
gs = fig.add_gridspec(4, 2, height_ratios=[.42, 1, 1, .16])
head = fig.add_subplot(gs[0,:]); head.axis('off')
head.text(0, .80, '团队论文绘图 · 基础风格 v0.1', fontsize=18, weight='normal')
head.text(0, .58, '白底细线 / 蓝橙主色 / 统一字体与标注', fontsize=10, color='#626C78')
for i,c in enumerate(PALETTE):
    head.add_patch(Rectangle((i*.20,.14),.045,.19, transform=head.transAxes, color=c, lw=0))
    head.text(i*.20+.055,.22,c,va='center',fontsize=8)

ax=fig.add_subplot(gs[1,0]); x=np.linspace(0,2.1,60)
for i,(slope,label,ls,m) in enumerate([(110,'方案 A','-','o'),(65,'方案 B','--','s'),(0,'方案 C','-.','^')]):
    ax.plot(x, 260+slope*x, label=label, linestyle=ls, marker=m,markevery=12,markerfacecolor='white')
ax.set(title='(a) 参数曲线',xlabel='行进距离（海里）',ylabel='覆盖宽度（m）')
ax.grid(axis='y');ax.legend(loc='upper left');ax.set_xlim(0,2.1);ax.set_ylim(220,560)

ax=fig.add_subplot(gs[1,1]);values=[344,318,300];colors=[PALETTE[1],PALETTE[3],PALETTE[0]]
bars=ax.bar(['等距方案','调整方案','优化方案'],values,color=colors,width=.56,edgecolor=INK,linewidth=.5)
ax.bar_label(bars,padding=5,fontsize=9)
ax.set(title='(b) 方案比较',ylabel='测线总长度（海里）',ylim=(0,405));ax.grid(axis='y');ax.set_axisbelow(True)

ax=fig.add_subplot(gs[2,0]);xx=np.linspace(0,4,90); yy=np.linspace(0,5,110); X,Y=np.meshgrid(xx,yy)
Z=30+120*(X/4)**1.35+25*np.sin(Y*.7)*np.cos(X*.5)
im=ax.pcolormesh(X,Y,Z,cmap=CMAP,shading='auto',vmin=20,vmax=170,rasterized=True)
ax.set(title='(c) 连续量分布',xlabel='东西距离（海里）',ylabel='南北距离（海里）',aspect='equal')
cb=fig.colorbar(im,ax=ax,shrink=.83,pad=.04);cb.set_label('水深（m）');cb.outline.set_linewidth(.5)

ax=fig.add_subplot(gs[2,1]);ax.set(title='(d) 测线与覆盖区域',xlabel='东西距离（海里）',ylabel='南北距离（海里）')
positions=np.array([.18,.55,.97,1.43,1.93,2.49,3.10,3.74])
for i,p in enumerate(positions):
    w=.40+.055*i
    ax.add_patch(Rectangle((max(0,p-w/2),0),min(4,p+w/2)-max(0,p-w/2),5,facecolor=PALETTE[1],alpha=.15,lw=0))
    ax.plot([p,p],[0,5],color=PALETTE[0],lw=1,label='测线' if i==0 else None)
    ax.annotate('',xy=(p,3 if i%2==0 else 2),xytext=(p,2 if i%2==0 else 3),arrowprops=dict(arrowstyle='->',lw=.9,color=PALETTE[0]))
ax.add_patch(Rectangle((0,0),4,5,fill=False,edgecolor=INK,lw=.8))
ax.set(xlim=(-.1,4.1),ylim=(-.1,5.1),aspect='equal')

foot=fig.add_subplot(gs[3,:]);foot.axis('off')
foot.text(0,.5,'评审样图：全部数据为合成演示数据，不代表论文计算结果。',fontsize=9,color='#626C78')
save_figure(fig,Path(__file__).parent/'style-preview')

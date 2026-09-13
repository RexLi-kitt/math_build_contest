"""Q4 paper figures from frozen routes and recorded direction observations."""
from pathlib import Path
import sys
import json
import math
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents/skills/paper-plot-style'))
sys.path.insert(0, str(ROOT / 'src/q4'))
from paper_style import apply_style, save_figure, PALETTE
from d_agent import point_in_convex_polygon
from feasible_region import build_region
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon, Wedge
from matplotlib.lines import Line2D

OUT = ROOT / 'outputs/q4/figures/paper_geometry'
BLUE, ORANGE = PALETTE[0], PALETTE[3]
apply_style()
plt.rcParams['figure.constrained_layout.use'] = False

def route(name):
    p = ROOT / f'src/q4/assets/d_model/{name.lower()}_winner_design.json'
    data = json.loads(p.read_text(encoding='utf-8'))
    return np.array([data['sites'][i] for i in data['order']])

def axes_map(ax):
    ax.set_aspect('equal')
    ax.set_xlabel('横坐标 x / m')
    ax.set_ylabel('纵坐标 y / m')
    ax.tick_params(labelsize=8)

def nearest(q, poly):
    if point_in_convex_polygon(tuple(q), tuple(map(tuple, poly))):
        return q.copy(), 0.0
    choices = []
    for a, b in zip(poly, np.roll(poly, -1, axis=0)):
        v = b-a
        t = np.clip(np.dot(q-a, v)/max(np.dot(v,v), 1e-20), 0, 1)
        p = a+t*v
        choices.append((p, np.linalg.norm(q-p)))
    return min(choices, key=lambda x:x[1])

def routes_figure():
    fig, axs = plt.subplots(1, 2, figsize=(15/2.54, 9/2.54), layout=None)
    fig.subplots_adjust(left=.10, right=.985, bottom=.30, top=.80, wspace=.32)
    meta = {}
    for ax, name, color, tag in zip(axs, ['B','C'], [BLUE,ORANGE], ['a','b']):
        pts = route(name)
        length = np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()
        meta[name] = {'stations':len(pts), 'open_length_m':float(length)}
        ax.add_patch(Circle((0,0),1800,fill=False,color='#9199A5',ls='--',lw=.9))
        ax.plot(*pts.T,color=color,lw=1.1,zorder=2)
        ax.scatter(*pts.T,s=13,color=color,zorder=3)
        for a,b in zip(pts[:-1],pts[1:]):
            ax.annotate('',xy=a+.60*(b-a),xytext=a+.40*(b-a),
                        arrowprops=dict(arrowstyle='->',color=color,lw=.9,mutation_scale=7))
        ax.scatter(0,0,marker='*',s=75,color='#303640',zorder=5)
        ax.scatter(*pts[-1],marker='s',s=32,facecolor='white',edgecolor=color,zorder=4)
        axes_map(ax)
        ax.set(xlim=(-2250,2250),ylim=(-2250,2250),xticks=[-2000,0,2000],yticks=[-2000,0,2000])
        ax.set_title(f'({tag}) {name} 路线 · {len(pts)} 站',fontsize=10,pad=25)
        ax.text(.5,1.02,f'开放路径 {length:,.2f} m',transform=ax.transAxes,ha='center',fontsize=8)
    fig.legend(handles=[Line2D([],[],color='#9199A5',ls='--',label='干扰源分布区域（R = 1800 m）'),
                        Line2D([],[],color='#303640',marker='*',ls='',label='原点 / 起点'),
                        Line2D([],[],color='#303640',marker='s',mfc='white',ls='',label='终点')],
               loc='lower center',bbox_to_anchor=(.5,.065),ncol=3,fontsize=7.5)
    fig.text(.5,.025,'箭头表示访问方向；检测点允许位于目标区域外。',ha='center',fontsize=8)
    save_figure(fig,OUT/'q4_certified_routes')
    plt.close(fig)
    return meta

def pruning_figure():
    log = ROOT/'outputs/q4/official_runs/D_official_20260913_105737.json'
    records=json.loads(log.read_text(encoding='utf-8'))['records']
    obs=[]
    for r in records:
        if r['path']=='/measure' and r['payload']['channel']==1 and r['response'].get('measure_result')=='direction':
            p=r['payload']['position']
            obs.append(((p['x'],p['y']),r['response']['svd_deg']))
            if len(obs)==2: break
    poly=np.array(build_region(obs,[]).polygon)
    assert len(poly)>=3
    candidates=[(q,*nearest(q,poly)) for q in route('C') if all(np.linalg.norm(q-np.array(o[0]))>1 for o in obs)]
    keep=min((x for x in candidates if 300<x[2]<=1500),key=lambda x:abs(x[2]-950))
    skip=min((x for x in candidates if x[2]>1500),key=lambda x:abs(x[2]-1950))
    fig,axs=plt.subplots(1,2,figsize=(15/2.54,9.6/2.54),layout=None)
    fig.subplots_adjust(left=.11,right=.98,bottom=.36,top=.87,wspace=.42)
    ax=axs[0]
    ax.add_patch(Circle((0,0),1800,fill=False,color='#AAB0BA',ls='--',lw=.8))
    for i,(p,angle) in enumerate(obs,1):
        ax.add_patch(Wedge(p,1500,angle-1,angle+1,fc=BLUE,ec=BLUE,alpha=.20,lw=.7))
        ax.plot(*p,'o',color=BLUE,ms=4)
        ax.annotate(f'$M_{i}$',p,xytext=(-17,7),textcoords='offset points',fontsize=9)
    ax.add_patch(Polygon(poly,fc=ORANGE,ec=ORANGE,lw=1.0,zorder=4))
    for (q,p,d),color,mark,txt in [(keep,BLUE,'o','保留'),(skip,ORANGE,'X','跳过')]:
        ax.scatter(*q,color=color,marker=mark,s=32,zorder=5)
        ax.plot([q[0],p[0]],[q[1],p[1]],ls='--',color=color,lw=1.1)
        ax.annotate(f'{txt}\n{d:.0f} m',q,xytext=(5,7),textcoords='offset points',fontsize=8,color=color)
    axes_map(ax)
    ax.set(xlim=(-2350,2350),ylim=(-2350,2350),xticks=[-2000,0,2000],yticks=[-2000,0,2000])
    ax.set_title('(a) 示向约束与候选测站',fontsize=10)
    ax=axs[1]
    center=poly.mean(axis=0)
    span=max(np.ptp(poly[:,0]),np.ptp(poly[:,1]))*1.8
    for p,angle in obs:
        ax.add_patch(Wedge(p,1500,angle-1,angle+1,fc=BLUE,ec=BLUE,alpha=.17,lw=.8))
    ax.add_patch(Polygon(poly,fc=ORANGE,ec=ORANGE,alpha=.8,lw=1.2,zorder=3))
    ax.text(*center,r'$P_h^{(2)}$',ha='center',va='center',fontsize=11,zorder=4)
    ax.set(xlim=(center[0]-span/2,center[0]+span/2),ylim=(center[1]-span/2,center[1]+span/2))
    axes_map(ax)
    ax.locator_params(axis='both',nbins=3)
    ax.set_title('(b) 可行域局部放大',fontsize=10)
    fig.text(.5,.18,r'$d(M,P_h^{(2)})\leq1500\ \mathrm{m}$：保留候选共观测',ha='center',fontsize=9,color=BLUE)
    fig.text(.5,.125,r'$d(M,P_h^{(2)})>1500\ \mathrm{m}$：安全跳过',ha='center',fontsize=9,color=ORANGE)
    fig.text(.5,.065,'真实示向重建；候选站点为判据演示，并非实际剪枝记录。',ha='center',fontsize=7.6)
    fig.text(.5,.025,'蓝色为 ±1° 示向约束；橙色为保守可行域；保留不代表必然接收。',ha='center',fontsize=7.6)
    save_figure(fig,OUT/'q4_safe_pruning')
    plt.close(fig)
    return {'source_log':str(log.relative_to(ROOT)),'channel':1,'observations':obs,
            'polygon':poly.tolist(),'keep_station':keep[0].tolist(),'keep_distance_m':float(keep[2]),
            'skip_station':skip[0].tolist(),'skip_distance_m':float(skip[2])}

if __name__=='__main__':
    info={'routes':routes_figure(),'pruning':pruning_figure()}
    (OUT/'figure_data.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(info,ensure_ascii=False,indent=2))

"""Plot existing MC035 geometry; no localization or random experiment is rerun.

Run from repository root: .venv/Scripts/python.exe -m src.q1.plot_random_geometry
"""
import json
from pathlib import Path
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle, Arc

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.agents/skills/paper-plot-style'))
from paper_style import apply_style, save_figure, PALETTE


def main():
    data = json.loads((ROOT / 'src/q1/results/experiment_data.json').read_text(encoding='utf-8'))
    case = next(c for c in data['cases'] if c['case_id'] == 'MC035')
    assert case['status'] == 'polygon' and case['passed']
    # Translation only: maintain original orientation, distances and aspect ratio.
    source = np.array(case['source'])
    stations = np.array(case['stations']) - source
    vertices = np.array(case['vertices']) - source
    endpoints = np.array(case['endpoints']) - source
    assert np.isclose(np.linalg.norm(endpoints[1]-endpoints[0]), case['diameter_m'])
    blue, sky, yellow, orange, red = PALETTE
    apply_style()
    plt.rcParams['figure.constrained_layout.use'] = False
    fig = plt.figure(figsize=(19/2.54, 9.8/2.54), layout='none')
    ax = fig.add_axes([.09,.18,.37,.72])
    detail = fig.add_axes([.57,.18,.37,.72])
    for a in (ax, detail):
        a.set_aspect('equal', adjustable='box')
        a.set_xlabel(r'相对横坐标 $x-x_S$（m）')
        a.set_ylabel(r'相对纵坐标 $y-y_S$（m）')
        a.tick_params(labelsize=8)
    ax.set(xlim=(-830,770), ylim=(-670,930))
    ax.set_xticks([-600,0,600]); ax.set_yticks([-600,0,600])
    detail.set(xlim=(-24,24), ylim=(-23,25))
    detail.set_axis_off()
    ax.set_title('(a) 监测点与测向交会', fontsize=10)
    detail.set_title('(b) 定位多边形与直径', fontsize=10)
    offsets = [(16,-20),(0,10),(-5,12)]
    for i, (p, obs) in enumerate(zip(stations,case['observations'])):
        theta = np.deg2rad(obs['measured_bearing_deg'])
        angles = theta + np.deg2rad(np.array([-1,1]))
        ends = p + 1300*np.column_stack([np.cos(angles),np.sin(angles)])
        ax.add_patch(Polygon([p,*ends],facecolor=sky,alpha=.18,edgecolor='none',zorder=0))
        for a in (ax, detail):
            for end in ends:
                a.plot([p[0],end[0]],[p[1],end[1]],color=sky,lw=.9,zorder=1)
        end = p + 1300*np.array([np.cos(theta),np.sin(theta)])
        ax.plot([p[0],end[0]],[p[1],end[1]],'--',color=blue,lw=1.1,zorder=2)
        ax.plot(*p,'o',color=blue,ms=5,zorder=6)
        ax.annotate(f'$M_{i+1}$',p,
                    xytext=offsets[i],textcoords='offset points',fontsize=10,ha='center',zorder=7)
    # The observed bearing at M1 is measured counterclockwise from east.
    p = stations[0]
    theta1 = case['observations'][0]['measured_bearing_deg']
    ax.plot([p[0],p[0]+250],[p[1],p[1]],color='#9299A3',lw=.8)
    ax.add_patch(Arc(p,320,320,theta1=0,theta2=theta1,color=orange,lw=1.2))
    ax.text(p[0]+180,p[1]+37,r'$\hat\theta_1$',color='#99602D',fontsize=9)
    ax.text(p[0]+265,p[1]-20,'东',fontsize=8,color='#6B737E')
    for a in (ax,detail):
        a.add_patch(Polygon(vertices,facecolor=yellow,alpha=.45,edgecolor='none',zorder=3))
        a.add_patch(Polygon(vertices,fill=False,edgecolor=blue,lw=1.6,zorder=4))
        a.plot(0,0,'*',color=red,ms=9,markeredgecolor='white',markeredgewidth=.4,zorder=8)
    ax.annotate('源点 S',(0,0),xytext=(24,-8),textcoords='offset points',fontsize=9,color=red)
    ax.add_patch(Rectangle((-24,-23),48,48,fill=False,edgecolor=orange,lw=1.2,zorder=7))
    ax.annotate('局部放大',(24,25),xytext=(20,280),fontsize=8,color='#99602D',
                arrowprops=dict(arrowstyle='-',color=orange,lw=.9))
    detail.plot(endpoints[:,0],endpoints[:,1],color=orange,lw=2.4,zorder=6)
    # Label the saved diameter endpoints A, B; name the remaining vertices C, D.
    remaining = iter('CD')
    for v in vertices:
        if np.allclose(v,endpoints[0]): name='A'
        elif np.allclose(v,endpoints[1]): name='B'
        else: name=next(remaining)
        detail.plot(*v,'o',color=blue,ms=4,zorder=7)
        offset = (7 if v[0]>0 else -12, 8 if v[1]>0 else -14)
        detail.annotate(name,v,xytext=offset,textcoords='offset points',fontsize=9)
    detail.annotate('S',(0,0),xytext=(3,-15),textcoords='offset points',color=red,fontsize=9)
    midpoint=endpoints.mean(axis=0)
    detail.annotate(r'$D=|AB|$',midpoint,
                    xytext=(0,25),textcoords='offset points',ha='center',fontsize=9,
                    arrowprops=dict(arrowstyle='-',color=orange,lw=.8),
                    bbox=dict(facecolor='white',edgecolor='none',alpha=.9,pad=2),zorder=9)
    save_figure(fig,ROOT/'outputs/q1/figures/modeling_geometry')
    # Additional high-resolution raster for print; the skill also exports vector PDF.
    fig.savefig(ROOT/'outputs/q1/figures/modeling_geometry_600dpi.png',dpi=600,
                facecolor='white',bbox_inches=None)
    plt.close(fig)
    print('Saved MC035 PNG/PDF; diameter:',case['diameter_m'])


if __name__ == '__main__':
    main()

"""读取 EQ_LAST 已有结果，按项目 paper-plot-style 导出等边三角形反例。

只绘图，不重新求解。运行：.venv/Scripts/python.exe -m src.q1.plot_equilateral
"""

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.agents/skills/paper-plot-style'))
from paper_style import apply_style, save_figure, PALETTE, INK
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Polygon, Patch, Rectangle

BLUE, SKY, YELLOW, ORANGE, RED = PALETTE


def new_axes(title, height=13):
    fig = plt.figure(figsize=(15/2.54, height/2.54), layout='none')
    ax = fig.add_axes([0.15, 0.30, 0.77, 0.59])
    fig.text(0.10, 0.95, title, ha='left', va='top', fontsize=11)
    ax.set_aspect('equal', adjustable='box')
    ax.set_xlabel('横坐标 x（m）')
    ax.set_ylabel('纵坐标 y（m）')
    return fig, ax


def draw_detail(case, out):
    vertices = case['vertices']
    center = case['circle_center']
    radius = case['circle_radius_m']
    source = case['source']
    # 本等边三角形的理论外接圆心与S重合，半径读取已有解析结果。
    mec_radius = case['analytic']['minimum_circle_radius_m']
    fig, ax = new_axes('等边三角形反例：同直径圆不能覆盖定位区域', 14)
    ax.set_xlim(-17, 19)
    ax.set_ylim(-18, 16)
    ax.set_xticks([-15,-10,-5,0,5,10,15])
    ax.set_yticks([-15,-10,-5,0,5,10,15])
    ax.add_patch(Circle(center, radius, facecolor=ORANGE, edgecolor=ORANGE,
                        linewidth=1.6, alpha=0.25, zorder=1))
    ax.add_patch(Circle(center, radius, fill=False, edgecolor=ORANGE, linewidth=1.6, zorder=2))
    ax.add_patch(Circle(source, mec_radius, fill=False, edgecolor=SKY,
                        linewidth=1.6, linestyle='--', zorder=2))
    ax.add_patch(Polygon(vertices, closed=True, facecolor=BLUE, alpha=0.12, zorder=2))
    ax.add_patch(Polygon(vertices, closed=True, fill=False, edgecolor=BLUE, linewidth=1.8, zorder=3))
    # 沿已有顶点顺序标记A、B、C；最远点对AB为底边。
    for name, point, offset in zip('ABC', vertices, [(-13,-2),(7,-2),(7,3)]):
        color = RED if name=='C' else BLUE
        ax.plot(*point, 'o', color=color, markersize=4, zorder=6)
        ax.annotate(name + ('（圆外）' if name=='C' else ''), point,
                    xytext=offset, textcoords='offset points', color=color, fontsize=9)
    ax.plot(*center, 'o', color=ORANGE, markersize=4.5, zorder=6)
    ax.annotate('O', center, xytext=(-13,-13),textcoords='offset points',color=INK)
    ax.plot(*source, '*', color=RED, markersize=8, zorder=6)
    ax.annotate('S', source, xytext=(-13,5),textcoords='offset points',color=RED)
    ax.plot([center[0],vertices[2][0]],[center[1],vertices[2][1]],
            color=RED,linestyle=':',linewidth=1.2,zorder=3)
    # 尺寸标注仅为显示转换，不改变点、圆或区域。
    x_dimension=15.2
    ax.annotate('',(x_dimension,vertices[2][1]),(x_dimension,center[1]),
                arrowprops={'arrowstyle':'<->','color':RED,'lw':1})
    ax.text(16.2,(vertices[2][1]+center[1])/2,
            r'$OC\approx17.32\,\mathrm{m}>10\,\mathrm{m}$',
            rotation=90,ha='center',va='center',fontsize=8,color=RED)
    ax.annotate('',(vertices[0][0],-8.4),(vertices[1][0],-8.4),
                arrowprops={'arrowstyle':'<->','color':BLUE,'lw':1})
    ax.text(0,-9.4,r'$D=AB=20\,\mathrm{m}$',ha='center',va='top',color=BLUE,fontsize=9)
    handles=[Patch(facecolor=BLUE,alpha=.25,edgecolor=BLUE,label='交会定位区域'),
             Line2D([],[],color=ORANGE,label='同直径圆（半径10 m）'),
             Line2D([],[],color=SKY,linestyle='--',label='最小外接圆（半径11.547 m）')]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.112),ncol=1,
               handlelength=2.8,labelspacing=.35)
    fig.text(.5,.061,r'$R_{\min}=20/\sqrt{3}\approx11.547\,\mathrm{m}>D/2=10\,\mathrm{m}$',
             ha='center',fontsize=9)
    fig.text(.5,.027,'算例 EQ_LAST；S为真实源点及本例最小外接圆圆心，O为AB中点。',
             ha='center',fontsize=7.5,color=INK)
    save_figure(fig,out/'equilateral_counterexample')
    plt.close(fig)


def draw_overview(case, out):
    fig, ax = new_axes('三次测向交会形成等边三角形定位区域', 13)
    ax.set_xlim(-720,720)
    ax.set_ylim(-670,670)
    ax.set_xticks([-600,-300,0,300,600])
    ax.set_yticks([-600,-300,0,300,600])
    offsets=[(8,13),(0,-22),(0,14)]
    aligns=['left','center','center']
    for point, obs, offset, align in zip(case['stations'],case['observations'],offsets,aligns):
        theta=math.radians(obs['measured_bearing_deg'])
        endpoints=[]
        # 射线仅为显示限制取900米；区域本身读取已有求解结果，不作裁剪求解。
        for angle in (theta-math.radians(1),theta+math.radians(1)):
            end=(point[0]+900*math.cos(angle),point[1]+900*math.sin(angle))
            endpoints.append(end)
            ax.plot([point[0],end[0]],[point[1],end[1]],color=SKY,linewidth=1,zorder=1)
        ax.add_patch(Polygon([point,*endpoints],facecolor=SKY,alpha=.12,edgecolor='none',zorder=0))
        end=(point[0]+900*math.cos(theta),point[1]+900*math.sin(theta))
        ax.plot([point[0],end[0]],[point[1],end[1]],color=BLUE,linestyle='--',linewidth=1,zorder=2)
        ax.plot(*point,'o',color=BLUE,markersize=4,zorder=3)
        label=obs['monitor']+f" ({point[0]:.2f}, {point[1]:.2f})"
        ax.annotate(label,point,xytext=offset,textcoords='offset points',ha=align,fontsize=8)
    ax.add_patch(Polygon(case['vertices'],facecolor=BLUE,edgecolor=BLUE,alpha=.7,zorder=4))
    ax.plot(*case['source'],'*',color=RED,markersize=6,zorder=5)
    ax.add_patch(Rectangle((-24,-24),48,48,fill=False,edgecolor=ORANGE,linewidth=1.2,zorder=4))
    ax.annotate('S=(0, 0)\n定位区域见放大图',(24,24),xytext=(190,140),
                arrowprops={'arrowstyle':'-','color':ORANGE,'lw':.9},fontsize=8,color=INK)
    handles=[Line2D([],[],color=BLUE,linestyle='--',label='测得的示向方向'),
             Line2D([],[],color=SKY,label='±1°误差边界'),
             Line2D([],[],marker='o',linestyle='none',color=BLUE,label='监测点'),
             Line2D([],[],marker='*',linestyle='none',color=RED,label='真实源点S')]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.095),ncol=2,
               columnspacing=1.8,handlelength=2.5)
    fig.text(.5,.052,'示向度：M1  1°，M2  121°，M3  241°；各误差半角均为1°。',
             ha='center',fontsize=8)
    fig.text(.5,.025,'算例 EQ_LAST；坐标轴等比例，三角形边长约20 m。',
             ha='center',fontsize=7.5)
    save_figure(fig,out/'equilateral_bearing_overview')
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=ROOT/'src/q1/results/experiment_data.json')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/q1/figures')
    args=parser.parse_args()
    data=json.loads(args.input.read_text(encoding='utf-8'))
    case=next(c for c in data['cases'] if c['case_id']=='EQ_LAST')
    if case['status']!='polygon' or case['circle_covers'] is not False or not case['checks']['triangle_boundary_matches']:
        raise ValueError('输入不是已经核对的等边三角形反例')
    apply_style()
    # 手动预留坐标标签、图例与结论的位置，不使用自动布局或裁边。
    plt.rcParams['figure.constrained_layout.use'] = False
    draw_detail(case,args.output)
    draw_overview(case,args.output)
    print(f'PNG/PDF 已导出至：{args.output}')


if __name__=='__main__':
    main()

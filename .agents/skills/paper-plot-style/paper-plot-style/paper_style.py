"""团队论文绘图风格 v0.1：评审草案，只改变表现，不改变数据。"""
from pathlib import Path
import matplotlib as mpl
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap
from cycler import cycler

PALETTE = ['#5271AE', '#70ACDE', '#F5CC7D', '#FFA660', '#D85B59']
INK = '#303640'
CMAP = LinearSegmentedColormap.from_list('team_blue_warm', PALETTE)

def apply_style():
    font = Path(__file__).parent / 'assets' / 'NotoSansSC.ttf'
    if not font.exists():
        raise FileNotFoundError(f'缺少团队字体：{font}。请同步完整样式目录。')
    font_manager.fontManager.addfont(str(font))
    name = font_manager.FontProperties(fname=str(font)).get_name()
    mpl.rcParams.update({
        'font.family': [name, 'DejaVu Sans'], 'font.size': 9,
        'mathtext.fontset': 'dejavusans', 'axes.unicode_minus': False,
        'figure.facecolor': 'white', 'axes.facecolor': 'white',
        'text.color': INK, 'axes.labelcolor': INK, 'axes.edgecolor': INK,
        'xtick.color': INK, 'ytick.color': INK,
        'axes.labelsize': 10, 'axes.titlesize': 11, 'axes.titleweight': 'normal',
        'axes.titlelocation': 'left', 'axes.titlepad': 10,
        'xtick.labelsize': 9, 'ytick.labelsize': 9, 'legend.fontsize': 8,
        'axes.spines.top': False, 'axes.spines.right': False,
        'axes.linewidth': .7, 'lines.linewidth': 1.6, 'lines.markersize': 4,
        'xtick.direction': 'out', 'ytick.direction': 'out',
        'xtick.major.width': .6, 'ytick.major.width': .6,
        'axes.grid': False, 'grid.color': '#E5E8ED', 'grid.linewidth': .6,
        'legend.frameon': False, 'figure.figsize': (15/2.54, 10/2.54),
        'axes.prop_cycle': cycler(color=[PALETTE[i] for i in [0,3,1,4,2]]),
        'figure.constrained_layout.use': True, 'savefig.dpi': 300,
        'savefig.bbox': None, 'pdf.fonttype': 42, 'svg.fonttype': 'path',
    })

def save_figure(fig, basename):
    """按原画布尺寸保存，不自动裁边，供 Word 按尺寸插入。"""
    base = Path(basename)
    base.parent.mkdir(parents=True, exist_ok=True)
    for ext in ('png', 'pdf'):
        fig.savefig(base.with_suffix('.' + ext), dpi=300, facecolor='white', bbox_inches=None)

---
name: paper-plot-style
description: 根据已有计算结果生成或修改论文数据图表，统一蓝橙配色、中文字体、字号和 PNG/PDF 导出。适用于数模论文曲线、柱状图、热力图和测线地图；不用于照片、艺术插画或重新求解模型。
---

# 论文绘图风格

先阅读本技能目录中的 [STYLE.md](STYLE.md)，遵循其中的视觉和数据约定。用户明确指定的期刊格式、尺寸和配色优先于默认值。

## 从已有结果绘图

1. 找到用户提供的结果文件、数组或已有绘图代码，确认字段含义、单位、比较对象和输出位置。可从上下文确定的信息不重复询问；缺少真实数据或关键含义时再询问。只有用户要求示例时才能使用合成数据，并在图和交付说明中标注。
2. 使用本技能的 `paper_style.py`，创建图之前调用 `apply_style()`，完成后调用 `save_figure(fig, basename)`。依据本 `SKILL.md` 所在目录定位模块，不假定当前工作目录就是技能目录。
3. 只改变表现，不改变数据、参数、单位或结论，不为绘图擅自重跑昂贵求解。不添加无依据的误差棒、显著性符号、平滑、插值或抽样。保留现有分析方法；必要的数据转换需在代码中说明。
4. 同一对象跨图固定同色；同一指标跨图比较时固定色标范围。轴标签注明含义和单位，图例避免遮挡数据，地图和几何关系保持适当比例。
5. 用 PNG 检查中文是否正确、标签是否裁切或重叠、图例是否遮挡和线条是否清晰；有问题则调整尺寸或布局后重新导出。导出 PNG 300 dpi 和 PDF，不使用自动裁边。未能运行或查看时明确说明，不声称已验证。
6. 交付图片、PDF 和可重运行的绘图代码，注明源数据路径和必要转换。正式输出保存到用户项目中，不覆盖技能内资源。正式图号和长图题交给论文排版。

## 运行与资源

- 依赖见 [requirements.txt](requirements.txt)。优先使用项目已有环境；需要新环境时在项目中建立虚拟环境并安装依赖，不覆盖现有依赖清单。
- 字体为 `assets/NotoSansSC.ttf`，授权在 `assets/OFL.txt`。必须保留完整目录；缺失时报错，不能静默换成系统中文字体。
- [preview.py](preview.py) 提供四类合成数据样图，仅在需要演示或验证安装时运行。它会在技能目录生成 `style-preview.png` 和 `style-preview.pdf`，不代表用户的研究结果。
- 默认单幅宽 15 cm；预览总览宽 21 cm，不能直接作为单幅模板。

在项目的绘图脚本中，可用以下方式导入（示例假设脚本位于仓库根目录且技能已放入 `.agents/skills`）：

```python
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SKILL_DIR = ROOT / '.agents' / 'skills' / 'paper-plot-style'
sys.path.insert(0, str(SKILL_DIR))
from paper_style import apply_style, save_figure, PALETTE, CMAP
import matplotlib.pyplot as plt

apply_style()
# 从实际结果读取数据并创建图形。
# save_figure(fig, ROOT / 'figures' / 'result')
```

脚本位于其他目录时调整 `ROOT`；手动引用未安装的技能时使用其实际路径。保存的脚本应使用项目相对定位，避免绑定作者电脑的绝对路径。

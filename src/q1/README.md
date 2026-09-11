# Q1：交会定位前四步

主要实现：`localization.py`。需要 Python 3.10 或以上，仅使用标准库，无需安装第三方依赖。

从仓库根目录运行示例：

```python
from src.q1.localization import localize

# 同一固定干扰源的有效观测；仅演示调用，不是正式比赛数据。
result = localize(
    stations=[(0, 0), (100, 0), (0, 100)],
    bearings_deg=[45, 135, 315],
    error_deg=1,
)
print(result.region.status)
print(result.region.float_vertices())
if result.diameter is not None:
    print("直径（米）：", result.diameter.distance)
    print("最远点对：", result.diameter.endpoints)
if result.circle is not None:
    print("圆心：", tuple(map(float, result.circle.center)))
    print("半径（米）：", result.circle.radius)
    print("同直径圆能否覆盖：", result.circle.covers)
```

## 可单独调用的函数

| 函数 | 输入 | 输出 |
|---|---|---|
| `bearing_halfplanes` | 检测点、示向度、误差半角 | 半平面约束元组 |
| `intersect_halfplanes` | 任意二维闭半平面组 | 区域状态、有序顶点、可行点、无界延伸方向 |
| `convex_diameter` | 有限点集，算法选择 | 凸包直径、距离平方、最远点对 |
| `diameter_circle_coverage` | 有限点集 | 同直径圆的圆心、半径、覆盖结论、最远顶点及超出量 |
| `localize` | 检测点、示向度、误差半角、算法选择 | 串联前四步的完整结果 |

`HalfPlane(a, b, c)` 表示 `a*x + b*y <= c`，可用于定位以外的通用半平面交。例如矩形：

```python
from src.q1.localization import HalfPlane, intersect_halfplanes, convex_diameter

region = intersect_halfplanes([
    HalfPlane(-1, 0, 0), HalfPlane(1, 0, 4),
    HalfPlane(0, -1, 0), HalfPlane(0, 1, 3),
])
diameter = convex_diameter(region.vertices, method="calipers")
```

## 结果状态

- `empty`：约束不一致。串联入口返回 `diameter=None, circle=None`。
- `unbounded`：可行但无界。直径为正无穷，无有限覆盖圆；给出一个可行点及非零延伸方向。此时 `vertices` 留空，不能当作有限多边形。
- `point`：单点，直径及圆半径为零。
- `segment`：线段，直径为端点距离。
- `polygon`：凸多边形，顶点逆时针排列，不重复首点。

空观测表示全平面，返回 `unbounded`；两组输入长度不一致、非法数值、非法误差半角会抛出异常。

这里的「圆」一律指 `diameter_circle_coverage` 输出的**以区域直径为直径的同直径圆**，半径即 D/2，与 `diameter.distance / 2` 相同；本模块不计算通用最小外接圆（MEC）。等边三角形反例的最小外接圆半径 20/√3 米只作为解析值出现在实验与绘图中。

## 算法与数值范围

角度从正东逆时针计量，单位为度。默认误差半角 1°，接口支持 `0 < error_deg < 90`。不会对同一位置的重复测向取平均，也不会添加目标圆域或人工矩形截断。调用者负责保证所有观测对应同一固定干扰源。

半平面交采用边界交点枚举，约束数为 k 时为 O(k³) 次有理数运算，适合第一问的少量观测。可行性通过原点、边界垂足和边界交点检查；有界性通过二维衰退方向检查。因此不依赖线性规划库。该实现与方案卡提出的线性规划检查具有相同目的，具体实现路径不同。

直径默认使用旋转卡壳，也支持 `method="exhaustive"`。对任意输入点集先求凸包，预处理 O(m log m)；之后旋转卡壳 O(m)，枚举 O(m²)。

几何运算保留 `Fraction` 有理数，平行判断、去重、凸包和覆盖判定针对输入系数进行精确比较，不用任意阈值裁掉狭长区域。角度转方向时仍使用浮点三角函数，所以这不等同于对真实角度的符号精确计算；极端临界构型可能受到角度转换舍入影响。不会自动修改误差界以修复矛盾约束。

后续函数优先传递原始 `region.vertices`。`float_vertices()` 用于打印或绘图；直径和圆半径也为浮点显示值，距离平方和顶点保持有理数。尺度过大导致浮点显示溢出时会抛出异常；本题的米级坐标远小于通常的浮点上限。有理数运算耗时还受数值位数影响，本实现不适用于海量约束。

## 随机实验与边界测试

`experiments.py` 已实现第一轮结果检验。仓库根目录执行：

```text
python -m src.q1.experiments --cases 100 --seed 20260911
```

也可通过 `--output` 指定其他结果目录。默认输出到 `src/q1/results`：

- `定位实验汇总.csv`：一组一行，含真实源点 S、全部监测点 M1～M6 的坐标、直径、区域状态及检查结果。不存在的监测点坐标留空。
- `观测明细.csv`：一次观测一行，含真实方位、加入误差、模拟示向度和源点距离。
- `边界测试.csv`：确定性构造的空集、无界、单点、线段、近乎平行及角度跨零测试。
- `误差界敏感性.csv`：一次「组×误差档」一行，含误差半角、区域状态、直径、包含检查与直径不减检查。
- `experiment_data.json`：完整输入、每项检查结果、区域顶点、最远点对、圆参数、随机种子和代码摘要，供复算与导表。

实验中 S 指真实干扰源，M_i 指监测点；前面模型里的 G 与这里的 S 同义。S 在半径 1800 米圆域内按面积均匀抽样；每组 2～6 个监测点，各自在以 S 为中心、半径 50～900 米的环域内按面积均匀抽样。这样能避开近距离测向盲区，且距离小于最小有效接收半径。允许监测点在目标圆域外。

不同监测点的误差按 U(-1°,1°) 抽样，这是实验设计，不是题目额外给定的概率假设。固定随机种子可复现同一测试集；不按输出区域形状筛样，也不通过重抽样隐藏无界或失败结果。

每个随机组检查：输入误差满足上界、真值满足半平面约束、真值位于输出多边形、输出顶点满足全部约束、旋转卡壳与枚举所得距离平方精确一致。无界组检查非零可行延伸方向，并单独记录。圆覆盖为“否”是合法的几何结果，并不表示算法检查失败。

误差界敏感性固定同一组观测，只把误差半角依次改为 0.9°、1.0°、1.1°，检查区域随误差界放宽而扩张、非空有界时直径不减。模拟误差本身抽样于 [−1°,1°]，故 0.9° 档出现空集属于预期结果，只记录状态、不计失败；空集与无界档的直径单调性记为空缺。

主测试集最后一组 `EQ_LAST` 用三组测向楔形构造边长约 20 米的等边三角形。通过几何输出与理论顶点、理论直径核对（绝对容差 1e-8 米），并确认同直径圆不能覆盖。三角函数带来的数值近似与理论上的精确等边三角形应区分。理论最小外接圆半径为 20/√3 ≈ 11.547005 米，大于直径的一半 10 米。

确定性边界测试与蒙特卡洛分开统计。连续随机抽样几乎不可能恰好生成点或线段，因此精确退化采用整数/有理数半平面直接构造；跨零、小交会角以及相背观测空集、单观测无界则测试完整测向入口。

第一轮固定种子 20260911 的结果：100/100 个随机组通过且均为凸多边形，9/9 项边界测试通过，最后的等边三角形反例通过，误差界敏感性 300/300 项通过。该结果只说明这些测试未发现错误，不能代替数学证明，也不表示任意输入均可成功定位。

`export_workbook.mjs` 将 JSON 快照整理为 Excel，使用 Codex 附带的 `@oai/artifact-tool`。Python 求解和 CSV 输出不依赖它。脚本直接从当前用户的 Codex 运行时解析依赖，无需在项目内创建目录链接；若运行时位置不同，可通过环境变量 `Q1_NODE_MODULES` 指定 Node 包目录。使用相应 Node 执行：

```text
node src/q1/export_workbook.mjs [输入JSON路径] [输出XLSX路径]
```

默认工作簿位于 `outputs/q1/tables/Q1_定位实验.xlsx`，包含“定位实验”“观测明细”“边界测试与方法”“误差界敏感性”。预览与导出检查日志放入本次运行独有的系统临时目录，结束后自动清理；如需人工查看预览，可设置环境变量 `Q1_KEEP_PREVIEWS=1` 保留。表格是运行结果快照，更改坐标后必须重跑实验和导表，不会在 Excel 内自动调用几何函数。

## 等边三角形反例绘图

`plot_equilateral.py` 读取 `EQ_LAST` 的现有结果，调用项目 `paper-plot-style` 技能输出局部圆覆盖反例图与测向交会总览图，不重新求解。执行：

```text
.venv/Scripts/python.exe -m src.q1.plot_equilateral
```

绘图依赖见 `.agents/skills/paper-plot-style/requirements.txt`。PNG（300 dpi）和 PDF 均位于 `outputs/q1/figures`，该目录说明文件记录了源数据、画布尺寸和显示转换。

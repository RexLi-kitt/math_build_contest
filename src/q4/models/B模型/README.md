# B 模型：认证环路线（Certified Route）

## 一句话

用几何证书（定向可见性角隙 ≤ 180°）离线搜索出 **27 站、20.4 km** 的扫描路线，
正常 500 局 **667.36 s/源（100% 全清除）**，边界压力 200 局 **572.67 s/源（100%）**。

## 与基线对比（同批配对案例）

| 场景 | B 模型（27 站） | 保底基线 ShiftB（28 站） | H8（31 站） |
|---|---:|---:|---:|
| 正常 500 局 s/源 | **667.36** | 756.10 | 713.42 |
| 正常 P95 | **856.96** | 996.11 | 916.52 |
| 压力 200 局 s/源 | **572.67** | 702.78 | 638.58 |
| 压力 P95 | **676.80** | 797.03 | 765.97 |
| 证书 gap | 162.2°（余量 17.8°） | 150.2° | 151.4° |
| 巡游长度 | 20.4 km | 26.2 km | 21.4 km |

## 文件

| 文件 | 说明 |
|---|---|
| `cert_route_agent.py` | 出货代理：`CertRouteAgent`（冠军）/ `CertRouteAggressiveAgent`（备选 29 站） |
| `winner_design.json` | 冠军设计：27 站坐标 + TSP 访问顺序 + 证书/验证数字 |
| `aggressive_design.json` | 备选设计：29 站 / 18.1 km / 证书 173.9° |
| `优化结果.md` | 完整报告（方法、证书、时间构成、复现命令） |
| `certificate/certfast.py` | numpy 向量化审计 + 管道云审计 |
| `certificate/certify_final.py` | certify.py 原版双网格终审脚本 |
| `results/paired_holdout500/summary.json` | 正常组 500 局汇总 |
| `results/stress_boundary200/summary.json` | 边界压力 200 局汇总 |

## 接入官方 runner

```python
from cert_route_agent import CertRouteAgent
# 注册进策略表, 替换 Q4_full_clear_950_C2 / ShiftB
```

代理构造时读取一次同目录设计 JSON，运行时无额外求解开销；若基线模块
`q4_experiment` 不在 `sys.path`，模块会自动追加
`C:\Users\李\Desktop\第四问定向源实验`。

## 复现

```powershell
# 证书终审（约 10 秒）
python certificate/certify_final.py

# 设计搜索与配对验证的完整工具链在:
#   C:\Users\李\Desktop\第四问路线压缩\
```

## 注意

- 以上为离线模拟器结果，正式测试前请先用官方模拟器做 ≥100 局演练。
- 冠军证书 gap 162.2°（距 180° 余量 17.8°），三种审计分辨率结果一致。
- 若追求更短路线可换备选 29 站版，但证书余量降至 6.1°。
- 第一轮迭代（扫描中插入 / 动作点路由 / 绕行上限）已实测，均未超过当前模型；
  详见 `迭代记录.md`（可作论文消融实验），原始汇总在 `results/iter_screens/`。

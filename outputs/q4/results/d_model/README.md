# D 模型冻结证据

| 文件 | 内容 |
|---|---|
| `cplus3a_validation.json` | C+3A 对 C+、B、C 的五场景验证 |
| `cplus3f_validation.json` | C+3F 对 C+3A 与既有基线的五场景验证 |
| `d_b_filter_validation.json` | C+3FB（现 D）在 normal 与两类边界场景的 150 例验收 |
| `d_source_count_validation.json` | D 在 10/12/14/16 源下的分层弱支配验证 |
| `dg2_screen.json` | 延迟门控与 B 路线重排筛选 |
| `mixture_report.json` | 五档朝外比例下的连续过渡实验 |
| `manifest.json` | D 代码、B/C 设计资产和两份核心验收文件的 SHA-256 清单 |

不同文件来自不同实验批次，绝对均值不直接混合。模型升级结论以文件内部同批案例的配对
差为准。当前生产实现为 `src/q4/d_agent.py` 中的 `DAgent`。

`d_b_filter_validation.json` 来自探索目录的原始验收。原探索代理的真值审计曾直接迭代
`sim.sources` 字典键，因此文件里的 `truth_hits_total=0` 不作为冻结依据；距离门安全性由
1500 m 上界与保守可行域的构造证明支持。仓库生产类已经移除真值访问。

可从仓库根目录运行 `python -B src/q4/run_d_validation.py`，重新生成同口径的分层配对结果。

完整修正版鲁棒性实验位于相邻目录 `../d_robustness/`。该版本区分独立案例数与模型运行
次数，并修正了旧探索实验的剪枝审计范围、空间场景方向和清除字段口径。

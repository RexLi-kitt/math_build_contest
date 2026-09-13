# q2_actual_replay.py 变动说明与前后对比

## 1. 文档目的

本文记录 `src/q2/核心代码段/q2_actual_replay.py` 的必要修改。Q2 方案卡不变，首测点 S1 继续使用固定示例坐标，不作为本次修改内容。

## 2. 修改结论

本次只保留两项必要修改：

1. 修正 Python 导入路径，使文件可以直接运行。
2. 将 `no_signal` 的失败罚值与真实 MEC 分列，避免把 250 m 当作实际定位误差。

函数签名、S1 坐标、接收与清除判断逻辑均保持原样。

## 3. 前后变动对比

| 项目 | 修改前 | 修改后 | 修改原因 |
|---|---|---|---|
| 导入路径 | `parents[1] / "q2"`，指向不存在的 `src/q2/q2` | `parents[1]`，指向 `src/q2` | 修复直接运行时的 `ModuleNotFoundError` |
| no_signal 的 MEC | `mec_m=250.0` | `mec_m=None` | 250 m 是失败罚值，不是实际 MEC |
| 失败罚值字段 | 无 | `mec_penalty_m=250.0` | 保留外层优化所需的失败惩罚 |
| near 返回 | `mec_m=0.0` | 增加 `mec_penalty_m=0.0` | 统一各分支返回字段 |
| direction 返回 | `mec_m=实际MEC` | 增加 `mec_penalty_m` | 便于下游统一处理 |

## 4. 代码前后对比

### 4.1 导入路径

修改前：

```python
Q2_DIR = Path(__file__).resolve().parents[1] / "q2"
sys.path.insert(0, str(Q2_DIR))
```

修改后：

```python
Q2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Q2_DIR))
```

### 4.2 no_signal 分支

修改前：

```python
return {
    "return_type": "no_signal",
    "received": False,
    "mec_m": FAILURE_MEC,
    "can_clear": False,
}
```

修改后：

```python
return {
    "return_type": "no_signal",
    "received": False,
    "mec_m": None,
    "mec_penalty_m": FAILURE_MEC,
    "can_clear": False,
}
```

### 4.3 未改变的接口

以下内容保持不变：

```python
def replay_second_measurement(g_true, receive_radius_m,
                              first_bearing_deg, second_error_deg,
                              s2):
```

```python
S1 = (-750.0, -450.0)
```

因此现有调用方不需要增加 `s1` 参数。

## 5. 返回字段对比

| 字段 | 修改前 | 修改后 | 说明 |
|---|---|---|---|
| `return_type` | 有 | 有 | `direction`、`near` 或 `no_signal` |
| `received` | 有 | 有 | 是否收到第二次信号 |
| `mec_m` | 有 | 有 | 真实 MEC；no_signal 时为 `None` |
| `mec_penalty_m` | 无 | 有 | 仅供外层损失使用的失败罚值 |
| `can_clear` | 有 | 有 | MEC 不超过 20 m 时为真 |

## 6. 行为对比

| 场景 | 修改前行为 | 修改后行为 |
|---|---|---|
| 直接运行文件 | 报 `ModuleNotFoundError` | 正常导入并结束运行 |
| 距离小于等于 5 m | 返回 `near` | 返回 `near`，并增加罚值字段 0 |
| 距离超过接收半径 | 返回 `no_signal`，`mec_m=250` | 返回 `no_signal`，`mec_m=None`，罚值单列 |
| 收到 direction | 返回实际 MEC | 返回实际 MEC，并增加罚值字段 |
| 更换首测点 | 仍使用固定 S1 | 仍使用固定 S1，按已确定口径不变 |

## 7. 验证结果

验证结果：

- `direction`：返回实际 MEC，`can_clear` 按 20 m 阈值判断。
- `near`：返回 `mec_m=0.0`、`mec_penalty_m=0.0`、`can_clear=True`。
- `no_signal`：返回 `mec_m=None`、`mec_penalty_m=250.0`、`can_clear=False`。

验证命令：

```text
python src/q2/核心代码段/q2_actual_replay.py
python -m py_compile src/q2/核心代码段/q2_actual_replay.py
```

## 8. 对下游代码的影响

1. 统计真实 MEC 时，应过滤 `mec_m=None` 的 `no_signal` 记录。
2. 外层损失可以使用 `mec_penalty_m`，该字段不是实际定位误差。
3. 固定 S1 是当前约定，调用方无需修改参数。
4. 该文件是核心代码片段，正式实验入口仍保留自己的回放实现。若后续需要完全统一，应一次性合并两套实现。

## 9. 当前状态

- 已修正导入路径。
- 已分离真实 MEC 与失败罚值。
- 已通过语法编译。
- Q2 方案卡未修改。
- 固定 S1 保持不变。

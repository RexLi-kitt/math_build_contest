# 功能：以最坏覆盖距离闭式解联合设计覆盖环点数 k 与半径 R，解析保证任务圆域内每个源都被某个停靠点覆盖。
from __future__ import annotations

import math

AREA_R = 1800.0        # 任务圆域半径（m）
MIN_RECEIVE_R = 1000.0  # 接收半径下界；检测必须 d <= 1000 m 才能保证有信号
RING_COUNT = 7         # J+ 采用的环点数 k
SEARCH_RING_R = 1000.0  # J+ 采用的环半径 R（m）


def worst_coverage_distance(k: int, ring_r: float) -> float:
    """k 个等角环点、半径 R 时的最坏覆盖距离。

    最坏点落在任务圆域边界上相邻环点的角平分线处：
        d_k(R) = sqrt(1800² + R² − 2·1800·R·cos(π/k))。
    """
    return math.sqrt(AREA_R ** 2 + ring_r ** 2 - 2.0 * AREA_R * ring_r * math.cos(math.pi / k))


def min_safe_radius(k: int) -> float:
    """由 d_k(R) <= 1000 解出的最小安全半径 R_min(k)。

    R² − 3600·cos(π/k)·R + 2240000 <= 0，取较小根：
        R_min(k) = 1800·cos(π/k) − sqrt(3240000·cos²(π/k) − 2240000)。
    """
    cosine = math.cos(math.pi / k)
    return AREA_R * cosine - math.sqrt(3240000.0 * cosine * cosine - 2240000.0)


def open_sweep_length(k: int, ring_r: float) -> float:
    """原点 + k 个环点的开环巡回长度：R·(1 + 2(k−1)·sin(π/k))。"""
    return ring_r * (1.0 + 2.0 * (k - 1) * math.sin(math.pi / k))


def search_points(k: int = RING_COUNT, ring_r: float = SEARCH_RING_R):
    """覆盖发现层的停靠点集合：原点（覆盖圆心附近）+ k 个等角外环点。

    每多一个环点要多扫一轮未发现频道（约 60 s）：k=6→7 省 106 s 移动只付约 61 s
    扫描；k=7→8 只省 49 s 移动却仍付约 60 s，故联合最优取 k=7、R≈1000。
    """
    step = 360.0 / k
    return [(0.0, 0.0)] + [
        (ring_r * math.cos(math.radians(step * i)), ring_r * math.sin(math.radians(step * i)))
        for i in range(k)
    ]


if __name__ == "__main__":
    for k in (6, 7, 8):
        print(f"k={k}: R_min={min_safe_radius(k):8.1f} m   "
              f"d_k(1000)={worst_coverage_distance(k, 1000.0):8.2f} m   "
              f"巡回(R=1000)={open_sweep_length(k, 1000.0):7.0f} m")
    print(f"J+ 采用 k={RING_COUNT}, R={SEARCH_RING_R:.0f} m："
          f"最坏覆盖 {worst_coverage_distance(RING_COUNT, SEARCH_RING_R):.2f} m"
          f"（余量 {MIN_RECEIVE_R - worst_coverage_distance(RING_COUNT, SEARCH_RING_R):.2f} m），"
          f"巡回 {open_sweep_length(RING_COUNT, SEARCH_RING_R):.0f} m")

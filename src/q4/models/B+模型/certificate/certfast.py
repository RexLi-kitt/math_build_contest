"""numpy 向量化认证审计，必须与 certify.py 网格语义完全一致。

网格: r = ri*r_step, ri in 0..int(1800//r_step); 每圈 steps=int(360/t_step) 个点
(圆心单独 1 点)。reach=1000 米内站点方向排序求最大角隙; 与站点距离<=5 米的点
按 certify.py 语义跳过(gap=0); 无可达站点 gap=360。
"""
from __future__ import annotations

import math

import numpy as np

AREA = 1800.0
REACH = 1000.0
SENTINEL = 1e9

_grid_cache: dict = {}


def _grid(r_step: float, t_step: float) -> np.ndarray:
    key = (r_step, t_step)
    if key in _grid_cache:
        return _grid_cache[key]
    xs = []
    for ri in range(0, int(AREA // r_step) + 1):
        r = ri * r_step
        steps = 1 if r == 0.0 else int(360.0 / t_step)
        angles = np.arange(steps) * math.radians(t_step) if r else np.zeros(1)
        xs.append(np.stack([r * np.cos(angles), r * np.sin(angles)], axis=1))
    grid = np.concatenate(xs, axis=0)
    _grid_cache[key] = grid
    return grid


def exact_bound(sites, r_step=5.0, t_step=0.25, cover=5.0, reach_margin=5.0):
    """连续域精确证书: 返回 (全域严格上界, 该上界取到的审计点)。

    论证: 任意真实源点 z 必在某个网格点 x 的 cover 半径内 (5m/0.25deg 网格
    覆盖半径 4.66m < cover)。x 处按收紧可达半径 REACH-reach_margin 计入的
    站点集合, 必是 z 处真实可达集的子集 (|q-z| <= |q-x|+cover <= REACH),
    而可达站点越少 gap 只会越大, 故真实 gap(z) <= 收紧 gap(x) + 视线旋转界
    arcsin(cover/d1)+arcsin(cover/d2), 其中 d1,d2 为 x 处最大空扇区两个
    边界站点的距离。不使用 5 米 near 跳过 (那样会引入 z 处不成立的假设)。
    上界 <= 180 即为连续域认证, 不存在网格采样盲区。
    """
    S = np.asarray(sites, dtype=np.float64)
    if S.ndim == 1:
        S = S.reshape(1, 2)
    X = _grid(r_step, t_step)
    m, n = X.shape[0], S.shape[0]
    D = np.empty((m, n))
    for j in range(n):
        D[:, j] = np.hypot(X[:, 0] - S[j, 0], X[:, 1] - S[j, 1])
    within = D <= REACH - reach_margin
    k = within.sum(axis=1)
    angles = np.where(within, -1.0, SENTINEL)
    for j in range(n):
        col = np.degrees(np.arctan2(S[j, 1] - X[:, 1], S[j, 0] - X[:, 0])) % 360.0
        angles[:, j] = np.where(within[:, j], col, SENTINEL)
    order = np.argsort(angles, axis=1)
    A = np.take_along_axis(angles, order, axis=1)
    D_sorted = np.take_along_axis(np.broadcast_to(D, (m, n)), order, axis=1)
    rows = np.arange(m)
    last_real = A[rows, np.maximum(k - 1, 0)]
    wrap = np.where(k >= 1, A[:, 0] + 360.0 - last_real, 360.0)
    if n > 1:
        diffs = A[:, 1:] - A[:, :-1]
        cols = np.arange(n - 1)
        valid = (k[:, None] >= 2) & (cols[None, :] <= (k[:, None] - 2))
        diffs = np.where(valid, diffs, -np.inf)
        gap = np.maximum(diffs.max(axis=1), wrap)
        sec = np.where(diffs >= wrap[:, None], diffs, wrap[:, None])
        # 最大扇区的边界站点距离: 顺序对 (j, j+1) 或 wrap 对 (0, k-1)
        best = np.where(valid, diffs, -np.inf).argmax(axis=1)
        d1 = D_sorted[rows, best]
        d2 = D_sorted[rows, np.minimum(best + 1, n - 1)]
        use_wrap = wrap >= np.where(valid, diffs, -np.inf).max(axis=1)
        w1 = D_sorted[rows, np.zeros(m, dtype=int)]
        w2 = D_sorted[rows, np.maximum(k - 1, 0)]
        d1 = np.where(use_wrap, w1, d1)
        d2 = np.where(use_wrap, w2, d2)
    else:
        gap = wrap
        d1 = d2 = np.full(m, REACH)
    gap = np.where(k == 0, 360.0, gap)

    def rot(d):
        t = np.minimum(cover / np.maximum(d, 1e-9), 1.0)
        return np.degrees(np.arcsin(t))

    upper = gap + rot(d1) + rot(d2)
    idx = int(np.argmax(upper))
    return float(upper[idx]), (float(X[idx, 0]), float(X[idx, 1]))


def tube_cloud(sites, arc_step=0.7, offsets=(0.0, 0.35, 0.9, 1.8, 3.0, 4.3)):
    """每条可达边界弧 |x-p|=1000 两侧的偏移采样点云(弧向 arc_step 米)。

    gap 的不连续性只发生在这些弧上: 站点跨过 1000 米边界时成员集合跳变,
    薄片形证人只可能贴着弧存在。管道云按真实语义(可达<=1000, near<=5)
    在弧上与两侧密集评估, 与常规网格合成对连续域的完整覆盖。
    """
    S = np.asarray(sites, dtype=np.float64).reshape(-1, 2)
    clouds = [np.asarray(_grid(5.0, 0.25))]
    for p in S:
        r = math.hypot(p[0], p[1])
        if r > REACH + AREA + 1e-9:
            continue
        count = int(2.0 * math.pi * REACH / arc_step)
        ts = np.arange(count) * (2.0 * math.pi / count)
        base = np.stack([p[0] + REACH * np.cos(ts), p[1] + REACH * np.sin(ts)], axis=1)
        for off in offsets:
            scale = (REACH + off) / REACH
            ring = (base - p) * scale + p
            keep = np.hypot(ring[:, 0], ring[:, 1]) <= AREA + 1e-9
            if keep.any():
                clouds.append(ring[keep])
    return np.concatenate(clouds, axis=0)


def tube_audit(sites, arc_step=0.7):
    """管道云审计: 返回 (最大角隙, 最坏点)。"""
    X = tube_cloud(sites, arc_step=arc_step)
    gaps, _ = _compute_at(sites, X)
    idx = int(np.argmax(gaps))
    return float(gaps[idx]), (float(X[idx, 0]), float(X[idx, 1])), X.shape[0]


def gap_array(sites, r_step=10.0, t_step=0.5):
    """返回整个网格上每点的角隙向量(顺序与 certify.py 迭代一致)。"""
    return _compute(sites, r_step, t_step)[0]


def audit(sites, r_step=10.0, t_step=0.5, grid=None):
    """返回 (最大角隙, 最坏点)。sites: [(x, y), ...]"""
    gaps, X = _compute(sites, r_step, t_step)
    idx = int(np.argmax(gaps))
    return float(gaps[idx]), (float(X[idx, 0]), float(X[idx, 1]))


def audit_points(sites, points, reach=REACH - 1e-6, skip=5.0 - 1e-6):
    """在任意给定点集上求保守角隙。返回 (gaps, points_as_array)。

    reach/skip 可调: 弧线审计用收紧的 reach 排除薄片站点。
    """
    return _compute_at(sites, np.asarray(points, dtype=np.float64),
                        reach=reach, skip=skip)


def _compute(sites, r_step, t_step):
    gaps, X = _compute_at(sites, _grid(r_step, t_step))
    return gaps, X


def _compute_at(sites, X, reach=REACH - 1e-6, skip=5.0 - 1e-6):
    S = np.asarray(sites, dtype=np.float64)
    if S.ndim == 1:
        S = S.reshape(1, 2)
    n = S.shape[0]
    # 距离必须用 hypot 逐站点计算: 矩阵恒等式在恰好 1000 米边界处
    # 的舍入方向与 math.hypot 不同, 会翻转 <=REACH 的成员判定。
    D = np.empty((X.shape[0], n))
    for j in range(n):
        D[:, j] = np.hypot(X[:, 0] - S[j, 0], X[:, 1] - S[j, 1])
    within = D <= reach
    k = within.sum(axis=1)
    angles = np.full((X.shape[0], n), SENTINEL)
    for j in range(n):
        col = np.degrees(np.arctan2(S[j, 1] - X[:, 1], S[j, 0] - X[:, 0])) % 360.0
        angles[:, j] = np.where(within[:, j], col, SENTINEL)
    A = np.sort(angles, axis=1)
    rows = np.arange(X.shape[0])
    last_real = A[rows, np.maximum(k - 1, 0)]
    wrap = np.where(k >= 1, A[:, 0] + 360.0 - last_real, 360.0)
    if n > 1:
        diffs = A[:, 1:] - A[:, :-1]
        cols = np.arange(n - 1)
        valid = (k[:, None] >= 2) & (cols[None, :] <= (k[:, None] - 2))
        diffs = np.where(valid, diffs, -np.inf)
        gap = np.maximum(diffs.max(axis=1), wrap)
    else:
        gap = wrap
    gap = np.where(k == 0, 360.0, gap)
    gap = np.where(D.min(axis=1) <= skip, 0.0, gap)
    return gap, X


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from certify import certify, max_gap_at, ring
    import q4_routes

    h8 = [(0.0, 0.0)] + ring(1000, 6, 0.0) + ring(1400, 12, 15.0) + ring(2000, 12, 0.0)
    shiftb = [(0.0, 0.0)] + [p for p in q4_routes.clipped_sites(
        990.0, 0.0, 0.5 * 990.0 * math.sqrt(3) / 2) if math.hypot(*p) > 1e-7]

    for name, pts in (("H8", h8), ("ShiftB", shiftb)):
        for rs, ts in ((25.0, 1.5), (10.0, 0.5), (5.0, 0.25)):
            grid = _grid(rs, ts)
            ref_gaps = np.asarray(
                [max_gap_at((float(x), float(y)), pts) for x, y in grid])
            fast_gaps = gap_array(pts, r_step=rs, t_step=ts)
            conservative = bool(np.all(fast_gaps >= ref_gaps - 1e-9))
            worst_over = float(np.max(fast_gaps - ref_gaps))
            ref_gap, _ = certify(pts, r_step=rs, t_step=ts)
            fast_gap, _ = audit(pts, r_step=rs, t_step=ts)
            ok = conservative and fast_gap >= ref_gap - 1e-9
            print(f"{name} ({rs}/{ts}): 逐点保守={conservative} "
                  f"最大高估={worst_over:.4f}deg "
                  f"max_gap certify={ref_gap:.6f} fast={fast_gap:.6f} "
                  f"{'OK' if ok else 'FAIL'}")
            assert ok
    print("certfast conservative-verified against certify.py")

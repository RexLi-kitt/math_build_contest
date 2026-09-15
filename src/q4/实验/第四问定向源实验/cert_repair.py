"""证书贪心修补: 在证书最坏点处定向补站, 提升余量。

依据
----
`max_gap_at(x)` 只统计 reach(1000m) 内站点相对 x 的方向, 并取相邻方向的最大夹角。
**增加一个站点只会新增一个方向, 只会填补夹角, 不会让它变大。**
因此补站对证书是单调有利的: 全域最坏 gap 只会下降或不变, 代价仅 +66 s/case 与巡游增长。

策略
----
1) 全域细扫 + reach 边界环扫, 取 top-K 热点(含其 gap 值);
2) 在当前最坏点处求最大间隙方向;
3) 沿该方向、若干半径与角度偏移上生成候选补站点;
4) 用热点集上的新最坏值打分, 取最优; 重复直到余量达标或达到补站上限。

用法
----
python cert_repair.py \
    --design "C:\\Users\\李\\Desktop\\第四问路线压缩\\best_design.json" \
    --tag rand1800 --target-margin 6.5 --add-max 3 \
    --out "c:\\Users\\李\\.trae-cn\\work\\...\\repair"
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from certify import Area, Reach  # noqa: E402
from cert_local_refine import gap_at, scan_reach_boundary, refine_local  # noqa: E402
from strong_tsp import solve_tour, route_cost  # noqa: E402

SCAN_S_PER_SITE = 66.0


# ---------------------------------------------------------------- 工具

def to_xy(sites):
    return [p[0] for p in sites], [p[1] for p in sites]


def hot_points(sx, sy, step=3.0, topk=600):
    """全域笛卡尔扫描, 保留 gap 最大的 topk 个点。"""
    R = Area
    top = []
    ny = int(2 * R / step) + 1
    for iy in range(ny):
        y = -R + iy * step
        for ix in range(ny):
            x = -R + ix * step
            if x * x + y * y > R * R:
                continue
            g = gap_at(x, y, sx, sy)
            if len(top) < topk:
                heapq.heappush(top, (g, x, y))
            elif g > top[0][0]:
                heapq.heapreplace(top, (g, x, y))
    return top


def collect_hot(sites, step=3.0, topk=600):
    sx, sy = to_xy(sites)
    hot = list(hot_points(sx, sy, step=step, topk=topk))
    _, _, btop = scan_reach_boundary(sx, sy, n_angles=1440,
                                     deltas=(-0.2, 0.05, 0.5, 2.0), topk=250)
    hot += list(btop)
    hot.sort(reverse=True)
    return hot, sx, sy


def score(sites, hot):
    """候选设计在热点集上的最坏 gap(越小越好)。"""
    sx, sy = to_xy(sites)
    worst = 0.0
    for g, x, y in hot:
        v = gap_at(x, y, sx, sy)
        if v > worst:
            worst = v
    return worst


def gap_direction(x, y, sx, sy, reach=Reach):
    """返回 (最大夹角, 该夹角中点方向(度), 参与的方向列表)。"""
    dirs = []
    for i in range(len(sx)):
        dx, dy = sx[i] - x, sy[i] - y
        if dx * dx + dy * dy <= reach * reach:
            dirs.append(math.degrees(math.atan2(dy, dx)) % 360.0)
    if not dirs:
        return 360.0, 0.0, dirs
    dirs.sort()
    best_gap = dirs[0] + 360.0 - dirs[-1]
    best_mid = (dirs[-1] + best_gap / 2.0) % 360.0
    for a, b in zip(dirs, dirs[1:]):
        if b - a > best_gap:
            best_gap = b - a
            best_mid = (a + (b - a) / 2.0) % 360.0
    return best_gap, best_mid, dirs


def cost_of(sites):
    order, tour = solve_tour(list(sites), restarts=40)
    return order, tour, tour / 5.0 + SCAN_S_PER_SITE * len(sites)


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="证书贪心修补")
    ap.add_argument("--design", required=True)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--target-margin", type=float, default=6.5,
                    help="目标余量(180-gap), 达到即停")
    ap.add_argument("--add-max", type=int, default=3)
    ap.add_argument("--hot-step", type=float, default=3.0)
    ap.add_argument("--out", default="results/repair")
    args = ap.parse_args()

    raw = json.loads(Path(args.design).read_text(encoding="utf-8"))
    entries = raw if isinstance(raw, list) else [raw]
    target = None
    for e in entries:
        if not isinstance(e, dict) or "sites" not in e:
            continue
        nm = str(e.get("tag") or e.get("trial") or "")
        if args.tag and nm != args.tag:
            continue
        if not args.tag or nm == args.tag:
            target = e
            break
    if target is None:
        raise SystemExit(f"未找到 tag={args.tag} 的设计")

    sites = [(float(p[0]), float(p[1])) for p in target["sites"]]
    print(f"原始设计 {args.tag}: n={len(sites)}")

    order0, tour0, cost0 = cost_of(sites)
    hot, sx, sy = collect_hot(sites, step=args.hot_step)
    worst0 = hot[0][0]
    worst0_l, at0_l = refine_local(sx, sy, (hot[0][1], hot[0][2]), 20.0, 0.1)
    print(f"  初始热点最坏={worst0:.3f}  局部加密后={worst0_l:.3f} @{tuple(round(v,1) for v in at0_l)}")
    print(f"  初始 tour={tour0:.0f}m cost={cost0:.0f}  余量={180-worst0_l:.3f}\n")

    cur = list(sites)
    log = []
    for it in range(1, args.add_max + 1):
        hot, sx, sy = collect_hot(cur, step=args.hot_step)
        g, hx, hy = hot[0]
        # 以热点为中心做局部加密, 拿到更准的最坏点
        gl, (lx, ly) = refine_local(sx, sy, (hx, hy), 20.0, 0.1)
        cur_worst = gl
        margin = 180.0 - cur_worst
        print(f"-- 第{it}轮: 当前最坏={cur_worst:.3f} @{tuple(round(v,1) for v in (lx,ly))}  余量={margin:.3f}")
        if margin >= args.target_margin:
            print("   已达目标余量, 停止补站。")
            break

        gapv, mid, dirs = gap_direction(lx, ly, sx, sy)
        print(f"   热点处最大间隙={gapv:.2f}°  补站方向={mid:.1f}°  reach内方向数={len(dirs)}")

        cands = []
        for R in (300, 400, 500, 600, 700, 800, 900, 950):
            for off in (-20, -10, 0, 10, 20):
                th = math.radians(mid + off)
                p = (lx + R * math.cos(th), ly + R * math.sin(th))
                if any(math.dist(p, q) < 40.0 for q in cur):
                    continue
                cands.append(p)
        # 去重
        uniq = []
        for p in cands:
            if all(math.dist(p, q) > 1.0 for q in uniq):
                uniq.append(p)
        print(f"   候选补站点 {len(uniq)} 个", flush=True)

        best = None
        t0 = time.perf_counter()
        for p in uniq:
            trial = cur + [p]
            w = score(trial, hot)
            if best is None or w < best[0] - 1e-9:
                best = (w, p)
        print(f"   打分用时 {time.perf_counter()-t0:.0f}s  最优候选={tuple(round(v,1) for v in best[1])} "
              f"热点集新最坏={best[0]:.3f}", flush=True)
        cur = cur + [best[1]]
        _, tour1, cost1 = cost_of(cur)
        log.append({"iter": it, "added": [round(best[1][0], 2), round(best[1][1], 2)],
                    "hot_worst": round(best[0], 3), "tour": round(tour1, 1),
                    "cost": round(cost1, 1), "n": len(cur)})
        print(f"   补入后: n={len(cur)} tour={tour1:.0f} cost={cost1:.0f} "
              f"(+{cost1-cost0:.0f} vs 原始)\n", flush=True)

    order, tour, cost = cost_of(cur)
    hotf, sxf, syf = collect_hot(cur, step=args.hot_step)
    wf = hotf[0][0]
    glf, atf = refine_local(sxf, syf, (hotf[0][1], hotf[0][2]), 20.0, 0.1)
    print(f"最终: n={len(cur)} tour={tour:.0f} cost={cost:.0f}  "
          f"热点最坏={glf:.3f} @{tuple(round(v,1) for v in atf)}  余量={180-glf:.3f}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    design = {"tag": f"{args.tag}_patched", "sites": [[round(a, 4), round(b, 4)] for a, b in cur],
              "order": order, "tour": round(tour, 2), "cost": round(cost, 2), "n": len(cur)}
    (out / f"{args.tag}_patched.json").write_text(json.dumps(design, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
    (out / f"{args.tag}_repair_log.json").write_text(
        json.dumps({"original": {"n": len(sites), "tour": round(tour0, 2), "cost": round(cost0, 2),
                                 "worst_est": round(worst0_l, 3)},
                    "log": log,
                    "final": {"n": len(cur), "tour": round(tour, 2), "cost": round(cost, 2),
                              "worst_est": round(glf, 3), "margin_est": round(180 - glf, 3)}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved -> {(out).resolve()}")


if __name__ == "__main__":
    main()

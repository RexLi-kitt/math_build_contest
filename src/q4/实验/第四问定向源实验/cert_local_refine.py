"""最坏角间隙的"网格外"专项复核。

动机
----
`certify()` 只在极坐标格点上采样 max_gap_at, 返回的是**真实上确界的下界**:
采样点越多, 报告值只增不减。因此一个设计"细审 174.11 通过"并不能证明
真实最坏 gap <= 180。尤其 `max_gap_at` 在 |x-p| = reach(1000m) 处不连续
(站点跨过 1000m 就整条方向消失, max gap 向上跳变), 而均匀格点最容易漏掉跳变。

本脚本用四种更强的探测交叉验证同一个设计:
  1) 递增分辨率的极坐标 certify(复现现有口径, 并观察收敛趋势)
  2) 笛卡尔细网格全域扫描(消除极坐标在 r 大处的切向粗采样)
  3) reach=1000m 边界环扫描(专打不连续跳变处)
  4) 对上述最坏点做 0.1m 级局部超细加密

用法
----
python cert_local_refine.py \
    --design "C:\\Users\\李\\Desktop\\第四问路线压缩\\best_design.json" \
             "C:\\Users\\李\\Desktop\\第四问路线压缩\\search_results.json" \
    --step 2.0 --out "C:\\Users\\李\\Desktop\\Q4保底基线\\results\\cert_refine"
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from certify import Area, Reach, certify, max_gap_at  # noqa: E402


# ---------------------------------------------------------------- 内核

def gap_at(x, y, sx, sy, reach=Reach):
    """与 certify.max_gap_at 等价(含 5m 光学直清豁免), 避免构造 tuple 列表。"""
    best_d2 = None
    for i in range(len(sx)):
        dx = sx[i] - x
        dy = sy[i] - y
        d2 = dx * dx + dy * dy
        if best_d2 is None or d2 < best_d2:
            best_d2 = d2
    if best_d2 is not None and best_d2 <= 25.0:      # 5 m 内直接光学清除
        return 0.0
    reach2 = reach * reach
    dirs = []
    for i in range(len(sx)):
        dx = sx[i] - x
        dy = sy[i] - y
        if dx * dx + dy * dy <= reach2:
            dirs.append(math.degrees(math.atan2(dy, dx)) % 360.0)
    if not dirs:
        return 360.0
    dirs.sort()
    gap = dirs[0] + 360.0 - dirs[-1]
    prev = dirs[0]
    for a in dirs[1:]:
        d = a - prev
        if d > gap:
            gap = d
        prev = a
    return gap


def self_check(sites, trials=300):
    """随机点上核对 gap_at 与官方 certify.max_gap_at 一致。"""
    rng = random.Random(12345)
    bad = 0
    for _ in range(trials):
        r = rng.uniform(0, Area)
        t = rng.uniform(0, 2 * math.pi)
        x, y = r * math.cos(t), r * math.sin(t)
        a = gap_at(x, y, [p[0] for p in sites], [p[1] for p in sites])
        b = max_gap_at((x, y), sites)
        if abs(a - b) > 1e-9:
            bad += 1
    return bad


def scan_cartesian(sx, sy, step, reach=Reach, topk=8, verbose=False):
    R = Area
    worst, wx, top = 0.0, None, []
    t0 = time.perf_counter()
    ny = int(2 * R / step) + 1
    for iy in range(ny):
        y = -R + iy * step
        for ix in range(ny):
            x = -R + ix * step
            if x * x + y * y > R * R:
                continue
            g = gap_at(x, y, sx, sy, reach)
            if g > worst:
                worst, wx = g, (x, y)
            if len(top) < topk:
                heapq.heappush(top, (g, x, y))
            elif g > top[0][0]:
                heapq.heapreplace(top, (g, x, y))
        if verbose and iy % 200 == 0:
            print(f"    cartesian row {iy}/{ny} ({time.perf_counter() - t0:.0f}s)", flush=True)
    return worst, wx, top


def scan_reach_boundary(sx, sy, n_angles=7200,
                        deltas=(-2.0, -0.5, -0.1, -0.02, 0.02, 0.1, 0.5, 1.0, 2.0, 5.0),
                        reach=Reach, topk=6):
    """专打 |x-p|=reach 的不连续处: 站点刚出界, 该方向消失, max gap 跳变。"""
    R = Area
    worst, wx, top = 0.0, None, []
    for i in range(len(sx)):
        px, py = sx[i], sy[i]
        for d in deltas:
            rr = reach + d
            if rr <= 0:
                continue
            for k in range(n_angles):
                t = 2 * math.pi * k / n_angles
                x = px + rr * math.cos(t)
                y = py + rr * math.sin(t)
                if x * x + y * y > R * R:
                    continue
                g = gap_at(x, y, sx, sy, reach)
                if g > worst:
                    worst, wx = g, (x, y)
                if len(top) < topk:
                    heapq.heappush(top, (g, x, y))
                elif g > top[0][0]:
                    heapq.heapreplace(top, (g, x, y))
    return worst, wx, top


def refine_local(sx, sy, center, half, step, reach=Reach, radius=Area):
    """局部加密。**严格限制在可行域 r <= radius 内**(源只可能落在半径 Area 圆盘内)。"""
    worst, wx = 0.0, None
    cx, cy = center
    n = int(2 * half / step) + 1
    r2 = radius * radius
    for iy in range(n):
        y = cy - half + iy * step
        for ix in range(n):
            x = cx - half + ix * step
            if x * x + y * y > r2:
                continue
            g = gap_at(x, y, sx, sy, reach)
            if g > worst:
                worst, wx = g, (x, y)
    return worst, wx


# ---------------------------------------------------------------- 设计载入

def load_designs(paths, tags=None):
    out, seen = [], set()
    for f in paths:
        raw = json.loads(Path(f).read_text(encoding="utf-8"))
        entries = raw if isinstance(raw, list) else [raw]
        for idx, e in enumerate(entries):
            if not isinstance(e, dict) or "sites" not in e:
                continue
            if e.get("ship") is False:
                continue
            sites = [(float(p[0]), float(p[1])) for p in e["sites"]]
            name = str(e.get("tag") or e.get("trial") or f"entry{idx}")
            if tags and name not in tags:
                continue
            sig = (name, len(sites)) + tuple(sorted((round(a, 3), round(b, 3)) for a, b in sites))
            if sig in seen:
                continue
            seen.add(sig)
            out.append({
                "name": name, "n": len(sites), "sites": sites,
                "claimed_fine": e.get("gap_fine") or e.get("gap_fine_10_0.5"),
                "claimed_ultra": e.get("gap_ultra") or e.get("gap_ultra_5_0.25"),
                "source_file": str(f),
            })
    return out


# ---------------------------------------------------------------- 主流程

def audit_one(d, step, half, fine_step):
    sites = d["sites"]
    sx = [p[0] for p in sites]
    sy = [p[1] for p in sites]
    res = {"name": d["name"], "n": d["n"],
           "claimed_fine": d["claimed_fine"], "claimed_ultra": d["claimed_ultra"]}

    # 1) 复现现有口径 + 收敛趋势
    polar = {}
    for rs, ts in ((10.0, 0.5), (5.0, 0.25), (2.0, 0.1)):
        g, _ = certify(sites, r_step=rs, t_step=ts)
        polar[f"{rs}/{ts}"] = round(g, 3)
    res["polar"] = polar

    # 2) 笛卡尔细网格
    t0 = time.perf_counter()
    wc, wxc, topc = scan_cartesian(sx, sy, step)
    res["cartesian"] = {"step": step, "worst": round(wc, 3),
                        "at": [round(wxc[0], 2), round(wxc[1], 2)] if wxc else None,
                        "seconds": round(time.perf_counter() - t0, 1)}

    # 3) reach 边界环扫描
    t1 = time.perf_counter()
    wb, wxb, topb = scan_reach_boundary(sx, sy)
    res["reach_boundary"] = {"worst": round(wb, 3),
                             "at": [round(wxb[0], 2), round(wxb[1], 2)] if wxb else None,
                             "seconds": round(time.perf_counter() - t1, 1)}

    # 4) 迭代式局部超细加密(严格限制可行域, 只对域内候选点加密)
    seeds = []
    for g, x, y in list(topc) + list(topb):
        if x * x + y * y <= Area * Area:
            seeds.append((g, x, y))
    if wxc and wxc[0] ** 2 + wxc[1] ** 2 <= Area * Area:
        seeds.append((wc, wxc[0], wxc[1]))
    if wxb and wxb[0] ** 2 + wxb[1] ** 2 <= Area * Area:
        seeds.append((wb, wxb[0], wxb[1]))
    seeds.sort(reverse=True)
    local_best, local_at = 0.0, None
    t2 = time.perf_counter()
    centers = [(x, y) for g, x, y in seeds[:8]]
    for (h, st) in ((half, fine_step), (5.0, fine_step / 5.0)):
        for cx, cy in centers:
            lg, lat = refine_local(sx, sy, (cx, cy), h, st)
            if lg > local_best:
                local_best, local_at = lg, lat
        if local_at:
            centers = [local_at] + centers[:3]
    res["local_refine"] = {"half_m": [half, 5.0], "step_m": [fine_step, fine_step / 5.0],
                           "worst": round(local_best, 3),
                           "at": [round(local_at[0], 3), round(local_at[1], 3)] if local_at else None,
                           "seconds": round(time.perf_counter() - t2, 1)}

    overall = max(wc, wb, local_best, polar["2.0/0.1"])
    res["overall_worst_gap"] = round(overall, 3)
    res["margin_to_180"] = round(180.0 - overall, 3)
    res["verdict"] = "PASS" if overall <= 180.0 else "FAIL"
    res["verdict_1deg"] = "PASS" if overall <= 179.0 else "TIGHT/FAIL"
    return res


def main():
    ap = argparse.ArgumentParser(description="最坏角间隙网格外复核")
    ap.add_argument("--design", nargs="+", required=True)
    ap.add_argument("--tag", default=None, help="逗号分隔, 仅这些名字")
    ap.add_argument("--step", type=float, default=2.0, help="笛卡尔全域格步(m)")
    ap.add_argument("--half", type=float, default=20.0, help="局部加密半宽(m)")
    ap.add_argument("--fine-step", type=float, default=0.1, help="局部加密步长(m)")
    ap.add_argument("--out", default="results/cert_refine")
    args = ap.parse_args()

    tags = [t.strip() for t in args.tag.split(",")] if args.tag else None
    designs = load_designs(args.design, tags)
    if not designs:
        raise SystemExit("无可用设计(ship=True 且含 sites)")
    print(f"载入 {len(designs)} 个设计: "
          f"{[(d['name'], d['n']) for d in designs]}\n")

    bad = self_check(designs[0]["sites"])
    print(f"内核自检 (gap_at vs certify.max_gap_at): 不一致 {bad} 例\n")

    results = []
    for d in designs:
        print(f"== {d['name']} (n={d['n']}) ==", flush=True)
        r = audit_one(d, args.step, args.half, args.fine_step)
        results.append(r)
        print(f"   极坐标收敛 : {r['polar']}")
        print(f"   笛卡尔{args.step}m  : {r['cartesian']['worst']}  @{r['cartesian']['at']} "
              f"({r['cartesian']['seconds']}s)")
        print(f"   reach边界环 : {r['reach_boundary']['worst']}  @{r['reach_boundary']['at']}")
        print(f"   局部加密    : {r['local_refine']['worst']}  @{r['local_refine']['at']} "
              f"({r['local_refine']['seconds']}s)")
        print(f"   >>> 真实最坏 gap 下界 = {r['overall_worst_gap']}  "
              f"余量 {r['margin_to_180']}  [{r['verdict']}]\n", flush=True)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "cert_refine.json").write_text(
        json.dumps({"config": vars(args), "results": results},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    print("汇总(真实最坏 gap 下界 / 余量):")
    for r in sorted(results, key=lambda z: -z["overall_worst_gap"]):
        print(f"   {r['name']:>10} n={r['n']:>3}  声称ultra={r['claimed_ultra']}  "
              f"实测>={r['overall_worst_gap']:>7.3f}  余量={r['margin_to_180']:>7.3f}  {r['verdict']}")
    print(f"\nsaved -> {out.resolve()}")


if __name__ == "__main__":
    main()

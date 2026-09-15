"""认证路线搜索 v2: 缓存/续跑/双账本 + 管道云出货门槛。

成本模型: cost = 巡游/5 + 66*站数 (s/case)。
Stage A 随机环形结构 -> stage_a.json 缓存。
Stage B 自由形态局部搜索 -> 每任务完成即写 stage_b_results.jsonl, 可续跑;
        每个轨迹同时维护 best_any(gap<=174) 与 best_safe(gap<=168)。
Stage C 决赛: solve_tour(restarts=200)+热路径取优; 审计 (5/0.25) 网格 + 管道云
        (真实语义); 出货要求两者 <= 175。全部落盘 finalists.json。

用法: python search_cert_route.py --trials 5000 --iters 340 --variants 2 --jobs 8
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

EXP = r"C:\Users\李\Desktop\第四问定向源实验"
sys.path.insert(0, EXP)
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from certify import certify, ring  # noqa: E402
from strong_tsp import solve_tour, two_opt, or_opt, route_cost  # noqa: E402
from certfast import audit as faudit, tube_audit  # noqa: E402
import q4_routes  # noqa: E402

SCAN_S_PER_SITE = 66.0
SCREEN_STEP = (20.0, 1.0)
FINE_STEP = (10.0, 0.5)
SCREEN_TH = 176.0
FINE_TH = 174.0
SAFE_TH = 168.0
SHIP_TH = 175.0
ORIGIN = (0.0, 0.0)
STAGE_A_PATH = HERE / "stage_a.json"
STAGE_B_PATH = HERE / "stage_b_results.jsonl"


def sites_cost(sites, tour):
    return tour / 5.0 + SCAN_S_PER_SITE * len(sites)


def fine_gap(sites):
    return faudit(sites, *FINE_STEP)[0]


def screen_gap(sites):
    return faudit(sites, *SCREEN_STEP)[0]


def tour_of(sites, restarts=20):
    order, cost = solve_tour(list(sites), restarts=restarts)
    return order, cost


def refine_order(order, sites):
    best = list(order)
    best_cost = route_cost(best, sites)
    for _ in range(8):
        cand = two_opt(best, sites)
        cand = or_opt(cand, sites)
        cand_cost = route_cost(cand, sites)
        if cand_cost < best_cost - 1e-9:
            best, best_cost = cand, cand_cost
        else:
            break
    return best, best_cost


def spec_sites(spec, with_origin):
    sites = [ORIGIN] if with_origin else []
    for r, k, off in spec:
        sites.extend(ring(r, k, off))
    return sites


def evaluate(sites, tag, restarts=20):
    if screen_gap(sites) > SCREEN_TH:
        return None
    g = fine_gap(sites)
    if g > FINE_TH:
        return None
    order, tour = tour_of(sites, restarts)
    return {
        "cost": sites_cost(sites, tour), "tour": tour, "n": len(sites),
        "gap": g, "sites": [tuple(p) for p in sites],
        "order": list(order), "tag": tag,
    }


def random_spec(rng):
    m = rng.choices((2, 3, 4), weights=(2, 5, 2))[0]
    table = {
        2: ((400, 1150, 3, 9), (1250, 2400, 8, 16)),
        3: ((400, 1160, 3, 9), (1180, 1620, 8, 14), (1680, 2160, 8, 14)),
        4: ((400, 1160, 3, 8), (1180, 1600, 8, 13),
            (1650, 2150, 8, 13), (2050, 2600, 6, 12)),
    }[m]
    spec, prev = [], 150.0
    for rlo, rhi, klo, khi in table:
        k = rng.randint(klo, khi)
        lo = max(prev + 260.0, float(rlo))
        if lo > rhi:
            return None
        r = rng.uniform(lo, rhi)
        spec.append((r, k, rng.uniform(0.0, 360.0 / k)))
        prev = r
    return spec


def known_seeds():
    h8 = spec_sites(((1000, 6, 0), (1400, 12, 15), (2000, 12, 0)), True)
    h7 = spec_sites(((1000, 6, 0), (1300, 6, 30), (1600, 6, 0),
                     (1900, 6, 30), (2200, 6, 0)), True)
    shiftb = [ORIGIN] + [p for p in q4_routes.clipped_sites(
        990.0, 0.0, 0.5 * 990.0 * math.sqrt(3) / 2) if math.hypot(*p) > 1e-7]
    return ((h8, "H8"), (h7, "H7"), (shiftb, "ShiftB"))


def stage_a(trials, rng_seed):
    if STAGE_A_PATH.exists():
        data = json.loads(STAGE_A_PATH.read_text(encoding="utf-8"))
        print(f"Stage A loaded from cache: {len(data)} candidates", flush=True)
        return data
    rng = random.Random(rng_seed)
    seeds = []
    for sites, tag in known_seeds():
        cand = evaluate(sites, tag)
        if cand:
            seeds.append(cand)
    t0 = time.perf_counter()
    found = 0
    for trial in range(trials):
        spec = random_spec(rng)
        if spec is None:
            continue
        cand = evaluate(spec_sites(spec, rng.random() < 0.75), f"rand{trial}")
        if cand:
            found += 1
            seeds.append(cand)
            if found % 25 == 0:
                print(f"  A trial={trial} pass#{found}: cost={cand['cost']:.0f} "
                      f"n={cand['n']} gap={cand['gap']:.2f}", flush=True)
    seeds.sort(key=lambda d: d["cost"])
    STAGE_A_PATH.write_text(json.dumps(seeds), encoding="utf-8")
    print(f"Stage A done: {found}/{trials} passed, "
          f"{time.perf_counter() - t0:.0f}s, top cost={seeds[0]['cost']:.0f}",
          flush=True)
    return seeds


def local_search(task):
    seed_dict, iters, rng_seed = task
    rng = random.Random(rng_seed)
    sites = [tuple(p) for p in seed_dict["sites"]]
    order = list(seed_dict["order"])
    order_cost = route_cost(order, sites)
    best_any = {"cost": sites_cost(sites, order_cost), "tour": order_cost,
                "n": len(sites), "gap": seed_dict["gap"],
                "sites": list(sites), "order": list(order),
                "tag": seed_dict["tag"]}
    best_safe = dict(best_any) if best_any["gap"] <= SAFE_TH else None

    def try_accept(new_sites, new_order):
        nonlocal sites, order, order_cost, best_any, best_safe
        # 成本优先过滤: 巡游重排约 20ms, 证书审计约 300ms; 成本不可能
        # 改善(既不破轨迹最优也不破全局最优)时直接跳过审计。
        new_order, new_cost = refine_order(new_order, new_sites)
        new_total = sites_cost(new_sites, new_cost)
        cur_cost = sites_cost(sites, order_cost)
        if (new_total >= best_any["cost"] - 1e-9
                and new_total >= cur_cost - 1e-9):
            return False
        g = fine_gap(new_sites)
        if g > FINE_TH:
            return False
        if new_total < best_any["cost"] - 1e-9:
            best_any = {"cost": new_total, "tour": new_cost, "n": len(new_sites),
                        "gap": g, "sites": [tuple(p) for p in new_sites],
                        "order": list(new_order), "tag": seed_dict["tag"]}
        if g <= SAFE_TH and (best_safe is None
                             or new_total < best_safe["cost"] - 1e-9):
            best_safe = {"cost": new_total, "tour": new_cost, "n": len(new_sites),
                         "gap": g, "sites": [tuple(p) for p in new_sites],
                         "order": list(new_order), "tag": seed_dict["tag"]}
        if new_total < cur_cost - 1e-9:
            sites, order = [tuple(p) for p in new_sites], new_order
            order_cost = new_cost
            return True
        return False

    def remove_idx(idx):
        if idx >= len(sites):
            return
        new = sites[:idx] + sites[idx + 1:]
        pos = order.index(idx)
        new_order = [i if i < idx else i - 1
                     for i in (order[:pos] + order[pos + 1:])]
        try_accept(new, new_order)

    for it in range(iters):
        n = len(sites)
        move = rng.random()
        if move < 0.22 and n > 18:
            remove_idx(rng.randrange(n))
        elif move < 0.62:
            i = rng.randrange(n)
            d = rng.uniform(30.0, 450.0)
            a = rng.uniform(0.0, 2.0 * math.pi)
            new = sites[:i] + [(sites[i][0] + d * math.cos(a),
                                sites[i][1] + d * math.sin(a))] + sites[i + 1:]
            try_accept(new, list(order))
        elif move < 0.82:
            i = rng.randrange(n)
            pos = order.index(i)
            a = sites[order[pos - 1]] if pos > 0 else ORIGIN
            b = sites[order[pos + 1]] if pos + 1 < n else sites[order[pos - 1]]
            ax, ay = a
            bx, by = b
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((sites[i][0] - ax) * dx + (sites[i][1] - ay) * dy)
                                  / max(dx * dx + dy * dy, 1e-9)))
            jx, jy = rng.uniform(-40, 40), rng.uniform(-40, 40)
            new = sites[:i] + [(ax + t * dx + jx, ay + t * dy + jy)] + sites[i + 1:]
            try_accept(new, list(order))
        else:
            i = rng.randrange(n)
            d = rng.uniform(5.0, 80.0)
            a = rng.uniform(0.0, 2.0 * math.pi)
            new = sites[:i] + [(sites[i][0] + d * math.cos(a),
                                sites[i][1] + d * math.sin(a))] + sites[i + 1:]
            try_accept(new, list(order))
        if (it + 1) % 45 == 0:
            for idx in rng.sample(range(len(sites)), len(sites)):
                if len(sites) > 18:
                    remove_idx(idx)
        if (it + 1) % 70 == 0:
            cold_order, cold_cost = tour_of(sites, restarts=12)
            if cold_cost < route_cost(order, sites) - 1e-9:
                order, order_cost = cold_order, cold_cost
    return {"task": f"{seed_dict['tag']}_v{rng_seed}", "any": best_any,
            "safe": best_safe}


def load_done_tasks():
    done = {}
    if STAGE_B_PATH.exists():
        for line in STAGE_B_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            done[item["task"]] = item
    return done


def stage_b(seeds, iters, variants, jobs):
    top = sorted(seeds, key=lambda d: d["cost"])[:9]
    known = {d["tag"] for d in top}
    for seed in seeds:
        if seed["tag"] in ("H8", "H7", "ShiftB") and seed["tag"] not in known:
            top.append(seed)
    done = load_done_tasks()
    tasks = [((seed, iters, rng_seed), f"{seed['tag']}_v{rng_seed}")
             for seed in top for rng_seed in range(variants)]
    todo = [t for t, key in tasks if key not in done]
    print(f"Stage B: {len(tasks)} tasks, {len(tasks) - len(todo)} cached, "
          f"{len(todo)} to run, jobs={jobs}", flush=True)
    if todo:
        t0 = time.perf_counter()
        with ProcessPoolExecutor(max_workers=jobs) as pool, \
                open(STAGE_B_PATH, "a", encoding="utf-8") as log:
            for i, res in enumerate(pool.map(local_search, todo), 1):
                log.write(json.dumps(res) + "\n")
                log.flush()
                done[res["task"]] = res
                print(f"  B {i:03d}/{len(todo)} {res['task']}: "
                      f"any(cost={res['any']['cost']:.0f} n={res['any']['n']} "
                      f"gap={res['any']['gap']:.2f}) "
                      f"safe={'yes' if res['safe'] else 'no'} "
                      f"({time.perf_counter() - t0:.0f}s)", flush=True)
    return list(done.values())


def dedupe(cands):
    seen, out = set(), []
    for c in sorted(cands, key=lambda d: d["cost"]):
        key = tuple(sorted((round(x, 1), round(y, 1)) for x, y in c["sites"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def finalize(cand):
    sites = [tuple(p) for p in cand["sites"]]
    order, tour = tour_of(sites, restarts=200)
    warm_order, warm_tour = refine_order(cand["order"], sites)
    if warm_tour < tour - 1e-9:
        order, tour = warm_order, warm_tour
    g_grid, _ = faudit(sites, 5.0, 0.25)
    g_tube, wx, _ = tube_audit(sites)
    return {"cost": sites_cost(sites, tour), "tour": tour, "n": len(sites),
            "gap_10_05": cand["gap"], "gap_grid_5_025": g_grid,
            "gap_tube": g_tube, "worst_x": list(wx), "sites": sites,
            "order": list(order), "tag": cand["tag"],
            "ship": g_grid <= SHIP_TH and g_tube <= SHIP_TH}


def stage_c(results, n_any=8, n_safe=4):
    any_list = dedupe([r["any"] for r in results if r])
    safe_list = dedupe([r["safe"] for r in results if r and r["safe"]])
    finalists = dedupe(any_list[:n_any] + safe_list[:n_safe])
    print(f"\nStage C: {len(finalists)} finalists", flush=True)
    out = []
    for cand in finalists:
        fin = finalize(cand)
        out.append(fin)
        print(f"  C {cand['tag']}: n={fin['n']} tour={fin['tour']:.0f} "
              f"cost={fin['cost']:.0f} gap(10/0.5)={fin['gap_10_05']:.2f} "
              f"grid(5/.25)={fin['gap_grid_5_025']:.2f} "
              f"tube={fin['gap_tube']:.2f} "
              f"{'SHIP' if fin['ship'] else 'reject'}", flush=True)
    (HERE / "finalists.json").write_text(json.dumps(out, indent=2),
                                         encoding="utf-8")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=5000)
    parser.add_argument("--iters", type=int, default=340)
    parser.add_argument("--variants", type=int, default=2)
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args()

    seeds = stage_a(args.trials, 20260924)
    results = stage_b(seeds, args.iters, args.variants, args.jobs)
    finalists = stage_c(results)

    shipped = [d for d in finalists if d["ship"]]
    shipped.sort(key=lambda d: (d["cost"], d["gap_tube"]))
    best = shipped[0] if shipped else None
    if best is None and finalists:
        best = min(finalists, key=lambda d: d["gap_tube"])
        print("WARNING: no design within ship threshold; best by tube", flush=True)
    if best:
        (HERE / "best_design.json").write_text(json.dumps({
            "sites": [list(p) for p in best["sites"]],
            "order": best["order"],
            "tour_m": best["tour"], "scan_cost_s": best["cost"],
            "n_sites": best["n"], "gap_10_05": best["gap_10_05"],
            "gap_grid_5_025": best["gap_grid_5_025"],
            "gap_tube": best["gap_tube"], "worst_x": best["worst_x"],
            "tag": best["tag"], "ship": best["ship"],
        }, indent=2), encoding="utf-8")
        print(f"\nBEST: n={best['n']} tour={best['tour']:.0f}m "
              f"cost={best['cost']:.0f}s gap_tube={best['gap_tube']:.2f} "
              f"ship={best['ship']} -> best_design.json", flush=True)


if __name__ == "__main__":
    main()

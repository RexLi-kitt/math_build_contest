"""Profile H8: where do post-search measures go? (direction / no_signal / near)"""
from __future__ import annotations

import random
import statistics
import sys

sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")

from q4_experiment import DirectionalSimulator, clone_sources, random_mixed_sources
from fast_q4 import H8Agent


def main():
    cases = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 20260916
    rng = random.Random(seed)
    rows = []
    for index in range(1, cases + 1):
        sources = random_mixed_sources(rng, None, 0.5)
        sim = DirectionalSimulator(clone_sources(sources), seed * 100000 + index)
        agent = H8Agent(sim)
        agent.run()
        search_end = getattr(agent, "search_end_time_s", float("inf"))
        post = {"direction": 0, "no_signal": 0, "near": 0}
        search = {"direction": 0, "no_signal": 0, "near": 0}
        for a in sim.actions:
            if a.kind != "measure":
                continue
            bucket = post if a.virtual_time_s > search_end + 1e-6 else search
            bucket[a.result] += 1
        rows.append({"post": post, "search": search})
    post_dir = sum(r["post"]["direction"] for r in rows)
    post_ns = sum(r["post"]["no_signal"] for r in rows)
    post_near = sum(r["post"]["near"] for r in rows)
    search_dir = sum(r["search"]["direction"] for r in rows)
    search_ns = sum(r["search"]["no_signal"] for r in rows)
    print(f"H8 {cases} cases seed {seed}")
    print(f"search measures: direction={search_dir} no_signal={search_ns} "
          f"({search_ns / max(1, search_dir + search_ns):.1%} wasted)")
    print(f"post   measures: direction={post_dir} no_signal={post_ns} near={post_near} "
          f"({post_ns / max(1, post_dir + post_ns):.1%} wasted)")
    print(f"post wasted wall: {post_ns * 6 / cases:.1f} s/case")


if __name__ == "__main__":
    main()

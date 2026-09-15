"""迭代 2 筛选: 100 局 seed 20260928, Base / ActionNode / StickyAction / StickyOnly。"""
import sys
import time
from pathlib import Path

EXP = r"C:\Users\李\Desktop\第四问定向源实验"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, EXP)
sys.path.insert(0, str(HERE))

import q4_optimize  # noqa: E402
from cert_route_agent import CertRouteAgent  # noqa: E402
from cert_iter2_agents import (ActionNodeAgent, StickyActionAgent,  # noqa: E402
                               StickyOnlyAgent)

q4_optimize.STRATEGIES.update({
    "Base": CertRouteAgent,
    "ActionNode": ActionNodeAgent,
    "StickyAction": StickyActionAgent,
    "StickyOnly": StickyOnlyAgent,
})

if __name__ == "__main__":
    if "--time" in sys.argv:
        import random
        from q4_experiment import random_mixed_sources
        from q4_optimize import run_case
        rng = random.Random(20260928)
        cases = [random_mixed_sources(rng, None, 0.5) for _ in range(5)]
        for name, cls in (("Base", CertRouteAgent), ("ActionNode", ActionNodeAgent),
                          ("StickyAction", StickyActionAgent)):
            t0 = time.perf_counter()
            rows = [run_case(i, s, 20260928, name, cls)
                    for i, s in enumerate(cases, 1)]
            per = sum(r["total_virtual_time_s"] for r in rows) / sum(r["source_count"] for r in rows)
            print(f"{name}: {per:.1f} s/源, wall {time.perf_counter() - t0:.2f}s")
        sys.exit(0)
    sys.argv = [
        "screen",
        "--cases", "100",
        "--seed", "20260928",
        "--strategies", "Base,ActionNode,StickyAction,StickyOnly",
        "--min-success", "1.0",
        "--jobs", "16",
        "--output", str(HERE / "results" / "iter2_screen100"),
    ]
    q4_optimize.main()

"""诊断: 搜索后移动由测量行程还是清除行程主导。"""
import random
import sys
from collections import defaultdict
from pathlib import Path

EXP = r"C:\Users\李\Desktop\第四问定向源实验"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, EXP)
sys.path.insert(0, str(HERE))

from baseline_core import dist  # noqa: E402
from q4_experiment import DirectionalSimulator, clone_sources, random_mixed_sources  # noqa: E402
from cert_route_agent import CertRouteAgent  # noqa: E402
from cert_insert_agent import Insert500Agent  # noqa: E402

rng = random.Random(20260928)
cases = [random_mixed_sources(rng, None, 0.5) for _ in range(12)]

for cls in (CertRouteAgent, Insert500Agent):
    agg = defaultdict(float)
    cnt = defaultdict(int)
    insertions = 0
    for i, sources in enumerate(cases, 1):
        sim = DirectionalSimulator(clone_sources(sources), 20260928 * 100000 + i)
        agent = cls(sim)
        agent.run()
        insertions += getattr(agent, "coverage_insertions", 0)
        end = getattr(agent, "search_end_time_s", 0.0)
        prev = (0.0, 0.0)
        for a in sim.actions:
            if a.position is not None:
                mv = dist(prev, a.position) / 5.0
                prev = a.position
                if a.virtual_time_s > end + 1e-6 and a.kind in ("measure", "clear"):
                    agg[a.kind + "_mv"] += mv
                    cnt[a.kind] += 1
    n = len(cases)
    print(f"{cls.__name__}: insertions={insertions}")
    print(f"  搜索后测量行程: {agg['measure_mv']/n:6.1f} s/局 ({cnt['measure']/n:.1f} 次/局)")
    print(f"  搜索后清除行程: {agg['clear_mv']/n:6.1f} s/局 ({cnt['clear']/n:.1f} 次/局)")
    print(f"  合计: {(agg['measure_mv']+agg['clear_mv'])/n:6.1f} s/局")

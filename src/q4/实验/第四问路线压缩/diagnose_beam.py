"""诊断 3: Beam 选点是否真的减少了 no_signal 白跑 (Base vs Beam, 30 局)。"""
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
from cert_beam_agents import CertBeamAgent  # noqa: E402

rng = random.Random(20260928)
cases = [random_mixed_sources(rng, None, 0.5) for _ in range(30)]

for cls in (CertRouteAgent, CertBeamAgent):
    agg = defaultdict(float)
    cnt = defaultdict(int)
    for i, sources in enumerate(cases, 1):
        sim = DirectionalSimulator(clone_sources(sources), 20260928 * 100000 + i)
        agent = cls(sim)
        agent.run()
        end = getattr(agent, "search_end_time_s", 0.0)
        prev = (0.0, 0.0)
        for a in sim.actions:
            if a.position is not None:
                mv = dist(prev, a.position) / 5.0
                prev = a.position
                if a.virtual_time_s > end + 1e-6 and a.kind == "measure":
                    agg[a.result] += mv
                    cnt[a.result] += 1
    total_src = sum(len(c) for c in cases)
    print(f"{cls.__name__}:")
    print(f"  direction: {agg['direction']/total_src:6.1f} s/源 ({cnt['direction']/total_src:.2f} 次)")
    print(f"  no_signal: {agg['no_signal']/total_src:6.1f} s/源 ({cnt['no_signal']/total_src:.2f} 次)")
    tot = (agg['direction'] + agg['no_signal'] + agg['near'])
    print(f"  测量行程合计: {tot/total_src:.1f} s/源")

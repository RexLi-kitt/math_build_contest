"""诊断 2: 搜索后测量行程的有效性构成 (direction / no_signal / near)。

若大量专程测量返回 no_signal(跑到定向源背面), 则 beam-aware 选点仍有
余量; 若几乎全是有效方位, 则搜索后移动已无无效功可挤。
"""
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

rng = random.Random(20260928)
cases = [random_mixed_sources(rng, None, 0.5) for _ in range(30)]

agg = defaultdict(float)
cnt = defaultdict(int)
for i, sources in enumerate(cases, 1):
    sim = DirectionalSimulator(clone_sources(sources), 20260928 * 100000 + i)
    agent = CertRouteAgent(sim)
    agent.run()
    end = getattr(agent, "search_end_time_s", 0.0)
    prev = (0.0, 0.0)
    for a in sim.actions:
        if a.position is not None:
            mv = dist(prev, a.position) / 5.0
            prev = a.position
            if a.virtual_time_s > end + 1e-6:
                if a.kind == "measure":
                    agg["mv_" + a.result] += mv
                    cnt[a.result] += 1
                elif a.kind == "clear":
                    agg["mv_clear"] += mv
                    cnt["clear"] += 1

n = len(cases)
total_src = sum(len(c) for c in cases)
print(f"30 局, {total_src} 源, 每源平均:")
print(f"  测量-有效方位 direction: {agg['mv_direction']/total_src:6.1f} s/源 "
      f"({cnt['direction']/total_src:.2f} 次/源)")
print(f"  测量-背面无信号 no_signal: {agg['mv_no_signal']/total_src:6.1f} s/源 "
      f"({cnt['no_signal']/total_src:.2f} 次/源)")
print(f"  测量-near: {agg['mv_near']/total_src:6.1f} s/源 ({cnt['near']/total_src:.2f} 次/源)")
print(f"  清除行程: {agg['mv_clear']/total_src:6.1f} s/源 ({cnt['clear']/total_src:.2f} 次/源)")
tot = sum(agg.values())
print(f"  合计: {tot/total_src:.1f} s/源")
waste = agg['mv_no_signal'] / total_src
print(f"  其中背面白跑: {waste:.1f} s/源 ({waste/(tot/total_src)*100:.1f}%)")

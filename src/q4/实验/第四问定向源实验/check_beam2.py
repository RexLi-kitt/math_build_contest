"""Count _raw_metrics outcomes for H8 (CPlus scorer) vs H8Beam."""
from __future__ import annotations

import random
import sys

sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")

from fast_q4 import BeamAwareMixin, H8Agent, H8BeamAgent
from q4_experiment import DirectionalSimulator, clone_sources, random_mixed_sources
from strategies import CPlusAgent

stats = {"calls": 0, "none": 0, "ok": 0}


def wrap(cls):
    orig = cls._raw_metrics

    def wrapped(self, st, snapshot, candidate):
        stats["calls"] += 1
        result = orig(self, st, snapshot, candidate)
        if result is None:
            stats["none"] += 1
        else:
            stats["ok"] += 1
        return result

    cls._raw_metrics = wrapped


def run(name, agent_cls):
    for key in stats:
        stats[key] = 0
    rng = random.Random(20260916)
    for index in range(1, 11):
        sources = random_mixed_sources(rng, None, 0.5)
        sim = DirectionalSimulator(clone_sources(sources), 20260916 * 100000 + index)
        agent_cls(sim).run()
    print(f"{name:>8}: calls={stats['calls']} none={stats['none']} ok={stats['ok']}")


wrap(CPlusAgent)
wrap(BeamAwareMixin)
run("H8", H8Agent)
run("H8Beam", H8BeamAgent)

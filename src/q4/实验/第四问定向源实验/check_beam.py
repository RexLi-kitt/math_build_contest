"""Check that the beam-aware scorer actually gets exercised."""
from __future__ import annotations

import random
import sys

sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")

from fast_q4 import BeamAwareMixin, H8BeamAgent, H8Agent
from q4_experiment import DirectionalSimulator, clone_sources, random_mixed_sources

print("mixin wins:", H8BeamAgent._raw_metrics is BeamAwareMixin._raw_metrics)

calls = [0]
nones = [0]
orig = BeamAwareMixin._raw_metrics


def wrapped(self, st, snapshot, candidate):
    calls[0] += 1
    result = orig(self, st, snapshot, candidate)
    if result is None:
        nones[0] += 1
    return result


BeamAwareMixin._raw_metrics = wrapped

rng = random.Random(20260916)
sources = random_mixed_sources(rng, None, 0.5)
sim = DirectionalSimulator(clone_sources(sources), 20260916 * 100000 + 1)
agent = H8BeamAgent(sim)
agent.run()
print("calls:", calls[0], "none:", nones[0], "clear:", agent.summary())

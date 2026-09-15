"""Model J: model I with a compact 7-stop coverage ring at R = 1000 m.

Only the discovery/coverage-layer geometry changes relative to I.  The second
question's four-metric selector (coarse polar grid -> top-two refinement ->
re-scoring on the refined pool, r_pred = mean), the 19.75 m conservative
clearing rule, co-observation and the per-action rolling scheduler are all
inherited unchanged.

Coverage guarantee.  With the origin stop plus k evenly spaced ring stops at
radius R, the worst point of the task disk lies on the boundary half-way
between two adjacent ring stops:

    d_k(R) = sqrt(1800^2 + R^2 - 2 * 1800 * R * cos(180 deg / k))

Detection only needs d_k(R) <= 1000 (every receive radius is >= 1000 m), so

    R_min(k) = 1800 cos(pi/k) - sqrt(3240000 cos^2(pi/k) - 2240000)

    k = 6: R_min = 1122.9 m, worst coverage 1000.0 m, sweep length 6R = 6737 m
    k = 7: R_min =  997.2 m, worst coverage 1000.0 m, sweep length 6190 m
    k = 8: R_min =  938.1 m, worst coverage 1000.0 m, sweep length 5964 m

J uses R = 1000 m (worst point 998.25 m, i.e. 1.75 m margin; centre covered by
the origin scan and by R <= 1000).  The open sweep is origin -> first ring stop
plus (k-1) chords, P(k, R) = R * (1 + 2(k-1) sin(pi/k)).

Why k = 7.  Each extra stop costs one full scan of the still-undiscovered
channels (measured ~60 s per episode).  Moving k = 6 -> 7 saves 106 s of
movement and pays ~61 s of scanning (net +45 s); k = 7 -> 8 saves only 49 s and
still pays ~60 s (net negative, confirmed by the 8-stop ablation).  The joint
(k, R) optimum of this trade-off is k = 7 at R ~= 1000.
"""
from __future__ import annotations

from baseline_core import add
from strategies import RingOptimizedAgent

RING_R = 1000.0
RING_K = 7


class JAgent(RingOptimizedAgent):
    search_ring_r = RING_R
    ring_count = RING_K

    def __init__(self, sim, verbose: bool = False):
        super().__init__(sim, verbose)
        step = 360.0 / self.ring_count
        self.search_points = [(0.0, 0.0)] + [
            add((0.0, 0.0), self.search_ring_r, step * k)
            for k in range(self.ring_count)
        ]

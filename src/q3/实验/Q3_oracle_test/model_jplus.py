"""Model J+ (final): model J with the measurement-scheduling correction.

J+ = J + two changes, both confined to where measurements are taken:

1. No measurement detours during the coverage sweep.  ``_insertion_before``
   is disabled, so the sweep only visits the 8 stops (origin + 7 ring points),
   scans undiscovered channels and co-observes at the stops.  The Q2
   measurement points are taken later, on the way, inside the rolling clearing
   route.  Under the compact R = 1000 ring the sweep is close to the sources,
   so a detour inserted mid-sweep costs more than it saves; this was the
   opposite for the old R = 1250 geometry, where the mechanism came from.
2. The Q2 four-metric weights are re-calibrated to equal weights and the
   co-observation budget per stop is raised from 3 to 5, both screened and
   validated on three paired 1000-case seeds.

Everything else (Q2 selector core, 19.75 m clearing rule, rolling scheduler,
coverage ring) is inherited from J unchanged.
"""
from __future__ import annotations

from model_j import JAgent


class JPlusAgent(JAgent):
    def _insertion_before(self, next_coverage):
        return None

    weights = (0.25, 0.25, 0.25, 0.25)
    coverage_extra_measure_budget = 5

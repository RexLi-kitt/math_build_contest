"""One-command certificate audit for the recommended H8 design."""
from __future__ import annotations

from certify import certify
from fast_q4 import H8Agent


class _StubSim:
    position = (0.0, 0.0)
    time_s = 0.0
    actions: list = []


if __name__ == "__main__":
    agent = H8Agent(_StubSim())
    for r_step, t_step in ((10.0, 0.5), (5.0, 0.25)):
        gap, worst = certify(agent.search_points, r_step=r_step, t_step=t_step)
        verdict = "PASS" if gap <= 180.0 else "FAIL"
        print(f"H8 n={len(agent.search_points)} grid(r={r_step:g}m,t={t_step:g}deg) "
              f"max_gap={gap:.2f} worst=({worst[0]:.0f},{worst[1]:.0f}) {verdict}")

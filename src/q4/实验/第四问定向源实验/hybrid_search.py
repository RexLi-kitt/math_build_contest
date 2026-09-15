"""Hybrid designs: inner surround patch + sparse outer rings (certificate + tour)."""
from __future__ import annotations

import sys

sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")
from certify import certify, ring


def build(*spec):
    sites = [(0.0, 0.0)]
    for radius, count, offset in spec:
        sites.extend(ring(radius, count, offset))
    return sites


CANDIDATES = {
    "H1 i3r450 + 6x1100 + 6x1905 + 12x2200": build((450, 3, 90), (1100, 6, 0), (1905, 6, 30), (2200, 12, 0)),
    "H2 i3r450 + 6x1100 + 6x1905 + 6x2400": build((450, 3, 90), (1100, 6, 0), (1905, 6, 30), (2400, 6, 0)),
    "H3 i6r500 + 6x1100 + 6x1905 + 12x2200": build((500, 6, 0), (1100, 6, 0), (1905, 6, 30), (2200, 12, 0)),
    "H4 i3r450 + 6x1000 + 6x1900 + 6x2200": build((450, 3, 90), (1000, 6, 0), (1900, 6, 0), (2200, 6, 0)),
    "H5 i3r450 + 6x1000 + 12x1900": build((450, 3, 90), (1000, 6, 0), (1900, 12, 0)),
    "H6 i6r500 + 6x1000 + 12x1900": build((500, 6, 0), (1000, 6, 0), (1900, 12, 0)),
    "H7 6x1000 + 6x1300 + 6x1600 + 6x1900 + 6x2200": build((1000, 6, 0), (1300, 6, 30), (1600, 6, 0), (1900, 6, 30), (2200, 6, 0)),
    "H8 6x1000 + 12x1400 + 12x2000": build((1000, 6, 0), (1400, 12, 15), (2000, 12, 0)),
    "H9 8x900 + 8x1300 + 8x1700 + 8x2100 + 8x2400": build((900, 8, 0), (1300, 8, 22.5), (1700, 8, 0), (2100, 8, 22.5), (2400, 8, 0)),
    "H10 8x900 + 8x1400 + 8x1900 + 8x2300": build((900, 8, 0), (1400, 8, 22.5), (1900, 8, 0), (2300, 8, 22.5)),
    "H11 8x950 + 8x1400 + 8x1850 + 8x2300": build((950, 8, 0), (1400, 8, 22.5), (1850, 8, 0), (2300, 8, 22.5)),
    "H12 8x1000 + 8x1400 + 8x1800 + 8x2200": build((1000, 8, 0), (1400, 8, 22.5), (1800, 8, 0), (2200, 8, 22.5)),
    "H13 8x1000 + 8x1500 + 8x2000 + 8x2400": build((1000, 8, 0), (1500, 8, 22.5), (2000, 8, 0), (2400, 8, 22.5)),
    "H14 8x1000 + 8x1450 + 8x1900 + 8x2350": build((1000, 8, 0), (1450, 8, 22.5), (1900, 8, 0), (2350, 8, 22.5)),
}

if __name__ == "__main__":
    from strong_tsp import solve_tour
    passing = []
    for name, sites in CANDIDATES.items():
        coarse, wx = certify(sites, r_step=50.0, t_step=3.0)
        if coarse <= 180.0:
            fine, wx2 = certify(sites, r_step=20.0, t_step=1.0)
            if fine <= 180.0:
                wx = wx2
        else:
            fine = coarse
        if fine <= 180.0:
            order, cost = solve_tour(sites[1:], restarts=25)
            passing.append((cost, fine, len(sites), name))
        print(f"{name:>50}: n={len(sites):>2} gap={fine:7.2f} "
              f"{'PASS' if fine <= 180 else 'FAIL'} worst=({wx[0]:6.0f},{wx[1]:6.0f})")
    print()
    passing.sort()
    for cost, gap, n, name in passing:
        print(f"BEST {name}: n={n} gap={gap:.2f} tour={cost:.0f}m ({cost/5:.0f}s)")

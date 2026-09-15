"""Search certified ring/lattice Q4 sweep designs: min tour subject to surround gap <= 180."""
from __future__ import annotations

import itertools
import math
import sys

sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")
from certify import Area, Reach, certify, dist, max_gap_at, ring, tour_length


def evaluate(sites, coarse=True):
    worst, wx = certify(sites, r_step=50.0, t_step=3.0) if coarse else certify(sites)
    return worst, tour_length(sites), wx


def design(*rings):
    sites = []
    for r, n, off in rings:
        if r == 0.0:
            sites.append((0.0, 0.0))
        else:
            sites.extend(ring(r, n, off))
    return sites


CANDIDATES = {
    "c+6x1000+12x2000": design((0, 1, 0), (1000, 6, 0), (2000, 12, 0)),
    "c+6x1000+12x2000off15": design((0, 1, 0), (1000, 6, 0), (2000, 12, 15)),
    "c+6x1000+6x1500+12x2000": design((0, 1, 0), (1000, 6, 0), (1500, 6, 30), (2000, 12, 0)),
    "c+12x1000+12x2000": design((0, 1, 0), (1000, 12, 0), (2000, 12, 15)),
    "c+6x1000+12x1700+12x2400": design((0, 1, 0), (1000, 6, 0), (1700, 12, 15), (2400, 12, 0)),
    "c+12x950+12x1900": design((0, 1, 0), (950, 12, 0), (1900, 12, 15)),
    "c+6x1000+6x1550+6x2100+6x2600": design((0, 1, 0), (1000, 6, 0), (1550, 6, 30), (2100, 6, 0), (2600, 6, 30)),
    "c+8x900+8x1400+8x1900+8x2400": design((0, 1, 0), (900, 8, 0), (1400, 8, 22.5), (1900, 8, 0), (2400, 8, 22.5)),
    "c+9x950+9x1500+9x2050+9x2550": design((0, 1, 0), (950, 9, 0), (1500, 9, 20), (2050, 9, 40), (2550, 9, 0)),
    "c+6x1000+6x1450+6x1900+6x2350+6x2750": design((0, 1, 0), (1000, 6, 0), (1450, 6, 30),
                                                    (1900, 6, 0), (2350, 6, 30), (2750, 6, 0)),
    "c+6x1000+12x1800+12x2600": design((0, 1, 0), (1000, 6, 0), (1800, 12, 15), (2600, 12, 0)),
}

if __name__ == "__main__":
    for name, sites in CANDIDATES.items():
        worst, length, wx = evaluate(sites, coarse=True)
        if worst <= 180.0:
            fine, _ = certify(sites)
            status = "PASS" if fine <= 180.0 else "FAIL-fine"
            print(f"{name:>36}: n={len(sites):>2} coarse={worst:7.2f} fine={fine:7.2f} "
                  f"tour={length:7.0f}m ({length/5:5.0f}s) {status}")
        else:
            print(f"{name:>36}: n={len(sites):>2} coarse={worst:7.2f} tour={length:7.0f}m FAIL")

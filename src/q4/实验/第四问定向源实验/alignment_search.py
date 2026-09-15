"""Test L1100-family ring alignments: same 19 sites, no extra scan cost."""
from __future__ import annotations

import sys

sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")
from certify import certify, ring, tour_length


def design(*rings):
    sites = []
    for r, n, off in rings:
        sites.extend([(0.0, 0.0)] if r == 0 else ring(r, n, off))
    return sites


CANDIDATES = {
    "L1100 offsets 0/30/0": design((0, 1, 0), (1100, 6, 0), (1905, 6, 30), (2200, 6, 0)),
    "A 0/0/30": design((0, 1, 0), (1100, 6, 0), (1905, 6, 0), (2200, 6, 30)),
    "B 0/0/0": design((0, 1, 0), (1100, 6, 0), (1905, 6, 0), (2200, 6, 0)),
    "C 1000 0/0/0": design((0, 1, 0), (1000, 6, 0), (1900, 6, 0), (2600, 6, 0)),
    "D 1000 0/0/30": design((0, 1, 0), (1000, 6, 0), (1900, 6, 0), (2600, 6, 30)),
    "E 1100 0/30/30": design((0, 1, 0), (1100, 6, 0), (1905, 6, 30), (2200, 6, 30)),
    "F 1100 0/30/15": design((0, 1, 0), (1100, 6, 0), (1905, 6, 30), (2200, 6, 15)),
    "G 1000 0/30/0": design((0, 1, 0), (1000, 6, 0), (1800, 6, 30), (2500, 6, 0)),
    "H 1100 0/0/30 x2300": design((0, 1, 0), (1100, 6, 0), (1900, 6, 0), (2300, 6, 30)),
    "I 1100 0/0/30 x2100": design((0, 1, 0), (1100, 6, 0), (1900, 6, 0), (2100, 6, 30)),
    "J 1100 0/0 rings12": design((0, 1, 0), (1100, 6, 0), (1900, 12, 0)),
    "K 1050 0/0/30": design((0, 1, 0), (1050, 6, 0), (1900, 6, 0), (2200, 6, 30)),
    "L 1100 0/0/30 no2200": design((0, 1, 0), (1100, 6, 0), (1900, 6, 0)),
    "M 900+1700+2500 0/30/0": design((0, 1, 0), (900, 6, 0), (1700, 6, 30), (2500, 6, 0)),
}

if __name__ == "__main__":
    for name, sites in CANDIDATES.items():
        coarse, wx = certify(sites, r_step=50.0, t_step=3.0)
        tag = "coarse"
        if coarse <= 180.0:
            fine, wx2 = certify(sites, r_step=20.0, t_step=1.0)
            tag = "fine"
        else:
            fine = coarse
        length = tour_length(sites)
        status = "PASS" if fine <= 180.0 else "FAIL"
        print(f"{name:>30}: n={len(sites):>2} {tag}={fine:7.2f} "
              f"tour={length:7.0f}m ({length/5:5.0f}s) {status} "
              f"worst=({wx[0]:6.0f},{wx[1]:6.0f})")

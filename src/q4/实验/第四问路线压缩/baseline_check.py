"""基线校准：同一 TSP 求解器、同一细审计下复测 H8 与 ShiftB。"""
import sys
import math

sys.path.insert(0, r"C:\Users\李\Desktop\第四问定向源实验")
from certify import certify, ring
from strong_tsp import solve_tour

# H8: 中心 + 6x1000 + 12x1400 + 12x2000
h8 = [(0.0, 0.0)] + ring(1000, 6, 0.0) + ring(1400, 12, 15.0) + ring(2000, 12, 0.0)

# ShiftB: 990 米三角格，(0, 0.5) 相位，与圆相交三角形顶点 + 原点
import q4_routes
shiftb = [(0.0, 0.0)] + [p for p in q4_routes.clipped_sites(
    990.0, 0.0, 0.5 * 990.0 * math.sqrt(3) / 2) if math.hypot(*p) > 1e-7]

for name, pts in (("H8", h8), ("ShiftB", shiftb)):
    order, cost = solve_tour(pts[1:], restarts=100)
    gap, wx = certify(pts, r_step=10.0, t_step=0.5)
    print(f"{name}: n={len(pts)} tour={cost:.0f}m ({cost/5:.0f}s) "
          f"fine_gap={gap:.2f} worst=({wx[0]:.0f},{wx[1]:.0f})")

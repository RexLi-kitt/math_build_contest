"""certify.py 原版终审: 对冠军与激进设计跑双网格审计, 输出论文用证书数字。"""
import json
import sys
import time
from pathlib import Path

Q4_ROOT = Path(__file__).resolve().parents[3]
if str(Q4_ROOT) not in sys.path:
    sys.path.insert(0, str(Q4_ROOT))
from certify import certify  # noqa: E402

HERE = Path(__file__).resolve().parent.parent  # 设计 JSON 在上一级

for name in ("winner_design.json", "aggressive_design.json"):
    data = json.loads((HERE / name).read_text(encoding="utf-8"))
    sites = [tuple(p) for p in data["sites"]]
    t0 = time.perf_counter()
    gf, wx1 = certify(sites, r_step=10.0, t_step=0.5)
    gu, wx2 = certify(sites, r_step=5.0, t_step=0.25)
    print(f"{name}: n={len(sites)} tour={data['tour_m']:.0f}m "
          f"certify(10/0.5)={gf:.2f} certify(5/0.25)={gu:.2f} "
          f"worst=({wx2[0]:.0f},{wx2[1]:.0f}) "
          f"tube(certfast)={data.get('gap_tube', float('nan')):.2f} "
          f"({time.perf_counter() - t0:.0f}s)", flush=True)

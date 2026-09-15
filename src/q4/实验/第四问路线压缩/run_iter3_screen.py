"""迭代 3 筛选: D-opt 选点最大绕行上限 250(基线)/450/700, 100 局 seed 20260928。"""
import sys
from pathlib import Path

EXP = r"C:\Users\李\Desktop\第四问定向源实验"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, EXP)
sys.path.insert(0, str(HERE))

import q4_optimize  # noqa: E402
from cert_route_agent import CertRouteAgent  # noqa: E402


class Extra450Agent(CertRouteAgent):
    max_extra_distance_m = 450.0


class Extra700Agent(CertRouteAgent):
    max_extra_distance_m = 700.0


q4_optimize.STRATEGIES.update({
    "Base": CertRouteAgent,
    "Extra450": Extra450Agent,
    "Extra700": Extra700Agent,
})

if __name__ == "__main__":
    sys.argv = [
        "screen",
        "--cases", "100",
        "--seed", "20260928",
        "--strategies", "Base,Extra450,Extra700",
        "--min-success", "1.0",
        "--jobs", "16",
        "--output", str(HERE / "results" / "iter3_screen100"),
    ]
    q4_optimize.main()

"""顺序变体筛选: 100 局 seed 20260928, Base / OrdDens / OrdArea / OrdTspReopt。"""
import sys
from pathlib import Path

EXP = r"C:\Users\李\Desktop\第四问定向源实验"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, EXP)
sys.path.insert(0, str(HERE))

import q4_optimize  # noqa: E402
from cert_route_agent import CertRouteAgent  # noqa: E402
from cert_order_agents import (OrderAreaAgent, OrderDensAgent,  # noqa: E402
                               OrderTspReoptAgent)

q4_optimize.STRATEGIES.update({
    "Base": CertRouteAgent,
    "OrdDens": OrderDensAgent,
    "OrdArea": OrderAreaAgent,
    "OrdTspReopt": OrderTspReoptAgent,
})

if __name__ == "__main__":
    sys.argv = [
        "screen",
        "--cases", "100",
        "--seed", "20260928",
        "--strategies", "Base,OrdDens,OrdArea,OrdTspReopt",
        "--min-success", "1.0",
        "--jobs", "16",
        "--output", str(HERE / "results" / "iter5_order_screen100"),
    ]
    q4_optimize.main()

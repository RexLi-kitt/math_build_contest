"""边际插入预算筛选: 100 局新种子(20260928), 对比不同绕行预算。

策略: Base(无插入) / Ins200 / Ins350 / Ins500 / Ins800 / Ins500x16。
筛选种子不用于最终验证; 选定预算后在 20260923(500) + 20260924(200) 上复核。
"""
import sys
from pathlib import Path

EXP = r"C:\Users\李\Desktop\第四问定向源实验"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, EXP)
sys.path.insert(0, str(HERE))

import q4_optimize  # noqa: E402
from cert_route_agent import CertRouteAgent  # noqa: E402
from cert_insert_agent import (Insert200Agent, Insert350Agent, Insert500Agent,  # noqa: E402
                               Insert500x16Agent, Insert800Agent)

q4_optimize.STRATEGIES.update({
    "Base": CertRouteAgent,
    "Ins200": Insert200Agent,
    "Ins350": Insert350Agent,
    "Ins500": Insert500Agent,
    "Ins800": Insert800Agent,
    "Ins500x16": Insert500x16Agent,
})

if __name__ == "__main__":
    sys.argv = [
        "screen",
        "--cases", "100",
        "--seed", "20260928",
        "--strategies", "Base,Ins200,Ins350,Ins500,Ins800,Ins500x16",
        "--min-success", "1.0",
        "--jobs", "16",
        "--output", str(HERE / "results" / "insert_screen100"),
    ]
    q4_optimize.main()

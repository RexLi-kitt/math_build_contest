"""边界与朝向压力回放、覆盖几何检查，以及独立配对结果汇总。"""
import json
import math
import random
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from q4_experiment import random_mixed_sources
from q4_optimize import run_case, L950C2
from q4_routes import ShiftB, triangle_intersects_disk


def work(item):
    index, sources = item
    return [run_case(index, sources, 20260924, name, cls)
            for name, cls in [('baseline', L950C2), ('route28', ShiftB)]]


def main():
    # 半径1000米，16源中12定向，靠边且定向朝外；策略不可读取这些真值。
    rng = random.Random(20260924)
    cases = []
    for index in range(200):
        sources = random_mixed_sources(rng, 16, .75)
        for source in sources:
            angle = rng.random() * 2 * math.pi
            radius = 1800.0 if index % 2 == 0 else rng.uniform(1700, 1800)
            source.position = radius * math.cos(angle), radius * math.sin(angle)
            source.receive_radius = 1000.0
            if source.beam_direction is not None:
                source.beam_direction = math.degrees(angle) % 360
        cases.append((index + 1, sources))
    rows = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        for index, result in enumerate(pool.map(work, cases), 1):
            rows.extend(result)
            if index % 25 == 0:
                print(f'stress {index}/200', flush=True)
    result = {}
    for name in ('baseline', 'route28'):
        group = [r for r in rows if r['strategy'] == name]
        result[name] = {'all_clear': sum(r['all_cleared'] for r in group),
                        'cases': len(group),
                        'mean_seconds_per_source': statistics.mean(r['total_virtual_time_s']/r['source_count'] for r in group)}
    assert all(v['all_clear'] == v['cases'] for v in result.values()), result
    output = Path('results/route_boundary200')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (output / 'cases.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

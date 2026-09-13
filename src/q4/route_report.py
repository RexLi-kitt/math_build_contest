"""汇总独立配对效果，保留代码哈希和验证口径。"""
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent


def main():
    folder = ROOT / 'outputs' / 'q4' / 'results' / 'route_holdout500'
    rows = list(csv.DictReader((folder / 'case_results.csv').open(encoding='utf-8-sig')))
    for row in rows:
        total = sum(float(row[key]) for key in ('movement_time_s', 'detection_time_s',
                    'switching_time_s', 'clearing_time_s'))
        assert abs(total-float(row['total_virtual_time_s'])) <= 0.00051
        assert int(row['all_cleared']) == 1
    groups = {name: {int(r['case']): r for r in rows if r['strategy'] == name}
              for name in ('L950_C2', 'ShiftB')}
    delta = [(float(groups['L950_C2'][i]['total_virtual_time_s'])-
              float(groups['ShiftB'][i]['total_virtual_time_s'])) /
             int(groups['L950_C2'][i]['source_count']) for i in groups['L950_C2']]
    mean = statistics.mean(delta)
    half = 1.96 * statistics.stdev(delta) / math.sqrt(len(delta))
    checks = {'paired_mean_saved_s_per_source': mean, 'normal_95_ci': [mean-half, mean+half],
              'improved_cases': sum(d > 0 for d in delta), 'cases': len(delta),
              'hashes': {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                         for name in ('q4_routes.py','q4_experiment.py','q4_optimize.py')}}
    (folder / 'paired_effect.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
    print(json.dumps(checks, indent=2))


if __name__ == '__main__':
    main()

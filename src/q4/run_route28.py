"""运行已验证的28点路线方案，默认与旧31点方案配对比较。"""
import sys
from pathlib import Path
from q4_optimize import main

if __name__ == '__main__':
    if '--strategies' not in sys.argv:
        sys.argv.extend(['--strategies', 'L950_C2,ShiftB'])
    if '--min-success' not in sys.argv:
        sys.argv.extend(['--min-success', '1.0'])
    if '--output' not in sys.argv:
        output = Path(__file__).resolve().parents[2] / 'outputs' / 'q4' / 'results' / 'route_holdout500'
        sys.argv.extend(['--output', str(output)])
    main()

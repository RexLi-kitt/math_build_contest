from pathlib import Path
import ast
import json
import subprocess
import sys

root = Path(__file__).resolve().parent / '支撑材料'
for path in sorted(root.glob('*.py')):
    ast.parse(path.read_text(encoding='utf-8-sig'), filename=path.name)
    program = 'import sys, runpy; sys.path.insert(0, sys.argv[1]); runpy.run_path(sys.argv[2], run_name="__main__")'
    result = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', '-c', program, str(root), str(path)], cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=20)
    print(json.dumps({'file':path.name, 'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr},ensure_ascii=False))

for path in sorted(root.glob('*.json')):
    payload = json.loads(path.read_text(encoding='utf-8-sig'))
    print('\nDATA', path.name, type(payload).__name__)
    if isinstance(payload, dict):
        for key, value in payload.items():
            rendered = str(value)
            print(key, type(value).__name__, len(value) if hasattr(value, '__len__') else '', rendered[:900])
    else:
        print('length', len(payload), 'first', str(payload[:1])[:900])

for path in sorted(root.glob('*.jlog')):
    data=path.read_bytes()
    print('LOG',path.name,'bytes',len(data),'prefix',repr(data[:80]))

sys.path.insert(0, str(root))
import q3_selector
try:
    def metrics(candidate):
        return q3_selector.raw_metrics([(0., 0.)], [((100.,0.),180.)], (100.,0.), candidate,1000.,lambda *_:((0.,0.),1.))
    print('Q3 selector no reception:',q3_selector.next_measurement_point((0.,0.),0.,q3_selector.WEIGHTS_JPLUS,metrics))
except Exception as exc:
    print('Q3 selector no reception:',type(exc).__name__,str(exc))

import q2_solver
try:
    print('Q2 negative-score candidates:', q2_solver.choose_second_point(0.,(0.,0.25,0.50,0.25),lambda q:dict(q_geo=0.,p_rec=1.,travel_s=1. if q[1]>=-450. else 2.,r_pred_m=2. if q[1]>=-450. else 1.)))
except Exception as exc:
    print('Q2 negative-score candidates:',type(exc).__name__,str(exc))

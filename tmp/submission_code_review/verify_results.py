from pathlib import Path
import sys
import json
import math

root=Path(__file__).resolve().parent/'支撑材料'
sys.path.insert(0,str(root))
import q1_solver as q1
import q1_exact_verify as exact
payload=json.loads((root/'q1_experiment_data.json').read_text(encoding='utf-8'))
matched=0
failures=[]
for case in payload['cases']:
    angles=[obs['measured_bearing_deg'] for obs in case['observations']]
    state,vertices,_,_=q1.localize(case['stations'],angles)
    d,d2,_=exact.convex_diameter(vertices)
    _,d2_ex,_=exact.convex_diameter(vertices,'exhaustive')
    covers=exact.diameter_circle_coverage(vertices)[2]
    good=state==case['status'] and math.isclose(d,case['diameter_m'],abs_tol=1e-8,rel_tol=1e-10) and d2==d2_ex and covers==case['circle_covers']
    matched+=good
    if not good: failures.append(dict(case=case['case_id'],actual=d,expected=case['diameter_m'],state=state,covers=covers))
print('Q1_RECOMPUTE',json.dumps(dict(total=len(payload['cases']),matched=matched,failures=failures),ensure_ascii=False))

for name in ['b','c']:
    route=json.loads((root/f'q4_{name}_route_design.json').read_text(encoding='utf-8'))
    sites=route['sites']
    points=[sites[i] for i in route['order']]
    distance=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
    print('Q4_ROUTE',name,len(points),len({tuple(x) for x in points}),points[0],distance,'recorded',route['tour_m'])

for path in sorted(root.glob('*.jlog')):
    header=json.JSONDecoder().raw_decode(path.read_bytes()[14:].decode('utf-8',errors='replace'))[0]
    print('LOG_HEADER',json.dumps({key:header.get(key) for key in ['package_type','problem_no','formal_index','case_code','content_encryption']},ensure_ascii=False))

payload=json.loads((root/'q3_jplus_final_actions.json').read_text(encoding='utf-8'))
from collections import Counter
print('Q3_ACTION_KINDS',dict(Counter(x['kind'] for x in payload)))
print('Q3_ACTION_CLEAR_RESULTS',dict(Counter(x['result'] for x in payload if 'clear' in x['kind'])))
print('Q3_ACTION_LAST',json.dumps(payload[-1],ensure_ascii=False))

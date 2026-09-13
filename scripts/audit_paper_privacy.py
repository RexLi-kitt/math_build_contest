from zipfile import ZipFile
from pathlib import Path
from lxml import etree

p = Path('outputs/论文修订/26B主论文_Q4插图与覆盖条件修订版.docx')
z = ZipFile(p)
terms = ['李培煜','TEAM_ID','robot_id','参赛队','队号','队员','姓名','手机号','电话','邮箱','@','Desktop','codex','简要用途','TODO','待补','占位']
print('metadata:')
for name in ('docProps/core.xml', 'docProps/app.xml', 'docProps/custom.xml'):
    if name in z.namelist(): print(name, z.read(name).decode('utf-8', 'ignore'))
print('term hits by package part:')
for name in z.namelist():
    raw = z.read(name)
    try: text = raw.decode('utf-8', 'ignore')
    except Exception: continue
    hits = sorted({t for t in terms if t.lower() in text.lower()})
    if hits: print(name, hits)
print('external relationships:')
for name in z.namelist():
    if name.endswith('.rels'):
        text = z.read(name).decode('utf-8', 'ignore')
        if 'TargetMode="External"' in text: print(name, text)
ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
print('visible lines with sensitive/template hits:')
for name in z.namelist():
    if not (name.startswith('word/') and name.endswith('.xml')): continue
    try: root=etree.fromstring(z.read(name))
    except Exception: continue
    txt='\n'.join(root.xpath('//w:t/text()|//m:t/text()', namespaces=ns))
    for line in txt.splitlines():
        if any(t.lower() in line.lower() for t in terms): print(name+': '+line)

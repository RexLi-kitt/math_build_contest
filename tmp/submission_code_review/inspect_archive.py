from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent
archive = Path(r'C:\Users\李\Desktop\最终最终提交文件\支撑材料.zip')
with zipfile.ZipFile(archive) as z:
    for member in z.infolist():
        target = (root / member.filename).resolve()
        if not target.is_relative_to(root):
            raise ValueError(member.filename)
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(member))
for path in sorted((root / '支撑材料').glob('*.py')):
    print('\n=== ' + path.name + ' ===')
    for index, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        print(f'{index}: {line}')

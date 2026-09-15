import json
from pathlib import Path

base = Path(r"C:\Users\李\Desktop\第四问定向源实验\results")
for name in ("screen50", "refine100", "optimization", "better_screen80"):
    p = base / name / "summary.json"
    if not p.exists():
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    print("==", name)
    for s in d.get("summaries", []):
        print(f"  {s['strategy']:>10}: succ={s.get('success_rate')} "
              f"s/src={s.get('mean_time_per_source_s', 0):7.1f} "
              f"det={s.get('mean_detection_per_source_s', 0):6.1f} "
              f"post_mv={s.get('mean_post_search_movement_per_source_s', 0):6.1f}")

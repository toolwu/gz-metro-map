"""用高德官方坐标转换 API 把 WGS-84 点转成 GCJ-02，带缓存"""
import json
import pathlib
import time

import requests

BASE = pathlib.Path(__file__).parent.parent
DATA_DIR = BASE / "data"
KEY_FILE = BASE / "secrets.json"
CONVERT_URL = "https://restapi.amap.com/v3/assistant/coordinate/convert"


def load_key():
    if KEY_FILE.exists():
        return json.loads(KEY_FILE.read_text(encoding="utf-8")).get("AMAP_KEY")
    return None


def convert_to_gcj(points, delay=0.35):
    """points: [(lng, lat), ...] -> [(glng, glat), ...]（失败点返回 None）"""
    cache_path = DATA_DIR / "gcj_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    results = [None] * len(points)
    todo = []
    for i, (lng, lat) in enumerate(points):
        key = f"{round(lng, 6)},{round(lat, 6)}"
        if key in cache:
            results[i] = tuple(cache[key])
        else:
            todo.append(i)

    for start in range(0, len(todo), 40):
        batch = todo[start:start + 40]
        locs = "|".join(f"{points[i][0]},{points[i][1]}" for i in batch)
        params = {"key": load_key(), "locations": locs, "coordsys": "gps"}
        try:
            d = requests.get(CONVERT_URL, params=params, timeout=20,
                             headers={"User-Agent": "Mozilla/5.0"}).json()
            if d.get("status") == "1" and d.get("locations"):
                vals = d["locations"].split(";")
                for idx, v in zip(batch, vals):
                    glng, glat = map(float, v.split(","))
                    cache[f"{round(points[idx][0], 6)},{round(points[idx][1], 6)}"] = [glng, glat]
                    results[idx] = (glng, glat)
            else:
                print("  坐标转换失败:", d.get("info"))
        except Exception as e:
            print("  坐标转换请求失败:", str(e)[:80])
        time.sleep(delay)

    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return results

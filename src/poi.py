"""poi.py — 通过 ohsome API(OpenStreetMap 聚合计数，免 key) 并发抓取每个站点周边 POI 密度。

对每个唯一站点，以站点坐标为中心、config.radius_m 为半径，按 OSM key 分组计数
（amenity/shop/leisure/tourism/healthcare/office/building）。
带：线程池并发、缓存(poi_cache.json)、断点续跑、限速、重试、429/5xx 退避。
数据为「抽样密度」(OSM 在逃数据)，非商业全量，仅供便利度参考。
"""
import json
import os
import time
import threading
import sqlite3
import urllib.parse
import urllib.request
import concurrent.futures

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stations import BASE, DATA, DB

CONFIG = json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))
POI = CONFIG["poi"]
CACHE = os.path.join(DATA, "poi_cache.json")
KEYS = POI["keys"]
ENDPOINT = POI["endpoint"]
FILTER = POI["filter"]
RETRY = POI.get("retry_times", 3)
WORKERS = POI.get("workers", 8)
RADIUS = CONFIG["scope"]["radius_m"]
SAVE_EVERY = 25

_lock = threading.Lock()


def _query(lat, lng, radius):
    params = {
        "bcircles": "1:%s,%s,%d" % (lng, lat, radius),
        "groupByKeys": ",".join(KEYS),
        "filter": FILTER,
    }
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "gz-metro-convenience/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.load(r)
    out = {k: 0 for k in KEYS}
    for item in d.get("groupByResult", []):
        try:
            out[item["groupByObject"]] = int(item["result"][0]["value"])
        except (KeyError, IndexError, TypeError):
            pass
    return out


def _fetch_one(st, radius, cache):
    sid = st["station_id"]
    res = None
    for attempt in range(RETRY):
        try:
            res = _query(st["lat"], st["lng"], radius)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 5 * (attempt + 1)
            else:
                wait = 2 * (attempt + 1)
            time.sleep(wait)
        except Exception:
            time.sleep(2 * (attempt + 1))
    if res is None:
        res = {k: 0 for k in KEYS}
    with _lock:
        cache[sid] = {
            "name": st["name"], "lat": st["lat"], "lng": st["lng"],
            "radius_m": radius, "counts": res,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }


def run(stations, force=False, radius=None):
    radius = radius or RADIUS
    cache = {}
    if os.path.exists(CACHE) and not force:
        try:
            cache = json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            cache = {}

    todo = [s for s in stations if force or s["station_id"] not in cache]
    total = len(stations)
    print("[poi] 待抓取 %d / 共 %d（缓存命中 %d）" % (len(todo), total, total - len(todo)))

    done = 0
    if todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            fut_to_st = {ex.submit(_fetch_one, st, radius, cache): st for st in todo}
            for fut in concurrent.futures.as_completed(fut_to_st):
                fut.result()
                done += 1
                if done % SAVE_EVERY == 0:
                    with _lock:
                        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
                    print("  [progress] %d/%d" % (done, len(todo)))
    with _lock:
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    # 写库 poi_stats
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS poi_stats
                 (station_id TEXT, category TEXT, count INTEGER, radius_m INTEGER, fetched_at TEXT)""")
    c.execute("DELETE FROM poi_stats")
    for sid, v in cache.items():
        for k, cnt in v.get("counts", {}).items():
            c.execute("INSERT INTO poi_stats VALUES (?,?,?,?,?)",
                      (sid, k, cnt, v.get("radius_m", radius), v.get("fetched_at")))
    conn.commit()
    conn.close()
    print("[poi] 完成，缓存 %d 站 → %s" % (len(cache), CACHE))
    return cache


if __name__ == "__main__":
    import stations as S
    _, sts = S.run()
    run(sts)

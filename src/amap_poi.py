"""用高德官方 POI 统计地铁站周边配套（半径 300m，坐标 GCJ-02）
餐饮/购物/生活/医疗/教育 用高德；交通用 OSM 地铁口（同半径）。
解决 OSM 覆盖不均问题；count 在 600 封顶时自动缩小半径重查。
"""
import json
import math
import pathlib
import random
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

BASE = pathlib.Path(__file__).parent.parent
DATA_DIR = BASE / "data"
KEY_FILE = BASE / "secrets.json"

URL = "https://restapi.amap.com/v3/place/around"
TYPES = {
    "餐饮服务": "050000",
    "购物服务": "060000",
    "生活服务": "070000",
    "医疗卫生": "090000",
    "科教文化": "100000",
}
RADIUS = 300
CAP = 600  # 高德 count 封顶值


# ---------- WGS-84 -> GCJ-02 ----------
def _out_of_china(lng, lat):
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _t_lat(x, y):
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _t_lng(x, y):
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lng, lat):
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _t_lat(lng - 105.0, lat - 35.0)
    dlng = _t_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - 0.00669342162296594323 * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((6378245.0 * (1 - 0.00669342162296594323)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (6378245.0 / sqrtmagic * math.cos(radlat) * math.pi)
    return lng + dlng, lat + dlat


def load_key():
    if KEY_FILE.exists():
        data = json.loads(KEY_FILE.read_text(encoding="utf-8"))
        return data.get("AMAP_KEY")
    return None


def _query(lng, lat, types, radius):
    params = {
        "key": load_key(),
        "location": f"{lng},{lat}",
        "types": types,
        "radius": radius,
        "offset": 25,
        "page": 1,
        "extensions": "base",
    }
    r = requests.get(URL, params=params, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    d = r.json()
    if d.get("status") != "1":
        return None, d.get("info", "")
    return int(d.get("count") or 0), ""


def around_count(lng, lat, types, retries=2):
    """count 封顶时缩小半径重查（250m）"""
    glng, glat = wgs84_to_gcj02(lng, lat)
    for attempt in range(retries + 1):
        try:
            c, info = _query(glng, glat, types, RADIUS)
            if c is None:
                if info:
                    print(f"    高德: {info}")
                if "USER_DAILY_QUERY_OVER_LIMIT" in info or "CUQPS_HAS_EXCEEDED_THE_LIMIT" in info:
                    return None
            else:
                if c >= CAP:
                    c2, _ = _query(glng, glat, types, 250)
                    if c2 is not None:
                        return c2
                return c
        except Exception as e:
            print(f"    请求失败 {type(e).__name__} {str(e)[:60]}")
        time.sleep(random.uniform(1.2, 2.0))
    return None


def around_paginate(lng, lat, types, radius=300, max_pages=60, delay=0.35, retries=2):
    """翻页数真实数量（处理 count 600 封顶）；返回累计条数，页数超上限或失败返回 None"""
    glng, glat = wgs84_to_gcj02(lng, lat)
    total = 0
    for page in range(1, max_pages + 1):
        got = None
        for attempt in range(retries + 1):
            try:
                params = {
                    "key": load_key(),
                    "location": f"{glng},{glat}",
                    "types": types,
                    "radius": radius,
                    "offset": 25,
                    "page": page,
                    "extensions": "base",
                }
                d = requests.get(URL, params=params, timeout=20, headers={"User-Agent": "Mozilla/5.0"}).json()
                if d.get("status") == "1":
                    got = len(d.get("pois", []))
                    break
                print(f"    高德: {d.get('info')}")
                if "USER_DAILY_QUERY_OVER_LIMIT" in d.get("info", "") or "CUQPS_HAS_EXCEEDED_THE_LIMIT" in d.get("info", ""):
                    return None
            except Exception as e:
                print(f"    请求失败 {type(e).__name__} {str(e)[:60]}")
            time.sleep(random.uniform(1.2, 2.0))
        if got is None:
            return None
        total += got
        if got < 25:
            break
        time.sleep(delay)
    if page >= max_pages:
        print(f"    达到页数上限 {max_pages}，累计 {total}（可能仍不完整）")
    return total


def fix_capped(capped_names=None, cat="购物服务", max_pages=60):
    """对 count 封顶的站翻页补全真实数量（默认处理所有 >=600 的购物站）"""
    cache_path = DATA_DIR / "amap_poi_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    stations = json.loads((DATA_DIR / "stations_dedup.json").read_text(encoding="utf-8"))
    by_name = {st["name"]: st for st in stations}

    if capped_names is None:
        capped_names = [n for n, d in cache.items() if d.get(cat, 0) >= CAP]

    print(f"待补全 {len(capped_names)} 站: {capped_names}")
    for i, name in enumerate(capped_names, 1):
        st = by_name.get(name)
        if not st or st.get("lng") is None:
            print(f"  [{name}] 无坐标，跳过")
            continue
        real = around_paginate(st["lng"], st["lat"], TYPES[cat], radius=RADIUS, max_pages=max_pages)
        if real is None:
            print(f"  [{name}] 失败，保留原值")
            continue
        if name in cache:
            cache[name][cat] = real
        else:
            cache[name] = {cat: real}
        print(f"  [{name}] 购物 {cache[name].get(cat)} -> {real}")
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(0.5)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"补全完成，缓存已更新（{len(cache)} 站）")
    return cache


MALL_TYPE = "060100"  # 商场/购物中心


def fetch_mall_counts(stations, delay=0.35, limit=None):
    """给所有站数'大型商场'数量（060100），存进缓存和 poi_stats.json"""
    cache_path = DATA_DIR / "amap_poi_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    todo = stations[:limit] if limit else stations
    for i, st in enumerate(todo, 1):
        name = st["name"]
        if "商场数" in cache.get(name, {}):
            continue
        c = around_count(st["lng"], st["lat"], MALL_TYPE)
        if c is None:
            print(f"  [{name}] 商场数查询失败，跳过")
            continue
        cache.setdefault(name, {})["商场数"] = c
        if i % 50 == 0:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"进度 {i}/{len(todo)}")
        time.sleep(delay)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    # 同步到 poi_stats.json
    poi = json.loads((DATA_DIR / "poi_stats.json").read_text(encoding="utf-8"))
    for name, d in cache.items():
        if "商场数" in d and name in poi:
            poi[name]["商场数"] = d["商场数"]
    (DATA_DIR / "poi_stats.json").write_text(json.dumps(poi, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"商场数完成：{sum(1 for d in cache.values() if '商场数' in d)} 站")


def run(stations, limit=None, delay=0.35):
    key = load_key()
    if not key:
        print("没有高德 key（secrets.json），跳过")
        return {}
    cache_path = DATA_DIR / "amap_poi_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    todo = stations[:limit] if limit else stations
    results = {}
    for i, st in enumerate(todo, 1):
        name = st["name"]
        if name in cache:
            results[name] = cache[name]
            continue
        counts = {}
        ok = True
        for cat, t in TYPES.items():
            c = around_count(st["lng"], st["lat"], t)
            if c is None:
                ok = False
                print(f"  [{name}] 高德失败，跳过（将回退 OSM）")
                break
            counts[cat] = c
            time.sleep(delay)
        if not ok:
            continue
        cache[name] = counts
        results[name] = counts
        if i % 20 == 0:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"进度 {i}/{len(todo)}")
        time.sleep(delay)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"高德 POI 完成：{len(results)} 站（缓存 {len(cache)}）")
    return results


def merge_into_poi_stats(amap_counts, osm_path="poi_stats_osm_300.json"):
    """高德 5 类 + OSM 交通(300m)；缺高德的站回退 OSM 全量"""
    osm = json.loads((DATA_DIR / osm_path).read_text(encoding="utf-8"))
    poi = json.loads((DATA_DIR / "poi_stats.json").read_text(encoding="utf-8"))
    merged = 0
    for name, counts in amap_counts.items():
        if name in osm:
            base = dict(osm[name])
            for cat in TYPES:
                base[cat] = counts.get(cat, base.get(cat, 0))
            poi[name] = base
            merged += 1
    poi_path = DATA_DIR / "poi_stats.json"
    poi_path.write_text(json.dumps(poi, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已合并高德数据：{merged} 站；其余 {len(poi) - merged} 站回退 OSM")
    return poi


if __name__ == "__main__":
    stations = json.loads((DATA_DIR / "stations_dedup.json").read_text(encoding="utf-8"))
    counts = run(stations)
    if counts:
        merge_into_poi_stats(counts)

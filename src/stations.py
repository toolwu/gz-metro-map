"""获取广州地铁站点+线路数据（高德公开接口），坐标 GCJ-02 -> WGS-84"""
import json
import math
import pathlib
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

AMAP_URL = "https://map.amap.com/service/subway?_=1&srhdata=4401_drw_guangzhou.json"
BASE = pathlib.Path(__file__).parent.parent
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(exist_ok=True)


# ---------- GCJ-02 -> WGS-84 ----------
def _out_of_china(lng, lat):
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(x, y):
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x, y):
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def gcj02_to_wgs84(lng, lat):
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lon(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - 0.00669342162296594323 * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((6378245.0 * (1 - 0.00669342162296594323)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (6378245.0 / sqrtmagic * math.cos(radlat) * math.pi)
    mg_lat = lat + dlat
    mg_lng = lng + dlng
    return lng * 2 - mg_lng, lat * 2 - mg_lat


# ---------- 抓取与解析 ----------
def fetch_raw():
    r = requests.get(AMAP_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.json()


def parse_lines(raw):
    lines = []
    for ln in raw.get("l", []):
        line_name = ln.get("ln", "")
        color = ln.get("cl", "#666666")
        stations = []
        for st in ln.get("st", []):
            name = st.get("n", "").strip()
            sl = st.get("sl", "")
            seq = int(st.get("su", 0) or 0)
            lng = lat = None
            if "," in sl:
                try:
                    lng_s, lat_s = sl.split(",")
                    lng, lat = gcj02_to_wgs84(float(lng_s), float(lat_s))
                except ValueError:
                    lng = lat = None
            stations.append({"name": name, "line": line_name, "seq": seq, "lng": lng, "lat": lat})
        if stations:
            lines.append({"line": line_name, "color": color, "stations": stations})
    return lines


def save_lines(lines):
    (DATA_DIR / "stations.json").write_text(
        json.dumps(lines, ensure_ascii=False, indent=1), encoding="utf-8")


def dedup_stations(lines):
    seen = {}
    for ln in lines:
        for st in ln["stations"]:
            name = st["name"]
            if name not in seen:
                seen[name] = {"name": name, "lng": st["lng"], "lat": st["lat"], "lines": [], "is_transfer": False}
            if ln["line"] not in seen[name]["lines"]:
                seen[name]["lines"].append(ln["line"])
            seen[name]["is_transfer"] = len(seen[name]["lines"]) > 1
    stations = list(seen.values())
    (DATA_DIR / "stations_dedup.json").write_text(
        json.dumps(stations, ensure_ascii=False, indent=1), encoding="utf-8")
    return stations


def fetch_and_save():
    raw = fetch_raw()
    lines = parse_lines(raw)
    save_lines(lines)
    stations = dedup_stations(lines)
    print(f"线路 {len(lines)} 条，去重后站点 {len(stations)} 个")
    return lines, stations


if __name__ == "__main__":
    fetch_and_save()

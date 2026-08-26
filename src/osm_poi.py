"""从本地 OSM pbf（广东省）解析广州 POI 并按站点周边 1000m 计数"""
import json
import math
import pathlib
import sys

import numpy as np
import osmium

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

BASE = pathlib.Path(__file__).parent.parent
DATA_DIR = BASE / "data"
PBF_SRC = pathlib.Path(r"C:\Users\Administrator\Desktop\知乎未答\gz_metro_map_codex\data\guangdong.osm.pbf")
# 中文路径会导致 pyosmium 在 Windows 打不开，解析前复制到纯 ASCII 临时路径
import tempfile as _tf
PBF = pathlib.Path(_tf.gettempdir()) / "gz_guangdong.osm.pbf"
RADIUS = 1000

CATEGORIES = ["餐饮服务", "购物服务", "生活服务", "医疗卫生", "科教文化", "交通设施"]

AMENITY_TO_CAT = {
    "restaurant": "餐饮服务", "cafe": "餐饮服务", "fast_food": "餐饮服务",
    "bar": "餐饮服务", "pub": "餐饮服务", "food_court": "餐饮服务",
    "bank": "生活服务", "atm": "生活服务", "post_office": "生活服务",
    "laundry": "生活服务", "beauty": "生活服务", "car_wash": "生活服务",
    "hospital": "医疗卫生", "clinic": "医疗卫生", "pharmacy": "医疗卫生",
    "dentist": "医疗卫生", "doctors": "医疗卫生",
    "school": "科教文化", "kindergarten": "科教文化", "college": "科教文化",
    "university": "科教文化", "library": "科教文化",
}

# 广州 bbox（含佛山接入线、增城、从化）
BBOX = (22.70, 112.95, 23.70, 113.95)  # south, west, north, east


class POIHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.pois = {c: [] for c in CATEGORIES}

    def node(self, n):
        if not n.location.valid():
            return
        lat, lon = n.location.lat, n.location.lon
        if not (BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lon <= BBOX[3]):
            return
        tags = dict(n.tags)
        name = tags.get("name", "")
        amenity = tags.get("amenity", "")
        # 只数"有名气"的 POI（带 name），减少小卖部/无名点位噪音
        if amenity in AMENITY_TO_CAT and name:
            self.pois[AMENITY_TO_CAT[amenity]].append((lat, lon))
        if "shop" in tags and name:
            self.pois["购物服务"].append((lat, lon))
        # 交通只算地铁出入口（去掉公交站，公交站到处都有、无区分度）
        if tags.get("railway") == "subway_entrance":
            self.pois["交通设施"].append((lat, lon))


def ensure_pbf():
    if not PBF_SRC.exists():
        raise FileNotFoundError(f"缺少 OSM 数据包：{PBF_SRC}")
    import shutil
    if not PBF.exists() or PBF.stat().st_size != PBF_SRC.stat().st_size:
        print(f"复制数据包到临时路径（{PBF}）...")
        shutil.copyfile(str(PBF_SRC), str(PBF))
    return PBF


def load_poi_arrays():
    ensure_pbf()
    handler = POIHandler()
    handler.apply_file(str(PBF), locations=True)
    arrays = {}
    for c in CATEGORIES:
        arr = np.array(handler.pois[c], dtype=np.float64).reshape(-1, 2)
        arrays[c] = arr
        print(f"  {c}: {len(arr)} 个点")
    return arrays


def count_for_stations(stations, poi_arrays, radius=1000):
    results = {}
    m_per_deg_lat = 111320.0
    for i, st in enumerate(stations, 1):
        lat0, lng0 = st["lat"], st["lng"]
        m_per_deg_lng = 111320.0 * math.cos(math.radians(lat0))
        dlat_max = radius / m_per_deg_lat
        dlng_max = radius / m_per_deg_lng
        counts = {}
        for c, arr in poi_arrays.items():
            if len(arr) == 0:
                counts[c] = 0
                continue
            sub = arr[(np.abs(arr[:, 0] - lat0) <= dlat_max) & (np.abs(arr[:, 1] - lng0) <= dlng_max)]
            if len(sub) == 0:
                counts[c] = 0
                continue
            dy = (sub[:, 0] - lat0) * m_per_deg_lat
            dx = (sub[:, 1] - lng0) * m_per_deg_lng
            counts[c] = int(np.sum(dx * dx + dy * dy <= radius * radius))
        results[st["name"]] = counts
        if i % 50 == 0:
            print(f"  计数进度 {i}/{len(stations)}")
    return results


def run(radius=1000, out_name="poi_stats.json"):
    print(f"解析 OSM pbf（约 1~3 分钟）...")
    arrays = load_poi_arrays()
    stations = json.loads((DATA_DIR / "stations_dedup.json").read_text(encoding="utf-8"))
    print(f"按站点 {radius}m 计数...")
    results = count_for_stations(stations, arrays, radius=radius)
    (DATA_DIR / out_name).write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    # 汇总
    total = {c: 0 for c in CATEGORIES}
    for name, counts in results.items():
        for c in CATEGORIES:
            total[c] += counts[c]
    print("全站 POI 汇总:", total)
    return results


if __name__ == "__main__":
    run()

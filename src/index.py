"""生活便利指数计算：各类 POI 全站百分位归一化 + 加权求和"""
import json
import pathlib

BASE = pathlib.Path(__file__).parent.parent
DATA_DIR = BASE / "data"

DEFAULT_WEIGHTS = {
    "餐饮服务": 0.25,
    "购物服务": 0.20,
    "生活服务": 0.20,
    "交通设施": 0.15,
    "医疗卫生": 0.10,
    "科教文化": 0.10,
}


def compute_index(stations, poi_stats, weights=None):
    weights = weights or DEFAULT_WEIGHTS
    cats = list(weights.keys())

    # 每类在全站中的百分位（0~100）
    ranked = {}
    for c in cats:
        vals = sorted(poi_stats.get(st["name"], {}).get(c, 0) for st in stations)
        n = max(len(vals), 1)
        r = {}
        for st in stations:
            v = poi_stats.get(st["name"], {}).get(c, 0)
            r[st["name"]] = round(sum(1 for x in vals if x <= v) / n * 100, 1)
        ranked[c] = r

    # 购物 = 70% 购物数量 + 30% 大型商场数（治 count 封顶 + 顺带治"数量≠质量"）
    if "购物服务" in ranked:
        mall_vals = sorted(poi_stats.get(st["name"], {}).get("商场数", 0) for st in stations)
        nm = max(len(mall_vals), 1)
        for st in stations:
            mv = poi_stats.get(st["name"], {}).get("商场数", 0)
            mall_pct = sum(1 for x in mall_vals if x <= mv) / nm * 100
            ranked["购物服务"][st["name"]] = 0.7 * ranked["购物服务"][st["name"]] + 0.3 * mall_pct

    out = []
    for st in stations:
        name = st["name"]
        poi = poi_stats.get(name, {})
        idx = sum(weights[c] * ranked[c].get(name, 0) for c in cats)
        out.append({
            "name": name,
            "lng": st.get("lng"),
            "lat": st.get("lat"),
            "lines": st.get("lines", []),
            "is_transfer": st.get("is_transfer", False),
            "facility_index": round(idx, 1),
            "poi": poi,
            "poi_total": sum(poi.values()),
        })

    out.sort(key=lambda x: x["facility_index"], reverse=True)
    for i, st in enumerate(out, 1):
        st["rank_city"] = i
    return out


def save_index(items):
    (DATA_DIR / "index.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return items


def load_and_compute():
    stations = json.loads((DATA_DIR / "stations_dedup.json").read_text(encoding="utf-8"))
    poi = json.loads((DATA_DIR / "poi_stats.json").read_text(encoding="utf-8"))
    items = compute_index(stations, poi)
    save_index(items)
    print(f"指数计算完成：{len(items)} 个站点")
    return items


if __name__ == "__main__":
    load_and_compute()

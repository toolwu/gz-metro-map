"""一键：抓站点 → 本地解析OSM POI → 算指数 → 出图 → 摘要"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from src import stations, osm_poi, index, build_map, summary


def main():
    print("=== 1/5 抓取地铁站点（高德公开接口） ===")
    lines, sts = stations.fetch_and_save()

    print("=== 2/5 本地解析 OSM POI（guangdong.osm.pbf） ===")
    osm_poi.run()

    print("=== 3/5 计算便利指数 ===")
    index.load_and_compute()

    print("=== 4/5 生成地图 ===")
    build_map.build_map()

    print("=== 5/5 生成摘要 ===")
    summary.run()

    print("\n全部完成！打开 output/广州地铁生活便利地图.html 查看")


if __name__ == "__main__":
    main()

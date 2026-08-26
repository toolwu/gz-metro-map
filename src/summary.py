"""生成便利指数 TOP 站点摘要（md）"""
import json
import pathlib
from datetime import datetime, timezone, timedelta

BASE = pathlib.Path(__file__).parent.parent
DATA_DIR = BASE / "data"
OUTPUT_DIR = BASE / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

CN_TZ = timezone(timedelta(hours=8))


def run():
    items = json.loads((DATA_DIR / "index.json").read_text(encoding="utf-8"))
    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    lines = [
        f"# 广州地铁生活便利指数 TOP（数据截至 {today}）\n",
        f"- 站点总数：{len(items)}",
        f"- 数据说明：POI 为 OpenStreetMap 抽样密度（站点周边 1000m），非全量；指数为百分位加权分（餐饮25% 购物20% 生活20% 交通15% 医疗10% 教育10%）\n",
        "",
        "## TOP 20\n",
        "| 排名 | 站点 | 指数 | 线路 | 换乘 | 餐饮 | 购物 | 生活 | 医疗 | 教育 | 交通 |",
        "|------|------|------|------|------|------|------|------|------|------|------|",
    ]
    for st in items[:20]:
        poi = st.get("poi", {})
        lines.append(
            f"| {st['rank_city']} | {st['name']} | {st['facility_index']} | "
            f"{' / '.join(st['lines'])} | {'是' if st['is_transfer'] else ''} | "
            f"{poi.get('餐饮服务', 0)} | {poi.get('购物服务', 0)} | {poi.get('生活服务', 0)} | "
            f"{poi.get('医疗卫生', 0)} | {poi.get('科教文化', 0)} | {poi.get('交通设施', 0)} |"
        )
    lines.append("\n## 底部 5 站\n")
    for st in items[-5:]:
        lines.append(f"- {st['name']}（{st['facility_index']}）")
    (OUTPUT_DIR / "便利指数TOP.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"摘要已生成：{OUTPUT_DIR / '便利指数TOP.md'}")
    return lines


if __name__ == "__main__":
    run()

"""把 folium HTML 里的外部 CDN 资源全部内嵌，生成完全离线的单文件"""
import pathlib
import re

import requests

BASE = pathlib.Path(__file__).parent.parent
ASSET_CACHE = BASE / "data" / "assets"
ASSET_CACHE.mkdir(parents=True, exist_ok=True)


def fetch(url):
    cache = ASSET_CACHE / (re.sub(r"[^A-Za-z0-9_.-]", "_", url))
    if cache.exists():
        return cache.read_bytes()
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    cache.write_bytes(r.content)
    return r.content


def strip_fonts(css):
    """去掉 @font-face（避免内嵌后字体 404），图标降级为文字"""
    return re.sub(r"@font-face\s*{[^}]*}", "", css)


def inline_file(html_path):
    html = pathlib.Path(html_path).read_text(encoding="utf-8")

    def repl_script(m):
        url = m.group(1)
        content = fetch(url).decode("utf-8", errors="replace")
        return "<script>\n" + content + "\n</script>"

    html = re.sub(r'<script src="([^"]+)"[^>]*></script>', repl_script, html)

    def repl_link(m):
        url = m.group(1)
        content = fetch(url).decode("utf-8", errors="replace")
        if ".css" in url or "css" in url:
            return "<style>\n" + strip_fonts(content) + "\n</style>"
        return ""

    html = re.sub(r'<link[^>]+href="([^"]+)"[^>]*/?>', repl_link, html)

    pathlib.Path(html_path).write_text(html, encoding="utf-8")
    print(f"已内嵌全部资源，文件大小：{len(html) // 1024} KB")


if __name__ == "__main__":
    inline_file(BASE / "output" / "广州地铁生活便利地图.html")

"""生成广州地铁生活便利交互地图（自包含单 HTML，底图适配国内网络）"""
import json
import pathlib
from datetime import datetime, timezone, timedelta

import folium
from folium.plugins import HeatMap

BASE = pathlib.Path(__file__).parent.parent
DATA_DIR = BASE / "data"
OUTPUT_DIR = BASE / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

CN_TZ = timezone(timedelta(hours=8))


def load_config():
    return json.loads((BASE / "config.json").read_text(encoding="utf-8"))


def tier_color(idx, cfg):
    if idx >= cfg["index"]["green"]:
        return "#2E8B57"
    if idx >= cfg["index"]["yellow"]:
        return "#E6A23C"
    return "#D64545"


def add_base_layers(m):
    """国内可达的底图：ESRI 默认，高德/OSM/Carto 备选"""
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        name="ESRI 街道（默认）", attr="ESRI",
    ).add_to(m)
    folium.TileLayer(
        tiles="https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
        name="高德", attr="高德", subdomains="1234",
    ).add_to(m)
    folium.TileLayer(
        tiles="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        name="OSM", attr="OSM",
    ).add_to(m)
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        name="Carto 亮", attr="Carto", subdomains="abcd",
    ).add_to(m)


def build_map():
    cfg = load_config()
    lines = json.loads((DATA_DIR / "stations.json").read_text(encoding="utf-8"))
    items = json.loads((DATA_DIR / "index.json").read_text(encoding="utf-8"))
    by_name = {st["name"]: st for st in items}

    center = cfg["map"]["center"]
    m = folium.Map(location=center, zoom_start=cfg["map"]["zoom"], tiles=None)
    mapvar = m.get_name()
    add_base_layers(m)

    # 1) 线路 polyline
    for ln in lines:
        pts = [(st["lat"], st["lng"]) for st in sorted(ln["stations"], key=lambda x: x["seq"])
               if st["lat"] is not None]
        if len(pts) >= 2:
            folium.PolyLine(pts, color="#" + ln["color"] if ln.get("color") else "#666",
                            weight=4, opacity=0.75, tooltip=ln["line"]).add_to(m)

    # 2) 站点标记
    fg_stations = folium.FeatureGroup(name="站点")
    for st in items:
        if st["lat"] is None or st["lng"] is None:
            continue
        idx = st["facility_index"]
        radius = 8 + idx / 100 * 18
        color = tier_color(idx, cfg)
        lines_str = " / ".join(st["lines"])
        popup_html = (
            f"<b>{st['name']}</b>（{lines_str}）<br>"
            f"便利指数：<b>{idx}</b>（全市第 {st['rank_city']}）<br>"
            f"换乘站：{'是' if st['is_transfer'] else '否'}<br>"
            f"餐饮 {st['poi'].get('餐饮服务', 0)} · 购物 {st['poi'].get('购物服务', 0)} · "
            f"生活 {st['poi'].get('生活服务', 0)}<br>"
            f"医疗 {st['poi'].get('医疗卫生', 0)} · 教育 {st['poi'].get('科教文化', 0)} · "
            f"交通 {st['poi'].get('交通设施', 0)}<br>"
            f"<span style='color:#999'>POI 为 OSM 周边 1000m 抽样密度</span>"
        )
        folium.CircleMarker(
            location=[st["lat"], st["lng"]],
            radius=radius,
            color=color,
            weight=1.5,
            fill=True,
            fill_color=color,
            fill_opacity=0.75,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=st["name"],
            title=st["name"],
        ).add_to(fg_stations)
    fg_stations.add_to(m)

    # 3) POI 总密度热力
    heat_data = [[st["lat"], st["lng"], max(st["poi_total"], 1)] for st in items
                 if st["lat"] is not None]
    heat_wgs = heat_data
    fg_heat = folium.FeatureGroup(name="POI 密度热力", show=False)
    HeatMap(heat_data, radius=22, blur=18, min_opacity=0.3).add_to(fg_heat)
    fg_heat.add_to(m)

    # 4) 数据注入 + 控制面板 + 底图自动切换兜底
    marker_names = [st["name"] for st in items]

    # 官方 GCJ-02 坐标（高德底图用；失败点回退 JS 近似）
    try:
        from src import gcj_convert
    except ImportError:
        import gcj_convert
    gcj_markers = []
    for st in items:
        r = gcj_convert.convert_to_gcj([(st["lng"], st["lat"])])
        gcj_markers.append([r[0][1], r[0][0]] if r[0] else None)
    gcj_lines = []
    for ln in lines:
        pts = [(st["lat"], st["lng"]) for st in sorted(ln["stations"], key=lambda x: x["seq"]) if st["lat"] is not None]
        if len(pts) >= 2:
            rs = gcj_convert.convert_to_gcj([(lng, lat) for lat, lng in pts])
            gcj_lines.append([[r[1], r[0]] if r else [lat, lng] for r, (lat, lng) in zip(rs, pts)])
    gcj_heat = []
    for lat, lng, w in heat_data:
        r = gcj_convert.convert_to_gcj([(lng, lat)])
        gcj_heat.append([r[0][1], r[0][0], w] if r[0] else [lat, lng, w])

    data_js = {st["name"]: {
        "idx": st["facility_index"],
        "lines": st["lines"],
        "transfer": st["is_transfer"],
    } for st in items}

    # 排名查询数据
    stations_js = {}
    for st in items:
        stations_js[st["name"]] = {
            "idx": st["facility_index"], "rank": st["rank_city"],
            "lat": st["lat"], "lng": st["lng"], "lines": st["lines"],
            "poi": st.get("poi", {}),
        }
    ranked_js = [st["name"] for st in sorted(items, key=lambda x: x["rank_city"])]
    top_rows = "".join(
        f'<div onclick="flyToStation(\'{st["name"]}\')" style="cursor:pointer;padding:2px 0;border-bottom:1px solid #eee">'
        f'<span style="color:#999">#{st["rank_city"]}</span> {st["name"]} <b>{st["facility_index"]}</b></div>'
        for st in sorted(items, key=lambda x: x["rank_city"])[:20]
    )

    line_names = [ln["line"] for ln in lines]
    checkboxes = "".join(
        f'<label><input type="checkbox" class="lineCb" value="{ln}" checked> {ln}</label>'
        for ln in line_names
    )

    panel_html = f"""
    <div id="ctl" style="position:absolute;top:10px;right:10px;z-index:1000;background:#fff;
         border:1px solid #ccc;border-radius:8px;padding:12px;width:250px;box-shadow:0 2px 8px rgba(0,0,0,.15);
         font:12px/1.6 'Microsoft YaHei',sans-serif;max-height:90vh;overflow:auto;">
      <b>广州地铁生活便利度</b><br>
      <span style="color:#999">数据截至 {datetime.now(CN_TZ).strftime('%Y-%m-%d')} · OSM 抽样</span><br>
      <label>指数 ≥ <input id="idxMin" type="number" value="0" min="0" max="100" style="width:50px"></label><br>
      <label><input id="onlyTransfer" type="checkbox"> 只看换乘站</label><br>
      <div id="lineBox" style="margin:4px 0">{checkboxes}</div>
      <button onclick="applyFilter()">应用筛选</button>
      <div style="margin-top:8px">当前显示：<b id="statCount">{len(items)}</b> 站</div>
      <div style="margin-top:8px;border-top:1px solid #eee;padding-top:6px">
        <b>查询</b><br>
        站名：<input id="qStation" style="width:80px" placeholder="如 公园前"> <button onclick="queryStation()">查</button>
        <div id="qResult" style="color:#333"></div>
        排名：<input id="qRank" type="number" min="1" style="width:50px" placeholder="如 3"> <button onclick="queryRank()">查</button>
        <div id="qRankResult" style="color:#333"></div>
      </div>
      <div style="margin-top:8px;border-top:1px solid #eee;padding-top:6px">
        <b>TOP 20（点击跳转）</b>
        <div id="topList" style="max-height:180px;overflow:auto">{top_rows}</div>
      </div>
      <div style="margin-top:8px">
        <span style="color:#2E8B57">●</span> ≥75（优）
        <span style="color:#E6A23C">●</span> 50~74
        <span style="color:#D64545">●</span> &lt;50
      </div>
      <div style="margin-top:8px;color:#999">若底图空白会自动切换；也可用右上角"图层"按钮手动换底图。</div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(panel_html))

    js = f"""
    var DATA = {json.dumps(data_js, ensure_ascii=False)};
    var STATIONS = {json.dumps(stations_js, ensure_ascii=False)};
    var RANKED = {json.dumps(ranked_js, ensure_ascii=False)};
    var MARKER_NAMES = {json.dumps(marker_names, ensure_ascii=False)};
    var GCJ_MARKERS = {json.dumps(gcj_markers, ensure_ascii=False)};
    var GCJ_LINES = {json.dumps(gcj_lines, ensure_ascii=False)};
    var GCJ_HEAT = {json.dumps(gcj_heat, ensure_ascii=False)};
    var HEAT_WGS = {json.dumps(heat_wgs, ensure_ascii=False)};

    // ---------- 坐标转换：高德底图用 GCJ-02，其余用 WGS-84 ----------
    function wgs2gcj(lng, lat) {{
      var a = 6378245.0, ee = 0.00669342162296594323;
      function tLat(x, y) {{
        var r = -100.0 + 2.0*x + 3.0*y + 0.2*y*y + 0.1*x*y + 0.2*Math.sqrt(Math.abs(x));
        r += (20.0*Math.sin(6.0*x*Math.PI) + 20.0*Math.sin(2.0*x*Math.PI)) * 2.0/3.0;
        r += (20.0*Math.sin(y*Math.PI) + 40.0*Math.sin(y/3.0*Math.PI)) * 2.0/3.0;
        r += (160.0*Math.sin(y/12.0*Math.PI) + 320.0*Math.sin(y*Math.PI/30.0)) * 2.0/3.0;
        return r;
      }}
      function tLng(x, y) {{
        var r = 300.0 + x + 2.0*y + 0.1*x*x + 0.1*x*y + 0.1*Math.sqrt(Math.abs(x));
        r += (20.0*Math.sin(6.0*x*Math.PI) + 20.0*Math.sin(2.0*x*Math.PI)) * 2.0/3.0;
        r += (20.0*Math.sin(x*Math.PI) + 40.0*Math.sin(x/3.0*Math.PI)) * 2.0/3.0;
        r += (150.0*Math.sin(x/12.0*Math.PI) + 300.0*Math.sin(x/30.0*Math.PI)) * 2.0/3.0;
        return r;
      }}
      var dLat = tLat(lng - 105.0, lat - 35.0);
      var dLng = tLng(lng - 105.0, lat - 35.0);
      var radLat = lat / 180.0 * Math.PI;
      var magic = Math.sin(radLat);
      magic = 1 - ee * magic * magic;
      var sqrtMagic = Math.sqrt(magic);
      dLat = (dLat * 180.0) / ((a * (1 - ee)) / (magic * sqrtMagic) * Math.PI);
      dLng = (dLng * 180.0) / (a / sqrtMagic * Math.cos(radLat) * Math.PI);
      return [lng + dLng, lat + dLat];
    }}

    var vectorLayers = {{markers: [], lines: [], heat: null, bases: []}};
    var markersByName = {{}};
    function selectStation(name) {{
      var mk = markersByName[name];
      if (!mk) return;
      var el = mk.getElement();
      if (el) el.style.display = '';
      try {{ mk.bringToFront(); }} catch (e) {{}}
      try {{ if (mk.getPopup()) mk.openPopup(); }} catch (e) {{}}
    }}
    var BASE_ORDER = ['ESRI 街道（默认）', '高德', 'OSM', 'Carto 亮'];
    function collectVectorLayers() {{
      {mapvar}.eachLayer(function(layer) {{
        if (layer instanceof L.CircleMarker) {{
          var ll = layer.getLatLng();
          layer._wgs = [ll.lat, ll.lng];
          layer._name = MARKER_NAMES[vectorLayers.markers.length] || '';
          layer._gcj = GCJ_MARKERS[vectorLayers.markers.length] || null;
          layer._origStyle = {{
            radius: layer.options.radius, color: layer.options.color,
            weight: layer.options.weight, fillColor: layer.options.fillColor,
            fillOpacity: layer.options.fillOpacity
          }};
          if (layer._name) markersByName[layer._name] = layer;
          vectorLayers.markers.push(layer);
        }} else if (layer instanceof L.Polyline) {{
          layer._wgs = layer.getLatLngs().map(function(ll){{ return [ll.lat, ll.lng]; }});
          layer._gcj = GCJ_LINES[vectorLayers.lines.length] || null;
          vectorLayers.lines.push(layer);
        }} else if (layer instanceof L.HeatLayer) {{
          layer._wgs = HEAT_WGS;
          layer._gcj = GCJ_HEAT;
          vectorLayers.heat = layer;
        }} else if (layer instanceof L.TileLayer && vectorLayers.bases.length < BASE_ORDER.length) {{
          layer._baseName = BASE_ORDER[vectorLayers.bases.length];
          vectorLayers.bases.push(layer);
        }}
      }});
    }}
    function setVectorCoords(useGcj) {{
      vectorLayers.markers.forEach(function(m) {{
        if (useGcj && m._gcj) {{ m.setLatLng(m._gcj); }}
        else if (!useGcj) {{ m.setLatLng(m._wgs); }}
        else {{ var p = wgs2gcj(m._wgs[1], m._wgs[0]); m.setLatLng([p[1], p[0]]); }}
      }});
      vectorLayers.lines.forEach(function(pl) {{
        if (useGcj && pl._gcj) {{ pl.setLatLngs(pl._gcj); }}
        else if (!useGcj) {{ pl.setLatLngs(pl._wgs); }}
        else {{ pl.setLatLngs(pl._wgs.map(function(ll){{ var p = wgs2gcj(ll[1], ll[0]); return [p[1], p[0]]; }})); }}
      }});
      if (vectorLayers.heat && vectorLayers.heat.setLatLngs) {{
        if (useGcj && vectorLayers.heat._gcj) {{ vectorLayers.heat.setLatLngs(vectorLayers.heat._gcj); }}
        else if (!useGcj) {{ vectorLayers.heat.setLatLngs(vectorLayers.heat._wgs); }}
        else {{ vectorLayers.heat.setLatLngs(vectorLayers.heat._wgs.map(function(p){{ var q = wgs2gcj(p[1], p[0]); return [q[1], q[0], p[2]]; }})); }}
      }}
    }}
    function activeBaseIsGaode() {{
      for (var i = 0; i < vectorLayers.bases.length; i++) {{
        if ({mapvar}.hasLayer(vectorLayers.bases[i]) && vectorLayers.bases[i]._baseName.indexOf('高德') >= 0) return true;
      }}
      return false;
    }}
    function flyToStation(name) {{
      var st = STATIONS[name];
      if (st && st.lat) {mapvar}.flyTo([st.lat, st.lng], 15);
      selectStation(name);
    }}
    function queryStation() {{
      var q = document.getElementById('qStation').value.trim();
      var out = document.getElementById('qResult');
      var st = STATIONS[q];
      if (!st) {{ out.innerHTML = '<span style="color:#c00">未找到「' + q + '」（试试：公园前 / 体育西路）</span>'; return; }}
      var poi = st.poi || {{}};
      out.innerHTML = '<b>' + q + '</b> 便利指数 <b>' + st.idx + '</b>（全市第 ' + st.rank + '）<br>' +
        '线路：' + st.lines.join(' / ') + '<br>' +
        '餐饮 ' + (poi['餐饮服务'] || 0) + ' · 购物 ' + (poi['购物服务'] || 0) + ' · 生活 ' + (poi['生活服务'] || 0) + '<br>' +
        '医疗 ' + (poi['医疗卫生'] || 0) + ' · 教育 ' + (poi['科教文化'] || 0) + ' · 交通 ' + (poi['交通设施'] || 0);
      flyToStation(q);
    }}
    function queryRank() {{
      var q = parseInt(document.getElementById('qRank').value, 10);
      var out = document.getElementById('qRankResult');
      var name = RANKED[q - 1];
      if (!name) {{ out.innerHTML = '<span style="color:#c00">没有第 ' + q + ' 名（共 ' + RANKED.length + ' 站）</span>'; return; }}
      out.innerHTML = '第 ' + q + ' 名：<b>' + name + '</b>（' + STATIONS[name].idx + ' 分）';
      flyToStation(name);
    }}
    function applyFilter() {{
      var minIdx = parseFloat(document.getElementById('idxMin').value) || 0;
      var onlyTransfer = document.getElementById('onlyTransfer').checked;
      var showLines = {{}};
      document.querySelectorAll('input.lineCb').forEach(function(cb){{ showLines[cb.value] = cb.checked; }});
      var count = 0;
      {mapvar}.eachLayer(function(layer){{
        if (!(layer instanceof L.CircleMarker)) return;
        var info = DATA[layer._name] || {{idx:0, lines:[], transfer:false}};
        var ok = info.idx >= minIdx;
        if (ok && onlyTransfer && !info.transfer) ok = false;
        if (ok && !info.lines.some(function(ln){{ return showLines[ln]; }})) ok = false;
        var el = layer.getElement();
        if (el) el.style.display = ok ? '' : 'none';
        if (ok) count++;
      }});
      document.getElementById('statCount').textContent = count;
    }}

    // 底图加载失败自动切换（地图初始化完成后注册）
    document.addEventListener('DOMContentLoaded', function () {{
    collectVectorLayers();
    {mapvar}.on('baselayerchange', function(e) {{
      var name = e.name || (e.layer && e.layer._baseName) || '';
      setVectorCoords(name.indexOf('高德') >= 0);
    }});
    // 兜底：底图增删也同步坐标（兼容部分环境 baselayerchange 不触发）
    function _syncBaseCoords() {{ setVectorCoords(activeBaseIsGaode()); }}
    {mapvar}.on('layeradd layerremove', function(e) {{
      if (e.layer && e.layer._baseName) setTimeout(_syncBaseCoords, 50);
    }});
    var baseNames = ['ESRI 街道（默认）', '高德（坐标略有偏移）', 'OSM', 'Carto 亮'];
    var errCount = {{}};
    {mapvar}.on('tileerror', function(ev){{
      var layer = ev.layer;
      if (!layer || !layer._baseName) return;
      var name = layer._baseName;
      errCount[name] = (errCount[name] || 0) + 1;
      if (errCount[name] >= 3) {{
        var i = baseNames.indexOf(name);
        var next = baseNames[(i + 1) % baseNames.length];
        {mapvar}.eachLayer(function(l){{
          if (l instanceof L.TileLayer && l.options.name) {{
            if (l.options.name === next) {{ {mapvar}.addLayer(l); }}
            else if (l.options.name === name) {{ {mapvar}.removeLayer(l); }}
          }}
        }});
        errCount[name] = 0;
        setVectorCoords(activeBaseIsGaode());
      }}
    }});
    }});
    """
    m.get_root().script.add_child(folium.Element(js))

    folium.LayerControl(collapsed=False, position='bottomleft').add_to(m)

    out_path = OUTPUT_DIR / "广州地铁生活便利地图.html"
    m.save(str(out_path))
    print(f"地图已生成：{out_path}")
    try:
        from inline_assets import inline_file
        inline_file(out_path)
    except Exception as e:
        print("内嵌资源失败（不影响地图生成）:", e)
    return out_path


if __name__ == "__main__":
    build_map()

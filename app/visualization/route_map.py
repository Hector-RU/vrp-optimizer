"""Road geometry with ordered concurrent fetching and an atomic local cache."""
from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path
import json
import math
import threading

import folium
import requests
from app.config import config

route_cache = {}
CACHE_FILE = str(Path(config.MAP_OUTPUT_DIR) / "route_cache.json")
cache_lock = threading.RLock()


def popup_text(value):
    # Folium embeds popup HTML in a JavaScript template literal.
    return escape(str(value)).replace("`", "&#96;").replace("$", "&#36;").replace("\\", "&#92;")


def load_cache():
    with cache_lock:
        if route_cache:
            return
        try:
            data = json.loads(Path(CACHE_FILE).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                route_cache.update(data)
        except (OSError, ValueError):
            pass


def save_cache():
    with cache_lock:
        try:
            path = Path(CACHE_FILE)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(route_cache), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            pass


def fallback_segment(start, end):
    lat1, lng1, lat2, lng2 = map(math.radians, (*start, *end))
    a = math.sin((lat2 - lat1) / 2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lng2 - lng1) / 2)**2
    distance = 6371 * 2 * math.asin(min(1, math.sqrt(a)))
    return [start, end], distance, distance * 2.5


def _fetch_osrm_segment(start, end, cache_key):
    url = f"https://router.project-osrm.org/route/v1/driving/{start[1]},{start[0]};{end[1]},{end[0]}"
    try:
        response = requests.get(url, params={"overview": "full", "geometries": "geojson"}, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            result = ([[lat, lng] for lng, lat in route["geometry"]["coordinates"]],
                      route["distance"] / 1000, route["duration"] / 60)
            with cache_lock:
                route_cache[cache_key] = result
            return result
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        pass
    return fallback_segment(start, end)


def get_osrm_route(coords, use_cache=True):
    if len(coords) < 2:
        return coords, 0, 0
    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for i, (start, end) in enumerate(zip(coords, coords[1:])):
            key = str(tuple(round(value, 6) for value in (*start, *end)))
            with cache_lock:
                cached = route_cache.get(key) if use_cache else None
            if start == end:
                results[i] = ([start, end], 0, 0)
            elif cached is not None:
                results[i] = cached
            else:
                futures[i] = executor.submit(_fetch_osrm_segment, start, end, key)
        for i, future in futures.items():
            results[i] = future.result()
    full_route = [coords[0]]
    distance = duration = 0
    for i in range(len(coords) - 1):
        segment, leg_distance, leg_duration = results[i]
        full_route.extend(segment[1:])
        distance += leg_distance
        duration += leg_duration
    return full_route, distance, duration


def generate_route_map(routes_data, orders_data, output_file=None, lightweight=False):
    if not orders_data:
        return None, []
    load_cache()
    output = Path(output_file) if output_file else Path(config.MAP_OUTPUT_DIR) / "routes_map.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    depot = min(orders_data, key=lambda order: order["id"])
    by_id = {order["id"]: order for order in orders_data}
    map_view = folium.Map(location=[depot["lat"], depot["lng"]], zoom_start=9, tiles=None)
    folium.TileLayer("OpenStreetMap", control=False).add_to(map_view)
    map_view.get_root().header.add_child(folium.Element(
        '<link rel="stylesheet" href="/static/css/map-controls.css">'
    ))
    folium.Marker([depot["lat"], depot["lng"]], tooltip="Depósito central",
                  popup=popup_text(depot["customer_name"]),
                  icon=folium.Icon(color="black", icon="home", prefix="fa")).add_to(map_view)
    colors = ["#2563eb", "#0d9488", "#d97706", "#7c3aed", "#e11d48"]
    stats = []
    for i, route in enumerate(routes_data):
        color = colors[i % len(colors)]
        layer = folium.FeatureGroup(name=f"Vehículo {route['vehicle_id']}").add_to(map_view)
        coords, stops = [], []
        for order_id in route["sequence"]:
            order = by_id.get(order_id)
            if order is None:
                continue
            coord = [order["lat"], order["lng"]]
            coords.append(coord)
            if order_id == depot["id"]:
                continue
            stops.append(order)
            number = len(stops)
            popup = f"Parada {number}" if lightweight else f"{popup_text(order['customer_name'])} · {order['demand']} unidades"
            icon = f'<div style="background:{color};color:white;border-radius:50%;width:28px;height:28px;text-align:center;border:2px solid white;font:600 13px/24px sans-serif">{number}</div>'
            folium.Marker(coord, popup=popup, tooltip=f"Parada {number}",
                          icon=folium.DivIcon(html=icon, icon_anchor=(14, 14))).add_to(layer)
        if len(coords) > 1:
            geometry, distance, duration = get_osrm_route(coords)
            folium.PolyLine(geometry, color=color, weight=4, opacity=0.85,
                            tooltip=f"Vehículo {route['vehicle_id']} · {distance:.1f} km").add_to(layer)
            stats.append({"vehicle_id": route["vehicle_id"], "distance": distance,
                          "duration": duration, "stops": len(stops), "color": color,
                          "demand": sum(order["demand"] for order in stops)})
    folium.LayerControl(collapsed=False).add_to(map_view)
    folium.Element('<div style="position:fixed;bottom:24px;left:12px;z-index:1000;background:white;color:#334155;padding:8px 12px;border-radius:6px;font:12px sans-serif">Trazado vial: OSRM. Si no responde, se unen las paradas en línea recta.</div>').add_to(map_view.get_root().html)
    map_view.fit_bounds(map_view.get_bounds(), padding=(30, 30))
    bounds = json.dumps(map_view.get_bounds())
    name = map_view.get_name()
    map_view.get_root().script.add_child(folium.Element(f"""
        function refitRoutes() {{
            if (typeof {name} !== 'undefined') {{
                {name}.invalidateSize();
                {name}.fitBounds({bounds}, {{padding: [30, 30], animate: false}});
            }}
        }}
        window.addEventListener('resize', refitRoutes);
        window.addEventListener('load', refitRoutes);
    """))
    map_view.save(str(output))
    save_cache()
    return str(output), stats

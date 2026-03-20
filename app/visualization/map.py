import folium
from folium import plugins
from typing import List, Dict
import requests

def get_osrm_route(coords):
    # coords should be list of (lat, lng)
    if len(coords) < 2:
        return coords
        
    # OSRM expects lng,lat
    coords_str = ";".join([f"{lng},{lat}" for lat, lng in coords])
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data['code'] == 'Ok':
                # GeoJSON returns [lng, lat]
                route = data['routes'][0]['geometry']['coordinates']
                # folium expects [lat, lng]
                return [[lat, lng] for lng, lat in route]
    except Exception as e:
        print(f"OSRM Error: {e}")
    
    return coords

def generate_route_map(routes_data: List[Dict], orders_data: List[Dict], output_file: str = "routes_map.html"):
    """
    Genera un mapa HTML de Folium mostrando las rutas conectadas por calles vía OSRM.
    """
    if not orders_data:
        return
        
    depot = next((o for o in orders_data if o['id'] == 1), orders_data[0])
    
    m = folium.Map(location=[depot['lat'], depot['lng']], zoom_start=9)
    
    # Marcador para el depot destacado
    folium.Marker(
        [depot['lat'], depot['lng']], 
        popup='Depot Central', 
        icon=folium.Icon(color='black', icon='home', prefix='fa')
    ).add_to(m)

    colors = ['#3b82f6', '#10b981', '#8b5cf6', '#f59e0b', '#ef4444', '#14b8a6', '#f43f5e', '#6366f1']
    
    # Dibuja rutas
    for i, route in enumerate(routes_data):
        color = colors[i % len(colors)]
        
        sequence = route.get('sequence', [])
        
        stop_coords = []
        stop_number = 1
        for order_id in sequence:
            order = next((o for o in orders_data if o['id'] == order_id), None)
            if not order:
                continue
                
            coord = (order['lat'], order['lng'])
            stop_coords.append(coord)
            
            if order['id'] != depot['id']:
                icon_html = f'''
                <div style="background-color: {color}; color: white; border-radius: 50%; width: 24px; height: 24px; display: flex; justify-content: center; align-items: center; font-weight: bold; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3); font-family: sans-serif; font-size: 12px;">
                    {order['id']}
                </div>
                '''
                
                folium.Marker(
                    coord, 
                    popup=f"Parada {stop_number}<br>Pedido #{order['id']}<br>Vehículo #{route['vehicle_id']}", 
                    icon=folium.DivIcon(html=icon_html, icon_anchor=(12,12))
                ).add_to(m)
                stop_number += 1
                
        # Fetch actual street route via OSRM
        real_route_coords = get_osrm_route(stop_coords)
                
        # Dibuja las lineas animadas con flechas sobre el camino real
        plugins.AntPath(
            locations=real_route_coords,
            delay=1000,
            dash_array=[10, 20],
            color=color,
            pulse_color='#FFFFFF',
            weight=5,
            opacity=0.8,
            tooltip=f"Ruta Vehículo #{route['vehicle_id']}"
        ).add_to(m)
        
    m.save(output_file)
    print(f"Map saved to {output_file}")
    
    return output_file


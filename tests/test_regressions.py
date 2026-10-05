"""Regression coverage for constraints, mutation safety and map geometry."""
import json
import csv
import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.db import models
from app.main import RATE_LIMIT, request_times
from app.vrp.solver import solve_vrp
from app.visualization import route_map
from tests.test_api import client, cleanup_db, TestingSessionLocal


def order(name="Destino", demand=10, **values):
    payload = {"customer_name": name, "lat": 18.49, "lng": -69.93,
               "demand": demand, "window_start": 0, "window_end": 1440, **values}
    response = client.post("/api/orders", json=payload)
    assert response.status_code == 200
    return response.json()


def plan():
    depot = order("Depósito", 0, lat=18.48)
    stop = order()
    vehicle = client.post("/api/vehicles", json={"name": "Camión", "capacity": 100}).json()
    response = client.post("/api/routes/generate")
    assert response.status_code == 200
    return depot, stop, vehicle


@pytest.mark.parametrize("change", [{"window_start": 100, "window_end": 50},
                                   {"demand": None}, {"customer_name": "   "},
                                   {"lat": None}, {"window_end": 0, "window_start": 1}])
def test_invalid_order_update_is_atomic(change):
    original = order()
    response = client.put(f"/api/orders/{original['id']}", json=change)
    assert response.status_code == 422
    assert client.get("/api/orders").json() == [original]


def test_partial_window_update_checks_existing_values():
    original = order(window_start=100, window_end=200)
    assert client.put(f"/api/orders/{original['id']}", json={"window_end": 50}).status_code == 422


@pytest.mark.parametrize("change", [{"name": "   "}, {"capacity": None}, {"name": None}])
def test_invalid_vehicle_update(change):
    vehicle = client.post("/api/vehicles", json={"name": "Camión", "capacity": 10}).json()
    assert client.put(f"/api/vehicles/{vehicle['id']}", json=change).status_code == 422
    assert client.get("/api/vehicles").json() == [vehicle]


def test_names_allow_business_punctuation_and_escape_in_map(monkeypatch, tmp_path):
    depot = order('Depósito & Cía.', 0)
    stop = order('<img src=x onerror=alert(1)>')
    client.post("/api/vehicles", json={"name": "Camión", "capacity": 100})
    assert client.post('/api/routes/generate').status_code == 200
    monkeypatch.setattr(route_map, 'CACHE_FILE', str(tmp_path / 'cache.json'))
    monkeypatch.setattr(route_map, 'get_osrm_route', lambda coords: (coords, 1, 2))
    response = client.get('/api/routes/map')
    assert response.status_code == 200
    assert '&lt;img' in response.text
    assert '<img src=x' not in response.text
    assert 'Vehículo' in response.text


@pytest.mark.parametrize("kind", ['new_order', 'edit_order', 'delete_order', 'new_vehicle', 'edit_vehicle', 'delete_vehicle'])
def test_mutations_invalidate_old_routes(kind):
    _, stop, vehicle = plan()
    if kind == 'new_order': order('Otro destino')
    elif kind == 'edit_order': client.put(f"/api/orders/{stop['id']}", json={"demand": 20})
    elif kind == 'delete_order': client.delete(f"/api/orders/{stop['id']}")
    elif kind == 'new_vehicle': client.post('/api/vehicles', json={"name": "Otro camión", "capacity": 50})
    elif kind == 'edit_vehicle': client.put(f"/api/vehicles/{vehicle['id']}", json={"capacity": 50})
    else: client.delete(f"/api/vehicles/{vehicle['id']}")
    assert client.get('/api/routes').json() == []


def test_failed_update_preserves_plan():
    _, stop, _ = plan()
    original = client.get('/api/routes').json()
    assert client.put(f"/api/orders/{stop['id']}", json={"window_start": 1440, "window_end": 0}).status_code == 422
    assert client.get('/api/routes').json() == original


def test_analytics_with_non_one_depot_id():
    with TestingSessionLocal() as db:
        db.add_all([models.Order(id=10, customer_name='Depósito', lat=18.48, lng=-69.93, demand=0, window_start=0, window_end=1440),
                    models.Order(id=20, customer_name='Entrega', lat=18.49, lng=-69.93, demand=10, window_start=0, window_end=1440),
                    models.Vehicle(id=7, name='Camión', capacity=100),
                    models.Route(vehicle_id=7, route_sequence='[10,20,10]', total_distance=2, total_time=20)])
        db.commit()
    result = client.get('/api/routes/analytics').json()
    assert result['summary']['total_stops'] == 1
    assert result['summary']['total_demand'] == 10


def test_rate_limit_returns_429_and_static_remains_available():
    for _ in range(RATE_LIMIT): assert client.get('/api/health').status_code == 200
    response = client.get('/api/health')
    assert response.status_code == 429
    assert response.headers['Retry-After'] == '60'
    assert client.get('/static/index.html').status_code == 200


def test_impossible_plan_does_not_drop_orders():
    order('Depósito', 0)
    order(demand=101)
    client.post('/api/vehicles', json={"name": "Camión", "capacity": 100})
    assert client.post('/api/routes/generate').status_code == 400
    assert client.get('/api/routes').json() == []


def test_time_constraint_cannot_silently_drop_stop():
    orders = [SimpleNamespace(id=5, lat=18.48, lng=-69.93, demand=0, window_start=0, window_end=1440),
              SimpleNamespace(id=6, lat=19.48, lng=-70.93, demand=1, window_start=0, window_end=0)]
    assert solve_vrp(orders, [SimpleNamespace(capacity=100)], time_limit_seconds=1) is None


def test_solver_skips_unused_vehicles_and_includes_waiting():
    orders = [SimpleNamespace(id=5, lat=18.48, lng=-69.93, demand=0, window_start=0, window_end=1000),
              SimpleNamespace(id=6, lat=18.49, lng=-69.93, demand=1, window_start=500, window_end=600)]
    routes = solve_vrp(orders, [SimpleNamespace(capacity=100), SimpleNamespace(capacity=100)], time_limit_seconds=1)
    assert len(routes) == 1
    assert routes[0]['sequence'] == [5, 6, 5]
    assert routes[0]['time_mins'] >= 500


def test_cache_and_fresh_segments_keep_geographic_order(monkeypatch):
    coords = [[1, 2], [2, 3], [3, 4], [4, 5]]
    key = str(tuple(round(x, 6) for x in (*coords[1], *coords[2])))
    monkeypatch.setattr(route_map, 'route_cache', {key: ([coords[1], [2.5, 3.5], coords[2]], 2, 4)})
    monkeypatch.setattr(route_map, '_fetch_osrm_segment', lambda start, end, key: ([start, end], 1, 2))
    geometry, distance, duration = route_map.get_osrm_route(coords)
    assert geometry == [coords[0], coords[1], [2.5, 3.5], coords[2], coords[3]]
    assert (distance, duration) == (4, 8)


def test_osrm_failure_uses_nonzero_estimate(monkeypatch):
    monkeypatch.setattr(route_map.requests, 'get', Mock(side_effect=route_map.requests.Timeout))
    segment, distance, duration = route_map._fetch_osrm_segment([18.48, -69.93], [18.49, -69.93], 'test')
    assert len(segment) == 2 and distance > 0 and duration > 0


def transfer_setup(capacity=100):
    with TestingSessionLocal() as db:
        db.add_all([models.Order(id=10, customer_name='Depósito', lat=18.48, lng=-69.93, demand=0, window_start=0, window_end=1440),
                    models.Order(id=20, customer_name='A', lat=18.49, lng=-69.93, demand=10, window_start=0, window_end=1440),
                    models.Order(id=30, customer_name='B', lat=18.50, lng=-69.93, demand=10, window_start=0, window_end=1440),
                    models.Vehicle(id=1, name='Camión A', capacity=100), models.Vehicle(id=2, name='Camión B', capacity=capacity),
                    models.Route(vehicle_id=1, route_sequence='[10,20,10]', total_distance=2, total_time=20),
                    models.Route(vehicle_id=2, route_sequence='[10,30,10]', total_distance=3, total_time=30)])
        db.commit()


def test_transfer_recalculates_metrics_and_preserves_depot():
    transfer_setup()
    response = client.post('/api/routes/swap-stops', json={"from_vehicle": 1, "to_vehicle": 2, "stop_id": 20})
    assert response.status_code == 200
    routes = client.get('/api/routes').json()
    assert len(routes) == 1
    assert json.loads(routes[0]['route_sequence']) == [10, 30, 20, 10]
    assert routes[0]['total_distance'] != 3


@pytest.mark.parametrize('transfer', [{"from_vehicle": 1, "to_vehicle": 1, "stop_id": 20}, {"from_vehicle": 1, "to_vehicle": 2, "stop_id": 10}, {"from_vehicle": 1, "to_vehicle": 2, "stop_id": 999}])
def test_invalid_transfer_preserves_routes(transfer):
    transfer_setup()
    original = client.get('/api/routes').json()
    assert client.post('/api/routes/swap-stops', json=transfer).status_code == 400
    assert client.get('/api/routes').json() == original


def test_transfer_capacity_rejected_atomically():
    transfer_setup(capacity=15)
    original = client.get('/api/routes').json()
    assert client.post('/api/routes/swap-stops', json={"from_vehicle": 1, "to_vehicle": 2, "stop_id": 20}).status_code == 400
    assert client.get('/api/routes').json() == original


def test_transfer_time_window_rejected_atomically():
    transfer_setup()
    with TestingSessionLocal() as db:
        db.get(models.Order, 20).window_end = 10
        db.get(models.Order, 30).window_start = 100
        db.commit()
    original = client.get('/api/routes').json()
    assert client.post('/api/routes/swap-stops', json={"from_vehicle": 1, "to_vehicle": 2, "stop_id": 20}).status_code == 400
    assert client.get('/api/routes').json() == original


def test_concurrent_mutation_is_rejected():
    from app.api.routes import mutation_lock
    with mutation_lock:
        response = client.post('/api/vehicles', json={"name": "Camión", "capacity": 100})
    assert response.status_code == 409
    assert client.get('/api/vehicles').json() == []


def test_demo_can_plan_every_delivery(monkeypatch):
    from app.config import config
    monkeypatch.setattr(config, 'VRP_TIME_LIMIT_SECONDS', 5)
    assert client.post('/api/seed').status_code == 200
    response = client.post('/api/routes/generate')
    assert response.status_code == 200
    orders = client.get('/api/orders').json()
    expected = {o['id'] for o in orders[1:]}
    sequences = [r['sequence'] for r in response.json()['routes']]
    assigned = [stop for sequence in sequences for stop in sequence[1:-1]]
    assert set(assigned) == expected and len(assigned) == len(expected)


def test_eta_extrapolation_and_zero_distance():
    from app.ml.eta_model import ETAPredictor
    predictor = ETAPredictor()
    predictor.model = Mock()
    assert predictor.predict_eta(0) == 0
    assert predictor.predict_eta(200) == 505
    predictor.model.predict.assert_not_called()


def test_popup_escapes_javascript_template_syntax():
    assert route_map.popup_text('${alert(1)}`<img>') == '&#36;{alert(1)}&#96;&lt;img&gt;'


def test_create_rejects_invalid_and_default_time_windows():
    payload = {"customer_name": "Destino", "lat": 18.5, "lng": -69.9, "demand": 1,
               "window_start": 500, "window_end": 400}
    assert client.post('/api/orders', json=payload).status_code == 422
    payload.pop('window_end')
    response = client.post('/api/orders', json=payload)
    assert response.status_code == 200 and response.json()['window_end'] == 1440


def test_csv_export_contains_metrics_and_escapes_formula():
    plan()
    with TestingSessionLocal() as db:
        db.query(models.Vehicle).first().name = '=HYPERLINK("bad")'
        db.commit()
    response = client.get('/api/routes/export')
    assert response.status_code == 200
    assert 'attachment' in response.headers['Content-Disposition']
    rows = list(csv.reader(io.StringIO(response.text.lstrip('\ufeff'))))
    assert len(rows) == 2
    assert rows[1][1].startswith("'=")
    assert 'Depósito → Destino → Depósito' in rows[1][2]
    assert float(rows[1][4]) > 0


def test_csv_export_requires_routes():
    assert client.get('/api/routes/export').status_code == 400

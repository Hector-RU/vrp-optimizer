import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.database import Base, get_db

SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

client = TestClient(app)

@pytest.fixture(autouse=True)
def cleanup_db(monkeypatch):
    from app.db import models
    from app.main import request_times
    from app.config import config
    request_times.clear()
    monkeypatch.setattr(config, "VRP_TIME_LIMIT_SECONDS", 1)
    app.dependency_overrides[get_db] = override_get_db
    db = TestingSessionLocal()
    db.query(models.Route).delete()
    db.query(models.Order).delete()
    db.query(models.Vehicle).delete()
    db.commit()
    db.close()
    yield
    app.dependency_overrides.clear()
    request_times.clear()

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200

def test_create_order_valid():
    response = client.post("/api/orders", json={
        "customer_name": "Test Client",
        "lat": 40.7128,
        "lng": -74.0060,
        "demand": 10,
        "window_start": 0,
        "window_end": 1440
    })
    assert response.status_code == 200
    data = response.json()
    assert data["customer_name"] == "Test Client"
    assert data["lat"] == 40.7128

def test_create_order_invalid_lat():
    response = client.post("/api/orders", json={
        "customer_name": "Test", "lat": 100, "lng": -74, "demand": 10, "window_start": 0, "window_end": 1440
    })
    assert response.status_code == 422

def test_create_order_negative_demand():
    response = client.post("/api/orders", json={
        "customer_name": "Test", "lat": 40.7, "lng": -74, "demand": -5, "window_start": 0, "window_end": 1440
    })
    assert response.status_code == 422

def test_create_vehicle_valid():
    response = client.post("/api/vehicles", json={"name": "Van Test", "capacity": 50})
    assert response.status_code == 200
    assert response.json()["capacity"] == 50

def test_create_vehicle_invalid_capacity():
    response = client.post("/api/vehicles", json={"name": "Van", "capacity": 0})
    assert response.status_code == 422

def test_get_orders_pagination():
    for i in range(5):
        client.post("/api/orders", json={
            "customer_name": f"Client {i}", "lat": 40.7 + i*0.01, "lng": -74 + i*0.01,
            "demand": 10, "window_start": 0, "window_end": 1440
        })

    response = client.get("/api/orders?skip=0&limit=2")
    assert response.status_code == 200
    assert len(response.json()) == 2

def test_search_orders():
    client.post("/api/orders", json={"customer_name": "Santiago Tests", "lat": 40.7, "lng": -74, "demand": 10, "window_start": 0, "window_end": 1440})
    client.post("/api/orders", json={"customer_name": "Puerto Plata", "lat": 40.8, "lng": -74.1, "demand": 5, "window_start": 0, "window_end": 1440})

    response = client.get("/api/orders?search=Santiago")
    assert response.status_code == 200
    assert any("Santiago" in o["customer_name"] for o in response.json())

def test_generate_routes():
    client.post("/api/orders", json={"customer_name": "Depot", "lat": 40.7128, "lng": -74.0060, "demand": 0, "window_start": 0, "window_end": 1440})
    client.post("/api/orders", json={"customer_name": "C1", "lat": 40.72, "lng": -74.01, "demand": 10, "window_start": 0, "window_end": 1440})
    client.post("/api/vehicles", json={"name": "Van 1", "capacity": 100})

    response = client.post("/api/routes/generate")
    assert response.status_code == 200
    assert "Routes generated successfully" in response.json()["message"]

def test_generate_routes_no_orders():
    response = client.post("/api/routes/generate")
    assert response.status_code == 400

def test_generate_routes_no_vehicles():
    client.post("/api/orders", json={"customer_name": "Test", "lat": 40.7, "lng": -74, "demand": 10, "window_start": 0, "window_end": 1440})
    response = client.post("/api/routes/generate")
    assert response.status_code == 400

def test_update_order():
    create_resp = client.post("/api/orders", json={
        "customer_name": "Original", "lat": 40.7, "lng": -74, "demand": 10, "window_start": 0, "window_end": 1440
    })
    order_id = create_resp.json()["id"]

    response = client.put(f"/api/orders/{order_id}", json={"demand": 25})
    assert response.status_code == 200
    assert response.json()["demand"] == 25

def test_delete_order():
    create_resp = client.post("/api/orders", json={
        "customer_name": "To Delete", "lat": 40.7, "lng": -74, "demand": 10, "window_start": 0, "window_end": 1440
    })
    order_id = create_resp.json()["id"]

    response = client.delete(f"/api/orders/{order_id}")
    assert response.status_code == 200

    get_resp = client.get("/api/orders")
    assert not any(o["id"] == order_id for o in get_resp.json())

def test_delete_nonexistent_order():
    response = client.delete("/api/orders/9999")
    assert response.status_code == 404

def test_seed_data():
    response = client.post("/api/seed")
    assert response.status_code == 200

    orders = client.get("/api/orders").json()
    assert len(orders) > 0

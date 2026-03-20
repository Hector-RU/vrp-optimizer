import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.database import Base, get_db
import json

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def test_read_main():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to VRP Optimizer API"}

def test_create_order():
    response = client.post(
        "/api/orders",
        json={"customer_name": "Depot Test", "lat": 40.7128, "lng": -74.0060, "demand": 0, "window_start": 0, "window_end": 1440}
    )
    assert response.status_code == 200
    assert response.json()["customer_name"] == "Depot Test"

def test_create_vehicle():
    response = client.post(
        "/api/vehicles",
        json={"name": "Van Test", "capacity": 50}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Van Test"

def test_generate_routes():
    # Setup some basic orders for routing
    client.post("/api/orders", json={"customer_name": "C1 Test", "lat": 40.720, "lng": -74.010, "demand": 10, "window_start": 0, "window_end": 1440})
    
    response = client.post("/api/routes/generate")
    assert response.status_code == 200
    assert "Routes generated successfully" in response.json()["message"]
    
def test_reroute():
    response = client.post("/api/routes/reroute")
    assert response.status_code == 200
    
def test_map_generation():
    response = client.get("/api/routes/map")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"

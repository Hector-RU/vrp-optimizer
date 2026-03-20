from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import json
import os
from fastapi.responses import FileResponse

from app.db import schemas, models
from app.db.database import get_db
from app.vrp.solver import solve_vrp
from app.visualization.map import generate_route_map

router = APIRouter()

@router.post("/orders", response_model=schemas.Order)
def create_order(order: schemas.OrderCreate, db: Session = Depends(get_db)):
    db_order = models.Order(**order.model_dump())
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

@router.get("/orders", response_model=List[schemas.Order])
def get_orders(db: Session = Depends(get_db)):
    return db.query(models.Order).all()

@router.delete("/orders/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db)):
    db_order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    db.delete(db_order)
    db.commit()
    return {"message": "Order deleted"}


@router.post("/vehicles", response_model=schemas.Vehicle)
def create_vehicle(vehicle: schemas.VehicleCreate, db: Session = Depends(get_db)):
    db_vehicle = models.Vehicle(**vehicle.model_dump())
    db.add(db_vehicle)
    db.commit()
    db.refresh(db_vehicle)
    return db_vehicle

@router.get("/vehicles", response_model=List[schemas.Vehicle])
def get_vehicles(db: Session = Depends(get_db)):
    return db.query(models.Vehicle).all()

@router.delete("/vehicles/{vehicle_id}")
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    db_vehicle = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if not db_vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    db.delete(db_vehicle)
    db.commit()
    return {"message": "Vehicle deleted"}



@router.post("/routes/generate")
def generate_routes(db: Session = Depends(get_db)):
    orders = db.query(models.Order).all()
    vehicles = db.query(models.Vehicle).all()
    
    if not orders:
        raise HTTPException(status_code=400, detail="No orders found to route.")
    if not vehicles:
        raise HTTPException(status_code=400, detail="No vehicles available.")

    # Sort orders by ID. Assuming depot is the first order (id=1 or minimum id)
    orders = sorted(orders, key=lambda x: x.id)

    routes = solve_vrp(orders, vehicles)
    
    if routes is None:
         raise HTTPException(status_code=400, detail="Could not find a feasible solution for the given constraints.")

    # Save to db
    saved_routes = []
    # clean old routes
    db.query(models.Route).delete()
    
    for r in routes:
        vehicle_entity = vehicles[r["vehicle_id"]]
        db_route = models.Route(
            vehicle_id=vehicle_entity.id,
            total_distance=r["distance_km"],
            total_time=r["time_mins"],
            route_sequence=json.dumps(r["sequence"])
        )
        db.add(db_route)
        saved_routes.append(db_route)
    
    db.commit()
    for sr in saved_routes:
        db.refresh(sr)
        
    return {"message": "Routes generated successfully", "routes": [
        {"id": sr.id, "vehicle_id": sr.vehicle_id, "distance_km": sr.total_distance, "time_mins": sr.total_time, "sequence": json.loads(sr.route_sequence)} 
        for sr in saved_routes
    ]}

@router.get("/routes", response_model=List[schemas.Route])
def get_routes(db: Session = Depends(get_db)):
    return db.query(models.Route).all()


@router.get("/routes/map")
def get_routes_map(db: Session = Depends(get_db)):
    routes = db.query(models.Route).all()
    orders = db.query(models.Order).all()
    
    if not routes or not orders:
        raise HTTPException(status_code=400, detail="No routes or orders found. Generate routes first.")
        
    orders_data = [{"id": o.id, "lat": o.lat, "lng": o.lng, "customer_name": o.customer_name} for o in orders]
    routes_data = [{"vehicle_id": r.vehicle_id, "sequence": json.loads(r.route_sequence)} for r in routes]
    
    map_file = "routes_map.html"
    generate_route_map(routes_data, orders_data, output_file=map_file)
    
    if os.path.exists(map_file):
        return FileResponse(map_file)
    else:
         raise HTTPException(status_code=500, detail="Error generating map")

@router.post("/routes/reroute")
def reroute_orders(db: Session = Depends(get_db)):
    # Simple re-route just re-generates everything for this prototype
    return generate_routes(db)


@router.post("/seed")
def seed_data(db: Session = Depends(get_db)):
    db.query(models.Route).delete()
    db.query(models.Order).delete()
    db.query(models.Vehicle).delete()
    
    # 20+ Orders en República Dominicana (Santo Domingo y cercanías)
    rd_orders = [
        {"customer_name": "Depot Santo Domingo", "lat": 18.4861, "lng": -69.9312, "demand": 0, "window_start": 0, "window_end": 1440},
        {"customer_name": "Santiago", "lat": 19.4582, "lng": -70.6627, "demand": 15, "window_start": 0, "window_end": 480},
        {"customer_name": "Puerto Plata", "lat": 19.7808, "lng": -70.6871, "demand": 10, "window_start": 60, "window_end": 500},
        {"customer_name": "Punta Cana", "lat": 18.5820, "lng": -68.4055, "demand": 20, "window_start": 120, "window_end": 600},
        {"customer_name": "La Romana", "lat": 18.4273, "lng": -68.9728, "demand": 5, "window_start": 0, "window_end": 300},
        {"customer_name": "San Pedro de Macorís", "lat": 18.4616, "lng": -69.2968, "demand": 25, "window_start": 120, "window_end": 720},
        {"customer_name": "La Vega", "lat": 19.2221, "lng": -70.5296, "demand": 12, "window_start": 0, "window_end": 1440},
        {"customer_name": "Bonao", "lat": 18.9350, "lng": -70.4092, "demand": 8, "window_start": 300, "window_end": 800},
        {"customer_name": "San Cristóbal", "lat": 18.4167, "lng": -70.1000, "demand": 14, "window_start": 0, "window_end": 600},
        {"customer_name": "Baní", "lat": 18.2796, "lng": -70.3318, "demand": 18, "window_start": 0, "window_end": 1440},
        {"customer_name": "Azua", "lat": 18.4532, "lng": -70.7349, "demand": 6, "window_start": 60, "window_end": 240},
        {"customer_name": "Barahona", "lat": 18.2105, "lng": -71.1008, "demand": 22, "window_start": 100, "window_end": 900},
        {"customer_name": "San Juan", "lat": 18.8059, "lng": -71.2299, "demand": 30, "window_start": 0, "window_end": 1440},
        {"customer_name": "Higüey", "lat": 18.6150, "lng": -68.7070, "demand": 40, "window_start": 120, "window_end": 1440},
        {"customer_name": "Samaná", "lat": 19.2056, "lng": -69.3369, "demand": 16, "window_start": 0, "window_end": 1440},
        {"customer_name": "Mao", "lat": 19.5519, "lng": -71.0781, "demand": 25, "window_start": 0, "window_end": 1440},
        {"customer_name": "Dajabón", "lat": 19.5514, "lng": -71.7081, "demand": 10, "window_start": 0, "window_end": 1440},
        {"customer_name": "Monte Cristi", "lat": 19.8483, "lng": -71.6459, "demand": 30, "window_start": 120, "window_end": 1000},
        {"customer_name": "Moca", "lat": 19.3904, "lng": -70.5259, "demand": 15, "window_start": 200, "window_end": 1200},
        {"customer_name": "Cotuí", "lat": 19.0527, "lng": -70.1492, "demand": 10, "window_start": 0, "window_end": 1440},
        {"customer_name": "Hato Mayor", "lat": 18.7628, "lng": -69.2568, "demand": 45, "window_start": 0, "window_end": 1440}
    ]
    
    rd_vehicles = [
        {"name": "Camión Furgón 1", "capacity": 150},
        {"name": "Camión Furgón 2", "capacity": 200},
        {"name": "Camioneta Carga 1", "capacity": 120},
        {"name": "Camioneta Carga 2", "capacity": 120}
    ]
    
    for od in rd_orders:
        db.add(models.Order(**od))
    for vd in rd_vehicles:
        db.add(models.Vehicle(**vd))
        
    db.commit()
    return {"message": "Data de prueba en República Dominicana generada exitosamente."}


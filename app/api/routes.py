from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional
import json
import csv
import io
import tempfile
from pathlib import Path
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError
from functools import wraps
from threading import RLock

from app.db import schemas, models
from app.db.database import get_db
from app.vrp.solver import solve_vrp, haversine, eta_predictor
from app.visualization.route_map import generate_route_map
from app.logging import logger

router = APIRouter()
mutation_lock = RLock()


def serialized_mutation(function):
    """Keep planning snapshots consistent with changes from other clients."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        if not mutation_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="Hay una operación en curso. Inténtalo al finalizar.")
        try:
            return function(*args, **kwargs)
        finally:
            mutation_lock.release()
    return wrapped

@router.post("/orders", response_model=schemas.Order)
@serialized_mutation
def create_order(order: schemas.OrderCreate, db: Session = Depends(get_db)):
    db_order = models.Order(**order.model_dump())
    db.query(models.Route).delete()
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

@router.get("/orders", response_model=List[schemas.Order])
def get_orders(
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    search: Optional[str] = Query(default=None)
):
    query = db.query(models.Order)
    if search:
        query = query.filter(models.Order.customer_name.ilike(f"%{search}%"))
    return query.order_by(models.Order.id).offset(skip).limit(limit).all()

@router.get("/orders/count")
def get_orders_count(db: Session = Depends(get_db)):
    return {"total": db.query(models.Order).count()}

@router.delete("/orders/{order_id}")
@serialized_mutation
def delete_order(order_id: int, db: Session = Depends(get_db)):
    db_order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    db.query(models.Route).delete()
    db.delete(db_order)
    db.commit()
    return {"message": "Order deleted"}

@router.put("/orders/{order_id}", response_model=schemas.Order)
@serialized_mutation
def update_order(order_id: int, order: schemas.OrderUpdate, db: Session = Depends(get_db)):
    db_order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")

    update_data = order.model_dump(exclude_unset=True)
    try:
        validated = schemas.OrderCreate.model_validate({
            **{key: getattr(db_order, key) for key in schemas.OrderCreate.model_fields},
            **update_data,
        })
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.query(models.Route).delete()
    for key, value in validated.model_dump().items():
        setattr(db_order, key, value)

    db.commit()
    db.refresh(db_order)
    return db_order


@router.post("/vehicles", response_model=schemas.Vehicle)
@serialized_mutation
def create_vehicle(vehicle: schemas.VehicleCreate, db: Session = Depends(get_db)):
    db_vehicle = models.Vehicle(**vehicle.model_dump())
    db.query(models.Route).delete()
    db.add(db_vehicle)
    db.commit()
    db.refresh(db_vehicle)
    return db_vehicle

@router.get("/vehicles", response_model=List[schemas.Vehicle])
def get_vehicles(
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500)
):
    return db.query(models.Vehicle).order_by(models.Vehicle.id).offset(skip).limit(limit).all()

@router.delete("/vehicles/{vehicle_id}")
@serialized_mutation
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    db_vehicle = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if not db_vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    db.query(models.Route).delete()
    db.delete(db_vehicle)
    db.commit()
    return {"message": "Vehicle deleted"}

@router.put("/vehicles/{vehicle_id}", response_model=schemas.Vehicle)
@serialized_mutation
def update_vehicle(vehicle_id: int, vehicle: schemas.VehicleUpdate, db: Session = Depends(get_db)):
    db_vehicle = db.query(models.Vehicle).filter(models.Vehicle.id == vehicle_id).first()
    if not db_vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    update_data = vehicle.model_dump(exclude_unset=True)
    try:
        validated = schemas.VehicleCreate.model_validate({
            "name": db_vehicle.name, "capacity": db_vehicle.capacity, **update_data,
        })
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.query(models.Route).delete()
    for key, value in validated.model_dump().items():
        setattr(db_vehicle, key, value)

    db.commit()
    db.refresh(db_vehicle)
    return db_vehicle



@router.post("/routes/generate")
@serialized_mutation
def generate_routes(db: Session = Depends(get_db)):
    orders = db.query(models.Order).order_by(models.Order.id).all()
    vehicles = db.query(models.Vehicle).all()

    if not orders:
        raise HTTPException(status_code=400, detail="No orders found to route.")
    if not vehicles:
        raise HTTPException(status_code=400, detail="No vehicles available.")

    if len(orders) < 2 or orders[0].demand != 0:
        raise HTTPException(status_code=400, detail="El primer pedido debe ser el depósito, con demanda 0, seguido de al menos una entrega.")
    if sum(o.demand for o in orders) > sum(v.capacity for v in vehicles):
        raise HTTPException(status_code=400, detail="La demanda supera la capacidad total de la flota.")

    logger.info(f"Starting VRP solve with {len(orders)} orders and {len(vehicles)} vehicles")

    routes = solve_vrp(orders, vehicles)

    if routes is None:
        logger.error("VRP solver could not find feasible solution")
        raise HTTPException(status_code=400, detail="Could not find a feasible solution for the given constraints.")

    try:
        db.query(models.Route).delete()
        db.flush()

        saved_routes = []
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

        logger.info(f"Successfully generated {len(saved_routes)} routes")

        return {"message": "Routes generated successfully", "routes": [
            {"id": sr.id, "vehicle_id": sr.vehicle_id, "distance_km": sr.total_distance, "time_mins": sr.total_time, "sequence": json.loads(sr.route_sequence)}
            for sr in saved_routes
        ]}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error during route generation: {e}")
        raise HTTPException(status_code=500, detail="Database error during route generation")

@router.get("/routes", response_model=List[schemas.Route])
def get_routes(db: Session = Depends(get_db)):
    return db.query(models.Route).all()


@router.get("/routes/export")
def export_routes(db: Session = Depends(get_db)):
    routes = db.query(models.Route).order_by(models.Route.id).all()
    if not routes:
        raise HTTPException(status_code=400, detail="Genera rutas antes de exportar.")
    orders = {o.id: o.customer_name for o in db.query(models.Order).all()}
    vehicles = {v.id: v.name for v in db.query(models.Vehicle).all()}

    def safe_text(value):
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Ruta", "Vehículo", "Secuencia de destinos", "Distancia estimada (km)", "Duración estimada (min)"])
    for route in routes:
        names = " → ".join(orders.get(i, f"#{i}") for i in json.loads(route.route_sequence))
        writer.writerow([route.id, safe_text(vehicles.get(route.vehicle_id, f"#{route.vehicle_id}")),
                         safe_text(names), route.total_distance, route.total_time])
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="planificacion-rutas.csv"',
                             "Cache-Control": "no-store"})


@router.get("/routes/map")
def get_routes_map(db: Session = Depends(get_db), lightweight: bool = Query(default=False)):
    """Obtiene el mapa de rutas. lightweight=true para carga más rápida"""
    routes = db.query(models.Route).all()
    orders = db.query(models.Order).order_by(models.Order.id).all()

    if not routes or not orders:
        raise HTTPException(status_code=400, detail="No routes or orders found. Generate routes first.")

    orders_data = [{"id": o.id, "lat": o.lat, "lng": o.lng, "customer_name": o.customer_name, "demand": o.demand} for o in orders]
    routes_data = [{"vehicle_id": r.vehicle_id, "sequence": json.loads(r.route_sequence)} for r in routes]

    # Each request owns its output: concurrent maps cannot overwrite one another.
    with tempfile.TemporaryDirectory() as directory:
        map_file, _ = generate_route_map(
            routes_data, orders_data, output_file=str(Path(directory) / "map.html"),
            lightweight=lightweight,
        )
        return HTMLResponse(Path(map_file).read_text(encoding="utf-8"),
                            headers={"Cache-Control": "no-store"})

@router.get("/routes/analytics")
def get_routes_analytics(db: Session = Depends(get_db)):
    """Obtiene análisis detallado de las rutas - para el panel de cargas"""
    routes = db.query(models.Route).all()
    orders = db.query(models.Order).order_by(models.Order.id).all()
    vehicles = db.query(models.Vehicle).all()

    if not routes or not orders:
        raise HTTPException(status_code=400, detail="No routes or orders found.")

    analytics = []
    total_demand = 0
    total_capacity = 0

    for route in routes:
        vehicle = next((v for v in vehicles if v.id == route.vehicle_id), None)
        if not vehicle:
            continue

        sequence = json.loads(route.route_sequence)
        route_demand = 0
        route_stops = 0

        for order_id in sequence:
            order = next((o for o in orders if o.id == order_id), None)
            if order and order.id != orders[0].id:
                route_demand += order.demand
                route_stops += 1

        total_demand += route_demand
        total_capacity += vehicle.capacity

        capacity_percentage = (route_demand / vehicle.capacity * 100) if vehicle.capacity > 0 else 0

        analytics.append({
            'vehicle_id': vehicle.id,
            'vehicle_name': vehicle.name,
            'capacity': vehicle.capacity,
            'current_demand': route_demand,
            'capacity_percentage': round(capacity_percentage, 2),
            'num_stops': route_stops,
            'total_distance': route.total_distance,
            'total_time_minutes': route.total_time
        })

    return {
        'routes': analytics,
        'summary': {
            'total_vehicles': len(analytics),
            'total_stops': sum(r['num_stops'] for r in analytics),
            'total_demand': total_demand,
            'total_capacity': total_capacity,
            'average_capacity_usage': round((total_demand / total_capacity * 100) if total_capacity > 0 else 0, 2),
            'total_distance': sum(r['total_distance'] for r in analytics),
            'total_time_hours': round(sum(r['total_time_minutes'] for r in analytics) / 60, 2)
        }
    }

@router.get("/routes/by-vehicle/{vehicle_id}")
def get_routes_by_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    """Obtiene detalles de una ruta específica"""
    route = db.query(models.Route).filter(models.Route.vehicle_id == vehicle_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    orders = db.query(models.Order).order_by(models.Order.id).all()
    sequence = json.loads(route.route_sequence)

    stops = []
    for order_id in sequence:
        order = next((o for o in orders if o.id == order_id), None)
        if order:
            stops.append({
                'id': order.id,
                'name': order.customer_name,
                'lat': order.lat,
                'lng': order.lng,
                'demand': order.demand,
                'window_start': order.window_start,
                'window_end': order.window_end
            })

    return {
        'vehicle_id': vehicle_id,
        'total_distance': route.total_distance,
        'total_time': route.total_time,
        'stops': stops
    }

def evaluate_sequence(sequence, orders, capacity):
    depot = orders[0]
    by_id = {o.id: o for o in orders}
    if not sequence or any(order_id not in by_id for order_id in sequence):
        raise HTTPException(status_code=400, detail="La ruta contiene pedidos que ya no existen. Genera nuevas rutas.")
    if sequence[0] != depot.id or sequence[-1] != depot.id:
        raise HTTPException(status_code=400, detail="La ruta debe salir y regresar al depósito.")
    if sum(by_id[i].demand for i in sequence[1:-1]) > capacity:
        raise HTTPException(status_code=400, detail="La parada supera la capacidad del vehículo de destino.")
    elapsed = depot.window_start
    distance = 0.0
    for previous, current in zip(sequence, sequence[1:]):
        start, end = by_id[previous], by_id[current]
        leg = haversine(start.lat, start.lng, end.lat, end.lng)
        distance += leg
        elapsed = max(elapsed + int(eta_predictor.predict_eta(leg) * 60) / 60,
                      end.window_start)
        if elapsed > end.window_end:
            raise HTTPException(status_code=400, detail="El traslado incumple una ventana de entrega.")
    return distance, elapsed - depot.window_start


@router.post("/routes/swap-stops")
@serialized_mutation
def swap_stops(transfer: schemas.StopTransfer, db: Session = Depends(get_db)):
    if transfer.from_vehicle == transfer.to_vehicle:
        raise HTTPException(status_code=400, detail="Selecciona dos vehículos diferentes.")
    from_route = db.query(models.Route).filter(models.Route.vehicle_id == transfer.from_vehicle).first()
    to_route = db.query(models.Route).filter(models.Route.vehicle_id == transfer.to_vehicle).first()
    if not from_route or not to_route:
        raise HTTPException(status_code=404, detail="Route not found")
    orders = db.query(models.Order).order_by(models.Order.id).all()
    if transfer.stop_id == orders[0].id:
        raise HTTPException(status_code=400, detail="El depósito no se puede mover.")
    source, target = json.loads(from_route.route_sequence), json.loads(to_route.route_sequence)
    if transfer.stop_id not in source[1:-1] or transfer.stop_id in target[1:-1]:
        raise HTTPException(status_code=400, detail="La parada no está disponible en la ruta de origen.")
    source.remove(transfer.stop_id)
    target.insert(len(target) - 1, transfer.stop_id)
    source_vehicle = db.get(models.Vehicle, transfer.from_vehicle)
    target_vehicle = db.get(models.Vehicle, transfer.to_vehicle)
    if not source_vehicle or not target_vehicle:
        raise HTTPException(status_code=400, detail="La ruta contiene vehículos que ya no existen. Genera nuevas rutas.")
    source_metrics = evaluate_sequence(source, orders, source_vehicle.capacity)
    target_metrics = evaluate_sequence(target, orders, target_vehicle.capacity)
    for route, sequence, metrics in ((from_route, source, source_metrics), (to_route, target, target_metrics)):
        route.route_sequence = json.dumps(sequence)
        route.total_distance, route.total_time = metrics
    if len(source) == 2:
        db.delete(from_route)
    db.commit()
    return {"message": "Stop moved successfully", **transfer.model_dump()}

@router.post("/routes/reroute")
def reroute_orders(db: Session = Depends(get_db)):
    # Simple re-route just re-generates everything for this prototype
    return generate_routes(db)


@router.post("/seed")
@serialized_mutation
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


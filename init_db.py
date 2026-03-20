from app.db.database import Base, engine, SessionLocal
from app.db import models

# Crear tablas
Base.metadata.create_all(bind=engine)

def init_db():
    db = SessionLocal()
    
    if db.query(models.Order).count() == 0:
        # Añadir depot
        depot = models.Order(id=1, customer_name="Depot", lat=40.7128, lng=-74.0060, demand=0, window_start=0, window_end=1440)
        
        # Añadir clientes (ej: en NY)
        c1 = models.Order(id=2, customer_name="C1", lat=40.720, lng=-74.010, demand=10, window_start=0, window_end=1440)
        c2 = models.Order(id=3, customer_name="C2", lat=40.730, lng=-73.990, demand=15, window_start=0, window_end=1440)
        c3 = models.Order(id=4, customer_name="C3", lat=40.715, lng=-73.950, demand=20, window_start=0, window_end=1440)
        c4 = models.Order(id=5, customer_name="C4", lat=40.700, lng=-74.015, demand=5, window_start=0, window_end=1440)

        db.add_all([depot, c1, c2, c3, c4])

    if db.query(models.Vehicle).count() == 0:
        v1 = models.Vehicle(id=1, name="Van 1", capacity=25)
        v2 = models.Vehicle(id=2, name="Van 2", capacity=30)
        db.add_all([v1, v2])

    db.commit()
    db.close()
    print("Database initialized with seeded data.")

if __name__ == "__main__":
    init_db()

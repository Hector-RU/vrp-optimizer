from sqlalchemy import Column, Integer, String, Float

from .database import Base

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, index=True)
    lat = Column(Float)
    lng = Column(Float)
    demand = Column(Integer)
    window_start = Column(Integer)
    window_end = Column(Integer)

class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    capacity = Column(Integer)

class Route(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer)
    total_distance = Column(Float)
    total_time = Column(Float)
    route_sequence = Column(String)

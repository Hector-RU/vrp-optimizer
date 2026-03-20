from pydantic import BaseModel
from typing import List, Optional

class OrderBase(BaseModel):
    customer_name: str
    lat: float
    lng: float
    demand: int
    window_start: int
    window_end: int

class OrderCreate(OrderBase):
    pass

class Order(OrderBase):
    id: int

    class Config:
        from_attributes = True

class VehicleBase(BaseModel):
    name: str
    capacity: int

class VehicleCreate(VehicleBase):
    pass

class Vehicle(VehicleBase):
    id: int

    class Config:
        from_attributes = True

class RouteBase(BaseModel):
    vehicle_id: int
    total_distance: float
    total_time: float
    route_sequence: str

class RouteCreate(RouteBase):
    pass

class Route(RouteBase):
    id: int

    class Config:
        from_attributes = True

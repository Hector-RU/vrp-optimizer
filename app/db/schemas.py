from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
import re

class OrderBase(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=100)
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    demand: int = Field(..., ge=0)
    window_start: int = Field(default=0, ge=0, le=1440)
    window_end: int = Field(default=1440, ge=0, le=1440)

    @field_validator('window_end')
    @classmethod
    def validate_window_end(cls, v, info):
        if 'window_start' in info.data and v < info.data['window_start']:
            raise ValueError('window_end must be >= window_start')
        return v

    @field_validator('customer_name')
    @classmethod
    def validate_customer_name(cls, v):
        v = v.strip()
        if not re.match(r'^[\w\s\-áéíóúüñÁÉÍÓÚÜÑ]+$', v):
            raise ValueError('customer_name contains invalid characters')
        return v

class OrderCreate(OrderBase):
    pass

class OrderUpdate(BaseModel):
    customer_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    demand: Optional[int] = Field(default=None, ge=0)
    window_start: Optional[int] = Field(default=None, ge=0, le=1440)
    window_end: Optional[int] = Field(default=None, ge=0, le=1440)

class Order(OrderBase):
    id: int

    class Config:
        from_attributes = True

class VehicleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    capacity: int = Field(..., ge=1, le=10000)

class VehicleCreate(VehicleBase):
    pass

class VehicleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    capacity: Optional[int] = Field(default=None, ge=1, le=10000)

class Vehicle(VehicleBase):
    id: int

    class Config:
        from_attributes = True

class RouteBase(BaseModel):
    vehicle_id: int
    total_distance: float = Field(..., ge=0)
    total_time: float = Field(..., ge=0)
    route_sequence: str

class RouteCreate(RouteBase):
    pass

class Route(RouteBase):
    id: int

    class Config:
        from_attributes = True

class PaginatedResponse(BaseModel):
    items: List
    total: int
    page: int
    page_size: int
    pages: int

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import Optional


class OrderBase(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=100)
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    demand: int = Field(..., ge=0)
    window_start: int = Field(default=0, ge=0, le=1440)
    window_end: int = Field(default=1440, ge=0, le=1440)

    @model_validator(mode="after")
    def validate_window_end(self):
        if self.window_end < self.window_start:
            raise ValueError('window_end must be >= window_start')
        return self

    @field_validator('customer_name')
    @classmethod
    def validate_customer_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('El nombre no puede estar vacío')
        return v

class OrderCreate(OrderBase):
    pass

class UpdateBase(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def reject_null(cls, values):
        if isinstance(values, dict) and any(value is None for value in values.values()):
            raise ValueError("Los campos no pueden ser nulos")
        return values

class OrderUpdate(UpdateBase):
    customer_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    demand: Optional[int] = Field(default=None, ge=0)
    window_start: Optional[int] = Field(default=None, ge=0, le=1440)
    window_end: Optional[int] = Field(default=None, ge=0, le=1440)

class Order(OrderBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

class VehicleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    capacity: int = Field(..., ge=1, le=10000)

    @field_validator('name')
    @classmethod
    def validate_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("El nombre no puede estar vacío")
        return value

class VehicleCreate(VehicleBase):
    pass

class VehicleUpdate(UpdateBase):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    capacity: Optional[int] = Field(default=None, ge=1, le=10000)

class Vehicle(VehicleBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

class RouteBase(BaseModel):
    vehicle_id: int
    total_distance: float = Field(..., ge=0)
    total_time: float = Field(..., ge=0)
    route_sequence: str

class RouteCreate(RouteBase):
    pass

class Route(RouteBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

class StopTransfer(BaseModel):
    from_vehicle: int = Field(gt=0)
    to_vehicle: int = Field(gt=0)
    stop_id: int = Field(gt=0)

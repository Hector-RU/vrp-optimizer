"""Compatibility exports; map generation lives in route_map."""
from .route_map import generate_route_map, get_osrm_route

__all__ = ["generate_route_map", "get_osrm_route"]

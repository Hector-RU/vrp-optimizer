from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import math
from app.ml.eta_model import ETAPredictor
from app.config import config
from app.logging import logger

eta_predictor = ETAPredictor()

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    return distance

def solve_vrp(orders, vehicles, time_limit_seconds: int = None):
    if len(orders) < 2 or not vehicles or orders[0].demand != 0:
        return None
    if sum(o.demand for o in orders) > sum(v.capacity for v in vehicles):
        return None
    num_locations = len(orders)
    num_vehicles = len(vehicles)
    depot_index = 0

    if time_limit_seconds is None:
        time_limit_seconds = config.VRP_TIME_LIMIT_SECONDS

    distance_matrix = []
    time_matrix = []

    for i in range(num_locations):
        dist_row = []
        time_row = []
        for j in range(num_locations):
            if i == j:
                dist_row.append(0)
                time_row.append(0)
            else:
                dist = haversine(orders[i].lat, orders[i].lng, orders[j].lat, orders[j].lng)
                dist_row.append(int(dist * 1000))
                time_mins = eta_predictor.predict_eta(dist)
                time_row.append(int(time_mins * 60))
        distance_matrix.append(dist_row)
        time_matrix.append(time_row)

    demands = [order.demand for order in orders]
    vehicle_capacities = [v.capacity for v in vehicles]

    manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, depot_index)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return demands[from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        vehicle_capacities,
        True,
        'Capacity'
    )

    time_windows = [(o.window_start * 60, o.window_end * 60) if getattr(o, 'window_start', None) is not None else (0, 24*3600) for o in orders]

    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return time_matrix[from_node][to_node]

    time_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.AddDimension(
        time_callback_index,
        24 * 3600,
        24 * 3600,
        False,
        'Time'
    )
    time_dimension = routing.GetDimensionOrDie('Time')
    for location_idx, time_window in enumerate(time_windows):
        if location_idx == depot_index:
            continue
        index = manager.NodeToIndex(location_idx)

        time_dimension.CumulVar(index).SetRange(*time_window)

    for vehicle_id in range(num_vehicles):
        time_dimension.CumulVar(routing.Start(vehicle_id)).SetRange(*time_windows[0])
        time_dimension.CumulVar(routing.End(vehicle_id)).SetRange(*time_windows[0])
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.Start(vehicle_id)))
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.End(vehicle_id)))

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        getattr(routing_enums_pb2.FirstSolutionStrategy, config.VRP_SOLVER_STRATEGY,
                routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION))
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
    search_parameters.time_limit.FromSeconds(time_limit_seconds)

    logger.info(f"Starting VRP solver with {time_limit_seconds}s time limit")
    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        routes = []
        for vehicle_id in range(num_vehicles):
            index = routing.Start(vehicle_id)
            route_sequence = []
            route_distance = 0

            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                route_sequence.append(orders[node_index].id)
                previous_index = index
                index = solution.Value(routing.NextVar(index))
                route_distance += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)

            node_index = manager.IndexToNode(index)
            route_sequence.append(orders[node_index].id)

            if len(route_sequence) <= 2:
                continue
            route_time = (solution.Value(time_dimension.CumulVar(routing.End(vehicle_id)))
                          - solution.Value(time_dimension.CumulVar(routing.Start(vehicle_id))))
            routes.append({
                "vehicle_id": vehicle_id,
                "sequence": route_sequence,
                "distance_km": route_distance / 1000.0,
                "time_mins": route_time / 60.0
            })
        logger.info(f"VRP solved successfully: {len(routes)} routes generated")
        return routes
    else:
        logger.warning("VRP solver could not find a solution")
        return None

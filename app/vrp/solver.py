from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import math
from app.ml.eta_model import ETAPredictor

eta_predictor = ETAPredictor()

def haversine(lat1, lon1, lat2, lon2):
    # Radius of earth in km
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    return distance

def solve_vrp(orders, vehicles):
    """
    Solves VRP for the given orders and vehicles.
    Assumes orders[0] is the depot.
    """
    num_locations = len(orders)
    num_vehicles = len(vehicles)
    depot_index = 0
    
    # Create distance and time matrices
    # For now, distance matrix is used for costs, but time matrix could be used instead.
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
                dist_row.append(int(dist * 1000)) # in meters
                # predict time
                time_mins = eta_predictor.predict_eta(dist)
                time_row.append(int(time_mins * 60)) # in seconds
        distance_matrix.append(dist_row)
        time_matrix.append(time_row)
    
    demands = [order.demand for order in orders]
    # If capacity is 0, we treat it as infinite capacity
    vehicle_capacities = [v.capacity if v.capacity > 0 else 1000000 for v in vehicles]
    
    # Or-Tools setup
    manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, depot_index)
    routing = pywrapcp.RoutingModel(manager)
    
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
    
    # Capacity constraint
    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return demands[from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # null capacity slack
        vehicle_capacities,  # vehicle maximum capacities
        True,  # start cumul to zero
        'Capacity'
    )
    
    # Time Windows Constraint
    # Assuming orders have window_start and window_end in minutes
    time_windows = [(o.window_start * 60, o.window_end * 60) if getattr(o, 'window_start', None) is not None else (0, 24*3600) for o in orders]
    
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        # Service time + transit time. Service time assumed 0 for simplification here.
        return time_matrix[from_node][to_node]

    time_callback_index = routing.RegisterTransitCallback(time_callback)
    # Add Time dimension
    routing.AddDimension(
        time_callback_index,
        24 * 3600,  # allow waiting time (24 hours instead of 1 hour)
        24 * 3600,  # maximum time per vehicle
        False,  # Don't force start cumul to zero (though depot starts at 0 anyway)
        'Time'
    )
    time_dimension = routing.GetDimensionOrDie('Time')
    # Add time window constraints for each location except depot
    for location_idx, time_window in enumerate(time_windows):
        if location_idx == depot_index:
            continue
        index = manager.NodeToIndex(location_idx)
        
        # If window_end is 0, we treat it as no time window limit
        window_end = time_window[1]
        if window_end == 0:
            window_end = 24 * 3600
            
        time_dimension.CumulVar(index).SetRange(time_window[0], window_end)

    # Allow dropping nodes
    penalty = 10000000  # A large penalty to discourage dropping unless necessary
    for node in range(1, num_locations):
        routing.AddDisjunction([manager.NodeToIndex(node)], penalty)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
    search_parameters.time_limit.FromSeconds(5)

    solution = routing.SolveWithParameters(search_parameters)
    
    if solution:
        routes = []
        for vehicle_id in range(num_vehicles):
            index = routing.Start(vehicle_id)
            route_sequence = []
            route_distance = 0
            route_time = 0
            
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                route_sequence.append(orders[node_index].id)
                previous_index = index
                index = solution.Value(routing.NextVar(index))
                route_distance += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
                route_time += time_callback(previous_index, index)
                
            node_index = manager.IndexToNode(index)
            route_sequence.append(orders[node_index].id)
            
            routes.append({
                "vehicle_id": vehicle_id,
                "sequence": route_sequence,
                "distance_km": route_distance / 1000.0,
                "time_mins": route_time / 60.0
            })
        return routes
    else:
        return None

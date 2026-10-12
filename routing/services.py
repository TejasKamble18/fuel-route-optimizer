"""One route request end to end: geocode, route, corridor, optimise, cache."""
import hashlib
from dataclasses import asdict

from django.conf import settings
from django.core.cache import cache

from .corridor import stations_along_route
from .geocoding import Location, geocode, get_place_index
from .optimizer import FuelStation, plan_fuel_stops
from .ors_client import ORSClient
from .stations import get_station_index

GEO_CACHE_SECONDS = 7 * 24 * 3600


def get_client() -> ORSClient:
    return ORSClient(settings.ORS_API_KEY, settings.ORS_BASE_URL, settings.ORS_TIMEOUT_SECONDS)


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def make_route_id(start: str, finish: str, start_fuel_gallons: float) -> str:
    raw = f"{_normalise(start)}|{_normalise(finish)}|{start_fuel_gallons:.3f}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def get_cached_plan(route_id: str):
    return cache.get(f"plan:{route_id}")


def _geocode_cached(text: str, client) -> Location:
    key = "geo:" + hashlib.sha1(_normalise(text).encode()).hexdigest()
    hit = cache.get(key)
    if hit:
        return Location(**hit)
    location = geocode(text, places=get_place_index(), client=client)
    cache.set(key, asdict(location), GEO_CACHE_SECONDS)
    return location


def _point(loc: Location) -> dict:
    return {"query": loc.query, "label": loc.label, "lat": round(loc.lat, 5), "lon": round(loc.lon, 5)}


def plan_route(start: str, finish: str, start_fuel_gallons: float = 0.0):
    route_id = make_route_id(start, finish, start_fuel_gallons)
    cached = get_cached_plan(route_id)
    if cached is not None:
        return cached, True

    client = get_client()
    origin = _geocode_cached(start, client)
    destination = _geocode_cached(finish, client)
    route = client.directions((origin.lat, origin.lon), (destination.lat, destination.lon))

    index = get_station_index()
    hits = stations_along_route(index, route.coordinates, settings.CORRIDOR_MILES, route_miles=route.distance_miles)
    fuel_plan = plan_fuel_stops(
        [FuelStation(h.station, h.route_mile, float(index.price[h.station])) for h in hits],
        route.distance_miles,
        range_miles=settings.VEHICLE_RANGE_MILES,
        mpg=settings.VEHICLE_MPG,
        start_fuel_gallons=start_fuel_gallons,
        start_radius_miles=settings.START_RADIUS_MILES,
    )

    payload = {
        "route_id": route_id,
        "start": _point(origin),
        "finish": _point(destination),
        "route": {
            "distance_miles": round(route.distance_miles, 1),
            "duration_hours": round(route.duration_hours, 2),
            "geometry": {
                "type": "LineString",
                "coordinates": [[round(lon, 5), round(lat, 5)] for lon, lat, *_ in route.coordinates],
            },
        },
        "fuel_stops": [
            {
                "order": n,
                **index.describe(stop.key),
                "route_mile": round(stop.route_mile, 1),
                "price_per_gallon": round(stop.price, 3),
                "gallons": round(stop.gallons, 2),
                "cost": round(stop.cost, 2),
            }
            for n, stop in enumerate(fuel_plan.stops, start=1)
        ],
        "totals": {
            "stops": len(fuel_plan.stops),
            "gallons": round(fuel_plan.total_gallons, 2),
            "fuel_cost": round(fuel_plan.total_cost, 2),
        },
        "assumptions": {
            "range_miles": settings.VEHICLE_RANGE_MILES,
            "mpg": settings.VEHICLE_MPG,
            "tank_gallons": settings.VEHICLE_RANGE_MILES / settings.VEHICLE_MPG,
            "start_fuel_gallons": start_fuel_gallons,
            "corridor_miles": settings.CORRIDOR_MILES,
            "start_radius_miles": settings.START_RADIUS_MILES,
            "stations_considered": len(hits),
        },
    }
    cache.set(f"plan:{route_id}", payload, settings.PLAN_CACHE_SECONDS)
    return payload, False

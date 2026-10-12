"""Find fuel stations near a route and their position along it."""
from dataclasses import dataclass

import numpy as np

from .geo import haversine_miles

MILES_PER_DEGREE_LAT = 69.0
CHUNK = 512


@dataclass(frozen=True)
class CorridorHit:
    station: int
    route_mile: float
    offset_miles: float


def resample_route(coords_lonlat, step_miles: float = 1.0):
    """Points every `step_miles` along the route, plus cumulative miles."""
    pts = np.asarray(coords_lonlat, dtype=float)
    lon, lat = pts[:, 0], pts[:, 1]
    if len(pts) < 2:
        return lat[:1], lon[:1], np.zeros(1)
    cum = np.concatenate([[0.0], np.cumsum(haversine_miles(lat[:-1], lon[:-1], lat[1:], lon[1:]))])
    total = float(cum[-1])
    if total <= 0:
        return lat[:1], lon[:1], np.zeros(1)
    samples = np.append(np.arange(0.0, total, step_miles), total)
    return np.interp(samples, cum, lat), np.interp(samples, cum, lon), samples


def _candidates_near(index, lat, lon, corridor_miles: float) -> np.ndarray:
    """Stations in grid cells next to the route. Cells are at least `corridor_miles` wide,
    so any station within the corridor sits in a route cell or one of its 8 neighbours."""
    cell_lat = corridor_miles / MILES_PER_DEGREE_LAT
    widest = min(float(np.abs(lat).max()) + cell_lat, 89.0)
    cell_lon = cell_lat / np.cos(np.radians(widest))

    def keys(lats, lons):
        return np.floor(lats / cell_lat).astype(np.int64) * 100_000 + np.floor(lons / cell_lon).astype(np.int64)

    route_keys = np.unique(keys(lat, lon))
    near = np.unique((route_keys[:, None] + np.array([dr * 100_000 + dc for dr in (-1, 0, 1) for dc in (-1, 0, 1)])).ravel())
    return np.flatnonzero(np.isin(keys(index.lat, index.lon), near))


def stations_along_route(index, coords_lonlat, corridor_miles: float, *, route_miles=None, step_miles: float = 1.0):
    lat, lon, miles = resample_route(coords_lonlat, step_miles)
    if route_miles and miles[-1] > 0:
        miles = miles * (route_miles / miles[-1])  # align with the road distance OpenRouteService reports

    candidates = _candidates_near(index, lat, lon, corridor_miles)

    hits = []
    for start in range(0, len(candidates), CHUNK):
        chunk = candidates[start:start + CHUNK]
        dist = haversine_miles(index.lat[chunk][:, None], index.lon[chunk][:, None], lat[None, :], lon[None, :])
        nearest = dist.argmin(axis=1)
        offsets = dist[np.arange(len(chunk)), nearest]
        keep = offsets <= corridor_miles
        for station, vertex, offset in zip(chunk[keep], nearest[keep], offsets[keep]):
            hits.append(CorridorHit(int(station), float(miles[vertex]), float(offset)))
    hits.sort(key=lambda h: h.route_mile)
    return hits

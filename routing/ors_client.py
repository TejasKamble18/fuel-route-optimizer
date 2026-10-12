"""Thin client for the two OpenRouteService endpoints this app uses."""
from dataclasses import dataclass

import requests

METERS_PER_MILE = 1609.344
DIRECTIONS_PATH = "/openrouteservice/v2/directions/driving-hgv/geojson"
SEARCH_PATH = "/pelias/v1/search"


@dataclass(frozen=True)
class RouteResult:
    coordinates: list  # [[lon, lat], ...]
    distance_miles: float
    duration_hours: float


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lon: float
    label: str
    country_code: str
    region_code: str


class ORSError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class ORSTimeout(ORSError):
    pass


class NoRouteFound(ORSError):
    pass


def _error_message(resp) -> str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text[:200] or f"HTTP {resp.status_code}"
    error = data.get("error", data) if isinstance(data, dict) else data
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error)


class ORSClient:
    def __init__(self, api_key: str, base_url: str = "https://api.heigit.org", timeout: float = 20.0, session=None):
        if not api_key:
            raise ORSError("ORS_API_KEY is not configured.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": api_key, "Accept": "application/json, application/geo+json"})

    def _request(self, method: str, path: str, **kwargs):
        try:
            resp = self.session.request(method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs)
        except requests.Timeout as exc:
            raise ORSTimeout("OpenRouteService did not respond in time.") from exc
        except requests.RequestException as exc:
            raise ORSError(f"Could not reach OpenRouteService ({exc.__class__.__name__}).") from exc
        if resp.status_code >= 400:
            message = _error_message(resp)
            if resp.status_code == 404 or "routable point" in message.lower():
                raise NoRouteFound(message, resp.status_code)
            raise ORSError(message, resp.status_code)
        return resp.json()

    def directions(self, start: tuple[float, float], end: tuple[float, float]) -> RouteResult:
        body = {"coordinates": [[start[1], start[0]], [end[1], end[0]]], "instructions": False}
        data = self._request("POST", DIRECTIONS_PATH, json=body)
        feature = data["features"][0]
        summary = feature.get("properties", {}).get("summary", {})
        return RouteResult(
            coordinates=feature["geometry"]["coordinates"],
            distance_miles=float(summary.get("distance", 0.0)) / METERS_PER_MILE,
            duration_hours=float(summary.get("duration", 0.0)) / 3600.0,
        )

    def geocode(self, text: str) -> GeocodeResult | None:
        data = self._request("GET", SEARCH_PATH, params={"text": text, "size": 1})
        features = data.get("features") or []
        if not features:
            return None
        feature = features[0]
        lon, lat = feature["geometry"]["coordinates"][:2]
        props = feature.get("properties", {})
        country = (props.get("country_code") or props.get("country_a") or "").upper()
        return GeocodeResult(
            lat=float(lat),
            lon=float(lon),
            label=props.get("label", text),
            country_code=country,
            region_code=(props.get("region_a") or "").upper(),
        )

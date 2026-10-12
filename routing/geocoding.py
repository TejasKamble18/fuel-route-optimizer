"""Turn user input into coordinates: local lookups first, OpenRouteService last."""
import re
import string
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings

from .datasets import normalise_place, read_places
from .us_states import STATE_NAME_TO_CODE, US_STATES

_LATLON = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
_COUNTRY_SUFFIXES = {"usa", "us", "united states", "united states of america"}


@dataclass(frozen=True)
class Location:
    query: str
    lat: float
    lon: float
    label: str
    source: str


class GeocodingError(Exception):
    code = "geocoding_error"


class LocationNotFound(GeocodingError):
    code = "location_not_found"


class OutsideUSA(GeocodingError):
    code = "outside_usa"


def in_usa(lat: float, lon: float) -> bool:
    """Bounding boxes for the contiguous US, Alaska and Hawaii."""
    contiguous = 24.3 <= lat <= 49.5 and -125.0 <= lon <= -66.8
    alaska = 51.0 <= lat <= 71.6 and (-180.0 <= lon <= -129.9 or 172.0 <= lon <= 180.0)
    hawaii = 18.8 <= lat <= 22.4 and -160.3 <= lon <= -154.7
    return contiguous or alaska or hawaii


def parse_latlon(text: str):
    m = _LATLON.match(text)
    return (float(m.group(1)), float(m.group(2))) if m else None


def _parts(text: str) -> list[str]:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    while parts and parts[-1].lower() in _COUNTRY_SUFFIXES:
        parts.pop()
    return parts


def _region_token(text: str) -> str | None:
    parts = _parts(text)
    return parts[-1] if len(parts) >= 2 else None


def parse_city_state(text: str):
    parts = _parts(text)
    if len(parts) < 2:
        return None
    region = parts[-1]
    first_word = region.split()[0].upper()
    if len(first_word) == 2 and first_word in US_STATES:
        return parts[-2], first_word
    code = STATE_NAME_TO_CODE.get(region.lower())
    return (parts[-2], code) if code else None


class PlaceIndex:
    def __init__(self, places: dict):
        self._places = places

    @classmethod
    def from_csv(cls, path) -> "PlaceIndex":
        return cls(read_places(path))

    def lookup(self, city: str, state: str):
        return self._places.get((state, normalise_place(city)))


@lru_cache(maxsize=1)
def get_place_index() -> PlaceIndex:
    return PlaceIndex.from_csv(settings.PLACES_CSV)


def geocode(text: str, *, places: PlaceIndex, client) -> Location:
    text = text.strip()

    latlon = parse_latlon(text)
    if latlon:
        lat, lon = latlon
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise LocationNotFound(f"'{text}' is not a valid latitude,longitude pair.")
        if not in_usa(lat, lon):
            raise OutsideUSA(f"'{text}' is outside the USA.")
        return Location(text, lat, lon, f"{lat:.5f}, {lon:.5f}", "coordinates")

    city_state = parse_city_state(text)
    if city_state:
        hit = places.lookup(*city_state)
        if hit:
            return Location(text, hit[0], hit[1], f"{string.capwords(city_state[0])}, {city_state[1]}", "places")
    else:
        region = _region_token(text)
        if region and len(region.split()[0]) == 2 and region.split()[0].upper() not in US_STATES:
            raise OutsideUSA(f"'{region}' is not a US state; both locations must be in the USA.")

    result = client.geocode(text)
    if result is None:
        raise LocationNotFound(f"Could not find '{text}'.")
    if result.country_code not in ("US", "USA") or not in_usa(result.lat, result.lon):
        raise OutsideUSA(f"'{text}' resolved to {result.label}, which is outside the USA.")
    return Location(text, result.lat, result.lon, result.label, "ors")

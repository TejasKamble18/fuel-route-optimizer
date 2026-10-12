import pytest

from routing.geocoding import (
    LocationNotFound, OutsideUSA, PlaceIndex, geocode, parse_city_state, parse_latlon,
)
from routing.ors_client import GeocodeResult

PLACES = PlaceIndex({("TX", "dallas"): (32.78, -96.80), ("IL", "chicago"): (41.88, -87.63)})


class FakeClient:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def geocode(self, text):
        self.calls.append(text)
        return self.result


def test_parse_latlon():
    assert parse_latlon("41.88, -87.63") == (41.88, -87.63)
    assert parse_latlon("Chicago, IL") is None


@pytest.mark.parametrize("text,expected", [
    ("Dallas, TX", ("Dallas", "TX")),
    ("dallas, tx", ("dallas", "TX")),
    ("Dallas, Texas", ("Dallas", "TX")),
    ("Chicago, IL, USA", ("Chicago", "IL")),
    ("Chicago, IL 60601", ("Chicago", "IL")),
    ("Chicago IL", None),
])
def test_parse_city_state(text, expected):
    assert parse_city_state(text) == expected


def test_local_lookup_makes_no_api_call():
    client = FakeClient()
    loc = geocode("dallas, texas", places=PLACES, client=client)
    assert (loc.lat, loc.lon, loc.source) == (32.78, -96.80, "places")
    assert client.calls == []


def test_coordinates_inside_usa():
    loc = geocode("41.88,-87.63", places=PLACES, client=FakeClient())
    assert loc.source == "coordinates"


def test_coordinates_outside_usa():
    with pytest.raises(OutsideUSA):
        geocode("19.43,-99.13", places=PLACES, client=FakeClient())  # Mexico City


def test_canadian_province_rejected_without_api_call():
    client = FakeClient()
    with pytest.raises(OutsideUSA):
        geocode("Toronto, ON", places=PLACES, client=client)
    assert client.calls == []


def test_ors_fallback_us_result():
    client = FakeClient(GeocodeResult(29.76, -95.37, "Houston, TX, USA", "US", "TX"))
    loc = geocode("Houston Astrodome", places=PLACES, client=client)
    assert (loc.lat, loc.source) == (29.76, "ors")


def test_ors_fallback_non_us_result():
    client = FakeClient(GeocodeResult(48.85, 2.35, "Paris, France", "FR", ""))
    with pytest.raises(OutsideUSA):
        geocode("Paris, France", places=PLACES, client=client)


def test_ors_fallback_no_result():
    with pytest.raises(LocationNotFound):
        geocode("zzzz qqqq", places=PLACES, client=FakeClient(None))

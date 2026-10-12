import pytest
import requests
import responses

from routing.ors_client import NoRouteFound, ORSClient, ORSError, ORSTimeout

BASE = "https://api.heigit.org"
DIRECTIONS = f"{BASE}/openrouteservice/v2/directions/driving-hgv/geojson"
SEARCH = f"{BASE}/pelias/v1/search"


def client():
    return ORSClient("test-key", BASE)


@responses.activate
def test_directions_parses_route_and_sends_lon_lat():
    responses.post(DIRECTIONS, json={
        "features": [{
            "geometry": {"coordinates": [[-87.6, 41.8], [-96.8, 32.7]]},
            "properties": {"summary": {"distance": 1609344.0, "duration": 7200.0}},
        }]
    })
    route = client().directions((41.8, -87.6), (32.7, -96.8))
    assert route.coordinates == [[-87.6, 41.8], [-96.8, 32.7]]
    assert route.distance_miles == pytest.approx(1000.0)
    assert route.duration_hours == pytest.approx(2.0)
    sent = responses.calls[0].request
    assert sent.headers["Authorization"] == "test-key"
    assert b'"coordinates": [[-87.6, 41.8], [-96.8, 32.7]]' in sent.body


@responses.activate
def test_directions_404_is_no_route():
    responses.post(DIRECTIONS, status=404, json={"error": {"code": 2010, "message": "Could not find routable point"}})
    with pytest.raises(NoRouteFound, match="routable point"):
        client().directions((41.8, -87.6), (32.7, -96.8))


@responses.activate
def test_directions_server_error():
    responses.post(DIRECTIONS, status=500, body="boom")
    with pytest.raises(ORSError) as info:
        client().directions((41.8, -87.6), (32.7, -96.8))
    assert info.value.status == 500


@responses.activate
def test_directions_timeout():
    responses.post(DIRECTIONS, body=requests.exceptions.ConnectTimeout())
    with pytest.raises(ORSTimeout):
        client().directions((41.8, -87.6), (32.7, -96.8))


@responses.activate
def test_geocode_returns_first_feature():
    responses.get(SEARCH, json={"features": [{
        "geometry": {"coordinates": [-96.8, 32.78]},
        "properties": {"label": "Dallas, TX, USA", "country_code": "US", "region_a": "TX"},
    }]})
    result = client().geocode("Dallas")
    assert (result.lat, result.lon) == (32.78, -96.8)
    assert result.country_code == "US"
    assert result.region_code == "TX"


@responses.activate
def test_geocode_no_match():
    responses.get(SEARCH, json={"features": []})
    assert client().geocode("nowhere at all") is None


def test_missing_key_rejected():
    with pytest.raises(ORSError, match="not configured"):
        ORSClient("", BASE)

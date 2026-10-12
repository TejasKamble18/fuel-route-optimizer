import pytest
from django.core.cache import cache

from routing import services
from routing.geo import haversine_miles
from routing.geocoding import PlaceIndex
from routing.ors_client import ORSTimeout, RouteResult
from routing.stations import StationIndex

START, END = (40.0, -100.0), (40.0, -90.0)


class FakeClient:
    def __init__(self, error=None):
        self.error = error
        self.direction_calls = 0

    def directions(self, start, end):
        self.direction_calls += 1
        if self.error:
            raise self.error
        miles = float(haversine_miles(start[0], start[1], end[0], end[1]))
        return RouteResult([[start[1], start[0]], [end[1], end[0]]], miles, miles / 55.0)

    def geocode(self, text):
        return None


def station(opis, lon, price):
    return {"opis_id": opis, "name": f"STOP {opis}", "address": "I-70", "city": "Town",
            "state": "KS", "price": price, "lat": 40.0, "lon": lon}


@pytest.fixture
def fake(monkeypatch):
    cache.clear()
    client = FakeClient()
    monkeypatch.setattr(services, "get_client", lambda: client)
    monkeypatch.setattr(services, "get_place_index", lambda: PlaceIndex({
        ("KS", "alpha"): START, ("MO", "omega"): END,
    }))
    monkeypatch.setattr(services, "get_station_index", lambda: StationIndex.from_rows([
        station(1, -100.0, 3.5), station(2, -95.0, 3.0),
    ]))
    return client


def test_post_returns_plan(client, fake):
    resp = client.post("/api/route/", {"start": "Alpha, KS", "finish": "Omega, MO"}, content_type="application/json")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["route"]["distance_miles"] == pytest.approx(530, abs=5)
    assert [s["opis_id"] for s in body["fuel_stops"]] == [1, 2]
    assert body["totals"]["gallons"] == pytest.approx(body["route"]["distance_miles"] / 10, abs=0.05)
    assert body["map_url"].endswith(f"/api/route/{body['route_id']}/map/")
    assert body["meta"]["cached"] is False


def test_get_with_query_params(client, fake):
    resp = client.get("/api/route/", {"start": "Alpha, KS", "finish": "Omega, MO"})
    assert resp.status_code == 200


def test_second_call_is_cached(client, fake):
    for _ in range(2):
        resp = client.get("/api/route/", {"start": "Alpha, KS", "finish": "Omega, MO"})
    assert fake.direction_calls == 1
    assert resp.json()["meta"]["cached"] is True


def test_missing_finish_is_400(client, fake):
    resp = client.post("/api/route/", {"start": "Alpha, KS"}, content_type="application/json")
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_input"


@pytest.mark.parametrize("value", [-1, 51])
def test_start_fuel_out_of_range_is_400(client, fake, value):
    resp = client.post("/api/route/", {"start": "Alpha, KS", "finish": "Omega, MO", "start_fuel_gallons": value},
                       content_type="application/json")
    assert resp.status_code == 400


def test_outside_usa_is_404(client, fake):
    resp = client.get("/api/route/", {"start": "Toronto, ON", "finish": "Omega, MO"})
    assert resp.status_code == 404
    assert resp.json()["error"] == "outside_usa"


def test_range_gap_is_422(client, fake, monkeypatch):
    monkeypatch.setattr(services, "get_station_index", lambda: StationIndex.from_rows([station(1, -100.0, 3.5)]))
    resp = client.get("/api/route/", {"start": "Alpha, KS", "finish": "Omega, MO"})
    assert resp.status_code == 422
    assert resp.json()["error"] == "range_gap"


def test_routing_timeout_is_504(client, fake):
    fake.error = ORSTimeout("slow")
    resp = client.get("/api/route/", {"start": "Alpha, KS", "finish": "Omega, MO"})
    assert resp.status_code == 504
    assert resp.json()["error"] == "routing_timeout"


def test_same_start_and_finish(client, fake):
    resp = client.get("/api/route/", {"start": "Alpha, KS", "finish": "Alpha, KS"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["fuel_stops"] == []
    assert body["totals"]["fuel_cost"] == 0


def test_map_page(client, fake):
    body = client.get("/api/route/", {"start": "Alpha, KS", "finish": "Omega, MO"}).json()
    page = client.get(f"/api/route/{body['route_id']}/map/")
    assert page.status_code == 200
    assert b"leaflet" in page.content
    assert b"plan-data" in page.content


def test_unknown_map_is_404(client, fake):
    assert client.get("/api/route/doesnotexist/map/").status_code == 404


def test_map_page_sends_origin_referrer_for_osm_tiles(client, fake):
    # tile.openstreetmap.org rejects tile requests that carry no Referer; Django defaults to same-origin.
    body = client.get("/api/route/", {"start": "Alpha, KS", "finish": "Omega, MO"}).json()
    page = client.get(f"/api/route/{body['route_id']}/map/")
    assert page["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert b"tile.openstreetmap.org" in page.content

import pytest

from routing.corridor import resample_route, stations_along_route
from routing.stations import StationIndex

ROUTE = [[-100.0, 40.0], [-90.0, 40.0]]  # roughly 530 miles due east along latitude 40


def station(opis, lat, lon):
    return {"opis_id": opis, "name": f"S{opis}", "address": "", "city": "X", "state": "KS",
            "price": 3.0, "lat": lat, "lon": lon}


def test_resample_route_spacing():
    lat, lon, miles = resample_route(ROUTE, step_miles=1.0)
    assert miles[0] == 0.0
    assert miles[-1] == pytest.approx(530, abs=5)
    assert len(miles) == pytest.approx(int(miles[-1]) + 2, abs=1)


def test_stations_along_route_filters_by_offset_and_orders_by_mile():
    index = StationIndex.from_rows([
        station(1, 40.0, -95.0),             # on the route, mid-way
        station(2, 40.0 + 5 / 69.0, -99.0),  # 5 miles north, near the start
        station(3, 40.0 + 30 / 69.0, -95.0), # 30 miles north: outside corridor
        station(4, 40.0, -85.0),             # beyond the end
    ])
    hits = stations_along_route(index, ROUTE, corridor_miles=10)
    ids = [index.describe(h.station)["opis_id"] for h in hits]
    assert ids == [2, 1]
    assert hits[0].offset_miles == pytest.approx(5, abs=0.6)
    assert hits[1].route_mile == pytest.approx(265, abs=3)


def test_route_miles_scales_positions():
    index = StationIndex.from_rows([station(1, 40.0, -90.0)])
    hits = stations_along_route(index, ROUTE, corridor_miles=10, route_miles=600.0)
    assert hits[0].route_mile == pytest.approx(600.0, abs=0.01)


def test_single_point_route():
    index = StationIndex.from_rows([station(1, 40.0, -100.0)])
    hits = stations_along_route(index, [[-100.0, 40.0], [-100.0, 40.0]], corridor_miles=10)
    assert [h.route_mile for h in hits] == [0.0]


def test_station_near_corridor_edge_in_neighbouring_cell():
    index = StationIndex.from_rows([station(1, 40.0 - 9.5 / 69.0, -95.0), station(2, 40.0 - 10.5 / 69.0, -95.0)])
    hits = stations_along_route(index, ROUTE, corridor_miles=10)
    assert [index.describe(h.station)["opis_id"] for h in hits] == [1]

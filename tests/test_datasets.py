from routing.datasets import attach_coordinates, clean_fuel_rows, load_census_places, normalise_place


def row(opis, city, state, price, name="STOP"):
    return {"OPIS Truckstop ID": str(opis), "Truckstop Name": name, "Address": "I-1, EXIT 1",
            "City": city, "State": state, "Rack ID": "1", "Retail Price": str(price)}


def test_normalise_place():
    assert normalise_place("East St. Louis city", census=True) == "east saint louis"
    assert normalise_place("East Saint Louis") == "east saint louis"
    assert normalise_place("Mc Calla") == "mccalla"
    assert normalise_place("McCalla CDP", census=True) == "mccalla"
    assert normalise_place("Indianapolis city (balance)", census=True) == "indianapolis"
    assert normalise_place("Kansas City") == "kansas city"
    assert normalise_place("Kansas City city", census=True) == "kansas city"
    assert normalise_place("  New Castle                 ") == "new castle"
    assert normalise_place("Mt. Vernon") == "mount vernon"


def test_clean_fuel_rows_drops_canada_and_keeps_lowest_price():
    rows = [
        row(1, "Tomah", "WI", 3.5), row(1, "Tomah", "WI", 3.2), row(1, "Tomah", "WI", 3.9),
        row(2, "Edmonton", "AB", 4.4),
        row(3, "New Castle                     ", " DE ", 3.249),
    ]
    cleaned = clean_fuel_rows(rows)
    assert [(s["opis_id"], s["price"]) for s in cleaned] == [(1, 3.2), (3, 3.249)]
    assert cleaned[1]["city"] == "New Castle"
    assert cleaned[1]["state"] == "DE"


def test_load_census_places_strips_suffixes_and_adds_aliases(tmp_path):
    path = tmp_path / "gaz.txt"
    path.write_text(
        "USPS|GEOID|GEOIDFQ|ANSICODE|NAME|LSAD|FUNCSTAT|ALAND|AWATER|ALAND_SQMI|AWATER_SQMI|INTPTLAT|INTPTLONG\n"
        "ID|1|x|x|Boise City city|25|A|1|1|1|1|43.6|-116.2\n"
        "GA|2|x|x|Athens-Clarke County unified government (balance)|25|A|1|1|1|1|33.95|-83.37\n"
        "PR|3|x|x|San Juan zona urbana|25|A|1|1|1|1|18.4|-66.1\n",
        encoding="utf-8",
    )
    places = {(s, n): (lat, lon) for s, n, lat, lon in load_census_places(path)}
    assert places[("ID", "boise city")] == (43.6, -116.2)
    assert places[("ID", "boise")] == (43.6, -116.2)
    assert places[("GA", "athens")] == (33.95, -83.37)
    assert not any(state == "PR" for state, _ in places)


def test_attach_coordinates_prefers_overrides():
    stations = [
        {"opis_id": 1, "name": "A", "address": "", "city": "Dallas", "state": "TX", "price": 3.0},
        {"opis_id": 2, "name": "B", "address": "", "city": "Nowhere", "state": "TX", "price": 3.0},
        {"opis_id": 3, "name": "C", "address": "", "city": "Milford", "state": "CT", "price": 3.0},
    ]
    places = {("TX", "dallas"): (32.7, -96.8)}
    overrides = {("CT", "milford"): (41.2, -73.1)}
    located, missing = attach_coordinates(stations, places, overrides)
    assert [(s["opis_id"], s["lat"], s["lon"]) for s in located] == [(1, 32.7, -96.8), (3, 41.2, -73.1)]
    assert [s["opis_id"] for s in missing] == [2]

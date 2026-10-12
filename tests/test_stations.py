from routing.stations import StationIndex


def test_from_rows_and_describe():
    index = StationIndex.from_rows([
        {"opis_id": "7", "name": "WOODSHED", "address": "I-44, EXIT 283", "city": "Big Cabin",
         "state": "OK", "price": "3.007", "lat": "36.53", "lon": "-95.22"},
    ])
    assert len(index) == 1
    assert index.describe(0) == {
        "opis_id": 7, "name": "WOODSHED", "address": "I-44, EXIT 283",
        "city": "Big Cabin", "state": "OK", "lat": 36.53, "lon": -95.22,
    }
    assert float(index.price[0]) == 3.007

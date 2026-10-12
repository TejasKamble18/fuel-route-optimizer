import pytest

from routing.geo import haversine_miles


def test_chicago_to_dallas_great_circle():
    assert haversine_miles(41.8781, -87.6298, 32.7767, -96.7970) == pytest.approx(803, abs=5)


def test_zero_distance():
    assert haversine_miles(40.0, -100.0, 40.0, -100.0) == pytest.approx(0.0)

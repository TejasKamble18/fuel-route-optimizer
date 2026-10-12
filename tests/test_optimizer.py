import pytest

from routing.optimizer import FuelStation, NoFuelNearStart, RangeGap, plan_fuel_stops


def stops_summary(plan):
    return [(s.key, round(s.gallons, 6), round(s.cost, 6)) for s in plan.stops]


def test_single_stop_when_destination_within_range():
    plan = plan_fuel_stops([FuelStation(1, 0.0, 3.0)], 300.0)
    assert stops_summary(plan) == [(1, 30.0, 90.0)]
    assert plan.total_gallons == pytest.approx(30.0)
    assert plan.total_cost == pytest.approx(90.0)


def test_buys_only_enough_to_reach_cheaper_station():
    stations = [FuelStation(1, 0.0, 4.0), FuelStation(2, 200.0, 3.0)]
    plan = plan_fuel_stops(stations, 600.0)
    assert stops_summary(plan) == [(1, 20.0, 80.0), (2, 40.0, 120.0)]
    assert plan.total_cost == pytest.approx(200.0)


def test_fills_tank_when_no_cheaper_station_in_range():
    stations = [FuelStation(1, 0.0, 3.0), FuelStation(2, 400.0, 3.5), FuelStation(3, 800.0, 3.2)]
    plan = plan_fuel_stops(stations, 1000.0)
    assert stops_summary(plan) == [(1, 50.0, 150.0), (2, 30.0, 105.0), (3, 20.0, 64.0)]
    assert plan.total_gallons == pytest.approx(100.0)
    assert plan.total_cost == pytest.approx(319.0)


def test_range_gap_raises():
    stations = [FuelStation(1, 0.0, 3.0), FuelStation(2, 600.0, 3.0)]
    with pytest.raises(RangeGap) as info:
        plan_fuel_stops(stations, 900.0)
    assert info.value.from_mile == pytest.approx(0.0)
    assert info.value.to_mile == pytest.approx(600.0)


def test_no_station_near_start():
    with pytest.raises(NoFuelNearStart):
        plan_fuel_stops([FuelStation(1, 40.0, 3.0)], 300.0)


def test_start_fuel_skips_first_purchase():
    plan = plan_fuel_stops([FuelStation(1, 100.0, 3.0)], 550.0, start_fuel_gallons=50.0)
    assert stops_summary(plan) == [(1, 5.0, 15.0)]


def test_start_fuel_enough_for_whole_trip():
    plan = plan_fuel_stops([FuelStation(1, 100.0, 3.0)], 300.0, start_fuel_gallons=40.0)
    assert plan.stops == []
    assert plan.total_cost == 0.0


def test_zero_length_route_needs_no_fuel():
    plan = plan_fuel_stops([], 0.0)
    assert plan.stops == []
    assert plan.total_cost == 0.0


def test_station_exactly_at_range_limit_is_reachable():
    stations = [FuelStation(1, 0.0, 4.0), FuelStation(2, 500.0, 3.0)]
    plan = plan_fuel_stops(stations, 900.0)
    assert stops_summary(plan) == [(1, 50.0, 200.0), (2, 40.0, 120.0)]


def test_cheapest_station_near_start_is_used_first():
    stations = [FuelStation(1, 0.0, 4.0), FuelStation(2, 20.0, 3.0)]
    plan = plan_fuel_stops(stations, 300.0)
    assert stops_summary(plan) == [(2, 30.0, 90.0)]
    assert plan.stops[0].route_mile == 20.0

"""Cheapest fuel stops along a fixed route (the classic gas-station problem).

Pure Python, no Django: positions are route miles, prices are per gallon.
"""
from dataclasses import dataclass

EPS = 1e-9


@dataclass(frozen=True)
class FuelStation:
    key: int
    route_mile: float
    price: float


@dataclass(frozen=True)
class Stop:
    key: int
    route_mile: float
    price: float
    gallons: float
    cost: float


@dataclass(frozen=True)
class FuelPlan:
    stops: list
    total_gallons: float
    total_cost: float


class OptimizationError(Exception):
    code = "optimization_error"


class NoFuelNearStart(OptimizationError):
    code = "no_fuel_near_start"


class RangeGap(OptimizationError):
    code = "range_gap"

    def __init__(self, from_mile: float, to_mile: float):
        self.from_mile = from_mile
        self.to_mile = to_mile
        super().__init__(
            f"No reachable fuel station between route mile {from_mile:.0f} and {to_mile:.0f}; "
            "the gap is longer than the vehicle range."
        )


def plan_fuel_stops(
    stations,
    route_miles: float,
    *,
    range_miles: float = 500.0,
    mpg: float = 10.0,
    start_fuel_gallons: float = 0.0,
    start_radius_miles: float = 25.0,
) -> FuelPlan:
    capacity = range_miles / mpg
    ordered = sorted(
        (s for s in stations if -EPS <= s.route_mile <= route_miles + EPS),
        key=lambda s: (s.route_mile, s.price),
    )
    fuel = min(max(start_fuel_gallons, 0.0), capacity)
    position = 0.0
    stops: list[Stop] = []

    if route_miles <= EPS:
        return FuelPlan([], 0.0, 0.0)

    if fuel <= EPS:
        nearby = [s for s in ordered if s.route_mile <= start_radius_miles + EPS]
        if not nearby:
            raise NoFuelNearStart(f"No fuel station within {start_radius_miles:.0f} miles of the start.")
        # Fuel before departing: the cheapest station near the origin counts as mile 0.
        current = min(nearby, key=lambda s: (s.price, s.route_mile))
    else:
        current = None  # at the origin with fuel already in the tank

    while True:
        ahead = [
            s for s in ordered
            if s is not current and position + EPS < s.route_mile <= position + range_miles + EPS
        ]
        to_destination = route_miles - position

        if current is None:
            reach = fuel * mpg
            if to_destination <= reach + EPS:
                break
            options = [s for s in ahead if s.route_mile <= position + reach + EPS]
            if not options:
                following = [s for s in ordered if s.route_mile > position + EPS]
                raise RangeGap(position, following[0].route_mile if following else route_miles)
            target = min(options, key=lambda s: (s.price, -s.route_mile))
            fuel = max(fuel - (target.route_mile - position) / mpg, 0.0)
            position, current = target.route_mile, target
            continue

        cheaper = next((s for s in ahead if s.price < current.price - EPS), None)
        if cheaper is not None:
            buy = max(0.0, (cheaper.route_mile - position) / mpg - fuel)
            nxt = cheaper
        elif to_destination <= range_miles + EPS:
            buy = max(0.0, to_destination / mpg - fuel)
            nxt = None
        elif ahead:
            buy = capacity - fuel
            nxt = min(ahead, key=lambda s: (s.price, -s.route_mile))
        else:
            following = [s for s in ordered if s.route_mile > position + EPS]
            raise RangeGap(position, following[0].route_mile if following else route_miles)

        if buy > EPS:
            stops.append(Stop(current.key, current.route_mile, current.price, buy, buy * current.price))
            fuel += buy
        if nxt is None:
            break
        fuel = max(fuel - (nxt.route_mile - position) / mpg, 0.0)
        position, current = nxt.route_mile, nxt

    return FuelPlan(stops, sum(s.gallons for s in stops), sum(s.cost for s in stops))

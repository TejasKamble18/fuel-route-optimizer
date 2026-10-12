# Fuel Route Optimizer

A Django REST API that plans a truck route between two US locations and picks the
**cheapest places to refuel** along it, for a vehicle with a **500-mile range** that
gets **10 miles per gallon**. It returns the route, every fuel stop (where, how much,
at what price), the total fuel cost, and a link to a map.

```
POST /api/route/   {"start": "Chicago, IL", "finish": "Dallas, TX"}
→ 966.3 mi · 7 fuel stops · 96.63 gal · $284.62 · map_url
```

- **One routing API call** per new request (OpenRouteService, truck profile).
- **About 2–3 seconds** for a new route, almost all of it waiting on the routing API;
  **about 5–10 ms** on the server for a repeated request (cached).
- Fuel prices come from the supplied CSV; stations are located and indexed offline,
  so a request never geocodes stations.

## Quick start

Requires Python 3.12+ and a free [OpenRouteService](https://openrouteservice.org) key.

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # then put your key in ORS_API_KEY
python manage.py runserver
```

Try it:

```bash
curl -X POST http://127.0.0.1:8000/api/route/ \
     -H "Content-Type: application/json" \
     -d '{"start": "Chicago, IL", "finish": "Dallas, TX"}'
```

Open the `map_url` from the response in a browser to see the route and stops.
A Postman collection is in [`postman/`](postman/fuel-route-optimizer.postman_collection.json).

## API

### `POST /api/route/` (or `GET /api/route/?start=…&finish=…`)

| Field | Required | Description |
|---|---|---|
| `start` | yes | `"City, ST"`, `"City, State"`, `"lat,lon"`, or any US address |
| `finish` | yes | Same formats as `start` |
| `start_fuel_gallons` | no | Fuel already in the tank, 0–50. Default 0 (truck starts empty) |

Response (trimmed):

```json
{
  "route_id": "30fdc8c0a8e7138c",
  "start":  {"query": "Chicago, IL", "label": "Chicago, IL", "lat": 41.83705, "lon": -87.68494},
  "finish": {"query": "Dallas, TX",  "label": "Dallas, TX",  "lat": 32.79333, "lon": -96.76651},
  "route": {
    "distance_miles": 966.3,
    "duration_hours": 21.53,
    "geometry": {"type": "LineString", "coordinates": [[-87.68489, 41.83705], "…"]}
  },
  "fuel_stops": [
    {"order": 1, "opis_id": 72577, "name": "QUIKTRIP #7205", "address": "I-80, EXIT 161",
     "city": "Lansing", "state": "IL", "lat": 41.565, "lon": -87.546,
     "route_mile": 20.0, "price_per_gallon": 3.079, "gallons": 8.7, "cost": 26.79},
    "…"
  ],
  "totals": {"stops": 7, "gallons": 96.63, "fuel_cost": 284.62},
  "assumptions": {"range_miles": 500.0, "mpg": 10.0, "tank_gallons": 50.0, "start_fuel_gallons": 0.0,
                  "corridor_miles": 10.0, "start_radius_miles": 25.0, "stations_considered": 189},
  "map_url": "http://127.0.0.1:8000/api/route/30fdc8c0a8e7138c/map/",
  "meta": {"cached": false, "elapsed_ms": 1971.1}
}
```

### `GET /api/route/<route_id>/map/`

An HTML page (Leaflet + OpenStreetMap) with the route, numbered fuel stops and a
summary panel. It renders the cached result, so it costs no API calls.

### Errors

All errors are JSON: `{"error": "<code>", "detail": "<message>"}`.

| Status | `error` | When |
|---|---|---|
| 400 | `invalid_input` | Missing `start`/`finish`, or `start_fuel_gallons` outside 0–50 |
| 404 | `location_not_found` / `outside_usa` | A location can't be found, or isn't in the USA |
| 422 | `no_fuel_near_start` | Starting empty with no station within 25 miles of the start |
| 422 | `range_gap` | A stretch of the route longer than 500 miles has no station (includes `from_mile`, `to_mile`) |
| 422 | `no_route` | No truck route between the two points |
| 502 / 504 | `routing_error` / `routing_timeout` | OpenRouteService failed or timed out |

## How it works

```
input ─► geocode (local, 0 calls) ─► route (1 ORS call) ─► stations near route ─► greedy optimiser ─► cache
```

1. **Geocoding.** `"City, ST"` resolves locally from the US Census places list
   (32,000+ places). `"lat,lon"` is checked with one reverse lookup of the country, so
   border cities like Tijuana or Toronto are rejected. Anything else falls back to
   OpenRouteService's geocoder. Non-US input is rejected. So a typical request makes
   **one** external call; the worst case is three.
2. **Routing.** One call to OpenRouteService's `driving-hgv` (heavy goods vehicle)
   profile, which respects truck restrictions.
3. **Stations near the route.** The route is resampled every mile. A grid prefilter
   picks stations in cells next to the route, then a vectorised haversine finds each
   one's distance to the route and its position (route mile). Stations within
   **10 miles** are kept. (New York → Los Angeles: 455 stations considered in about
   150 ms.)
4. **Choosing stops.** The classic "gas station problem" greedy, which is optimal for a
   fixed route with fixed prices:
   - If a **cheaper** station is reachable within 500 miles, buy **just enough** to get
     there.
   - Otherwise, if the destination is within range, buy just enough to finish.
   - Otherwise, **fill the tank** and go to the cheapest station in range.
   The truck arrives with an empty tank, so total gallons always equal distance ÷ 10.
5. **Caching.** Results are cached for 24 hours by a hash of the inputs, and geocodes
   for 7 days.

### Station data

The supplied CSV has 8,151 rows but no coordinates. `build_stations` cleans it once:

- drops 620 Canadian rows (the task is USA-only);
- collapses repeated OPIS IDs to **one station at its lowest price** (8,151 → 6,626);
- attaches coordinates from the Census places list (95% match), and looks up the rest
  once through OpenRouteService, saved in `data/geocode_overrides.csv`;
- result: **6,623 stations** in `data/stations.csv` (3 could not be located).

## Assumptions

- The truck **starts empty** and fuels at the cheapest station within 25 miles of the
  start (pass `start_fuel_gallons` to change this).
- Where a station is listed several times, its **lowest price** is used.
- Station coordinates are the **centre of the station's city**, because the CSV gives
  only a highway exit. The 10-mile corridor allows for this.
- The extra distance to drive off the highway to a station is ignored.
- Cost is optimised purely on fuel price, so the plan may include small top-ups where
  a few gallons are cheaper than carrying fuel from a pricier stop.

## Performance (local, Python 3.14)

| Route | Distance | Stops | Fuel cost | First request | Repeat |
|---|---|---|---|---|---|
| Chicago, IL → Dallas, TX | 966 mi | 7 | $284.62 | 2.0 s | 10 ms |
| 41.8781,-87.6298 → Denver, CO | 1,001 mi | 7 | $291.13 | 2.1 s | 4 ms |
| Atlanta, GA → Houston, TX (30 gal at start) | 797 mi | 6 | $141.06 | 1.7 s | – |
| New York, NY → Los Angeles, CA | 2,812 mi | 17 | $852.84 | 2.8 s | – |
| Miami, FL → Seattle, WA | 3,295 mi | 20 | $1,005.18 | 2.6 s | – |

Almost all of the first-request time is the OpenRouteService call; this app's own
work (corridor search + optimisation) takes about 20–150 ms.

## Limitations

- California has only 16 stations in the supplied data, so some West Coast routes may
  return `range_gap`.
- City-level station coordinates: a station's `lat`/`lon` is its city centre.
- The cache is in memory (Django `LocMemCache`); a production deployment would use Redis.

## Project layout

```
config/                     settings, URLs
routing/
  optimizer.py              greedy fuel-stop algorithm (pure Python)
  corridor.py               stations near the route + route miles
  geocoding.py              local place lookup + ORS fallback, USA check
  ors_client.py             OpenRouteService directions + geocoding
  stations.py               in-memory station index (numpy)
  services.py               one request end to end, with caching
  views.py, serializers.py, errors.py, urls.py
  templates/routing/map.html
  management/commands/      build_places, build_stations
data/                       raw CSV, places list, cleaned stations
docs/design.md              design notes
tests/                      66 tests (pytest)
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The routing API is mocked in tests, so they run offline in about a second.

## Rebuilding the station data

```bash
# Census places (https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html)
python manage.py build_places path/to/2025_Gaz_place_national.txt
python manage.py build_stations --geocode-missing
```

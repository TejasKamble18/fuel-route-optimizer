# Fuel Route Optimizer — Design

A Django API that takes a start and finish location in the USA, returns the
truck route, the most cost-effective fuel stops along it, and the total fuel
cost.

## Requirements (from the brief)

- Input: start and finish, both within the USA.
- Output: a map of the route, the fuel stops along it, and the total money
  spent on fuel.
- Vehicle range: 500 miles. Fuel economy: 10 miles per gallon.
- Fuel prices come from the supplied CSV (`data/fuel-prices-for-be-assessment.csv`).
- Latest stable Django. Fast responses. One call to the routing API is ideal,
  two or three are acceptable.

## Decisions

| Topic | Decision |
|---|---|
| Routing provider | OpenRouteService, `driving-hgv` (truck) profile, via `https://api.heigit.org/openrouteservice/v2/directions/driving-hgv/geojson` |
| Geocoding | Local US place gazetteer for "City, ST" input (0 API calls); fallback to OpenRouteService Pelias `search/structured` |
| Starting fuel | Truck starts empty and fuels at a station near the origin. Optional `start_fuel_gallons` overrides this |
| Duplicate stations | Same OPIS ID appears several times with different prices: keep the lowest price |
| Station coordinates | City centroid from the US Census Gazetteer (the CSV has no coordinates). Precomputed once, committed as `data/stations.csv` |
| Detours | Distance from the highway to a station is ignored in cost and range |

## Data preparation (offline, once)

Management command `build_stations` reads the raw CSV and writes
`data/stations.csv`:

1. Strip whitespace from every field.
2. Drop rows outside the 50 US states and DC (the file contains Canadian
   provinces such as AB, ON, BC, QC).
3. Group by OPIS Truckstop ID; keep the lowest Retail Price and the first name
   and address.
4. Attach latitude and longitude by matching (city, state) against the Census
   Gazetteer places file, after normalising names (case, punctuation,
   "Saint"/"St", place-type suffixes such as "city", "town", "village", "CDP").
5. Rows still unmatched are geocoded once through Pelias and cached in a small
   `data/geocode_overrides.csv`. Any row that still fails is dropped and
   reported.

The command prints counts: raw rows, US rows, unique stations, matched,
overridden, dropped.

At runtime the app loads `data/stations.csv` once into numpy arrays
(lat, lon, price, id).

## Request flow

`POST /api/route/` with `{"start": "...", "finish": "...", "start_fuel_gallons": 0}`
(`GET` with the same query parameters is also accepted for browser testing).

1. **Geocode** start and finish. "City, ST" and "lat,lon" inputs resolve
   locally; anything else calls Pelias. Results are cached.
2. **Route**: one call to OpenRouteService directions (GeoJSON). Gives the line
   geometry, distance and duration.
3. **Corridor**: keep stations inside the route's bounding box (padded), then
   compute each candidate's distance to the nearest route vertex (vectorised
   haversine). Keep those within `CORRIDOR_MILES` (default 10). Each kept
   station gets a position = cumulative route miles at its nearest vertex.
4. **Optimise** (below).
5. **Respond** and cache the full result for 24 hours under a hash of the
   normalised inputs.

Typical external calls per uncached request: 1 (routing). Worst case: 3.

## Fuel-stop algorithm

Tank capacity `C = 500 / 10 = 50` gallons. Stations are sorted by route
position.

- **Start**: stations within `START_RADIUS_MILES` (default 25) of the origin
  are treated as being at mile 0 (the truck fuels before departing). If there
  are none and `start_fuel_gallons` is 0, return 422.
- **Greedy step** at station `i` with fuel `f` (gallons):
  1. If a cheaper station is reachable (within 500 miles ahead), go to the
     nearest such station, buying only what is needed to reach it.
  2. Else, if the destination is within 500 miles, buy just enough to reach the
     destination.
  3. Else, fill the tank and go to the cheapest station within range.
  4. If no station is within range and the destination is not reachable,
     return 422 with the uncovered stretch.
- For a fixed path with fixed prices this greedy is optimal (the classic
  gas-station problem).
- Total cost = Σ gallons bought × price at each stop. The truck arrives with an
  empty tank.

## Response

```json
{
  "start": {"query": "Chicago, IL", "lat": 41.88, "lon": -87.63},
  "finish": {"query": "Dallas, TX", "lat": 32.78, "lon": -96.80},
  "route": {"distance_miles": 967.4, "duration_hours": 15.2,
            "geometry": {"type": "LineString", "coordinates": [[-87.63, 41.88]]}},
  "fuel_stops": [
    {"order": 1, "opis_id": 1234, "name": "…", "address": "…", "city": "…",
     "state": "IL", "lat": 0, "lon": 0, "route_mile": 0.0,
     "price_per_gallon": 3.199, "gallons": 50.0, "cost": 159.95}
  ],
  "totals": {"gallons": 96.74, "fuel_cost": 312.40, "stops": 3},
  "assumptions": {"range_miles": 500, "mpg": 10, "corridor_miles": 10},
  "map_url": "/api/route/<id>/map/"
}
```

`GET /api/route/<id>/map/` renders a Leaflet page (OpenStreetMap tiles) with
the route line and numbered stop markers, from the cached result.

## Errors

| Status | When |
|---|---|
| 400 | Missing or invalid input |
| 404 | A location could not be geocoded, or is outside the USA |
| 422 | No fuel near the start, or a stretch longer than 500 miles with no station |
| 502 / 504 | OpenRouteService returned an error or timed out |

All errors return `{"error": "<code>", "detail": "<message>"}`.

## Code layout

```
config/                 Django settings and URLs (settings read .env)
routing/
  stations.py           Load data/stations.csv into an in-memory index
  geocoding.py          Gazetteer lookup + Pelias fallback
  ors_client.py         OpenRouteService directions call
  corridor.py           Stations near the route + their route positions
  optimizer.py          Greedy fuel-stop algorithm (pure, no Django)
  services.py           Orchestrates one request, caching
  views.py, serializers.py, urls.py
  templates/routing/map.html
  management/commands/build_stations.py
data/                   Raw CSV, gazetteer extract, stations.csv
postman/                Postman collection for the demo
tests/
```

## Configuration (`.env`)

`ORS_API_KEY` (required), `ORS_BASE_URL` (default `https://api.heigit.org`),
`CORRIDOR_MILES` (10), `START_RADIUS_MILES` (25), `DJANGO_SECRET_KEY`,
`DJANGO_DEBUG`. `.env` is git-ignored; `.env.example` is committed.

## Testing

- `optimizer`: hand-computed cases (cheaper station ahead, fill-up branch,
  destination in range, unreachable gap, non-zero start fuel).
- `corridor`: synthetic straight-line route with stations on and off it.
- `build_stations`: Canadian rows dropped, duplicates collapsed to the lowest
  price, name normalisation.
- API: end-to-end with OpenRouteService mocked; error codes.

## Out of scope

Hosting (not required by the brief), authentication, live fuel prices, and
detour costs to stations.

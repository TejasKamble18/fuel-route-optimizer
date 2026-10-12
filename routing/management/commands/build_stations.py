import csv
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from routing.datasets import (
    attach_coordinates, clean_fuel_rows, read_overrides, read_places, write_csv,
)
from routing.ors_client import ORSClient
from routing.us_states import US_STATES

STATION_FIELDS = ["opis_id", "name", "address", "city", "state", "price", "lat", "lon"]


class Command(BaseCommand):
    help = "Clean the fuel price CSV and attach coordinates, writing data/stations.csv."

    def add_arguments(self, parser):
        data = settings.DATA_DIR
        parser.add_argument("--raw", default=str(data / "fuel-prices-for-be-assessment.csv"))
        parser.add_argument("--places", default=str(settings.PLACES_CSV))
        parser.add_argument("--overrides", default=str(data / "geocode_overrides.csv"))
        parser.add_argument("--out", default=str(settings.STATIONS_CSV))
        parser.add_argument("--geocode-missing", action="store_true",
                            help="Look up unmatched cities through OpenRouteService once and save them as overrides.")

    def handle(self, raw, places, overrides, out, geocode_missing, **options):
        with open(raw, newline="", encoding="utf-8-sig") as f:
            raw_rows = list(csv.DictReader(f))
        stations = clean_fuel_rows(raw_rows)
        place_index = read_places(places)
        override_index = read_overrides(overrides)
        located, missing = attach_coordinates(stations, place_index, override_index)

        if geocode_missing and missing:
            added = self._geocode(missing, overrides)
            override_index = read_overrides(overrides)
            located, missing = attach_coordinates(stations, place_index, override_index)
            self.stdout.write(f"Geocoded {added} cities through OpenRouteService")

        write_csv(out, STATION_FIELDS, located)
        self.stdout.write(f"Raw rows: {len(raw_rows)}")
        self.stdout.write(f"US stations (unique OPIS IDs): {len(stations)}")
        self.stdout.write(f"Located: {len(located)}  Missing: {len(missing)}")
        for s in missing[:50]:
            self.stdout.write(f"  missing: {s['city']}, {s['state']} (OPIS {s['opis_id']})")
        self.stdout.write(self.style.SUCCESS(f"Wrote {out}"))

    def _geocode(self, missing, overrides_path) -> int:
        client = ORSClient(settings.ORS_API_KEY, settings.ORS_BASE_URL, settings.ORS_TIMEOUT_SECONDS)
        existing = read_overrides(overrides_path)
        pairs = sorted({(s["city"], s["state"]) for s in missing})
        new_rows = []
        for city, state in pairs:
            result = client.geocode(f"{city}, {US_STATES[state]}, USA")
            time.sleep(1.0)  # stay well under the per-minute quota
            if result and result.country_code in ("US", "USA") and result.region_code == state:
                new_rows.append({"state": state, "city": city, "lat": result.lat, "lon": result.lon})
            else:
                self.stdout.write(f"  no confident match for {city}, {state}")
        rows = [{"state": s, "city": c, "lat": lat, "lon": lon} for (s, c), (lat, lon) in existing.items()]
        write_csv(overrides_path, ["state", "city", "lat", "lon"], rows + new_rows)
        return len(new_rows)

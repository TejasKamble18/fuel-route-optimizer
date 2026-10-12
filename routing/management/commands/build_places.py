from django.conf import settings
from django.core.management.base import BaseCommand

from routing.datasets import load_census_places, write_csv


class Command(BaseCommand):
    help = "Build data/us_places.csv from the Census Gazetteer places file."

    def add_arguments(self, parser):
        parser.add_argument("census_file", help="Path to *_Gaz_place_national.txt")
        parser.add_argument("--out", default=str(settings.PLACES_CSV))

    def handle(self, census_file, out, **options):
        rows = load_census_places(census_file)
        write_csv(out, ["state", "name", "lat", "lon"],
                  [{"state": s, "name": n, "lat": lat, "lon": lon} for s, n, lat, lon in rows])
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(rows)} places to {out}"))

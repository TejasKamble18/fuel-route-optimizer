import csv
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from django.conf import settings


@dataclass(frozen=True, eq=False)
class StationIndex:
    opis_ids: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    price: np.ndarray
    names: tuple
    addresses: tuple
    cities: tuple
    states: tuple

    def __len__(self) -> int:
        return len(self.opis_ids)

    @classmethod
    def from_rows(cls, rows) -> "StationIndex":
        rows = list(rows)
        return cls(
            opis_ids=np.array([int(r["opis_id"]) for r in rows], dtype=np.int64),
            lat=np.array([float(r["lat"]) for r in rows], dtype=float),
            lon=np.array([float(r["lon"]) for r in rows], dtype=float),
            price=np.array([float(r["price"]) for r in rows], dtype=float),
            names=tuple(r["name"] for r in rows),
            addresses=tuple(r["address"] for r in rows),
            cities=tuple(r["city"] for r in rows),
            states=tuple(r["state"] for r in rows),
        )

    @classmethod
    def from_csv(cls, path) -> "StationIndex":
        with open(path, newline="", encoding="utf-8") as f:
            return cls.from_rows(csv.DictReader(f))

    def describe(self, i: int) -> dict:
        return {
            "opis_id": int(self.opis_ids[i]),
            "name": self.names[i],
            "address": self.addresses[i],
            "city": self.cities[i],
            "state": self.states[i],
            "lat": round(float(self.lat[i]), 5),
            "lon": round(float(self.lon[i]), 5),
        }


@lru_cache(maxsize=1)
def get_station_index() -> StationIndex:
    return StationIndex.from_csv(settings.STATIONS_CSV)

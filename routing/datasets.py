"""Offline data preparation: clean the fuel CSV and attach coordinates."""
import csv
import re

from .us_states import US_STATES

_SUFFIX = re.compile(
    r"\s+(city and borough|consolidated government|metropolitan government|metro government|"
    r"unified government|urban county|city|town|township|village|borough|municipality|cdp|"
    r"plantation|corporation)$"
)
_ABBREVIATIONS = {"st": "saint", "ste": "sainte", "mt": "mount", "ft": "fort"}


def normalise_place(name: str, *, census: bool = False) -> str:
    """Comparable form of a place name. census=True also drops Census place-type suffixes."""
    s = name.strip().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[-/]", " ", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if census:
        s = _SUFFIX.sub("", s)
    s = " ".join(_ABBREVIATIONS.get(w, w) for w in s.split())
    return re.sub(r"\bmc (\w)", r"mc\1", s)


def clean_fuel_rows(rows) -> list[dict]:
    best: dict[int, dict] = {}
    for raw in rows:
        r = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
        state = r.get("State", "").upper()
        if state not in US_STATES:
            continue
        try:
            opis_id = int(r["OPIS Truckstop ID"])
            price = float(r["Retail Price"])
        except (KeyError, ValueError):
            continue
        if price <= 0:
            continue
        current = best.get(opis_id)
        if current is None:
            best[opis_id] = {
                "opis_id": opis_id, "name": r["Truckstop Name"], "address": r["Address"],
                "city": r["City"], "state": state, "price": price,
            }
        elif price < current["price"]:
            current["price"] = price
    return [best[k] for k in sorted(best)]


def load_census_places(path) -> list[tuple[str, str, float, float]]:
    """Read the Census Gazetteer places file (pipe-delimited) into (state, name, lat, lon)."""
    places: dict[tuple[str, str], tuple[float, float]] = {}
    aliases: dict[tuple[str, str], tuple[float, float]] = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="|"):
            r = {k.strip(): (v or "").strip() for k, v in r.items()}
            state = r["USPS"]
            if state not in US_STATES:
                continue
            coords = (float(r["INTPTLAT"]), float(r["INTPTLONG"]))
            name = normalise_place(r["NAME"], census=True)
            places.setdefault((state, name), coords)
            raw = r["NAME"].lower()
            if "-" in raw:  # "Athens-Clarke County ..." is also known as "Athens"
                aliases.setdefault((state, normalise_place(raw.split("-")[0], census=True)), coords)
            if name.endswith(" city"):  # "Boise City city" is also "Boise"
                aliases.setdefault((state, name[: -len(" city")]), coords)
    for key, coords in aliases.items():
        places.setdefault(key, coords)
    return [(s, n, lat, lon) for (s, n), (lat, lon) in sorted(places.items())]


def read_places(path) -> dict[tuple[str, str], tuple[float, float]]:
    with open(path, newline="", encoding="utf-8") as f:
        return {(r["state"], r["name"]): (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)}


def read_overrides(path) -> dict[tuple[str, str], tuple[float, float]]:
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return {
                (r["state"], normalise_place(r["city"])): (float(r["lat"]), float(r["lon"]))
                for r in csv.DictReader(f)
            }
    except FileNotFoundError:
        return {}


def attach_coordinates(stations, places, overrides):
    located, missing = [], []
    for s in stations:
        key = (s["state"], normalise_place(s["city"]))
        coords = overrides.get(key) or places.get(key)
        if coords:
            located.append({**s, "lat": coords[0], "lon": coords[1]})
        else:
            missing.append(s)
    return located, missing


def write_csv(path, fieldnames, rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

"""Fuel-aware routing using one Census batch geocode and one OSRM route request."""

import csv
import io
import json
import math
import re
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "fuel-prices.csv"
CACHE_FILE = BASE_DIR / "data" / "city-coordinates.json"
RANGE_MILES = 500.0
MPG = 10.0
EARTH_MILES = 3958.7613
STATE_CODES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
_stations = None
_city_coords = None
_lock = threading.Lock()


class RouteError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _load_stations():
    global _stations
    if _stations is not None:
        return _stations
    if not DATA_FILE.exists():
        raise RouteError("Fuel price data is missing from the project.", 500)
    stations = []
    with DATA_FILE.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            try:
                city, state = row["City"].strip(), row["State"].strip().upper()
                price = float(row["Retail Price"])
                if city and state in STATE_CODES and math.isfinite(price) and price > 0:
                    stations.append({
                        "id": row["OPIS Truckstop ID"].strip(),
                        "name": row["Truckstop Name"].strip(),
                        "address": row["Address"].strip(),
                        "city": city,
                        "state": state,
                        "price": price,
                    })
            except (KeyError, ValueError, TypeError):
                continue
    if not stations:
        raise RouteError("Fuel price data contains no usable stations.", 500)
    _stations = stations
    return stations


def _city_key(city, state):
    return f"{re.sub(r'[^a-z0-9]+', ' ', city.lower()).strip()}|{state.upper()}"


def _read_cache():
    global _city_coords
    if _city_coords is None:
        try:
            _city_coords = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _city_coords = {}
    return _city_coords


def _csv_field(value):
    return '"' + str(value).replace('"', '""') + '"'


def _geocode_city_batch(cities):
    """Resolve missing station cities together; cache each result locally."""
    with _lock:
        cache = _read_cache()
        missing = [city for city in cities if _city_key(*city) not in cache]
        if not missing:
            return cache, 0
        if len(missing) > 9998:
            raise RouteError("Fuel station dataset exceeds the Census batch-geocoder limit.", 503)

        rows = []
        for index, (city, state) in enumerate(missing):
            # A street anchor gives the geocoder a usable point inside the town.
            rows.append(",".join((str(index), _csv_field("1 Main St"), _csv_field(city), state, "")))
        body = "\n".join(rows).encode("utf-8")
        boundary = f"----SpotterFuelRoute{int(time.time() * 1000)}"
        chunks = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"benchmark\"\r\n\r\nPublic_AR_Current\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"addressFile\"; filename=\"fuel-cities.csv\"\r\nContent-Type: text/csv\r\n\r\n".encode(),
            body,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        request = Request(
            "https://geocoding.geo.census.gov/geocoder/locations/addressbatch",
            data=b"".join(chunks),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "SpotterFuelRouteAssessment/1.0"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=25) as response:
                result_text = response.read().decode("utf-8-sig")
        except HTTPError as exc:
            raise RouteError(f"Census geocoding failed (HTTP {exc.code}). Try again shortly.", 502) from exc
        except (URLError, TimeoutError) as exc:
            raise RouteError("Census geocoding timed out. Please retry the route.", 504) from exc

        results = list(csv.reader(io.StringIO(result_text)))
        for city in missing:
            cache[_city_key(*city)] = None
        for row in results:
            if len(row) < 6:
                continue
            try:
                index = int(row[0])
                matched = row[2].strip().lower()
                if 0 <= index < len(missing) and matched == "match" and row[5].strip():
                    lon, lat = (float(value) for value in row[5].split(","))
                    cache[_city_key(*missing[index])] = [lat, lon]
            except (ValueError, IndexError):
                continue
        _city_coords = cache
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
        except OSError:
            pass
        return cache, 1


def _geocode_trip_inputs(start, finish):
    missing = []
    parsed = []
    for label, text in (("start", start), ("finish", finish)):
        match = re.fullmatch(r"\s*(.+?)\s*,\s*([A-Za-z]{2})\s*", text)
        if not match or match.group(2).upper() not in STATE_CODES:
            raise RouteError(f"{label.title()} must be a US city and two-letter state, such as Denver, CO.")
        city, state = match.group(1).strip(), match.group(2).upper()
        parsed.append((city, state))
        missing.append((city, state))
    return parsed


def _haversine(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_MILES * math.asin(min(1, math.sqrt(h)))


def _route(start, finish):
    coords = f"{start[1]},{start[0]};{finish[1]},{finish[0]}"
    query = urlencode({"overview": "full", "geometries": "geojson", "steps": "false"})
    request = Request(
        f"https://router.project-osrm.org/route/v1/driving/{coords}?{query}",
        headers={"Accept": "application/json", "User-Agent": "SpotterFuelRouteAssessment/1.0"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RouteError(f"OSRM routing failed (HTTP {exc.code}). Try again shortly.", 502) from exc
    except (URLError, TimeoutError) as exc:
        raise RouteError("The routing service timed out. Please retry.", 504) from exc
    routes = data.get("routes") or []
    if data.get("code") != "Ok" or not routes:
        raise RouteError("No driving route was found between those US cities.", 422)
    route = routes[0]
    return route["geometry"]["coordinates"], float(route["distance"]) / 1609.344


def _project_station(station, coordinates):
    """Return route distance and lateral distance for the nearest route segment."""
    point = (station["lat"], station["lon"])
    lengths = [_haversine((a[1], a[0]), (b[1], b[0])) for a, b in zip(coordinates, coordinates[1:])]
    total = sum(lengths)
    walked = 0.0
    best = None
    for index, (a, b) in enumerate(zip(coordinates, coordinates[1:])):
        mid_lat = math.radians((a[1] + b[1] + point[0]) / 3)
        scale_x = math.cos(mid_lat) * 69.0
        ax, ay = a[0] * scale_x, a[1] * 69.0
        bx, by = b[0] * scale_x, b[1] * 69.0
        px, py = point[1] * scale_x, point[0] * 69.0
        dx, dy = bx - ax, by - ay
        denominator = dx * dx + dy * dy
        fraction = 0 if denominator == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / denominator))
        distance = math.hypot(px - (ax + fraction * dx), py - (ay + fraction * dy))
        if best is None or distance < best[0]:
            best = (distance, walked + fraction * lengths[index])
        walked += lengths[index]
    return best[1] * (total and 1.0 or 0.0), best[0], total


def _fuel_plan(stations, coordinates, route_miles, start, finish):
    candidates = []
    projected_cities = {}
    geometry_length = sum(_haversine((a[1], a[0]), (b[1], b[0])) for a, b in zip(coordinates, coordinates[1:]))
    if geometry_length <= 0:
        raise RouteError("The routing service returned invalid route geometry.", 502)
    for station in stations:
        key = _city_key(station["city"], station["state"])
        location = _read_cache().get(key)
        if not location:
            continue
        station["lat"], station["lon"] = location
        if key not in projected_cities:
            projected_cities[key] = _project_station(station, coordinates)[:2]
        along, lateral = projected_cities[key]
        if lateral <= 18:
            station["routeMile"] = along
            candidates.append(station)
    if not candidates:
        raise RouteError("No fuel stations could be matched near this route. Check that the city geocoder has completed and retry.", 422)

    # OSRM distance can differ from geometry length; scale projections to route miles.
    for station in candidates:
        station["routeMile"] = min(route_miles, max(0, station["routeMile"] * route_miles / geometry_length))

    # Collapse nearby stations to the cheapest option at approximately each mile.
    bins = {}
    for station in candidates:
        mile = round(station["routeMile"])
        current = bins.get(mile)
        if current is None or station["price"] < current["price"]:
            bins[mile] = station
    ordered = sorted(bins.values(), key=lambda station: station["routeMile"])
    start_options = [
        station for station in ordered
        if station["routeMile"] <= 3 and _haversine((station["lat"], station["lon"]), start) <= 10
    ]
    if not start_options:
        raise RouteError("No listed fuel station was found within 10 miles of the starting city.", 422)
    start_point = min(start_options, key=lambda station: station["price"])
    start_point = dict(start_point, routeMile=0.0)
    nodes = [start_point] + [s for s in ordered if 3 < s["routeMile"] < route_miles - 1]
    nodes.append({"routeMile": route_miles, "terminal": True})
    # Dynamic programming minimizes purchase cost. Each purchase covers the miles to
    # the next chosen station; stops farther than the vehicle's 500-mile range are forbidden.
    costs = [math.inf] * len(nodes)
    previous = [None] * len(nodes)
    costs[0] = 0.0
    for target in range(1, len(nodes)):
        for source in range(target):
            distance = nodes[target]["routeMile"] - nodes[source]["routeMile"]
            if distance <= 0 or distance > RANGE_MILES or not math.isfinite(costs[source]):
                continue
            value = costs[source] + (distance / MPG) * nodes[source]["price"]
            if value < costs[target]:
                costs[target], previous[target] = value, source
    if not math.isfinite(costs[-1]):
        raise RouteError("The route has a gap greater than 500 miles between reachable fuel stations.", 422)
    path = []
    cursor = len(nodes) - 1
    while cursor is not None:
        path.append(nodes[cursor])
        cursor = previous[cursor]
    path.reverse()
    visible = []
    for index, station in enumerate(path[:-1]):
        next_station = path[index + 1]
        gallons = (next_station["routeMile"] - station["routeMile"]) / MPG
        visible.append({
            "id": station["id"], "name": station["name"], "address": station["address"],
            "city": station["city"], "state": station["state"], "pricePerGallon": station["price"],
            "latitude": station["lat"], "longitude": station["lon"],
            "routeMile": round(station["routeMile"], 1), "gallonsToNextLeg": round(gallons, 2),
        })
    return visible, costs[-1], path[0]


def plan_trip(start_text, finish_text):
    start_text = str(start_text or "").strip()[:160]
    finish_text = str(finish_text or "").strip()[:160]
    if not start_text or not finish_text:
        raise RouteError("Both start and finish locations are required.")
    start_city, finish_city = _geocode_trip_inputs(start_text, finish_text)
    stations = _load_stations()
    cities = {(station["city"], station["state"]) for station in stations}
    cities.update((start_city, finish_city))
    cache, geocode_calls = _geocode_city_batch(sorted(cities))
    start = cache.get(_city_key(*start_city))
    finish = cache.get(_city_key(*finish_city))
    if not start or not finish:
        raise RouteError("Could not locate one of those US cities. Use a city and two-letter state abbreviation.", 422)
    coordinates, route_miles = _route(start, finish)
    if route_miles <= 0:
        raise RouteError("The routing service returned a zero-length route.", 422)
    stops, total_cost, start_station = _fuel_plan(stations, coordinates, route_miles, start, finish)
    return {
        "start": {"label": start_text, "latitude": start[0], "longitude": start[1]},
        "finish": {"label": finish_text, "latitude": finish[0], "longitude": finish[1]},
        "route": {"distanceMiles": round(route_miles, 1), "coordinates": [[lat, lon] for lon, lat in coordinates]},
        "vehicle": {"maxRangeMiles": RANGE_MILES, "milesPerGallon": MPG},
        "fuel": {"totalGallons": round(route_miles / MPG, 2), "totalEstimatedCost": round(total_cost, 2), "currency": "USD", "startFuelPricePerGallon": start_station["price"]},
        "stops": stops,
        "externalApiCalls": {"censusBatchGeocoding": geocode_calls, "osrmRouting": 1},
        "assumptions": ["Fuel cost is based on the supplied retail prices and 10 MPG.", "The vehicle begins with an empty tank and buys enough fuel at each selected stop for the next leg.", "Station coordinates use a Census geocode for 1 Main St in the listed city as a town-level location estimate."],
    }

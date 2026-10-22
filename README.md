# Fuelwise Route Planner

A separate Django implementation of the Backend Django Engineer fuel-routing assessment. It accepts US start and finish cities, returns an OpenStreetMap driving route, recommends cost-effective fuel stops subject to a 500-mile maximum leg, and estimates fuel spend at 10 MPG using the attached assessment dataset.

## Run locally

Requires Python 3.12+.

```powershell
cd fuel-route-assessment
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py manage.py runserver
```

Open `http://127.0.0.1:8000/`. The app uses bundled 2025 Census Gazetteer place centers to match fuel stations locally. It calls the Census batch geocoder only when a requested trip endpoint is missing from the local place file, and saves that result in `data/city-coordinates.json`. Each trip uses one OSRM routing request. Gazetteer points are approximate city centers, not exact station coordinates. A local geographic grid narrows route-segment checks without a separate vector database.

## API

`POST /api/route/`

```json
{
  "start": "Denver, CO",
  "finish": "Chicago, IL"
}
```

Returns route GeoJSON coordinates, distance, selected stations and prices, fuel estimate, and documented assumptions. `GET /api/health/` returns service configuration.

Example with `curl`:

```bash
curl -X POST http://127.0.0.1:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{"start":"Denver, CO","finish":"Chicago, IL"}'
```

## Cost model

The supplied CSV has 8,151 station records and 4,271 distinct city/state pairs. The bundled Gazetteer resolves incorporated places and census-designated places to representative town centers; station cities absent from the Gazetteer are skipped; the Census geocoder is reserved for missing trip endpoints. Stations are projected onto the OSRM route; stations within 18 miles of the route are considered. Dynamic programming chooses a sequence of fuel purchases with no leg over 500 miles, minimizing estimated dollars at the CSV price. The vehicle starts with an empty tank and buys enough fuel for each next leg. Coordinates are town-level estimates because the CSV does not contain station latitude/longitude.

## Free services

- [2025 Census Gazetteer](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.2025.html) for local city/place coordinates, with the [US Census Geocoder batch API](https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html) as a fallback.
- [OSRM routing API](https://project-osrm.org/docs/v26.6.1/http) for one driving route request.
- [OpenFreeMap](https://openfreemap.org/) Positron vector style via MapLibre GL JS for the map; the map displays OpenFreeMap, OpenMapTiles, and OpenStreetMap attribution.

The Census batch service is used only for missing trip endpoints, so a route does not wait for thousands of station-town lookups. A local grid index speeds up matching station city centers to route segments. For production, use exact station coordinates and a maintained routing service.

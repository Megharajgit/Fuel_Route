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

Open `http://127.0.0.1:8000/`. The first route request batch-geocodes the station cities through the US Census Geocoder and caches their coordinates in `data/city-coordinates.json`. Each route uses one OSRM request. Both services are free to use without an API key; the first request may take longer while the 4,271 unique station cities are geocoded.

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

The supplied CSV has 8,151 station records and 4,271 distinct city/state pairs. The Census batch geocoder resolves `1 Main St` in each city as a town-level coordinate estimate. Stations are projected onto the OSRM route; stations within 18 miles of the route are considered. Dynamic programming chooses a sequence of fuel purchases with no leg over 500 miles, minimizing estimated dollars at the CSV price. The vehicle starts with an empty tank and buys enough fuel for each next leg. A town-level coordinate is approximate; the CSV does not contain station latitude/longitude.

## Free services

- [US Census Geocoder batch API](https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html) for city coordinates.
- [OSRM routing API](https://project-osrm.org/docs/v26.6.1/http) for one driving route request.
- [OpenStreetMap tiles](https://www.openstreetmap.org/copyright) via Leaflet for the map.

The Census batch service accepts up to 10,000 records per request. Station coordinates are cached locally after the first successful batch. For a production deployment, warm the cache once before accepting user traffic and replace shared public services with hosted instances or a provider with a production service agreement.

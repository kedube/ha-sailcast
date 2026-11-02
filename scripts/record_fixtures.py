#!/usr/bin/env python3
"""Record the provider responses the tests run on.

The test spots are made-up places in San Diego, far from anywhere the
maintainer sails, so the recordings need no anonymizing. Large responses are
trimmed: station and zone lists keep only the San Diego area, and zone shapes
keep a few hundred points.

Usage: .venv/bin/python scripts/record_fixtures.py
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import math
from pathlib import Path
import ssl
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

import certifi

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
USER_AGENT = "SailCast tests (https://github.com/kedube/ha-sailcast)"
CONTEXT = ssl.create_default_context(cafile=certifi.where())

# Name, latitude, longitude, water type, tide station, current station.
SPOTS = (
    ("Harbor", 32.75, -117.27, "open_coast", "9410170", None),
    ("Bay", 32.68, -117.17, "bay", "9410166", "PCT0056_1"),
    ("River", 32.76, -117.24, "river", "9410196", None),
)
ZONES = ("PZZ740", "PZZ745")
NEAR_KM = 40

MODELS = "ecmwf_ifs,ncep_gfs_seamless,dwd_icon_seamless"
FORECAST_VARIABLES = (
    "wind_speed_10m,wind_gusts_10m,wind_direction_10m,temperature_2m,"
    "precipitation_probability,weather_code,visibility,cape"
)
MARINE_VARIABLES = "wave_height,wave_period,wave_direction,sea_surface_temperature"
COOPS = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
MDAPI = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi"
NWS = "https://api.weather.gov"


def get(url: str, params: dict[str, Any] | None = None) -> Any:
    """Return a URL's JSON, or the error body for a 4xx response."""
    if params:
        url += "?" + urllib.parse.urlencode(params, safe=",")
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
    )
    try:
        with urllib.request.urlopen(request, context=CONTEXT, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        if 400 <= err.code < 500:
            return json.load(err)
        raise


def save(name: str, data: Any) -> None:
    """Write a fixture."""
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"{path.name:44} {path.stat().st_size // 1024:5} KB")


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the distance between two points along the Earth's surface."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371 * math.asin(math.sqrt(a))


def near_spots(lat: float, lon: float) -> bool:
    """Return whether a point is near any test spot."""
    return any(distance_km(lat, lon, s[1], s[2]) <= NEAR_KM for s in SPOTS)


def thin(ring: list[list[float]], keep: int = 300) -> list[list[float]]:
    """Keep about `keep` points of a polygon ring, and its closing point."""
    step = max(1, len(ring) // keep)
    return [*ring[:-1:step], ring[-1]]


def main() -> None:
    """Record every fixture."""
    OUT.mkdir(exist_ok=True)
    today = datetime.now(UTC).strftime("%Y%m%d")
    lats = ",".join(str(spot[1]) for spot in SPOTS)
    lons = ",".join(str(spot[2]) for spot in SPOTS)

    save(
        "open_meteo_forecast",
        get(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": lats,
                "longitude": lons,
                "hourly": FORECAST_VARIABLES,
                "models": MODELS,
                "wind_speed_unit": "kn",
                "timeformat": "unixtime",
                "timezone": "GMT",
                "past_days": 1,
                "forecast_days": 7,
            },
        ),
    )
    marine = [spot for spot in SPOTS if spot[3] in ("open_coast", "bay")]
    save(
        "open_meteo_marine",
        get(
            "https://marine-api.open-meteo.com/v1/marine",
            {
                "latitude": ",".join(str(spot[1]) for spot in marine),
                "longitude": ",".join(str(spot[2]) for spot in marine),
                "hourly": MARINE_VARIABLES,
                "cell_selection": "sea",
                "timeformat": "unixtime",
                "timezone": "GMT",
                "past_days": 1,
                "forecast_days": 7,
            },
        ),
    )

    tide_params = {
        "product": "predictions",
        "application": "SailCast",
        "begin_date": today,
        "range": 240,
        "datum": "MLLW",
        "units": "metric",
        "time_zone": "gmt",
        "format": "json",
    }
    for station in sorted({spot[4] for spot in SPOTS}):
        for interval in ("h", "hilo"):
            save(
                f"noaa_tides_{station}_{interval}",
                get(COOPS, {**tide_params, "station": station, "interval": interval}),
            )
    for station_bin in sorted({spot[5] for spot in SPOTS if spot[5]}):
        station, bin_ = station_bin.split("_")
        save(
            f"noaa_currents_{station_bin}",
            get(
                COOPS,
                {
                    **tide_params,
                    "product": "currents_predictions",
                    "station": station,
                    "bin": bin_,
                    "units": "english",
                    "interval": "MAX_SLACK",
                },
            ),
        )

    bay = SPOTS[1]
    save(
        "noaa_tide_stations",
        get(
            f"{MDAPI}/tidepredstations.json",
            {"lat": bay[1], "lon": bay[2], "radius": 25},
        ),
    )
    currents = get(f"{MDAPI}/stations.json", {"type": "currentpredictions"})
    keys = ("id", "name", "lat", "lng", "type", "currbin", "depth")
    currents["stations"] = [
        {key: station[key] for key in keys}
        for station in currents["stations"]
        if near_spots(station["lat"], station["lng"])
    ]
    currents["count"] = len(currents["stations"])
    save("noaa_current_stations", currents)

    harbor = SPOTS[0]
    save(
        "nws_zones_harbor",
        get(f"{NWS}/zones", {"type": "coastal", "point": f"{harbor[1]},{harbor[2]}"}),
    )
    save(
        "nws_zones_bay",
        get(f"{NWS}/zones", {"type": "coastal", "point": f"{bay[1]},{bay[2]}"}),
    )
    points = get(f"{NWS}/points/{bay[1]},{bay[2]}")
    save("nws_points_bay", {"properties": {"cwa": points["properties"]["cwa"]}})
    coastal = get(f"{NWS}/zones", {"type": "coastal"})
    coastal["features"] = [
        {"properties": {key: zone["properties"][key] for key in ("id", "name", "cwa")}}
        for zone in coastal["features"]
        if zone["properties"]["id"].startswith(("PZZ6", "PZZ7"))
    ]
    save("nws_zones_coastal", coastal)
    for zone in ZONES:
        shape = get(f"{NWS}/zones/coastal/{zone}")
        geometry = shape["geometry"]
        if geometry["type"] == "Polygon":
            geometry["coordinates"] = [thin(ring) for ring in geometry["coordinates"]]
        else:
            geometry["coordinates"] = [
                [thin(ring) for ring in polygon] for polygon in geometry["coordinates"]
            ]
        save(
            f"nws_zone_{zone}",
            {
                "geometry": geometry,
                "properties": {"id": zone, "name": shape["properties"]["name"]},
            },
        )
    save("nws_alerts", get(f"{NWS}/alerts/active", {"zone": ",".join(ZONES)}))


if __name__ == "__main__":
    main()

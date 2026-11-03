#!/usr/bin/env python3
"""Record the provider responses the tests run on.

The test spots are made-up places in San Diego, far from anywhere the
maintainer sails, so the recordings need no anonymizing. Three more, in the
Solent, the Wadden Sea and on Lake Garda, test sources outside the US. Large
responses are trimmed: station and zone lists keep only the test spots'
areas, zone shapes keep a few hundred points, and map tiles keep only their
water. Canada's tide predictions can't be passed on under CHS's licence, and
WorldTides needs a key, so their tests use made-up predictions instead.

Readings from buoys and airports are cut to what a fetch at `--as-of` would
have seen, so they can line up with forecasts recorded earlier. Name groups to
record only those.

Usage: .venv/bin/python scripts/record_fixtures.py [--as-of TIME] [GROUP ...]
Groups: forecast, tides, stations, nws, observations, spread, shoreline, world,
meteoalarm
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import gzip
import json
import math
from pathlib import Path
import re
import ssl
import sys
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

import certifi

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from custom_components.sailcast.providers import (
    eccc,
    kartverket,
    meteoalarm,
    open_meteo,
    openfreemap,
    rws,
)

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
USER_AGENT = "SailCast tests (https://github.com/kedube/ha-sailcast)"
CONTEXT = ssl.create_default_context(cafile=certifi.where())

# Name, latitude, longitude, water type, tide station, current station.
SPOTS = (
    ("Harbor", 32.75, -117.27, "open_coast", "9410170", None),
    ("Bay", 32.68, -117.17, "bay", "9410166", "PCT0056_1"),
    ("River", 32.76, -117.24, "river", "9410196", None),
)
# The test spots' buoys and airports.
BUOYS = ("46258", "SDBC1")
AIRPORTS = ("KSAN", "KNZY")
# A buoy's readings: as much of the newest part of its file as SailCast reads.
BUOY_BYTES = 8192
# Map tiles cover this far around each spot, at this zoom.
SHORE_KM = openfreemap.REACH_KM
SHORE_ZOOM = openfreemap.ZOOM
ZONES = ("PZZ740", "PZZ745")
NEAR_KM = 40
# Name, latitude, longitude, water type: spots outside the US.
WORLD = (
    ("Solent", 50.785, -1.305, "bay"),
    ("Wadden", 53.18, 5.38, "bay"),
    ("Garda", 45.8, 10.83, "lake"),
)
# Dutch tides at Harlingen, Norwegian ones near Bergen, a lake's NWS alerts
# (Lake Tahoe, which gets Lake Wind Advisories), and a Canadian marine area.
RWS_STATION = "harlingen.waddenzee"
# MeteoAlarm's regions near the Wadden and Garda spots, and Vlissingen's,
# which had a warning in effect when they were recorded.
METEOALARM_REGIONS = ("NL801", "NL806", "NL809", "IT002", "IT003", "IT006")
BERGEN = (60.39, 5.32)
LAKE_PIN = (39.09, -120.04)
HALIFAX = (44.63, -63.55)

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


def post(url: str, body: Any) -> Any:
    """Return the JSON a URL answers a posted JSON body with."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, context=CONTEXT, timeout=60) as response:
        return json.load(response)


def get_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
    """Return a URL's body, unzipped."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(request, context=CONTEXT, timeout=60) as response:
        body = response.read()
    return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body


def save(name: str, data: Any) -> None:
    """Write a fixture."""
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"{path.name:44} {path.stat().st_size // 1024:5} KB")


def save_raw(name: str, data: bytes) -> None:
    """Write a fixture that isn't JSON, such as a buoy's text file or a tile."""
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"{name:44} {len(data) // 1024:5} KB")


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


def record_forecast(as_of: datetime) -> None:
    """Record the forecast and marine data for the spots."""
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


def record_tides(as_of: datetime) -> None:
    """Record ten days of tide and current predictions."""
    today = as_of.strftime("%Y%m%d")
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


def record_stations(as_of: datetime) -> None:
    """Record the tide and current stations near the spots."""
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


def record_nws(as_of: datetime) -> None:
    """Record the marine zones and the warnings in them."""
    harbor, bay = SPOTS[0], SPOTS[1]
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


def record_observations(as_of: datetime) -> None:
    """Record buoy and airport readings as of a time, and the forecast there."""
    stations = get_bytes("https://www.ndbc.noaa.gov/activestations.xml").decode()
    kept = [
        line
        for line in re.findall(r"<station [^>]*>", stations)
        if (lat := re.search(r'lat="([-0-9.]+)"', line))
        and (lon := re.search(r'lon="([-0-9.]+)"', line))
        and near_spots(float(lat[1]), float(lon[1]))
    ]
    save_raw(
        "ndbc_stations.xml",
        (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<stations created="{as_of:%Y-%m-%dT%H:%M:%S}UTC" count="{len(kept)}">\n'
            + "".join(f"  {line}\n" for line in kept)
            + "</stations>\n"
        ).encode(),
    )
    positions = {}
    for line in kept:
        station = re.search(r'id="([^"]+)"', line)[1].upper()  # type: ignore[index]
        lat = float(re.search(r'lat="([-0-9.]+)"', line)[1])  # type: ignore[index]
        lon = float(re.search(r'lon="([-0-9.]+)"', line)[1])  # type: ignore[index]
        positions[station] = (lat, lon)
    for buoy in BUOYS:
        # Lines are newest first. Keep the header and what was there at as_of.
        text = get_bytes(
            f"https://www.ndbc.noaa.gov/data/realtime2/{buoy}.txt",
            {"Range": "bytes=0-131071"},
        ).decode()
        lines = text.splitlines(keepends=True)
        header = [line for line in lines[:2] if line.startswith("#")]
        rows = [
            line
            for line in lines[len(header) : -1]
            if datetime(*map(int, line.split()[:5]), tzinfo=UTC) <= as_of
        ]
        body = "".join(header + rows).encode()[:BUOY_BYTES]
        save_raw(f"ndbc_{buoy}.txt", body)

    lats = [spot[1] for spot in SPOTS]
    lons = [spot[2] for spot in SPOTS]
    bbox = (
        f"{min(lats) - 0.3:.4f},{min(lons) - 0.3:.4f},"
        f"{max(lats) + 0.3:.4f},{max(lons) + 0.3:.4f}"
    )
    save(
        "aviationweather_stationinfo",
        get(
            "https://aviationweather.gov/api/data/stationinfo",
            {"bbox": bbox, "format": "json"},
        ),
    )
    reports = get(
        "https://aviationweather.gov/api/data/metar",
        {"ids": ",".join(AIRPORTS), "format": "json", "hours": 12},
    )
    latest = {}
    for report in reports:
        if report["obsTime"] <= as_of.timestamp():
            station = report["icaoId"]
            if station not in latest or report["obsTime"] > latest[station]["obsTime"]:
                latest[station] = report
    save("aviationweather_metar", [latest[station] for station in AIRPORTS])
    for report in latest.values():
        positions[report["icaoId"]] = (report["lat"], report["lon"])

    # The forecast where the buoys and airports are, in the order the tests use.
    places = [positions[station] for station in (*BUOYS, *AIRPORTS)]
    save(
        "open_meteo_nearby",
        get(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": ",".join(f"{lat:.4f}" for lat, _ in places),
                "longitude": ",".join(f"{lon:.4f}" for _, lon in places),
                "hourly": ",".join(open_meteo.NEARBY_VARIABLES),
                "models": MODELS,
                "wind_speed_unit": "kn",
                "timeformat": "unixtime",
                "timezone": "GMT",
                "past_days": 1,
                "forecast_days": 1,
            },
        ),
    )
    buoys = [positions[station] for station in BUOYS]
    save(
        "open_meteo_marine_buoys",
        get(
            "https://marine-api.open-meteo.com/v1/marine",
            {
                "latitude": ",".join(f"{lat:.4f}" for lat, _ in buoys),
                "longitude": ",".join(f"{lon:.4f}" for _, lon in buoys),
                "hourly": "wave_height,sea_surface_temperature",
                "cell_selection": "sea",
                "timeformat": "unixtime",
                "timezone": "GMT",
                "past_days": 1,
                "forecast_days": 1,
            },
        ),
    )
    print("positions:", json.dumps(positions))


def record_spread(as_of: datetime) -> None:
    """Record the ECMWF ensemble's wind spread at the spots."""
    save(
        "open_meteo_spread",
        get(
            "https://ensemble-api.open-meteo.com/v1/ensemble",
            {
                "latitude": ",".join(str(spot[1]) for spot in SPOTS),
                "longitude": ",".join(str(spot[2]) for spot in SPOTS),
                "hourly": "wind_speed_10m_spread",
                "models": "ecmwf_ifs025_ensemble_mean",
                "wind_speed_unit": "kn",
                "timeformat": "unixtime",
                "timezone": "GMT",
                "past_days": 1,
                "forecast_days": 7,
            },
        ),
    )


def record_shoreline(as_of: datetime) -> None:
    """Record the map tiles around the spots, keeping only their water."""
    tilejson = get(openfreemap.TILEJSON_URL)
    save("openfreemap_tilejson", {"tiles": tilejson["tiles"]})
    template = tilejson["tiles"][0]
    tiles = set()
    for spot in SPOTS:
        tiles.update(openfreemap.tiles_around(spot[1], spot[2], SHORE_KM, SHORE_ZOOM))
    for z, x, y in sorted(tiles):
        url = template.format(z=z, x=x, y=y)
        save_raw(
            f"tiles/{z}/{x}/{y}.pbf", openfreemap.only_layer(get_bytes(url), "water")
        )


def record_world(as_of: datetime) -> None:
    """Record the forecast, tides, warnings and shorelines for spots abroad."""
    points = {
        "latitude": ",".join(str(spot[1]) for spot in WORLD),
        "longitude": ",".join(str(spot[2]) for spot in WORLD),
        "timeformat": "unixtime",
        "timezone": "GMT",
        "past_days": 1,
        "forecast_days": 7,
    }
    save(
        "open_meteo_forecast_world",
        get(
            "https://api.open-meteo.com/v1/forecast",
            points
            | {
                "hourly": FORECAST_VARIABLES,
                "models": MODELS,
                "wind_speed_unit": "kn",
            },
        ),
    )
    save(
        "open_meteo_spread_world",
        get(
            "https://ensemble-api.open-meteo.com/v1/ensemble",
            points
            | {
                "hourly": "wind_speed_10m_spread",
                "models": "ecmwf_ifs025_ensemble_mean",
                "wind_speed_unit": "kn",
            },
        ),
    )
    sea = [spot for spot in WORLD if spot[3] != "lake"]
    sea_points = points | {
        "latitude": ",".join(str(spot[1]) for spot in sea),
        "longitude": ",".join(str(spot[2]) for spot in sea),
        "cell_selection": "sea",
    }
    save(
        "open_meteo_marine_world",
        get(
            "https://marine-api.open-meteo.com/v1/marine",
            sea_points | {"hourly": MARINE_VARIABLES},
        ),
    )
    solent = WORLD[0]
    save(
        "open_meteo_sea_level_solent",
        get(
            "https://marine-api.open-meteo.com/v1/marine",
            points
            | {
                "latitude": solent[1],
                "longitude": solent[2],
                "hourly": open_meteo.SEA_LEVEL_VARIABLE,
                "cell_selection": "sea",
            },
        ),
    )
    record_rws(as_of)
    begin = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
    for datatype, extra in (("tab", ""), ("pre", "&interval=60")):
        url = (
            f"{kartverket.API}?tide_request=locationdata&lat={BERGEN[0]:.4f}"
            f"&lon={BERGEN[1]:.4f}&fromtime={begin:%Y-%m-%dT%H:%M}"
            f"&totime={begin + timedelta(days=kartverket.DAYS):%Y-%m-%dT%H:%M}"
            f"&refcode=cd&tzone=0&lang=en&datatype={datatype}{extra}"
        )
        save_raw(f"kartverket_bergen_{datatype}.xml", get_bytes(url))
    save(
        "nws_alerts_lake",
        get(f"{NWS}/alerts/active", {"point": f"{LAKE_PIN[0]:.4f},{LAKE_PIN[1]:.4f}"}),
    )
    search = get(
        eccc.API,
        {
            "f": "json",
            "skipGeometry": "true",
            "bbox": f"{HALIFAX[1] - 0.01:.4f},{HALIFAX[0] - 0.01:.4f},"
            f"{HALIFAX[1] + 0.01:.4f},{HALIFAX[0] + 0.01:.4f}",
        },
    )
    save("eccc_areas_halifax", search)
    area = search["features"][0]["id"]
    save(
        f"eccc_area_{area}",
        get(f"{eccc.API}/{area}", {"f": "json", "skipGeometry": "true"}),
    )
    record_meteoalarm(as_of)
    # Only a lake's waves are worked out from its shoreline in the tests.
    tilejson = get(openfreemap.TILEJSON_URL)
    template = tilejson["tiles"][0]
    tiles = set()
    for spot in WORLD:
        if spot[3] == "lake":
            tiles.update(
                openfreemap.tiles_around(spot[1], spot[2], SHORE_KM, SHORE_ZOOM)
            )
    for z, x, y in sorted(tiles):
        url = template.format(z=z, x=x, y=y)
        save_raw(
            f"tiles/{z}/{x}/{y}.pbf", openfreemap.only_layer(get_bytes(url), "water")
        )


def record_meteoalarm(as_of: datetime) -> None:
    """Record MeteoAlarm's feeds for the spots' countries, and their warnings' text.

    The text is kept for warnings in the spots' regions, or whose outline
    holds the Solent's pin. MeteoAlarm's region outlines aren't openly
    licensed, so the tests use made-up ones with the same codes.
    """
    solent = WORLD[0]
    for country in ("NL", "UK", "IT"):
        text = get_bytes(
            meteoalarm.FEED_URL.format(slug=meteoalarm.COUNTRIES[country][0])
        ).decode()
        save_raw(f"meteoalarm_{country.lower()}.xml", text.encode())
        for warning in meteoalarm.parse_feed(text):
            if set(warning.regions) & set(METEOALARM_REGIONS) or meteoalarm.applies(
                warning, meteoalarm.Place((), ()), solent[1], solent[2]
            ):
                uuid = warning.link.rsplit("/", 1)[1]
                save_raw(f"meteoalarm_cap_{uuid}.xml", get_bytes(warning.link))


def record_rws(as_of: datetime) -> None:
    """Record Rijkswaterstaat's stations with tides, and Harlingen's tides."""
    catalogue = post(rws.CATALOGUE_URL, rws.CATALOGUE)
    stations = {station.id for station in rws.parse_stations(catalogue)}
    places = {
        item["Locatie_MessageID"]
        for item in catalogue["LocatieLijst"]
        if item["Code"] in stations
    }
    wanted = {
        item["AquoMetadata_MessageID"]
        for item in catalogue["AquoMetadataLijst"]
        if item.get("ProcesType") == "astronomisch"
        and item.get("Grootheid", {}).get("Code") == "WATHTE"
    }
    save(
        "rws_catalogue",
        {
            "Succesvol": catalogue["Succesvol"],
            "AquoMetadataLijst": [
                item
                for item in catalogue["AquoMetadataLijst"]
                if item["AquoMetadata_MessageID"] in wanted
            ],
            "AquoMetadataLocatieLijst": [
                link
                for link in catalogue["AquoMetadataLocatieLijst"]
                if link["AquoMetaData_MessageID"] in wanted
                and link["Locatie_MessageID"] in places
            ],
            "LocatieLijst": [
                item
                for item in catalogue["LocatieLijst"]
                if item["Locatie_MessageID"] in places
            ],
        },
    )
    begin = (as_of - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    period = {
        "Begindatumtijd": begin.strftime("%Y-%m-%dT%H:%M:%S.000+00:00"),
        "Einddatumtijd": (begin + timedelta(days=rws.DAYS)).strftime(
            "%Y-%m-%dT%H:%M:%S.000+00:00"
        ),
    }
    for name, metadata in (("heights", rws.EXTREMES), ("kinds", rws.KINDS)):
        save(
            f"rws_{RWS_STATION.split('.', maxsplit=1)[0]}_{name}",
            post(
                rws.DATA_URL,
                {
                    "Locatie": {"Code": RWS_STATION},
                    "AquoPlusWaarnemingMetadata": {"AquoMetadata": metadata},
                    "Periode": period,
                },
            ),
        )


GROUPS: dict[str, Callable[[datetime], None]] = {
    "forecast": record_forecast,
    "tides": record_tides,
    "stations": record_stations,
    "nws": record_nws,
    "observations": record_observations,
    "spread": record_spread,
    "shoreline": record_shoreline,
    "world": record_world,
    "meteoalarm": record_meteoalarm,
}


def main() -> None:
    """Record the fixtures in the groups asked for, or all of them."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--as-of", type=datetime.fromisoformat, default=None)
    parser.add_argument("groups", nargs="*", choices=[*GROUPS, []])
    args = parser.parse_args()
    as_of = (args.as_of or datetime.now(UTC)).astimezone(UTC)
    OUT.mkdir(exist_ok=True)
    for group in args.groups or GROUPS:
        GROUPS[group](as_of)


if __name__ == "__main__":
    main()

"""Write the panel demo's data from the recorded San Diego week.

The demo page (`npm run demo` in frontend/) answers the panel's commands with
these replies, so the panel can be checked without Home Assistant. They come
from the integration's own code, run on the recorded responses the tests use.

Run it with the development environment:

    .venv/bin/python scripts/demo_data.py
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from custom_components.sailcast.limits import BOAT_LIMITS, SKILL_WIND_LIMITS  # noqa: E402
from custom_components.sailcast.outlook import SpotConditions, compute  # noqa: E402
from custom_components.sailcast.planner import sail_status  # noqa: E402
from custom_components.sailcast.profiles import (  # noqa: E402
    AutoCalendar,
    Boat,
    Profiles,
    Sailor,
    SizeClass,
    Skill,
    Spot,
    WaterType,
)
from custom_components.sailcast.providers import (  # noqa: E402
    ProviderError,
    noaa_coops,
    nws,
    open_meteo,
)
from custom_components.sailcast.storage import PlannedSail  # noqa: E402
from custom_components.sailcast.timeline import build, daylight  # noqa: E402
from custom_components.sailcast.week import week  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
OUTPUT = ROOT / "frontend" / "demo" / "data.json"
# When the fixtures were recorded: 2:36 PM in San Diego.
NOW = datetime(2026, 11, 2, 22, 36, tzinfo=UTC)
ZONE = ZoneInfo("America/Los_Angeles")

# Made-up spots in San Diego, as in the tests. The harbor's zone is the one
# with the recorded Small Craft Advisory, so the demo shows a warning.
SPOTS = (
    Spot(
        id="harbor",
        name="Harbor",
        latitude=32.75,
        longitude=-117.27,
        radius=12_000,
        water_type=WaterType.OPEN_COAST,
        offshore=("ne", "e", "se"),
        exposed=("sw", "w", "nw"),
        tide_station="9410170",
        marine_zone="PZZ745",
        source_names={
            "tide_station": "SAN DIEGO",
            "marine_zone": "Waters from San Mateo Point to Mexico, 10 to 60 nm out",
        },
    ),
    Spot(
        id="bay",
        name="Bay",
        latitude=32.68,
        longitude=-117.17,
        radius=10_000,
        water_type=WaterType.BAY,
        offshore=("ne", "e"),
        exposed=("s", "sw"),
        tide_station="9410166",
        current_station="PCT0056_1",
        marine_zone="PZZ740",
        source_names={
            "tide_station": "U.S. Quarantine Station, S.D. Bay",
            "current_station": "North Island",
            "marine_zone": "Coastal waters from San Mateo Point to the Mexican Border",
        },
    ),
    Spot(
        id="river",
        name="River",
        latitude=32.76,
        longitude=-117.24,
        radius=8_000,
        water_type=WaterType.RIVER,
        exposed=("w",),
        tide_station="9410196",
        marine_zone="PZZ740",
        source_names={
            "tide_station": "Mission Bay",
            "marine_zone": "Coastal waters from San Mateo Point to the Mexican Border",
        },
    ),
)
BOATS = (
    Boat(
        id="keelboat",
        name="Day sailer",
        size_class=SizeClass.SMALL_KEELBOAT,
        length=6.096,
    ),
    Boat(id="cruiser", name="Cruiser", size_class=SizeClass.CRUISER, length=10.363),
)
SAILORS = (
    Sailor(
        id="alex",
        name="Alex",
        skill=Skill.INTERMEDIATE,
        boats=("keelboat", "cruiser"),
        days=("sat", "sun"),
        start="09:00:00",
        auto_calendar=AutoCalendar(
            calendar="calendar.family",
            days=("sat", "sun"),
            min_score=60,
            ahead=6,
            spots=("harbor", "bay", "river"),
        ),
    ),
    Sailor(
        id="sam",
        name="Sam",
        skill=Skill.BEGINNER,
        boats=("keelboat",),
        days=("mon", "tue", "wed", "thu", "fri", "sat", "sun"),
    ),
)
CALENDARS = [
    {
        "entity_id": "calendar.family",
        "name": "Family",
        "via": "Local calendar",
        "update": True,
        "delete": True,
    },
    {
        "entity_id": "calendar.club",
        "name": "Sailing club",
        "via": "CalDAV",
        "update": False,
        "delete": False,
    },
]


def fixture(name: str) -> Any:
    """Return a recorded response."""
    return json.loads((FIXTURES / f"{name}.json").read_text())


def conditions() -> dict[str, SpotConditions]:
    """Build each spot's week from the recorded responses."""
    forecasts = open_meteo.parse_forecast(fixture("open_meteo_forecast"), 3)
    marine = open_meteo.parse_marine(fixture("open_meteo_marine"), 2)
    currents = noaa_coops.parse_currents(
        fixture("noaa_currents_PCT0056_1"), "PCT0056_1"
    )
    alerts = nws.parse_alerts(fixture("nws_alerts"), {"PZZ740", "PZZ745"})
    today = NOW.astimezone(ZONE).date()
    result = {}
    for index, spot in enumerate(SPOTS):
        station = spot.tide_station or ""
        try:
            hourly = noaa_coops.parse_tide_heights(
                fixture(f"noaa_tides_{station}_h"), station
            )
        except ProviderError:
            # Subordinate stations only have highs and lows.
            hourly = ()
        tides = noaa_coops.Tides(
            station=station,
            events=noaa_coops.parse_tide_events(
                fixture(f"noaa_tides_{station}_hilo"), station
            ),
            hourly=hourly,
        )
        days = [
            daylight(spot.latitude, spot.longitude, today + timedelta(days=n), ZONE)
            for n in range(7)
        ]
        spot_alerts = tuple(alert for alert in alerts if alert.zone == spot.marine_zone)
        spot_currents = currents if spot.current_station else None
        hours = build(
            forecast=forecasts[index],
            days=days,
            marine=marine[index] if spot.open_water else None,
            tides=tides,
            currents=spot_currents,
            alerts=spot_alerts,
        )
        result[spot.id] = SpotConditions(
            spot=spot,
            hours=tuple(hours),
            days=tuple(days),
            tide_events=tides.events,
            current_events=spot_currents.events if spot_currents else (),
            alerts=spot_alerts,
        )
    return result


def main() -> None:
    """Write the replies the demo answers with."""
    profiles = Profiles(
        spots={spot.id: spot for spot in SPOTS},
        boats={boat.id: boat for boat in BOATS},
        sailors={sailor.id: sailor for sailor in SAILORS},
    )
    spots = conditions()
    results = compute(profiles, spots)
    # Saturday's river window, in Alex's own calendar.
    sail = PlannedSail(
        id="demo1",
        sailor="alex",
        boat="keelboat",
        spot="river",
        calendar="calendar.family",
        start=datetime(2026, 11, 7, 21, tzinfo=UTC),
        end=datetime(2026, 11, 8, tzinfo=UTC),
        title="Sailing: River",
        auto=True,
        uid="demo-event",
        score=79,
    )
    planned = [
        sail.as_dict()
        | {"status": sail_status(sail, results, NOW).as_dict(), "can_delete": True}
    ]
    forecasts = {}
    for (sailor_id, spot_id), outlook in results.outlooks.items():
        spot = profiles.spots[spot_id]
        for boat in outlook.boats:
            forecasts[f"{spot_id}|{sailor_id}|{boat.boat.id}"] = week(
                outlook, boat, spots[spot_id], NOW
            ) | {
                "fetched": NOW.replace(minute=5).isoformat(),
                "sources": {
                    key: {"id": value, "name": spot.source_names.get(key)}
                    if (value := getattr(spot, key))
                    else None
                    for key in ("tide_station", "current_station", "marine_zone")
                },
                "planned": [item for item in planned if item["sailor"] == sailor_id],
            }
    config = profiles.as_dict() | {
        "limits": {
            size.value: {
                "wind": limits.wind,
                "gust": limits.gust,
                "wave": limits.wave,
                "ideal_wind": limits.ideal_wind,
            }
            for size, limits in BOAT_LIMITS.items()
        },
        "skills": {skill.value: limit for skill, limit in SKILL_WIND_LIMITS.items()},
        "calendars": CALENDARS,
        "users": [
            {"id": "user-alex", "name": "Alex"},
            {"id": "user-sam", "name": "Sam"},
        ],
    }
    data = {
        "now": NOW.isoformat(),
        "time_zone": str(ZONE),
        "config": config,
        "forecasts": forecasts,
        "planned": {"planned": planned, "skipped": {"alex": [], "sam": []}},
    }
    OUTPUT.write_text(json.dumps(data, default=_json, separators=(",", ":")))
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size // 1024} KB)")


def _json(value: Any) -> Any:
    """Turn dataclasses and enums into JSON."""
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return str(value)


if __name__ == "__main__":
    main()

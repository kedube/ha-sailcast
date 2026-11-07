"""The week the panel shows for a sailor in one boat at one spot.

Today's earlier hours keep their conditions for the charts, but a day's
windows, score and ratings count only the hours still to come that the boat
can sail in, as the panel shows them: its daylight hours, or every hour with
navigation lights. Values are in the timeline's units (knots, meters and °C)
and times in UTC; the panel converts them to the user's units and time zone.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime
from typing import Any

from .advice import advise
from .nowcast import Observation, latest
from .outlook import (
    BoatOutlook,
    HourOutlook,
    Outlook,
    SpotConditions,
    day_windows,
    sails,
)
from .profiles import SizeClass
from .rating import Rating
from .scoring import Slot, Window, best_window, confidence, day_score, steady_level
from .summary import Summary, hours_between, summarize
from .timeline import HOUR, Hour


def week(
    outlook: Outlook, boat: BoatOutlook, conditions: SpotConditions, now: datetime
) -> dict[str, Any]:
    """Return a sailor's week in a boat at a spot, for the panel."""
    zone = conditions.days[0].zone if conditions.days else None
    hours = conditions.hours
    days = []
    for day in conditions.days:
        indexes = [
            index
            for index, hour in enumerate(hours)
            if hour.start.astimezone(zone).date() == day.date
        ]
        ahead = [
            index
            for index in indexes
            if sails(boat.boat, hours[index]) and hours[index].start + HOUR > now
        ]
        slots = [
            Slot(hours[index].start, score, boat.hours[index].available)
            for index in ahead
            if (score := boat.hours[index].score) is not None
        ]
        windows = day_windows(boat.boat, slots, day)
        best = best_window(windows)
        agreement = confidence([hours[index] for index in ahead])
        summary = summarize([hours[index] for index in ahead])
        sailor_hours = outlook.hours_on(day.date)
        days.append(
            {
                "date": day.date.isoformat(),
                "sunrise": day.sunrise.isoformat(),
                "sunset": day.sunset.isoformat(),
                "over": not ahead,
                "available": any(boat.hours[index].available for index in ahead),
                # The sailor's hours that day, None if they don't sail, and
                # whether they were set for this date.
                "hours": None if sailor_hours is None else asdict(sailor_hours),
                "changed": day.date in outlook.changes,
                "score": day_score(slots, windows),
                "confidence": agreement[0] if agreement else None,
                "spread": agreement[1] if agreement else None,
                "windows": [_window(window, hours) for window in windows],
                "best": windows.index(best) if best else None,
                "sizes": {
                    size.value: _size(
                        [outlook.sizes[size][index] for index in ahead],
                        [hours[index] for index in ahead],
                    )
                    for size in SizeClass
                    if ahead
                },
                "summary": _summary(summary),
                "tides": [
                    {
                        "time": event.time.isoformat(),
                        "height": event.height,
                        "high": event.high,
                    }
                    for event in conditions.tide_events
                    if event.time.astimezone(zone).date() == day.date
                ],
                "advice": [
                    {
                        "key": advice.key,
                        "icon": advice.icon,
                        "values": dict(advice.values),
                        "hot": advice.hot,
                    }
                    for advice in advise(
                        conditions.spot,
                        boat.boat.size_class,
                        outlook.sailor.skill,
                        day,
                        [hours[index] for index in ahead],
                        tides=conditions.tide_events,
                        lights=boat.boat.lights,
                    )
                ],
            }
        )
    first, last = (hours[0].start, hours[-1].start + HOUR) if hours else (now, now)
    return {
        "spot": outlook.spot.id,
        "sailor": outlook.sailor.id,
        "boat": boat.boat.id,
        "lights": boat.boat.lights,
        "now": now.isoformat(),
        "days": days,
        "hours": [
            _hour(
                item,
                {
                    size.value: outlook.sizes[size][index].level.key
                    for size in SizeClass
                },
            )
            for index, item in enumerate(boat.hours)
        ],
        "current_events": [
            {"time": event.time.isoformat(), "speed": event.speed}
            for event in conditions.current_events
            if first - HOUR <= event.time <= last + HOUR
        ],
        "alerts": [
            {
                "event": alert.event,
                "start": alert.start.isoformat(),
                "end": alert.end.isoformat(),
                "headline": alert.headline,
                "issued": alert.issued.isoformat() if alert.issued else None,
                "issuer": alert.issuer,
                "details": alert.details,
            }
            for alert in conditions.alerts
        ],
    }


def _hour(item: HourOutlook, sizes: dict[str, str]) -> dict[str, Any]:
    hour, rating = item.hour, item.rating
    return {
        "time": hour.start.isoformat(),
        "daylight": hour.daylight,
        "available": item.available,
        "wind": hour.wind,
        "gust": hour.gust,
        "direction": round(hour.wind_direction),
        "models": list(hour.wind_models),
        "temperature": hour.temperature,
        "rain_chance": hour.rain_chance,
        "weather_code": hour.weather_code,
        "visibility": hour.visibility,
        "visibility_measured": hour.visibility_measured,
        "wave_height": hour.wave_height,
        "wave_period": hour.wave_period,
        "wave_source": hour.wave_source,
        "wind_spread": hour.wind_spread,
        "adjusted": list(hour.adjusted),
        "water_temperature": hour.water_temperature,
        "tide_height": hour.tide_height,
        "tide_rising": hour.tide_rising,
        "current": hour.current,
        "current_direction": hour.current_direction,
        "rating": rating.level.key,
        "reasons": [reason.as_dict() for reason in rating.reasons],
        "score": item.score,
        "sizes": sizes,
        "warnings": [alert.event for alert in hour.alerts],
    }


def readings_now(observations: Sequence[Observation], now: datetime) -> dict[str, Any]:
    """Return each field's freshest reading and every source's newest, for the panel."""
    return {
        "fields": {
            key: {
                "value": reading.value,
                "time": reading.time.isoformat(),
                "kind": observation.kind,
                "station": observation.station,
            }
            for key, (observation, reading) in latest(observations, now).items()
        },
        "sources": [
            {
                "kind": observation.kind,
                "station": observation.station,
                "newest": newest.isoformat()
                if (newest := observation.readings.latest)
                else None,
            }
            for observation in observations
        ],
    }


def _window(window: Window, hours: Sequence[Hour]) -> dict[str, Any]:
    summary = summarize(hours_between(hours, window.start, window.end))
    return {
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
        "score": window.score,
        "hours": window.hours,
        "wind_low": summary.wind_low if summary else None,
        "wind_high": summary.wind_high if summary else None,
        "gust": summary.gust if summary else None,
        "direction": round(summary.direction) if summary else None,
    }


def _size(ratings: Sequence[Rating], hours: Sequence[Hour]) -> dict[str, Any]:
    """Return a boat size's day: its steady and worst rating, and why."""
    levels = [rating.level for rating in ratings]
    worst = max(levels)
    at = levels.index(worst)
    return {
        "best": steady_level(levels).key,
        "worst": worst.key,
        "worst_at": hours[at].start.isoformat(),
        "reasons": [item.as_dict() for item in ratings[at].reasons],
    }


def _summary(summary: Summary | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    return {
        "wind_low": summary.wind_low,
        "wind_high": summary.wind_high,
        "gust": summary.gust,
        "direction": round(summary.direction),
        "trend": summary.trend,
        "waves": list(summary.waves) if summary.waves else None,
        "temperature": list(summary.temperature) if summary.temperature else None,
        "rain_chance": summary.rain_chance,
        "weather_code": summary.weather_code,
        "visibility": summary.visibility,
        "water_temperature": summary.water_temperature,
    }

"""Coordinators: one per data source, shared by every spot, and one for results.

The forecast is fetched hourly, marine data every three hours, the ensemble's
spread every six, tide and current predictions once a day (kept on disk), and
NWS warnings every five minutes. Buoys are read every 20 minutes and airports
every 30, with an hourly forecast where they are. Whenever one of them
changes, and at the top of each hour, the results are worked out again in a
worker thread, with your own sensors' latest readings.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, tzinfo
import logging
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN
from .nowcast import AIRPORT, BUOY, SENSORS, Observation
from .outlook import Results, SpotConditions, compute
from .planner import Planner
from .profiles import Profiles, Spot
from .providers import (
    ProviderError,
    Readings,
    ha_entity,
    metar,
    ndbc,
    noaa_coops,
    nws,
    open_meteo,
)
from .providers.noaa_coops import CurrentEvent, Currents, TideEvent, Tides
from .shoreline import DATA_SHORELINES, Shoreline, Shorelines
from .storage import SailCastStore
from .timeline import Alert, build, daylight, localize

LOGGER = logging.getLogger(__package__)

FORECAST_INTERVAL: Final = timedelta(hours=1)
SLOW_FORECAST_INTERVAL: Final = timedelta(hours=3)
MARINE_INTERVAL: Final = timedelta(hours=3)
PREDICTION_INTERVAL: Final = timedelta(hours=1)
ALERT_INTERVAL: Final = timedelta(minutes=5)
SPREAD_INTERVAL: Final = timedelta(hours=6)
# Readings are checked this often; each kind is fetched on its own schedule.
OBSERVATION_INTERVAL: Final = timedelta(minutes=10)
BUOY_EVERY: Final = timedelta(minutes=20)
AIRPORT_EVERY: Final = timedelta(minutes=30)
NEARBY_EVERY: Final = timedelta(hours=1)
BUOY_MARINE_EVERY: Final = timedelta(hours=3)
DAYS: Final = 7

# Open-Meteo's free tier allows 10,000 calls a day per IP address, shared with
# anything else on it, such as Home Assistant's own Open-Meteo weather.
SLOW_DOWN_AT: Final = 8000

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.predictions"

DATA_BUDGET: HassKey[Budget] = HassKey(f"{DOMAIN}_budget")


@dataclass
class Budget:
    """Open-Meteo calls counted so far today (UTC).

    It's kept while Home Assistant runs, so reloading the entry after a
    settings change doesn't start the count again.
    """

    day: date | None = None
    calls: float = 0.0

    def add(self, calls: float) -> None:
        """Count calls, starting again each day."""
        today = dt_util.utcnow().date()
        if today != self.day:
            self.day, self.calls = today, 0.0
        self.calls += calls

    @property
    def today(self) -> float:
        """Return the calls counted today."""
        return self.calls if self.day == dt_util.utcnow().date() else 0.0


class SourceCoordinator[DataT](DataUpdateCoordinator[DataT]):
    """Fetches one source for every spot."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        profiles: Profiles,
        name: str,
        interval: timedelta,
    ) -> None:
        """Set up the source."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"SailCast {name}",
            update_interval=interval,
            always_update=False,
        )
        self.profiles = profiles
        self.session = async_get_clientsession(hass)


class ForecastCoordinator(SourceCoordinator[dict[str, open_meteo.Forecast]]):
    """The three models' forecast for every spot, in one request."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        profiles: Profiles,
        budget: Budget,
    ) -> None:
        """Set up the forecast."""
        super().__init__(hass, entry, profiles, "forecast", FORECAST_INTERVAL)
        self.budget = budget
        # When the forecast in use was fetched.
        self.fetched: datetime | None = None

    async def _async_update_data(self) -> dict[str, open_meteo.Forecast]:
        spots = list(self.profiles.spots.values())
        if not spots:
            return {}
        try:
            forecasts = await open_meteo.async_get_forecast(
                self.session, [(spot.latitude, spot.longitude) for spot in spots]
            )
        except ProviderError as err:
            raise UpdateFailed(f"Couldn't get the forecast: {err}") from err
        self.budget.add(open_meteo.forecast_calls(len(spots)))
        self.fetched = dt_util.utcnow()
        self.update_interval = (
            SLOW_FORECAST_INTERVAL
            if self.budget.today >= SLOW_DOWN_AT
            else FORECAST_INTERVAL
        )
        return {
            spot.id: forecast for spot, forecast in zip(spots, forecasts, strict=True)
        }


class MarineCoordinator(SourceCoordinator[dict[str, open_meteo.Marine]]):
    """Waves and water temperature for the spots on open water."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        profiles: Profiles,
        budget: Budget,
    ) -> None:
        """Set up marine data."""
        super().__init__(hass, entry, profiles, "marine", MARINE_INTERVAL)
        self.budget = budget

    async def _async_update_data(self) -> dict[str, open_meteo.Marine]:
        spots = [spot for spot in self.profiles.spots.values() if spot.open_water]
        if not spots:
            return {}
        try:
            marine = await open_meteo.async_get_marine(
                self.session, [(spot.latitude, spot.longitude) for spot in spots]
            )
        except ProviderError as err:
            raise UpdateFailed(f"Couldn't get marine data: {err}") from err
        self.budget.add(open_meteo.marine_calls(len(spots)))
        return {spot.id: data for spot, data in zip(spots, marine, strict=True)}


@dataclass(frozen=True, slots=True)
class Predictions:
    """Tide and current predictions, by station."""

    tides: dict[str, Tides] = field(default_factory=dict)
    currents: dict[str, Currents] = field(default_factory=dict)


class SpreadCoordinator(SourceCoordinator[dict[str, open_meteo.Spread]]):
    """The ECMWF ensemble's wind spread at every spot, in one request."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        profiles: Profiles,
        budget: Budget,
    ) -> None:
        """Set up the spread."""
        super().__init__(hass, entry, profiles, "spread", SPREAD_INTERVAL)
        self.budget = budget

    async def _async_update_data(self) -> dict[str, open_meteo.Spread]:
        spots = list(self.profiles.spots.values())
        if not spots:
            return {}
        try:
            spreads = await open_meteo.async_get_spread(
                self.session, [(spot.latitude, spot.longitude) for spot in spots]
            )
        except ProviderError as err:
            raise UpdateFailed(f"Couldn't get the ensemble's spread: {err}") from err
        self.budget.add(open_meteo.spread_calls(len(spots)))
        return {spot.id: spread for spot, spread in zip(spots, spreads, strict=True)}


@dataclass(frozen=True, slots=True)
class Station:
    """A buoy or airport a spot reads, and where it is, if that's known."""

    kind: str
    id: str
    position: tuple[float, float] | None = None

    @property
    def key(self) -> str:
        """Return the key its readings are kept under."""
        return f"{self.kind}:{self.id}"


def stations(profiles: Profiles) -> dict[str, Station]:
    """Return every spot's buoy and airport, by key."""
    found: dict[str, Station] = {}
    for spot in profiles.spots.values():
        for kind, station in ((BUOY, spot.buoy), (AIRPORT, spot.airport)):
            if station:
                item = Station(kind, station, spot.source_points.get(kind))
                found.setdefault(item.key, item)
    return found


@dataclass(frozen=True, slots=True)
class Observed:
    """The latest readings at each buoy and airport, and the forecast there.

    Each is kept by station key, such as "buoy:46258".
    """

    readings: dict[str, Readings] = field(default_factory=dict)
    forecasts: dict[str, open_meteo.Forecast] = field(default_factory=dict)
    marine: dict[str, open_meteo.Marine] = field(default_factory=dict)


class ObservationCoordinator(SourceCoordinator[Observed]):
    """Readings from every spot's buoy and airport, and the forecast where they are.

    Each kind is fetched on its own schedule. `failing` says since when a
    station's readings couldn't be fetched, for repair issues, and `started`
    is when this began trying.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        profiles: Profiles,
        budget: Budget,
    ) -> None:
        """Set up the readings."""
        super().__init__(hass, entry, profiles, "readings", OBSERVATION_INTERVAL)
        self.budget = budget
        self.started = dt_util.utcnow()
        self.failing: dict[str, datetime] = {}
        self._fetched: dict[str, datetime] = {}

    def _due(self, key: str, every: timedelta, now: datetime) -> bool:
        fetched = self._fetched.get(key)
        return fetched is None or now - fetched >= every

    async def _async_update_data(self) -> Observed:
        now = dt_util.utcnow()
        wanted = stations(self.profiles)
        if not wanted:
            return Observed()
        old = self.data or Observed()
        readings = {k: v for k, v in old.readings.items() if k in wanted}
        attempts = failures = 0
        for station in wanted.values():
            if station.kind != BUOY or not self._due(station.key, BUOY_EVERY, now):
                continue
            attempts += 1
            try:
                readings[station.key] = await ndbc.async_get_readings(
                    self.session, station.id
                )
            except ProviderError as err:
                failures += 1
                LOGGER.debug("Couldn't read buoy %s: %s", station.id, err)
                self.failing.setdefault(station.key, now)
                continue
            self._fetched[station.key] = now
            self.failing.pop(station.key, None)
        airports = [station for station in wanted.values() if station.kind == AIRPORT]
        if airports and self._due(AIRPORT, AIRPORT_EVERY, now):
            attempts += 1
            try:
                reports = await metar.async_get_reports(
                    self.session, [station.id for station in airports]
                )
            except ProviderError as err:
                failures += 1
                LOGGER.debug("Couldn't get airport reports: %s", err)
                reports = None
            else:
                self._fetched[AIRPORT] = now
            for station in airports:
                if reports and station.id in reports:
                    readings[station.key] = reports[station.id]
                    self.failing.pop(station.key, None)
                else:
                    self.failing.setdefault(station.key, now)
        if attempts and failures == attempts:
            raise UpdateFailed("Couldn't get readings from any buoy or airport")
        forecasts, marine = await self._async_forecasts(wanted, old, now)
        return Observed(readings, forecasts, marine)

    async def _async_forecasts(
        self, wanted: dict[str, Station], old: Observed, now: datetime
    ) -> tuple[dict[str, open_meteo.Forecast], dict[str, open_meteo.Marine]]:
        """Return the forecast at each placed station, fetching it when due."""
        placed = {
            station.key: station.position
            for station in wanted.values()
            if station.position is not None
        }
        buoys = {
            key: position
            for key, position in placed.items()
            if wanted[key].kind == BUOY
        }
        forecasts = {k: v for k, v in old.forecasts.items() if k in placed}
        marine = {k: v for k, v in old.marine.items() if k in buoys}
        every = NEARBY_EVERY * 3 if self.budget.today >= SLOW_DOWN_AT else NEARBY_EVERY
        if placed and (
            self._due("nearby", every, now) or placed.keys() - forecasts.keys()
        ):
            try:
                found = await open_meteo.async_get_nearby(
                    self.session, list(placed.values())
                )
            except ProviderError as err:
                LOGGER.debug("Couldn't get the forecast at buoys and airports: %s", err)
            else:
                self.budget.add(open_meteo.nearby_calls(len(placed)))
                self._fetched["nearby"] = now
                forecasts = dict(zip(placed, found, strict=True))
        if buoys and (
            self._due("buoy_marine", BUOY_MARINE_EVERY, now)
            or buoys.keys() - marine.keys()
        ):
            try:
                found_marine = await open_meteo.async_get_buoy_marine(
                    self.session, list(buoys.values())
                )
            except ProviderError as err:
                LOGGER.debug("Couldn't get marine data at buoys: %s", err)
            else:
                self.budget.add(open_meteo.buoy_calls(len(buoys)))
                self._fetched["buoy_marine"] = now
                marine = dict(zip(buoys, found_marine, strict=True))
        return forecasts, marine


class PredictionCoordinator(SourceCoordinator[Predictions]):
    """Tide and current predictions, fetched once a day and kept on disk.

    NOAA throttles heavy users, so each station is fetched at most once a
    day, for ten days. Predictions from an earlier day are used while they
    still cover the coming week. `failing` says since when a station has
    failed, by "tide:<id>" or "current:<id>", for repair issues.
    """

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, profiles: Profiles
    ) -> None:
        """Set up predictions."""
        super().__init__(hass, entry, profiles, "predictions", PREDICTION_INTERVAL)
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._fetched: dict[str, date] = {}
        self._loaded = False
        self.failing: dict[str, datetime] = {}

    async def _async_update_data(self) -> Predictions:
        if not self._loaded:
            await self._async_load()
        spots = self.profiles.spots.values()
        tide_stations = {spot.tide_station for spot in spots if spot.tide_station}
        current_stations = {
            spot.current_station for spot in spots if spot.current_station
        }
        old = self.data or Predictions()
        tides = {k: v for k, v in old.tides.items() if k in tide_stations}
        currents = {k: v for k, v in old.currents.items() if k in current_stations}
        today = dt_util.utcnow().date()
        # Start a day early, so the timeline can begin at local midnight.
        begin = today - timedelta(days=1)
        wanted = {f"tide:{station}" for station in tide_stations} | {
            f"current:{station}" for station in current_stations
        }
        self._fetched = {k: v for k, v in self._fetched.items() if k in wanted}
        self.failing = {k: v for k, v in self.failing.items() if k in wanted}
        now = dt_util.utcnow()
        failures = []
        for station in sorted(tide_stations):
            if self._fetched.get(f"tide:{station}") == today:
                continue
            try:
                tides[station] = await noaa_coops.async_get_tides(
                    self.session, station, begin
                )
            except ProviderError as err:
                failures.append(str(err))
                self.failing.setdefault(f"tide:{station}", now)
                continue
            self._fetched[f"tide:{station}"] = today
            self.failing.pop(f"tide:{station}", None)
        for station in sorted(current_stations):
            if self._fetched.get(f"current:{station}") == today:
                continue
            try:
                currents[station] = await noaa_coops.async_get_currents(
                    self.session, station, begin
                )
            except ProviderError as err:
                failures.append(str(err))
                self.failing.setdefault(f"current:{station}", now)
                continue
            self._fetched[f"current:{station}"] = today
            self.failing.pop(f"current:{station}", None)
        predictions = Predictions(tides, currents)
        if predictions != self.data:
            await self._store.async_save(_to_store(predictions, self._fetched))
        if failures and len(failures) == len(tide_stations) + len(current_stations):
            raise UpdateFailed(f"Couldn't get predictions: {failures[0]}")
        return predictions

    async def _async_load(self) -> None:
        """Read the predictions kept from earlier days."""
        self._loaded = True
        stored = await self._store.async_load()
        if not stored:
            return
        try:
            predictions, self._fetched = _from_store(stored)
        except KeyError, TypeError, ValueError:
            LOGGER.warning("Ignoring unreadable saved tide predictions")
            return
        self.data = predictions


class AlertCoordinator(SourceCoordinator[tuple[Alert, ...]]):
    """Official marine warnings for every spot's zone, in one request."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, profiles: Profiles
    ) -> None:
        """Set up warnings."""
        super().__init__(hass, entry, profiles, "warnings", ALERT_INTERVAL)

    async def _async_update_data(self) -> tuple[Alert, ...]:
        zones = {
            spot.marine_zone
            for spot in self.profiles.spots.values()
            if spot.marine_zone
        }
        if not zones:
            return ()
        try:
            return tuple(await nws.async_get_alerts(self.session, zones))
        except ProviderError as err:
            raise UpdateFailed(f"Couldn't get marine warnings: {err}") from err


class ResultsCoordinator(DataUpdateCoordinator[Results]):
    """Ratings, scores and windows, worked out again when a source changes."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        profiles: Profiles,
        sources: Sources,
    ) -> None:
        """Set up the results."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name="SailCast results",
            request_refresh_debouncer=Debouncer(
                hass, LOGGER, cooldown=1.0, immediate=True
            ),
        )
        self.entry = entry
        self.profiles = profiles
        self.sources = sources

    @callback
    def async_follow_sources(self) -> list[CALLBACK_TYPE]:
        """Refresh whenever a source changes, and return the unsubscribers."""
        return [
            source.async_add_listener(self._async_source_changed)
            for source in self.sources.all
        ]

    @callback
    def _async_source_changed(self) -> None:
        self.entry.async_create_background_task(
            self.hass, self.async_request_refresh(), "sailcast results"
        )

    @callback
    def async_new_hour(self, now: datetime) -> None:
        """Move "now" on to the next hour."""
        self._async_source_changed()

    async def _async_update_data(self) -> Results:
        zone = dt_util.get_default_time_zone()
        now = dt_util.utcnow()
        today = now.astimezone(zone).date()
        # Sensors are read here, in the event loop, before the work moves to
        # a worker thread.
        sensors = {
            spot.id: ha_entity.read(self.hass, spot.sensors)
            for spot in self.profiles.spots.values()
            if spot.sensors
        }
        return await self.hass.async_add_executor_job(
            self._compute, today, zone, now, sensors
        )

    def _compute(
        self, today: date, zone: tzinfo, now: datetime, sensors: dict[str, Readings]
    ) -> Results:
        """Build each spot's timeline and every outlook, in a worker thread."""
        conditions = {
            spot.id: spot_conditions
            for spot in self.profiles.spots.values()
            if (
                spot_conditions := self.sources.conditions(
                    spot, today, zone, now, sensors.get(spot.id)
                )
            )
        }
        return compute(self.profiles, conditions)


@dataclass
class Sources:
    """The source coordinators, and each pin's shoreline."""

    forecast: ForecastCoordinator
    marine: MarineCoordinator
    predictions: PredictionCoordinator
    alerts: AlertCoordinator
    spread: SpreadCoordinator
    observations: ObservationCoordinator
    shorelines: Shorelines

    @property
    def all(self) -> tuple[SourceCoordinator[Any], ...]:
        """Return every source."""
        return (
            self.forecast,
            self.marine,
            self.predictions,
            self.alerts,
            self.spread,
            self.observations,
        )

    def shoreline(self, spot: Spot) -> Shoreline | None:
        """Return a spot's shoreline, if its pin has been measured."""
        return self.shorelines.get(spot.latitude, spot.longitude)

    def readings(
        self, spot: Spot, sensors: Readings | None = None
    ) -> tuple[Observation, ...]:
        """Return a spot's sources of readings: its sensors, buoy and airport."""
        observed = self.observations.data or Observed()
        found = []
        if spot.sensors:
            found.append(Observation(SENSORS, None, sensors or Readings()))
        for kind, station in ((BUOY, spot.buoy), (AIRPORT, spot.airport)):
            key = f"{kind}:{station}"
            if station and key in observed.readings:
                found.append(
                    Observation(
                        kind,
                        station,
                        observed.readings[key],
                        observed.forecasts.get(key),
                        observed.marine.get(key),
                    )
                )
        return tuple(found)

    def conditions(
        self,
        spot: Spot,
        today: date,
        zone: tzinfo,
        now: datetime,
        sensors: Readings | None = None,
    ) -> SpotConditions | None:
        """Return a spot's timeline for the coming week, if it has a forecast."""
        forecast = (self.forecast.data or {}).get(spot.id)
        if forecast is None:
            return None
        predictions = self.predictions.data or Predictions()
        tides = predictions.tides.get(spot.tide_station or "")
        currents = predictions.currents.get(spot.current_station or "")
        alerts = tuple(
            alert for alert in self.alerts.data or () if alert.zone == spot.marine_zone
        )
        days = [
            daylight(spot.latitude, spot.longitude, today + timedelta(days=n), zone)
            for n in range(DAYS)
        ]
        marine = (self.marine.data or {}).get(spot.id)
        hours = build(
            forecast=forecast,
            days=days,
            marine=marine,
            tides=tides,
            currents=currents,
            alerts=alerts,
            spread=(self.spread.data or {}).get(spot.id),
        )
        shoreline = self.shoreline(spot)
        measured = shoreline if shoreline and shoreline.on_water else None
        observations = self.readings(spot, sensors)
        hours, adjustments = localize(
            hours,
            now=now,
            forecast=forecast,
            marine=marine,
            observations=observations,
            open_water=spot.open_water,
            exposed=spot.exposed or (measured.exposed if measured else None),
            fetch=_fetch(spot, measured),
        )
        return SpotConditions(
            spot=spot,
            hours=tuple(hours),
            days=tuple(days),
            tide_events=tides.events if tides else (),
            current_events=currents.events if currents else (),
            alerts=alerts,
            observations=observations,
            adjustments=adjustments,
            shoreline=shoreline,
        )


def _fetch(spot: Spot, shoreline: Shoreline | None) -> Callable[[float], float] | None:
    """Return the open water upwind of a direction: set by hand, or measured."""
    if (by_hand := spot.fetch) is not None:
        return lambda _direction: by_hand
    return shoreline.fetch if shoreline else None


@dataclass
class SailCastData:
    """Everything SailCast keeps while its entry is loaded."""

    profiles: Profiles
    budget: Budget
    sources: Sources
    results: ResultsCoordinator
    planner: Planner

    @classmethod
    def create(
        cls,
        hass: HomeAssistant,
        entry: ConfigEntry,
        profiles: Profiles,
        store: SailCastStore,
    ) -> SailCastData:
        """Create the coordinators and planner for an entry."""
        budget = hass.data.setdefault(DATA_BUDGET, Budget())
        sources = Sources(
            forecast=ForecastCoordinator(hass, entry, profiles, budget),
            marine=MarineCoordinator(hass, entry, profiles, budget),
            predictions=PredictionCoordinator(hass, entry, profiles),
            alerts=AlertCoordinator(hass, entry, profiles),
            spread=SpreadCoordinator(hass, entry, profiles, budget),
            observations=ObservationCoordinator(hass, entry, profiles, budget),
            shorelines=hass.data.setdefault(DATA_SHORELINES, Shorelines(hass)),
        )
        results = ResultsCoordinator(hass, entry, profiles, sources)
        return cls(
            profiles=profiles,
            budget=budget,
            sources=sources,
            results=results,
            planner=Planner(hass, store, profiles, results),
        )


type SailCastConfigEntry = ConfigEntry[SailCastData]


def _to_store(predictions: Predictions, fetched: dict[str, date]) -> dict[str, Any]:
    return {
        "fetched": {key: day.isoformat() for key, day in fetched.items()},
        "tides": {
            station: {
                "events": [
                    [event.time.isoformat(), event.height, event.high]
                    for event in tides.events
                ],
                "hourly": [[when.isoformat(), height] for when, height in tides.hourly],
            }
            for station, tides in predictions.tides.items()
        },
        "currents": {
            station: {
                "flood": currents.flood_direction,
                "ebb": currents.ebb_direction,
                "events": [
                    [event.time.isoformat(), event.speed] for event in currents.events
                ],
            }
            for station, currents in predictions.currents.items()
        },
    }


def _from_store(stored: dict[str, Any]) -> tuple[Predictions, dict[str, date]]:
    tides = {
        station: Tides(
            station=station,
            events=tuple(
                TideEvent(datetime.fromisoformat(when), height, high)
                for when, height, high in data["events"]
            ),
            hourly=tuple(
                (datetime.fromisoformat(when), height)
                for when, height in data["hourly"]
            ),
        )
        for station, data in stored["tides"].items()
    }
    currents = {
        station: Currents(
            station=station,
            events=tuple(
                CurrentEvent(datetime.fromisoformat(when), speed)
                for when, speed in data["events"]
            ),
            flood_direction=data["flood"],
            ebb_direction=data["ebb"],
        )
        for station, data in stored["currents"].items()
    }
    fetched = {key: date.fromisoformat(day) for key, day in stored["fetched"].items()}
    return Predictions(tides, currents), fetched

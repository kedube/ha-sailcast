/** The parts of Home Assistant's `hass` object the panel uses. */
export interface HomeAssistant {
  language: string;
  locale?: {
    language?: string;
    number_format?: string;
    time_format?: string;
  };
  themes?: { darkMode?: boolean };
  user?: { id: string; is_admin: boolean; name?: string };
  config: {
    latitude: number;
    longitude: number;
    time_zone: string;
    unit_system: { length: string; temperature: string };
  };
  states?: Record<string, EntityState>;
  connection: Connection;
}

export interface EntityState {
  entity_id: string;
  state: string;
  attributes: { friendly_name?: string; device_class?: string; [key: string]: unknown };
}

export interface Connection {
  sendMessagePromise<T>(message: Record<string, unknown>): Promise<T>;
  subscribeMessage<T>(
    callback: (message: T) => void,
    subscribe: Record<string, unknown>,
  ): Promise<() => Promise<void>>;
}

/** A safety rating, from best to worst. */
export type Level = "good" | "caution" | "not_recommended" | "dangerous";
export type SizeClass = "dinghy" | "small_keelboat" | "cruiser" | "large_cruiser";
export type Skill = "beginner" | "intermediate" | "advanced";
export type WaterType = "open_coast" | "bay" | "river" | "lake";
export type Theme = "auto" | "day" | "night";
export type View = "week" | "day" | "map" | "settings";
export type SourceKey = "tide_station" | "current_station" | "marine_zone" | "buoy" | "airport";
/** Readings a spot can take from your own sensors. */
export type SensorKey = "wind" | "gust" | "wind_direction" | "temperature" | "water_temperature";
export type ReadingKind = "sensors" | "buoy" | "airport";
/** Where an hour's waves come from: the ocean model, the model from a sheltered direction, or worked out from the fetch. */
export type WaveSource = "model" | "sheltered" | "estimate";
/** Who a spot's tides come from. "model" is the ocean model's rough sea level. */
export type TideProvider = "noaa" | "chs" | "rws" | "kartverket" | "worldtides" | "model";
/** Who a spot's official warnings come from. */
export type WarningProvider = "nws" | "eccc" | "meteoalarm";

export interface Spot {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  /** Meters. */
  radius: number;
  water_type: WaterType;
  offshore: string[];
  exposed: string[];
  tide_station: string | null;
  current_station: string | null;
  marine_zone: string | null;
  buoy: string | null;
  airport: string | null;
  sensors: Partial<Record<SensorKey, string>>;
  /** The open water upwind set by hand, in km, overriding the shoreline. */
  fetch: number | null;
  source_names: Partial<Record<SourceKey, string>>;
  /** Where the buoy and airport are. */
  source_points: Partial<Record<"buoy" | "airport", [number, number]>>;
}

export interface Boat {
  id: string;
  name: string;
  size_class: SizeClass;
  /** Meters. */
  length: number;
}

export interface Comfort {
  /** Knots. */
  ideal_low: number | null;
  ideal_high: number | null;
  /** °C. */
  coldest: number | null;
  rain: "avoid" | "some" | "any";
}

export interface AutoCalendar {
  calendar: string;
  days: string[];
  min_score: number;
  ahead: number;
  spots: string[];
}

export interface Sailor {
  id: string;
  name: string;
  skill: Skill;
  /** Boat IDs, the usual boat first. */
  boats: string[];
  days: string[];
  start: string | null;
  end: string | null;
  user: string | null;
  comfort: Comfort;
  auto_calendar: AutoCalendar | null;
}

export interface Limits {
  wind: [number, number];
  gust: [number, number];
  /** Meters. */
  wave: [number, number, number];
  ideal_wind: [number, number];
}

export interface CalendarInfo {
  entity_id: string;
  name: string;
  /** The integration it comes from, such as Local calendar. */
  via: string;
  update: boolean;
  delete: boolean;
}

/** The reply to `sailcast/config`. */
export interface SailCastConfig {
  spots: Spot[];
  boats: Boat[];
  sailors: Sailor[];
  limits: Record<SizeClass, Limits>;
  skills: Record<Skill, number | null>;
  calendars: CalendarInfo[];
  users: { id: string; name: string }[];
  /** Whether the AI summary is turned on, with AI Task set up. */
  ai: boolean;
}

export interface Preferences {
  spot?: string;
  sailor?: string;
  boat?: string;
  view?: string;
  theme?: string;
  calendar?: string;
}

export interface Reason {
  key: string;
  level: Level;
  values: Record<string, number | string>;
  modifier: boolean;
}

export interface Hour {
  time: string;
  daylight: boolean;
  available: boolean;
  wind: number;
  gust: number;
  direction: number;
  models: (number | null)[];
  temperature: number | null;
  rain_chance: number | null;
  weather_code: number | null;
  visibility: number | null;
  /** Whether the visibility was measured nearby, not forecast. */
  visibility_measured: boolean;
  wave_height: number | null;
  wave_period: number | null;
  wave_source: WaveSource | null;
  /** The ECMWF ensemble's spread: one standard deviation, in knots. */
  wind_spread: number | null;
  /** Fields that readings have nudged this hour. */
  adjusted: string[];
  water_temperature: number | null;
  tide_height: number | null;
  tide_rising: boolean | null;
  current: number | null;
  current_direction: number | null;
  rating: Level;
  reasons: Reason[];
  score: number | null;
  sizes: Record<SizeClass, Level>;
  warnings: string[];
}

export interface Window {
  start: string;
  end: string;
  score: number;
  hours: number;
  wind_low: number | null;
  wind_high: number | null;
  gust: number | null;
  direction: number | null;
}

export interface SizeDay {
  best: Level;
  worst: Level;
  worst_at: string;
  reasons: Reason[];
}

export interface Summary {
  wind_low: number;
  wind_high: number;
  gust: number;
  direction: number;
  trend: "building" | "easing" | null;
  waves: [number, number] | null;
  temperature: [number, number] | null;
  rain_chance: number | null;
  weather_code: number | null;
  visibility: number | null;
  water_temperature: number | null;
}

export interface TideTurn {
  time: string;
  /** Meters. */
  height: number;
  high: boolean;
}

export interface Advice {
  key: string;
  icon: string;
  values: Record<string, unknown>;
  hot: boolean;
}

export interface Day {
  date: string;
  sunrise: string;
  sunset: string;
  /** True once the day's daylight is over. */
  over: boolean;
  /** Whether the sailor is free at any daylight hour still to come. */
  available: boolean;
  score: number | null;
  confidence: "high" | "medium" | "low" | null;
  spread: number | null;
  windows: Window[];
  best: number | null;
  sizes: Partial<Record<SizeClass, SizeDay>>;
  summary: Summary | null;
  tides: TideTurn[];
  advice: Advice[];
  /** The AI summary written for this day in the panel's language, with AI on. */
  ai?: AiSummary | null;
}

export interface AiSummary {
  text: string;
  /** When it was written. */
  made: string;
  /** False once the ratings, windows or warnings it describes have changed. */
  current: boolean;
}

export interface SailStatus {
  rating: Level | null;
  score: number | null;
  worse: boolean;
  reasons: Reason[];
}

export interface PlannedSail {
  id: string;
  sailor: string;
  boat: string;
  spot: string;
  calendar: string;
  start: string;
  end: string;
  title: string;
  auto: boolean;
  watch: boolean;
  user: string | null;
  uid: string | null;
  score: number | null;
  worse: boolean;
  status: SailStatus;
  can_delete: boolean;
}

/** The reply to `sailcast/forecast`: a sailor's week in a boat at a spot. */
export interface Forecast {
  spot: string;
  sailor: string;
  boat: string;
  now: string;
  fetched: string | null;
  days: Day[];
  hours: Hour[];
  current_events: { time: string; speed: number }[];
  /** Official warnings; `issued`, `issuer` and `details` are shown where the provider asks for them. */
  alerts: {
    event: string;
    start: string;
    end: string;
    headline: string | null;
    issued: string | null;
    issuer: string | null;
    details: string | null;
  }[];
  planned: PlannedSail[];
  sources: Record<SourceKey, { id: string; name: string | null } | null> & {
    sensors: Partial<Record<SensorKey, string>>;
  };
  /** Who the tides come from: the datum heights are above, the station a provider chose, and any notice it asks to show. */
  tide: {
    provider: TideProvider;
    datum: string | null;
    station: string | null;
    notice: string | null;
  } | null;
  /**
   * Who the warnings come from; `at_pin` for alerts at the pin rather than a
   * zone, and `services` the national weather services MeteoAlarm's come from.
   */
  warnings: { provider: WarningProvider; at_pin: boolean; services: string[] } | null;
  readings: Readings;
  adjustments: Adjustment[];
  shoreline: { on_water: boolean; measured: string } | null;
}

/** One field's freshest reading, and who read it. */
export interface Reading {
  /** Knots for wind, degrees for directions, and SI units for the rest. */
  value: number;
  time: string;
  kind: ReadingKind;
  station: string | null;
}

/** What's been read at a spot: each field's freshest reading, and each source's newest. */
export interface Readings {
  fields: Partial<Record<string, Reading>>;
  sources: { kind: ReadingKind; station: string | null; newest: string | null }[];
}

/** How a reading moved the forecast: by its difference from the forecast there. */
export interface Adjustment {
  field: string;
  kind: ReadingKind;
  station: string | null;
  reading: number;
  time: string;
  difference: number;
}

/** The reply to `sailcast/settings/shoreline`: how far open water reaches each way. */
export interface Shoreline {
  on_water: boolean;
  /** Kilometers, every 3° clockwise from north. */
  rays: number[];
  measured: string;
  exposed: string[];
}

export interface PlannedList {
  planned: PlannedSail[];
  skipped: Record<string, string[]>;
}

export interface SourceChoice {
  id: string;
  name: string;
  /** What a station or zone is known by, shown with its name. */
  code: string | null;
  /** Kilometers; none for sources asked about the pin itself. */
  distance: number | null;
  /** Where a station is; zones have none. */
  latitude: number | null;
  longitude: number | null;
}

export interface SourceSuggestions {
  tide_station: SourceChoice[];
  current_station: SourceChoice[];
  marine_zone: SourceChoice[];
  buoy: SourceChoice[];
  airport: SourceChoice[];
  suggested: Record<SourceKey, string | null>;
  failed: boolean;
}

/**
 * The reply to `sailcast/wind_grid`: the wind on a grid, hour by hour from
 * the hour under way. Each hour has a value per point, a row at a time from
 * the south-west corner: speeds and gusts in knots, and directions in
 * degrees the wind comes from.
 */
export interface WindGrid {
  fetched: string;
  /** Whether it's older than SailCast would like, because it couldn't fetch another. */
  stale: boolean;
  south: number;
  west: number;
  north: number;
  east: number;
  rows: number;
  cols: number;
  /** The spots it covers. */
  spots: string[];
  times: string[];
  speed: (number | null)[][];
  gust: (number | null)[][];
  direction: (number | null)[][];
}

/** A settings change's result: the profile's ID, or what's wrong. */
export interface SaveResult {
  profile?: string;
  errors?: Record<string, string>;
  sailor?: string;
}

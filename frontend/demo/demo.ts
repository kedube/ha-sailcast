/**
 * The demo page: the panel with the recorded San Diego week, answered by a
 * stand-in for Home Assistant. Write its data first with
 * `.venv/bin/python scripts/demo_data.py` from the repository.
 *
 * Options: ?mode=night, ?units=metric, ?admin=0, ?empty, ?view=day or map,
 * and ?ai for the AI briefing: ?ai=slow while it's written, ?ai=stale after
 * the forecast changed, ?ai=fail when the provider fails.
 */
import "../src/sailcast-panel";
import type {
  Bounds,
  Briefing,
  BriefingPick,
  EntityState,
  Forecast,
  HomeAssistant,
  PlannedList,
  PlannedSail,
  SailCastConfig,
  Shoreline,
  WindGrid,
  WindView,
} from "../src/types";

interface DemoData {
  now: string;
  time_zone: string;
  config: SailCastConfig;
  forecasts: Record<string, Forecast>;
  planned: PlannedList;
  wind_grid: WindGrid;
  /** Each spot's shoreline, measured from the recorded map tiles. */
  shorelines: (Shoreline & { latitude: number; longitude: number })[];
}

// A weather station on the dock, for the spot editor's sensor pickers.
const STATES: Record<string, EntityState> = Object.fromEntries(
  (
    [
      ["sensor.dock_wind_speed", "Dock wind speed", "wind_speed"],
      ["sensor.dock_wind_gust", "Dock wind gust", "wind_speed"],
      ["sensor.dock_wind_direction", "Dock wind direction", "wind_direction"],
      ["sensor.dock_temperature", "Dock temperature", "temperature"],
    ] as const
  ).map(([entity_id, friendly_name, device_class]) => [
    entity_id,
    { entity_id, state: "0", attributes: { friendly_name, device_class } },
  ]),
);

const params = new URLSearchParams(location.search);
const listeners = new Set<() => void>();
const changed = () => listeners.forEach((listener) => listener());

/**
 * The wind over a map view. Inside the recorded grid, that grid; beyond it,
 * made-up wind on 15 points a side: each hour's average from the recording,
 * stronger to the south-west, from the recording's first direction.
 */
function madeUpView(data: DemoData, view: Bounds & { have?: string }): WindView {
  const recorded = data.wind_grid;
  // As SailCast does, a view may pass an edge by 1% of the grid's size.
  const tallSlack = (recorded.north - recorded.south) * 0.01;
  const wideSlack = (recorded.east - recorded.west) * 0.01;
  if (
    view.south >= recorded.south - tallSlack &&
    view.north <= recorded.north + tallSlack &&
    view.west >= recorded.west - wideSlack &&
    view.east <= recorded.east + wideSlack
  ) {
    return { grid: view.have === recorded.id ? null : recorded, retry: null };
  }
  const size = 15;
  const tall = (view.north - view.south) * 0.15;
  const wide = (view.east - view.west) * 0.15;
  const south = view.south - tall;
  const north = view.north + tall;
  const west = view.west - wide;
  const east = view.east + wide;
  const average = (hour: (number | null)[]): number => {
    const known = hour.filter((value): value is number => value !== null);
    return known.reduce((sum, value) => sum + value, 0) / Math.max(1, known.length);
  };
  const spread = (hours: (number | null)[][]): number[][] =>
    hours.map((hour) => {
      const base = average(hour);
      return Array.from({ length: size * size }, (_, index) => {
        const lean = (size - Math.floor(index / size)) / size - (index % size) / size;
        return Math.round(base * (1 + 0.3 * lean) * 10) / 10;
      });
    });
  return {
    grid: {
      ...recorded,
      id: `demo:${[south, west, north, east].join()}`,
      south,
      west,
      north,
      east,
      rows: size,
      cols: size,
      spots: data.config.spots
        .filter(
          (spot) =>
            spot.latitude >= south &&
            spot.latitude <= north &&
            spot.longitude >= west &&
            spot.longitude <= east,
        )
        .map((spot) => spot.id),
      speed: spread(recorded.speed),
      gust: spread(recorded.gust),
      direction: recorded.direction.map((hour) =>
        Array<number>(size * size).fill(hour.find((value) => value !== null) ?? 270),
      ),
    },
    retry: null,
  };
}

/**
 * What an AI might write for Alex's recorded week, in US units, following the
 * instructions SailCast gives it. Other sailors get placeholder text.
 */
const EXAMPLE = {
  sailor: "alex",
  headline: "Saturday afternoon on the River in the Day sailer is the pick of the week.",
  summary:
    "A Small Craft Advisory covers the Harbor from Tuesday 1 PM to Wednesday 4 AM, and a swell of 3 to 5 ft keeps the Harbor and the Bay at caution or worse all week. The River is sheltered from it: a light northwesterly builds to 5–6 kt each afternoon, with gusts in the mid-teens. The models agree closely, apart from a less certain Wednesday.",
  why: {
    "2026-11-07": "The best score of the week: northwest 5–6 kt on flat water, gusts to 15 kt.",
    "2026-11-06": "Almost as good, and it starts at noon.",
  } as Record<string, string>,
  days: {
    "2026-11-03":
      "You're not sailing today. The Small Craft Advisory starts at the Harbor at 1 PM.",
    "2026-11-04":
      "The River in the Day sailer from 1 PM until sunset scores 70. The Harbor is not recommended in the swell.",
    "2026-11-06":
      "The River from noon until sunset in the Day sailer (74), or 1 to 3 PM in the Cruiser (65).",
    "2026-11-07":
      "The week's best: the River from 1 PM until sunset in the Day sailer (80). The Harbor and the Bay stay at caution in the swell.",
    "2026-11-08": "A shorter window on the River, 1 to 3 PM in the Day sailer (68).",
  } as Record<string, string>,
  recheck: "Check again on Tuesday evening, since Wednesday's forecast is less certain.",
};

/**
 * A stand-in AI briefing: the sailor's best two windows across the recorded
 * spots and boats, with the example's text for Alex.
 */
function standInBriefing(data: DemoData, config: SailCastConfig, sailorId: string): Briefing {
  const sailor = config.sailors.find((item) => item.id === sailorId);
  const example = sailorId === EXAMPLE.sailor ? EXAMPLE : undefined;
  const found: BriefingPick[] = [];
  for (const spot of config.spots) {
    for (const boat of sailor?.boats ?? []) {
      const forecast = data.forecasts[`${spot.id}|${sailorId}|${boat}`];
      for (const day of forecast?.days ?? []) {
        for (const window of day.windows) {
          found.push({
            spot: spot.id,
            boat,
            date: day.date,
            start: window.start,
            end: window.end,
            score: window.score,
            why:
              example?.why[day.date] ??
              "Steady wind inside your limit, and the best score of the week.",
          });
        }
      }
    }
  }
  const picks = found.sort((a, b) => b.score - a.score).slice(0, 2);
  return {
    headline:
      example?.headline ?? "This is where the AI's headline goes: the best choice this week.",
    summary:
      example?.summary ??
      "And here two to four sentences that compare the days, spots and boats, written by the AI provider set up in Home Assistant, in your language.",
    picks,
    days:
      example?.days ??
      Object.fromEntries(
        picks.map((pick) => [pick.date, "A note about the day: the best spot, boat and time."]),
      ),
    recheck:
      example?.recheck ??
      "Check again on Friday evening, as the models disagree about the weekend.",
    made: data.now,
    current: true,
  };
}

async function start(): Promise<void> {
  const response = await fetch("/demo/data.json");
  if (!response.ok) {
    document.body.textContent =
      "Write the demo's data first: .venv/bin/python scripts/demo_data.py";
    return;
  }
  const data = (await response.json()) as DemoData;
  const config: SailCastConfig = {
    ...(params.has("empty") ? { ...data.config, spots: [], boats: [], sailors: [] } : data.config),
    // `?ai` shows the AI briefing, with a stand-in one.
    ai: params.has("ai"),
  };
  let planned = data.planned.planned;
  const preferences: Record<string, string | null> = {};

  const answer = (message: Record<string, unknown>): unknown => {
    const type = String(message.type).replace("sailcast/", "");
    switch (type) {
      case "config":
        return config;
      case "forecast": {
        const sailor = config.sailors.find((item) => item.id === message.sailor);
        const boat = (message.boat as string | undefined) ?? sailor?.boats[0];
        const forecast = data.forecasts[`${message.spot}|${message.sailor}|${boat}`];
        if (!forecast) throw { code: "not_found", message: "There's no forecast for that yet" };
        return { ...forecast, planned: planned.filter((sail) => sail.sailor === message.sailor) };
      }
      case "preferences/get":
        return params.has("view") ? { ...preferences, view: params.get("view") } : preferences;
      case "preferences/set":
        Object.assign(preferences, message);
        return preferences;
      case "planned/list":
        return { ...data.planned, planned };
      case "calendar/add": {
        const sail: PlannedSail = {
          id: `demo${Date.now()}`,
          sailor: String(message.sailor),
          boat: String(message.boat),
          spot: String(message.spot),
          calendar: String(message.calendar),
          start: String(message.start),
          end: String(message.end),
          title: String(message.title),
          auto: false,
          watch: Boolean(message.watch),
          user: null,
          uid: "demo",
          score: 80,
          worse: false,
          status: { rating: "good", score: 80, worse: false, reasons: [] },
          can_delete: true,
        };
        planned = [...planned, sail];
        setTimeout(changed, 50);
        return sail;
      }
      case "calendar/remove":
        planned = planned.filter((sail) => sail.id !== message.planned);
        setTimeout(changed, 50);
        return { deleted: true };
      case "settings/sources":
        return {
          tide_station: [
            {
              id: "9410170",
              name: "SAN DIEGO",
              distance: 2.4,
              latitude: 32.7142,
              longitude: -117.1736,
            },
            {
              id: "9410196",
              name: "MISSION BAY",
              distance: 4.0,
              latitude: 32.7633,
              longitude: -117.2267,
            },
          ],
          current_station: [
            {
              id: "PCT0056_1",
              name: "North Island",
              distance: 6.1,
              latitude: 32.7034,
              longitude: -117.2196,
            },
          ],
          marine_zone: [
            {
              id: "PZZ740",
              name: "Coastal waters to 10 nm",
              distance: 0,
              latitude: null,
              longitude: null,
            },
          ],
          buoy: [
            {
              id: "SDBC1",
              name: "9410170 - San Diego, CA",
              distance: 3.8,
              latitude: 32.714,
              longitude: -117.174,
            },
            {
              id: "46258",
              name: "Mission Bay West, CA (220)",
              distance: 22.1,
              latitude: 32.749,
              longitude: -117.502,
            },
          ],
          airport: [
            {
              id: "KNZY",
              name: "San Diego/North Island NAS",
              distance: 4.0,
              latitude: 32.6922,
              longitude: -117.2098,
            },
            {
              id: "KSAN",
              name: "San Diego Intl Arpt",
              distance: 6.8,
              latitude: 32.7364,
              longitude: -117.1973,
            },
          ],
          suggested: {
            tide_station: "9410170",
            current_station: null,
            marine_zone: "PZZ740",
            buoy: "SDBC1",
            airport: "KNZY",
          },
          failed: false,
        };
      case "settings/shoreline": {
        // The demo has the spots' own pins measured; others get the nearest.
        const [latitude, longitude] = [Number(message.latitude), Number(message.longitude)];
        const nearest = [...data.shorelines].sort(
          (a, b) =>
            Math.hypot(a.latitude - latitude, a.longitude - longitude) -
            Math.hypot(b.latitude - latitude, b.longitude - longitude),
        )[0];
        return nearest;
      }
      case "settings/save":
        return { profile: message.profile ?? "new" };
      case "settings/delete":
        return { profile: message.profile };
      case "planned/skipped":
        return message.days;
      case "hours":
        return { date: message.date };
      case "briefing": {
        const mode = params.get("ai");
        const briefing = standInBriefing(data, config, String(message.sailor));
        if (mode === "fail" && message.write) {
          throw { code: "ai_failed", message: "The AI provider didn't answer" };
        }
        if (mode === "stale") return { ...briefing, current: false };
        if (mode === "slow" && message.write) {
          return new Promise((resolve) => window.setTimeout(() => resolve(briefing), 4000));
        }
        return briefing;
      }
      case "wind_grid":
        if (!data.wind_grid.spots.includes(String(message.spot))) {
          throw { code: "not_found", message: "Unknown spot" };
        }
        return data.wind_grid;
      case "wind_view":
        return madeUpView(data, message as unknown as Bounds & { have?: string });
      default:
        throw { code: "unknown_command", message: `The demo doesn't answer ${type}` };
    }
  };

  const hass: HomeAssistant = {
    language: params.get("lang") ?? "en",
    locale: { language: params.get("lang") ?? "en", time_format: "language" },
    themes: { darkMode: params.get("mode") === "night" },
    user: { id: "user-alex", name: "Alex", is_admin: params.get("admin") !== "0" },
    config: {
      latitude: 32.72,
      longitude: -117.2,
      time_zone: data.time_zone,
      unit_system:
        params.get("units") === "metric"
          ? { length: "km", temperature: "°C" }
          : { length: "mi", temperature: "°F" },
    },
    states: STATES,
    connection: {
      sendMessagePromise: <T>(message: Record<string, unknown>) =>
        new Promise<T>((resolve, reject) => {
          try {
            resolve(answer(message) as T);
          } catch (err) {
            reject(err);
          }
        }),
      subscribeMessage: <T>(callback: (message: T) => void) => {
        const listener = () => callback({ updated: new Date().toISOString() } as T);
        listeners.add(listener);
        return Promise.resolve(async () => {
          listeners.delete(listener);
        });
      },
    },
  };
  document.documentElement.style.colorScheme = params.get("mode") === "night" ? "dark" : "light";
  document.body.style.background = params.get("mode") === "night" ? "#101315" : "#f4f6f8";
  const panel = document.querySelector("sailcast-panel");
  if (panel) {
    panel.narrow = window.innerWidth < 870;
    panel.hass = hass;
  }
}

void start();

/**
 * The demo page: the panel with the recorded San Diego week, answered by a
 * stand-in for Home Assistant. Write its data first with
 * `.venv/bin/python scripts/demo_data.py` from the repository.
 *
 * Options: ?mode=night, ?units=metric, ?admin=0, ?empty, ?view=day or map.
 */
import "../src/sailcast-panel";
import type {
  Forecast,
  HomeAssistant,
  PlannedList,
  PlannedSail,
  SailCastConfig,
  WindGrid,
} from "../src/types";

interface DemoData {
  now: string;
  time_zone: string;
  config: SailCastConfig;
  forecasts: Record<string, Forecast>;
  planned: PlannedList;
  wind_grid: WindGrid;
}

const params = new URLSearchParams(location.search);
const listeners = new Set<() => void>();
const changed = () => listeners.forEach((listener) => listener());

async function start(): Promise<void> {
  const response = await fetch("/demo/data.json");
  if (!response.ok) {
    document.body.textContent =
      "Write the demo's data first: .venv/bin/python scripts/demo_data.py";
    return;
  }
  const data = (await response.json()) as DemoData;
  const config: SailCastConfig = params.has("empty")
    ? { ...data.config, spots: [], boats: [], sailors: [] }
    : data.config;
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
          suggested: { tide_station: "9410170", current_station: null, marine_zone: "PZZ740" },
          failed: false,
        };
      case "settings/save":
        return { profile: message.profile ?? "new" };
      case "settings/delete":
        return { profile: message.profile };
      case "planned/skipped":
        return message.days;
      case "wind_grid":
        if (!data.wind_grid.spots.includes(String(message.spot))) {
          throw { code: "not_found", message: "Unknown spot" };
        }
        return data.wind_grid;
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

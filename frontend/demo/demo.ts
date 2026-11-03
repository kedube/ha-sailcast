import "../src/sailcast-panel";
import type { HomeAssistant, SailCastConfig } from "../src/types";

// Made-up profiles. The spots are in San Diego Bay, not anyone's home water.
const CONFIG: SailCastConfig = {
  spots: [
    {
      id: "bay",
      name: "Bay",
      latitude: 32.68,
      longitude: -117.17,
      radius: 15000,
      water_type: "bay",
      offshore: ["e"],
      exposed: ["s", "sw"],
    },
    {
      id: "harbor",
      name: "Harbor",
      latitude: 32.71,
      longitude: -117.2,
      radius: 10000,
      water_type: "open_coast",
      offshore: ["ne", "e"],
      exposed: ["sw", "w", "nw"],
    },
    {
      id: "river",
      name: "River",
      latitude: 32.76,
      longitude: -117.24,
      radius: 8000,
      water_type: "river",
      offshore: [],
      exposed: ["w"],
    },
  ],
  boats: [
    { id: "cruiser", name: "Cruiser", size_class: "cruiser", length: 10.363 },
    { id: "keelboat", name: "Day sailer", size_class: "small_keelboat", length: 6.096 },
  ],
  sailors: [
    {
      id: "alex",
      name: "Alex",
      skill: "intermediate",
      boats: ["keelboat", "cruiser"],
      days: ["sat", "sun"],
      start: null,
      end: null,
    },
    {
      id: "jordan",
      name: "Jordan",
      skill: "advanced",
      boats: ["cruiser"],
      days: ["fri", "sat", "sun"],
      start: "09:00:00",
      end: null,
    },
    {
      id: "sam",
      name: "Sam",
      skill: "beginner",
      boats: ["keelboat"],
      days: ["sat"],
      start: null,
      end: "15:00:00",
    },
  ],
};

const params = new URLSearchParams(location.search);
const hass: HomeAssistant = {
  language: params.get("lang") ?? "en",
  themes: { darkMode: params.get("mode") === "night" },
  user: { is_admin: params.get("admin") !== "0" },
  config: { unit_system: { length: params.get("units") === "metric" ? "km" : "mi" } },
  connection: {
    sendMessagePromise: <T>() =>
      Promise.resolve((params.has("empty") ? { spots: [], boats: [], sailors: [] } : CONFIG) as T),
  },
};

const panel = document.querySelector("sailcast-panel");
if (panel) {
  panel.narrow = window.innerWidth < 870;
  panel.hass = hass;
}

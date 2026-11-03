import { describe, expect, it } from "vitest";

import en from "./translations/en.json";

// English and the 11 languages with the most Home Assistant installs.
const LANGUAGES = ["en", "de", "fr", "nl", "es", "zh-Hans", "it", "pl", "sv", "ru", "cs", "pt-BR"];
const FILES = import.meta.glob<Record<string, unknown>>("./translations/*.json", {
  import: "default",
  eager: true,
});

/** Every string's dotted path, and its placeholders. */
function strings(node: unknown, prefix = ""): Map<string, string[]> {
  const found = new Map<string, string[]>();
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    if (typeof value === "string") {
      // A language may use a placeholder twice.
      const names = new Set([...value.matchAll(/\{(\w+)\}/g)].map((m) => m[1]));
      found.set(`${prefix}${key}`, [...names].sort());
    } else {
      for (const [path, names] of strings(value, `${prefix}${key}.`)) found.set(path, names);
    }
  }
  return found;
}

/** Return whether English has a string at a dotted path. */
function has(key: string): boolean {
  let node: unknown = en;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return false;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string";
}

// The panel's source files, as text.
const SOURCES = import.meta.glob<string>(["./*.ts", "!./*.test.ts"], {
  query: "?raw",
  import: "default",
  eager: true,
});

// Keys the panel builds from values: each family must be complete.
const FAMILIES: Record<string, string[]> = {
  level: ["good", "caution", "not_recommended", "dangerous"],
  level_short: ["good", "caution", "not_recommended", "dangerous"],
  // Labels as words inside a sentence.
  level_word: ["good", "caution", "not_recommended", "dangerous"],
  band: ["great", "good", "fair", "poor"],
  band_word: ["great", "good", "fair", "poor"],
  skill_word: ["beginner", "intermediate", "advanced"],
  ahead_word: ["1", "2", "4", "6"],
  confidence: ["high", "medium", "low"],
  confidence_word: ["high", "medium", "low"],
  size_class: ["dinghy", "small_keelboat", "cruiser", "large_cruiser"],
  size_letter: ["dinghy", "small_keelboat", "cruiser", "large_cruiser"],
  size_noun: ["dinghy", "small_keelboat", "cruiser", "large_cruiser"],
  size_lengths: ["dinghy", "small_keelboat", "cruiser", "large_cruiser"],
  skill: ["beginner", "intermediate", "advanced"],
  skill_text: ["beginner", "intermediate", "advanced"],
  water_type: ["open_coast", "bay", "river", "lake"],
  weekday: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
  theme: ["auto", "day", "night", "auto_label", "day_label", "night_label"],
  rain: ["avoid", "some", "any"],
  ahead: ["1", "2", "4", "6"],
  auto: ["score_60", "score_60_hint", "score_80", "score_80_hint"],
  tabs: ["week", "day", "map", "settings"],
  map: ["wind", "gust"],
  compass: "n nne ne ene e ese se sse s ssw sw wsw w wnw nw nnw".split(" "),
  spot: [
    "tide_station",
    "current_station",
    "marine_zone",
    "buoy",
    "airport",
    "tide_station_short",
    "current_station_short",
    "marine_zone_short",
    "buoy_short",
    "airport_short",
    "offshore",
    "exposed",
    "offshore_hint",
    "exposed_hint",
    "tide_mark",
    "current_mark",
    "buoy_mark",
    "airport_mark",
  ],
  // The backend's advice keys (advice.py).
  advice: [
    "day_over",
    "warning",
    "warning_dangerous",
    "warning_not_recommended",
    "warning_caution",
    "wind",
    "trend_building",
    "trend_easing",
    "light_air",
    "gusty",
    "gusty_dinghy",
    "over_limit_hour",
    "over_limit",
    "near_limit",
    "reef",
    "depower",
    "waves",
    "against_flood",
    "against_ebb",
    "offshore",
    "water",
    "rain",
    "rain_visibility",
    "tides",
    "sunset",
  ],
  // The rating's reasons (rating.py), except warnings, which use the event's name.
  reason: [
    "wind_over_limit",
    "wind",
    "gusts",
    "gusty",
    "waves",
    "steep_waves",
    "wind_against_flood",
    "wind_against_ebb",
    "offshore_wind",
    "wind_chill",
    "visibility",
    "visibility_measured",
    "thunderstorms",
    "thunderstorms_possible",
  ],
  "spot.sensor": ["wind", "gust", "wind_direction", "temperature", "water_temperature"],
  "sources.tide_by": ["noaa", "chs", "rws", "kartverket", "worldtides", "model"],
  "sources.warnings_by": ["nws", "nws_pin", "eccc", "meteoalarm"],
  datum: ["MLLW", "CD", "LAT", "MSL", "NAP"],
  // MeteoAlarm's warnings, by level and kind (meteoalarm.py).
  meteoalarm: ["yellow", "orange", "red"],
  "meteoalarm.kind": [
    "wind",
    "snow_ice",
    "thunderstorm",
    "fog",
    "high_temperature",
    "low_temperature",
    "coastal_event",
    "forest_fire",
    "avalanches",
    "rain",
    "flooding",
    "rain_flood",
  ],
  reading_source: ["sensors", "buoy", "airport"],
  sources: ["buoy_text", "airport_text"],
  // Errors the settings commands send back (profiles.py and websocket_api.py).
  error: [
    "name_required",
    "name_too_long",
    "name_taken",
    "radius_out_of_range",
    "length_out_of_range",
    "unknown_boat",
    "no_days",
    "end_before_start",
    "ideal_out_of_range",
    "ideal_high_below_low",
    "coldest_out_of_range",
    "calendar_read_only",
    "no_spots",
    "invalid_min_score",
    "invalid_ahead",
    "unknown_user",
    "boat_in_use",
    "fetch_out_of_range",
    "invalid_sensor",
  ],
};

describe("English strings", () => {
  it.each(Object.entries(FAMILIES))("has every %s key", (family, members) => {
    const missing = members.filter((member) => !has(`${family}.${member}`));
    expect(missing).toEqual([]);
  });

  it("has every key the panel names", () => {
    const missing: string[] = [];
    expect(Object.keys(SOURCES).length).toBeGreaterThan(10);
    for (const [file, text] of Object.entries(SOURCES)) {
      for (const match of text.matchAll(/\bt\(\s*"([a-z0-9_.]+)"/g)) {
        if (!has(match[1])) missing.push(`${file}: ${match[1]}`);
      }
      for (const match of text.matchAll(
        /\?\s*"([a-z_]+\.[a-z0-9_.]+)"\s*:\s*"([a-z_]+\.[a-z0-9_.]+)"/g,
      )) {
        for (const key of [match[1], match[2]]) if (!has(key)) missing.push(`${file}: ${key}`);
      }
    }
    expect(missing).toEqual([]);
  });
});

describe("Every language", () => {
  it("is there", () => {
    const names = Object.keys(FILES).map((path) => path.replace(/^.*\//, "").replace(".json", ""));
    expect(names.sort()).toEqual([...LANGUAGES].sort());
  });

  it.each(LANGUAGES.slice(1))("%s has English's strings and placeholders", (language) => {
    const english = strings(en);
    const found = strings(FILES[`./translations/${language}.json`]);
    expect([...found.keys()].sort()).toEqual([...english.keys()].sort());
    const differ = [...english].filter(
      ([key, names]) => JSON.stringify(found.get(key)) !== JSON.stringify(names),
    );
    expect(differ.map(([key]) => key)).toEqual([]);
  });
});

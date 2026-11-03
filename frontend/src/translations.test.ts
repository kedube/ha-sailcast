import { describe, expect, it } from "vitest";

import en from "./translations/en.json";

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
  band: ["great", "good", "fair", "poor"],
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
  tabs: ["week", "day", "settings"],
  compass: "n nne ne ene e ese se sse s ssw sw wsw w wnw nw nnw".split(" "),
  spot: [
    "tide_station",
    "current_station",
    "marine_zone",
    "tide_station_short",
    "current_station_short",
    "marine_zone_short",
    "offshore",
    "exposed",
    "offshore_hint",
    "exposed_hint",
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
    "thunderstorms",
    "thunderstorms_possible",
  ],
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

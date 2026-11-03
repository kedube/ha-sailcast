import { describe, expect, it } from "vitest";

import { Formatter } from "./format";
import { localize } from "./localize";
import { adviceText, reasonsText, reasonText } from "./text";
import type { Advice, HomeAssistant, Reason } from "./types";

function formatter(units: "us" | "metric"): Formatter {
  return new Formatter({
    language: "en",
    locale: { language: "en", time_format: "language" },
    config: {
      latitude: 32.7,
      longitude: -117.2,
      time_zone: "America/Los_Angeles",
      unit_system:
        units === "us" ? { length: "mi", temperature: "°F" } : { length: "km", temperature: "°C" },
    },
    connection: {} as HomeAssistant["connection"],
  });
}

const t = (key: string, values?: Record<string, string | number>) => localize("en", key, values);
const us = formatter("us");
const metric = formatter("metric");

function reason(key: string, values: Reason["values"] = {}, extra: Partial<Reason> = {}): Reason {
  return { key, level: "caution", values, modifier: false, ...extra };
}

function advice(key: string, values: Record<string, unknown> = {}): Advice {
  return { key, icon: "", values, hot: false };
}

describe("reasonText", () => {
  it("writes each reason in the user's units", () => {
    expect(reasonText(us, t, reason("waves", { height: 1.38 }))).toBe("waves 4.5 ft");
    expect(reasonText(metric, t, reason("waves", { height: 1.38 }))).toBe("waves 1.4 m");
    expect(reasonText(us, t, reason("gusts", { gust: 22.6 }))).toBe("gusts 23 kt");
    expect(reasonText(us, t, reason("visibility", { visibility: 1500 }))).toBe("visibility 0.8 nm");
    expect(reasonText(us, t, reason("wind_chill", { temperature: -2 }))).toBe("wind chill 28 °F");
    expect(reasonText(us, t, reason("warning", { event: "Gale Warning" }))).toBe("Gale Warning");
    expect(reasonText(us, t, reason("thunderstorms"))).toBe("thunderstorms forecast");
  });

  it("shows a decimal when rounding would hide that the limit is passed", () => {
    expect(reasonText(us, t, reason("wind_over_limit", { wind: 10.4, limit: 10 }))).toBe(
      "wind 10.4 kt, over your 10 kt limit",
    );
    expect(reasonText(us, t, reason("wind_over_limit", { wind: 12.6, limit: 10 }))).toBe(
      "wind 13 kt, over your 10 kt limit",
    );
  });
});

describe("reasonsText", () => {
  it("says what set the rating, then what made it worse, at most three", () => {
    const reasons = [
      reason("waves", { height: 1.4 }, { level: "not_recommended" }),
      reason("gusts", { gust: 23 }),
      reason("gusty", { spread: 11 }, { level: "good", modifier: true }),
    ];
    expect(reasonsText(us, t, reasons)).toBe("waves 4.6 ft, gusty, 11 kt over the mean");
    expect(reasonsText(us, t, [])).toBe("");
  });
});

describe("adviceText", () => {
  it("writes the day's wind with its trend", () => {
    expect(
      adviceText(
        us,
        t,
        advice("wind", { direction: 270, low: 8, high: 12, gust: 16, trend: "building" }),
      ),
    ).toBe("W 8–12 kt, building through the day, gusts to 16 kt.");
    expect(
      adviceText(us, t, advice("wind", { direction: 45, low: 6, high: 6, gust: 9, trend: null })),
    ).toBe("NE 6 kt, gusts to 9 kt.");
  });

  it("says when the wind is past the sailor's limit", () => {
    expect(
      adviceText(
        us,
        t,
        advice("over_limit", {
          limit: 10,
          start: "2026-11-07T21:00:00Z",
          end: "2026-11-07T23:00:00Z",
        }),
      ),
    ).toBe("Wind above your 10 kt limit between 1 PM and 3 PM.");
  });

  it("lists the tides in daylight", () => {
    expect(
      adviceText(
        us,
        t,
        advice("tides", {
          events: [
            { time: "2026-11-07T17:33:00Z", height: 0.94, high: true },
            { time: "2026-11-07T23:41:00Z", height: 0.12, high: false },
          ],
        }),
      ),
    ).toBe("High tide 9:33 AM (3.1 ft), low tide 3:41 PM (0.4 ft).");
  });

  it("explains what an official warning means for the boat", () => {
    expect(
      adviceText(
        us,
        t,
        advice("warning_not_recommended", {
          event: "Small Craft Advisory",
          size: "small_keelboat",
        }),
      ),
    ).toBe("Small Craft Advisory in effect. Not a day for a small keelboat, whatever your skill.");
  });

  it("writes the water and rain in the user's units", () => {
    expect(adviceText(metric, t, advice("water", { temperature: 17.8 }))).toBe("Water 18 °C.");
    expect(adviceText(us, t, advice("rain_visibility", { chance: 60, visibility: 2500 }))).toBe(
      "Rain likely (60%), with visibility down to 1.3 nm.",
    );
  });
});

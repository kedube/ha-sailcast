import { describe, expect, it } from "vitest";

import { band, compassKey, Formatter, localHours, localTime, weekdayKey } from "./format";
import type { HomeAssistant } from "./types";

const ZONE = "America/Los_Angeles";

function hass(units: "us" | "metric" = "us", timeFormat = "language"): HomeAssistant {
  return {
    language: "en",
    locale: { language: "en", time_format: timeFormat, number_format: "language" },
    config: {
      latitude: 32.7,
      longitude: -117.2,
      time_zone: ZONE,
      unit_system:
        units === "us" ? { length: "mi", temperature: "°F" } : { length: "km", temperature: "°C" },
    },
    connection: {} as HomeAssistant["connection"],
  };
}

describe("local times", () => {
  it("reads the date and clock time at the spot", () => {
    expect(localTime("2026-11-07T21:00:00+00:00", ZONE)).toEqual({
      date: "2026-11-07",
      hour: 13,
      minute: 0,
    });
    expect(localHours("2026-11-07T21:30:00Z", ZONE)).toBe(13.5);
  });

  it("handles the night the clocks go back", () => {
    // 1:30 AM happens twice on November 1, 2026: in daylight time, then standard.
    expect(localTime("2026-11-01T08:30:00Z", ZONE).hour).toBe(1);
    expect(localTime("2026-11-01T09:30:00Z", ZONE).hour).toBe(1);
  });

  it("names the weekday of a date", () => {
    expect(weekdayKey("2026-11-02")).toBe("mon");
    expect(weekdayKey("2026-11-08")).toBe("sun");
  });
});

describe("band", () => {
  it("reads scores as the plan's bands", () => {
    expect([80, 79, 60, 59, 40, 39, 0].map(band)).toEqual([
      "great",
      "good",
      "good",
      "fair",
      "fair",
      "poor",
      "poor",
    ]);
  });
});

describe("compassKey", () => {
  it("rounds to the nearest of 16 points", () => {
    expect([0, 11.2, 11.3, 270, 350, -90, 720].map(compassKey)).toEqual([
      "n",
      "n",
      "nne",
      "w",
      "n",
      "w",
      "n",
    ]);
  });
});

describe("Formatter", () => {
  const us = new Formatter(hass());
  const metric = new Formatter(hass("metric", "24"));

  it("follows Home Assistant's units, with wind always in knots", () => {
    expect(us.feet && us.fahrenheit && us.miles).toBe(true);
    expect(metric.feet || metric.fahrenheit || metric.miles).toBe(false);
    expect(us.height(1)).toBeCloseTo(3.28084);
    expect(metric.height(1)).toBe(1);
    expect(us.temperature(10)).toBe(50);
    expect(us.celsius(50)).toBe(10);
    expect(us.distance(1.609344)).toBeCloseTo(1);
  });

  it("formats numbers and ranges", () => {
    expect(us.number(12.6)).toBe("13");
    expect(us.number(1.38, 1)).toBe("1.4");
    expect(us.number(-0.04, 1)).toBe("0.0");
    expect(us.range(8.2, 8.4)).toBe("8");
    expect(us.range(8, 12)).toBe("8–12");
  });

  it("writes times as the user reads them", () => {
    expect(us.clock("2026-11-07T21:00:00Z")).toBe("1 PM");
    expect(us.clock("2026-11-08T00:53:00Z")).toBe("4:53 PM");
    expect(us.span("2026-11-07T21:00:00Z", "2026-11-08T00:53:00Z")).toBe("1 PM–4:53 PM");
    expect(metric.clock("2026-11-07T21:00:00Z")).toBe("13:00");
  });

  it("finds the moment a local date reaches a clock time", () => {
    expect(us.at("2026-11-07", 13.5).toISOString()).toBe("2026-11-07T21:30:00.000Z");
    // Midnight is still daylight time on November 1; noon is standard time.
    expect(us.at("2026-11-01", 0).toISOString()).toBe("2026-11-01T07:00:00.000Z");
    expect(us.at("2026-11-01", 12).toISOString()).toBe("2026-11-01T20:00:00.000Z");
    expect(us.hourOf("2026-11-07", 6)).toBe("6 AM");
  });

  it("names days and dates", () => {
    expect(us.weekday("2026-11-07")).toBe("Sat");
    expect(us.weekday("2026-11-07", "long")).toBe("Saturday");
    expect(us.dayOfMonth("2026-11-07")).toBe("7");
    expect(us.shortDate("2026-11-07")).toBe("Nov 7");
    expect(us.longDate("2026-11-07")).toBe("Saturday, Nov 7");
  });
});

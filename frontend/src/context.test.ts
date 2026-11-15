import { describe, expect, it } from "vitest";

import { allDay, dayAndDate, hoursText, type Ctx } from "./context";
import { Formatter } from "./format";
import { loadLanguage, localize } from "./localize";
import { sailingTimes } from "./settings";
import type { Day, HomeAssistant, Sailor } from "./types";

function ctx(language: string): Ctx {
  const hass = {
    language,
    locale: { language, time_format: "language", number_format: "language" },
    config: {
      latitude: 32.7,
      longitude: -117.2,
      time_zone: "America/Los_Angeles",
      unit_system: { length: "mi", temperature: "°F" },
    },
    connection: {} as HomeAssistant["connection"],
  } as HomeAssistant;
  const days = ["2026-11-03", "2026-11-07"].map((date) => ({ date }) as Day);
  return {
    hass,
    fmt: new Formatter(hass),
    t: (key, values) => localize(language, key, values),
    forecast: { days },
  } as Ctx;
}

describe("dayAndDate", () => {
  it.each([
    ["en", "Today, Nov 3", "Saturday, Nov 7"],
    ["de", "Heute, 3. Nov.", "Samstag, 7. Nov."],
    ["fr", "Aujourd'hui 3 nov.", "samedi 7 nov."],
    ["zh-Hans", "11月3日 今天", "11月7日 星期六"],
  ])("follows %s order and punctuation", async (language, today, saturday) => {
    await loadLanguage(language);
    const context = ctx(language);
    const [first, second] = context.forecast?.days ?? [];
    expect(dayAndDate(context, first)).toBe(today);
    expect(dayAndDate(context, second)).toBe(saturday);
  });
});

describe("hoursText", () => {
  const split = [
    { start: "09:00:00", end: "11:00:00" },
    { start: "15:00:00", end: "19:00:00" },
  ];

  it.each([
    ["en", "9 AM to 11 AM, 3 PM to 7 PM"],
    ["de", "9:00 bis 11:00, 15:00 bis 19:00"],
    ["zh-Hans", "9:00–11:00，15:00–19:00"],
  ])("names each stretch of the day in %s", async (language, text) => {
    await loadLanguage(language);
    expect(hoursText(ctx(language), "2026-11-07", split, false)).toBe(text);
  });

  it("says when a stretch runs from sunrise or to sunset, or any time with lights", async () => {
    await loadLanguage("en");
    const context = ctx("en");
    const edges = [
      { start: null, end: "08:00:00" },
      { start: "17:00:00", end: null },
    ];
    expect(hoursText(context, "2026-11-07", edges, false)).toBe("sunrise to 8 AM, 5 PM to sunset");
    expect(hoursText(context, "2026-11-07", edges, true)).toBe(
      "midnight to 8 AM, 5 PM to midnight",
    );
    expect(hoursText(context, "2026-11-07", [{ start: null, end: null }], false)).toBe(
      "Sunrise to sunset",
    );
    expect(hoursText(context, "2026-11-07", [{ start: null, end: null }], true)).toBe("Any time");
    expect(hoursText(context, "2026-11-07", null, false)).toBe("Not sailing");
  });

  it("knows a whole day", () => {
    expect(allDay([{ start: null, end: null }])).toBe(true);
    expect(allDay([])).toBe(true);
    expect(allDay(split)).toBe(false);
    expect(allDay([{ start: "09:00:00", end: null }])).toBe(false);
  });
});

describe("sailingTimes", () => {
  it("puts days with the same stretches together", async () => {
    await loadLanguage("en");
    const sailor = {
      week: {
        mon: [{ start: "17:00:00", end: null }],
        wed: [{ start: "17:00:00", end: null }],
        sat: [
          { start: "09:00:00", end: "11:00:00" },
          { start: "15:00:00", end: "19:00:00" },
        ],
        sun: [
          { start: "09:00:00", end: "11:00:00" },
          { start: "15:00:00", end: "19:00:00" },
        ],
      },
    } as unknown as Sailor;
    expect(sailingTimes(ctx("en"), sailor)).toBe(
      "Mon, Wed: 5 PM to sunset · Weekends: 9 AM to 11 AM, 3 PM to 7 PM",
    );
  });
});

import { describe, expect, it } from "vitest";

import { dayAndDate, type Ctx } from "./context";
import { Formatter } from "./format";
import { loadLanguage, localize } from "./localize";
import type { Day, HomeAssistant } from "./types";

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

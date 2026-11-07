import { describe, expect, it } from "vitest";

import type { Day } from "./types";
import { calendarHours } from "./week";

const ZONE = "America/Los_Angeles";

/** A day's sunrise and sunset, and windows that start at the times given. */
function day(date: string, sunrise: string, sunset: string, starts: string[] = []): Day {
  return {
    date,
    sunrise,
    sunset,
    windows: starts.map((start) => ({ start, end: start, score: 80, hours: 2 })),
  } as unknown as Day;
}

describe("the calendar's hours", () => {
  // November in San Diego: sunrise about 6:10 AM and sunset about 4:50 PM.
  const week = [
    day("2026-11-07", "2026-11-07T14:10:00+00:00", "2026-11-08T00:50:00+00:00"),
    day("2026-11-08", "2026-11-08T14:11:00+00:00", "2026-11-09T00:49:00+00:00"),
  ];

  it("show an hour before the earliest sunrise to an hour after the latest sunset", () => {
    expect(calendarHours(week, ZONE, true)).toEqual({
      first: 0,
      last: 24,
      start: 5,
      end: 18,
      open: 5,
    });
  });

  it("lay out only those hours in a boat without lights", () => {
    expect(calendarHours(week, ZONE, false)).toEqual({
      first: 5,
      last: 18,
      start: 5,
      end: 18,
      open: 5,
    });
  });

  it("open earlier for a window that starts before then", () => {
    // 3 AM, in a boat with navigation lights.
    const early = day("2026-11-08", week[1].sunrise, week[1].sunset, ["2026-11-08T11:00:00+00:00"]);
    expect(calendarHours([week[0], early], ZONE, true).open).toBe(3);
  });

  it("stay within the day when the sun doesn't set", () => {
    const midsummer = day("2026-06-21", "2026-06-21T07:00:00+00:00", "2026-06-22T07:00:00+00:00");
    expect(calendarHours([midsummer], ZONE, false)).toEqual({
      first: 0,
      last: 24,
      start: 0,
      end: 24,
      open: 0,
    });
  });
});

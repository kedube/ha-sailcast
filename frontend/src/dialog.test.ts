import { describe, expect, it } from "vitest";

import { editable, fieldNumber, nextStretch, saved } from "./dialog";

describe("fieldNumber", () => {
  it("writes what a number field takes, whatever the user's number format", () => {
    // A 34 ft boat, stored in meters.
    expect(fieldNumber(10.363 * 3.28084, 1)).toBe("34");
    expect(fieldNumber(10.4, 1)).toBe("10.4");
    // Swedish formats minus as "−", which a number field would drop.
    expect(fieldNumber(-3.4)).toBe("-3");
    expect(fieldNumber(-0.2)).toBe("0");
    expect(fieldNumber(1234.56, 1)).toBe("1234.6");
  });
});

describe("stretches of hours", () => {
  it("start from the day's hours, or the whole day", () => {
    const split = [
      { start: "09:00:00", end: "11:00:00" },
      { start: "15:00:00", end: "19:00:00" },
    ];
    const rows = editable(split);
    expect(saved(rows)).toEqual(split);
    expect(new Set(rows.map((row) => row.key)).size).toBe(2);
    expect(saved(editable(null))).toEqual([{ start: null, end: null }]);
    expect(saved(editable([]))).toEqual([{ start: null, end: null }]);
  });

  it("add the next one an hour after the last ends, until sunset", () => {
    const next = nextStretch([{ start: "09:00:00", end: "11:00:00" }]);
    expect(saved([next])).toEqual([{ start: "12:00:00", end: null }]);
    // After a stretch to sunset, or one ending at 11 PM, there's no room.
    expect(saved([nextStretch([{ start: "09:00:00", end: null }])])).toEqual([
      { start: null, end: null },
    ]);
    expect(saved([nextStretch([{ start: "20:00:00", end: "23:00:00" }])])).toEqual([
      { start: null, end: null },
    ]);
  });
});

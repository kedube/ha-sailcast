import { describe, expect, it } from "vitest";

import { fieldNumber } from "./dialog";

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

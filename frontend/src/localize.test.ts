import { describe, expect, it } from "vitest";

import { localize } from "./localize";

describe("localize", () => {
  it("finds nested strings", () => {
    expect(localize("en", "skill.advanced")).toBe("Advanced");
  });

  it("fills placeholders", () => {
    expect(localize("en", "unit.feet", { value: 20 })).toBe("20 ft");
  });

  it("falls back to English for other languages", () => {
    expect(localize("de", "settings.boats")).toBe("Boats");
    expect(localize("pt-BR", "settings.boats")).toBe("Boats");
    expect(localize(undefined, "settings.boats")).toBe("Boats");
  });

  it("shows the key when a string is missing", () => {
    expect(localize("en", "no.such.key")).toBe("no.such.key");
  });
});

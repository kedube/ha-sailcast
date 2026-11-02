import { describe, expect, it } from "vitest";

import { PALETTES, WAVE, contrast, type Mode } from "./theme";

// Text and the backgrounds it sits on. Every pair needs WCAG AA contrast
// (4.5:1) in both the day and the night palette.
const PAIRS: [text: string, background: string][] = [
  ["fg", "page"],
  ["fg", "toolbar"],
  ["fg", "card"],
  ["fg2", "page"],
  ["fg2", "card"],
  ["primary-ink", "card"],
  ["primary-ink", "primary-tint"],
  ["btn-ink", "btn"],
  ["danger", "danger-bg"],
];

describe.each(["day", "night"] as Mode[])("the %s palette", (mode) => {
  const palette = PALETTES[mode];

  it.each(PAIRS)("has readable %s on %s", (text, background) => {
    // See-through backgrounds sit on a card.
    expect(contrast(palette[text], palette[background], palette.card)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("the welcome banner", () => {
  it("has readable text on its lightest blue", () => {
    expect(contrast(WAVE.foam, WAVE.ocean)).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#ffffff", WAVE.ocean)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("contrast", () => {
  it("matches known ratios", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrast("#777777", "#ffffff")).toBeCloseTo(4.48, 2);
  });
});

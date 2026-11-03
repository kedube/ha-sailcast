import { describe, expect, it } from "vitest";

import { PALETTES, contrast, paletteCss, type Mode } from "./theme";

// Text and the backgrounds it sits on. Every pair needs WCAG AA contrast
// (4.5:1) in both the day and the night palette.
const PAIRS: [text: string, background: string][] = [
  ["fg", "page"],
  ["fg", "card"],
  ["fg2", "page"],
  ["fg2", "card"],
  ["toolbar-ink", "toolbar"],
  ["primary-ink", "card"],
  ["primary-ink", "primary-tint"],
  ["btn-ink", "btn"],
  ["sea-ink", "sea"],
  ["sea-ink2", "sea"],
  ["danger", "danger-bg"],
];

// Card colors of Home Assistant's default theme, which replace SailCast's
// own inside Home Assistant.
const HA_CARDS: Record<Mode, string> = { day: "#ffffff", night: "#1c1c1c" };

describe.each(["day", "night"] as Mode[])("the %s palette", (mode) => {
  const palette = PALETTES[mode];

  it.each(PAIRS)("has readable %s on %s", (text, background) => {
    // See-through backgrounds sit on a card.
    expect(contrast(palette[text], palette[background], palette.card)).toBeGreaterThanOrEqual(4.5);
  });

  it("keeps its own blues readable on Home Assistant's cards", () => {
    const card = HA_CARDS[mode];
    expect(contrast(palette["primary-ink"], card)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(palette["primary-ink"], palette["primary-tint"], card)).toBeGreaterThanOrEqual(
      4.5,
    );
  });
});

describe("paletteCss", () => {
  it("follows the Home Assistant theme, with SailCast's colors as fallbacks", () => {
    const css = paletteCss("day");
    expect(css).toContain("--sc-card: var(--card-background-color, #ffffff);");
    expect(css).toContain("--sc-toolbar-ink: var(--app-header-text-color, #15222c);");
    expect(css).toContain("--sc-sea: #0b4466;");
  });
});

describe("contrast", () => {
  it("matches known ratios", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrast("#777777", "#ffffff")).toBeCloseTo(4.48, 2);
  });
});

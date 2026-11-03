import { describe, expect, it } from "vitest";

import { PALETTES, contrast, paletteCss, type Mode } from "./theme";

// Text and the backgrounds it sits on. Every pair needs WCAG AA contrast
// (4.5:1) in both the day and the night palette.
const PAIRS: [text: string, background: string][] = [
  ["fg", "page"],
  ["fg", "card"],
  ["fg", "sunk"],
  ["fg2", "page"],
  ["fg2", "card"],
  ["fg2", "sunk"],
  ["toolbar-ink", "toolbar"],
  ["primary-ink", "card"],
  ["primary-ink", "primary-tint"],
  ["btn-ink", "btn"],
  ["sea-ink", "sea"],
  ["sea-ink2", "sea"],
  ["sea-ink", "sea-chip"],
  // Safety ratings.
  ["good", "good-bg"],
  ["caution", "caution-bg"],
  ["notrec", "notrec-bg"],
  ["danger", "danger-bg"],
  // Sailing windows in the week calendar and the day view.
  ["event-ink", "event"],
  ["event-ink", "event-hover"],
  ["event-ink", "event-added"],
  // Scores.
  ["s-great-ink", "s-great"],
  ["s-good-ink", "s-good"],
  ["s-fair-ink", "s-fair"],
  ["s-poor-ink", "s-poor"],
  // Sunrise and sunset in the calendar's night hours.
  ["h-ink", "h-night"],
  ["map-ink", "map-chip"],
];

// Card colors of Home Assistant's default theme, which replace SailCast's
// own inside Home Assistant.
const HA_CARDS: Record<Mode, string> = { day: "#ffffff", night: "#1c1c1c" };

describe.each(["day", "night"] as Mode[])("the %s palette", (mode) => {
  const palette = PALETTES[mode];

  it.each(PAIRS)("has readable %s on %s", (text, background) => {
    // See-through backgrounds sit on a card, or on the sea for its chips.
    const base = background.startsWith("sea-") ? palette.sea : palette.card;
    expect(contrast(palette[text], palette[background], base)).toBeGreaterThanOrEqual(4.5);
  });

  it("has the same colors as the other palette", () => {
    const other = PALETTES[mode === "day" ? "night" : "day"];
    expect(Object.keys(palette).sort()).toEqual(Object.keys(other).sort());
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

  it("uses its own colors when Day or Night overrides Home Assistant", () => {
    const css = paletteCss("night", false);
    expect(css).toContain("--sc-card: #1a1e21;");
    expect(css).not.toContain("var(--");
  });
});

describe("contrast", () => {
  it("matches known ratios", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrast("#777777", "#ffffff")).toBeCloseTo(4.48, 2);
  });
});

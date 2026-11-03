/**
 * SailCast follows the Home Assistant theme: its page, toolbar, cards and text
 * take the theme's colors, in light and dark mode. SailCast's own day and
 * night palettes fill in anything a theme doesn't set, and supply the deep sea
 * blue that marks sailing windows. Green, amber, orange and red only ever mean
 * safety ratings.
 *
 * When someone picks Day or Night in the panel, that overrides Home
 * Assistant's mode for SailCast only, so the palette is used as it is.
 */
export type Mode = "day" | "night";

/** The Home Assistant theme variable each SailCast color follows. */
export const THEME_VARIABLES: Record<string, string> = {
  page: "primary-background-color",
  toolbar: "app-header-background-color",
  "toolbar-ink": "app-header-text-color",
  card: "card-background-color",
  fg: "primary-text-color",
  fg2: "secondary-text-color",
  line: "divider-color",
};

export const PALETTES: Record<Mode, Record<string, string>> = {
  day: {
    page: "#f4f6f8",
    toolbar: "#ffffff",
    "toolbar-ink": "#15222c",
    card: "#ffffff",
    raised: "#ffffff",
    sunk: "#f1f4f7",
    fg: "#15222c",
    fg2: "#52616d",
    fg3: "#7f8e9a",
    line: "#d9e1e7",
    line2: "#ebf0f3",
    primary: "#03a9f4",
    "primary-ink": "#0a6a9c",
    "primary-tint": "rgba(3, 169, 244, 0.11)",
    btn: "#0a6a9c",
    "btn-ink": "#ffffff",
    focus: "#0a6a9c",
    knob: "#ffffff",
    sea: "#0b4466",
    "sea-ink": "#ffffff",
    "sea-ink2": "rgba(255, 255, 255, 0.76)",
    "sea-line": "rgba(255, 255, 255, 0.42)",
    "sea-chip": "rgba(255, 255, 255, 0.13)",
    "sea-wave": "rgba(255, 255, 255, 0.08)",
    "sea-wave2": "rgba(255, 255, 255, 0.18)",
    "sea-wave3": "rgba(255, 255, 255, 0.05)",
    event: "#0c6aa1",
    "event-hover": "#095985",
    "event-ink": "#ffffff",
    "event-added": "#0a5986",
    "h-good": "#b4d8ee",
    "h-fair": "#d8eaf5",
    "h-poor": "#edf1f4",
    "h-caution": "#f8df9c",
    "h-notrec": "#f6bf9e",
    "h-danger": "#ec9a9a",
    "h-night": "#d6dee5",
    "h-twilight": "#e4eaef",
    "h-ink": "#4f5f6b",
    "h-past": "#e9edf0",
    "h-hatch": "rgba(21, 34, 44, 0.12)",
    now: "#e5484d",
    good: "#1e7a3a",
    "good-bg": "#ddf1e3",
    caution: "#875800",
    "caution-bg": "#fbedc5",
    notrec: "#b1420e",
    "notrec-bg": "#fce0d0",
    danger: "#b32222",
    "danger-bg": "#f8d6d6",
    "dot-good": "#2e9b4e",
    "dot-caution": "#e3a008",
    "dot-notrec": "#ea6a20",
    "dot-danger": "#d53a3c",
    "s-great": "#0a6a9c",
    "s-good": "#4aa3d4",
    "s-fair": "#a7d0e8",
    "s-poor": "#c8d2da",
    "ring-track": "#e4ebf0",
    "s-great-ink": "#ffffff",
    "s-good-ink": "#062636",
    "s-fair-ink": "#1d3d4c",
    "s-poor-ink": "#43515c",
    av1: "#0f7a8a",
    av2: "#a3527c",
    av3: "#6b5bb0",
    av4: "#8a6a12",
    sun: "#e9a10b",
    cloud: "#a9b6c0",
    rain: "#2f86c9",
    "chart-wind": "#0a6a9c",
    "chart-fill": "rgba(10, 106, 156, 0.1)",
    "chart-gust": "#8593a0",
    "chart-spread": "rgba(10, 106, 156, 0.12)",
    window: "rgba(3, 169, 244, 0.1)",
    tide: "#0a6a9c",
    "tide-fill": "rgba(3, 169, 244, 0.12)",
    flood: "#0a6a9c",
    ebb: "#8a5cc7",
    "map-ink": "#ffffff",
    "map-chip": "rgba(9, 18, 25, 0.74)",
    scrim: "rgba(8, 18, 26, 0.46)",
    "shadow-pop": "0 18px 40px rgba(10, 30, 45, 0.22), 0 3px 10px rgba(10, 30, 45, 0.12)",
  },
  night: {
    page: "#101315",
    toolbar: "#1a1e21",
    "toolbar-ink": "#e3e8ec",
    card: "#1a1e21",
    raised: "#23282c",
    sunk: "#15191c",
    fg: "#e3e8ec",
    fg2: "#a1adb7",
    fg3: "#74828d",
    line: "#2b3237",
    line2: "#22282c",
    primary: "#03a9f4",
    "primary-ink": "#63c7f6",
    "primary-tint": "rgba(3, 169, 244, 0.17)",
    btn: "#4fbdf2",
    "btn-ink": "#05202f",
    focus: "#63c7f6",
    knob: "#ffffff",
    sea: "#0a344f",
    "sea-ink": "#ffffff",
    "sea-ink2": "rgba(255, 255, 255, 0.74)",
    "sea-line": "rgba(255, 255, 255, 0.38)",
    "sea-chip": "rgba(255, 255, 255, 0.11)",
    "sea-wave": "rgba(255, 255, 255, 0.06)",
    "sea-wave2": "rgba(255, 255, 255, 0.15)",
    "sea-wave3": "rgba(255, 255, 255, 0.04)",
    event: "#1874ab",
    "event-hover": "#1a7ab3",
    "event-ink": "#ffffff",
    "event-added": "#135f8c",
    "h-good": "#1e5170",
    "h-fair": "#183849",
    "h-poor": "#232a2f",
    "h-caution": "#54420f",
    "h-notrec": "#5c301a",
    "h-danger": "#702424",
    "h-night": "#0d1114",
    "h-twilight": "#171c20",
    "h-ink": "#8d9aa4",
    "h-past": "#1c2125",
    "h-hatch": "rgba(255, 255, 255, 0.08)",
    now: "#ff6b70",
    good: "#74d08c",
    "good-bg": "rgba(76, 175, 80, 0.17)",
    caution: "#f4c552",
    "caution-bg": "rgba(240, 165, 0, 0.17)",
    notrec: "#ff9f6e",
    "notrec-bg": "rgba(236, 106, 30, 0.2)",
    danger: "#ff8383",
    "danger-bg": "rgba(211, 47, 47, 0.22)",
    "dot-good": "#4cb862",
    "dot-caution": "#f2b600",
    "dot-notrec": "#ff7a33",
    "dot-danger": "#f05050",
    "s-great": "#5ec7f7",
    "s-good": "#2d8dc2",
    "s-fair": "#285b76",
    "s-poor": "#414b52",
    "ring-track": "#2b3237",
    "s-great-ink": "#04202f",
    "s-good-ink": "#03141d",
    "s-fair-ink": "#d4ebf7",
    "s-poor-ink": "#d3dbe1",
    av1: "#2a9fb0",
    av2: "#c46f9b",
    av3: "#8a7bd0",
    av4: "#b8902a",
    sun: "#f2b632",
    cloud: "#7d8a93",
    rain: "#5aa9e6",
    "chart-wind": "#63c7f6",
    "chart-fill": "rgba(99, 199, 246, 0.1)",
    "chart-gust": "#8b98a2",
    "chart-spread": "rgba(99, 199, 246, 0.14)",
    window: "rgba(3, 169, 244, 0.14)",
    tide: "#63c7f6",
    "tide-fill": "rgba(3, 169, 244, 0.15)",
    flood: "#63c7f6",
    ebb: "#b493ea",
    "map-ink": "#ffffff",
    "map-chip": "rgba(9, 18, 25, 0.74)",
    scrim: "rgba(0, 0, 0, 0.6)",
    "shadow-pop": "0 18px 44px rgba(0, 0, 0, 0.6), 0 3px 10px rgba(0, 0, 0, 0.4)",
  },
};

/**
 * Return a palette as CSS custom properties, such as `--sc-fg`. When the
 * panel follows Home Assistant, the themed colors use the theme's variables
 * with the palette's values as fallbacks.
 */
export function paletteCss(mode: Mode, followTheme = true): string {
  return Object.entries(PALETTES[mode])
    .map(([name, value]) => {
      const variable = followTheme ? THEME_VARIABLES[name] : undefined;
      return `--sc-${name}: ${variable ? `var(--${variable}, ${value})` : value};`;
    })
    .join("\n");
}

type Rgba = [number, number, number, number];

function parse(color: string): Rgba {
  const hex = /^#([0-9a-f]{6})$/i.exec(color);
  if (hex) {
    const value = parseInt(hex[1], 16);
    return [value >> 16, (value >> 8) & 255, value & 255, 1];
  }
  const rgba = /^rgba\((\d+), (\d+), (\d+), ([\d.]+)\)$/.exec(color);
  if (rgba) return [+rgba[1], +rgba[2], +rgba[3], +rgba[4]];
  throw new Error(`Unsupported color ${color}`);
}

function luminance([r, g, b]: Rgba): number {
  const [lr, lg, lb] = [r, g, b].map((channel) => {
    const c = channel / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
}

/** Lay a color that may be see-through over an opaque one. */
function over(top: Rgba, base: Rgba): Rgba {
  const a = top[3];
  return [0, 1, 2].map((i) => top[i] * a + base[i] * (1 - a)) as unknown as Rgba;
}

/**
 * Return the WCAG contrast ratio of text on a background. A see-through
 * background is first laid over `base`.
 */
export function contrast(text: string, background: string, base = "#ffffff"): number {
  const bg = over(parse(background), parse(base));
  const fg = over(parse(text), bg);
  const [light, dark] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

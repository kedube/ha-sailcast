/**
 * SailCast follows the Home Assistant theme: its page, toolbar, cards and text
 * take the theme's colors, in light and dark mode. SailCast's own day and
 * night palettes fill in anything a theme doesn't set, and supply the deep sea
 * blue that marks SailCast's own parts. Green, amber, orange and red are kept
 * for safety ratings.
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
    fg: "#15222c",
    fg2: "#52616d",
    line: "#d9e1e7",
    line2: "#ebf0f3",
    "primary-ink": "#0a6a9c",
    "primary-tint": "rgba(3, 169, 244, 0.11)",
    btn: "#0a6a9c",
    "btn-ink": "#ffffff",
    focus: "#0a6a9c",
    sea: "#0b4466",
    "sea-ink": "#ffffff",
    "sea-ink2": "rgba(255, 255, 255, 0.76)",
    "sea-wave": "rgba(255, 255, 255, 0.08)",
    "sea-wave2": "rgba(255, 255, 255, 0.18)",
    "sea-wave3": "rgba(255, 255, 255, 0.05)",
    danger: "#b32222",
    "danger-bg": "#f8d6d6",
  },
  night: {
    page: "#101315",
    toolbar: "#1a1e21",
    "toolbar-ink": "#e3e8ec",
    card: "#1a1e21",
    fg: "#e3e8ec",
    fg2: "#a1adb7",
    line: "#2b3237",
    line2: "#22282c",
    "primary-ink": "#63c7f6",
    "primary-tint": "rgba(3, 169, 244, 0.17)",
    btn: "#4fbdf2",
    "btn-ink": "#05202f",
    focus: "#63c7f6",
    sea: "#0a344f",
    "sea-ink": "#ffffff",
    "sea-ink2": "rgba(255, 255, 255, 0.74)",
    "sea-wave": "rgba(255, 255, 255, 0.06)",
    "sea-wave2": "rgba(255, 255, 255, 0.15)",
    "sea-wave3": "rgba(255, 255, 255, 0.04)",
    danger: "#ff8383",
    "danger-bg": "rgba(211, 47, 47, 0.22)",
  },
};

/**
 * Return a palette as CSS custom properties, such as `--sc-fg`. Colors that
 * follow the Home Assistant theme keep the palette's value as a fallback.
 */
export function paletteCss(mode: Mode): string {
  return Object.entries(PALETTES[mode])
    .map(([name, value]) => {
      const variable = THEME_VARIABLES[name];
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

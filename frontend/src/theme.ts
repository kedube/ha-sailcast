/**
 * SailCast's own look: Paper Heart Design's "Under the Wave" palette, in a day
 * and a night version. The panel doesn't take colors from the Home Assistant
 * theme. Green, amber, orange and red are kept for safety ratings.
 */
export const WAVE = {
  abyss: "#00022b",
  deep: "#010e54",
  ocean: "#0855b1",
  sky: "#4fa5d8",
  foam: "#daeaf7",
} as const;

export type Mode = "day" | "night";

export const PALETTES: Record<Mode, Record<string, string>> = {
  day: {
    page: "#dce9f6",
    toolbar: "#f0f6fc",
    card: "#ffffff",
    fg: WAVE.abyss,
    fg2: "#3a4872",
    line: "#cadbee",
    line2: "#e2ecf6",
    "primary-ink": WAVE.ocean,
    "primary-tint": "rgba(8, 85, 177, 0.1)",
    btn: WAVE.ocean,
    "btn-ink": "#ffffff",
    focus: WAVE.ocean,
    danger: "#b32222",
    "danger-bg": "#f8d6d6",
  },
  night: {
    page: WAVE.abyss,
    toolbar: "#020837",
    card: "#0a1755",
    fg: WAVE.foam,
    fg2: "#9db7d8",
    line: "#1e2f78",
    line2: "#142264",
    "primary-ink": "#7cc0e8",
    "primary-tint": "rgba(79, 165, 216, 0.17)",
    btn: WAVE.sky,
    "btn-ink": WAVE.abyss,
    focus: "#7cc0e8",
    danger: "#ff8383",
    "danger-bg": "rgba(211, 47, 47, 0.22)",
  },
};

/** Return a palette as CSS custom properties, such as `--sc-fg`. */
export function paletteCss(mode: Mode): string {
  return Object.entries(PALETTES[mode])
    .map(([name, value]) => `--sc-${name}: ${value};`)
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

/**
 * Icons and small drawings: Material Design Icons like the rest of Home
 * Assistant, plus wind arrows, weather symbols, score rings and the wind dial
 * from the mockup.
 */
import {
  mdiAccount,
  mdiAlert,
  mdiBeach,
  mdiCalendarAlert,
  mdiCalendarCheck,
  mdiCalendarMonth,
  mdiCalendarPlus,
  mdiCalendarRemove,
  mdiCalendarSync,
  mdiCheck,
  mdiCheckCircle,
  mdiChevronRight,
  mdiClockOutline,
  mdiClose,
  mdiCog,
  mdiDelete,
  mdiFlagTriangle,
  mdiInformationOutline,
  mdiMapMarker,
  mdiPencil,
  mdiPlus,
  mdiSailBoat,
  mdiShieldAccount,
  mdiStar,
  mdiStarFourPoints,
  mdiThemeLightDark,
  mdiThermometerWater,
  mdiWaveArrowDown,
  mdiWaveArrowUp,
  mdiWaves,
  mdiWavesArrowRight,
  mdiWeatherNight,
  mdiWeatherPouring,
  mdiWeatherSunny,
  mdiWeatherSunsetDown,
  mdiWeatherSunsetUp,
  mdiWeatherWindy,
} from "@mdi/js";
import { svg, type SVGTemplateResult } from "lit";

import { band } from "./format";

export const ICONS = {
  ai: mdiStarFourPoints,
  account: mdiAccount,
  alert: mdiAlert,
  beach: mdiBeach,
  calAlert: mdiCalendarAlert,
  calCheck: mdiCalendarCheck,
  calMonth: mdiCalendarMonth,
  calPlus: mdiCalendarPlus,
  calRemove: mdiCalendarRemove,
  calSync: mdiCalendarSync,
  check: mdiCheck,
  chevR: mdiChevronRight,
  clock: mdiClockOutline,
  close: mdiClose,
  cog: mdiCog,
  current: mdiWavesArrowRight,
  del: mdiDelete,
  flag: mdiFlagTriangle,
  info: mdiInformationOutline,
  night: mdiWeatherNight,
  ok: mdiCheckCircle,
  pencil: mdiPencil,
  pin: mdiMapMarker,
  plus: mdiPlus,
  rain: mdiWeatherPouring,
  sail: mdiSailBoat,
  shield: mdiShieldAccount,
  star: mdiStar,
  sun: mdiWeatherSunny,
  sunrise: mdiWeatherSunsetUp,
  sunset: mdiWeatherSunsetDown,
  themeAuto: mdiThemeLightDark,
  tideDown: mdiWaveArrowDown,
  tideUp: mdiWaveArrowUp,
  water: mdiThermometerWater,
  waves: mdiWaves,
  windy: mdiWeatherWindy,
} as const;

export type IconName = keyof typeof ICONS;

/** An icon, hidden from screen readers; the text beside it says what it means. */
export function icon(name: IconName, className = ""): SVGTemplateResult {
  return svg`<svg class="i ${className}" viewBox="0 0 24 24" aria-hidden="true"><path d=${ICONS[name]}></path></svg>`;
}

/** An arrow pointing where the wind blows to, from a direction it blows from. */
export function arrow(direction: number, size = 14): SVGTemplateResult {
  return svg`<svg class="arr" width=${size} height=${size} viewBox="0 0 24 24" aria-hidden="true"
    style="transform:rotate(${Math.round((direction + 180) % 360)}deg)">
    <path d="M12 2.5 6 13h4.2v8.5h3.6V13H18z" fill="currentColor"></path></svg>`;
}

/** A weather symbol for a WMO weather code. */
export function weather(code: number | null | undefined): SVGTemplateResult {
  const value = code ?? 0;
  if (value >= 95) {
    return svg`<svg class="wx" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 15h10.6a4 4 0 0 0 .5-8 5.6 5.6 0 0 0-10.8 1.6A3.3 3.3 0 0 0 7 15z" fill="var(--sc-cloud)"/><path d="M12.5 13.5 9.5 18h3l-1.5 4.5 4.5-6h-3l1.5-3z" fill="var(--sc-sun)"/></svg>`;
  }
  if (value >= 51) {
    return svg`<svg class="wx" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 15.5h10.6a4 4 0 0 0 .5-8 5.6 5.6 0 0 0-10.8 1.6A3.3 3.3 0 0 0 7 15.5z" fill="var(--sc-cloud)"/><path d="M8.5 18l-1.2 2.6M12.5 18l-1.2 2.6M16.5 18l-1.2 2.6" stroke="var(--sc-rain)" stroke-width="1.8" stroke-linecap="round"/></svg>`;
  }
  if (value >= 45) {
    return svg`<svg class="wx" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8h16M3 12h18M5 16h14" stroke="var(--sc-cloud)" stroke-width="2" stroke-linecap="round"/></svg>`;
  }
  if (value >= 3) {
    return svg`<svg class="wx" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 19h10.6a4 4 0 0 0 .5-8 5.6 5.6 0 0 0-10.8 1.6A3.3 3.3 0 0 0 7 19z" fill="var(--sc-cloud)"/></svg>`;
  }
  if (value >= 1) {
    return svg`<svg class="wx" viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="9" r="3.6" fill="var(--sc-sun)"/><path d="M9 2.4v1.6M2.4 9H4M4.3 4.3l1.1 1.1M13.7 4.3l-1.1 1.1" stroke="var(--sc-sun)" stroke-width="1.6" stroke-linecap="round" fill="none"/><path d="M8 20.5h9.6a3.7 3.7 0 0 0 .4-7.3 5 5 0 0 0-9.7 1.3A3.1 3.1 0 0 0 8 20.5z" fill="var(--sc-cloud)"/></svg>`;
  }
  return svg`<svg class="wx" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.3" fill="var(--sc-sun)"/><path d="M12 2.6v2.4M12 19v2.4M2.6 12h2.4M19 12h2.4M5.4 5.4l1.7 1.7M16.9 16.9l1.7 1.7M5.4 18.6l1.7-1.7M16.9 7.1l1.7-1.7" stroke="var(--sc-sun)" stroke-width="1.8" stroke-linecap="round" fill="none"/></svg>`;
}

/**
 * A score in a ring filled in proportion, colored by its band. Without a
 * label the ring is decorative and the score is read out nearby.
 */
export function ring(score: number | null | undefined, label?: string): SVGTemplateResult {
  const value = score ?? 0;
  const text = score == null ? "–" : String(score);
  const fill =
    value > 0
      ? svg`<circle class="rv" cx="18" cy="18" r="15" pathLength="100" stroke-dasharray="${value} 100" transform="rotate(-90 18 18)"></circle>`
      : svg``;
  return label
    ? svg`<svg class="ring s-${band(value)}" viewBox="0 0 36 36" role="img" aria-label=${label}><circle class="rt" cx="18" cy="18" r="15"></circle>${fill}<text x="18" y="18" dy=".36em" text-anchor="middle">${text}</text></svg>`
    : svg`<svg class="ring s-${band(value)}" viewBox="0 0 36 36" aria-hidden="true"><circle class="rt" cx="18" cy="18" r="15"></circle>${fill}<text x="18" y="18" dy=".36em" text-anchor="middle">${text}</text></svg>`;
}

/** A compass dial with an arrow for the wind. */
export function dial(direction: number): SVGTemplateResult {
  return svg`<svg class="dial" viewBox="0 0 64 64" aria-hidden="true">
    <circle class="dial-ring" cx="32" cy="32" r="28"></circle>
    ${[0, 90, 180, 270].map(
      (angle) =>
        svg`<line class="dial-tick" x1="32" y1="5" x2="32" y2="10" transform="rotate(${angle} 32 32)"></line>`,
    )}
    <text class="dial-n" x="32" y="18" text-anchor="middle">N</text>
    <path class="dial-arrow" d="M32 14 38.5 32 33.6 30v17h-3.2V30L25.5 32z"
      transform="rotate(${Math.round((direction + 180) % 360)} 32 32)"></path>
  </svg>`;
}
